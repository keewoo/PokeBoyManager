import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin


class Set(Base, TimestampMixin):
    """Une extension du jeu (ex: 'Écarlate et Violet')."""

    __tablename__ = "sets"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    series: Mapped[str | None] = mapped_column(String(255), nullable=True)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)


class Card(Base, TimestampMixin):
    """Carte du catalogue partagé — pas un exemplaire possédé (voir `collection_items`)."""

    __tablename__ = "cards"
    __table_args__ = (
        UniqueConstraint("set_id", "number", name="uq_cards_set_number"),
        Index(
            "ix_cards_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    set_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rarity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supertype: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)


class CardName(Base):
    """Nom localisé d'une carte (une ligne par langue)."""

    __tablename__ = "card_names"
    __table_args__ = (
        UniqueConstraint("card_id", "language", name="uq_card_names_card_language"),
        Index(
            "ix_card_names_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class PriceSource(enum.StrEnum):
    cardmarket = "cardmarket"
    tcgplayer = "tcgplayer"


class PriceVariant(enum.StrEnum):
    normal = "normal"
    holo = "holo"
    reverse_holo = "reverse_holo"
    first_edition = "first_edition"


# Instance partagée : `card_prices_daily` et `collection_items` référencent le même type
# ENUM Postgres ("price_variant") — réutiliser l'objet évite une double émission de CREATE TYPE.
PRICE_VARIANT_ENUM = Enum(PriceVariant, name="price_variant")


class CardPriceDaily(Base):
    """Un relevé de prix = une carte × une source × une variante × un jour (historique léger)."""

    __tablename__ = "card_prices_daily"
    __table_args__ = (
        UniqueConstraint(
            "card_id", "source", "variant", "day", name="uq_card_prices_daily_unique_point"
        ),
        Index("ix_card_prices_daily_card_day", "card_id", "day"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[PriceSource] = mapped_column(
        Enum(PriceSource, name="price_source"), nullable=False
    )
    variant: Mapped[PriceVariant] = mapped_column(PRICE_VARIANT_ENUM, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    price_low: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    price_mid: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    price_trend: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class CardInsight(Base):
    """Anecdotes et étude en jeu — cache partagé entre utilisateurs, une ligne par carte."""

    __tablename__ = "card_insights"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cards.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    anecdotes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    in_game_study: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cached_until: Mapped[datetime | None] = mapped_column(nullable=True)
