"""Schémas de réponse des routes de parties (lot `j-partie-service`).

Volontairement **minimaux et sans information cachée** : ce lot expose seulement de quoi lister ses
parties et constater l'état d'une partie (statut, sièges, dernier coup, fin). La **vue
autoritaire** (plateau projeté pour le joueur, sans la main adverse ni la graine) est le lot
`j-autorite-vues` ; la graine reste un secret serveur et n'apparaît jamais ici.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ActionIn(BaseModel):
    """Un coup soumis par un joueur (lot `j-autorite-vues`).

    `type` et `params` décrivent le coup ; `numero_attendu` est le numéro d'action que le client
    croit être le prochain — c'est la clé d'**idempotence** (un renvoi réseau du même coup au même
    numéro est sans effet) et de détection de conflit. L'auteur du coup n'est **jamais** dans le
    corps : le serveur l'impose depuis la session (`str(user_id)`) — un client ne peut pas agir sous
    une autre identité.
    """

    type: str
    params: dict = Field(default_factory=dict)
    numero_attendu: int


class GamePlayerOut(BaseModel):
    """Un siège de la partie : l'utilisateur et le deck joué."""

    user_id: uuid.UUID
    seat: int
    deck_id: uuid.UUID | None


class GameSummaryOut(BaseModel):
    """Résumé d'une partie pour la liste « mes parties »."""

    id: uuid.UUID
    status: str
    current_numero: int
    vainqueur_user_id: uuid.UUID | None
    raison_fin: str | None
    created_at: datetime
    updated_at: datetime


class GameDetailOut(GameSummaryOut):
    """Détail d'une partie : le résumé, l'engagement (commit-reveal) et les deux sièges.

    `engagement` est l'empreinte de la graine, publiable (commit-reveal) ; la graine elle-même
    n'est jamais renvoyée. `journal_version` dit sous quel schéma le journal a été écrit.
    """

    engagement: str
    journal_version: int
    players: list[GamePlayerOut]
