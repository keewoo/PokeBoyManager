"""Service de l'accueil connecté (mission `v4-dashboard`) : valeur totale et courbe sur 90 jours,
meilleures variations 30 j, cinq derniers ajouts. Réutilise tel quel `pricing.valuation.
bulk_item_values_multi` (posé par `v4-collection`, mission point 4 de ce lot-là) — jamais une
requête de prix par exemplaire.

Courbe de valeur : un point tous les `HISTORY_POINT_INTERVAL_DAYS` plutôt qu'un par jour (job
lourd = job bridé, `~/.claude/CLAUDE.md`) — `bulk_item_values_multi` fait un `UNION ALL` d'une
sous-requête par date demandée, 90 dates multiplieraient le coût par 90 pour un agrément visuel
qu'une dizaine de points suffit à donner sur la maquette (courbe lissée, pas un relevé quotidien
affiché brut).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.models import Card, CardName, CollectionItem, Set, User
from pbm_api.pricing.valuation import bulk_item_values_multi

RECENT_ADDITIONS_LIMIT = 5
TOP_MOVERS_LIMIT = 5
HISTORY_WINDOW_DAYS = 90
HISTORY_POINT_INTERVAL_DAYS = 7
_VALUE_CHANGE_WINDOW_DAYS = 30


@dataclass(frozen=True)
class ValuePoint:
    as_of: date
    total_value_eur: Decimal


@dataclass(frozen=True)
class MoverCard:
    item_id: uuid.UUID
    card_id: uuid.UUID
    card_name: str
    card_number: str
    set_name: str
    value_eur: Decimal
    change_30d_eur: Decimal
    change_30d_pct: Decimal | None


@dataclass(frozen=True)
class RecentAddition:
    item_id: uuid.UUID
    card_id: uuid.UUID
    card_name: str
    set_name: str
    added_at: datetime


@dataclass(frozen=True)
class DashboardData:
    items_total: int
    items_priced: int
    items_missing_price: int
    total_value_eur: Decimal
    value_change_30d_eur: Decimal
    value_history: list[ValuePoint]
    top_movers: list[MoverCard]
    recent_additions: list[RecentAddition]


@dataclass(frozen=True)
class _Row:
    item: CollectionItem
    card_id: uuid.UUID
    card_number: str
    card_name: str
    set_name: str


def _pct_change(current: Decimal, past: Decimal) -> Decimal | None:
    """Même règle que `pbm_api.routers.collection._pct_change` (mission `v4-collection`) :
    `None` si la valeur de référence est nulle, jamais un pourcentage inventé."""
    if past == 0:
        return None
    return (current - past) / past * 100


def _history_dates(as_of: date) -> tuple[date, ...]:
    """`as_of`, puis un point tous les `HISTORY_POINT_INTERVAL_DAYS` en remontant jusqu'à
    `HISTORY_WINDOW_DAYS`, la borne la plus ancienne toujours incluse même si elle ne tombe pas
    sur un multiple exact de l'intervalle."""
    offsets = list(range(0, HISTORY_WINDOW_DAYS + 1, HISTORY_POINT_INTERVAL_DAYS))
    if offsets[-1] != HISTORY_WINDOW_DAYS:
        offsets.append(HISTORY_WINDOW_DAYS)
    return tuple(sorted({as_of - timedelta(days=offset) for offset in offsets}))


async def get_dashboard(
    session: AsyncSession, user: User, as_of: date | None = None
) -> DashboardData:
    as_of = as_of or datetime.now(UTC).date()

    stmt = (
        select(CollectionItem, Card.id, Card.number, Card.name, Set.name, CardName.name)
        .join(Card, Card.id == CollectionItem.card_id)
        .join(Set, Set.id == Card.set_id)
        .outerjoin(
            CardName,
            and_(CardName.card_id == Card.id, CardName.language == CollectionItem.language),
        )
        .where(CollectionItem.user_id == user.id)
    )
    rows_raw = (await session.execute(stmt)).all()
    rows = [
        _Row(
            item=item,
            card_id=card_id,
            card_number=card_number,
            card_name=localized_name or card_name,
            set_name=set_name,
        )
        for item, card_id, card_number, card_name, set_name, localized_name in rows_raw
    ]
    items = [row.item for row in rows]

    history_dates = _history_dates(as_of)
    change_reference = as_of - timedelta(days=_VALUE_CHANGE_WINDOW_DAYS)
    as_of_dates = tuple(sorted({*history_dates, change_reference}))
    values_by_date = await bulk_item_values_multi(session, items, as_of_dates, currency="EUR")

    def _total(values: dict[uuid.UUID, Decimal | None]) -> Decimal:
        return sum((v for v in values.values() if v is not None), Decimal("0"))

    values_today = values_by_date[as_of]
    values_30d_ago = values_by_date[change_reference]

    total_value_eur = _total(values_today)
    items_priced = sum(1 for v in values_today.values() if v is not None)
    items_missing_price = len(items) - items_priced

    value_history = [
        ValuePoint(as_of=history_date, total_value_eur=_total(values_by_date[history_date]))
        for history_date in history_dates
    ]

    movers: list[MoverCard] = []
    for row in rows:
        current = values_today.get(row.item.id)
        past = values_30d_ago.get(row.item.id)
        if current is None or past is None:
            continue
        change = current - past
        if change == 0:
            continue
        movers.append(
            MoverCard(
                item_id=row.item.id,
                card_id=row.card_id,
                card_name=row.card_name,
                card_number=row.card_number,
                set_name=row.set_name,
                value_eur=current,
                change_30d_eur=change,
                change_30d_pct=_pct_change(current, past),
            )
        )
    movers.sort(key=lambda m: abs(m.change_30d_eur), reverse=True)

    recent = sorted(rows, key=lambda row: row.item.created_at, reverse=True)[
        :RECENT_ADDITIONS_LIMIT
    ]

    return DashboardData(
        items_total=len(items),
        items_priced=items_priced,
        items_missing_price=items_missing_price,
        total_value_eur=total_value_eur,
        value_change_30d_eur=total_value_eur - _total(values_30d_ago),
        value_history=value_history,
        top_movers=movers[:TOP_MOVERS_LIMIT],
        recent_additions=[
            RecentAddition(
                item_id=row.item.id,
                card_id=row.card_id,
                card_name=row.card_name,
                set_name=row.set_name,
                added_at=row.item.created_at,
            )
            for row in recent
        ],
    )
