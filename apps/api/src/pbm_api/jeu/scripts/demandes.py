"""Accès base à la **file de demandes** `card_play_requests` : signaler une carte, la suivre.

Ce module lit et écrit la base (il vit donc dans `apps/api`, jamais dans le moteur pur). Il sert à
la fois le joueur (ses propres demandes, avec leur progression) et l'exploitation (la file agrégée
qui dirige le chantier de scriptage). La *progression* d'une demande se lit en deux temps : le
``statut`` stocké (l'intention posée par un lot de scripts) **et** la jouabilité courante recalculée
contre le registre `card_scripts` — une carte peut être devenue jouable sans qu'on ait repassé son
statut à la main.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu.scripts.chargeur import refus_scripts_par_carte
from pbm_api.models import Card
from pbm_api.models.card_play_requests import (
    REQUEST_STATUT_EN_ATTENTE,
    REQUEST_STATUT_SCRIPTEE,
    CardPlayRequest,
)


@dataclass(frozen=True)
class DemandeJoueur:
    """Une demande d'un joueur, enrichie de sa progression réelle (statut + jouabilité courante)."""

    demande: CardPlayRequest
    card_name: str
    jouable_maintenant: bool


@dataclass(frozen=True)
class DemandeAgregeeCarte:
    """Une carte de la file, agrégée pour la priorisation : combien de joueurs distincts la veulent.
    """

    card_id: uuid.UUID
    nom: str
    demandeurs: int
    en_attente: int
    jouable_maintenant: bool


async def _cartes_jouables(db: AsyncSession, card_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """L'ensemble des cartes (parmi ``card_ids``) **entièrement jouables** aujourd'hui.

    S'appuie sur le chargeur de scripts (même porte D9 que le lancement d'une partie) : une carte
    est jouable si aucun de ses effets n'est refusé. Une seule passe, pas une requête par carte."""
    if not card_ids:
        return set()
    cartes = list(
        (await db.execute(select(Card).where(Card.id.in_(card_ids)))).scalars()
    )
    refus = await refus_scripts_par_carte(db, cartes)
    return {c.id for c in cartes if c.id not in refus}


async def creer_ou_maj_demande(
    db: AsyncSession, *, user_id: uuid.UUID, card_id: uuid.UUID, note: str | None = None
) -> CardPlayRequest:
    """Enregistre la demande d'un joueur pour une carte, ou **met à jour** la sienne si elle existe.

    Idempotent par ``(user_id, card_id)`` (contrainte d'unicité) : re-signaler la même carte ne crée
    pas de doublon, il rouvre la demande (statut « en attente », horodatage de résolution effacé) et
    rafraîchit la note. Le compte de demandeurs distincts par carte reste ainsi honnête."""
    ligne = (
        await db.execute(
            select(CardPlayRequest).where(
                CardPlayRequest.user_id == user_id, CardPlayRequest.card_id == card_id
            )
        )
    ).scalar_one_or_none()
    if ligne is None:
        ligne = CardPlayRequest(user_id=user_id, card_id=card_id)
        db.add(ligne)
    ligne.statut = REQUEST_STATUT_EN_ATTENTE
    ligne.note = note
    ligne.resolved_at = None
    await db.commit()
    await db.refresh(ligne)
    return ligne


async def demandes_du_joueur(db: AsyncSession, user_id: uuid.UUID) -> list[DemandeJoueur]:
    """Les demandes d'un joueur, chacune avec le nom de la carte et sa jouabilité courante.

    Bornée à ``user_id`` : un joueur ne voit **que** ses propres demandes — jamais celles d'un
    autre (isolation, comme toute donnée utilisateur)."""
    rows = (
        await db.execute(
            select(CardPlayRequest, Card.name)
            .join(Card, Card.id == CardPlayRequest.card_id)
            .where(CardPlayRequest.user_id == user_id)
            .order_by(CardPlayRequest.created_at.desc())
        )
    ).all()
    jouables = await _cartes_jouables(db, {r[0].card_id for r in rows})
    return [
        DemandeJoueur(demande=d, card_name=nom, jouable_maintenant=d.card_id in jouables)
        for d, nom in rows
    ]


async def file_agregee(db: AsyncSession) -> list[DemandeAgregeeCarte]:
    """La file agrégée par carte, pour la priorisation du chantier (jamais exposée à un joueur).

    Classe par nombre de demandeurs distincts décroissant : scripter en tête de cette liste
    satisfait le plus de joueurs. Chaque entrée dit aussi si la carte est **déjà** jouable (une
    demande peut être devenue caduque sans avoir été close)."""
    rows = (
        await db.execute(
            select(
                CardPlayRequest.card_id,
                Card.name,
                func.count(func.distinct(CardPlayRequest.user_id)),
                func.count()
                .filter(CardPlayRequest.statut == REQUEST_STATUT_EN_ATTENTE),
            )
            .join(Card, Card.id == CardPlayRequest.card_id)
            .group_by(CardPlayRequest.card_id, Card.name)
        )
    ).all()
    jouables = await _cartes_jouables(db, {cid for cid, _, _, _ in rows})
    file = [
        DemandeAgregeeCarte(
            card_id=cid,
            nom=nom,
            demandeurs=demandeurs,
            en_attente=en_attente,
            jouable_maintenant=cid in jouables,
        )
        for cid, nom, demandeurs, en_attente in rows
    ]
    file.sort(key=lambda d: (d.demandeurs, d.en_attente, d.nom), reverse=True)
    return file


async def marquer_resolue(
    db: AsyncSession, *, card_id: uuid.UUID, statut: str, note: str | None = None
) -> int:
    """Passe **toutes** les demandes d'une carte à un statut résolu (`scriptee`/`refusee`), pour
    l'exploitation quand un lot de scripts a traité la carte. Retourne le nombre de demandes
    touchées. Jamais appelé par une route : c'est un geste d'exploitation, pas une action joueur."""
    lignes = list(
        (
            await db.execute(select(CardPlayRequest).where(CardPlayRequest.card_id == card_id))
        ).scalars()
    )
    now = datetime.now(UTC)
    for ligne in lignes:
        ligne.statut = statut
        if note is not None:
            ligne.note = note
        ligne.resolved_at = None if statut == REQUEST_STATUT_EN_ATTENTE else now
    await db.commit()
    return len(lignes)


__all__ = [
    "DemandeJoueur",
    "DemandeAgregeeCarte",
    "creer_ou_maj_demande",
    "demandes_du_joueur",
    "file_agregee",
    "marquer_resolue",
    "REQUEST_STATUT_SCRIPTEE",
]
