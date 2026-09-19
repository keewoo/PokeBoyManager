import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin
from pbm_api.models.users import AiProvider


class AiUsageMonthly(Base, TimestampMixin):
    """Compteur d'usage IA par utilisateur, fournisseur et mois (`period` = premier jour du
    mois, UTC). Alimenté par le worker à chaque appel réel au fournisseur ; ce lot pose la
    table et sa lecture seule (`GET /me/ai-usage`)."""

    __tablename__ = "ai_usage_monthly"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "period", name="uq_ai_usage_monthly_user_provider_period"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[AiProvider] = mapped_column(
        Enum(AiProvider, name="ai_provider"), nullable=False
    )
    period: Mapped[date] = mapped_column(Date, nullable=False)
    calls_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )
