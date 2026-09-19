"""`pbm_api.identification.reconciliation.reconcile` (mission `v3-identification` point 2) :
cascade numéro+extension -> numéro+nom -> recherche floue, score combiné (catalogue × confiance
moyenne des champs utilisés par le palier retenu), présélection au-delà de 0,9.

Avant ce lot, `pbm_api.identification` n'existait pas : chacun de ces tests échoue à la
collection (`ModuleNotFoundError`) et passe une fois le module ajouté.
"""

import uuid

import pytest

from pbm_api.identification.reconciliation import PRESELECTION_THRESHOLD, reconcile
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
