import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base


class ExchangeRateDaily(Base):
    """Taux de change BCE du jour : unités de `currency` pour 1 EUR (format du flux BCE).

    Convertir EUR -> devise : `montant_eur * rate`. Convertir devise -> EUR : `montant / rate`.
    `EUR` lui-même n'a jamais de ligne ici (rate == 1 par construction, voir `get_rate_to_eur`).
    """

    __tablename__ = "exchange_rates_daily"
    __table_args__ = (
        UniqueConstraint("day", "currency", name="uq_exchange_rates_daily_day_currency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
