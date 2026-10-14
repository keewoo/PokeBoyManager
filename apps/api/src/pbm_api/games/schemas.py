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


class PartageReplayIn(BaseModel):
    """Ouvrir le replay à un compte invité, désigné par son **pseudo** (lot `j-replay`).

    Le pseudo, pas l'e-mail : c'est l'identifiant public d'un joueur (comme pour une invitation à
    jouer), et il n'apprend rien à qui le saisit — une adresse, si.
    """

    pseudo: str = Field(min_length=1, max_length=64)


class PartageReplayOut(BaseModel):
    """Un compte à qui le replay est ouvert : qui, par qui, et depuis quand.

    Aucune adresse e-mail : le pseudo suffit à reconnaître la personne à l'écran, et un partage ne
    justifie pas d'exposer l'adresse d'un autre compte.
    """

    user_id: uuid.UUID
    pseudo: str | None
    partage_par_user_id: uuid.UUID
    created_at: datetime


# --- Fin de partie : récapitulatif et revanche (lot `j-partie-fin-ui`) --------
# Le récapitulatif est **recalculé depuis le journal** à chaque demande (voir
# `pbm_api.games.recapitulatif` et le module pur `pbm_game.journal.recapitulatif`) : aucun de ces
# chiffres n'est stocké, donc aucun ne peut dériver.


class StatsJoueurOut(BaseModel):
    """Ce qu'un joueur a fait dans la partie — un siège, un compte, et ses compteurs.

    ``degats_infliges`` est le total **annoncé par ses attaques** (après faiblesse, résistance et
    modificateurs, R-10.9) : les dégâts d'un état spécial au Checkup ne sont infligés par personne
    et ne figurent donc dans la colonne de personne. ``cartes_jouees`` **exclut** les Énergies,
    comptées à part — « 12 cartes jouées » ne doit pas vouloir dire « dont 9 Énergies ».
    """

    seat: int
    user_id: uuid.UUID
    pseudo: str | None
    degats_infliges: int
    kos_infliges: int
    recompenses_prises: int
    cartes_jouees: int
    energies_attachees: int
    coups_joues: int


class MeilleurCoupOut(BaseModel):
    """Le coup qui a infligé le plus de dégâts, et s'il a mis K.O.

    ``user_id`` peut être ``None`` si le coup n'a pas pu être rattaché à un siège : l'écran
    l'affiche alors sans l'attribuer, plutôt que de l'attribuer au mauvais joueur.
    """

    numero: int
    user_id: uuid.UUID | None
    degats: int
    ko: bool


class RecapitulatifOut(BaseModel):
    """Le récapitulatif d'une partie finie, recalculé depuis son journal.

    ``duree_s`` vaut ``None`` quand les horodatages du journal ne permettent pas de la calculer :
    l'écran dit alors « durée inconnue », jamais « 0 s ». ``joueurs`` est dans l'ordre des sièges.
    """

    game_id: uuid.UUID
    statut: str
    raison_fin: str | None
    vainqueur_user_id: uuid.UUID | None
    entrainement: bool
    coups: int
    tours: int
    debut: str | None
    fin: str | None
    duree_s: int | None
    joueurs: list[StatsJoueurOut]
    meilleur_coup: MeilleurCoupOut | None


class RevancheOut(BaseModel):
    """La partie créée (ou retrouvée) par une demande de revanche.

    ``deja_creee`` est vrai quand une partie en cours existait déjà entre ces deux comptes : les
    deux joueurs ont cliqué « Revanche », et on les envoie au **même** plateau au lieu de créer
    une seconde partie (voir `pbm_api.games.revanche`). La réponse est alors 200, pas 201.
    """

    game_id: uuid.UUID
    deja_creee: bool
