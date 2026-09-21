"""Orchestration base des decks (mission `v7-decks-api`).

Toute fonction est bornée au propriétaire (`user_id` de la session) : un deck d'un autre
utilisateur lève `DeckNotFoundError` (→ 404), jamais 403 (pas de fuite d'existence). La légalité
n'est jamais mémorisée : elle est recalculée ici à chaque lecture à partir de la collection du
moment (`legality.evaluate`), ce qui satisfait « revalidation quand la collection change » sans
aucune écriture.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.decks import legality
from pbm_api.decks.errors import DeckCardNotFoundError, DeckNotFoundError
from pbm_api.decks.legality import DeckCardFact, DeckLegality
from pbm_api.decks.schemas import CreateDeckRequest, DeckCardInput
from pbm_api.models import Card, CollectionItem, Deck, DeckCard, Set, User
from pbm_api.validation.errors import CardNotFoundError

_COPY_SUFFIX = " (copie)"


@dataclass
class LoadedDeckCard:
    """Une entrée de deck jointe à sa carte du catalogue — tout ce qu'il faut pour le rapport."""

    deck_id: uuid.UUID
    card_id: uuid.UUID
    quantity: int
    card_name: str
    card_number: str
    supertype: str | None
    energy_type: str | None
    rarity: str | None
    image_url: str | None
    set_id: uuid.UUID
    set_name: str
    set_code: str


def _merge_inputs(cards: list[DeckCardInput]) -> dict[uuid.UUID, int]:
    """Additionne les quantités d'un même `card_id` : l'entrée peut citer la carte deux fois,
    la contrainte d'unicité `(deck_id, card_id)` ne l'accepterait pas en double."""
    merged: dict[uuid.UUID, int] = {}
    for entry in cards:
        merged[entry.card_id] = merged.get(entry.card_id, 0) + entry.quantity
    return merged


async def _ensure_cards_exist(session: AsyncSession, card_ids: list[uuid.UUID]) -> None:
    if not card_ids:
        return
    result = await session.execute(select(Card.id).where(Card.id.in_(card_ids)))
    found = {row[0] for row in result.all()}
    missing = set(card_ids) - found
    if missing:
        raise CardNotFoundError


async def _get_owned_deck(session: AsyncSession, user: User, deck_id: uuid.UUID) -> Deck:
    deck = await session.get(Deck, deck_id)
    if deck is None or deck.user_id != user.id:
        raise DeckNotFoundError
    return deck


async def _load_cards(
    session: AsyncSession, deck_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[LoadedDeckCard]]:
    by_deck: dict[uuid.UUID, list[LoadedDeckCard]] = {d: [] for d in deck_ids}
    if not deck_ids:
        return by_deck
    rows = await session.execute(
        select(
            DeckCard.deck_id.label("deck_id"),
            DeckCard.card_id.label("card_id"),
            DeckCard.quantity.label("quantity"),
            Card.name.label("card_name"),
            Card.number.label("card_number"),
            Card.supertype.label("supertype"),
            Card.energy_type.label("energy_type"),
            Card.rarity.label("rarity"),
            Card.image_url.label("image_url"),
            Set.id.label("set_id"),
            Set.name.label("set_name"),
            Set.code.label("set_code"),
        )
        .join(Card, DeckCard.card_id == Card.id)
        .join(Set, Card.set_id == Set.id)
        .where(DeckCard.deck_id.in_(deck_ids))
        .order_by(Card.name, Card.number)
    )
    for m in rows.mappings():
        by_deck[m["deck_id"]].append(LoadedDeckCard(**m))
    return by_deck


async def _owned_counts(
    session: AsyncSession, user_id: uuid.UUID, card_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Nombre d'exemplaires possédés par carte (une seule requête, jamais une par carte)."""
    if not card_ids:
        return {}
    rows = await session.execute(
        select(CollectionItem.card_id, func.count())
        .where(CollectionItem.user_id == user_id, CollectionItem.card_id.in_(card_ids))
        .group_by(CollectionItem.card_id)
    )
    return {card_id: count for card_id, count in rows.all()}


def _facts(cards: list[LoadedDeckCard], owned: dict[uuid.UUID, int]) -> list[DeckCardFact]:
    return [
        DeckCardFact(
            card_id=c.card_id,
            name=c.card_name,
            supertype=c.supertype,
            energy_type=c.energy_type,
            quantity=c.quantity,
            owned=owned.get(c.card_id, 0),
        )
        for c in cards
    ]


async def create_deck(session: AsyncSession, user: User, data: CreateDeckRequest) -> Deck:
    merged = _merge_inputs(data.cards)
    await _ensure_cards_exist(session, list(merged))
    deck = Deck(user_id=user.id, name=data.name)
    session.add(deck)
    await session.flush()
    for card_id, quantity in merged.items():
        session.add(DeckCard(deck_id=deck.id, card_id=card_id, quantity=quantity))
    await session.commit()
    await session.refresh(deck)
    return deck


async def list_decks(session: AsyncSession, user: User) -> list[tuple[Deck, DeckLegality]]:
    result = await session.execute(
        select(Deck).where(Deck.user_id == user.id).order_by(Deck.created_at)
    )
    decks = list(result.scalars().all())
    if not decks:
        return []
    loaded = await _load_cards(session, [d.id for d in decks])
    all_card_ids = {c.card_id for cards in loaded.values() for c in cards}
    owned = await _owned_counts(session, user.id, list(all_card_ids))
    return [(d, legality.evaluate(_facts(loaded.get(d.id, []), owned))) for d in decks]


async def deck_detail(
    session: AsyncSession, user: User, deck_id: uuid.UUID
) -> tuple[Deck, list[LoadedDeckCard], DeckLegality]:
    deck = await _get_owned_deck(session, user, deck_id)
    loaded = (await _load_cards(session, [deck.id]))[deck.id]
    owned = await _owned_counts(session, user.id, [c.card_id for c in loaded])
    return deck, loaded, legality.evaluate(_facts(loaded, owned))


async def rename_deck(session: AsyncSession, user: User, deck_id: uuid.UUID, name: str) -> Deck:
    deck = await _get_owned_deck(session, user, deck_id)
    deck.name = name
    await session.commit()
    await session.refresh(deck)
    return deck


async def delete_deck(session: AsyncSession, user: User, deck_id: uuid.UUID) -> None:
    deck = await _get_owned_deck(session, user, deck_id)
    await session.delete(deck)
    await session.commit()


async def duplicate_deck(session: AsyncSession, user: User, deck_id: uuid.UUID) -> Deck:
    source = await _get_owned_deck(session, user, deck_id)
    rows = await session.execute(select(DeckCard).where(DeckCard.deck_id == source.id))
    name = (source.name + _COPY_SUFFIX)[:120]
    copy = Deck(user_id=user.id, name=name)
    session.add(copy)
    await session.flush()
    for dc in rows.scalars().all():
        session.add(DeckCard(deck_id=copy.id, card_id=dc.card_id, quantity=dc.quantity))
    await session.commit()
    await session.refresh(copy)
    return copy


async def set_deck_card(
    session: AsyncSession, user: User, deck_id: uuid.UUID, card_id: uuid.UUID, quantity: int
) -> Deck:
    """Pose (ou met à jour) la quantité d'une carte. Permissif à dessein : on peut ajouter une
    carte non possédée — la légalité signale le manque, jamais l'ajout n'est refusé (une Énergie
    de base n'est de toute façon jamais possédée, D10)."""
    deck = await _get_owned_deck(session, user, deck_id)
    await _ensure_cards_exist(session, [card_id])
    result = await session.execute(
        select(DeckCard).where(DeckCard.deck_id == deck_id, DeckCard.card_id == card_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(DeckCard(deck_id=deck_id, card_id=card_id, quantity=quantity))
    else:
        row.quantity = quantity
    deck.updated_at = datetime.now(UTC)  # une modif de contenu date le deck
    await session.commit()
    await session.refresh(deck)
    return deck


async def remove_deck_card(
    session: AsyncSession, user: User, deck_id: uuid.UUID, card_id: uuid.UUID
) -> Deck:
    deck = await _get_owned_deck(session, user, deck_id)
    result = await session.execute(
        select(DeckCard).where(DeckCard.deck_id == deck_id, DeckCard.card_id == card_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise DeckCardNotFoundError
    await session.delete(row)
    deck.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(deck)
    return deck
