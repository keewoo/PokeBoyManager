"""Étude d'utilisation en jeu d'une carte (mission `v4-jeu`) — légalités et règle des Prix
(déterministe, catalogue), présence en tournoi (relevé périodique, `card_tournament_presence`)
et synthèse IA en cache partagé. Session requise (`get_current_user`) comme les anecdotes : la
première ouverture d'une carte jamais vue déclenche la synthèse avec la clé IA de l'utilisateur
courant."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.errors import AIProviderError
from pbm_api.ai.factory import create_provider
from pbm_api.auth.dependencies import get_current_user
from pbm_api.db import get_session
from pbm_api.ingame.schemas import (
    InGameStudyResponse,
    LegalitiesOut,
    PrizeRuleOut,
    StudyOut,
    TournamentDeckOut,
    TournamentPresenceOut,
)
from pbm_api.ingame.service import ProviderFactory, get_or_create_in_game_study
from pbm_api.models import Card, User

router = APIRouter(prefix="/cards", tags=["in-game-study"])

CARD_NOT_FOUND_MESSAGE = "Carte introuvable."
PROVIDER_ERROR_MESSAGE = "La génération de l'étude en jeu a échoué : {}"


def get_ai_provider_factory() -> ProviderFactory:
    return create_provider


async def _get_card_or_404(db: AsyncSession, card_id: uuid.UUID) -> Card:
    card = await db.get(Card, card_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CARD_NOT_FOUND_MESSAGE)
    return card


@router.get("/{card_id}/in-game-study", response_model=InGameStudyResponse)
async def get_in_game_study(
    card_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    provider_factory: ProviderFactory = Depends(get_ai_provider_factory),
) -> InGameStudyResponse:
    card = await _get_card_or_404(db, card_id)
    try:
        result = await get_or_create_in_game_study(
            db, card=card, current_user=current_user, provider_factory=provider_factory
        )
    except AIProviderError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, PROVIDER_ERROR_MESSAGE.format(exc.user_message)
        ) from exc

    return InGameStudyResponse(
        card_id=card_id,
        legalities=LegalitiesOut(
            standard=result.legalities.standard, expanded=result.legalities.expanded
        ),
        prize_rule=PrizeRuleOut(
            applies=result.prize_rule.applies,
            prizes_taken=result.prize_rule.prizes_taken,
            label=result.prize_rule.label,
        ),
        attacks=result.attacks,
        abilities=result.abilities,
        tournament_presence=TournamentPresenceOut(
            status=result.tournament_status.value,
            source_url=result.tournament_source_url,
            checked_at=result.tournament_checked_at,
            decks=[TournamentDeckOut(**deck) for deck in result.tournament_decks],
        ),
        study=StudyOut(
            status=result.study_status,
            text=result.study_text,
            generated_at=result.study_generated_at,
        ),
    )
