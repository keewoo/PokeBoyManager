"""Légalités et règle des Prix (`pbm_api.ingame.rules`) — purement déterministe, aucun appel IA
ni réseau.

Depuis le lot `fix-marqueur-recompenses` (01/10/2026), la règle des Prix se lit sur le **marqueur
de règle normalisé** du catalogue (`Card.prize_marker`), plus jamais sur le suffixe du nom
(R-13.7). Les cas « bout en bout » ci-dessous partent d'une **vraie carte** (nom + `rule_marker`
du catalogue), calculent son marqueur (`normalized_prize_marker`) et vérifient le nombre de
récompenses (`prize_rule_of`) — ils **échouent avec l'ancien code** qui rangeait une Méga-Évolution
Pokémon ex (« ex » → 3) ou une TAG TEAM (« GX » → 3) d'après le seul suffixe.
"""

import pytest

from pbm_api.catalog.prize_marker import normalized_prize_marker
from pbm_api.ingame.rules import legalities_of, prize_rule_of

_POK = "Pokémon"


def test_legalities_of_passes_through_catalog_flags():
    result = legalities_of(legal_standard=True, legal_expanded=False)
    assert result.standard is True
    assert result.expanded is False


def test_legalities_of_keeps_unknown_as_none():
    result = legalities_of(legal_standard=None, legal_expanded=None)
    assert result.standard is None
    assert result.expanded is None


# --- Règle des Prix bout en bout : vraie carte → marqueur → nombre de récompenses -----------

# (tcgdex_id, name, rule_marker, nombre de récompenses attendu)
_PRIZE_CASES = [
    ("mep-035", "Méga-Roitiflam-ex", "ex", 3),  # Méga-Évolution ex : finit par « ex », donne 3
    ("smp-SM166", "Magicarpe et Wailord GX", "ESCOUADE", 3),  # TAG TEAM : finit par « GX », donne 3
    ("smp-SM217", "Desséliande et Noctunoir GX", None, 3),  # TAG TEAM sans rule_marker
    ("swsh4-21", "Astronelle VMAX", "VMAX", 3),
    ("swshp-SWSH139", "Pikachu V-UNION", "V", 3),
    ("ex1-97", "Elektek ex", "ex", 2),
    ("xy5-19", "Desséliande EX", "EX", 2),  # Pokémon-EX
    ("xya-24a", "M-Élecsprint-ex", "MÉGA", 2),  # M Pokémon-EX (ère XY)
    ("sm6-73", "Zygarde GX", "GX", 2),
    ("swsh4-20", "Astronelle V", "V", 2),
    ("swsh10-190", "Fragilady de Hisui VSTAR", "V", 2),
    ("hgss2-90", "Entei & Raikou LÉGENDE (haut)", "LÉGENDE", 2),
    ("xy8-79", "Ossatueur TURBO", "TURBO", 1),  # BREAK
    ("dp5-97", "Carchacrok", "Niveau Sup", 1),  # LV.X
    ("swshp-SWSH230", "Évoli Radieux", None, 1),  # Radiant
    ("sm6-74", "Diancie ◇", None, 1),  # Prisme Étoile
    ("ex10-113", "Entei ☆", None, 1),  # Pokémon ★
    ("base1-58", "Pikachu", None, 1),  # ordinaire
]


@pytest.mark.parametrize(("tcgdex_id", "name", "rule_marker", "expected_prizes"), _PRIZE_CASES)
def test_prize_rule_end_to_end(
    tcgdex_id: str, name: str, rule_marker: str | None, expected_prizes: int
) -> None:
    marker = normalized_prize_marker(name=name, supertype=_POK, rule_marker=rule_marker)
    rule = prize_rule_of(marker=marker, supertype=_POK)
    assert rule.applies is True, tcgdex_id
    assert rule.prizes_taken == expected_prizes, tcgdex_id
    assert f"{expected_prizes} Prix" in rule.label, tcgdex_id


def test_tera_ex_marker_is_two_prizes() -> None:
    # Tera Pokémon ex (R-15.2) : indistinct d'un ex dans les données, mais le marqueur `tera_ex`
    # du moteur existe et donne bien 2.
    rule = prize_rule_of(marker="tera_ex", supertype=_POK)
    assert rule.prizes_taken == 2


def test_mega_ex_label_mentions_three_prizes() -> None:
    rule = prize_rule_of(marker="mega_ex", supertype=_POK)
    assert "3 Prix" in rule.label


# --- Hors Pokémon, marqueur absent, marqueur inconnu --------------------------------------


@pytest.mark.parametrize("supertype", ["Dresseur", "Énergie", "Trainer", "Energy", None])
def test_prize_rule_does_not_apply_outside_pokemon(supertype: str | None) -> None:
    rule = prize_rule_of(marker=None, supertype=supertype)
    assert rule.applies is False
    assert rule.prizes_taken is None
    assert "hors Pokémon" in rule.label


def test_unknown_marker_is_not_determined_never_guessed() -> None:
    rule = prize_rule_of(marker="inconnu", supertype=_POK)
    assert rule.applies is True
    assert rule.prizes_taken is None
    assert "non déterminé" in rule.label.lower()


def test_pokemon_without_marker_is_not_determined() -> None:
    # Un Pokémon dont le marqueur n'a pas été résolu (None) ne se range PAS « hors Pokémon » :
    # il est « non déterminé » — jamais un nombre deviné.
    rule = prize_rule_of(marker=None, supertype=_POK)
    assert rule.applies is True
    assert rule.prizes_taken is None
