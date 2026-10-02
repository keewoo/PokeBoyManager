"""Routes de lecture des parties (lot `j-partie-service`) : lister ses parties, en consulter une.

Ce lot pose l'**enveloppe** de persistance d'une partie ; son API HTTP ici se limite à la lecture,
toujours **bornée au participant** : une partie à laquelle l'utilisateur ne joue pas répond 404
(jamais 403 — pas de fuite d'existence, comme les decks). La création d'une partie (choix du deck,
adversaire, tirage au sort) est le lot `j-lancement-partie` ; appliquer un coup et sa diffusion
temps réel sont `j-autorite-vues`/`j-temps-reel`. On ne les approxime pas ici.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user
from pbm_api.db import get_session
from pbm_api.games.errors import PartieIntrouvable
from pbm_api.games.schemas import GameDetailOut, GamePlayerOut, GameSummaryOut
from pbm_api.games.service import _game_pour_participant, parties_du_joueur
from pbm_api.models import GamePlayer, User

router = APIRouter(prefix="/games", tags=["games"])

GAME_NOT_FOUND_MESSAGE = "Partie introuvable."


@router.get("", response_model=list[GameSummaryOut])
async def list_games(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[GameSummaryOut]:
    """Les parties du joueur courant, de la plus récente à la plus ancienne."""
    games = await parties_du_joueur(db, current_user.id)
    return [GameSummaryOut.model_validate(g, from_attributes=True) for g in games]


@router.get("/{game_id}", response_model=GameDetailOut)
async def get_game(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> GameDetailOut:
    """Le détail d'une partie du joueur courant, ou 404 s'il n'y participe pas (pas de fuite)."""
    try:
        game = await _game_pour_participant(db, game_id, current_user.id)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc

    players = (
        await db.execute(
            select(GamePlayer).where(GamePlayer.game_id == game_id).order_by(GamePlayer.seat)
        )
    ).scalars().all()

    # Construction explicite (le `Game` ORM ne porte pas `players`) : on assemble le résumé et on
    # y greffe les sièges chargés à part.
    return GameDetailOut(
        id=game.id,
        status=game.status,
        current_numero=game.current_numero,
        vainqueur_user_id=game.vainqueur_user_id,
        raison_fin=game.raison_fin,
        created_at=game.created_at,
        updated_at=game.updated_at,
        engagement=game.engagement,
        journal_version=game.journal_version,
        players=[GamePlayerOut.model_validate(p, from_attributes=True) for p in players],
    )
