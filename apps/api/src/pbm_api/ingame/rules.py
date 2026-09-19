"""Légalités et règle des Prix — mission `v4-jeu` point 1 : déterministe, uniquement depuis le
catalogue (`Card.legal_standard`/`legal_expanded`, déjà peuplés par TCGdex à l'import), jamais
un appel IA. La règle des Prix (combien de cartes Prix l'adversaire retourne en mettant KO cette
carte) se déduit du suffixe du nom, comme imprimé sur la carte elle-même (ex/V/VMAX/VSTAR/GX) —
une règle officielle et stable du jeu, pas une donnée qui varie d'une carte à l'autre au sein
d'une même catégorie.
"""

import re

from pydantic import BaseModel

_POKEMON_SUPERTYPE = "Pokemon"

# Ordre sans importance pour la justesse (voir tests) : l'ancre de fin de chaîne ($) empêche
# "V" de matcher la fin de "VMAX"/"VSTAR", chaque suffixe ne peut matcher qu'à son unique
# position réelle. VMAX seule prend 3 Prix ; ex/V/VSTAR/GX/EX (ancien et nouveau style) en
# prennent 2 ; une carte Pokémon sans suffixe est une carte standard, 1 Prix.
_SUFFIX_PATTERN = re.compile(r"(?:^|[\s-])(VMAX|VSTAR|GX|EX|ex|V)$")

_PRIZES_TAKEN_BY_SUFFIX: dict[str, int] = {
    "VMAX": 3,
    "VSTAR": 2,
    "GX": 2,
    "EX": 2,
    "ex": 2,
    "V": 2,
}

_SUFFIX_LABELS: dict[str, str] = {
    "VMAX": "carte VMAX",
    "VSTAR": "carte VSTAR",
    "GX": "carte GX",
    "EX": "carte-EX",
    "ex": "carte ex",
    "V": "carte V",
}


class PrizeRule(BaseModel):
    applies: bool
    prizes_taken: int | None
    label: str


class Legalities(BaseModel):
    standard: bool | None
    expanded: bool | None


def legalities_of(*, legal_standard: bool | None, legal_expanded: bool | None) -> Legalities:
    return Legalities(standard=legal_standard, expanded=legal_expanded)


def prize_rule_of(*, card_name: str, supertype: str | None) -> PrizeRule:
    """`supertype` vient de `Card.supertype` (catégorie TCGdex : "Pokemon"/"Trainer"/"Energy") —
    la règle des Prix ne concerne que les Pokémon, jamais un Dresseur ou une Énergie."""
    if supertype != _POKEMON_SUPERTYPE:
        return PrizeRule(applies=False, prizes_taken=None, label="Non applicable (hors Pokémon)")

    match = _SUFFIX_PATTERN.search(card_name.strip())
    if match is None:
        return PrizeRule(applies=True, prizes_taken=1, label="1 Prix (carte standard)")

    suffix = match.group(1)
    taken = _PRIZES_TAKEN_BY_SUFFIX[suffix]
    label = f"{taken} Prix ({_SUFFIX_LABELS[suffix]})"
    return PrizeRule(applies=True, prizes_taken=taken, label=label)
