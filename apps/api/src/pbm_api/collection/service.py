"""Service de la page collection (mission `v4-collection`) : liste filtrable/triable/paginée
avec agrégats de valeur, ajout manuel d'un exemplaire, correction et suppression.

Le prix d'un exemplaire n'est stocké nulle part (calculé à la demande, comme
`pbm_api.pricing.valuation.item_value`) : `list_collection` charge le sous-ensemble filtré par
les critères "bon marché" (catalogue, langue, variante, état, dates) en une requête, calcule la
valeur de chaque exemplaire par lots (`bulk_item_values` — jamais une requête de prix par
exemplaire, mission point 4 : 5 000 exemplaires en moins de 300 ms), puis applique le filtre de
valeur, le tri et la pagination en mémoire. Un utilisateur de cette taille tient largement en
mémoire le temps d'une requête ; au-delà, le risque est documenté dans le compte rendu de clôture
plutôt que résolu par une matérialisation prématurée.
"""

import base64
import binascii
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.collection.errors import CollectionItemNotFoundError, CollectionItemPhotoMissingError
from pbm_api.collection.schemas import (
    CollectionSort,
    CreateCollectionItemRequest,
    UpdateCollectionItemRequest,
)
from pbm_api.models import Card, CardName, Set, User
from pbm_api.models.catalog import PriceVariant
from pbm_api.models.collection import CollectionItem
from pbm_api.pricing.valuation import bulk_item_values_multi
from pbm_api.storage import StorageBackend
from pbm_api.validation.errors import CardNotFoundError

DEFAULT_LIMIT = 60
MAX_LIMIT = 200
_VALUE_CHANGE_WINDOW_DAYS = (7, 30)


@dataclass(frozen=True)
class CollectionFilters:
    q: str | None = None
    set_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    series: frozenset[str] = field(default_factory=frozenset)
    rarities: frozenset[str] = field(default_factory=frozenset)
    card_types: frozenset[str] = field(default_factory=frozenset)
    languages: frozenset[str] = field(default_factory=frozenset)
    variants: frozenset[PriceVariant] = field(default_factory=frozenset)
    condition_grades: frozenset[str] = field(default_factory=frozenset)
    value_min: Decimal | None = None
    value_max: Decimal | None = None
    acquired_from: date | None = None
    acquired_to: date | None = None
    duplicates_only: bool = False
    counterfeit_only: bool = False


@dataclass(frozen=True)
class CollectionRow:
    item: CollectionItem
    card_id: uuid.UUID
    set_id: uuid.UUID
    card_name: str
    card_number: str
    set_name: str
    set_code: str
    series: str | None
    rarity: str | None
    card_type: str | None
    element_type: str | None
    hp: int | None
    is_duplicate: bool


@dataclass(frozen=True)
class CollectionPage:
    rows: list[CollectionRow]
    values_eur: dict[uuid.UUID, Decimal | None]
    values_30d_eur: dict[uuid.UUID, Decimal | None]
    next_cursor: str | None
    items_total: int
    items_priced: int
    items_missing_price: int
    total_value_eur: Decimal
    value_change_7d_eur: Decimal
    value_change_30d_eur: Decimal


@dataclass(frozen=True)
class CollectionFacetsResult:
    sets: list[tuple[uuid.UUID, str, str]]
    series: list[str]
    rarities: list[str]
    card_types: list[str]
    languages: list[str]
    variants: list[PriceVariant]
    condition_grades: list[str]


def _encode_cursor(item_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(str(item_id).encode()).decode()


def _decode_cursor(cursor: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, binascii.Error):
        # Curseur illisible (manipulé côté client, ou exemplaire supprimé entre deux pages) :
        # reprendre depuis le début plutôt qu'échouer la requête — dégradation documentée.
        return None


def _ilike_unaccent(column, pattern: str):
    needle = func.unaccent(func.lower(pattern))
    return func.unaccent(func.lower(func.coalesce(column, ""))).ilike(needle)


def _apply_cheap_filters(stmt, user_id: uuid.UUID, filters: CollectionFilters):
    stmt = stmt.where(CollectionItem.user_id == user_id)
    if filters.q:
        pattern = f"%{filters.q}%"
        stmt = stmt.where(
            or_(
                _ilike_unaccent(Card.name, pattern),
                _ilike_unaccent(CardName.name, pattern),
                _ilike_unaccent(Set.name, pattern),
                Card.number.ilike(pattern),
            )
        )
    if filters.set_ids:
        stmt = stmt.where(Card.set_id.in_(filters.set_ids))
    if filters.series:
        stmt = stmt.where(Set.series.in_(filters.series))
    if filters.rarities:
        stmt = stmt.where(Card.rarity.in_(filters.rarities))
    if filters.card_types:
        stmt = stmt.where(Card.supertype.in_(filters.card_types))
    if filters.languages:
        stmt = stmt.where(CollectionItem.language.in_(filters.languages))
    if filters.variants:
        stmt = stmt.where(CollectionItem.variant.in_(filters.variants))
    if filters.condition_grades:
        stmt = stmt.where(CollectionItem.condition_grade.in_(filters.condition_grades))
    if filters.acquired_from:
        stmt = stmt.where(CollectionItem.acquired_at >= filters.acquired_from)
    if filters.acquired_to:
        stmt = stmt.where(CollectionItem.acquired_at <= filters.acquired_to)
    if filters.counterfeit_only:
        stmt = stmt.where(CollectionItem.counterfeit_suspected.is_(True))
    return stmt


async def _duplicate_card_ids(session: AsyncSession, user_id: uuid.UUID) -> set[uuid.UUID]:
    result = await session.execute(
        select(CollectionItem.card_id)
        .where(CollectionItem.user_id == user_id)
        .group_by(CollectionItem.card_id)
        .having(func.count() > 1)
    )
    return set(result.scalars().all())


def _passes_value_filter(value: Decimal | None, filters: CollectionFilters) -> bool:
    if filters.value_min is None and filters.value_max is None:
        return True
    if value is None:
        return False
    if filters.value_min is not None and value < filters.value_min:
        return False
    return not (filters.value_max is not None and value > filters.value_max)


def _sort_key_builder(
    sort: CollectionSort,
    values_eur: dict[uuid.UUID, Decimal | None],
    values_30d_eur: dict[uuid.UUID, Decimal | None],
):
    """Chaque clé place les exemplaires sans donnée connue en dernier, dans les deux sens de
    tri — jamais mélangés au hasard parmi les exemplaires effectivement valorisés/datés."""
    if sort in (CollectionSort.value_desc, CollectionSort.value_asc):
        desc = sort is CollectionSort.value_desc

        def key(row: CollectionRow):
            value = values_eur.get(row.item.id)
            if value is None:
                return (1, Decimal(0))
            return (0, -value if desc else value)

        return key

    if sort in (CollectionSort.value_change_30d_desc, CollectionSort.value_change_30d_asc):
        desc = sort is CollectionSort.value_change_30d_desc

        def key(row: CollectionRow):
            current = values_eur.get(row.item.id)
            past = values_30d_eur.get(row.item.id)
            if current is None or past is None:
                return (1, Decimal(0))
            change = current - past
            return (0, -change if desc else change)

        return key

    if sort in (CollectionSort.acquired_at_desc, CollectionSort.acquired_at_asc):
        desc = sort is CollectionSort.acquired_at_desc

        def key(row: CollectionRow):
            acquired = row.item.acquired_at
            if acquired is None:
                return (1, 0)
            ordinal = acquired.toordinal()
            return (0, -ordinal if desc else ordinal)

        return key

    if sort is CollectionSort.number_asc:
        return lambda row: (row.card_number,)

    return lambda row: (row.card_name.lower(),)  # name_asc


async def list_collection(
    session: AsyncSession,
    user: User,
    filters: CollectionFilters,
    sort: CollectionSort,
    cursor: str | None,
    limit: int,
    as_of: date | None = None,
) -> CollectionPage:
    as_of = as_of or datetime.now(UTC).date()

    # Colonnes explicites plutôt que les entités `Card`/`Set` complètes : `Card` porte plusieurs
    # colonnes JSONB (attaques, capacités, faiblesses...) inutiles à une grille et coûteuses à
    # décoder à 5 000 lignes — mesuré : diviser par ~3 le temps de cette requête (mission point 4).
    stmt = (
        select(
            CollectionItem,
            Card.id,
            Card.set_id,
            Card.number,
            Card.name,
            Card.rarity,
            Card.supertype,
            Card.element_type,
            Card.hp,
            Set.name,
            Set.code,
            Set.series,
            CardName.name,
        )
        .join(Card, Card.id == CollectionItem.card_id)
        .join(Set, Set.id == Card.set_id)
        .outerjoin(
            CardName,
            and_(CardName.card_id == Card.id, CardName.language == CollectionItem.language),
        )
    )
    stmt = _apply_cheap_filters(stmt, user.id, filters)

    result = await session.execute(stmt)
    rows_raw = result.all()
    duplicate_card_ids = await _duplicate_card_ids(session, user.id)

    rows = [
        CollectionRow(
            item=item,
            card_id=card_id,
            set_id=card_set_id,
            card_name=localized_name or card_name,
            card_number=card_number,
            set_name=set_name,
            set_code=set_code,
            series=series,
            rarity=rarity,
            card_type=supertype,
            element_type=element_type,
            hp=hp,
            is_duplicate=card_id in duplicate_card_ids,
        )
        for (
            item,
            card_id,
            card_set_id,
            card_number,
            card_name,
            rarity,
            supertype,
            element_type,
            hp,
            set_name,
            set_code,
            series,
            localized_name,
        ) in rows_raw
    ]

    items = [row.item for row in rows]
    # Une seule requête de prix pour les 3 dates de référence (aujourd'hui, -7 j, -30 j) —
    # `bulk_item_values_multi` plutôt que trois appels séquentiels à `bulk_item_values` : mesuré,
    # supprime deux allers-retours SQL sur les trois (mission point 4).
    as_of_dates = (as_of, *(as_of - timedelta(days=d) for d in _VALUE_CHANGE_WINDOW_DAYS))
    values_by_date = await bulk_item_values_multi(session, items, as_of_dates, currency="EUR")
    values_eur = values_by_date[as_of]
    window_values = {
        window_days: values_by_date[as_of - timedelta(days=window_days)]
        for window_days in _VALUE_CHANGE_WINDOW_DAYS
    }
    values_30d_eur = window_values[30]

    filtered_rows = [
        row
        for row in rows
        if _passes_value_filter(values_eur.get(row.item.id), filters)
        and (not filters.duplicates_only or row.is_duplicate)
    ]
    filtered_rows.sort(key=_sort_key_builder(sort, values_eur, values_30d_eur))

    start_index = 0
    cursor_id = _decode_cursor(cursor) if cursor else None
    if cursor_id is not None:
        for index, row in enumerate(filtered_rows):
            if row.item.id == cursor_id:
                start_index = index + 1
                break

    limit = min(limit, MAX_LIMIT)
    page_rows = filtered_rows[start_index : start_index + limit]
    has_more = start_index + limit < len(filtered_rows)
    next_cursor = _encode_cursor(page_rows[-1].item.id) if has_more and page_rows else None

    def _total(values: dict[uuid.UUID, Decimal | None]) -> Decimal:
        return sum(
            (v for v in (values.get(row.item.id) for row in filtered_rows) if v is not None),
            Decimal("0"),
        )

    total_value_eur = _total(values_eur)
    items_priced = sum(1 for row in filtered_rows if values_eur.get(row.item.id) is not None)

    return CollectionPage(
        rows=page_rows,
        values_eur=values_eur,
        values_30d_eur=values_30d_eur,
        next_cursor=next_cursor,
        items_total=len(filtered_rows),
        items_priced=items_priced,
        items_missing_price=len(filtered_rows) - items_priced,
        total_value_eur=total_value_eur,
        value_change_7d_eur=total_value_eur - _total(window_values[7]),
        value_change_30d_eur=total_value_eur - _total(window_values[30]),
    )


async def get_facets(session: AsyncSession, user: User) -> CollectionFacetsResult:
    stmt = (
        select(
            Set.id,
            Set.name,
            Set.code,
            Set.series,
            Card.rarity,
            Card.supertype,
            CollectionItem.language,
            CollectionItem.variant,
            CollectionItem.condition_grade,
        )
        .select_from(CollectionItem)
        .join(Card, Card.id == CollectionItem.card_id)
        .join(Set, Set.id == Card.set_id)
        .where(CollectionItem.user_id == user.id)
    )
    rows = (await session.execute(stmt)).all()

    sets: dict[uuid.UUID, tuple[str, str]] = {}
    series: set[str] = set()
    rarities: set[str] = set()
    card_types: set[str] = set()
    languages: set[str] = set()
    variants: set[PriceVariant] = set()
    condition_grades: set[str] = set()

    for set_id, set_name, set_code, serie, rarity, card_type, language, variant, grade in rows:
        sets[set_id] = (set_name, set_code)
        if serie:
            series.add(serie)
        if rarity:
            rarities.add(rarity)
        if card_type:
            card_types.add(card_type)
        languages.add(language)
        variants.add(variant)
        if grade:
            condition_grades.add(grade)

    sets_list = [(set_id, name, code) for set_id, (name, code) in sets.items()]
    return CollectionFacetsResult(
        sets=sorted(sets_list, key=lambda row: row[1]),
        series=sorted(series),
        rarities=sorted(rarities),
        card_types=sorted(card_types),
        languages=sorted(languages),
        variants=sorted(variants, key=lambda v: v.value),
        condition_grades=sorted(condition_grades),
    )


async def get_owned_item(session: AsyncSession, user: User, item_id: uuid.UUID) -> CollectionItem:
    item = await session.get(CollectionItem, item_id)
    if item is None or item.user_id != user.id:
        raise CollectionItemNotFoundError
    return item


async def create_manual_items(
    session: AsyncSession, user: User, data: CreateCollectionItemRequest
) -> list[CollectionItem]:
    card = await session.get(Card, data.card_id)
    if card is None:
        raise CardNotFoundError

    items = [
        CollectionItem(
            user_id=user.id,
            card_id=card.id,
            language=data.language,
            variant=data.variant,
            condition_grade=data.condition_grade,
            purchase_price=data.purchase_price,
            purchase_currency=data.purchase_currency,
            acquired_at=data.acquired_at or date.today(),
        )
        for _ in range(data.quantity)
    ]
    session.add_all(items)
    await session.commit()
    for item in items:
        await session.refresh(item)
    return items


async def update_item(
    session: AsyncSession, user: User, item_id: uuid.UUID, data: UpdateCollectionItemRequest
) -> CollectionItem:
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


async def get_item_photo(
    session: AsyncSession, storage: StorageBackend, user: User, item_id: uuid.UUID
) -> bytes:
    """Bascule « Ma photo » de la fiche carte (mission `v4-fiche`) — même distinction que
    `pbm_api.uploads.service.get_detection_crop` : un exemplaire ajouté manuellement n'a pas de
    photo, jamais un succès vide à la place."""
    item = await get_owned_item(session, user, item_id)
    if item.photo_s3_key is None:
        raise CollectionItemPhotoMissingError
    data = await storage.get(item.photo_s3_key)
    if data is None:
        raise CollectionItemPhotoMissingError
    return data
