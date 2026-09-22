"""Normaliser le type élémentaire d'un Pokémon vers le code du jeu (lot `pbm-carte-remplacement`).

TCGdex expose `types` sous forme de tableau en langue d'import ("Plante", "Feu", "Eau"...), y
compris pour les cartes sans image — c'est ce qui rend le visuel de remplacement possible. On
retient le PREMIER type (une carte bi-type est rare en TCG et le fond n'en montre qu'un) et on le
ramène à l'un des onze codes des fonds (`apps/web/public/fonds/<code>-01.webp`…).

`None` pour un Dresseur, une Énergie, ou un type inconnu : le visuel retombe alors sur "colorless".
"""

import unicodedata

# Les onze codes de fonds. "colorless" = Incolore (Pokémon de type Normal chez TCGdex).
ELEMENT_CODES = frozenset(
    {
        "grass",
        "fire",
        "water",
        "lightning",
        "psychic",
        "fighting",
        "darkness",
        "metal",
        "dragon",
        "fairy",
        "colorless",
    }
)

# Libellés TCGdex normalisés (minuscule, sans accent) -> code. Français (langue d'import du
# catalogue) et anglais par sécurité, comme `pbm_api.decks.energy`.
_LABEL_TO_CODE = {
    # Français
    "plante": "grass",
    "feu": "fire",
    "eau": "water",
    "electrique": "lightning",
    "electrik": "lightning",  # localisation ancienne, cf. decks.energy
    "psy": "psychic",
    "combat": "fighting",
    "obscurite": "darkness",
    "metal": "metal",
    "dragon": "dragon",
    "fee": "fairy",
    "incolore": "colorless",
    # Anglais (filet de sécurité)
    "grass": "grass",
    "fire": "fire",
    "water": "water",
    "lightning": "lightning",
    "psychic": "psychic",
    "fighting": "fighting",
    "darkness": "darkness",
    "dark": "darkness",
    "steel": "metal",
    "fairy": "fairy",
    "colorless": "colorless",
    "normal": "colorless",
}


def _normalize(text: str) -> str:
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(stripped.casefold().split())


def element_code(types: object) -> str | None:
    """Code de type du jeu pour le PREMIER type d'un Pokémon, ou `None`.

    Accepte le tableau `types` de TCGdex (liste de libellés), un libellé isolé, ou `None`. Un
    libellé inconnu donne `None` plutôt qu'un code inventé — le visuel retombe sur "colorless"
    et l'inconnu reste visible en base (NULL), jamais masqué.
    """
    if types is None:
        return None
    if isinstance(types, str):
        first: object = types
    elif isinstance(types, (list, tuple)):
        if not types:
            return None
        first = types[0]
    else:
        return None
    if not isinstance(first, str):
        return None
    return _LABEL_TO_CODE.get(_normalize(first))
