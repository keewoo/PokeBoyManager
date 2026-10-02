"""Socle commun des modèles SQLAlchemy : classe déclarative de base et mixin d'horodatage."""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Classe déclarative de base dont héritent tous les modèles SQLAlchemy du projet."""

    pass


class TimestampMixin:
    """Mixin ajoutant `created_at`/`updated_at` posés par le serveur, pour tout modèle qui
    doit tracer sa date de création et de dernière modification."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
