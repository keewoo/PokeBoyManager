"""`/me/wishlist` — liste de souhaits (mission `v6-import-export`) : cartes que l'utilisateur veut
acheter, avec un prix cible facultatif comparé au prix courant de marché.

Routes littérales déclarées avant `/{item_id}`, même précaution que
`pbm_api.routers.collection` : FastAPI essaierait sinon de parser leur segment comme un UUID.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.models import User
from pbm_api.validation.errors import CardNotFoundError
from pbm_api.wishlist import service
from pbm_api.wishlist.errors import WishlistItemAlreadyExistsError, WishlistItemNotFoundError
from pbm_api.wishlist.schemas import (
    CreateWishlistItemRequest,
    UpdateWishlistItemRequest,
    WishlistItemResponse,
    WishlistListResponse,
)

router = APIRouter(prefix="/me/wishlist", tags=["wishlist"])

ITEM_NOT_FOUND_MESSAGE = "vœu introuvable"
CARD_NOT_FOUND_MESSAGE = "carte introuvable au catalogue"
ALREADY_EXISTS_MESSAGE = "cette carte est déjà dans tes vœux"


def _to_response(row: service.WishlistRow) -> WishlistItemResponse:
    target_reached = (
        None
        if row.item.target_price_eur is None or row.current_price_eur is None
        else row.current_price_eur <= row.item.target_price_eur
    )
    return WishlistItemResponse(
        id=row.item.id,
        card_id=row.item.card_id,
        set_id=row.set_id,
        card_name=row.card_name,
        card_number=row.card_number,
        set_name=row.set_name,
        set_code=row.set_code,
        rarity=row.rarity,
        target_price_eur=row.item.target_price_eur,
        note=row.item.note,
        current_price_eur=row.current_price_eur,
        target_reached=target_reached,
    )


@router.get("", response_model=WishlistListResponse)
async def list_wishlist(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WishlistListResponse:
    rows = await service.list_rows(session, current_user)
    return WishlistListResponse(items=[_to_response(row) for row in rows])


@router.post("", response_model=WishlistItemResponse, status_code=status.HTTP_201_CREATED)
async def create_wishlist_item(
    payload: CreateWishlistItemRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> WishlistItemResponse:
    try:
        item = await service.create_item(session, current_user, payload)
    except CardNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CARD_NOT_FOUND_MESSAGE) from None
    except WishlistItemAlreadyExistsError:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_EXISTS_MESSAGE) from None
    row = await service.row_for_item(session, item)
    return _to_response(row)


@router.patch("/{item_id}", response_model=WishlistItemResponse)
async def update_wishlist_item(
    item_id: uuid.UUID,
    payload: UpdateWishlistItemRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> WishlistItemResponse:
    try:
        item = await service.update_item(session, current_user, item_id, payload)
    except WishlistItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ITEM_NOT_FOUND_MESSAGE) from None
    row = await service.row_for_item(session, item)
    return _to_response(row)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wishlist_item(
    item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> None:
    try:
        await service.delete_item(session, current_user, item_id)
    except WishlistItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ITEM_NOT_FOUND_MESSAGE) from None
