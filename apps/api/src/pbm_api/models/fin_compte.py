"""Ce qu'une partie finie laisse sur les comptes (lot `j-fin-effets-compte`, jalon J4, DJ6).

Trois tables, et une seule idée : **les faits d'abord, les totaux ensuite**.

* :class:`GameResult` — le **fait**, une ligne par partie close. ``game_id`` y est *unique* : c'est
  la clé d'idempotence du lot, et elle vit dans la base, pas dans un ``if``. Deux clôtures de la
  même partie (reprise, rejeu, double événement de fin) ne peuvent pas produire deux lignes — la
  seconde insertion heurte la contrainte et ne fait rien.
* :class:`GameResultPlayer` — le fait **par siège** : le résultat de ce joueur, son deck, son
  adversaire, et les chiffres de sa partie recalculés depuis le journal
  (:func:`pbm_game.journal.recapitulatif.construire_recapitulatif`). C'est la matière première des
  agrégats « par deck » et « par adversaire » que `j-stats-joueur` affichera, et du classement
  privé de `j-classement-prive`.
* :class:`PlayerStats` — les **totaux** d'un compte. Ce n'est pas une source de vérité : c'est un
  **cache dérivé**, recalculé intégralement depuis :class:`GameResultPlayer` à chaque clôture
  (:func:`pbm_api.games.fin_compte.recalculer_stats_joueur`). Aucun compteur n'est incrémenté au fil
  de l'eau — c'est le risque nommé du lot (« personne ne remarque un compteur faux avant que
  quelqu'un ne compte »), et un cache recalculé le rend structurellement impossible.

**Pourquoi ces lignes n'ont PAS de clé étrangère vers ``games``.** Parce que la purge
(:func:`pbm_api.games.service.purger`) supprime les parties mortes de plus de
``settings.jeu_purge_anciennete_j`` jours — trente par défaut. Une clé étrangère en cascade
emporterait donc **tout l'historique du joueur au bout d'un mois**, sans un mot : exactement la
panne muette que ce lot doit empêcher. Le résultat d'une partie **survit** à la partie : la purge
libère le journal (volumineux, rejouable, sans intérêt passé un mois), pas la trace. Un résultat
dont la partie a été purgée n'a simplement plus de replay à proposer, ce que `j-stats-joueur` lit
en ne trouvant pas la partie.

**Ce que ce lot ne décide pas.** Les **badges** appartiennent à `j-profil-jeu` (dont la mission
est d'en arrêter la liste avec JF et Aymeric) et le **classement privé** à `j-classement-prive` :
DJ6 les veut « en option, activables par JF ». Aucune table de badge ni de points n'est donc posée
ici — on ne devine pas une liste de badges pour la jeter ensuite (D9). Ce que ce lot leur laisse,
c'est le socle exact qu'ils liront : une ligne par partie et par joueur, écrite une seule fois.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin

# --- Résultat d'un joueur dans une partie ------------------------------------
#: Ce joueur a gagné.
RESULTAT_VICTOIRE = "victoire"
#: Ce joueur a perdu (y compris par abandon, désertion ou temps écoulé).
RESULTAT_DEFAITE = "defaite"
#: Personne n'a gagné : égalité par les règles, ou partie close sans vainqueur (inactivité).
RESULTAT_EGALITE = "egalite"

#: Les trois résultats possibles. Un résultat hors de cet ensemble est un bug, jamais écrit.
RESULTATS: frozenset[str] = frozenset({RESULTAT_VICTOIRE, RESULTAT_DEFAITE, RESULTAT_EGALITE})


class GameResult(Base):
    """Le résultat d'une partie close — **une ligne par partie, jamais deux**.

    L'unicité de ``game_id`` est le cœur du lot : c'est elle qui rend la clôture idempotente, et
    elle est posée en base (``uq_game_results_game``) parce qu'un ``if`` ne survit pas à deux
    requêtes concurrentes. Le chemin d'écriture insère en ``ON CONFLICT DO NOTHING`` et ne touche à
    rien d'autre si la ligne existait déjà.

    ``comptabilisee`` dit si cette partie **compte** pour les totaux et les séries du joueur. Elle
    est fausse dans deux cas, et dans ces deux cas seulement :

    * une partie d'**entraînement** contre le bot (DJ7) — elle entre dans l'historique mais
      n'affecte « ni classement ni série » (critère d'acceptation du lot) ;
    * une partie **expirée** faute d'activité — personne ne l'a jouée jusqu'au bout, elle n'a pas
      de vainqueur mérité (voir :data:`~pbm_api.models.games.GAME_STATUS_EXPIREE`). La compter en
      défaite pour les deux joueurs serait inventer un résultat (D9).

    ``journal_numero`` est le nombre d'entrées de journal d'où viennent les chiffres : il dit **sur
    quoi** le calcul a porté, et permet de voir qu'un résultat réparé par le balayage a été calculé
    sur le journal complet.

    Ne porte pas de ``TimestampMixin`` : un résultat ne se met jamais à jour. Il naît une fois.
    """

    __tablename__ = "game_results"
    __table_args__ = (UniqueConstraint("game_id", name="uq_game_results_game"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Volontairement SANS clé étrangère : le résultat survit à la purge de la partie (en-tête).
    game_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    # Statut terminal de la partie : `terminee` (par les règles) ou `expiree` (inactivité).
    statut: Mapped[str] = mapped_column(String(16), nullable=False)
    raison_fin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vainqueur_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    entrainement: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comptabilisee: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Chiffres de la partie, recalculés depuis le journal (jamais comptés au fil de l'eau).
    coups: Mapped[int] = mapped_column(Integer, nullable=False)
    tours: Mapped[int] = mapped_column(Integer, nullable=False)
    # `None` quand les horodatages du journal ne permettent pas de conclure : on préfère l'absence
    # au faux (0 se lirait « partie instantanée »), comme le récapitulatif du moteur.
    duree_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    journal_numero: Mapped[int] = mapped_column(Integer, nullable=False)
    # Instant de fin : l'horodatage que la base a posé sur la dernière entrée du journal — une
    # donnée serveur, pas une date reçue. C'est ce qui date l'historique une fois la partie purgée.
    finie_a: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GameResultPlayer(Base):
    """Ce que la partie laisse à **un** joueur : résultat, deck, adversaire et chiffres.

    Une ligne par siège, unique par ``(game_id, user_id)``. Les six compteurs sont ceux du
    récapitulatif du moteur, recalculés depuis le journal : ils ne sont pas accumulés pendant la
    partie, donc une reconnexion qui rejoue le journal ne les double pas.

    ``deck_id`` et ``adversaire_user_id`` sont ici pour les agrégats de `j-stats-joueur` (« ce deck
    gagne surtout contre… ») : un ``GROUP BY`` sur cette table suffit, sans jointure à une partie
    qui aura peut-être été purgée. ``adversaire_bot`` distingue le bot d'entraînement d'un vrai
    compte — ``adversaire_user_id`` pointe alors le compte réservé du bot, qu'on ne veut pas voir
    apparaître dans un tableau d'adversaires.

    ``comptabilisee`` et ``finie_a`` sont dénormalisés depuis :class:`GameResult` : le recalcul des
    totaux d'un joueur lit **cette table seule**, triée par ``finie_a`` — une requête, aucune
    jointure, et un ordre chronologique qui rend les séries reproductibles.
    """

    __tablename__ = "game_result_players"
    __table_args__ = (
        UniqueConstraint("game_id", "user_id", name="uq_game_result_players_game_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Volontairement SANS clé étrangère vers `games` (en-tête du module) : la trace survit à la
    # purge. `user_id` en cascade, en revanche : supprimer un compte efface bien son historique.
    game_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seat: Mapped[int] = mapped_column(Integer, nullable=False)
    # Le deck joué, en `SET NULL` : supprimer un deck ne doit pas effacer l'historique des parties
    # qu'il a jouées (même choix que `game_players.deck_id`).
    deck_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("decks.id", ondelete="SET NULL"), nullable=True
    )
    adversaire_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    adversaire_bot: Mapped[bool] = mapped_column(Boolean, nullable=False)
    resultat: Mapped[str] = mapped_column(String(8), nullable=False)
    comptabilisee: Mapped[bool] = mapped_column(Boolean, nullable=False)
    finie_a: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duree_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Les six chiffres du récapitulatif du moteur, pour ce joueur.
    degats_infliges: Mapped[int] = mapped_column(Integer, nullable=False)
    kos_infliges: Mapped[int] = mapped_column(Integer, nullable=False)
    recompenses_prises: Mapped[int] = mapped_column(Integer, nullable=False)
    cartes_jouees: Mapped[int] = mapped_column(Integer, nullable=False)
    energies_attachees: Mapped[int] = mapped_column(Integer, nullable=False)
    coups_joues: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PlayerStats(Base, TimestampMixin):
    """Les totaux d'un compte — un **cache dérivé**, jamais une source de vérité.

    Chaque champ est recalculé depuis :class:`GameResultPlayer` (une requête, triée par date) à
    chaque clôture : il n'existe aucun chemin qui incrémente un compteur. Supprimer une ligne de
    cette table n'est donc pas une perte de données — le recalcul la reconstruit à l'identique,
    ce que la suite de tests vérifie.

    **Ce que « compte » veut dire.** Les sept premiers champs ne portent que les parties
    *comptabilisées* (voir :class:`GameResult`) : ni l'entraînement contre le bot, ni les parties
    expirées faute d'activité. L'entraînement n'est pas perdu pour autant — il a ses deux champs à
    lui, parce qu'un joueur qui s'est entraîné dix heures a le droit de le voir.

    ``serie_en_cours`` est le nombre de victoires **consécutives** les plus récentes : une défaite
    comme une égalité la remettent à zéro (une égalité n'est pas une victoire, et prolonger une
    série sur une égalité serait flatteur, donc faux). ``meilleure_serie`` est la plus longue
    jamais atteinte, et elle ne redescend jamais.
    """

    __tablename__ = "player_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    parties: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    victoires: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    defaites: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    egalites: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    serie_en_cours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    meilleure_serie: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    temps_jeu_s: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    parties_entrainement: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    temps_jeu_entrainement_s: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    # Date de la dernière partie close du joueur, entraînement compris (c'est « la dernière fois
    # que j'ai joué », pas « la dernière fois que ça a compté »). `None` si aucune.
    derniere_partie_a: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = [
    "RESULTATS",
    "RESULTAT_DEFAITE",
    "RESULTAT_EGALITE",
    "RESULTAT_VICTOIRE",
    "GameResult",
    "GameResultPlayer",
    "PlayerStats",
]
