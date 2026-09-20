"""Fiche carte (mission `v4-fiche`) : catalogue + prix + classement pour l'en-tête et l'onglet
Valeur (`get_card_detail`, `get_price_history`), exemplaires possédés pour l'onglet « Mes
exemplaires » (`list_my_items`). Les onglets Histoire/En jeu ne passent pas par ce module : ils
réutilisent tels quels `GET /cards/{id}/insights` et `GET /cards/{id}/in-game-study` (missions
`v4-anecdotes`/`v4-jeu`), déjà en « génération à la demande si absente ».

`list_featured_cards` (mission `pbm-front-accueil`) sert l'accueil visiteur : neuf vraies cartes
du catalogue, pas de session requise (voir `pbm_api.routers.cards`).
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.cards.errors import CardNotFoundError
from pbm_api.cards.schemas import (
    CardDetailResponse,
    CardRankingOut,
    CardSetOut,
    MyCardItemOut,
    OwnedCollectionRankOut,
    PriceHistoryPoint,
    PriceHistoryResponse,
)
from pbm_api.models import Card, Detection, Set, User
from pbm_api.models.catalog import PriceVariant
from pbm_api.models.collection import CollectionItem
from pbm_api.pricing.exchange_rates import convert_to_eur, get_rate_to_eur
from pbm_api.pricing.valuation import item_value, price_history_eur, reference_price_eur
from pbm_api.ranking.service import CollectionRank, card_value_rank, collection_rank

PriceHistoryRange = Literal["7", "30", "365", "all"]

_RANGE_DAYS: dict[str, int | None] = {"7": 7, "30": 30, "365": 365, "all": None}


async def _get_card_and_set(session: AsyncSession, card_id: uuid.UUID) -> tuple[Card, Set]:
    card = await session.get(Card, card_id)
    if card is None:
        raise CardNotFoundError
    set_row = await session.get(Set, card.set_id)
    return card, set_row


async def _owned_items(
    session: AsyncSession, user_id: uuid.UUID, card_id: uuid.UUID
) -> list[CollectionItem]:
    result = await session.execute(
        select(CollectionItem).where(
            CollectionItem.user_id == user_id, CollectionItem.card_id == card_id
        )
    )
    return list(result.scalars().all())


@dataclass(frozen=True)
class _BestOwnedItem:
    item: CollectionItem
    value_eur: Decimal


async def _best_owned_item(
    session: AsyncSession, items: list[CollectionItem]
) -> _BestOwnedItem | None:
    """Le plus vraisemblable candidat pour le classement « n° X de ta collection » de l'en-tête
    (mission point 2, maquette) quand un utilisateur possède plusieurs exemplaires de la même
    carte : celui de plus forte valeur, jamais un choix arbitraire (premier/dernier ajouté)."""
    best: _BestOwnedItem | None = None
    for item in items:
        value = await item_value(session, item, currency="EUR")
        if value is None:
            continue
        if best is None or value > best.value_eur:
            best = _BestOwnedItem(item=item, value_eur=value)
    return best


async def get_card_detail(
    session: AsyncSession, card_id: uuid.UUID, user: User, as_of: date | None = None
) -> CardDetailResponse:
    card, set_row = await _get_card_and_set(session, card_id)
    as_of = as_of or date.today()

    prices_eur: dict[PriceVariant, Decimal | None] = {}
    for variant in PriceVariant:
        prices_eur[variant] = await reference_price_eur(session, card.id, variant, as_of)

    rank = await card_value_rank(session, card.id)
    ranking = CardRankingOut(
        rarity_rank=rank.rarity_rank if rank else None,
        rarity_group_size=rank.rarity_group_size if rank else None,
        value_percentile=rank.value_percentile if rank else None,
    )

    items = await _owned_items(session, user.id, card.id)
    collection_rank_out: OwnedCollectionRankOut | None = None
    if items:
        best = await _best_owned_item(session, items)
        if best is not None:
            rank_result: CollectionRank = await collection_rank(
                session, user.id, best.item, as_of=as_of
            )
            collection_rank_out = OwnedCollectionRankOut(
                position=rank_result.position, total_priced=rank_result.total_priced
            )

    return CardDetailResponse(
        id=card.id,
        name=card.name,
        number=card.number,
        rarity=card.rarity,
        supertype=card.supertype,
        hp=card.hp,
        has_image=card.image_url is not None,
        illustrator=card.illustrator,
        set=CardSetOut(
            id=set_row.id,
            name=set_row.name,
            code=set_row.code,
            series=set_row.series,
            release_date=set_row.release_date,
            total_cards=set_row.total_cards,
            logo_url=set_row.logo_url,
        ),
        prices_eur=prices_eur,
        ranking=ranking,
        owned_count=len(items),
        collection_rank=collection_rank_out,
    )


async def get_price_history(
    session: AsyncSession,
    card_id: uuid.UUID,
    variant: PriceVariant,
    range_key: PriceHistoryRange,
    as_of: date | None = None,
) -> PriceHistoryResponse:
    card = await session.get(Card, card_id)
    if card is None:
        raise CardNotFoundError

    end = as_of or date.today()
    days = _RANGE_DAYS[range_key]
    start = end - timedelta(days=days) if days is not None else None

    raw_points = await price_history_eur(session, card.id, variant, start, end)
    return PriceHistoryResponse(
        card_id=card.id,
        variant=variant,
        points=[PriceHistoryPoint(day=day, price_eur=price) for day, price in raw_points],
    )


_EUR_QUANTUM = Decimal("0.000001")


async def _purchase_price_eur(
    session: AsyncSession, item: CollectionItem
) -> Decimal | None:
    if item.purchase_price is None or item.purchase_currency is None:
        return None
    rate = await get_rate_to_eur(session, item.purchase_currency, item.acquired_at or date.today())
    if rate is None:
        return None
    # `Decimal.quantize` plutôt que la division brute de `convert_to_eur` : une division dont le
    # quotient est "rond" (ex. 40 USD à 2 USD/EUR) renvoie sinon un `Decimal` en notation
    # scientifique (`2E+1`) que Pydantic sérialiserait tel quel, illisible sur la fiche.
    return convert_to_eur(item.purchase_price, rate).quantize(_EUR_QUANTUM)


async def list_my_items(
    session: AsyncSession, user: User, card_id: uuid.UUID
) -> list[MyCardItemOut]:
    card = await session.get(Card, card_id)
    if card is None:
        raise CardNotFoundError

    items = await _owned_items(session, user.id, card.id)
    items.sort(key=lambda i: i.acquired_at or date.min, reverse=True)

    detection_ids = {item.detection_id for item in items if item.detection_id is not None}
    detections: dict[uuid.UUID, Detection] = {}
    if detection_ids:
        result = await session.execute(
            select(Detection).where(Detection.id.in_(detection_ids))
        )
        detections = {detection.id: detection for detection in result.scalars().all()}

    out: list[MyCardItemOut] = []
    for item in items:
        value = await item_value(session, item, currency="EUR")
        purchase_price_eur = await _purchase_price_eur(session, item)
        detection = detections.get(item.detection_id) if item.detection_id else None
        out.append(
            MyCardItemOut(
                id=item.id,
                language=item.language,
                variant=item.variant,
                condition_grade=item.condition_grade,
                counterfeit_suspected=item.counterfeit_suspected,
                purchase_price=item.purchase_price,
                purchase_currency=item.purchase_currency,
                purchase_price_eur=purchase_price_eur,
                acquired_at=item.acquired_at,
                value_eur=value,
                has_photo=item.photo_s3_key is not None,
                condition_detail=detection.condition_assessment if detection else None,
            )
        )
    return out


FEATURED_CARDS_LIMIT = 9


@dataclass(frozen=True)
class FeaturedCard:
    card_id: uuid.UUID
    name: str
    number: str
    set_name: str


async def list_featured_cards(
    session: AsyncSession, limit: int = FEATURED_CARDS_LIMIT
) -> list[FeaturedCard]:
    """Neuf cartes pour la démonstration de l'accueil visiteur (mission `pbm-front-accueil`,
    point 1) : la carte la plus valorisée de chaque extension (`card_value_rank`, mission
    `v4-ranking` — déjà rafraîchie par le cron quotidien de prix), jusqu'à `limit` extensions
    distinctes. Stable d'un rendu à l'autre (ne change qu'au prochain `REFRESH MATERIALIZED
    VIEW`), jamais un tirage aléatoire par requête. Une carte sans image officielle ou sans
    prix connu n'est jamais retenue — la démonstration doit ressembler à ce que fait le
    produit, pas laisser deviner une vignette vide."""
    result = await session.execute(
        text(
            """
            SELECT card_id, name, number, set_name FROM (
                SELECT DISTINCT ON (cvr.set_id)
                    c.id AS card_id, c.name AS name, c.number AS number,
                    s.name AS set_name, cvr.reference_price_eur AS reference_price_eur
                FROM card_value_rank cvr
                JOIN cards c ON c.id = cvr.card_id
                JOIN sets s ON s.id = c.set_id
                WHERE c.image_url IS NOT NULL AND cvr.reference_price_eur IS NOT NULL
                ORDER BY cvr.set_id, cvr.reference_price_eur DESC
            ) top_per_set
            ORDER BY reference_price_eur DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    )
    return [
        FeaturedCard(card_id=row.card_id, name=row.name, number=row.number, set_name=row.set_name)
        for row in result
    ]
