"""Routes de lecture des parties (lot `j-partie-service`) : lister ses parties, en consulter une.

Ce lot pose l'**enveloppe** de persistance d'une partie ; son API HTTP ici se limite à la lecture,
toujours **bornée au participant** : une partie à laquelle l'utilisateur ne joue pas répond 404
(jamais 403 — pas de fuite d'existence, comme les decks). La création d'une partie (choix du deck,
adversaire, tirage au sort) est le lot `j-lancement-partie` ; appliquer un coup, `j-autorite-vues` ;
sa diffusion temps réel, `j-temps-reel` (canal WebSocket + repli HTTP, `routers/games_ws.py`).
On ne les approxime pas ici.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_game_access
from pbm_api.db import get_session
from pbm_api.games.errors import (
    ActionRefusee,
    ConflitNumero,
    PartieIntrouvable,
    PartieNonActive,
)
from pbm_api.games.projection import projeter_resultat, vue_autoritaire
from pbm_api.games.schemas import ActionIn, GameDetailOut, GamePlayerOut, GameSummaryOut
from pbm_api.games.service import (
    _game_pour_participant,
    appliquer_action,
    parties_du_joueur,
    reprendre_partie,
)
from pbm_api.games.temps_reel import HUB
from pbm_api.models import GamePlayer, User

router = APIRouter(prefix="/games", tags=["games"])

GAME_NOT_FOUND_MESSAGE = "Partie introuvable."


@router.get("", response_model=list[GameSummaryOut])
async def list_games(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> list[GameSummaryOut]:
    """Les parties du joueur courant, de la plus récente à la plus ancienne."""
    games = await parties_du_joueur(db, current_user.id)
    return [GameSummaryOut.model_validate(g, from_attributes=True) for g in games]


@router.get("/{game_id}", response_model=GameDetailOut)
async def get_game(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
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


@router.get("/{game_id}/state")
async def get_game_state(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> dict:
    """La **vue autoritaire** de la partie pour le joueur courant, ou 404 s'il n'y participe pas.

    Le client reçoit exclusivement ce que le serveur autorise (`pbm_game.sortie.projeter` via
    :func:`vue_autoritaire`) : jamais la main adverse, ni l'ordre d'une pioche, ni l'identité d'une
    récompense. L'état est reconstruit depuis le journal (« tout est rejouable »), empreinte
    vérifiée. Le secret d'aléatoire n'apparaît jamais, seuls les jetons opaques en dérivent.
    """
    try:
        game = await _game_pour_participant(db, game_id, current_user.id)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    etat, rng = await reprendre_partie(db, game)
    return vue_autoritaire(etat, rng, user_id=current_user.id, graine_hex=game.graine)


@router.post("/{game_id}/actions")
async def play_action(
    game_id: uuid.UUID,
    body: ActionIn,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> dict:
    """Jouer un coup : le serveur fait autorité — il rejoue et valide, puis renvoie la vue projetée.

    L'auteur du coup est **toujours** le joueur de la session (`appliquer_action` l'impose) : un
    client ne peut pas agir sous une autre identité. Un coup illégal est refusé (422) avec le motif
    du moteur, **sans jamais altérer l'état** ; un conflit de numéro ou une partie close → 409. En
    retour, la vue autoritaire du joueur courant après le coup et les événements qui le concernent —
    jamais l'état brut, qui porte l'information cachée.

    Après un coup réel (non rejeu), le résultat est **diffusé** sur le canal temps réel (`HUB`) :
    chaque joueur abonné le reçoit projeté pour lui. Le journal reste la source de vérité — la
    diffusion est un raccourci de latence, pas la garantie de livraison (celle-ci tient à la
    resynchronisation par numéro, lot `j-temps-reel`).
    """
    try:
        resultat = await appliquer_action(
            db,
            game_id=game_id,
            user_id=current_user.id,
            type=body.type,
            params=body.params,
            numero_attendu=body.numero_attendu,
        )
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except ActionRefusee as exc:
        # 422 en clair : le nom du constant `HTTP_422_*` a changé entre versions de Starlette
        # (ENTITY → CONTENT) ; le code numérique, lui, est stable et sans avertissement.
        raise HTTPException(422, str(exc)) from exc
    except (ConflitNumero, PartieNonActive) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    # `appliquer_action` a commité ; on relit la partie pour sa graine (secret serveur, jamais
    # renvoyé — seuls les jetons opaques en dérivent) et pour re-vérifier la participation.
    game = await _game_pour_participant(db, game_id, current_user.id)
    HUB.publier(game_id, resultat, graine_hex=game.graine)
    return projeter_resultat(resultat, user_id=current_user.id, graine_hex=game.graine)
