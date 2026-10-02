"""Routes de la recherche d'adversaire (lot `j-file-attente`) : file d'attente, présence.

Entrer dans la file avec un deck choisi, consulter son attente, annuler, voir la présence des
comptes invités. **Toutes** les routes sont gardées par
:func:`~pbm_api.auth.dependencies.require_game_access` (D11) : un compte sans droit d'accès au jeu
reçoit **404** partout, comme pour un objet d'autrui —
le jeu n'existe pas pour lui. Les écritures (entrer, annuler) exigent le jeton CSRF, comme toute
mutation utilisateur.

Le serveur fait autorité : le client propose un `deck_id`, le serveur vérifie (possession, légalité,
scripts) et refuse en nommant ce qui manque. L'appariement lui-même, et son verrou anti-course,
vivent dans :mod:`pbm_api.games.matchmaking` — le routeur ne fait que traduire exceptions et
résultats en réponses HTTP.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_csrf, require_game_access
from pbm_api.db import get_session
from pbm_api.games import matchmaking
from pbm_api.games.entry import DeckInjouable, DeckIntrouvable
from pbm_api.games.matchmaking import Apparie, DejaEnPartie, EnAttente
from pbm_api.models import User
from pbm_api.security.rate_limit import get_redis

router = APIRouter(prefix="/matchmaking", tags=["matchmaking"])

NOT_FOUND_MESSAGE = "Ressource introuvable."


def get_redis_client() -> Redis:
    """Un client Redis par requête (comme `pbm_api.security.rate_limit.get_redis`).

    Exposé en dépendance FastAPI pour que les tests puissent le surcharger si besoin ; en pratique
    il renvoie le même client que le reste de l'app.
    """
    return get_redis()


# --- Schémas d'entrée / sortie ----------------------------------------------


class EntrerFileIn(BaseModel):
    """Entrée dans la file : le deck avec lequel le joueur veut jouer."""

    deck_id: uuid.UUID


class RefusDeckOut(BaseModel):
    """Une carte (ou le deck) refusé à l'entrée, avec la raison — jamais un refus muet."""

    carte: str
    raison: str


class FileOut(BaseModel):
    """État de la file pour le joueur. `status` discrimine les deux cas vivants.

    * `apparie` — une partie a été créée : `game_id` et `adversaire_user_id` sont renseignés ;
    * `en_attente` — personne encore : `position`, `joueurs_en_file`, `attente_secondes` ;
    * `absent` — le joueur n'est pas (ou plus) dans la file (seulement en consultation GET).
    """

    status: str
    game_id: uuid.UUID | None = None
    adversaire_user_id: uuid.UUID | None = None
    position: int | None = None
    joueurs_en_file: int | None = None
    attente_secondes: float | None = None


class PresenceOut(BaseModel):
    """Présence des comptes invités, et options de repli s'il n'y a personne à affronter."""

    en_ligne: int
    en_partie: int
    en_file: int
    autres_disponibles: int = Field(
        description="Joueurs en ligne, hors partie, autres que soi : les adversaires possibles."
    )
    options: list[str]


def _reponse(resultat: Apparie | EnAttente) -> FileOut:
    """Traduit le résultat du service en réponse HTTP (apparié ou en attente)."""
    if isinstance(resultat, Apparie):
        return FileOut(
            status="apparie",
            game_id=resultat.game_id,
            adversaire_user_id=resultat.adversaire_user_id,
        )
    return FileOut(
        status="en_attente",
        position=resultat.position,
        joueurs_en_file=resultat.joueurs_en_file,
        attente_secondes=resultat.attente_secondes,
    )


# --- Routes -----------------------------------------------------------------


@router.post("/queue", response_model=FileOut)
async def entrer_file(
    body: EntrerFileIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> FileOut:
    """Entre dans la file avec un deck et tente un appariement immédiat.

    404 si le deck n'est pas celui du joueur (pas de fuite) ; 422 si le deck n'est pas jouable, avec
    les cartes en cause ; 409 si le joueur est déjà dans une partie. Sinon : apparié (partie créée)
    ou en attente.
    """
    try:
        resultat = await matchmaking.rejoindre(
            db, redis, user_id=current_user.id, deck_id=body.deck_id
        )
    except DeckIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_MESSAGE) from exc
    except DeckInjouable as exc:
        # 422 avec le détail nommé : le client affiche exactement ce qui manque (critère du lot).
        raise HTTPException(
            422,
            detail={
                "message": "Deck non jouable.",
                "refus": [{"carte": nom, "raison": raison} for nom, raison in exc.refus],
            },
        ) from exc
    except DejaEnPartie as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _reponse(resultat)


@router.get("/queue", response_model=FileOut)
async def consulter_file(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> FileOut:
    """L'état réel de la recherche du joueur : apparié, en attente (rang, temps), ou pas en file."""
    game_id = await matchmaking.partie_active_de(db, current_user.id)
    if game_id is not None:
        return FileOut(status="apparie", game_id=game_id)
    attente = await matchmaking.statut_attente(redis, current_user.id)
    if attente is None:
        return FileOut(status="absent")
    return _reponse(attente)


@router.delete("/queue", response_model=FileOut)
async def quitter_file(
    current_user: Annotated[User, Depends(require_game_access)],
    _csrf: Annotated[None, Depends(require_csrf)],
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> FileOut:
    """Annule la recherche : retire le joueur de la file. Idempotent (absent → `absent`)."""
    await matchmaking.quitter(redis, current_user.id)
    return FileOut(status="absent")


@router.get("/presence", response_model=PresenceOut)
async def presence(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    redis: Annotated[Redis, Depends(get_redis_client)],
) -> PresenceOut:
    """La présence des comptes invités, et les options de repli s'il n'y a personne à affronter."""
    p = await matchmaking.presence(db, redis, current_user.id)
    return PresenceOut(
        en_ligne=p.en_ligne,
        en_partie=p.en_partie,
        en_file=p.en_file,
        autres_disponibles=p.autres_disponibles,
        options=p.options,
    )
