"""Schémas Pydantic exposés par les routes d'anecdotes (`GET`/`POST` insights d'une carte)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AnecdoteOut(BaseModel):
    """Une anecdote sourcée, prête à afficher sur la fiche carte."""

    text: str
    source_url: str


class CardInsightsResponse(BaseModel):
    """Réponse de la fiche anecdotes d'une carte, selon l'état de génération."""

    card_id: uuid.UUID
    status: str  # "ready" | "no_context" | "no_ai_key"
    anecdotes: list[AnecdoteOut]
    generated_at: datetime | None


class ReportCardInsightRequest(BaseModel):
    """Corps du signalement d'une erreur sur les anecdotes d'une carte."""

    reason: str | None = Field(default=None, max_length=500)
