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
    """Un siège de la partie : l'utilisateur, le deck joué, et le niveau du bot le cas échéant.

    ``bot_niveau`` est ``None`` pour un siège humain ; renseigné (« hasard »/« correct »/
    « coriace »), il désigne le siège tenu par le bot d'entraînement (lot `j-mode-solo`).
    ``adversaire_ia`` est vrai quand ce siège est tenu par l'IA du joueur (lot `j-adversaire-ia`) ;
    ``bot_niveau`` est alors son niveau de repli.
    """

    user_id: uuid.UUID
    seat: int
    deck_id: uuid.UUID | None
    bot_niveau: str | None = None
    adversaire_ia: bool = False


class GameSummaryOut(BaseModel):
    """Résumé d'une partie pour la liste « mes parties » (l'historique).

    ``entrainement`` distingue une partie contre le bot (lot `j-mode-solo`) : elle figure dans
    l'historique mais ne compte ni au classement ni aux séries.
    """

    id: uuid.UUID
    status: str
    current_numero: int
    vainqueur_user_id: uuid.UUID | None
    raison_fin: str | None
    created_at: datetime
    updated_at: datetime
    entrainement: bool = False


class IaCoutOut(BaseModel):
    """Le **coût estimé** de l'adversaire IA sur une partie (lot `j-adversaire-ia`).

    ``appels`` et ``jetons`` sont les compteurs réels (``games.ia_appels``/``ia_tokens``) ;
    ``plafond_appels`` est la limite par partie. Le coût en euros n'est pas encore calculé (aucune
    table de tarification par modèle dans ce dépôt — reste à faire, documenté) : l'écran affiche le
    nombre d'appels et de jetons, honnêtement, plutôt qu'un chiffre inventé.
    """

    appels: int
    jetons: int
    plafond_appels: int


class GameDetailOut(GameSummaryOut):
    """Détail d'une partie : le résumé, l'engagement (commit-reveal) et les deux sièges.

    `engagement` est l'empreinte de la graine, publiable (commit-reveal) ; la graine elle-même
    n'est jamais renvoyée. `journal_version` dit sous quel schéma le journal a été écrit.
    ``ia_cout`` n'est présent que pour une partie contre « mon IA » : le coût estimé à afficher.
    """

    engagement: str
    journal_version: int
    players: list[GamePlayerOut]
    ia_cout: IaCoutOut | None = None


class CoupConseille(BaseModel):
    """Le coup que le coach suggère (lot `j-coach-ia`) — une **suggestion**, pas un coup appliqué.

    ``index`` est la place du coup dans la liste légale (pour le surligner côté écran) ; ``type`` et
    ``params`` décrivent l'action, de quoi pré-remplir le geste que le joueur validera lui-même. Le
    serveur n'applique rien : c'est l'enfant qui joue.
    """

    index: int
    etiquette: str
    type: str
    params: dict


class ConseilOut(BaseModel):
    """La réponse du coach à une demande de conseil (lot `j-coach-ia`).

    ``coup`` est nul quand aucun conseil n'est possible (ce n'est pas son tour, l'IA n'a rien
    trouvé) : ``raison`` le dit alors, jamais un coup inventé. ``conseils_utilises`` /
    ``conseils_restants`` donnent l'état du plafond de conseils de la partie.
    """

    coup: CoupConseille | None
    explication: str | None
    raison: str | None
    conseils_utilises: int
    conseils_restants: int


class MomentBilanOut(BaseModel):
    """Un moment décisif du bilan (lot `j-coach-ia`) : le coup cité et le commentaire du coach.

    ``numero`` et ``etiquette`` désignent un coup **réellement joué** (vérifié contre le journal) ;
    ``commentaire`` est la phrase du coach sur ce moment.
    """

    numero: int
    etiquette: str
    commentaire: str


class BilanOut(BaseModel):
    """Le bilan de fin de partie (lot `j-coach-ia`) : un résumé et quelques moments décisifs."""

    resume: str
    moments: list[MomentBilanOut]
