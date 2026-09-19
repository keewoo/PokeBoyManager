"""Classements d'une carte (mission `v4-ranking`, D6 : les trois classements — rang de
rareté, rang de valeur dans la collection, percentile de valeur dans l'extension).

Le rang de rareté et le percentile de valeur dans l'extension sont matérialisés (vue
`card_value_rank`, migration `11f10f8c0f40`) : ils portent sur le catalogue entier, coûteux à
recalculer à chaque requête (risque documenté du lot). Le rang de valeur dans la collection
personnelle porte sur quelques dizaines/centaines d'exemplaires au plus : calculé à la demande,
jamais matérialisé.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.models.collection import CollectionItem
from pbm_api.pricing.valuation import item_value


@dataclass(frozen=True)
class CardValueRank:
    card_id: uuid.UUID
    set_id: uuid.UUID
    reference_price_eur: Decimal | None
    value_percentile: float | None
    rarity_rank: int | None
    rarity_group_size: int | None


async def refresh_card_value_rank(session: AsyncSession) -> None:
    """Rafraîchit `card_value_rank` — à appeler après un relevé de prix réussi (mission point 1),
    jamais depuis une route utilisateur (verrou exclusif le temps du recalcul, catalogue entier)."""
    await session.execute(text("REFRESH MATERIALIZED VIEW card_value_rank"))
    await session.commit()


async def card_value_rank(
    session: AsyncSession, card_id: uuid.UUID
) -> CardValueRank | None:
    """`None` si la carte n'existe pas (ou pas encore dans la vue avant le premier relevé) —
    jamais un classement inventé."""
    result = await session.execute(
        text(
            "SELECT card_id, set_id, reference_price_eur, value_percentile, "
            "rarity_rank, rarity_group_size FROM card_value_rank WHERE card_id = :card_id"
        ),
        {"card_id": card_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return CardValueRank(
        card_id=row["card_id"],
        set_id=row["set_id"],
        reference_price_eur=row["reference_price_eur"],
        value_percentile=row["value_percentile"],
        rarity_rank=row["rarity_rank"],
        rarity_group_size=row["rarity_group_size"],
    )


@dataclass(frozen=True)
class CollectionRank:
    position: int | None
    total_priced: int
    total_items: int


async def collection_rank(
    session: AsyncSession,
    user_id: uuid.UUID,
    item: CollectionItem,
    as_of: date | None = None,
) -> CollectionRank:
    """Position de `item` par valeur décroissante parmi les exemplaires **valorisés** de
    `user_id` (mission point 2 : « n° 3 sur 128 »). Filtre toujours par `user_id` reçu en
    paramètre, jamais par un identifiant fourni côté client (isolation, voir `CLAUDE.md`).

    Rangs à égalité (`RANK` SQL standard, pas `DENSE_RANK`) : deux exemplaires de même valeur
    partagent le même rang, le suivant saute d'autant. Un exemplaire sans prix connu n'est pas
    classé (`position=None`) et ne compte pas dans `total_priced` — la même règle que
    `pricing.valuation.item_value` (jamais de valeur inventée)."""
    items = (
        (await session.execute(select(CollectionItem).where(CollectionItem.user_id == user_id)))
        .scalars()
        .all()
    )

    valued: list[tuple[uuid.UUID, Decimal]] = []
    for collection_item in items:
        value = await item_value(session, collection_item, as_of=as_of, currency="EUR")
        if value is not None:
            valued.append((collection_item.id, value))
    valued.sort(key=lambda pair: pair[1], reverse=True)

    position: int | None = None
    previous_value: Decimal | None = None
    rank = 0
    for index, (item_id, value) in enumerate(valued, start=1):
        if previous_value is None or value != previous_value:
            rank = index
            previous_value = value
        if item_id == item.id:
            position = rank
            break

    return CollectionRank(position=position, total_priced=len(valued), total_items=len(items))
