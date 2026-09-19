import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint
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
    # Comment cette entrée a été résolue la première fois (mission `v3-identification-visuelle`) :
    # "visuel" (comparaison à l'index visuel, aucun appel IA), "ia" (appel `AIProvider.extract`,
    # éventuellement assisté de candidats visuels) — jamais recalculé, sert au badge « reconnue
    # sans IA » de l'écran de validation même sur un coup de cache. Défaut "ia" : les lignes
    # posées avant ce lot n'ont pu venir que de là.
    method: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ia")


class CardVisualIndex(Base, TimestampMixin):
    """Empreintes visuelles de l'image officielle d'une carte (mission `v3-identification-
    visuelle` point 1) — une ligne par carte et par langue d'impression (l'illustration est
    partagée, mais le nom/texte imprimé diffère, et TCGdex sert une image distincte par langue).
    Alimentée hors ligne par `scripts/build_visual_index.py`, jamais à la demande : comparer un
    recadrage à ~20 000 cartes × 2 langues ne doit jamais attendre un téléchargement réseau."""

    __tablename__ = "card_visual_index"
    __table_args__ = (
        UniqueConstraint("card_id", "language", name="uq_card_visual_index_card_language"),
        Index("ix_card_visual_index_full_phash", "full_phash"),
        Index("ix_card_visual_index_illustration_phash", "illustration_phash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    # Même hachage moyen 64 bits que `pbm_api.identification.fingerprint.compute_phash`, calculé
    # sur l'image officielle entière (`full_phash`) et sur sa seule zone d'illustration
    # (`illustration_phash`, `pbm_api.identification.visual_geometry`) — la comparaison pondère
    # les deux (mission point 2 : l'illustration seule seule ne différencie pas un normal d'un
    # reverse holo, le cadre entier si).
    full_phash: Mapped[int] = mapped_column(BigInteger, nullable=False)
    illustration_phash: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Clé de l'image basse définition dans le stockage objet (mission point 1 : téléchargée hors
    # serveur de PROD) — réutilisée par le proxy `/img/cards/{id}` au premier accès utilisateur
    # au lieu de retélécharger, jamais consultée par la recherche elle-même (empreintes en
    # mémoire, voir `pbm_api.identification.visual_index`).
    source_image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)


class IdentificationCorrection(Base, TimestampMixin):
    """Une ligne par décision humaine sur une détection (lot `v3-validation`, mission point 3) :
    le candidat proposé en premier par `pbm_api.identification.reconciliation` (`None` si aucun
    candidat n'a été trouvé) contre celui réellement retenu (`None` = rejetée, aucune carte ne
    correspondait). C'est le jeu de régression de l'identification — mesurer plus tard le taux de
    correction, jamais consulté par le produit lui-même."""

    __tablename__ = "identification_corrections"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    detection_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("detections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposed_card_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cards.id", ondelete="SET NULL"), nullable=True
    )
    chosen_card_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cards.id", ondelete="SET NULL"), nullable=True
    )
