"""Formats de jeu et légalité par format (mission `v7-decks-legalite`).

Trois formats, déduits des légalités portées par le catalogue (`Card.legal_standard`/
`Card.legal_expanded`, alimentés à l'import depuis TCGdex `legal.standard`/`legal.expanded`) :

  - **Standard** (`standard`) : rotation récente ; une carte est autorisée si `legal_standard`
    est vrai.
  - **Étendu** (`expanded`) : pool élargi ; autorisée si `legal_expanded` est vrai.
  - **Illimité** (`unlimited`) : aucune restriction de format — toute carte est autorisée.

Le format d'un deck est CHOISI par le joueur (`Deck.format`, défaut `standard`). Une carte est
« hors format » seulement quand sa légalité est explicitement FAUSSE pour le format retenu : une
légalité inconnue (`None`, fréquent sur de vieilles cartes non réévaluées) ne bloque pas — on ne
refuse pas une carte faute d'information (un repli silencieux serait de la bloquer par défaut).
Les Énergies de base sont toujours autorisées, dans tous les formats (elles ne portent pas
toujours de légalité au catalogue).
"""

STANDARD = "standard"
EXPANDED = "expanded"
UNLIMITED = "unlimited"

FORMATS = (STANDARD, EXPANDED, UNLIMITED)
DEFAULT_FORMAT = STANDARD

_LABELS = {STANDARD: "Standard", EXPANDED: "Étendu", UNLIMITED: "Illimité"}


def label(fmt: str) -> str:
    return _LABELS.get(fmt, fmt)


def is_valid(fmt: str | None) -> bool:
    return fmt in FORMATS


def card_in_format(
    fmt: str,
    *,
    is_basic_energy: bool,
    legal_standard: bool | None,
    legal_expanded: bool | None,
) -> bool:
    """La carte est-elle autorisée dans ce format ? Une légalité inconnue vaut « autorisée »
    (bénéfice du doute) : seule une légalité explicitement fausse rend la carte hors format."""
    if fmt == UNLIMITED or is_basic_energy:
        return True
    flag = legal_standard if fmt == STANDARD else legal_expanded
    return flag is not False
