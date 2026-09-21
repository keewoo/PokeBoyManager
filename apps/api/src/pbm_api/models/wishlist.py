import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin


class WishlistItem(Base, TimestampMixin):
    """Une carte du catalogue que l'utilisateur veut acheter, avec un prix cible facultatif
    (mission `v6-import-export`) — jamais un exemplaire de la collection (`collection_items`) :
    une carte quittée par un vœu n'est pas possédée, donc pas de langue/variante/état à porter,
    juste la carte visée et le prix qui déclenche l'envie de l'acheter.

    `ON DELETE RESTRICT` sur `card_id`, même choix que `collection_items`/`deck_cards` : une
    carte du catalogue citée par un souhait ne disparaît pas en silence sous lui.
    """

    __tablename__ = "wishlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_wishlist_items_user_card"),
    )

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
    # `None` : simple suivi, sans prix qui déclenche une alerte (mission « liste de souhaits avec
    # prix cible » — le prix cible est ce qui distingue ce lot d'un ajout à la collection, mais un
    # utilisateur qui veut juste garder un œil sur une carte sans encore savoir combien la payer
    # doit pouvoir le faire).
    target_price_eur: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(String(280), nullable=True)
