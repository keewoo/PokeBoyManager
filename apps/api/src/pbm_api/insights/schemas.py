import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AnecdoteOut(BaseModel):
    text: str
    source_url: str


class CardInsightsResponse(BaseModel):
    card_id: uuid.UUID
    status: str  # "ready" | "no_context" | "no_ai_key"
    anecdotes: list[AnecdoteOut]
    generated_at: datetime | None


class ReportCardInsightRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
