import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin


class Deck(Base, TimestampMixin):
    """Un deck construit par un utilisateur à partir de sa collection (mission `v7-decks-api`).

    Ne porte aucun état de légalité : elle est recalculée à la lecture (voir
    `pbm_api.decks.legality`), jamais mémorisée — c'est ce qui rend la « revalidation quand la
    collection change » automatique (une carte vendue rend le deck injouable sans qu'aucune
    écriture ne soit nécessaire, risque du lot)."""

    __tablename__ = "decks"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Format de jeu choisi par le joueur (Standard / Étendu / Illimité, `pbm_api.decks.
    # formats`) — sert au contrôle de légalité par format (lot `v7-decks-legalite`). Défaut
    # "standard" ; `server_default` pour les decks créés avant la colonne.
    format: Mapped[str] = mapped_column(
        String(16), nullable=False, default="standard", server_default=text("'standard'")
    )


class DeckCard(Base, TimestampMixin):
    """Une entrée de deck : une carte du catalogue et sa quantité.

    Référence le catalogue (`card_id`), pas un exemplaire précis de la collection
    (`collection_items.id`) — décision imposée par D10 : les Énergies de base font partie d'un
    deck sans être possédées (fournies en quantité illimitée), donc un deck DOIT pouvoir citer
    une carte qu'aucun `CollectionItem` ne représente. La contrainte « uniquement avec ses
    cartes » est un contrôle de légalité (possession comptée sur `collection_items` à la lecture,
    `pbm_api.decks.legality`), pas une clé étrangère : vendre un exemplaire rend le deck
    injouable mais le laisse lisible et modifiable (risque du lot), ce qu'une FK
    `ON DELETE CASCADE`/`SET NULL` casserait.

    `ON DELETE RESTRICT` sur `card_id` comme `collection_items` : une carte du catalogue citée
    par un deck ne disparaît pas en silence sous lui."""

    __tablename__ = "deck_cards"
    __table_args__ = (
        UniqueConstraint("deck_id", "card_id", name="uq_deck_cards_deck_card"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    deck_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("decks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cards.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
