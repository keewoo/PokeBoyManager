import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DeckCardInput(BaseModel):
    card_id: uuid.UUID
    quantity: int = Field(ge=1, le=60)


class CreateDeckRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    cards: list[DeckCardInput] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("le nom du deck ne peut pas être vide")
        return stripped


class RenameDeckRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("le nom du deck ne peut pas être vide")
        return stripped


class SetDeckCardRequest(BaseModel):
    quantity: int = Field(ge=1, le=60)


class LegalityIssueOut(BaseModel):
    code: str
    message: str
    card_id: uuid.UUID | None = None
    card_name: str | None = None
    detail: dict | None = None


class DeckLegalityOut(BaseModel):
    legal: bool
    card_count: int
    size_ok: bool
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
    owned: int
    missing: int
    in_collection: bool


class DeckSummary(BaseModel):
    id: uuid.UUID
    name: str
    card_count: int
    legal: bool
    created_at: datetime
    updated_at: datetime


class DeckDetail(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    cards: list[DeckCardOut]
    legality: DeckLegalityOut


class DeckListResponse(BaseModel):
    decks: list[DeckSummary]
