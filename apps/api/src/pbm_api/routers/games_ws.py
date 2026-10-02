"""Transport temps réel d'une partie (lot `j-temps-reel`) : WebSocket + repli en interrogation.

Deux portes vers le même calcul (`pbm_api.games.temps_reel`) :

* ``GET /games/{id}/sync?depuis=N`` — le **repli en interrogation périodique** : un client dont le
  WebSocket est impossible (réseau d'école, proxy) rejoue la partie en interrogeant cette route. Il
  reçoit la même charge que la resync du WebSocket (vue courante + coups depuis N) et avance
  ``depuis`` au fil des réponses. Plus lent, mais la partie se termine — et le client l'annonce
  (« connexion dégradée ») ;
* ``WS /games/{id}/ws?depuis=N`` — le canal **authentifié** : il s'ouvre sur la session du compte,
  refuse un joueur étranger à la partie (comme en HTTP : 404, pas de fuite d'existence) et refuse
  une origine tierce (défense anti-CSWSH). Le pilotage (diffusion numérotée, battement de cœur,
  resynchronisation) vit dans `temps_reel.piloter_canal` ; cette route n'en est que l'adaptateur.

Le WebSocket porte **les mêmes cookies** qu'une requête HTTP, mais **pas** la protection CORS du
navigateur : c'est l'en-tête ``Origin`` qui doit être contrôlé ici, sinon un site tiers ouvrirait un
canal authentifié à l'insu du joueur (`docs/SECURITE.md`).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect, WebSocketState

from pbm_api.auth.dependencies import require_game_access
from pbm_api.config import settings
from pbm_api.db import async_session_factory, get_session
from pbm_api.games.errors import PartieIntrouvable
from pbm_api.games.service import _game_pour_participant
from pbm_api.games.temps_reel import HUB, Canal, piloter_canal, resynchroniser
from pbm_api.models import Session, User
from pbm_api.security.tokens import hash_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["games"])

GAME_NOT_FOUND_MESSAGE = "Partie introuvable."

#: Codes de fermeture WebSocket (plage applicative 4000-4999). On distingue « non authentifié » de
#: « introuvable » exactement comme en HTTP (401 vs 404) : un compte sans droit de jeu ou non
#: participant reçoit « introuvable » (aucune fuite d'existence) ; une origine tierce est refusée
#: avant toute authentification.
FERMETURE_NON_AUTHENTIFIE = 4401
FERMETURE_INTROUVABLE = 4404
FERMETURE_ORIGINE = 4403


# --- Repli en interrogation périodique (HTTP) --------------------------------


@router.get("/{game_id}/sync")
async def sync_game(
    game_id: uuid.UUID,
    depuis: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_game_access),
) -> dict:
    """Repli en interrogation : vue courante + coups depuis ``depuis``, borné au participant.

    Même charge que la resynchronisation du WebSocket : un client sans WebSocket possible interroge
    périodiquement cette route pour finir la partie. 404 si l'utilisateur ne participe pas (pas de
    fuite d'existence, comme les autres routes de partie).
    """
    try:
        game = await _game_pour_participant(db, game_id, current_user.id)
    except PartieIntrouvable as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GAME_NOT_FOUND_MESSAGE) from exc
    return await resynchroniser(db, game, user_id=current_user.id, depuis=depuis)


# --- Authentification du canal WebSocket -------------------------------------


def origine_autorisee(origine: str | None) -> bool:
    """Vrai si ``origine`` est l'origine du front (défense anti-CSWSH).

    Le WebSocket échappe à la protection CORS : sans ce contrôle, un site tiers ouvrirait un canal
    authentifié par le cookie du joueur. On n'autorise que l'origine publique du front
    (``settings.app_public_url``). Une origine absente (client non-navigateur) est refusée : le
    canal est destiné au navigateur du joueur.
    """
    if not origine:
        return False
    return origine.rstrip("/") == settings.app_public_url.rstrip("/")


async def resoudre_utilisateur(db: AsyncSession, raw_token: str | None) -> User | None:
    """Résout l'utilisateur du cookie de session, **avec droit de jeu**, ou ``None``.

    Reproduit la chaîne HTTP (`get_current_session` → `get_current_user` → `require_game_access`)
    pour le WebSocket, qui ne passe pas par l'injection de dépendances FastAPI. ``None`` couvre tous
    les refus (cookie absent/invalide/expiré, compte sans droit de jeu) ; l'appelant choisit le code
    de fermeture selon qu'il y avait ou non une session valide.
    """
    if not raw_token:
        return None
    session_row = (
        await db.execute(select(Session).where(Session.token_hash == hash_token(raw_token)))
    ).scalar_one_or_none()
    if session_row is None or session_row.expires_at < datetime.now(UTC).replace(tzinfo=None):
        return None
    user = await db.get(User, session_row.user_id)
    if user is None or not user.game_access:
        return None
    return user


class _CanalWebSocket:
    """Adaptateur :class:`Canal` au-dessus d'une WebSocket Starlette.

    Traduit la déconnexion en ``None`` (fin propre du pilotage) et n'émet plus rien une fois le
    socket fermé. C'est l'unique couche qui connaît le transport : le pilotage reste testable sur un
    faux canal en mémoire.
    """

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket

    async def recevoir(self) -> dict | None:
        try:
            return await self._ws.receive_json()
        except (WebSocketDisconnect, RuntimeError):
            return None  # déconnexion : fin propre du pilotage
        except ValueError:
            # Trame non-JSON : on ne coupe pas le canal pour autant — le pilote répondra « type
            # inconnu » (jamais un repli silencieux), et le client reste connecté.
            return {}

    async def envoyer(self, message: dict) -> None:
        if self._ws.application_state == WebSocketState.CONNECTED:
            await self._ws.send_json(message)


@router.websocket("/{game_id}/ws")
async def ws_game(websocket: WebSocket, game_id: uuid.UUID) -> None:
    """Canal temps réel d'une partie : authentifié, borné au participant, défendu contre le CSWSH.

    On refuse une origine tierce avant toute chose, puis on authentifie sur le cookie de session et
    on vérifie la participation (sinon fermeture « introuvable », sans fuite). Une fois accepté, le
    pilotage est délégué à `temps_reel.piloter_canal` ; chaque resynchronisation ouvre une session
    courte plutôt que d'immobiliser une connexion de base pour toute la durée du canal.
    """
    if not origine_autorisee(websocket.headers.get("origin")):
        await websocket.close(code=FERMETURE_ORIGINE)
        return

    async with async_session_factory() as db:
        user = await resoudre_utilisateur(
            db, websocket.cookies.get(settings.session_cookie_name)
        )
        if user is None:
            # On ne distingue pas « pas de session » de « sans droit de jeu » côté client :
            # l'absence de cookie renvoie « non authentifié », le reste « introuvable ».
            if not websocket.cookies.get(settings.session_cookie_name):
                await websocket.close(code=FERMETURE_NON_AUTHENTIFIE)
            else:
                await websocket.close(code=FERMETURE_INTROUVABLE)
            return
        try:
            game = await _game_pour_participant(db, game_id, user.id)
        except PartieIntrouvable:
            await websocket.close(code=FERMETURE_INTROUVABLE)
            return
        graine_hex = game.graine

    await websocket.accept()
    try:
        depuis = max(0, int(websocket.query_params.get("depuis", 0)))
    except (TypeError, ValueError):
        depuis = 0

    abonne = HUB.souscrire(game_id, user.id)
    canal: Canal = _CanalWebSocket(websocket)
    try:
        await piloter_canal(
            canal,
            abonne=abonne,
            fabrique_session=async_session_factory,
            game_id=game_id,
            graine_hex=graine_hex,
            depuis=depuis,
        )
    except WebSocketDisconnect:
        pass
    finally:
        HUB.desouscrire(game_id, abonne)
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close()
