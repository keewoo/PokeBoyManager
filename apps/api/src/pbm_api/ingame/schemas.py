"""Schémas de réponse de la route d'étude en jeu — reflet exposable de `pbm_api.ingame.service`."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class LegalitiesOut(BaseModel):
    """Légalités Standard/Étendu d'une carte, `None` si non déterminées."""

    standard: bool | None
    expanded: bool | None


class PrizeRuleOut(BaseModel):
    """Règle des Prix d'une carte : s'applique-t-elle, combien, et son libellé lisible."""

    applies: bool
    prizes_taken: int | None
    label: str


class TournamentDeckOut(BaseModel):
    """Un deck relevé en tournoi pour cette carte, avec son classement."""

    deck_name: str
    tournament_name: str
    tournament_url: str | None
    placement: str


class TournamentPresenceOut(BaseModel):
    """Présence en tournoi relevée pour une carte, ou son absence (`status="unavailable"`)."""

    status: str  # "checked" | "unavailable"
    source_url: str | None
    checked_at: datetime | None
    decks: list[TournamentDeckOut]


class StudyOut(BaseModel):
    """Synthèse IA de l'étude en jeu, ou son absence si l'utilisateur n'a pas de clé IA."""

    status: str  # "ready" | "no_ai_key"
    text: str | None
    generated_at: datetime | None


class InGameStudyResponse(BaseModel):
    """Réponse complète de la route d'étude en jeu d'une carte."""

    card_id: uuid.UUID
    legalities: LegalitiesOut
    prize_rule: PrizeRuleOut
    attacks: list[dict] | None
    abilities: list[dict] | None
    tournament_presence: TournamentPresenceOut
    study: StudyOut
