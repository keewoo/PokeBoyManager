"""`GET /me/dashboard` (mission `v4-dashboard`) : agrégats de l'accueil connecté — valeur totale
et courbe sur 90 jours, meilleures variations 30 j, cinq derniers ajouts."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user
from pbm_api.dashboard import service
from pbm_api.dashboard.schemas import (
    DashboardMoverCard,
    DashboardRecentAddition,
    DashboardResponse,
    DashboardValuePoint,
)
from pbm_api.db import get_session
from pbm_api.models import User

router = APIRouter(prefix="/me", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DashboardResponse:
    data = await service.get_dashboard(session, current_user)
    return DashboardResponse(
        items_total=data.items_total,
        items_priced=data.items_priced,
        items_missing_price=data.items_missing_price,
        total_value_eur=data.total_value_eur,
        value_change_30d_eur=data.value_change_30d_eur,
        value_history=[
            DashboardValuePoint(as_of=point.as_of, total_value_eur=point.total_value_eur)
            for point in data.value_history
        ],
        top_movers=[
            DashboardMoverCard(
                item_id=mover.item_id,
                card_id=mover.card_id,
                card_name=mover.card_name,
                card_number=mover.card_number,
                set_name=mover.set_name,
                value_eur=mover.value_eur,
                value_change_30d_eur=mover.change_30d_eur,
                value_change_30d_pct=mover.change_30d_pct,
            )
            for mover in data.top_movers
        ],
        recent_additions=[
            DashboardRecentAddition(
                item_id=addition.item_id,
                card_id=addition.card_id,
                card_name=addition.card_name,
                set_name=addition.set_name,
                added_at=addition.added_at,
            )
            for addition in data.recent_additions
        ],
    )
