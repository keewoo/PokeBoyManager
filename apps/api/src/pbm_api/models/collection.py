import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin
from pbm_api.models.catalog import PRICE_VARIANT_ENUM, PriceVariant


class UploadStatus(enum.StrEnum):
    pending = "pending"
    processing = "processing"
    processed = "processed"
    failed = "failed"


class Upload(Base, TimestampMixin):
    """Une photo envoyée par l'utilisateur, source de zéro ou plusieurs détections."""

    __tablename__ = "uploads"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="upload_status"), nullable=False, default=UploadStatus.pending
    )


class DetectionStatus(enum.StrEnum):
    pending = "pending"
    validated = "validated"
    rejected = "rejected"


class Detection(Base, TimestampMixin):
    """Une carte détectée sur une photo : bbox, recadrage, candidats du catalogue, validation."""

    __tablename__ = "detections"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    upload_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bbox: Mapped[dict] = mapped_column(JSONB, nullable=False)
    crop_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Sortie brute de l'extraction IA par carte (mission `v3-identification` point 1 : nom,
    # numéro, total, code d'extension, langue, PV, type, variante, confiance par champ) — utile
    # à l'écran de validation (lot `v3-validation`) même quand aucun candidat catalogue ne
    # dépasse le seuil de présélection.
    extraction: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    candidates: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Centrage (OpenCV) + coins/bords/surface/contrefaçon (extraction ci-dessus) combinés en un
    # état indicatif (mission `v3-etat`, `pbm_api.state.service.run_state_estimation_for_upload`)
    # — colonne distincte d'`extraction` : le centrage n'en fait pas partie (mesuré, pas demandé
    # à l'IA), et ce résultat existe même quand `extraction` est absent (D4, sans clé IA).
    condition_assessment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[DetectionStatus] = mapped_column(
        Enum(DetectionStatus, name="detection_status"),
        nullable=False,
        default=DetectionStatus.pending,
    )
    selected_card_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cards.id", ondelete="SET NULL"), nullable=True
    )


class CollectionItem(Base, TimestampMixin):
    """L'exemplaire possédé par un utilisateur : état, langue, variante, prix d'achat, photo."""

    __tablename__ = "collection_items"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cards.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    detection_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("detections.id", ondelete="SET NULL"), nullable=True
    )
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="fr")
    variant: Mapped[PriceVariant] = mapped_column(
        PRICE_VARIANT_ENUM, nullable=False, default=PriceVariant.normal
    )
    condition_grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Reprend le drapeau de `Detection.condition_assessment` (mission `v3-etat` point 3) au
    # moment où l'exemplaire est créé (lot `v4-collection`, pas encore posé dans ce dépôt) :
    # `pbm_api.pricing.valuation.item_value` neutralise la valeur d'un exemplaire ainsi signalé,
    # jamais une contrefaçon probable valorisée comme l'originale.
    counterfeit_suspected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    purchase_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    photo_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    acquired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
