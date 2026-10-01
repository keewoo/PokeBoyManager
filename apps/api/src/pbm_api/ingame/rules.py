"""Légalités et règle des Prix — la règle des Prix (combien de cartes Prix l'adversaire retourne
en mettant K.O. cette carte) se lit sur le **marqueur de règle normalisé** du catalogue
(`cards.prize_marker`, calculé par `pbm_api.catalog.prize_marker.normalized_prize_marker`),
**jamais** sur le suffixe du nom (R-13.7 : une Méga-Évolution Pokémon ex finit par « ex » mais
donne 3, une TAG TEAM finit par « GX » mais donne 3).

**Une seule table de vérité.** Le nombre de récompenses par marqueur vit dans le **moteur**
(`pbm_game.combat.fin.MARQUEUR_RECOMPENSES`, paquet pur). `apps/api` n'ayant pas le moteur en
dépendance (aucun workspace uv commun), on en garde ici une **copie**, tenue **égale** par le test
`tests/test_prize_marker.py::test_prizes_table_matches_engine` (il lit le source du moteur et
compare) : si l'une des deux tables change sans l'autre, la CI casse (lot
`fix-marqueur-recompenses`, R-13.3/R-13.4).

Déterministe, uniquement depuis le catalogue (`Card.legal_standard`/`legal_expanded` pour les
légalités, `Card.prize_marker` pour les Prix), jamais un appel IA.
"""

from pydantic import BaseModel

from pbm_api.catalog.prize_marker import MARQUEUR_INCONNU, POKEMON_SUPERTYPES

#: Copie de `pbm_game.combat.fin.MARQUEUR_RECOMPENSES` — tenue **égale** par
#: `tests/test_prize_marker.py::test_prizes_table_matches_engine`. Ne pas modifier l'une sans
#: l'autre (R-13.3). Chaque clé est un marqueur normalisé rendu par `normalized_prize_marker`.
PRIZES_BY_MARKER: dict[str, int] = {
    # 1 récompense (R-13.3).
    "ordinaire": 1,
    "radiant": 1,
    "break": 1,
    "prisme_etoile": 1,
    "lv_x": 1,
    "etoile": 1,
    # 2 récompenses (R-13.3).
    "ex": 2,
    "tera_ex": 2,
    "pokemon_ex": 2,
    "m_pokemon_ex": 2,
    "gx": 2,
    "v": 2,
    "vstar": 2,
    "legende": 2,
    # 3 récompenses (R-13.3).
    "mega_ex": 3,
    "vmax": 3,
    "tag_team": 3,
    "v_union": 3,
}

#: Libellé lisible par marqueur — un par clé de :data:`PRIZES_BY_MARKER`. L'égalité des jeux de
#: clés est garantie par `tests/test_prize_marker.py::test_labels_cover_every_marker`.
LABELS_BY_MARKER: dict[str, str] = {
    "ordinaire": "Pokémon ordinaire",
    "radiant": "Pokémon Radiant",
    "break": "Pokémon BREAK",
    "prisme_etoile": "Prisme Étoile ◇",
    "lv_x": "Pokémon LV.X",
    "etoile": "Pokémon ★",
    "ex": "Pokémon ex",
    "tera_ex": "Tera Pokémon ex",
    "pokemon_ex": "Pokémon-EX",
    "m_pokemon_ex": "M Pokémon-EX",
    "gx": "Pokémon-GX",
    "v": "Pokémon V",
    "vstar": "Pokémon VSTAR",
    "legende": "Pokémon LÉGENDE",
    "mega_ex": "Méga-Évolution Pokémon ex",
    "vmax": "Pokémon VMAX",
    "tag_team": "TAG TEAM",
    "v_union": "Pokémon V-UNION",
}

_LABEL_HORS_POKEMON = "Non applicable (hors Pokémon)"
_LABEL_NON_DETERMINE = "Récompenses non déterminées (marqueur de règle inconnu)"


class PrizeRule(BaseModel):
    applies: bool
    prizes_taken: int | None
    label: str


class Legalities(BaseModel):
    standard: bool | None
    expanded: bool | None


def legalities_of(*, legal_standard: bool | None, legal_expanded: bool | None) -> Legalities:
    return Legalities(standard=legal_standard, expanded=legal_expanded)


def prize_rule_of(*, marker: str | None, supertype: str | None) -> PrizeRule:
    """Règle des Prix d'une carte depuis son **marqueur normalisé** (`Card.prize_marker`) et son
    ``supertype`` (`Card.supertype`).

    - Hors Pokémon (Dresseur, Énergie) : ``applies=False`` — la règle ne s'applique pas.
    - Marqueur ``None`` (Pokémon sans marqueur résolu) ou :data:`MARQUEUR_INCONNU`, ou tout
      marqueur absent de la table : ``applies=True`` mais ``prizes_taken=None`` et le libellé
      « non déterminées » — on **ne devine jamais** un nombre (R-13.4/R-15.22).
    - Sinon : le nombre vient de l'**unique** table :data:`PRIZES_BY_MARKER` (R-13.3).
    """
    if supertype not in POKEMON_SUPERTYPES:
        return PrizeRule(applies=False, prizes_taken=None, label=_LABEL_HORS_POKEMON)

    if marker is None or marker == MARQUEUR_INCONNU or marker not in PRIZES_BY_MARKER:
        return PrizeRule(applies=True, prizes_taken=None, label=_LABEL_NON_DETERMINE)

    taken = PRIZES_BY_MARKER[marker]
    label = f"{taken} Prix ({LABELS_BY_MARKER[marker]})"
    return PrizeRule(applies=True, prizes_taken=taken, label=label)
