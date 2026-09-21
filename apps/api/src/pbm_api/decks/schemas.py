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
