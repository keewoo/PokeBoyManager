"""Fiche carte (mission `v4-fiche`) : `GET /cards/{id}` (catalogue + prix + classement),
`GET /cards/{id}/price-history` (courbe de valeur par variante) et `GET /cards/{id}/my-items`
(exemplaires possédés par l'utilisateur courant, onglet « Mes exemplaires »). Session requise
sur ces trois routes, comme `card_insights`/`in_game_study` : le classement personnel et la
liste des exemplaires sont scopés à l'utilisateur courant, jamais un `user_id` fourni côté
client (voir `CLAUDE.md`).

`GET /cards/featured` (mission `pbm-front-accueil`) est **publique** — comme `/catalog/search`
et `/img/cards/{id}` — pour alimenter l'accueil visiteur, sans session. Déclarée avant
`/{card_id}` : un chemin littéral doit primer sur un paramètre, sinon FastAPI tente de parser
"featured" comme un UUID et renvoie 422 au lieu d'atteindre cette route.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user
from pbm_api.cards.errors import CardNotFoundError
from pbm_api.cards.schemas import (
    CardDetailResponse,
    FeaturedCardOut,
    MyCardItemOut,
    PriceHistoryResponse,
)
from pbm_api.cards.service import (
    PriceHistoryRange,
    get_card_detail,
    get_price_history,
    list_featured_cards,
    list_my_items,
)
from pbm_api.db import get_session
from pbm_api.models import PriceVariant, User

router = APIRouter(prefix="/cards", tags=["cards"])

CARD_NOT_FOUND_MESSAGE = "carte introuvable"


@router.get("/featured", response_model=list[FeaturedCardOut])
async def get_featured_cards(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[FeaturedCardOut]:
    cards = await list_featured_cards(session)
    return [
        FeaturedCardOut(id=c.card_id, name=c.name, number=c.number, set_name=c.set_name)
        for c in cards
    ]


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
