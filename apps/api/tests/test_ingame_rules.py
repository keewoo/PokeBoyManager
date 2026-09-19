"""Légalités et règle des Prix (mission `v4-jeu` point 1) — purement déterministe, aucun appel
IA ni réseau : ces tests documentent la règle officielle du jeu (combien de cartes Prix
l'adversaire retourne en mettant KO chaque catégorie de carte)."""

import pytest

from pbm_api.ingame.rules import legalities_of, prize_rule_of


def test_legalities_of_passes_through_catalog_flags():
    result = legalities_of(legal_standard=True, legal_expanded=False)
    assert result.standard is True
    assert result.expanded is False


def test_legalities_of_keeps_unknown_as_none():
    result = legalities_of(legal_standard=None, legal_expanded=None)
    assert result.standard is None
    assert result.expanded is None


@pytest.mark.parametrize(
    ("card_name", "expected_prizes"),
    [
        ("Pikachu", 1),
        ("Dracaufeu-ex", 2),
        ("Charizard ex", 2),
        ("Miraidon V", 2),
        ("Arceus VSTAR", 2),
        ("Rayquaza VMAX", 3),
        ("Mewtwo-EX", 2),
        ("Latias & Latios-GX", 2),
    ],
)
def test_prize_rule_of_pokemon_suffix(card_name: str, expected_prizes: int) -> None:
    rule = prize_rule_of(card_name=card_name, supertype="Pokemon")
    assert rule.applies is True
    assert rule.prizes_taken == expected_prizes


def test_prize_rule_of_standard_pokemon_has_no_suffix_label():
    rule = prize_rule_of(card_name="Pikachu", supertype="Pokemon")
    assert rule.label == "1 Prix (carte standard)"


def test_prize_rule_of_vmax_label_mentions_three_prizes():
    rule = prize_rule_of(card_name="Rayquaza VMAX", supertype="Pokemon")
    assert "3 Prix" in rule.label


@pytest.mark.parametrize("supertype", ["Trainer", "Energy", None])
def test_prize_rule_of_does_not_apply_outside_pokemon(supertype: str | None) -> None:
    rule = prize_rule_of(card_name="Professeur Platane", supertype=supertype)
    assert rule.applies is False
    assert rule.prizes_taken is None


def test_prize_rule_of_does_not_match_ex_as_a_mere_word_ending():
    # "ex" ne doit compter que comme suffixe isolé (espace/tiret avant), jamais comme simple
    # terminaison d'un nom qui contient ces lettres par hasard.
    rule = prize_rule_of(card_name="Complex", supertype="Pokemon")
    assert rule.applies is True
    assert rule.prizes_taken == 1
