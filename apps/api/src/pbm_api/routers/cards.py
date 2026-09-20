"""Fiche carte (mission `v4-fiche`) : `GET /cards/{id}` (catalogue + prix + classement),
`GET /cards/{id}/price-history` (courbe de valeur par variante) et `GET /cards/{id}/my-items`
(exemplaires possédés par l'utilisateur courant, onglet « Mes exemplaires »). Session requise
sur les trois routes, comme `card_insights`/`in_game_study` : le classement personnel et la
liste des exemplaires sont scopés à l'utilisateur courant, jamais un `user_id` fourni côté
client (voir `CLAUDE.md`).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user
from pbm_api.cards.errors import CardNotFoundError
from pbm_api.cards.schemas import CardDetailResponse, MyCardItemOut, PriceHistoryResponse
from pbm_api.cards.service import (
    PriceHistoryRange,
    get_card_detail,
    get_price_history,
    list_my_items,
)
from pbm_api.db import get_session
from pbm_api.models import PriceVariant, User

router = APIRouter(prefix="/cards", tags=["cards"])

CARD_NOT_FOUND_MESSAGE = "carte introuvable"


@router.get("/{card_id}", response_model=CardDetailResponse)
async def get_card(
    card_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CardDetailResponse:
    try:
        return await get_card_detail(session, card_id, current_user)
    except CardNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CARD_NOT_FOUND_MESSAGE) from None


@router.get("/{card_id}/price-history", response_model=PriceHistoryResponse)
async def get_card_price_history(
    card_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
    variant: Annotated[PriceVariant, Query()] = PriceVariant.normal,
    range: Annotated[PriceHistoryRange, Query()] = "30",  # noqa: A002 — nom imposé par la mission
) -> PriceHistoryResponse:
    try:
        return await get_price_history(session, card_id, variant, range)
    except CardNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CARD_NOT_FOUND_MESSAGE) from None


@router.get("/{card_id}/my-items", response_model=list[MyCardItemOut])
async def get_card_my_items(
    card_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[MyCardItemOut]:
    try:
        return await list_my_items(session, current_user, card_id)
    except CardNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CARD_NOT_FOUND_MESSAGE) from None
