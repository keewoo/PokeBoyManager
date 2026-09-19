"""`pbm_api.catalog.search` — appelée directement, sans passer par la route HTTP : c'est la
forme sous laquelle la reconnaissance (lot futur) la réutilisera, avec un nom et un numéro déjà
extraits d'une photo plutôt qu'une chaîne libre à analyser.
"""

import uuid

import pytest

from pbm_api.catalog.search import match_candidates, parse_query
from pbm_api.models import Card, CardName, Set


def test_parse_query_detects_number_only():
    assert parse_query("236") == parse_query("236")
    parsed = parse_query("236")
    assert parsed.number == "236"
    assert parsed.total is None
    assert parsed.name is None


def test_parse_query_detects_number_and_total():
    parsed = parse_query("236/217")
    assert parsed.number == "236"
    assert parsed.total == 217
    assert parsed.name is None


@pytest.mark.parametrize("raw", ["TG05", "GG10", "SV107", "XY121", "tg05"])
def test_parse_query_detects_promo_and_gallery_formats(raw):
    parsed = parse_query(raw)
    assert parsed.number == raw
    assert parsed.name is None


def test_parse_query_falls_back_to_name():
    parsed = parse_query("Pikachu VMAX")
    assert parsed.number is None
    assert parsed.name == "Pikachu VMAX"


def test_parse_query_empty_string():
    parsed = parse_query("   ")
    assert parsed == parse_query("")


@pytest.fixture
async def two_sets_two_cards(db_session):
    suffix = uuid.uuid4().hex[:8]
    set_a = Set(code=f"a-{suffix}", name="Écarlate et Violet", total_cards=198)
    set_b = Set(code=f"b-{suffix}", name="151", total_cards=165)
    db_session.add_all([set_a, set_b])
    await db_session.flush()

    card_a = Card(set_id=set_a.id, number="234", name="Miraidon-ex")
    card_b = Card(set_id=set_b.id, number="006", name="Mewtwo")
    db_session.add_all([card_a, card_b])
    await db_session.flush()
    db_session.add_all(
        [
            CardName(card_id=card_a.id, language="fr", name="Miraidon-ex"),
            CardName(card_id=card_a.id, language="en", name="Miraidon ex"),
            CardName(card_id=card_b.id, language="fr", name="Mewtwo"),
            CardName(card_id=card_b.id, language="en", name="Mewtwo"),
        ]
    )
    await db_session.flush()
    return {"set_a": set_a, "set_b": set_b, "card_a": card_a, "card_b": card_b}


async def test_match_candidates_without_criteria_returns_empty(db_session):
    assert await match_candidates(db_session) == []


async def test_match_candidates_by_name_scores_exact_match_highest(db_session, two_sets_two_cards):
    results = await match_candidates(db_session, nom="Mewtwo")
    assert results
    assert results[0].card_id == two_sets_two_cards["card_b"].id
    assert results[0].score == pytest.approx(0.5, abs=0.01)  # similarité 1.0 pondérée à 0.5


async def test_match_candidates_by_number_filters_strictly(db_session, two_sets_two_cards):
    results = await match_candidates(db_session, numero="234")
    assert {r.card_id for r in results} == {two_sets_two_cards["card_a"].id}


async def test_match_candidates_number_and_total_boosts_matching_set(
    db_session, two_sets_two_cards
):
    # Les deux cartes ont un numéro différent ici, donc pas de collision réelle : ce test isole
    # simplement l'effet du bonus `total` sur le score, indépendamment du filtre `numero`.
    results = await match_candidates(db_session, numero="234", total=198)
    assert results[0].score > (await match_candidates(db_session, numero="234"))[0].score


async def test_match_candidates_language_filter_restricts_results(db_session, two_sets_two_cards):
    fr_only = await match_candidates(db_session, nom="Miraidon ex", langue="fr")
    en_only = await match_candidates(db_session, nom="Miraidon ex", langue="en")
    assert all(r.language == "fr" for r in fr_only)
    assert all(r.language == "en" for r in en_only)
    assert {r.card_id for r in en_only} == {two_sets_two_cards["card_a"].id}


async def test_match_candidates_set_code_filters_strictly(db_session, two_sets_two_cards):
    set_b = two_sets_two_cards["set_b"]
    results = await match_candidates(db_session, nom="Mewtwo", set_code=set_b.code)
    assert results
    assert all(r.set_id == set_b.id for r in results)


async def test_match_candidates_unrelated_name_returns_empty(db_session, two_sets_two_cards):
    assert await match_candidates(db_session, nom="totalement inconnu xyzabc") == []
