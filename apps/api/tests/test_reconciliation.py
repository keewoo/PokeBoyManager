"""Rapprochement TCGdex <-> Pokémon TCG API — cas figés le 2026-09-19 depuis les deux API en direct
(voir `pbm_api.catalog.reconciliation` pour la méthode). Un test échoue ici si la table de
correspondance est modifiée par erreur.
"""

from pbm_api.catalog.reconciliation import (
    SET_ID_OVERRIDES,
    match_card_number,
    normalize_card_number,
    resolve_ptcg_set_id,
)


def test_known_ptcg_set_ids():
    known = {"hsp", "sv3pt5", "swsh12pt5gg", "base6"}
    assert known.issubset(set(SET_ID_OVERRIDES.values()))


def test_resolve_ptcg_set_id_special_case_hgssp():
    """Cas particulier réel : TCGdex 'hgssp' correspond à l'id ptcg 'hsp', pas 'hgssp'."""
    known_ptcg_set_ids = {"hsp", "sv3pt5"}
    assert resolve_ptcg_set_id("hgssp", known_ptcg_set_ids) == "hsp"


def test_resolve_ptcg_set_id_modern_dotted_case():
    known_ptcg_set_ids = {"sv3pt5"}
    assert resolve_ptcg_set_id("sv03.5", known_ptcg_set_ids) == "sv3pt5"


def test_resolve_ptcg_set_id_direct_match_when_no_override():
    known_ptcg_set_ids = {"base1"}
    assert resolve_ptcg_set_id("base1", known_ptcg_set_ids) == "base1"


def test_resolve_ptcg_set_id_returns_none_when_unmatchable():
    """Une promo régionale sans équivalent (ex: TCGdex 'wp') n'est pas une erreur, juste un None."""
    known_ptcg_set_ids = {"base1", "sv3pt5"}
    assert resolve_ptcg_set_id("wp", known_ptcg_set_ids) is None


def test_resolve_ptcg_set_id_override_target_missing_returns_none():
    """L'override existe mais l'id cible n'apparaît pas (ex: API ptcg en liste partielle)."""
    known_ptcg_set_ids = {"base1"}
    assert resolve_ptcg_set_id("hgssp", known_ptcg_set_ids) is None


def test_normalize_card_number_strips_leading_zeros():
    assert normalize_card_number("006") == "6"
    assert normalize_card_number("6") == "6"


def test_normalize_card_number_keeps_non_numeric_uppercased():
    assert normalize_card_number("tg05") == "TG05"
    assert normalize_card_number("SWSH001") == "SWSH001"


def test_match_card_number():
    index = {"6": "sv3pt5-6", "TG05": "sv3pt5-tg05"}
    assert match_card_number("006", index) == "sv3pt5-6"
    assert match_card_number("tg05", index) == "sv3pt5-tg05"
    assert match_card_number("999", index) is None
