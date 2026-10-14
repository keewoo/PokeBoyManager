"""Écriture des incidents du jeu — **hors de la transaction de l'appelant**, et c'est le point.

Un coup refusé lève une exception : la requête HTTP se termine en erreur, la session de la requête
est fermée **sans commit**, et tout ce qui y était en attente est perdu. Écrire la trace dans cette
session aurait donc produit exactement l'inverse du but du lot : l'incident qu'on voulait compter
disparaît avec le coup qu'on a refusé. Même raisonnement pour une partie refusée en D9 (le
lancement qui l'a demandée est annulé) et pour une erreur de moteur (on abandonne le coup).

D'où une **session autonome** : la trace est écrite et validée pour elle-même. Deux conséquences
voulues — la supervision ne peut pas faire échouer le jeu (une écriture de trace qui casse est
journalisée, pas propagée), et le jeu ne peut pas effacer sa supervision.

La fabrique de session est **injectable** (:func:`fabrique_de_session`) : la suite de tests la
remplace par une session liée à la connexion du test, pour que les lignes écrites disparaissent
avec le rollback de fin de test au lieu de s'accumuler dans la base de test.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.db import async_session_factory
from pbm_api.models.observabilite import INCIDENT_GENRES, JeuIncident

logger = logging.getLogger(__name__)

#: Fabrique de session utilisée pour écrire une trace. Remplacée dans les tests ; en production
#: c'est la fabrique ordinaire de l'application (une session, une transaction, un commit).
_fabrique: Callable[[], AsyncSession] = async_session_factory


def fabrique_de_session() -> AsyncSession:
    """La session dans laquelle écrire une trace — indirection pour que les tests l'injectent."""
    return _fabrique()


def definir_fabrique(fabrique: Callable[[], AsyncSession] | None) -> None:
    """Remplace (ou rétablit, avec ``None``) la fabrique de session des traces.

    Réservé aux tests : en production, la fabrique de l'application est la bonne.
    """
    global _fabrique
    _fabrique = fabrique or async_session_factory


async def consigner_incident(
    *,
    genre: str,
    motif: str,
    game_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    type_action: str | None = None,
    detail: str | None = None,
    horodatage: datetime | None = None,
) -> None:
    """Écrit un incident du jeu, et ne laisse **jamais** son échec casser la partie en cours.

    ``genre`` doit appartenir à :data:`pbm_api.models.observabilite.INCIDENT_GENRES` : un genre
    inconnu est une erreur de programmation, elle est journalisée en ``error`` et rien n'est écrit
    (un compteur sur un genre fantôme ne signalerait rien à personne).

    L'échec d'écriture est attrapé et journalisé en ``error``, pas propagé : la supervision est là
    pour observer le jeu, pas pour l'interrompre. Ce n'est pas un repli silencieux — l'échec part
    dans le journal du serveur avec sa cause, et un compteur d'incidents qui tombe brutalement à
    zéro est lui-même visible dans la métrique.
    """
    if genre not in INCIDENT_GENRES:
        logger.error("incident de genre inconnu « %s » — rien écrit (motif %s).", genre, motif)
        return
    try:
        async with fabrique_de_session() as session:
            incident = JeuIncident(
                genre=genre,
                motif=motif[:64],
                game_id=game_id,
                user_id=user_id,
                type_action=type_action[:48] if type_action else None,
                detail=detail,
            )
            if horodatage is not None:
                incident.created_at = horodatage
            session.add(incident)
            await session.commit()
    except Exception:  # noqa: BLE001 — la supervision n'interrompt jamais le jeu
        logger.exception(
            "échec d'écriture d'un incident du jeu (genre %s, motif %s) : la trace est perdue, "
            "le jeu continue.",
            genre,
            motif,
        )


__all__ = ["consigner_incident", "definir_fabrique", "fabrique_de_session"]
