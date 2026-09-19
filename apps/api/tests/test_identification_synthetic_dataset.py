"""Jeu de 100 cartes étiquetées et précision du rapprochement (mission point 5, objectif top-3
≥ 95 %).

⚠️ Aucune vraie photo ni clé IA réelle sur chimera (voir l'avertissement de
`pbm_api.identification.synthetic`) : ce test mesure la précision du *rapprochement catalogue*
(`pbm_api.identification.reconciliation.reconcile`) sur des extractions bruitées de façon
déterministe, pas la précision réelle d'un LLM de vision sur une vraie photo — seul un essai
avec une vraie clé (`scripts/test_identification_manual.py`) peut mesurer cela, hors de portée
de chimera aujourd'hui. Le taux top-1 est publié à titre informatif (aucun objectif chiffré en
mission), seul le taux top-3 est vérifié.

Avant ce lot, `pbm_api.identification` n'existait pas : ce test échoue à la collection et passe
une fois le module ajouté.
"""

import uuid

from pbm_api.identification.reconciliation import reconcile
from pbm_api.identification.synthetic import generate_dataset
from pbm_api.models import Card, CardName, Set

_TARGET_TOP3_RATE = 0.95


async def _seed_catalog(db_session, cases) -> dict[str, uuid.UUID]:
    # Pas de suffixe d'unicité ici (contrairement aux autres fixtures du dépôt) : le code
    # d'extension doit rester identique à `case.card.set_code`, comparé tel quel par le palier
    # « numéro + extension » (`extraction.set_code`) — la transaction de `db_session` est de
    # toute façon annulée en fin de test (`tests/conftest.py`), jamais commise.
    sets_by_code: dict[str, Set] = {}
    card_id_by_case: dict[str, uuid.UUID] = {}

    for case in cases:
        set_code = case.card.set_code
        set_row = sets_by_code.get(set_code)
        if set_row is None:
            set_row = Set(
                code=set_code, name=case.card.set_name, total_cards=case.card.total_cards
            )
            db_session.add(set_row)
            await db_session.flush()
            sets_by_code[set_code] = set_row

        card = Card(set_id=set_row.id, number=case.card.number, name=case.card.name_fr)
        db_session.add(card)
        await db_session.flush()
        db_session.add_all(
            [
                CardName(card_id=card.id, language="fr", name=case.card.name_fr),
                CardName(card_id=card.id, language="en", name=case.card.name_en),
            ]
        )
        card_id_by_case[case.id] = card.id

    await db_session.flush()
    return card_id_by_case


async def test_identification_precision_on_synthetic_dataset_meets_target(db_session):
    cases = generate_dataset()
    assert len(cases) == 100

    card_id_by_case = await _seed_catalog(db_session, cases)

    top1 = 0
    top3 = 0
    for case in cases:
        result = await reconcile(db_session, case.extraction)
        candidate_ids = [c.card_id for c in result.candidates]
        expected_id = str(card_id_by_case[case.id])

        if candidate_ids[:1] == [expected_id]:
            top1 += 1
        if expected_id in candidate_ids[:3]:
            top3 += 1

    total = len(cases)
    top1_rate = top1 / total
    top3_rate = top3 / total
    assert top3_rate >= _TARGET_TOP3_RATE, (
        f"top-3 {top3_rate:.1%} ({top3}/{total}), top-1 {top1_rate:.1%} ({top1}/{total})"
    )
