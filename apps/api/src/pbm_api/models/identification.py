import uuid

from sqlalchemy import BigInteger, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin


class IdentificationCache(Base, TimestampMixin):
    """Cache d'identification par empreinte perceptuelle du recadrage (mission `v3-identification`
    point 4) — partagé entre tous les utilisateurs, comme `card_insights` : le résultat d'une
    identification (extraction + candidats) ne dépend que de l'image photographiée, jamais de
    qui l'a envoyée. Une même carte rephotographiée (empreinte à distance de Hamming proche, voir
    `pbm_api.identification.cache`) ne rappelle jamais l'IA."""

    __tablename__ = "identification_cache"
    __table_args__ = (Index("ix_identification_cache_phash", "phash"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Hachage moyen 64 bits (`pbm_api.identification.fingerprint.compute_phash`), stocké tel
    # quel en entier signé (même représentation bit à bit qu'un `bigint` Postgres) — comparé
    # par XOR + `bit_count` (distance de Hamming), jamais par égalité stricte.
    phash: Mapped[int] = mapped_column(BigInteger, nullable=False)
    extraction: Mapped[dict] = mapped_column(JSONB, nullable=False)
    candidates: Mapped[list] = mapped_column(JSONB, nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
