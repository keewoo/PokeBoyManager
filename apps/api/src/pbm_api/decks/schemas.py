import uuid
from datetime import datetime
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
