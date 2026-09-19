import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin


class AiProvider(enum.StrEnum):
    anthropic = "anthropic"
    gemini = "gemini"
    openai = "openai"


class User(Base, TimestampMixin):
    """Compte utilisateur. Le mot de passe est un hash (jamais le mot de passe en clair)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Nouvelle adresse en attente de re-vérification (lot v1-profil) : `email` ne change
    # qu'une fois le jeton `change_email` envoyé à cette adresse consommé.
    pending_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    pseudo: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    avatar_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Devise d'affichage de la valeur de collection (lot v2-prix) — code ISO 4217, converti
    # depuis la référence EUR via `exchange_rates_daily` (pbm_api.pricing.exchange_rates).
    preferred_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")
    ai_default_provider: Mapped[AiProvider | None] = mapped_column(
        Enum(AiProvider, name="ai_provider"), nullable=True
    )
    ai_default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Session(Base):
    """Session de connexion (cookie côté client, hash du jeton côté serveur)."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)


class EmailTokenKind(enum.StrEnum):
    verify_email = "verify_email"
    reset_password = "reset_password"
    change_email = "change_email"


class EmailToken(Base):
    """Jeton à usage unique envoyé par e-mail (vérification, réinitialisation)."""

    __tablename__ = "email_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[EmailTokenKind] = mapped_column(
        Enum(EmailTokenKind, name="email_token_kind"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AiCredential(Base, TimestampMixin):
    """Clé IA de l'utilisateur : chiffrée AES-256-GCM, jamais stockée ni renvoyée en clair.

    `encrypted_key`/`nonce` contiennent le chiffré ; seul `key_mask` (ex: "sk-ant-...4f2a")
    est présentable côté API. La clé maître de déchiffrement vit hors base (environnement
    du worker).
    """

    __tablename__ = "ai_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_ai_credentials_user_provider"),
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
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_mask: Mapped[str] = mapped_column(String(32), nullable=False)
