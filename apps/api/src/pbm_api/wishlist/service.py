"""Liste de souhaits (mission `v6-import-export`) : cartes que l'utilisateur veut acheter, avec
un prix cible facultatif — jamais un exemplaire de la collection, juste un vœu sur une carte du
catalogue. Le prix courant comparé au prix cible est celui de la variante normale
(`pbm_api.pricing.valuation.reference_price_eur`, même source que la fiche carte) : un vœu ne
porte ni langue ni variante, il n'y a donc rien d'autre à choisir.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.models import Card, PriceVariant, Set, User
from pbm_api.models.wishlist import WishlistItem
from pbm_api.pricing.valuation import reference_price_eur
from pbm_api.validation.errors import CardNotFoundError
from pbm_api.wishlist.errors import WishlistItemAlreadyExistsError, WishlistItemNotFoundError
from pbm_api.wishlist.schemas import CreateWishlistItemRequest, UpdateWishlistItemRequest


@dataclass(frozen=True)
class WishlistRow:
    item: WishlistItem
    card_name: str
    card_number: str
    set_id: uuid.UUID
    set_name: str
    set_code: str
    rarity: str | None
    current_price_eur: Decimal | None


async def _card_and_set(session: AsyncSession, card_id: uuid.UUID) -> tuple[Card, Set] | None:
    result = await session.execute(
        select(Card, Set).join(Set, Set.id == Card.set_id).where(Card.id == card_id)
    )
    return result.first()


async def create_item(
    session: AsyncSession, user: User, data: CreateWishlistItemRequest
) -> WishlistItem:
    card_and_set = await _card_and_set(session, data.card_id)
    if card_and_set is None:
        raise CardNotFoundError

    existing = await session.execute(
        select(WishlistItem).where(
            WishlistItem.user_id == user.id, WishlistItem.card_id == data.card_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise WishlistItemAlreadyExistsError

    item = WishlistItem(
        user_id=user.id,
        card_id=data.card_id,
        target_price_eur=data.target_price_eur,
        note=data.note,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def get_owned_item(session: AsyncSession, user: User, item_id: uuid.UUID) -> WishlistItem:
    item = await session.get(WishlistItem, item_id)
    if item is None or item.user_id != user.id:
        raise WishlistItemNotFoundError
    return item


async def update_item(
    session: AsyncSession, user: User, item_id: uuid.UUID, data: UpdateWishlistItemRequest
) -> WishlistItem:
    item = await get_owned_item(session, user, item_id)
    for field_name, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field_name, value)
    await session.commit()
    await session.refresh(item)
    return item


async def delete_item(session: AsyncSession, user: User, item_id: uuid.UUID) -> None:
    item = await get_owned_item(session, user, item_id)
    await session.delete(item)
    await session.commit()


async def list_rows(session: AsyncSession, user: User) -> list[WishlistRow]:
    result = await session.execute(
        select(WishlistItem, Card, Set)
        .join(Card, Card.id == WishlistItem.card_id)
        .join(Set, Set.id == Card.set_id)
        .where(WishlistItem.user_id == user.id)
        .order_by(WishlistItem.created_at.desc())
    )
    as_of = datetime.now(UTC).date()
    rows: list[WishlistRow] = []
    for item, card, card_set in result.all():
        price = await reference_price_eur(session, card.id, PriceVariant.normal, as_of)
        rows.append(
            WishlistRow(
                item=item,
                card_name=card.name,
                card_number=card.number,
                set_id=card_set.id,
                set_name=card_set.name,
                set_code=card_set.code,
                rarity=card.rarity,
                current_price_eur=price,
            )
        )
    return rows


async def row_for_item(session: AsyncSession, item: WishlistItem) -> WishlistRow:
    """Même forme qu'une ligne de `list_rows` (mission point 1), pour un seul vœu — inutile de
    recharger toute la liste après une création/correction (même patron que
    `pbm_api.collection.routers._single_item_response`)."""
    card_and_set = await _card_and_set(session, item.card_id)
    if card_and_set is None:
        raise CardNotFoundError
    card, card_set = card_and_set
    as_of = datetime.now(UTC).date()
    price = await reference_price_eur(session, card.id, PriceVariant.normal, as_of)
    return WishlistRow(
        item=item,
        card_name=card.name,
        card_number=card.number,
        set_id=card_set.id,
        set_name=card_set.name,
        set_code=card_set.code,
        rarity=card.rarity,
        current_price_eur=price,
    )
