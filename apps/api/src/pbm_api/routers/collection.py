"""`/me/collection` — grille filtrable (mission `v4-collection`) et détail d'un exemplaire avec
ses classements (mission `v4-ranking` point 2, première route de collection posée dans ce
dépôt : volontairement réduite aux champs nécessaires à ce lot-là).

Routes littérales (`""`, `/facets`) déclarées avant `/{item_id}` : FastAPI essaierait sinon de
parser leur segment comme un UUID et renverrait 422 plutôt que de les atteindre.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.collection import service
from pbm_api.collection.errors import CollectionItemNotFoundError, CollectionItemPhotoMissingError
from pbm_api.collection.schemas import (
    CollectionAggregates,
    CollectionFacets,
    CollectionFacetSet,
    CollectionListItem,
    CollectionListResponse,
    CollectionSort,
    CreateCollectionItemRequest,
    CreateCollectionItemResponse,
    UpdateCollectionItemRequest,
)
from pbm_api.collection.service import CollectionFilters
from pbm_api.db import get_session
from pbm_api.models import Card, PriceVariant, Set, User
from pbm_api.models.collection import CollectionItem
from pbm_api.pricing.valuation import item_value
from pbm_api.ranking.service import card_value_rank, collection_rank
from pbm_api.storage import StorageBackend, build_storage
from pbm_api.validation.errors import CardNotFoundError

router = APIRouter(prefix="/me/collection", tags=["collection"])

ITEM_NOT_FOUND_MESSAGE = "exemplaire introuvable"
CARD_NOT_FOUND_MESSAGE = "carte introuvable au catalogue"
ITEM_PHOTO_MISSING_MESSAGE = "cet exemplaire n'a pas de photo"

_storage = build_storage()


def get_storage() -> StorageBackend:
    return _storage


def _pct_change(current: Decimal | None, past: Decimal | None) -> Decimal | None:
    """`None` si l'une des deux valeurs manque, ou si la valeur de référence est nulle (variation
    en pourcentage d'une base à zéro non définie) — jamais un pourcentage inventé."""
    if current is None or past is None or past == 0:
        return None
    return (current - past) / past * 100


def _to_list_item(
    row: service.CollectionRow,
    values_eur: dict[uuid.UUID, Decimal | None],
    values_30d_eur: dict[uuid.UUID, Decimal | None],
) -> CollectionListItem:
    value = values_eur.get(row.item.id)
    past = values_30d_eur.get(row.item.id)
    return CollectionListItem(
        id=row.item.id,
        card_id=row.card_id,
        set_id=row.set_id,
        card_name=row.card_name,
        card_number=row.card_number,
        set_name=row.set_name,
        set_code=row.set_code,
        series=row.series,
        rarity=row.rarity,
        card_type=row.card_type,
        language=row.item.language,
        variant=row.item.variant,
        condition_grade=row.item.condition_grade,
        counterfeit_suspected=row.item.counterfeit_suspected,
        purchase_price=row.item.purchase_price,
        purchase_currency=row.item.purchase_currency,
        acquired_at=row.item.acquired_at,
        value_eur=value,
        value_change_30d_eur=(value - past) if value is not None and past is not None else None,
        value_change_30d_pct=_pct_change(value, past),
        is_duplicate=row.is_duplicate,
    )


@router.get("", response_model=CollectionListResponse)
async def list_collection(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    q: Annotated[str | None, Query(max_length=255)] = None,
    set_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    series: Annotated[list[str] | None, Query()] = None,
    rarity: Annotated[list[str] | None, Query()] = None,
    card_type: Annotated[list[str] | None, Query()] = None,
    language: Annotated[list[str] | None, Query()] = None,
    variant: Annotated[list[PriceVariant] | None, Query()] = None,
    condition_grade: Annotated[list[str] | None, Query()] = None,
    value_min: Annotated[Decimal | None, Query(ge=0)] = None,
    value_max: Annotated[Decimal | None, Query(ge=0)] = None,
    acquired_from: date | None = None,
    acquired_to: date | None = None,
    duplicates: bool = False,
    counterfeit: bool = False,
    sort: CollectionSort = CollectionSort.value_desc,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=service.MAX_LIMIT)] = service.DEFAULT_LIMIT,
) -> CollectionListResponse:
    filters = CollectionFilters(
        q=q,
        set_ids=frozenset(set_id or []),
        series=frozenset(series or []),
        rarities=frozenset(rarity or []),
        card_types=frozenset(card_type or []),
        languages=frozenset(language or []),
        variants=frozenset(variant or []),
        condition_grades=frozenset(condition_grade or []),
        value_min=value_min,
        value_max=value_max,
        acquired_from=acquired_from,
        acquired_to=acquired_to,
        duplicates_only=duplicates,
        counterfeit_only=counterfeit,
    )
    page = await service.list_collection(session, current_user, filters, sort, cursor, limit)

    return CollectionListResponse(
        items=[_to_list_item(row, page.values_eur, page.values_30d_eur) for row in page.rows],
        next_cursor=page.next_cursor,
        aggregates=CollectionAggregates(
            items_total=page.items_total,
            items_priced=page.items_priced,
            items_missing_price=page.items_missing_price,
            total_value_eur=page.total_value_eur,
            value_change_7d_eur=page.value_change_7d_eur,
            value_change_30d_eur=page.value_change_30d_eur,
        ),
    )


@router.get("/facets", response_model=CollectionFacets)
async def get_collection_facets(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CollectionFacets:
    facets = await service.get_facets(session, current_user)
    return CollectionFacets(
        sets=[
            CollectionFacetSet(set_id=set_id, name=name, code=code)
            for set_id, name, code in facets.sets
        ],
        series=facets.series,
        rarities=facets.rarities,
        card_types=facets.card_types,
        languages=facets.languages,
        variants=facets.variants,
        condition_grades=facets.condition_grades,
    )


@router.post("", response_model=CreateCollectionItemResponse, status_code=status.HTTP_201_CREATED)
async def create_collection_item(
    payload: CreateCollectionItemRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> CreateCollectionItemResponse:
    try:
        items = await service.create_manual_items(session, current_user, payload)
    except CardNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CARD_NOT_FOUND_MESSAGE) from None
    return CreateCollectionItemResponse(collection_item_ids=[item.id for item in items])


async def _single_item_response(
    session: AsyncSession, user: User, item: CollectionItem
) -> CollectionListItem:
    """Même forme qu'une ligne de `GET /me/collection` (mission point 1), pour un seul
    exemplaire — inutile de recharger toute la page côté client après une correction."""
    card = await session.get(Card, item.card_id)
    set_row = await session.get(Set, card.set_id)
    duplicate_count = await session.execute(
        select(func.count())
        .select_from(CollectionItem)
        .where(CollectionItem.user_id == user.id, CollectionItem.card_id == item.card_id)
    )
    is_duplicate = duplicate_count.scalar_one() > 1

    as_of = date.today()
    value = await item_value(session, item, as_of=as_of, currency="EUR")
    past_value = await item_value(session, item, as_of=as_of - timedelta(days=30), currency="EUR")

    return CollectionListItem(
        id=item.id,
        card_id=item.card_id,
        set_id=card.set_id,
        card_name=card.name,
        card_number=card.number,
        set_name=set_row.name,
        set_code=set_row.code,
        series=set_row.series,
        rarity=card.rarity,
        card_type=card.supertype,
        language=item.language,
        variant=item.variant,
        condition_grade=item.condition_grade,
        counterfeit_suspected=item.counterfeit_suspected,
        purchase_price=item.purchase_price,
        purchase_currency=item.purchase_currency,
        acquired_at=item.acquired_at,
        value_eur=value,
        value_change_30d_eur=(
            value - past_value if value is not None and past_value is not None else None
        ),
        value_change_30d_pct=_pct_change(value, past_value),
        is_duplicate=is_duplicate,
    )


@router.patch("/{item_id}", response_model=CollectionListItem)
async def update_collection_item(
    item_id: uuid.UUID,
    payload: UpdateCollectionItemRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> CollectionListItem:
    try:
        item = await service.update_item(session, current_user, item_id, payload)
    except CollectionItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ITEM_NOT_FOUND_MESSAGE) from None

    return await _single_item_response(session, current_user, item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection_item(
    item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> None:
    try:
        await service.delete_item(session, current_user, item_id)
    except CollectionItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ITEM_NOT_FOUND_MESSAGE) from None


@router.get("/{item_id}/photo")
async def get_collection_item_photo(
    item_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Bascule « Ma photo » de la fiche carte (mission `v4-fiche`) — jamais la photo d'un
    exemplaire d'un autre utilisateur (`service.get_owned_item`, même filtre que le reste de ce
    routeur)."""
    try:
        data = await service.get_item_photo(session, storage, current_user, item_id)
    except CollectionItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ITEM_NOT_FOUND_MESSAGE) from None
    except CollectionItemPhotoMissingError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ITEM_PHOTO_MISSING_MESSAGE) from None
    return Response(content=data, media_type="image/jpeg")


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
        raise HTTPException(status.HTTP_404_NOT_FOUND, ITEM_NOT_FOUND_MESSAGE)

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
