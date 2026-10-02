"""Routes des invitations à jouer (lot `j-invitations`) : inviter, répondre, salon d'attente.

Inviter un compte par pseudo ou fabriquer un lien à usage unique ; lister ce qu'on a reçu (la
notification *dans l'application*) ou émis ; accepter, refuser, annuler ; consulter le salon
d'attente à deux. **Toutes** les routes sont gardées par
:func:`~pbm_api.auth.dependencies.require_game_access` (D11) : un compte sans droit d'accès au jeu
reçoit **404** partout — le jeu n'existe pas pour lui, et surtout **suivre un lien ne crée aucun
accès** (il faut être déjà invité et connecté). Les écritures exigent le jeton CSRF, comme toute
mutation utilisateur.

Le routeur ne fait que traduire : il appelle `pbm_api.games.invitations` et convertit ses
exceptions nommées en statuts HTTP. Le jeton en clair d'un lien n'est renvoyé **qu'une fois**, à la
création, et n'apparaît jamais dans une URL de route (il voyage dans le corps de la requête
d'acceptation) ni dans un journal.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_csrf, require_game_access
from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.email import EmailSender, get_email_sender
from pbm_api.games import invitations as service
from pbm_api.games.entry import DeckInjouable, DeckIntrouvable
from pbm_api.games.invitations import (
    AutoInvitation,
    DestinataireIntrouvable,
    InvitationIntrouvable,
    InvitationNonEnAttente,
    Salon,
)
from pbm_api.models import User
from pbm_api.models.invitations import GameInvitation

router = APIRouter(prefix="/invitations", tags=["invitations"])

NOT_FOUND_MESSAGE = "Ressource introuvable."


def _erreur_deck(exc: DeckInjouable) -> HTTPException:
    """Traduit un deck non jouable en 422 **nommant les cartes** — jamais un refus muet (D9)."""
    return HTTPException(
        422,
        detail={
            "message": "Deck non jouable.",
            "refus": [{"carte": nom, "raison": raison} for nom, raison in exc.refus],
        },
    )


# --- Schémas d'entrée / sortie ---------------------------------------------------------------


class InviterPseudoIn(BaseModel):
    """Invitation par pseudo : le pseudo visé et, éventuellement, le deck qu'on compte jouer."""

    pseudo: str
    deck_id: uuid.UUID | None = None


class InviterLienIn(BaseModel):
    """Invitation par lien : seul le deck annoncé est optionnel ; le reste est fabriqué."""

    deck_id: uuid.UUID | None = None


class RepondreIn(BaseModel):
    """Réponse à une invitation : le deck que l'on annonce à son tour (optionnel)."""

    deck_id: uuid.UUID | None = None


class AccepterLienIn(BaseModel):
    """Acceptation d'un lien : le jeton (dans le corps, jamais dans l'URL) et le deck annoncé."""

    jeton: str
    deck_id: uuid.UUID | None = None


class InvitationOut(BaseModel):
    """Une invitation, **sans jamais** son jeton en clair ni son empreinte.

    ``invitee_user_id`` est nul pour un lien pas encore accepté. Les champs de deck portent l'id
    annoncé de chaque camp (nul si rien n'est annoncé ou si le deck a été supprimé).
    """

    id: uuid.UUID
    mode: str
    statut: str
    inviter_user_id: uuid.UUID
    invitee_user_id: uuid.UUID | None
    inviter_deck_id: uuid.UUID | None
    invitee_deck_id: uuid.UUID | None

    @classmethod
    def de(cls, invitation: GameInvitation) -> InvitationOut:
        """Construit la sortie depuis le modèle, sans aucun secret (ni jeton, ni empreinte)."""
        return cls(
            id=invitation.id,
            mode=invitation.mode,
            statut=invitation.statut,
            inviter_user_id=invitation.inviter_user_id,
            invitee_user_id=invitation.invitee_user_id,
            inviter_deck_id=invitation.inviter_deck_id,
            invitee_deck_id=invitation.invitee_deck_id,
        )


class LienCreeOut(InvitationOut):
    """Invitation par lien à la création : le jeton en clair et l'URL partageable, une seule fois.

    C'est le seul endroit où le jeton sort du serveur — il n'est stocké que haché. Le client le
    partage ; il ne le reverra jamais via l'API.
    """

    jeton: str
    url: str


class DeckAnnonceOut(BaseModel):
    """Le deck annoncé d'un camp dans le salon : son id et son nom affichable."""

    deck_id: uuid.UUID
    nom: str


class JoueurSalonOut(BaseModel):
    """Un camp du salon : l'utilisateur, son pseudo affichable, le deck annoncé (ou nul)."""

    user_id: uuid.UUID
    pseudo: str | None
    deck: DeckAnnonceOut | None


class SalonOut(BaseModel):
    """Le salon d'attente à deux — vue symétrique, identique pour les deux joueurs."""

    invitation_id: uuid.UUID
    statut: str
    inviter: JoueurSalonOut
    invitee: JoueurSalonOut | None

    @classmethod
    def de(cls, salon: Salon) -> SalonOut:
        """Construit la sortie HTTP depuis la vue de salon du service."""

        def _joueur(joueur) -> JoueurSalonOut | None:
            if joueur is None:
                return None
            deck = (
                DeckAnnonceOut(deck_id=joueur.deck.deck_id, nom=joueur.deck.nom)
                if joueur.deck is not None
                else None
            )
            return JoueurSalonOut(user_id=joueur.user_id, pseudo=joueur.pseudo, deck=deck)

        return cls(
            invitation_id=salon.invitation_id,
            statut=salon.statut,
            inviter=_joueur(salon.inviter),
            invitee=_joueur(salon.invitee),
        )


# --- Routes : création -----------------------------------------------------------------------


@router.post("/pseudo", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
async def inviter_par_pseudo(
    body: InviterPseudoIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> InvitationOut:
    """Invite un compte invité par son pseudo (404 si aucun compte invité ne le porte).

    422 si on se vise soi-même ou si le deck annoncé n'est pas jouable (cartes nommées, D9).
    """
    try:
        invitation = await service.inviter_par_pseudo(
            db, email_sender, inviter_id=current_user.id, pseudo=body.pseudo, deck_id=body.deck_id
        )
    except DestinataireIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except AutoInvitation as exc:
        raise HTTPException(422, str(exc)) from exc
    except DeckIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except DeckInjouable as exc:
        raise _erreur_deck(exc) from exc
    return InvitationOut.de(invitation)


@router.post("/lien", response_model=LienCreeOut, status_code=status.HTTP_201_CREATED)
async def inviter_par_lien(
    body: InviterLienIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> LienCreeOut:
    """Fabrique un lien d'invitation à usage unique et renvoie son jeton **une seule fois**.

    422 si le deck annoncé n'est pas jouable (cartes nommées, D9).
    """
    try:
        invitation, jeton = await service.inviter_par_lien(
            db, inviter_id=current_user.id, deck_id=body.deck_id
        )
    except DeckIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except DeckInjouable as exc:
        raise _erreur_deck(exc) from exc
    base = InvitationOut.de(invitation)
    url = f"{settings.app_public_url.rstrip('/')}/jeu/invitation#{jeton}"
    return LienCreeOut(**base.model_dump(), jeton=jeton, url=url)


# --- Routes : notification (reçues) et suivi (envoyées) --------------------------------------


@router.get("/recues", response_model=list[InvitationOut])
async def invitations_recues(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
) -> list[InvitationOut]:
    """Les invitations en attente qui vous sont destinées — la notification dans l'application."""
    recues = await service.recues(db, user_id=current_user.id)
    return [InvitationOut.de(invitation) for invitation in recues]


@router.get("/envoyees", response_model=list[InvitationOut])
async def invitations_envoyees(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
) -> list[InvitationOut]:
    """Les invitations que vous avez émises (tous statuts), pour les suivre et les annuler."""
    envoyees = await service.envoyees(db, user_id=current_user.id)
    return [InvitationOut.de(invitation) for invitation in envoyees]


# --- Routes : transitions --------------------------------------------------------------------


# NB : la route statique `/lien/accepter` est déclarée AVANT la route dynamique
# `/{invitation_id}/accepter` — sinon FastAPI capte « lien » comme un `invitation_id` et
# répond 422 (UUID invalide) au lieu de rejoindre par lien. L'ordre de déclaration fait foi.
@router.post("/lien/accepter", response_model=SalonOut)
async def accepter_par_lien(
    body: AccepterLienIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> SalonOut:
    """Rejoint une invitation par lien via son jeton : ouvre le salon d'attente.

    404 si le jeton ne correspond à rien ; 409 si le lien a déjà servi ou a expiré (usage unique) ;
    422 si on rejoint son propre lien ou si le deck annoncé n'est pas jouable. **Ne crée aucun
    accès** : il faut déjà être un compte invité connecté (garde `require_game_access`).
    """
    try:
        invitation = await service.accepter_par_lien(
            db, jeton=body.jeton, invitee_id=current_user.id, deck_id=body.deck_id
        )
    except InvitationIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except InvitationNonEnAttente as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except AutoInvitation as exc:
        raise HTTPException(422, str(exc)) from exc
    except DeckIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except DeckInjouable as exc:
        raise _erreur_deck(exc) from exc
    return SalonOut.de(
        await service.salon(db, invitation_id=invitation.id, user_id=current_user.id)
    )


@router.post("/{invitation_id}/accepter", response_model=SalonOut)
async def accepter(
    invitation_id: uuid.UUID,
    body: RepondreIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> SalonOut:
    """Accepte une invitation par pseudo qui vous est destinée : ouvre le salon d'attente.

    404 si elle n'existe pas ou ne vous est pas destinée ; 409 si elle n'est plus en attente ; 422
    si le deck annoncé n'est pas jouable.
    """
    try:
        invitation = await service.accepter(
            db, invitation_id=invitation_id, invitee_id=current_user.id, deck_id=body.deck_id
        )
    except InvitationIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except InvitationNonEnAttente as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except DeckIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except DeckInjouable as exc:
        raise _erreur_deck(exc) from exc
    return SalonOut.de(
        await service.salon(db, invitation_id=invitation.id, user_id=current_user.id)
    )


@router.post("/{invitation_id}/refuser", response_model=InvitationOut)
async def refuser(
    invitation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> InvitationOut:
    """Refuse une invitation par pseudo qui vous est destinée (404 si ce n'est pas la vôtre)."""
    try:
        invitation = await service.refuser(
            db, invitation_id=invitation_id, invitee_id=current_user.id
        )
    except InvitationIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except InvitationNonEnAttente as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return InvitationOut.de(invitation)


@router.post("/{invitation_id}/annuler", response_model=InvitationOut)
async def annuler(
    invitation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> InvitationOut:
    """Annule une invitation que vous avez émise (404 si vous n'en êtes pas l'émetteur)."""
    try:
        invitation = await service.annuler(
            db, invitation_id=invitation_id, inviter_id=current_user.id
        )
    except InvitationIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except InvitationNonEnAttente as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return InvitationOut.de(invitation)


# --- Route : salon d'attente -----------------------------------------------------------------


@router.get("/{invitation_id}/salon", response_model=SalonOut)
async def consulter_salon(
    invitation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
) -> SalonOut:
    """Le salon d'attente à deux : vue symétrique, identique pour l'émetteur et l'invité.

    404 si l'invitation n'existe pas ou si vous n'y avez aucun rôle (pas de fuite).
    """
    try:
        salon = await service.salon(db, invitation_id=invitation_id, user_id=current_user.id)
    except InvitationIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    return SalonOut.de(salon)
