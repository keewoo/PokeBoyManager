"""Dépendances FastAPI réutilisables par toute route utilisateur (ce lot et les suivants).

`current_user`/`current_session` ne dérivent jamais d'un identifiant reçu du client — ils
proviennent exclusivement du cookie de session, résolu côté serveur.
"""

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.models import Session, User
from pbm_api.security.csrf import CSRF_HEADER_NAME, verify_csrf_token
from pbm_api.security.tokens import hash_token


async def get_current_session(
    request: Request, db: AsyncSession = Depends(get_session)
) -> tuple[Session, str]:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non authentifié")

    result = await db.execute(select(Session).where(Session.token_hash == hash_token(raw_token)))
    session_row = result.scalar_one_or_none()
    if session_row is None or session_row.expires_at < datetime.now(UTC).replace(tzinfo=None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide ou expirée")

    return session_row, raw_token


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_session)
) -> User:
    session_row, _ = await get_current_session(request, db)
    user = await db.get(User, session_row.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide")
    return user


async def require_csrf(
    request: Request,
    current: tuple[Session, str] = Depends(get_current_session),
) -> None:
    """À ajouter avec `get_current_user` sur toute route qui écrit pour un utilisateur connecté."""
    _, raw_session_token = current
    submitted = request.headers.get(CSRF_HEADER_NAME)
    if not verify_csrf_token(raw_session_token, submitted):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Jeton CSRF invalide")
