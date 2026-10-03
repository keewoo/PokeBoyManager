"""Routes de lecture des parties (lot `j-partie-service`) : lister ses parties, en consulter une.

Ce lot pose l'**enveloppe** de persistance d'une partie ; son API HTTP ici se limite à la lecture,
toujours **bornée au participant** : une partie à laquelle l'utilisateur ne joue pas répond 404
(jamais 403 — pas de fuite d'existence, comme les decks). La création d'une partie (choix du deck,
adversaire, tirage au sort) est le lot `j-lancement-partie` ; appliquer un coup, `j-autorite-vues` ;
sa diffusion temps réel, `j-temps-reel` (canal WebSocket + repli HTTP, `routers/games_ws.py`).
On ne les approxime pas ici.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pbm_game.state.serialisation import depuis_json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_game_access
from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.games import horloges as _adapt_horloges
from pbm_api.games.adversaire_ia import MAX_APPELS_PAR_PARTIE
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.coach import (
    BilanIndisponible,
    CleCoachIndisponible,
    CoachDesactive,
    ConseilHorsEntrainement,
    PartieNonTerminee,
    PlafondConseils,
    bilan_de_partie,
    conseil_pour_joueur,
)
from pbm_api.games.errors import (
    ActionRefusee,
    ConflitNumero,
    PartieIntrouvable,
    PartieNonActive,
)
from pbm_api.games.indicateurs import catalogue_pour_etat, catalogue_pour_resultat
from pbm_api.games.projection import projeter_resultat, vue_autoritaire
from pbm_api.games.schemas import (
    ActionIn,
    BilanOut,
    ConseilOut,
    CoupConseille,
    GameDetailOut,
    GamePlayerOut,
    GameSummaryOut,
    IaCoutOut,
    MomentBilanOut,
)
from pbm_api.games.service import (
    _game_pour_participant,
    abandonner_partie,
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

    # Coût estimé de l'adversaire IA (lot j-adversaire-ia) : présent seulement quand un siège est
    # tenu par l'IA du joueur. Compteurs réels de la partie ; le prix en euros reste à faire.
    ia_cout = None
    if any(p.adversaire_ia for p in players):
        ia_cout = IaCoutOut(
            appels=game.ia_appels,
            jetons=game.ia_tokens,
            plafond_appels=MAX_APPELS_PAR_PARTIE,
        )

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
        entrainement=game.entrainement,
        engagement=game.engagement,
        journal_version=game.journal_version,
        players=[GamePlayerOut.model_validate(p, from_attributes=True) for p in players],
        ia_cout=ia_cout,
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
    catalogue = await catalogue_pour_etat(db, etat)
    catalogue_jeu = await construire_catalogue_jeu(db, etat)
    vue = vue_autoritaire(
        etat, rng, user_id=current_user.id, graine_hex=game.graine,
        catalogue=catalogue, catalogue_jeu=catalogue_jeu,
    )
    vue["horloges"] = _adapt_horloges.restant_json(game.horloges, datetime.now(UTC).timestamp())
    # Numéro d'action courant (prochain attendu) : clé d'idempotence côté client pour soumettre
    # un coup (lot ``j-plateau-interactions``).
    vue["numero"] = game.current_numero
    return vue


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
    catalogue = await catalogue_pour_resultat(db, resultat)
    catalogue_jeu = await construire_catalogue_jeu(db, depuis_json(resultat.etat))
    HUB.publier(
        game_id, resultat, graine_hex=game.graine, catalogue=catalogue, catalogue_jeu=catalogue_jeu
    )
    reponse = projeter_resultat(
        resultat, user_id=current_user.id, graine_hex=game.graine, catalogue=catalogue,
        catalogue_jeu=catalogue_jeu,
    )
    # Le prochain numéro d'action attendu, pour que le client enchaîne un coup suivant sans aller
    # relire l'état (lot ``j-plateau-interactions``).
    reponse["numero"] = game.current_numero
    return reponse


@router.post("/{game_id}/abandon")
async def abandon_game(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> dict:
    """Abandonner explicitement la partie (R-14.3) : forfait du joueur courant, l'adversaire gagne.

    Chemin dédié de l'« abandon explicite » du lot ``j-deconnexion-abandon`` — plus simple que
    :func:`play_action` (aucun ``numero_attendu`` à fournir : abandonner est toujours légal à l'état
    courant). La **confirmation** est à la charge de l'écran (on peut annuler avant de valider) ; le
    serveur, lui, applique le forfait sitôt reçu. 404 si l'utilisateur ne participe pas (pas de
    fuite d'existence), 409 si la partie n'est plus en cours. Le résultat est diffusé sur le canal
    temps réel (`HUB`) : l'adversaire voit la partie se clore avec le motif « abandon ».
    """
    try:
        resultat = await abandonner_partie(db, game_id, current_user.id)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except PartieNonActive as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    game = await _game_pour_participant(db, game_id, current_user.id)
    catalogue = await catalogue_pour_resultat(db, resultat)
    catalogue_jeu = await construire_catalogue_jeu(db, depuis_json(resultat.etat))
    HUB.publier(
        game_id, resultat, graine_hex=game.graine, catalogue=catalogue, catalogue_jeu=catalogue_jeu
    )
    reponse = projeter_resultat(
        resultat, user_id=current_user.id, graine_hex=game.graine, catalogue=catalogue,
        catalogue_jeu=catalogue_jeu,
    )
    # Le prochain numéro d'action attendu, pour que le client enchaîne un coup suivant sans aller
    # relire l'état (lot ``j-plateau-interactions``).
    reponse["numero"] = game.current_numero
    return reponse


@router.post("/{game_id}/conseil", response_model=ConseilOut)
async def get_conseil(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> ConseilOut:
    """Un conseil de l'IA du joueur pour SON tour (lot `j-coach-ia`, DJ7) — une **suggestion**.

    L'IA (sa clé) reçoit sa vue projetée et ses coups légaux, propose un coup et l'explique ; le
    serveur n'applique **rien** — le geste reste celui du joueur. Réservé aux parties d'entraînement
    (jamais entre deux humains), borné par un plafond de conseils par partie, et refusé sans clé IA
    ou si le coach est désactivé. 404 si l'utilisateur ne participe pas (pas de fuite d'existence).
    Quand aucun conseil n'est possible (ce n'est pas son tour, l'IA n'a rien trouvé), ``coup`` est
    nul et ``raison`` le dit — jamais un coup inventé.
    """
    try:
        res = await conseil_pour_joueur(
            db, game_id=game_id, user=current_user, max_conseils=settings.coach_max_conseils
        )
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except CleCoachIndisponible as exc:
        raise HTTPException(422, str(exc)) from exc
    except (CoachDesactive, ConseilHorsEntrainement, PlafondConseils, PartieNonActive) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    conseil = res.conseil
    coup = None
    if conseil.coup is not None:
        coup = CoupConseille(
            index=conseil.index if conseil.index is not None else -1,
            etiquette=conseil.coup.etiquette,
            type=conseil.coup.action.type,
            params=conseil.coup.action.params,
        )
    return ConseilOut(
        coup=coup,
        explication=conseil.explication,
        raison=conseil.raison,
        conseils_utilises=res.conseils_utilises,
        conseils_restants=res.conseils_restants,
    )


@router.get("/{game_id}/bilan", response_model=BilanOut)
async def get_bilan(
    game_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> BilanOut:
    """Le bilan de l'IA du joueur après une partie **terminée** (lot `j-coach-ia`, DJ7).

    À partir du **journal** (les coups réellement joués, pas l'état complet), l'IA (sa clé) dégage
    deux ou trois moments décisifs. Chaque moment cité est **vérifié** contre le journal : un numéro
    inventé est écarté. Désactivable (coach éteint -> 409), refusé sans clé IA (422) ou sur une
    partie non terminée (409). 404 si l'utilisateur ne participe pas. Si l'IA ne rend rien
    d'exploitable, on le dit (502) plutôt qu'un bilan vide.
    """
    try:
        res = await bilan_de_partie(db, game_id=game_id, user=current_user)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    except CleCoachIndisponible as exc:
        raise HTTPException(422, str(exc)) from exc
    except (CoachDesactive, PartieNonTerminee) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except BilanIndisponible as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return BilanOut(
        resume=res.resume,
        moments=[MomentBilanOut(**m) for m in res.moments],
    )
