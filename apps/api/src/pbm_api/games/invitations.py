"""Invitations à jouer : par pseudo ou par lien, et le salon d'attente à deux (lot `j-invitations`).

« Je veux jouer avec *lui* » : on invite quelqu'un de précis plutôt que de chercher un inconnu dans
la file. Ce module tient le cycle de vie d'une invitation (émise → acceptée / refusée / annulée /
expirée) et la **vue de salon** que les deux joueurs partagent une fois l'invitation acceptée. Il
vit dans `apps/api` car il lit la base ; le moteur `pbm_game` reste pur (aucune règle de jeu ici).

Trois exigences du lot guident le code :

* **Un lien ne sert qu'une fois et expire.** Le jeton n'est stocké que haché (SHA-256,
  `pbm_api.security.tokens`) ; l'usage unique est structurel — accepter fait quitter le statut
  « envoyée », et seul ce statut autorise une acceptation, donc un second usage est refusé
  (:class:`InvitationNonEnAttente`). L'expiration est une transition paresseuse à la lecture
  (:func:`_expirer_si_echue`), jamais un silence.
* **Une invitation n'ouvre aucun droit au-delà de la partie (D11).** Toutes les routes sont déjà
  gardées par ``require_game_access`` (le routeur) : suivre un lien suppose un compte invité déjà
  connecté — le lien **rejoint** une invitation, il ne crée jamais d'accès ni de compte. Ce module
  ne touche **jamais** à ``User.game_access`` ; c'est vérifié par un test dédié.
* **Les deux joueurs voient le même salon et le même deck annoncé.** :func:`salon` reconstruit une
  vue **symétrique** depuis l'invitation : elle est identique quel que soit le participant qui la
  demande (contrairement à une vue de partie, un salon d'attente n'a rien de caché).

La notification *dans l'application* est la liste des invitations reçues (:func:`recues`) ; un
**relais e-mail** part en plus pour une invitation par pseudo (:func:`inviter_par_pseudo`). La
notification PWA viendra avec le lot `j-notifications-jeu` : on nomme ce relais futur, on ne
l'approxime pas.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.config import settings
from pbm_api.email import EmailSender
from pbm_api.games.entry import verifier_deck  # lève DeckIntrouvable / DeckInjouable (D9)
from pbm_api.games.errors import GameError
from pbm_api.models import Deck, User
from pbm_api.models.invitations import (
    INVITATION_MODE_LIEN,
    INVITATION_MODE_PSEUDO,
    INVITATION_STATUT_ACCEPTEE,
    INVITATION_STATUT_ANNULEE,
    INVITATION_STATUT_ENVOYEE,
    INVITATION_STATUT_EXPIREE,
    INVITATION_STATUT_REFUSEE,
    GameInvitation,
)
from pbm_api.security.tokens import generate_opaque_token, hash_token

logger = logging.getLogger(__name__)

#: Durée de validité par défaut d'une invitation (pseudo comme lien). Défaut pilote : une semaine
#: laisse le temps de répondre à une invitation asynchrone, sans qu'un lien traîne indéfiniment.
#: Modifiable par appel (les tests passent une échéance pour vérifier l'expiration sans attendre).
TTL_INVITATION = timedelta(days=7)


def _maintenant(fourni: datetime | None) -> datetime:
    """Instant courant (UTC, conscient du fuseau), ou celui fourni par un test (déterminisme)."""
    return fourni if fourni is not None else datetime.now(UTC)


# --- Erreurs du lot (chacune dit pourquoi ; la couche HTTP les traduit en statuts) -----------


class DestinataireIntrouvable(GameError):
    """Aucun **compte invité** ne porte ce pseudo (→ 404).

    On ne distingue pas « pseudo inconnu » de « pseudo connu mais sans accès au jeu » : révéler
    qu'un pseudo donné fait partie des comptes invités serait une fuite sur un jeu délibérément
    privé (D11). La réponse est la même dans les deux cas.
    """


class AutoInvitation(GameError):
    """On ne s'invite pas soi-même (→ 422). Un salon à deux a besoin de deux joueurs distincts."""


class InvitationIntrouvable(GameError):
    """L'invitation n'existe pas, ou l'appelant n'y a aucun rôle (→ 404, jamais 403).

    Même règle que les decks et les parties : on ne révèle pas l'existence d'un objet qui n'est pas
    le vôtre. Un lien dont l'empreinte ne correspond à rien tombe aussi ici.
    """


class InvitationNonEnAttente(GameError):
    """L'invitation n'est plus « envoyée » : déjà acceptée, refusée, annulée ou expirée (→ 409).

    C'est le refus d'un lien réutilisé : une fois accepté, il a quitté le statut « envoyée »,
    donc un second usage ne peut plus aboutir. Le message dit l'état réel, jamais un échec muet.
    """

    def __init__(self, statut: str) -> None:
        self.statut = statut
        super().__init__(
            f"Invitation non disponible : son statut est « {statut} », "
            "seule une invitation « envoyee » peut être acceptée, refusée ou annulée."
        )


# --- Vue de salon (symétrique : identique pour les deux joueurs) -----------------------------


@dataclass
class DeckAnnonce:
    """Le deck qu'un camp a annoncé dans le salon : son identifiant et son nom affichable."""

    deck_id: uuid.UUID
    nom: str


@dataclass
class JoueurSalon:
    """Un camp du salon : l'utilisateur, son pseudo affichable et le deck annoncé (ou None)."""

    user_id: uuid.UUID
    pseudo: str | None
    deck: DeckAnnonce | None


@dataclass
class Salon:
    """Le salon d'attente à deux, reconstruit depuis l'invitation — **vue symétrique**.

    ``invitee`` est ``None`` tant qu'un lien n'a pas été accepté (personne n'a encore rejoint). Une
    fois l'invitation acceptée, les deux camps sont présents et la vue est strictement identique
    pour l'émetteur et l'invité : c'est le critère « les deux joueurs voient le même salon ».
    """

    invitation_id: uuid.UUID
    statut: str
    inviter: JoueurSalon
    invitee: JoueurSalon | None


async def _deck_annonce(db: AsyncSession, deck_id: uuid.UUID | None) -> DeckAnnonce | None:
    """Charge le nom d'un deck annoncé, ou ``None`` si rien n'est annoncé (ou le deck supprimé).

    Un ``deck_id`` qui ne pointe plus sur un deck (supprimé après l'annonce, FK ``SET NULL``) est
    traité comme « pas de deck » : on n'invente pas de nom, et on ne lève pas — le salon reste
    lisible.
    """
    if deck_id is None:
        return None
    deck = await db.get(Deck, deck_id)
    if deck is None:
        return None
    return DeckAnnonce(deck_id=deck.id, nom=deck.name)


# --- Expiration paresseuse -------------------------------------------------------------------


def _expirer_si_echue(invitation: GameInvitation, maintenant: datetime) -> None:
    """Fait passer une invitation échue de « envoyée » à « expirée », en place.

    Transition **paresseuse** : déclenchée à la lecture ou avant toute action, elle évite d'avoir
    besoin d'un balayage de fond pour que l'expiration soit vraie. Ce n'est pas un repli
    silencieux : l'expiration est un statut observable (``resolved_at`` posé), pas un objet ignoré.
    """
    if invitation.statut == INVITATION_STATUT_ENVOYEE and invitation.expires_at <= maintenant:
        invitation.statut = INVITATION_STATUT_EXPIREE
        invitation.resolved_at = maintenant


# --- Création --------------------------------------------------------------------------------


async def inviter_par_pseudo(
    db: AsyncSession,
    email_sender: EmailSender,
    *,
    inviter_id: uuid.UUID,
    pseudo: str,
    deck_id: uuid.UUID | None = None,
    maintenant: datetime | None = None,
) -> GameInvitation:
    """Invite un compte invité par son pseudo, et lui envoie un rappel par e-mail.

    Lève :class:`DestinataireIntrouvable` (→ 404) si aucun compte **invité** ne porte ce pseudo (pas
    de fuite), :class:`AutoInvitation` (→ 422) si on se vise soi-même, et les erreurs de deck de
    :func:`verifier_deck` (→ 404/422, cartes nommées, D9) si un deck annoncé n'est pas jouable.
    La notification *dans l'application* reste la liste des reçues ; l'e-mail est un rappel.
    """
    maintenant = _maintenant(maintenant)
    cible = (
        await db.execute(select(User).where(func.lower(User.pseudo) == pseudo.strip().lower()))
    ).scalar_one_or_none()
    if cible is None or not cible.game_access:
        raise DestinataireIntrouvable(
            f"Aucun joueur invité ne porte le pseudo « {pseudo} »."
        )
    if cible.id == inviter_id:
        raise AutoInvitation("On ne peut pas s'inviter soi-même à jouer.")
    if deck_id is not None:
        await verifier_deck(db, inviter_id, deck_id)

    invitation = GameInvitation(
        mode=INVITATION_MODE_PSEUDO,
        statut=INVITATION_STATUT_ENVOYEE,
        inviter_user_id=inviter_id,
        invitee_user_id=cible.id,
        inviter_deck_id=deck_id,
        expires_at=maintenant + TTL_INVITATION,
    )
    db.add(invitation)
    await db.flush()

    inviteur = await db.get(User, inviter_id)
    await _notifier_par_email(email_sender, destinataire=cible, inviteur=inviteur)
    return invitation


async def inviter_par_lien(
    db: AsyncSession,
    *,
    inviter_id: uuid.UUID,
    deck_id: uuid.UUID | None = None,
    maintenant: datetime | None = None,
) -> tuple[GameInvitation, str]:
    """Fabrique une invitation par lien à usage unique, et renvoie ``(invitation, jeton_en_clair)``.

    Le jeton en clair n'est renvoyé **qu'ici**, une seule fois : seule son empreinte est stockée. Un
    deck annoncé non jouable est refusé en nommant les cartes (D9, via :func:`verifier_deck`).
    L'appelant (routeur) construit le lien partageable à partir du jeton et ne le journalise jamais.
    """
    maintenant = _maintenant(maintenant)
    if deck_id is not None:
        await verifier_deck(db, inviter_id, deck_id)

    jeton = generate_opaque_token()
    invitation = GameInvitation(
        mode=INVITATION_MODE_LIEN,
        statut=INVITATION_STATUT_ENVOYEE,
        inviter_user_id=inviter_id,
        inviter_deck_id=deck_id,
        token_hash=hash_token(jeton),
        expires_at=maintenant + TTL_INVITATION,
    )
    db.add(invitation)
    await db.flush()
    return invitation, jeton


# --- Transitions -----------------------------------------------------------------------------


async def _charger_en_attente(
    db: AsyncSession, invitation: GameInvitation | None, maintenant: datetime
) -> GameInvitation:
    """Applique l'expiration paresseuse et exige le statut « envoyée », sinon lève.

    Centralise la garde commune à l'acceptation, au refus et à l'annulation : une invitation échue
    devient « expirée » (persistée), et toute invitation déjà résolue lève
    :class:`InvitationNonEnAttente` (→ 409). ``invitation`` ``None`` (introuvable) lève
    :class:`InvitationIntrouvable` — c'est l'appelant qui a vérifié l'appartenance avant d'appeler.
    """
    if invitation is None:
        raise InvitationIntrouvable("Invitation introuvable.")
    _expirer_si_echue(invitation, maintenant)
    await db.flush()
    if invitation.statut != INVITATION_STATUT_ENVOYEE:
        raise InvitationNonEnAttente(invitation.statut)
    return invitation


async def accepter(
    db: AsyncSession,
    *,
    invitation_id: uuid.UUID,
    invitee_id: uuid.UUID,
    deck_id: uuid.UUID | None = None,
    maintenant: datetime | None = None,
) -> GameInvitation:
    """Accepte une invitation **par pseudo** qui vous est destinée : le salon d'attente s'ouvre.

    404 si l'invitation n'existe pas, n'est pas une invitation par pseudo, ou ne vous est pas
    destinée (pas de fuite). 409 si elle n'est plus en attente (déjà résolue ou expirée). Un deck
    annoncé non jouable est refusé en nommant les cartes (D9). On annonce le deck de l'invité et on
    passe en « acceptée ».
    """
    maintenant = _maintenant(maintenant)
    invitation = await db.get(GameInvitation, invitation_id)
    if (
        invitation is None
        or invitation.mode != INVITATION_MODE_PSEUDO
        or invitation.invitee_user_id != invitee_id
    ):
        raise InvitationIntrouvable("Invitation introuvable.")
    await _charger_en_attente(db, invitation, maintenant)
    if deck_id is not None:
        await verifier_deck(db, invitee_id, deck_id)

    invitation.invitee_deck_id = deck_id
    invitation.statut = INVITATION_STATUT_ACCEPTEE
    invitation.resolved_at = maintenant
    await db.flush()
    return invitation


async def accepter_par_lien(
    db: AsyncSession,
    *,
    jeton: str,
    invitee_id: uuid.UUID,
    deck_id: uuid.UUID | None = None,
    maintenant: datetime | None = None,
) -> GameInvitation:
    """Rejoint une invitation **par lien** à l'aide de son jeton : le salon d'attente s'ouvre.

    Le lien ne confère aucun droit (D11) : cette fonction suppose un compte invité déjà connecté
    (garde ``require_game_access`` côté routeur) et ne touche **jamais** à ``game_access``. 404 si
    le jeton ne correspond à aucun lien ; 409 si le lien a déjà servi ou a expiré (usage unique) ;
    422 si on tente de rejoindre son propre lien ou si le deck annoncé n'est pas jouable. On
    enregistre qui a rejoint et quel deck il annonce.
    """
    maintenant = _maintenant(maintenant)
    invitation = (
        await db.execute(
            select(GameInvitation).where(GameInvitation.token_hash == hash_token(jeton))
        )
    ).scalar_one_or_none()
    if invitation is None or invitation.mode != INVITATION_MODE_LIEN:
        raise InvitationIntrouvable("Lien d'invitation invalide.")
    await _charger_en_attente(db, invitation, maintenant)
    if invitation.inviter_user_id == invitee_id:
        raise AutoInvitation("On ne peut pas rejoindre sa propre invitation.")
    if deck_id is not None:
        await verifier_deck(db, invitee_id, deck_id)

    invitation.invitee_user_id = invitee_id
    invitation.invitee_deck_id = deck_id
    invitation.statut = INVITATION_STATUT_ACCEPTEE
    invitation.resolved_at = maintenant
    await db.flush()
    return invitation


async def refuser(
    db: AsyncSession,
    *,
    invitation_id: uuid.UUID,
    invitee_id: uuid.UUID,
    maintenant: datetime | None = None,
) -> GameInvitation:
    """Refuse une invitation par pseudo qui vous est destinée (404 si ce n'est pas la vôtre)."""
    maintenant = _maintenant(maintenant)
    invitation = await db.get(GameInvitation, invitation_id)
    if invitation is None or invitation.invitee_user_id != invitee_id:
        raise InvitationIntrouvable("Invitation introuvable.")
    await _charger_en_attente(db, invitation, maintenant)
    invitation.statut = INVITATION_STATUT_REFUSEE
    invitation.resolved_at = maintenant
    await db.flush()
    return invitation


async def annuler(
    db: AsyncSession,
    *,
    invitation_id: uuid.UUID,
    inviter_id: uuid.UUID,
    maintenant: datetime | None = None,
) -> GameInvitation:
    """Annule une invitation que **vous** avez émise (404 si vous n'en êtes pas l'émetteur)."""
    maintenant = _maintenant(maintenant)
    invitation = await db.get(GameInvitation, invitation_id)
    if invitation is None or invitation.inviter_user_id != inviter_id:
        raise InvitationIntrouvable("Invitation introuvable.")
    await _charger_en_attente(db, invitation, maintenant)
    invitation.statut = INVITATION_STATUT_ANNULEE
    invitation.resolved_at = maintenant
    await db.flush()
    return invitation


# --- Lectures (notification dans l'application + salon) --------------------------------------


async def recues(
    db: AsyncSession, *, user_id: uuid.UUID, maintenant: datetime | None = None
) -> list[GameInvitation]:
    """Les invitations **en attente** qui vous sont destinées — la notification dans l'application.

    Les invitations échues sont expirées au passage (transition paresseuse) et exclues : on ne
    propose jamais d'accepter une invitation morte. Triées de la plus récente à la plus ancienne.
    """
    maintenant = _maintenant(maintenant)
    lignes = (
        (
            await db.execute(
                select(GameInvitation)
                .where(
                    GameInvitation.invitee_user_id == user_id,
                    GameInvitation.statut == INVITATION_STATUT_ENVOYEE,
                )
                .order_by(GameInvitation.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    vivantes: list[GameInvitation] = []
    for invitation in lignes:
        _expirer_si_echue(invitation, maintenant)
        if invitation.statut == INVITATION_STATUT_ENVOYEE:
            vivantes.append(invitation)
    await db.flush()
    return vivantes


async def envoyees(
    db: AsyncSession, *, user_id: uuid.UUID, maintenant: datetime | None = None
) -> list[GameInvitation]:
    """Les invitations que **vous** avez émises (tous statuts), pour les suivre et les annuler.

    L'expiration paresseuse est appliquée au passage, pour que l'émetteur voie l'état réel plutôt
    qu'un « envoyée » périmé.
    """
    maintenant = _maintenant(maintenant)
    lignes = (
        (
            await db.execute(
                select(GameInvitation)
                .where(GameInvitation.inviter_user_id == user_id)
                .order_by(GameInvitation.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    for invitation in lignes:
        _expirer_si_echue(invitation, maintenant)
    await db.flush()
    return list(lignes)


async def salon(
    db: AsyncSession,
    *,
    invitation_id: uuid.UUID,
    user_id: uuid.UUID,
    maintenant: datetime | None = None,
) -> Salon:
    """Le salon d'attente à deux d'une invitation — vue **symétrique**, pour un participant.

    404 si l'invitation n'existe pas ou si l'appelant n'y a aucun rôle (ni émetteur, ni invité) :
    pas de fuite. La vue est identique pour l'émetteur et l'invité — c'est le critère « les deux
    joueurs voient le même salon et le même deck annoncé ».
    """
    maintenant = _maintenant(maintenant)
    invitation = await db.get(GameInvitation, invitation_id)
    if invitation is None:
        raise InvitationIntrouvable("Invitation introuvable.")
    _expirer_si_echue(invitation, maintenant)
    await db.flush()
    if user_id not in {invitation.inviter_user_id, invitation.invitee_user_id}:
        raise InvitationIntrouvable("Invitation introuvable.")

    inviteur = await db.get(User, invitation.inviter_user_id)
    inviter_joueur = JoueurSalon(
        user_id=invitation.inviter_user_id,
        pseudo=inviteur.pseudo if inviteur else None,
        deck=await _deck_annonce(db, invitation.inviter_deck_id),
    )
    invite_joueur: JoueurSalon | None = None
    if invitation.invitee_user_id is not None:
        invite = await db.get(User, invitation.invitee_user_id)
        invite_joueur = JoueurSalon(
            user_id=invitation.invitee_user_id,
            pseudo=invite.pseudo if invite else None,
            deck=await _deck_annonce(db, invitation.invitee_deck_id),
        )
    return Salon(
        invitation_id=invitation.id,
        statut=invitation.statut,
        inviter=inviter_joueur,
        invitee=invite_joueur,
    )


# --- Relais de notification ------------------------------------------------------------------


async def _notifier_par_email(
    email_sender: EmailSender, *, destinataire: User, inviteur: User | None
) -> None:
    """Envoie le rappel d'invitation reçue par e-mail — relais de la notification in-app.

    Source de vérité de la notification : la liste :func:`recues`, dans l'application. L'e-mail est
    un rappel ; s'il est désactivé (``SMTP_HOST`` vide), l'émetteur journalise proprement et n'émet
    rien (``pbm_api.email.DisabledEmailSender``) — ce n'est pas un repli silencieux mais un choix de
    configuration tracé. La notification PWA viendra avec le lot `j-notifications-jeu`.
    """
    nom = (inviteur.pseudo if inviteur and inviteur.pseudo else None) or "Un joueur"
    lien = f"{settings.app_public_url.rstrip('/')}/jeu"
    await email_sender.send(
        to=destinataire.email,
        subject="Invitation à jouer sur PokeBoy",
        body=(
            f"{nom} vous invite à jouer une partie sur PokeBoy.\n\n"
            f"Retrouvez l'invitation dans votre espace jeu : {lien}\n"
        ),
    )
