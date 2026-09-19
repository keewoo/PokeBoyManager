"""`GET /me/collection/{item}` — mission `v4-ranking` point 2 : classements exposés sur
l'exemplaire d'un utilisateur. Première route de collection posée dans le dépôt (aucun autre
lot fusionné ne l'avait encore créée) : volontairement réduite aux champs nécessaires à ce lot
et à ses classements ; `v4-collection`/`v4-fiche` l'étendront (liste, PATCH/DELETE, données de
catalogue enrichies) sans revenir sur ce qui suit.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user
from pbm_api.db import get_session
from pbm_api.models import Card, PriceVariant, User
from pbm_api.models.collection import CollectionItem
from pbm_api.pricing.valuation import item_value
from pbm_api.ranking.service import card_value_rank, collection_rank

router = APIRouter(prefix="/me/collection", tags=["collection"])


class CollectionItemRanking(BaseModel):
    rarity_rank: int | None
    rarity_group_size: int | None
    value_percentile: float | None
    collection_rank: int | None
    collection_rank_total: int


class CollectionItemDetail(BaseModel):
    id: uuid.UUID
    card_id: uuid.UUID
    set_id: uuid.UUID
    language: str
    variant: PriceVariant
    condition_grade: str | None
    purchase_price: Decimal | None
    purchase_currency: str | None
    acquired_at: date | None
    value_eur: Decimal | None
    ranking: CollectionItemRanking


@router.get("/{item_id}", response_model=CollectionItemDetail)
async def get_collection_item(
    item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CollectionItemDetail:
    item = await session.get(CollectionItem, item_id)
    if item is None or item.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "exemplaire introuvable")

    value_eur = await item_value(session, item, currency="EUR")
    rank = await card_value_rank(session, item.card_id)
    coll_rank = await collection_rank(session, current_user.id, item)

    return CollectionItemDetail(
        id=item.id,
        card_id=item.card_id,
        set_id=rank.set_id if rank is not None else (await _card_set_id(session, item.card_id)),
        language=item.language,
        variant=item.variant,
        condition_grade=item.condition_grade,
        purchase_price=item.purchase_price,
        purchase_currency=item.purchase_currency,
        acquired_at=item.acquired_at,
        value_eur=value_eur,
        ranking=CollectionItemRanking(
            rarity_rank=rank.rarity_rank if rank is not None else None,
            rarity_group_size=rank.rarity_group_size if rank is not None else None,
            value_percentile=rank.value_percentile if rank is not None else None,
            collection_rank=coll_rank.position,
            collection_rank_total=coll_rank.total_priced,
        ),
    )


async def _card_set_id(session: AsyncSession, card_id: uuid.UUID) -> uuid.UUID:
    """`card_value_rank` n'a de ligne que pour les cartes déjà vues par le job de prix — avant
    le tout premier relevé (jeu de données fraîchement importé), on retombe sur le catalogue."""
    card = await session.get(Card, card_id)
    return card.set_id
