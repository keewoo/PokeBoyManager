"""Proxy `/img/cards/{id}` : sert l'image officielle, mise en cache dans le stockage objet au
premier accès (mission `v2-catalogue`, point 3). Pas de repli silencieux : une carte sans image
ou une image officielle injoignable renvoie une erreur explicite, jamais un succès vide.
"""

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.db import get_session
from pbm_api.models import Card
from pbm_api.s3 import ObjectStorage

router = APIRouter()

_storage = ObjectStorage()
_tcgdex = TcgdexClient()


def get_storage() -> ObjectStorage:
    return _storage


def get_tcgdex_client() -> TcgdexClient:
    return _tcgdex


@router.get("/img/cards/{card_id}")
async def get_card_image(
    card_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_storage)],
    tcgdex: Annotated[TcgdexClient, Depends(get_tcgdex_client)],
    size: str = Query("high", pattern="^(high|low)$"),
) -> Response:
    result = await session.execute(select(Card.image_url).where(Card.id == card_id))
    image_base_url = result.scalar_one_or_none()
    if image_base_url is None:
        raise HTTPException(status_code=404, detail="carte introuvable ou sans image officielle")

    object_key = f"cards/{card_id}/{size}.webp"
    cached = await storage.get(object_key)
    if cached is not None:
        return Response(content=cached, media_type="image/webp")

    try:
        image_bytes = await tcgdex.fetch_image_bytes(image_base_url, size)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"image officielle injoignable : {exc}"
        ) from exc

    await storage.put(object_key, image_bytes, "image/webp")
    return Response(content=image_bytes, media_type="image/webp")
