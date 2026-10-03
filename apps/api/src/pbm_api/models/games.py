"""Modèle de persistance des **parties de jeu** (lot `j-partie-service`).

Une partie n'est pas une photo de son plateau : c'est un **état initial**, une **graine**
d'aléatoire et un **journal d'actions numéroté** (principe « tout est rejouable » du jalon J1,
porté par `pbm_game.journal`). Ces tables stockent exactement cela — jamais l'état courant comme
source de vérité :

* :class:`Game` — l'enveloppe : état initial, graine (secret serveur, jamais renvoyé au client),
  engagement (commit-reveal publiable), et un **cache** du dernier numéro appliqué + son empreinte
  (reconstructible par rejeu, gardé pour l'affichage et la coordination) ;
* :class:`GamePlayer` — les deux sièges, chacun un utilisateur et le deck joué ;
* :class:`GameEvent` — le **journal**, strictement *append-only* : une entrée numérotée porte ce
  qui a été demandé (l'action), ce que le moteur en a fait (les événements) et l'empreinte de
  l'état résultant. La contrainte d'unicité `(game_id, numero)` est le socle de l'idempotence par
  numéro d'action (risque nommé du lot : deux requêtes concurrentes ne doivent pas appliquer deux
  fois le même coup) ;
* :class:`GameSnapshot` — des **instantanés** de compaction (état + état du Rng à un point du
  journal), pour ne pas rejouer 400 coups à chaque reprise. Un instantané est un cache, jamais la
  source de vérité.

Rien ici ne met à jour une entrée de journal existante : une entrée écrite ne bouge plus. C'est ce
qui rend le rejeu fidèle et l'anti-triche possible (`pbm_game.journal.rejouer` compare l'empreinte
au coup près).
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin

# --- Statuts d'une partie (stables, lus par le service et les écrans) ---------
#: La partie est en cours : elle accepte des actions.
GAME_STATUS_EN_COURS = "en_cours"
#: La partie est terminée par une règle de fin (R-14) : vainqueur figé, plus aucune action.
GAME_STATUS_TERMINEE = "terminee"
#: La partie a expiré faute d'activité (abandon silencieux) : figée, mais distincte d'une fin par
#: les règles — elle n'a pas de vainqueur « mérité ». La purge la ramasse après un délai.
GAME_STATUS_EXPIREE = "expiree"

#: L'ensemble des statuts reconnus. Un statut hors de cet ensemble est un bug, jamais écrit.
GAME_STATUTS: frozenset[str] = frozenset(
    {GAME_STATUS_EN_COURS, GAME_STATUS_TERMINEE, GAME_STATUS_EXPIREE}
)


class Game(Base, TimestampMixin):
    """Une partie persistée : son état initial, sa graine, et un cache du dernier coup appliqué.

    `graine` est le **secret** d'aléatoire de la partie (commit-reveal) : il n'est révélé qu'à la
    fin et n'est **jamais** renvoyé au client en cours de partie (sinon la pioche adverse serait
    prévisible). `engagement` en est l'empreinte, publiable dès le début. `current_numero` et
    `current_empreinte` sont un **cache** reconstructible par rejeu (`pbm_game.journal.rejouer`) :
    on les garde pour afficher la partie et coordonner les écritures concurrentes sans tout
    rejouer, jamais comme source de vérité.
    """

    __tablename__ = "games"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=GAME_STATUS_EN_COURS, index=True
    )
    # État au coup 0 (forme JSON de `pbm_game.state`), avant toute action.
    etat_initial: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Graine d'aléatoire en hexadécimal — secret serveur, jamais exposé en cours de partie.
    graine: Mapped[str] = mapped_column(String(128), nullable=False)
    # Engagement (empreinte de la graine) publiable avant la partie (commit-reveal).
    engagement: Mapped[str] = mapped_column(String(64), nullable=False)
    journal_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Cache : nombre d'entrées de journal appliquées, et empreinte de l'état à ce point.
    current_numero: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_empreinte: Mapped[str] = mapped_column(String(64), nullable=False)
    # Fin de partie (R-14) : le gagnant (None pour une égalité ou une partie non finie) et le motif.
    vainqueur_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    raison_fin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Dernière action appliquée et échéance d'inactivité (expiration des parties abandonnées).
    last_action_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # Horloges de la partie (lot j-timer) : forme JSON de `pbm_game.horloges.EtatHorloges`,
    # calculée depuis des horodatages. C'est une donnée de la partie (survit au F5), jamais un
    # minuteur en mémoire. Nullable : les parties d'avant le lot n'en ont pas.
    horloges: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Partie d'ENTRAÎNEMENT contre un bot (lot `j-mode-solo`, DJ7) : elle entre dans l'historique
    # du joueur mais **ne compte pas** (ni classement ni séries — qui n'existent pas encore ; le
    # marqueur est posé pour qu'ils l'excluent dès qu'ils existeront). Dénormalisé ici (plutôt que
    # déduit du siège bot) pour que la liste « mes parties » le lise sans charger les sièges, et
    # pour que la boucle d'application sache piloter le bot sans requête supplémentaire.
    entrainement: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class GamePlayer(Base, TimestampMixin):
    """Un siège d'une partie : un utilisateur et le deck qu'il joue.

    `seat` (0/1) fixe l'ordre des joueurs dans l'état du moteur ; l'identifiant de joueur du moteur
    est `str(user_id)` (déterministe, donc rejouable). `deck_id` est en `SET NULL` : supprimer un
    deck ne doit pas effacer l'historique d'une partie déjà jouée (son état initial porte déjà les
    cartes résolues). Deux contraintes d'unicité empêchent un même utilisateur ou un même siège en
    double dans une partie.
    """

    __tablename__ = "game_players"
    __table_args__ = (
        UniqueConstraint("game_id", "seat", name="uq_game_players_game_seat"),
        UniqueConstraint("game_id", "user_id", name="uq_game_players_game_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    game_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deck_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("decks.id", ondelete="SET NULL"), nullable=True
    )
    seat: Mapped[int] = mapped_column(Integer, nullable=False)
    # Niveau du bot quand CE siège est tenu par le bot d'entraînement (lot `j-mode-solo`) :
    # "hasard" | "correct" | "coriace" (les trois niveaux de DJ7). `None` pour un siège humain —
    # un siège dont `bot_niveau` est renseigné est donc, et seulement dans ce cas, celui du bot.
    # Le bot joue côté serveur (il ne passe jamais par HTTP) ; `user_id` pointe le compte réservé.
    bot_niveau: Mapped[str | None] = mapped_column(String(16), nullable=True)


class GameEvent(Base):
    """Une entrée du **journal** d'une partie — numérotée, *append-only*, autosuffisante.

    Ne porte **pas** de `TimestampMixin` : son `updated_at` n'aurait aucun sens (une entrée de
    journal ne se met jamais à jour). `horodatage` est l'instant fourni au moteur au moment du coup
    (le moteur est pur, sans horloge) ; `created_at` est posé par la base à l'insertion.

    La contrainte d'unicité `(game_id, numero)` est le **socle de l'idempotence** : deux requêtes
    concurrentes réclamant le même numéro ne peuvent pas créer deux entrées — la seconde échoue, et
    le service la traite en rejeu idempotent ou en conflit (risque nommé du lot).
    """

    __tablename__ = "game_events"
    __table_args__ = (
        UniqueConstraint("game_id", "numero", name="uq_game_events_game_numero"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    game_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    auteur: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evenements: Mapped[list] = mapped_column(JSONB, nullable=False)
    horodatage: Mapped[str] = mapped_column(String(64), nullable=False)
    empreinte: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GameSnapshot(Base):
    """Un **instantané** de compaction : l'état et l'état du Rng à un point du journal.

    Permet de reprendre une longue partie sans rejouer tout son journal (`pbm_game.journal.
    reprendre`). C'est un **cache** : la source de vérité reste le journal. `(game_id,
    numero_entrees)` est unique — un même point n'a qu'un instantané.
    """

    __tablename__ = "game_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "game_id", "numero_entrees", name="uq_game_snapshots_game_numero_entrees"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    game_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero_entrees: Mapped[int] = mapped_column(Integer, nullable=False)
    etat: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rng_etat: Mapped[dict] = mapped_column(JSONB, nullable=False)
    empreinte: Mapped[str] = mapped_column(String(64), nullable=False)
    journal_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
