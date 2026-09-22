"""Synchronisation collection → decks (mission `v7-decks-collection-sync`).

Quand un exemplaire quitte le décompte de possession (vendu, échangé, supprimé, ou signalé
contrefaçon), un deck qui citait cette carte peut cesser d'être jouable. La légalité, elle, est
déjà juste : elle est recalculée à chaque lecture (`pbm_api.decks.legality`), donc le deck
apparaît « à compléter » sans aucune écriture. Ce que ce module ajoute, c'est la **notification** :
il inscrit une ligne `DeckEvent` pour prévenir le joueur — *« ton deck X n'est plus jouable, il te
manque la carte Y »* — sinon la bascule serait silencieuse.

Deux garde-fous portés par le code, pas par une consigne :

  - **on ne modifie JAMAIS le deck** (risque du lot) : aucune écriture sur `deck_cards`, aucune
    carte retirée en douce. Une partie en cours (quand elle existera) fige sa copie au démarrage ;
    de toute façon rien ici ne touche au contenu du deck.
  - **seule la BASCULE compte** : on n'écrit une alerte que si le deck était complet pour cette
    carte *avant* le changement et ne l'est plus *après*. Un deck déjà incomplet qui le reste ne
    reçoit pas de doublon d'alerte ; un doublon vendu dont il reste un exemplaire suffisant n'en
    déclenche aucune (le deck reste jouable).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.decks import energy
from pbm_api.models import (
    DECK_EVENT_CARD_INCOMPLETE,
    Card,
    CollectionItem,
    Deck,
    DeckCard,
    DeckEvent,
    User,
)


async def record_collection_change(
    session: AsyncSession,
    user: User,
    removed_counts: dict[uuid.UUID, int],
    reason: str,
) -> list[DeckEvent]:
    """Inscrit une alerte par deck que ce changement de collection vient de rendre « à compléter ».

    `removed_counts` : par carte, le nombre d'exemplaires qui étaient comptés dans la possession et
    ne le sont plus après le changement (un exemplaire supprimé : 1 ; un exemplaire déjà signalé
    contrefaçon puis supprimé : 0, il ne comptait déjà pas). À appeler **après** que le changement
    a été validé en base : le décompte de possession lu ici est celui d'« après ».
    """
    card_ids = [card_id for card_id, removed in removed_counts.items() if removed > 0]
    if not card_ids:
        return []

    # Toutes les entrées de deck de CET utilisateur qui citent une des cartes touchées.
    entries = (
        await session.execute(
            select(
                Deck.id,
                Deck.name,
                DeckCard.card_id,
                DeckCard.quantity,
                Card.name,
                Card.supertype,
                Card.energy_type,
            )
            .join(DeckCard, DeckCard.deck_id == Deck.id)
            .join(Card, Card.id == DeckCard.card_id)
            .where(Deck.user_id == user.id, DeckCard.card_id.in_(card_ids))
        )
    ).all()
    if not entries:
        return []

    # Possession actuelle (hors contrefaçon) des cartes touchées — une seule requête, groupée.
    owned_rows = (
        await session.execute(
            select(CollectionItem.card_id, func.count())
            .where(
                CollectionItem.user_id == user.id,
                CollectionItem.card_id.in_(card_ids),
                CollectionItem.counterfeit_suspected.is_(False),
            )
            .group_by(CollectionItem.card_id)
        )
    ).all()
    owned = {card_id: count for card_id, count in owned_rows}

    events: list[DeckEvent] = []
    for deck_id, deck_name, card_id, quantity, card_name, supertype, energy_type in entries:
        # Énergie de base : fournie en quantité illimitée, jamais un manque (décision D10).
        if energy.is_basic_energy(supertype, card_name, energy_type):
            continue
        owned_now = owned.get(card_id, 0)
        owned_before = owned_now + removed_counts.get(card_id, 0)
        became_incomplete = owned_before >= quantity and owned_now < quantity
        if not became_incomplete:
            continue
        events.append(
            DeckEvent(
                user_id=user.id,
                deck_id=deck_id,
                event_type=DECK_EVENT_CARD_INCOMPLETE,
                reason=reason,
                card_id=card_id,
                card_name=card_name,
                detail={
                    "deck_name": deck_name,
                    "required": quantity,
                    "owned": owned_now,
                    "missing": quantity - owned_now,
                },
            )
        )

    if events:
        session.add_all(events)
        await session.commit()
        for event in events:
            await session.refresh(event)
    return events
