"""`pbm_api.identification.reconciliation.reconcile` (mission `v3-identification` point 2) :
cascade numéro+extension -> numéro+nom -> recherche floue, score combiné (catalogue × confiance
moyenne des champs utilisés par le palier retenu), présélection au-delà de 0,9.

Avant ce lot, `pbm_api.identification` n'existait pas : chacun de ces tests échoue à la
collection (`ModuleNotFoundError`) et passe une fois le module ajouté.
"""

import uuid

import pytest

from pbm_api.identification.reconciliation import (
    PRESELECTION_THRESHOLD,
    reconcile,
    top_candidate_preselected,
)
from pbm_api.identification.schemas import CardExtraction
from pbm_api.models import Card, CardName, Set


@pytest.fixture
async def catalog_with_number_collision(db_session):
    """Deux extensions dont le même numéro `025` désigne des cartes différentes — le cas que la
    présélection par extension exacte doit départager, et que la recherche floue par nom seul
    (dernier palier) doit retrouver même sans numéro fiable."""
    suffix = uuid.uuid4().hex[:8]
    set_a = Set(code=f"sv01-{suffix}", name="Écarlate et Violet", total_cards=198)
    set_b = Set(code=f"sv02-{suffix}", name="Évolutions à Paldea", total_cards=200)
    db_session.add_all([set_a, set_b])
    await db_session.flush()

    pikachu_a = Card(set_id=set_a.id, number="025", name="Pikachu")
    pikachu_b = Card(set_id=set_b.id, number="025", name="Pikachu")
    raichu = Card(set_id=set_a.id, number="026", name="Raichu")
    db_session.add_all([pikachu_a, pikachu_b, raichu])
    await db_session.flush()
    db_session.add_all(
        [
            CardName(card_id=pikachu_a.id, language="fr", name="Pikachu"),
            CardName(card_id=pikachu_a.id, language="en", name="Pikachu"),
            CardName(card_id=pikachu_b.id, language="fr", name="Pikachu"),
            CardName(card_id=pikachu_b.id, language="en", name="Pikachu"),
            CardName(card_id=raichu.id, language="fr", name="Raichu"),
            CardName(card_id=raichu.id, language="en", name="Raichu"),
        ]
    )
    await db_session.flush()
    return {
        "set_a": set_a,
        "set_b": set_b,
        "pikachu_a": pikachu_a,
        "pikachu_b": pikachu_b,
        "raichu": raichu,
    }


def test_top_candidate_preselected_recomputes_from_stored_scores():
    """Politique de présélection ré-appliquée aux `combined_score` stockés (lot
    `pbm-parcours-validation`) : indispensable pour que les détections identifiées AVANT ce lot
    (drapeau `preselected` figé sous l'ancien seuil de 0,9 — les 143 d'Aymeric) profitent du
    nouveau seuil sans être réécrites."""
    # Drapeau figé à False, mais score au-dessus du seuil + candidat unique → présélectionné.
    assert top_candidate_preselected([{"combined_score": 0.82, "preselected": False}]) is True
    # Sous le seuil, quel que soit le drapeau stocké.
    assert top_candidate_preselected([{"combined_score": 0.49, "preselected": True}]) is False
    # Ex-aequo (numéro+nom dans deux extensions) : marge non atteinte → non présélectionné.
    assert (
        top_candidate_preselected([{"combined_score": 0.7}, {"combined_score": 0.7}]) is False
    )
    # Nettement détaché du suivant → présélectionné.
    assert top_candidate_preselected([{"combined_score": 0.8}, {"combined_score": 0.5}]) is True
    assert top_candidate_preselected([]) is False
    assert top_candidate_preselected(None) is False


async def test_reconcile_without_any_signal_returns_no_candidate(db_session):
    result = await reconcile(db_session, CardExtraction())
    assert result.tier == "aucun_indice"
    assert result.candidates == []


async def test_reconcile_number_and_exact_set_code_disambiguates(
    db_session, catalog_with_number_collision
):
    fixtures = catalog_with_number_collision
    extraction = CardExtraction(
        name="Pikachu",
        name_confidence=0.9,
        number="025",
        number_confidence=0.9,
        set_code=fixtures["set_a"].code,
        set_code_confidence=0.9,
    )

    result = await reconcile(db_session, extraction)

    assert result.tier == "numero_extension"
    assert result.candidates
    assert result.candidates[0].card_id == str(fixtures["pikachu_a"].id)


async def test_reconcile_falls_back_to_number_and_name_without_set_code(
    db_session, catalog_with_number_collision
):
    fixtures = catalog_with_number_collision
    extraction = CardExtraction(
        name="Pikachu", name_confidence=0.9, number="025", number_confidence=0.9
    )

    result = await reconcile(db_session, extraction)

    assert result.tier == "numero_nom"
    returned_ids = {c.card_id for c in result.candidates}
    assert returned_ids == {str(fixtures["pikachu_a"].id), str(fixtures["pikachu_b"].id)}


async def test_reconcile_falls_back_to_fuzzy_name_when_number_matches_nothing(
    db_session, catalog_with_number_collision
):
    """Le numéro lu ('999') ne correspond à aucune carte : le dernier palier retombe sur le nom
    seul, sans le numéro erroné qui écarterait sinon toute carte."""
    fixtures = catalog_with_number_collision
    extraction = CardExtraction(
        name="Raichu", name_confidence=0.85, number="999", number_confidence=0.6
    )

    result = await reconcile(db_session, extraction)

    assert result.tier == "nom_flou"
    assert result.candidates
    assert result.candidates[0].card_id == str(fixtures["raichu"].id)


async def test_reconcile_preselects_above_threshold_with_high_confidence(
    db_session, catalog_with_number_collision
):
    fixtures = catalog_with_number_collision
    extraction = CardExtraction(
        name="Pikachu",
        name_confidence=0.95,
        number="025",
        number_confidence=0.95,
        total=198,
        total_confidence=0.95,
        set_code=fixtures["set_a"].code,
        set_code_confidence=0.95,
    )

    result = await reconcile(db_session, extraction)

    assert result.candidates[0].combined_score > PRESELECTION_THRESHOLD
    assert result.candidates[0].preselected is True


async def test_reconcile_does_not_preselect_with_low_confidence(
    db_session, catalog_with_number_collision
):
    fixtures = catalog_with_number_collision
    extraction = CardExtraction(
        name="Pikachu",
        name_confidence=0.4,
        number="025",
        number_confidence=0.4,
        total=198,
        total_confidence=0.4,
        set_code=fixtures["set_a"].code,
        set_code_confidence=0.4,
    )

    result = await reconcile(db_session, extraction)

    assert result.candidates[0].preselected is False
    assert result.candidates[0].combined_score < PRESELECTION_THRESHOLD


async def test_reconcile_preselects_confident_unique_number_and_name(
    db_session, catalog_with_number_collision
):
    """Calibrage `pbm-parcours-validation` : un numéro+nom qui ne colle qu'à UNE carte (Raichu
    026, absent de l'autre extension) est présélectionné même sans code d'extension lu — le cas
    que « Tout ajouter » doit prendre en charge. L'ancien seuil de 0,9, inatteignable avec la
    somme de poids du score catalogue, ne présélectionnait jamais ce cas pourtant sûr."""
    fixtures = catalog_with_number_collision
    extraction = CardExtraction(
        name="Raichu", name_confidence=0.95, number="026", number_confidence=0.9
    )

    result = await reconcile(db_session, extraction)

    assert result.tier == "numero_nom"
    assert result.candidates[0].card_id == str(fixtures["raichu"].id)
    assert result.candidates[0].preselected is True


async def test_reconcile_does_not_preselect_ambiguous_number_and_name(
    db_session, catalog_with_number_collision
):
    """Le même numéro+nom (Pikachu 025) existe dans deux extensions : ex-aequo, aucun candidat
    présélectionné (marge `PRESELECTION_MARGIN`) — c'est à l'humain de trancher l'extension,
    « Tout ajouter » ne doit pas en choisir une au hasard."""
    extraction = CardExtraction(
        name="Pikachu", name_confidence=0.95, number="025", number_confidence=0.95
    )

    result = await reconcile(db_session, extraction)

    assert result.tier == "numero_nom"
    assert len(result.candidates) == 2
    assert all(candidate.preselected is False for candidate in result.candidates)


async def test_reconcile_never_preselects_name_only(db_session, catalog_with_number_collision):
    """Nom seul (numéro illisible) : le score plafonne sous le seuil (nom ≤ 0,5 × confiance),
    jamais présélectionné — plusieurs impressions partagent un nom. Le bon candidat reste
    proposé en tête, à un clic."""
    fixtures = catalog_with_number_collision
    extraction = CardExtraction(name="Raichu", name_confidence=0.95)

    result = await reconcile(db_session, extraction)

    assert result.tier == "nom_flou"
    assert result.candidates
    assert result.candidates[0].card_id == str(fixtures["raichu"].id)
    assert result.candidates[0].preselected is False
    assert result.candidates[0].combined_score < PRESELECTION_THRESHOLD
