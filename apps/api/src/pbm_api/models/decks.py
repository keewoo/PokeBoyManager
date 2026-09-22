import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
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


# Types d'événement d'un deck (stables, réutilisés par l'écran et l'en-tête).
DECK_EVENT_CARD_INCOMPLETE = "card_incomplete"

# Raison du changement de collection qui a rendu le deck « à compléter ».
DECK_EVENT_REASON_REMOVED = "removed"  # exemplaire supprimé / vendu / échangé
DECK_EVENT_REASON_COUNTERFEIT = "counterfeit"  # exemplaire signalé contrefaçon (exclu du décompte)


class DeckEvent(Base, TimestampMixin):
    """Trace persistante d'un changement de collection ayant rendu un deck « à compléter »
    (mission `v7-decks-collection-sync`).

    Ce lot ne modifie JAMAIS le contenu d'un deck (une carte vendue ne se retire pas toute seule,
    risque du lot) : la légalité reste recalculée à la lecture (`pbm_api.decks.legality`). Ce que
    ce lot ajoute, c'est la **mémoire** de la transition — sans elle, un deck passé « à compléter »
    la nuit dernière serait injouable sans que le joueur sache jamais quelle carte l'a rendu tel.
    Une ligne = un deck qui vient de perdre une carte requise. Elle sert deux écrans :

      - **notification au joueur** (badge d'en-tête + liste) tant que `read_at IS NULL` ;
      - **historique des modifications du deck** (toutes les lignes du deck, lues ou non).

    `card_id` en `SET NULL` + `card_name` figé : l'historique survit même si la carte disparaissait
    du catalogue. Aucune ligne n'est écrite quand un deck déjà incomplet le reste, ni quand un
    exemplaire retiré laisse le deck jouable (un doublon vendu dont il reste un exemplaire) — seule
    la **bascule** vers « à compléter » est un événement (voir `pbm_api.decks.collection_sync`)."""

    __tablename__ = "deck_events"
    __table_args__ = (
        # Requête de l'en-tête : « mes alertes non lues », triées du plus récent au plus ancien.
        Index("ix_deck_events_user_unread", "user_id", "read_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deck_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("decks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    card_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cards.id", ondelete="SET NULL"), nullable=True
    )
    card_name: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
