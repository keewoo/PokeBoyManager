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
    __table_args__ = (UniqueConstraint("tcgdex_id", name="uq_sets_tcgdex_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # Identifiant TCGdex (ex: "sv03.5") — clé d'idempotence de l'import, différente de `code`
    # (choisi librement) et différente de l'id Pokémon TCG API ("sv3pt5", voir reconciliation.py).
    tcgdex_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
        UniqueConstraint("tcgdex_id", name="uq_cards_tcgdex_id"),
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
    # URL de base TCGdex sans extension (ex: ".../sv/sv03.5/006") : le proxy /img/cards/{id}
    # y ajoute "/high.webp" ou "/low.webp" selon la définition demandée.
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    illustrator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # `none_as_null=True` partout : sans lui, assigner l'attribut Python `None` écrit un scalaire
    # JSON `null` en base, pas un SQL NULL — `IS NOT NULL` (complétude, recherche de trous) le
    # compterait alors à tort comme renseigné (constaté en écrivant le rapport de complétude).
    attacks: Mapped[list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    abilities: Mapped[list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    legal_standard: Mapped[bool | None] = mapped_column(nullable=True)
    legal_expanded: Mapped[bool | None] = mapped_column(nullable=True)
    weaknesses: Mapped[list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    resistances: Mapped[list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    retreat_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Marqueur de règle spéciale (ex/GX/V/VMAX/VSTAR/BREAK...) : TCGdex `suffix` si présent
    # (ex, GX — la carte garde un stade d'évolution ordinaire), sinon `stage` quand il porte
    # lui-même la règle (VMAX/VSTAR n'ont pas de `suffix`, voir catalog/import_service.py).
    rule_marker: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Variantes existantes pour cette carte (ex: {"normal": false, "holo": true, "reverse": false,
    # "firstEdition": false, "wPromo": false}), telles qu'exposées par TCGdex (`variants`).
    variants: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    # Identifiants externes pour le rapprochement (v2-catalogue) — voir catalog/reconciliation.py.
    tcgdex_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ptcg_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


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
    # `generated_at`/`cached_until`/`source_model` (ci-dessus) datent le cache des anecdotes ;
    # l'étude en jeu (`v4-jeu`) a son propre triplet ci-dessous, volontairement distinct — les
    # deux synthèses sont générées à des moments différents et ne doivent jamais réinitialiser
    # la fraîcheur l'une de l'autre (un `card_insights` déjà "frais" pour l'étude en jeu mais
    # dont les anecdotes n'ont jamais été générées ne doit pas empêcher leur génération, et
    # inversement).
    anecdotes: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    in_game_study: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cached_until: Mapped[datetime | None] = mapped_column(nullable=True)
    game_study_source_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    game_study_generated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    game_study_cached_until: Mapped[datetime | None] = mapped_column(nullable=True)


class TournamentPresenceStatus(enum.StrEnum):
    # Carte rapprochée sans ambiguïté sur Limitless TCG — `decks` peut être vide (carte
    # légitimement absente des tournois relevés, une information réelle en soi).
    checked = "checked"
    # Rapprochement impossible (extension/numéro non trouvés côté Limitless, ou site bloqué à
    # ce relevé) — mission point 2 : "sinon section masquée", jamais une carte "probable".
    unavailable = "unavailable"


class CardTournamentPresence(Base):
    """Présence en tournoi (mission `v4-jeu` point 2) — cache partagé entre utilisateurs, une
    ligne par carte, alimentée par le relevé périodique (`pbm_api.worker.weekly_tournament_
    presence_task`), jamais à la demande (site tiers, courtoisie réseau)."""

    __tablename__ = "card_tournament_presence"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cards.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    status: Mapped[TournamentPresenceStatus] = mapped_column(
        Enum(TournamentPresenceStatus, name="tournament_presence_status"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Liste de {"deck_name", "tournament_name", "tournament_url", "placement"} — jamais
    # réinterprétée, affichée telle quelle avec sa source et sa date de relevé (risque de la
    # mission : "ne jamais inventer un résultat de tournoi").
    decks: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(nullable=False)


class CardInsightReport(Base):
    """Signalement « erreur dans les anecdotes » (mission `v4-anecdotes` point 3) — un
    signalement par utilisateur et par carte, un second clic met à jour la raison plutôt que
    d'empiler des doublons."""

    __tablename__ = "card_insight_reports"
    __table_args__ = (
        UniqueConstraint("card_id", "user_id", name="uq_card_insight_reports_card_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
