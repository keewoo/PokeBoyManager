"""Classer une carte Énergie en « de base » ou « spéciale » (décision D10).

Deux régimes de légalité opposés en dépendent :
  - **Énergie de base** : fournie en quantité illimitée, jamais décomptée de la collection, non
    soumise à la règle des 4 exemplaires (mais comptée dans les 60 cartes) ;
  - **Énergie spéciale** : carte comme les autres — il faut la posséder, et la règle des 4
    s'applique.

La source de vérité est `Card.energy_type` (TCGdex `energyType` : "Normal"/"Special", posé par
`v7-decks-api` dans `catalog/import_service.py`). Pour les cartes importées AVANT cette colonne
(elle vaut alors `None`), on retombe sur le nom : l'ensemble des Énergies de base est fermé et
bien connu. Calibré sur les 514 cartes `supertype = "Énergie"` réellement présentes au
catalogue (FR), qui montrent deux pièges : l'Éclair s'écrit « Énergie Électrique » ET « Énergie
Electrik » (localisation ancienne), et la casse varie (« Énergie obscurité »). Les noms anglais
sont ajoutés par sécurité (une carte pourrait porter un nom EN).

Ne jamais classer sur la rareté : une Énergie de base existe aussi bien en « Commune » qu'en
« Sans Rareté », « Rare » ou « Magnifique rare » (full-art) — mesuré sur le catalogue.
"""

import unicodedata

# `category` TCGdex, en français au catalogue ("Énergie"), en anglais ailleurs ("Energy").
_ENERGY_SUPERTYPES = {"energie", "energy"}

# `energyType` TCGdex et quelques variantes défensives.
_BASIC_ENERGY_TYPES = {"normal", "basic", "base", "de base"}
_SPECIAL_ENERGY_TYPES = {"special", "speciale"}

# Noms d'Énergies de base, normalisés (accents ôtés, casse repliée, espaces réduits).
_BASIC_ENERGY_NAMES = {
    "energie plante",
    "energie feu",
    "energie eau",
    "energie electrique",
    "energie electrik",
    "energie psy",
    "energie combat",
    "energie obscurite",
    "energie metal",
    "energie fee",
    # Filet de sécurité anglais (Énergie de base) :
    "grass energy",
    "fire energy",
    "water energy",
    "lightning energy",
    "psychic energy",
    "fighting energy",
    "darkness energy",
    "metal energy",
    "fairy energy",
}


def normalize(text: str | None) -> str:
    """Minuscule, sans accents, espaces réduits — pour comparer des libellés de catalogue."""
    if not text:
        return ""
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(stripped.casefold().split())


def is_energy(supertype: str | None) -> bool:
    return normalize(supertype) in _ENERGY_SUPERTYPES


def is_basic_energy(supertype: str | None, name: str | None, energy_type: str | None) -> bool:
    """Vraie seulement pour une Énergie de base. `energy_type` prime ; à défaut, le nom tranche."""
    if not is_energy(supertype):
        return False
    et = normalize(energy_type)
    if et in _BASIC_ENERGY_TYPES:
        return True
    if et in _SPECIAL_ENERGY_TYPES:
        return False
    # `energy_type` absent (données importées avant la colonne) ou valeur inattendue : le nom.
    return normalize(name) in _BASIC_ENERGY_NAMES


def is_special_energy(supertype: str | None, name: str | None, energy_type: str | None) -> bool:
    return is_energy(supertype) and not is_basic_energy(supertype, name, energy_type)
