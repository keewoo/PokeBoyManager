"""Rapprochement TCGdex ↔ Pokémon TCG API (D3) — identifiants d'extension et de carte.

Les deux catalogues n'utilisent pas les mêmes identifiants d'extension : TCGdex zéro-remplit et
sépare les sous-extensions par un point (`sv01`, `sv03.5`), Pokémon TCG API les compacte sans
règle unique (`sv1`, `sv3pt5`, mais aussi `hgssp` → `hsp`, ou des séries dérivées comme les
McDonald's Collection). Pas de règle générique fiable : `SET_ID_OVERRIDES` est une capture des
cas réels, obtenue le 2026-09-19 en comparant `GET /v2/en/sets` (TCGdex) et `GET /v2/sets`
(Pokémon TCG API) et en repérant les extensions dont le nom correspond mais pas l'id. 43 cas trouvés
ce jour-là ; `test_reconciliation.py` fige un échantillon vérifié pour éviter une régression
silencieuse si la table est retouchée.
"""

SET_ID_OVERRIDES: dict[str, str] = {
    "lc": "base6",
    "bog": "bp",
    "hgssp": "hsp",
    "2011bw": "mcd11",
    "2012bw": "mcd12",
    "2014xy": "mcd14",
    "2015xy": "mcd15",
    "2016xy": "mcd16",
    "2017sm": "mcd17",
    "sm3.5": "sm35",
    "sm7.5": "sm75",
    "2018sm": "mcd18",
    "2019sm": "mcd19",
    "swsh3.5": "swsh35",
    "2021swsh": "mcd21",
    "swsh4.5": "swsh45",
    "swsh4.5sv": "swsh45sv",
    "swsh10.5": "pgo",
    "2022swsh": "mcd22",
    "swsh12.5": "swsh12pt5",
    "swsh12.5gg": "swsh12pt5gg",
    "sv01": "sv1",
    "sv02": "sv2",
    "sv03": "sv3",
    "sv03.5": "sv3pt5",
    "sv04": "sv4",
    "sv04.5": "sv4pt5",
    "sv05": "sv5",
    "sv06": "sv6",
    "sv06.5": "sv6pt5",
    "sv07": "sv7",
    "sv08": "sv8",
    "sv08.5": "sv8pt5",
    "sv09": "sv9",
    "sv10.5b": "zsv10pt5",
    "sv10.5w": "rsv10pt5",
    "me01": "me1",
    "me02": "me2",
    "me02.5": "me2pt5",
    "me03": "me3",
    "me04": "me4",
    "me05": "me5",
    "30th": "me55",
}


def resolve_ptcg_set_id(tcgdex_set_id: str, known_ptcg_set_ids: set[str]) -> str | None:
    """Retourne l'id Pokémon TCG API correspondant, ou None si aucun rapprochement fiable.

    Pas d'exception ici : un set non rapproché (promo régionale absente de l'autre catalogue,
    ex: TCGdex "wp"/"miscp") est un résultat normal, à consigner dans le rapport d'import —
    pas une panne.
    """
    override = SET_ID_OVERRIDES.get(tcgdex_set_id)
    if override is not None:
        return override if override in known_ptcg_set_ids else None
    return tcgdex_set_id if tcgdex_set_id in known_ptcg_set_ids else None


def normalize_card_number(number: str) -> str:
    """Numéro comparable entre catalogues : casse et zéros de tête ignorés (`"006"` == `"6"`)."""
    stripped = number.strip().upper()
    if stripped.isdigit():
        return str(int(stripped))
    return stripped


def match_card_number(
    tcgdex_local_id: str, ptcg_cards_by_number: dict[str, str]
) -> str | None:
    """`ptcg_cards_by_number` : numéro normalisé -> ptcg_id, déjà construit pour l'extension."""
    return ptcg_cards_by_number.get(normalize_card_number(tcgdex_local_id))
