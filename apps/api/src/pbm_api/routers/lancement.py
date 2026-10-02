"""Routes du **lancement** (lot `j-lancement-partie`) : préparer, tirer, choisir, basculer.

Depuis un salon d'attente accepté (`j-invitations`), ces routes conduisent les deux joueurs jusqu'à
une partie en cours : choisir son deck et se déclarer prêt, voir le tirage du premier joueur,
en choisir l'issue quand on l'a gagné, et basculer en partie. Le lancement est **identifié par son
invitation** (un lancement par invitation) : un `GET` crée le lancement au premier accès et le
reprend à la bonne étape après un rechargement.

**Toutes** les routes sont gardées par `require_game_access` (D11) :
un compte sans droit d'accès au jeu reçoit **404** partout. Les écritures exigent le jeton CSRF. Le
routeur ne fait que traduire : il appelle `pbm_api.games.lancement` et convertit ses exceptions
nommées en statuts HTTP. La **graine** (secret d'aléatoire) n'apparaît jamais tant que la partie
n'est pas terminée — c'est le service qui la retient, le routeur ne la décide pas.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_csrf, require_game_access
from pbm_api.db import get_session
from pbm_api.games.entry import DeckInjouable, DeckIntrouvable
from pbm_api.games.lancement import (
    InvitationPasAcceptee,
    LancementIntrouvable,
    LancementMauvaisePhase,
    LancementVue,
    PasLeGagnantDuTirage,
    abandonner,
    choisir,
    composer_vue,
    obtenir_ou_creer,
    se_preparer,
)
from pbm_api.models import User

router = APIRouter(prefix="/lancements", tags=["lancements"])

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


class PreparerIn(BaseModel):
    """Se déclarer prêt : le deck choisi (optionnel — à défaut, le deck déjà annoncé est gardé)."""

    deck_id: uuid.UUID | None = None


class ChoisirIn(BaseModel):
    """Le choix du gagnant du tirage : commencer (vrai) ou laisser l'adversaire commencer (faux)."""

    commencer: bool


class CampOut(BaseModel):
    """Un camp du lancement : l'utilisateur, son pseudo, le deck choisi, l'état « prêt »."""

    user_id: uuid.UUID
    pseudo: str | None
    deck_id: uuid.UUID | None
    pret: bool


class LancementOut(BaseModel):
    """La vue d'un lancement — symétrique, **sans la graine** tant que la partie n'est pas terminée.

    ``engagement`` et ``tirage`` sont publics dès le tirage (ils le rendent vérifiable) ; ``graine``
    n'apparaît qu'une fois la partie terminée (commit-reveal), pour recalculer le pile ou face.
    """

    invitation_id: uuid.UUID
    launch_id: uuid.UUID
    statut: str
    inviter: CampOut
    invitee: CampOut
    engagement: str | None
    tirage: dict | None
    tirage_gagnant_user_id: uuid.UUID | None
    premier_joueur_user_id: uuid.UUID | None
    choix_commencer: bool | None
    choix_expire_at: str | None
    game_id: uuid.UUID | None
    graine: str | None

    @classmethod
    def de(cls, vue: LancementVue) -> LancementOut:
        """Construit la sortie HTTP depuis la vue du service."""

        def _camp(camp) -> CampOut:
            return CampOut(
                user_id=camp.user_id, pseudo=camp.pseudo, deck_id=camp.deck_id, pret=camp.pret
            )

        return cls(
            invitation_id=vue.invitation_id,
            launch_id=vue.launch_id,
            statut=vue.statut,
            inviter=_camp(vue.inviter),
            invitee=_camp(vue.invitee),
            engagement=vue.engagement,
            tirage=vue.tirage,
            tirage_gagnant_user_id=vue.tirage_gagnant_user_id,
            premier_joueur_user_id=vue.premier_joueur_user_id,
            choix_commencer=vue.choix_commencer,
            choix_expire_at=vue.choix_expire_at.isoformat() if vue.choix_expire_at else None,
            game_id=vue.game_id,
            graine=vue.graine,
        )


# --- Traduction des erreurs du service en statuts HTTP ---------------------------------------


def _traduire(exc: Exception) -> HTTPException:
    """Convertit une erreur nommée du service en `HTTPException` (jamais un silence)."""
    if isinstance(exc, (LancementIntrouvable, DeckIntrouvable)):
        return HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE)
    if isinstance(exc, DeckInjouable):
        return _erreur_deck(exc)
    if isinstance(exc, (InvitationPasAcceptee, LancementMauvaisePhase, PasLeGagnantDuTirage)):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    raise exc  # une erreur non prévue n'est jamais masquée


# --- Routes ----------------------------------------------------------------------------------


@router.get("/{invitation_id}", response_model=LancementOut)
async def consulter_lancement(
    invitation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
) -> LancementOut:
    """Le lancement d'une invitation acceptée (créé au premier accès), repris à la bonne étape.

    404 si l'invitation n'existe pas ou pas la vôtre ; 409 si elle n'est pas acceptée.
    C'est aussi ce `GET` qui applique le choix par défaut après le délai (reprise après F5).
    """
    try:
        launch, invitation = await obtenir_ou_creer(
            db, invitation_id=invitation_id, user_id=current_user.id
        )
    except (LancementIntrouvable, InvitationPasAcceptee) as exc:
        raise _traduire(exc) from exc
    return LancementOut.de(await composer_vue(db, launch=launch, invitation=invitation))


@router.post("/{invitation_id}/preparer", response_model=LancementOut)
async def preparer(
    invitation_id: uuid.UUID,
    body: PreparerIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> LancementOut:
    """Choisir son deck et se déclarer prêt ; le tirage part si les deux le sont.

    404 si l'invitation/le deck n'est pas le vôtre ; 409 si le lancement n'est plus en préparation ;
    422 si le deck est injouable (cartes nommées, D9 ou possession).
    """
    try:
        launch, invitation = await se_preparer(
            db, invitation_id=invitation_id, user_id=current_user.id, deck_id=body.deck_id
        )
    except (
        LancementIntrouvable,
        InvitationPasAcceptee,
        LancementMauvaisePhase,
        DeckIntrouvable,
        DeckInjouable,
    ) as exc:
        raise _traduire(exc) from exc
    return LancementOut.de(await composer_vue(db, launch=launch, invitation=invitation))


@router.post("/{invitation_id}/choisir", response_model=LancementOut)
async def choisir_premier(
    invitation_id: uuid.UUID,
    body: ChoisirIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> LancementOut:
    """Le gagnant du tirage choisit de commencer ou non : la partie est créée et on bascule.

    404 si l'invitation n'est pas la vôtre ; 409 si le lancement n'est pas en tirage ou si vous
    n'êtes pas le gagnant ; 422 si un deck est devenu injouable (lancement arrêté, sans partie
    fantôme, cartes nommées).
    """
    try:
        launch, invitation = await choisir(
            db, invitation_id=invitation_id, user_id=current_user.id, commencer=body.commencer
        )
    except (
        LancementIntrouvable,
        InvitationPasAcceptee,
        LancementMauvaisePhase,
        PasLeGagnantDuTirage,
        DeckIntrouvable,
        DeckInjouable,
    ) as exc:
        raise _traduire(exc) from exc
    return LancementOut.de(await composer_vue(db, launch=launch, invitation=invitation))


@router.post("/{invitation_id}/abandonner", response_model=LancementOut)
async def abandonner_lancement(
    invitation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> LancementOut:
    """Quitter le lancement avant la partie (déconnexion / renoncement) : figé, aucune partie créée.

    404 si l'invitation n'est pas la vôtre ; 409 si la partie est déjà lancée.
    """
    try:
        launch, invitation = await abandonner(
            db, invitation_id=invitation_id, user_id=current_user.id
        )
    except (LancementIntrouvable, InvitationPasAcceptee, LancementMauvaisePhase) as exc:
        raise _traduire(exc) from exc
    return LancementOut.de(await composer_vue(db, launch=launch, invitation=invitation))
