import uuid
from datetime import datetime

from pydantic import BaseModel


class LegalitiesOut(BaseModel):
    standard: bool | None
    expanded: bool | None


class PrizeRuleOut(BaseModel):
    applies: bool
    prizes_taken: int | None
    label: str


class TournamentDeckOut(BaseModel):
    deck_name: str
    tournament_name: str
    tournament_url: str | None
    placement: str


class TournamentPresenceOut(BaseModel):
    status: str  # "checked" | "unavailable"
    source_url: str | None
    checked_at: datetime | None
    decks: list[TournamentDeckOut]


class StudyOut(BaseModel):
    status: str  # "ready" | "no_ai_key"
    text: str | None
    generated_at: datetime | None


class InGameStudyResponse(BaseModel):
    card_id: uuid.UUID
    legalities: LegalitiesOut
    prize_rule: PrizeRuleOut
    attacks: list[dict] | None
    abilities: list[dict] | None
    tournament_presence: TournamentPresenceOut
    study: StudyOut
