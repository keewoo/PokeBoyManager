"""Routes des **notifications du jeu** (`/jeu/notifications`) — lot `j-notifications-jeu`.

Lire ses notifications, les marquer lues, et régler ce qu'on accepte de recevoir. Comme toute route
du jeu, elles sont gardées par :func:`~pbm_api.auth.dependencies.require_game_access` (D11) : un
compte sans droit d'accès au jeu reçoit **404** partout — le jeu n'existe pas pour lui, ses
notifications non plus.

**Tout est borné au compte de la session**, sans exception et sans paramètre d'utilisateur : il n'y
a aucune route qui prenne un ``user_id``. La notification d'autrui est *introuvable* (404), jamais
« interdite » (403) : un 403 confirmerait son existence.

Le routeur ne décide rien. Il traduit :mod:`pbm_api.notifications.service` en HTTP, et les règles
d'émission (plafonds, silence nocturne) vivent dans :mod:`pbm_api.notifications.regles`. Une
notification ne s'émet **jamais** par HTTP : elle naît d'un événement du jeu (invitation,
appariement, coup, reconnexion), jamais d'une demande de client — sinon n'importe qui pourrait se
fabriquer une sonnerie, ou en fabriquer une à l'autre.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Annotated
from zoneinfo import ZoneInfo, available_timezones

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_csrf, require_game_access
from pbm_api.db import get_session
from pbm_api.models import User
from pbm_api.models.notifications import NOTIF_GENRES, GameNotification
from pbm_api.notifications import service
from pbm_api.notifications.regles import PLAFOND_PAR_GENRE, PLAFOND_PAR_PARTIE, Reglages

router = APIRouter(prefix="/jeu/notifications", tags=["notifications"])

NOT_FOUND_MESSAGE = "Ressource introuvable."


class NotificationOut(BaseModel):
    """Une notification telle qu'elle est servie à l'écran.

    ``donnees`` est le contexte d'affichage (pseudo de l'adversaire, secondes restantes, raison de
    fin) : l'écran fabrique la phrase, le serveur ne stocke pas de phrase — elle changerait de
    formulation sans migration. ``silencieuse`` dit « arrivée pendant le silence nocturne » :
    l'interface la montre dans la liste sans la sonner ni l'animer.
    """

    id: uuid.UUID
    genre: str
    game_id: uuid.UUID | None
    donnees: dict
    silencieuse: bool
    created_at: datetime
    lue_at: datetime | None

    @classmethod
    def de(cls, notification: GameNotification) -> NotificationOut:
        """Construit la sortie depuis le modèle — rien d'autre que ce que l'écran affiche."""
        return cls(
            id=notification.id,
            genre=notification.genre,
            game_id=notification.game_id,
            donnees=notification.donnees or {},
            silencieuse=notification.silencieuse,
            created_at=notification.created_at,
            lue_at=notification.lue_at,
        )


class ListeOut(BaseModel):
    """La liste et le compte des non lues — le second alimente le badge de la navigation."""

    notifications: list[NotificationOut]
    nb_non_lues: int


class ReglagesOut(BaseModel):
    """Les réglages du compte, plus ce qui est **imposé** par le produit (les plafonds).

    Les plafonds sont publiés avec les réglages pour que l'écran puisse dire la vérité : ils ne se
    règlent pas (ce sont des garde-fous contre le harcèlement, pas une préférence), mais un joueur
    qui se demande pourquoi il n'a reçu que quatre « c'est ton tour » mérite de le lire.
    ``genres_connus`` donne le vocabulaire complet, pour que l'écran liste les interrupteurs sans
    coder la liste en dur.
    """

    genres_connus: list[str]
    genres_desactives: list[str]
    silence_actif: bool
    silence_debut: time
    silence_fin: time
    fuseau: str
    relais_email_invitation: bool
    relais_push: bool
    plafond_par_partie: int
    plafond_par_genre: dict[str, int]

    @classmethod
    def de(cls, reglages: Reglages) -> ReglagesOut:
        """Construit la sortie depuis la vue pure des réglages, plafonds du produit compris."""
        return cls(
            genres_connus=sorted(NOTIF_GENRES),
            genres_desactives=sorted(reglages.genres_desactives),
            silence_actif=reglages.silence_actif,
            silence_debut=reglages.silence_debut,
            silence_fin=reglages.silence_fin,
            fuseau=reglages.fuseau,
            relais_email_invitation=reglages.relais_email_invitation,
            relais_push=reglages.relais_push,
            plafond_par_partie=PLAFOND_PAR_PARTIE,
            plafond_par_genre=dict(PLAFOND_PAR_GENRE),
        )


class ReglagesIn(BaseModel):
    """Modification **partielle** des réglages : seuls les champs fournis changent.

    C'est ce qui permet à l'écran de basculer un seul interrupteur sans renvoyer tout l'état — donc
    sans écraser un réglage changé entre-temps dans un autre onglet.
    """

    genres_desactives: list[str] | None = Field(
        default=None, description="Genres que le joueur ne veut plus recevoir."
    )
    silence_actif: bool | None = None
    silence_debut: time | None = None
    silence_fin: time | None = None
    fuseau: str | None = None
    relais_email_invitation: bool | None = None
    relais_push: bool | None = None

    @field_validator("genres_desactives")
    @classmethod
    def _genres_connus(cls, valeur: list[str] | None) -> list[str] | None:
        """Refuse un genre hors vocabulaire : un interrupteur qui ne coupe rien est un mensonge."""
        if valeur is None:
            return None
        inconnus = sorted(set(valeur) - NOTIF_GENRES)
        if inconnus:
            raise ValueError(f"Genres inconnus : {', '.join(inconnus)}.")
        return valeur

    @field_validator("fuseau")
    @classmethod
    def _fuseau_connu(cls, valeur: str | None) -> str | None:
        """Refuse un fuseau inconnu de la base IANA.

        Sans ce contrôle, un fuseau fautif ne casserait rien **ici** mais ferait échouer chaque
        émission plus tard (``ZoneInfoNotFoundError`` au moment de décider du silence nocturne) :
        l'erreur apparaîtrait loin de sa cause, dans le chemin d'un coup de jeu.
        """
        if valeur is None:
            return None
        if valeur not in available_timezones():
            raise ValueError(f"Fuseau horaire inconnu : {valeur}.")
        # Contrôle de chargement effectif : `available_timezones()` liste, `ZoneInfo` charge.
        ZoneInfo(valeur)
        return valeur


@router.get("", response_model=ListeOut)
async def lister(
    non_lues: Annotated[bool, Query(description="Ne rendre que les non lues.")] = False,
    limite: Annotated[int, Query(ge=1, le=service.LIMITE_LECTURE)] = service.LIMITE_LECTURE,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> ListeOut:
    """Mes notifications, les plus récentes d'abord, et le compte de mes non lues."""
    notifications = await service.lister(
        db, current_user.id, seulement_non_lues=non_lues, limite=limite
    )
    return ListeOut(
        notifications=[NotificationOut.de(n) for n in notifications],
        nb_non_lues=await service.nb_non_lues(db, current_user.id),
    )


@router.post("/lues", response_model=ListeOut)
async def marquer_toutes_lues(
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    db: AsyncSession = Depends(get_session),
) -> ListeOut:
    """Marque toutes mes notifications comme lues et rend la liste à jour.

    Déclarée **avant** ``/{notification_id}/lue`` : sans cela, « lues » serait d'abord essayé comme
    un identifiant de notification (et rejeté en 422 par la validation d'UUID).
    """
    await service.marquer_toutes_lues(db, current_user.id)
    await db.commit()
    notifications = await service.lister(db, current_user.id)
    return ListeOut(
        notifications=[NotificationOut.de(n) for n in notifications],
        nb_non_lues=await service.nb_non_lues(db, current_user.id),
    )


@router.post("/{notification_id}/lue", response_model=NotificationOut)
async def marquer_lue(
    notification_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    db: AsyncSession = Depends(get_session),
) -> NotificationOut:
    """Marque une de mes notifications comme lue. Celle d'un autre compte est **introuvable**."""
    try:
        notification = await service.marquer_lue(db, current_user.id, notification_id)
    except service.NotificationIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    await db.commit()
    return NotificationOut.de(notification)


@router.get("/reglages", response_model=ReglagesOut)
async def lire_reglages(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> ReglagesOut:
    """Mes réglages de notification — les défauts si je n'y ai jamais touché."""
    return ReglagesOut.de(await service.charger_reglages(db, current_user.id))


@router.patch("/reglages", response_model=ReglagesOut)
async def modifier_reglages(
    corps: ReglagesIn,
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    db: AsyncSession = Depends(get_session),
) -> ReglagesOut:
    """Modifie mes réglages (partiellement) et rend l'état complet qui en résulte."""
    try:
        reglages = await service.enregistrer_reglages(
            db,
            current_user.id,
            genres_desactives=corps.genres_desactives,
            silence_actif=corps.silence_actif,
            silence_debut=corps.silence_debut,
            silence_fin=corps.silence_fin,
            fuseau=corps.fuseau,
            relais_email_invitation=corps.relais_email_invitation,
            relais_push=corps.relais_push,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await db.commit()
    return ReglagesOut.de(reglages)
