"""Le **canal de notification** du jeu : émettre, lire, régler (lot `j-notifications-jeu`).

Ce module est la seule porte par laquelle une notification entre dans l'application. Il fait trois
choses, et rien d'autre :

1. **il lit les réglages** du destinataire (:func:`charger_reglages`) — l'absence de ligne vaut les
   défauts, ce qui évite d'écrire une ligne pour chaque compte qui n'a jamais ouvert ses réglages ;
2. **il compte** ce que la partie a déjà produit pour ce destinataire (:func:`_compteurs`) — c'est
   l'entrée des plafonds, et donc du critère « aucune partie ne produit plus de notifications que
   le plafond fixé » ;
3. **il soumet le tout aux règles** (:mod:`pbm_api.notifications.regles`, pur) et n'écrit que si
   elles l'autorisent — puis déclenche les relais hors application que la décision a permis.

Le découpage n'est pas un ornement : les règles se testent sans Postgres (silence nocturne à
n'importe quelle heure, plafonds à n'importe quel compteur), et ce module ne porte que du SQL.

**Un refus n'est jamais muet** : :func:`notifier` journalise le motif rendu par les règles et
renvoie ``None``. C'est ce qui permet de répondre à « pourquoi n'ai-je rien reçu ? » sans deviner.

**Une notification ne coûte jamais un coup.** Les points d'accroche dans le moteur de jeu
(:mod:`pbm_api.games.service`) appellent :func:`notifier_sans_casser`, qui enveloppe l'émission : si
elle échoue, on perd la notification en le disant (ERROR avec la pile), jamais le coup du joueur.
Ce n'est pas un repli silencieux — c'est une hiérarchie assumée entre l'accessoire et l'essentiel.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, time

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.email import EmailSender
from pbm_api.models import User
from pbm_api.models.notifications import (
    NOTIF_GENRES,
    GameNotification,
    NotificationReglages,
)
from pbm_api.notifications import relais
from pbm_api.notifications.regles import (
    Compteurs,
    Decision,
    Reglages,
    decider,
)

logger = logging.getLogger(__name__)

#: Nombre maximal de notifications rendues par une lecture. Une boîte de notifications n'est pas un
#: historique : au-delà, ce qui compte est déjà dans les écrans du jeu (parties en cours,
#: invitations reçues).
LIMITE_LECTURE = 50


class NotificationIntrouvable(LookupError):
    """Aucune notification de cet identifiant **pour ce compte** (→ 404).

    Bornée au destinataire : une notification d'autrui est *introuvable*, jamais « interdite » —
    répondre 403 révélerait son existence (même règle que partout dans le jeu, D11).
    """


# --- Réglages ---------------------------------------------------------------------------------


def _reglages_depuis_ligne(ligne: NotificationReglages | None) -> Reglages:
    """Traduit la ligne de base en vue pure, ou rend les défauts si le compte n'en a pas.

    C'est ici que « pas de ligne » devient « les défauts », une fois pour toutes : aucun appelant
    n'a à connaître cette convention, et il n'existe pas deux jeux de défauts (celui du modèle en
    ``server_default`` et celui de :class:`~pbm_api.notifications.regles.Reglages` doivent rester
    d'accord — un test le vérifie).
    """
    if ligne is None:
        return Reglages()
    return Reglages(
        genres_desactives=frozenset(ligne.genres_desactives or ()),
        silence_actif=ligne.silence_actif,
        silence_debut=ligne.silence_debut,
        silence_fin=ligne.silence_fin,
        fuseau=ligne.fuseau,
        relais_email_invitation=ligne.relais_email_invitation,
        relais_push=ligne.relais_push,
    )


async def charger_reglages(db: AsyncSession, user_id: uuid.UUID) -> Reglages:
    """Les réglages de notification du compte — les défauts s'il n'a jamais rien réglé."""
    ligne = await db.get(NotificationReglages, user_id)
    return _reglages_depuis_ligne(ligne)


async def enregistrer_reglages(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    genres_desactives: Iterable[str] | None = None,
    silence_actif: bool | None = None,
    silence_debut: time | None = None,
    silence_fin: time | None = None,
    fuseau: str | None = None,
    relais_email_invitation: bool | None = None,
    relais_push: bool | None = None,
) -> Reglages:
    """Écrit les réglages du compte (création de la ligne au premier passage) et les renvoie.

    Modification **partielle** : seuls les champs fournis changent — c'est ce qui permet à l'écran
    de basculer un seul genre sans renvoyer tout l'état, et donc sans écraser un réglage qu'un autre
    onglet vient de changer.

    Un genre inconnu est refusé par :class:`ValueError` : enregistrer « désactiver le genre
    *bidule* » laisserait croire à un réglage qui ne désactive rien.
    """
    if genres_desactives is not None:
        inconnus = sorted(set(genres_desactives) - NOTIF_GENRES)
        if inconnus:
            raise ValueError(f"Genres de notification inconnus : {', '.join(inconnus)}.")

    ligne = await db.get(NotificationReglages, user_id)
    if ligne is None:
        ligne = NotificationReglages(user_id=user_id)
        # Les défauts du modèle sont des `server_default` : ils ne sont connus qu'après un INSERT.
        # On pose donc explicitement l'état de départ depuis les défauts PURS (une seule source de
        # vérité pour « ce que reçoit un compte qui n'a rien réglé »).
        defauts = Reglages()
        ligne.genres_desactives = sorted(defauts.genres_desactives)
        ligne.silence_actif = defauts.silence_actif
        ligne.silence_debut = defauts.silence_debut
        ligne.silence_fin = defauts.silence_fin
        ligne.fuseau = defauts.fuseau
        ligne.relais_email_invitation = defauts.relais_email_invitation
        ligne.relais_push = defauts.relais_push
        db.add(ligne)

    if genres_desactives is not None:
        ligne.genres_desactives = sorted(set(genres_desactives))
    if silence_actif is not None:
        ligne.silence_actif = silence_actif
    if silence_debut is not None:
        ligne.silence_debut = silence_debut
    if silence_fin is not None:
        ligne.silence_fin = silence_fin
    if fuseau is not None:
        ligne.fuseau = fuseau
    if relais_email_invitation is not None:
        ligne.relais_email_invitation = relais_email_invitation
    if relais_push is not None:
        ligne.relais_push = relais_push

    await db.flush()
    return _reglages_depuis_ligne(ligne)


# --- Émission ---------------------------------------------------------------------------------


async def _compteurs(
    db: AsyncSession, *, user_id: uuid.UUID, genre: str, game_id: uuid.UUID | None
) -> Compteurs:
    """Compte ce que cette partie a déjà produit pour ce destinataire, et le doublon non lu.

    Sans partie (invitation reçue), aucun plafond de partie ne s'applique : on rend des compteurs à
    zéro, mais on relève tout de même le **doublon non lu** — deux invitations coup sur coup dont la
    première n'a pas été lue ne font qu'une notification.
    """
    doublon = (
        await db.execute(
            select(func.count())
            .select_from(GameNotification)
            .where(
                GameNotification.user_id == user_id,
                GameNotification.genre == genre,
                GameNotification.game_id == game_id,
                GameNotification.lue_at.is_(None),
            )
        )
    ).scalar_one()

    if game_id is None:
        return Compteurs(total_partie=0, par_genre={}, doublon_non_lu=doublon > 0)

    lignes = (
        await db.execute(
            select(GameNotification.genre, func.count())
            .where(
                GameNotification.user_id == user_id,
                GameNotification.game_id == game_id,
            )
            .group_by(GameNotification.genre)
        )
    ).all()
    par_genre = {g: n for g, n in lignes}
    return Compteurs(
        total_partie=sum(par_genre.values()), par_genre=par_genre, doublon_non_lu=doublon > 0
    )


async def _relayer(
    db: AsyncSession,
    decision: Decision,
    *,
    destinataire_id: uuid.UUID,
    genre: str,
    donnees: dict,
    email_sender: EmailSender | None,
) -> None:
    """Déclenche les relais hors application que la décision a autorisés, et seulement ceux-là."""
    if decision.relais_email:
        if email_sender is None:
            # L'appelant n'a pas fourni d'émetteur alors que le genre en a besoin : on le dit, on
            # n'envoie rien. La notification *dans l'application* est déjà écrite — c'est elle la
            # source de vérité, l'e-mail n'était qu'un rappel.
            logger.error(
                "relais e-mail autorisé pour « %s » mais aucun émetteur fourni : rien n'est "
                "envoyé (la notification dans l'application, elle, est enregistrée).",
                genre,
            )
        else:
            destinataire = await db.get(User, destinataire_id)
            if destinataire is None:
                logger.error(
                    "relais e-mail impossible : destinataire %s introuvable.", destinataire_id
                )
            else:
                await relais.relayer_par_email(
                    email_sender, destinataire=destinataire, genre=genre, donnees=donnees
                )

    if decision.relais_push:
        await relais.relayer_par_push(destinataire_id=destinataire_id, genre=genre)


async def notifier(
    db: AsyncSession,
    *,
    destinataire_id: uuid.UUID,
    genre: str,
    game_id: uuid.UUID | None = None,
    donnees: dict | None = None,
    instant: datetime | None = None,
    email_sender: EmailSender | None = None,
) -> GameNotification | None:
    """Émet une notification **si les règles l'autorisent** ; sinon ``None``, motif à l'appui.

    Ne commite pas : la notification est ``flush``ée dans la transaction de l'appelant, pour qu'elle
    partage le sort de ce qui l'a provoquée — on ne notifie pas « c'est ton tour » pour un coup qui
    a été annulé.

    ``donnees`` porte le contexte d'affichage (pseudo de l'adversaire, secondes restantes, raison de
    fin). Il ne doit **jamais** contenir de secret de partie (main, ordre de pioche) : une
    notification est un libellé, pas une vue — le serveur fait autorité, et une vue passe par
    ``GET /jeu/parties/{id}``.
    """
    instant = instant or datetime.now(UTC)
    donnees = donnees or {}
    reglages = await charger_reglages(db, destinataire_id)
    compteurs = await _compteurs(db, user_id=destinataire_id, genre=genre, game_id=game_id)
    decision = decider(genre, reglages=reglages, compteurs=compteurs, instant=instant)

    if not decision.enregistrer:
        logger.info(
            "notification « %s » non émise (destinataire %s, partie %s) : %s",
            genre,
            destinataire_id,
            game_id,
            decision.motif,
        )
        return None

    notification = GameNotification(
        user_id=destinataire_id,
        genre=genre,
        game_id=game_id,
        donnees=donnees,
        silencieuse=decision.silencieuse,
        created_at=instant,
    )
    db.add(notification)
    await db.flush()

    await _relayer(
        db,
        decision,
        destinataire_id=destinataire_id,
        genre=genre,
        donnees=donnees,
        email_sender=email_sender,
    )
    logger.info(
        "notification « %s » émise (destinataire %s, partie %s) : %s",
        genre,
        destinataire_id,
        game_id,
        decision.motif,
    )
    return notification


async def notifier_sans_casser(
    db: AsyncSession,
    *,
    destinataire_id: uuid.UUID,
    genre: str,
    game_id: uuid.UUID | None = None,
    donnees: dict | None = None,
    instant: datetime | None = None,
) -> GameNotification | None:
    """:func:`notifier`, mais une défaillance du canal ne fait jamais échouer le coup du joueur.

    Réservé aux points d'accroche **dans le chemin d'un coup** (moteur de jeu, appariement) : là, la
    notification est l'accessoire et le coup l'essentiel. Une exception est journalisée **avec sa
    pile** (``logger.exception``) et l'appelant continue.

    Ce n'est pas un ``except: pass`` : l'échec laisse une trace nominative et complète, et il n'y a
    aucun chemin où la perte d'une notification soit normale. Les appels *hors* chemin de coup
    (routes, invitations) passent par :func:`notifier` et laissent remonter l'erreur.
    """
    try:
        return await notifier(
            db,
            destinataire_id=destinataire_id,
            genre=genre,
            game_id=game_id,
            donnees=donnees,
            instant=instant,
        )
    except Exception:  # noqa: BLE001 — accessoire : un coup ne tombe pas pour une notification
        logger.exception(
            "notification « %s » perdue (destinataire %s, partie %s) : le coup, lui, est appliqué.",
            genre,
            destinataire_id,
            game_id,
        )
        return None


# --- Lecture ----------------------------------------------------------------------------------


async def lister(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    seulement_non_lues: bool = False,
    limite: int = LIMITE_LECTURE,
) -> list[GameNotification]:
    """Les notifications du compte, les plus récentes d'abord — **bornées à ce compte**."""
    requete = select(GameNotification).where(GameNotification.user_id == user_id)
    if seulement_non_lues:
        requete = requete.where(GameNotification.lue_at.is_(None))
    requete = requete.order_by(GameNotification.created_at.desc()).limit(limite)
    return list((await db.execute(requete)).scalars().all())


async def nb_non_lues(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Le compte des non lues — ce que le badge de la navigation affiche."""
    return (
        await db.execute(
            select(func.count())
            .select_from(GameNotification)
            .where(GameNotification.user_id == user_id, GameNotification.lue_at.is_(None))
        )
    ).scalar_one()


async def marquer_lue(
    db: AsyncSession,
    user_id: uuid.UUID,
    notification_id: uuid.UUID,
    *,
    instant: datetime | None = None,
) -> GameNotification:
    """Marque **une** notification lue. Celle d'autrui est introuvable (404), jamais interdite.

    Idempotent : une notification déjà lue garde sa date de lecture (on ne « relit » pas).
    """
    notification = (
        await db.execute(
            select(GameNotification).where(
                GameNotification.id == notification_id, GameNotification.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if notification is None:
        raise NotificationIntrouvable(f"Notification {notification_id} introuvable.")
    if notification.lue_at is None:
        notification.lue_at = instant or datetime.now(UTC)
        await db.flush()
    return notification


async def marquer_toutes_lues(
    db: AsyncSession, user_id: uuid.UUID, *, instant: datetime | None = None
) -> int:
    """Marque toutes les non lues du compte comme lues et renvoie leur nombre.

    Utile pour l'écran (« tout marquer comme lu ») **et** pour l'anti-doublon : un joueur qui vide
    sa liste redevient notifiable, dans la limite des plafonds — qui, eux, ne se vident pas.
    """
    resultat = await db.execute(
        update(GameNotification)
        .where(GameNotification.user_id == user_id, GameNotification.lue_at.is_(None))
        .values(lue_at=instant or datetime.now(UTC))
    )
    await db.flush()
    return resultat.rowcount or 0
