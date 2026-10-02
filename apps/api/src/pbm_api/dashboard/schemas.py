"""Schémas HTTP de l'accueil connecté : miroir pydantic des dataclasses de
`pbm_api.dashboard.service`, exposées telles quelles à la réponse de la route.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class DashboardValuePoint(BaseModel):
    """Un point de la courbe de valeur : valeur totale de la collection à une date donnée."""

    as_of: date
    total_value_eur: Decimal


class DashboardMoverCard(BaseModel):
    """Une carte parmi les plus fortes variations de valeur sur 30 jours."""

    item_id: uuid.UUID
    card_id: uuid.UUID
    card_name: str
    card_number: str
    set_name: str
    value_eur: Decimal
    value_change_30d_eur: Decimal
    value_change_30d_pct: Decimal | None


class DashboardRecentAddition(BaseModel):
    """Un exemplaire parmi les derniers ajoutés à la collection."""

    item_id: uuid.UUID
    card_id: uuid.UUID
    card_name: str
    set_name: str
    added_at: datetime


class DashboardResponse(BaseModel):
    """Réponse complète de l'accueil connecté : totaux, courbe de valeur, mouvements, ajouts."""

    items_total: int
    items_priced: int
    items_missing_price: int
    total_value_eur: Decimal
    value_change_30d_eur: Decimal
    value_history: list[DashboardValuePoint]
    top_movers: list[DashboardMoverCard]
    recent_additions: list[DashboardRecentAddition]
