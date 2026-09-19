"""Anecdotes sourcées d'une carte (mission `v4-anecdotes`) — chaque route exige une session
(`get_current_user`) : la première ouverture d'une carte jamais vue déclenche une génération
avec la clé IA de l'utilisateur courant (mission point 2).

Les collaborateurs réseau (wikis, fournisseur IA) sont injectés par dépendance FastAPI, comme
`ProviderKeyTester` pour le coffre de clés (`pbm_api.routers.ai_keys`) : la suite automatisée
les remplace par des doubles déterministes (aucun wiki ni clé IA réels sur chimera)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.errors import AIProviderError
from pbm_api.ai.factory import create_provider
from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.insights.context import BULBAPEDIA_API_URL, POKEPEDIA_API_URL, MediaWikiClient
from pbm_api.insights.errors import NoAiKeyConfiguredError
from pbm_api.insights.schemas import AnecdoteOut, CardInsightsResponse, ReportCardInsightRequest
from pbm_api.insights.service import (
    ProviderFactory,
    get_or_create_card_insight,
    report_card_insight,
)
from pbm_api.models import Card, User

router = APIRouter(prefix="/cards", tags=["card-insights"])

CARD_NOT_FOUND_MESSAGE = "Carte introuvable."
PROVIDER_ERROR_MESSAGE = "La génération des anecdotes a échoué : {}"


def get_pokepedia_client() -> MediaWikiClient:
    return MediaWikiClient(POKEPEDIA_API_URL)


def get_bulbapedia_client() -> MediaWikiClient:
    return MediaWikiClient(BULBAPEDIA_API_URL)


def get_ai_provider_factory() -> ProviderFactory:
    return create_provider


async def _get_card_or_404(db: AsyncSession, card_id: uuid.UUID) -> Card:
    card = await db.get(Card, card_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CARD_NOT_FOUND_MESSAGE)
    return card


@router.get("/{card_id}/insights", response_model=CardInsightsResponse)
async def get_card_insights(
    card_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    pokepedia_client: MediaWikiClient = Depends(get_pokepedia_client),
    bulbapedia_client: MediaWikiClient = Depends(get_bulbapedia_client),
    provider_factory: ProviderFactory = Depends(get_ai_provider_factory),
) -> CardInsightsResponse:
    card = await _get_card_or_404(db, card_id)
    try:
        try:
            result = await get_or_create_card_insight(
                db,
                card=card,
                current_user=current_user,
                pokepedia_client=pokepedia_client,
                bulbapedia_client=bulbapedia_client,
                provider_factory=provider_factory,
            )
        except NoAiKeyConfiguredError:
            return CardInsightsResponse(
                card_id=card_id, status="no_ai_key", anecdotes=[], generated_at=None
            )
        except AIProviderError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, PROVIDER_ERROR_MESSAGE.format(exc.user_message)
            ) from exc
    finally:
        await pokepedia_client.aclose()
        await bulbapedia_client.aclose()

    anecdotes = [AnecdoteOut(**item) for item in (result.card_insight.anecdotes or [])]
    return CardInsightsResponse(
        card_id=card_id,
        status=result.status,
        anecdotes=anecdotes,
        generated_at=result.card_insight.generated_at,
    )


@router.post("/{card_id}/insights/report", status_code=status.HTTP_204_NO_CONTENT)
async def report_card_insights(
    card_id: uuid.UUID,
    payload: ReportCardInsightRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> None:
    await _get_card_or_404(db, card_id)
    await report_card_insight(db, card_id=card_id, user=current_user, reason=payload.reason)
