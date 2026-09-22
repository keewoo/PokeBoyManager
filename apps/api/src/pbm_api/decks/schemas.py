import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Formats de jeu (voir `pbm_api.decks.formats`). Le schéma refuse toute autre valeur (422).
DeckFormat = Literal["standard", "expanded", "unlimited"]


class DeckCardInput(BaseModel):
    card_id: uuid.UUID
    quantity: int = Field(ge=1, le=60)


class CreateDeckRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    format: DeckFormat = "standard"
    cards: list[DeckCardInput] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("le nom du deck ne peut pas être vide")
        return stripped


class UpdateDeckRequest(BaseModel):
    """`PATCH` partiel : renommer et/ou changer de format. Tout champ absent reste inchangé."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    format: DeckFormat | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("le nom du deck ne peut pas être vide")
        return stripped


class SetDeckCardRequest(BaseModel):
    quantity: int = Field(ge=1, le=60)


class LegalityIssueOut(BaseModel):
    code: str
    message: str
    severity: str  # "bloquant" | "avertissement"
    card_id: uuid.UUID | None = None
    card_name: str | None = None
    detail: dict | None = None


class DeckLegalityOut(BaseModel):
    legal: bool
    card_count: int
    size_ok: bool
    format: DeckFormat
    format_label: str
    issues: list[LegalityIssueOut]


class DeckCardOut(BaseModel):
    card_id: uuid.UUID
    card_name: str
    card_number: str
    set_id: uuid.UUID
    set_name: str
    set_code: str
    image_url: str | None
    supertype: str | None
    rarity: str | None
    quantity: int
    is_basic_energy: bool
    is_special_energy: bool
    is_basic_pokemon: bool
    owned: int
    missing: int
    in_collection: bool
    in_format: bool
    counterfeit_excluded: int


class DeckSummary(BaseModel):
    id: uuid.UUID
    name: str
    format: DeckFormat
    card_count: int
    legal: bool
    created_at: datetime
    updated_at: datetime


class DeckDetail(BaseModel):
    id: uuid.UUID
    name: str
    format: DeckFormat
    created_at: datetime
    updated_at: datetime
    cards: list[DeckCardOut]
    legality: DeckLegalityOut


class DeckListResponse(BaseModel):
    decks: list[DeckSummary]


# ----------------------------------------------------- import / export (v7-decks-import-export)


class ImportDeckRequest(BaseModel):
    """Liste de deck collée à importer (mission `v7-decks-import-export`).

    `dry_run=True` ne crée aucun deck : il renvoie seulement le rapport (aperçu avant validation).
    Une liste importée ne crée JAMAIS de cartes dans la collection (risque du lot)."""

    text: str = Field(min_length=1, max_length=20000)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    format: DeckFormat = "standard"
    dry_run: bool = False

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ImportCandidateOut(BaseModel):
    card_id: uuid.UUID
    name: str
    set_code: str
    set_name: str
    number: str
    score: float


class ImportLineOut(BaseModel):
    line_no: int
    raw: str
    # "matched" | "ambiguous" | "not_found" | "section"
    status: str
    quantity: int
    parsed_name: str | None = None
    parsed_set: str | None = None
    parsed_number: str | None = None
    notes: list[str] = Field(default_factory=list)
    card: ImportCandidateOut | None = None
    alternatives: list[ImportCandidateOut] = Field(default_factory=list)
    owned: int = 0
    missing: int = 0


class ImportReportOut(BaseModel):
    matched: int
    ambiguous: int
    not_found: int
    sections_ignored: int
    cards_added: int
    distinct_cards: int
    truncated: bool
    warnings: list[str] = Field(default_factory=list)
    lines: list[ImportLineOut] = Field(default_factory=list)


class ImportDeckResponse(BaseModel):
    """Rapport d'import + le deck créé (`None` si `dry_run`)."""

    report: ImportReportOut
    deck: DeckDetail | None = None
# ---- recherche de cartes du constructeur (mission `v7-decks-recherche`) ----
class DeckCardSearchItem(BaseModel):
    """Une carte du CATALOGUE dans le constructeur, annotée pour l'utilisateur courant :
    `owned_count` = exemplaires possédés, `in_deck_count` = exemplaires déjà dans le deck édité
    (0 sans `deck_id`). `value_eur` = prix de référence de `card_value_rank` (`None` si non
    encore relevé). `name` = nom localisé (FR par défaut), repli sur le nom canonique."""

    card_id: uuid.UUID
    set_id: uuid.UUID
    number: str
    name: str
    set_name: str
    set_code: str
    series: str | None
    rarity: str | None
    supertype: str | None
    hp: int | None
    image_url: str | None
    energy_type: str | None
    is_basic_energy: bool
    is_special_energy: bool
    value_eur: Decimal | None
    owned_count: int
    in_deck_count: int
    is_duplicate: bool


class DeckCardSearchResponse(BaseModel):
    items: list[DeckCardSearchItem]
    next_cursor: str | None


class DeckCardFacetSet(BaseModel):
    set_id: uuid.UUID
    name: str
    code: str


# ---- alertes, remplacements et historique (mission `v7-decks-collection-sync`) ----


class DeckAlertOut(BaseModel):
    """Une alerte « à compléter » — un deck qui vient de perdre une carte requise."""

    id: uuid.UUID
    deck_id: uuid.UUID
    deck_name: str
    event_type: str  # "card_incomplete"
    reason: str  # "removed" | "counterfeit"
    card_id: uuid.UUID | None
    card_name: str
    required: int
    owned: int
    missing: int
    read: bool
    created_at: datetime


class DeckAlertsResponse(BaseModel):
    """Fil d'alertes + compte des non lues (le badge de l'en-tête)."""

    alerts: list[DeckAlertOut]
    unread_count: int


class MarkAlertsReadRequest(BaseModel):
    """Marque des alertes comme lues. `event_ids` absent → toutes les non lues."""

    event_ids: list[uuid.UUID] | None = None


class DeckReplacementItem(BaseModel):
    """Une carte possédée proposée en remplacement, avec la raison de son classement."""

    card_id: uuid.UUID
    set_id: uuid.UUID | None = None
    number: str
    name: str
    set_name: str
    set_code: str
    supertype: str | None
    hp: int | None
    image_url: str | None
    owned_count: int
    reason: str


class DeckReplacementsResponse(BaseModel):
    card_id: uuid.UUID
    replacements: list[DeckReplacementItem]


class DeckHistoryResponse(BaseModel):
    deck_id: uuid.UUID
    events: list[DeckAlertOut]


class DeckCardSearchFacets(BaseModel):
    """Valeurs de filtre du constructeur, à l'échelle du catalogue, plus deux compteurs propres à
    l'utilisateur pour les bascules « mes cartes » / « doublons »."""

    sets: list[DeckCardFacetSet]
    rarities: list[str]
    card_types: list[str]
    hp_min: int | None
    hp_max: int | None
    owned_card_count: int
    duplicate_card_count: int
