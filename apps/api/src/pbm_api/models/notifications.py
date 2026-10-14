"""Modèles de persistance des **notifications du jeu** (lot `j-notifications-jeu`).

Un jeu à deux où personne ne sait que l'autre attend ne se joue pas : une notification bien placée
remplace dix messages. Deux tables suffisent, et elles disent toutes les deux la même chose sous
deux angles — ce qui a été notifié, et ce que le joueur accepte de recevoir.

* :class:`GameNotification` — **une** notification destinée à **un** compte. ``genre`` nomme
  l'événement (voir les constantes ci-dessous), ``game_id`` la partie concernée quand il y en a
  une (une invitation reçue n'a pas encore de partie : la colonne est alors nulle). ``donnees``
  porte le contexte d'affichage (pseudo de l'adversaire, secondes restantes…) — **jamais** un
  secret, jamais la main de l'adversaire : une notification est un libellé, pas une vue de partie.
* :class:`NotificationReglages` — **une ligne par compte**, créée à la première écriture de
  réglage. Son absence n'est pas une anomalie : elle vaut « les défauts »
  (:mod:`pbm_api.notifications.regles`), ce qui évite d'écrire une ligne pour chaque compte qui
  n'a jamais touché à ses réglages.

``silencieuse`` est la trace du **silence nocturne** : pendant la fenêtre de silence, la
notification est bien enregistrée (elle sera lue au réveil, rien n'est perdu) mais **aucun relais
hors application** ne part et l'interface ne la sonne pas. C'est la différence entre « tu l'as
manquée » et « on ne t'a pas réveillé ».

``game_id`` est en **CASCADE** (contrairement aux incidents de ``jeu_incidents``, qui sont en SET
NULL) : une notification sans sa partie n'a plus rien à dire — « c'est ton tour » sur une partie
purgée est un mensonge, pas une archive. La purge des parties mortes emporte donc leurs
notifications.
"""

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin

# --- Les genres de notification (vocabulaire stable : base, API et écran s'y réfèrent) -------
#: Quelqu'un vous invite à jouer (lot `j-invitations`). Seul genre qui n'a **pas** de partie, et
#: seul genre relayé par **e-mail** (une invitation peut attendre des heures ; les autres non).
NOTIF_INVITATION_RECUE = "invitation_recue"
#: La file d'attente vous a trouvé un adversaire (lot `j-file-attente`) : la partie existe.
NOTIF_ADVERSAIRE_TROUVE = "adversaire_trouve"
#: C'est à vous de jouer. **Le genre à plafonner le plus sévèrement** : notifier chaque tour
#: transforme le jeu en sonnerie permanente (le risque nommé par le lot).
NOTIF_TON_TOUR = "ton_tour"
#: Votre horloge descend sous le seuil d'alerte (lot `j-timer`) : il faut jouer maintenant.
NOTIF_TEMPS_BIENTOT_ECOULE = "temps_bientot_ecoule"
#: L'adversaire déconnecté est revenu : les horloges reprennent, la partie peut continuer.
NOTIF_ADVERSAIRE_REVENU = "adversaire_revenu"
#: La partie s'est terminée sans être jouée jusqu'au bout : abandon volontaire (R-14.3) ou
#: désertion d'un joueur qui n'est pas revenu (R-14.6). Vous avez gagné par forfait.
NOTIF_PARTIE_FORFAIT = "partie_forfait"

#: L'ensemble des genres reconnus. Un genre hors de cet ensemble est un bug — il n'est jamais
#: écrit : :func:`pbm_api.notifications.regles.decider` lève plutôt que d'enregistrer un libellé
#: que l'écran ne saurait pas traduire.
NOTIF_GENRES: frozenset[str] = frozenset(
    {
        NOTIF_INVITATION_RECUE,
        NOTIF_ADVERSAIRE_TROUVE,
        NOTIF_TON_TOUR,
        NOTIF_TEMPS_BIENTOT_ECOULE,
        NOTIF_ADVERSAIRE_REVENU,
        NOTIF_PARTIE_FORFAIT,
    }
)


class GameNotification(Base):
    """Une notification destinée à un compte — le canal *dans l'application*.

    Pas de ``TimestampMixin`` : une notification ne se modifie pas, elle se lit. ``created_at``
    suffit (``lue_at`` date la lecture, et reste nul tant qu'elle attend).

    L'index composite ``(user_id, lue_at)`` sert la requête de tous les écrans — « mes non lues »
    — et l'index ``(user_id, game_id, genre)`` sert le **plafond par partie**
    (:mod:`pbm_api.notifications.regles`), compté à chaque émission : sans lui, chaque notification
    coûterait un balayage de la table du compte.
    """

    __tablename__ = "game_notifications"
    __table_args__ = (
        Index("ix_game_notifications_user_lue", "user_id", "lue_at"),
        Index("ix_game_notifications_user_game_genre", "user_id", "game_id", "genre"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Le destinataire. CASCADE : un compte supprimé n'a plus de notifications à lire.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    genre: Mapped[str] = mapped_column(String(32), nullable=False)
    # La partie concernée, ou nul pour une invitation reçue (aucune partie n'existe encore).
    game_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=True, index=True
    )
    #: Contexte d'affichage, jamais un secret : pseudo de l'adversaire, secondes restantes, raison
    #: de fin. L'écran traduit ``genre`` + ``donnees`` en une phrase ; le serveur ne stocke pas de
    #: phrase (elle changerait de langue ou de formulation sans migration).
    donnees: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    #: Enregistrée **sans alerte** : émise pendant le silence nocturne. Aucun relais hors
    #: application n'est parti, et l'interface ne la sonne pas — elle se lit au réveil.
    silencieuse: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    #: Instant de lecture, nul tant qu'elle attend. Sert aussi l'**anti-doublon** : on ne redit pas
    #: « c'est ton tour » quand la précédente n'a même pas été lue.
    lue_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationReglages(Base, TimestampMixin):
    """Les réglages de notification d'un compte — ce qu'il accepte de recevoir, et quand.

    Une ligne par compte, **créée à la première modification** : son absence vaut les défauts de
    :mod:`pbm_api.notifications.regles`, ce qui évite d'écrire une ligne pour chaque compte qui n'a
    jamais ouvert ses réglages.

    ``genres_desactives`` est une **liste JSON de genres** plutôt qu'une colonne booléenne par
    genre : le vocabulaire des genres s'étendra (le jeu est en construction), et chaque nouveau
    genre coûterait sinon une migration. Un genre inconnu dans cette liste est inoffensif — il ne
    correspond à rien, donc ne désactive rien ; l'API refuse de l'y écrire
    (:mod:`pbm_api.routers.notifications`).

    ``silence_debut`` / ``silence_fin`` bornent le **silence nocturne**, lu dans ``fuseau`` (le
    joueur est un enfant : « 21 h » veut dire 21 h chez lui, pas en UTC). La fenêtre peut franchir
    minuit — c'est même le cas par défaut.
    """

    __tablename__ = "notification_reglages"

    #: Clé primaire **et** clé étrangère : un compte a au plus une ligne de réglages.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    genres_desactives: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    silence_actif: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    silence_debut: Mapped[time] = mapped_column(Time, nullable=False, server_default="21:00:00")
    silence_fin: Mapped[time] = mapped_column(Time, nullable=False, server_default="07:00:00")
    fuseau: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Europe/Paris")
    #: Relais **e-mail** de l'invitation reçue (le seul genre qui en a un, cf. la fiche du lot).
    relais_email_invitation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    #: Relais **notification web (PWA)**. Le réglage existe et est respecté dès maintenant ; le
    #: transport, lui, n'est pas branché tant que `v6-pwa` n'est pas livré — et son absence est
    #: **dite** à chaque fois, jamais tue (:mod:`pbm_api.notifications.relais`).
    relais_push: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
