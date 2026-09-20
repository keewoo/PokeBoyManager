import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class DashboardValuePoint(BaseModel):
    as_of: date
    total_value_eur: Decimal


class DashboardMoverCard(BaseModel):
    item_id: uuid.UUID
    card_id: uuid.UUID
    card_name: str
    card_number: str
    set_name: str
    value_eur: Decimal
    value_change_30d_eur: Decimal
    value_change_30d_pct: Decimal | None


class DashboardRecentAddition(BaseModel):
    item_id: uuid.UUID
    card_id: uuid.UUID
    card_name: str
    set_name: str
    added_at: datetime


class DashboardResponse(BaseModel):
    items_total: int
    items_priced: int
    items_missing_price: int
    total_value_eur: Decimal
    value_change_30d_eur: Decimal
    value_history: list[DashboardValuePoint]
    top_movers: list[DashboardMoverCard]
    recent_additions: list[DashboardRecentAddition]
