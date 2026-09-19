"""Logique métier de la page profil — indépendante de FastAPI (testable directement).

Comme `pbm_api.auth.service` : toute route dérive l'utilisateur du cookie de session, jamais
d'un identifiant fourni par le client.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.errors import UnsupportedImageFormatError
from pbm_api.ai.images import detect_media_type
from pbm_api.auth.errors import (
    InvalidCredentialsError,
    InvalidTokenError,
    PasswordCompromisedError,
    PasswordTooShortError,
    TokenAlreadyUsedError,
    TokenExpiredError,
)
from pbm_api.auth.service import normalize_email
from pbm_api.config import settings
from pbm_api.email import EmailSender
from pbm_api.models import EmailToken, EmailTokenKind, Session, User
from pbm_api.profile.avatar import ALLOWED_MEDIA_TYPES, process_avatar
from pbm_api.profile.errors import (
    AvatarNotFoundError,
    PseudoAlreadyTakenError,
    SessionNotFoundError,
)
from pbm_api.security.compromised import CompromisedPasswordChecker
from pbm_api.security.passwords import hash_password, is_password_long_enough, verify_password
from pbm_api.security.tokens import generate_opaque_token, hash_token
from pbm_api.storage import StorageBackend

CHANGE_EMAIL_SUBJECT = "Confirme ta nouvelle adresse PokeBoyManager"
EMAIL_CHANGED_NOTICE_SUBJECT = "L'adresse e-mail de ton compte PokeBoyManager a changé"


def _utc_now_naive() -> datetime:
    """Comme `pbm_api.auth.service._utc_now_naive` : `sessions`/`email_tokens` sont en
    `TIMESTAMP WITHOUT TIME ZONE`, toujours en UTC, jamais "aware"."""
    return datetime.now(UTC).replace(tzinfo=None)


async def update_pseudo(db: AsyncSession, user: User, pseudo: str) -> User:
    existing = await db.execute(
        select(User).where(User.pseudo == pseudo, User.id != user.id)
    )
    if existing.scalar_one_or_none() is not None:
        raise PseudoAlreadyTakenError

    user.pseudo = pseudo
    await db.commit()
    return user


async def set_avatar(db: AsyncSession, user: User, storage: StorageBackend, data: bytes) -> User:
    media_type = detect_media_type(data)
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise UnsupportedImageFormatError("Format d'image non reconnu (JPEG ou PNG attendus).")

    processed = process_avatar(data)
    key = f"avatars/{user.id}.jpg"
    await storage.put(key, processed, "image/jpeg")

    user.avatar_key = key
    await db.commit()
    return user


async def get_avatar_bytes(user: User, storage: StorageBackend) -> bytes:
    if user.avatar_key is None:
        raise AvatarNotFoundError

    data = await storage.get(user.avatar_key)
    if data is None:
        raise AvatarNotFoundError
    return data


async def request_email_change(
    db: AsyncSession, user: User, new_email: str, email_sender: EmailSender
) -> None:
    """Même issue observable que l'adresse soit déjà prise ou non (anti-énumération, comme
    `pbm_api.auth.service.register_user`)."""
    normalized = normalize_email(new_email)
    if normalized == user.email:
        return

    existing = await db.execute(
        select(User).where(User.email == normalized, User.id != user.id)
    )
    if existing.scalar_one_or_none() is not None:
        return

    user.pending_email = normalized
    raw_token = generate_opaque_token()
    db.add(
        EmailToken(
            user_id=user.id,
            kind=EmailTokenKind.change_email,
            token_hash=hash_token(raw_token),
            expires_at=_utc_now_naive() + timedelta(minutes=settings.email_token_ttl_minutes),
        )
    )
    await db.commit()

    link = f"{settings.app_public_url}/confirmer-email?token={raw_token}"
    await email_sender.send(
        normalized,
        CHANGE_EMAIL_SUBJECT,
        f"Confirme ta nouvelle adresse e-mail PokeBoyManager : {link}\n"
        f"Ce lien expire dans {settings.email_token_ttl_minutes} minutes.",
    )


async def confirm_email_change(
    db: AsyncSession, token: str, email_sender: EmailSender
) -> None:
    result = await db.execute(
        select(EmailToken).where(
            EmailToken.token_hash == hash_token(token),
            EmailToken.kind == EmailTokenKind.change_email,
        )
    )
    email_token = result.scalar_one_or_none()
    if email_token is None:
        raise InvalidTokenError
    if email_token.used_at is not None:
        raise TokenAlreadyUsedError
    if email_token.expires_at < _utc_now_naive():
        raise TokenExpiredError

    user = await db.get(User, email_token.user_id)
    if user is None or user.pending_email is None:
        raise InvalidTokenError

    old_email = user.email
    email_token.used_at = _utc_now_naive()
    user.email = user.pending_email
    user.pending_email = None
    user.email_verified_at = _utc_now_naive()
    await db.commit()

    await email_sender.send(
        old_email,
        EMAIL_CHANGED_NOTICE_SUBJECT,
        f"L'adresse e-mail de ton compte PokeBoyManager est désormais {user.email}. "
        "Si tu n'es pas à l'origine de ce changement, contacte-nous immédiatement.",
    )


async def change_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
    compromised_checker: CompromisedPasswordChecker,
    keep_session: Session,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError
    if not is_password_long_enough(new_password):
        raise PasswordTooShortError
    if await compromised_checker.is_compromised(new_password):
        raise PasswordCompromisedError

    user.password_hash = hash_password(new_password)

    # Rotation : toute autre session est révoquée (la session courante, déjà authentifiée
    # par ce même mot de passe, est conservée — contrairement à la réinitialisation "mot de
    # passe oublié" qui n'a aucune session de confiance à garder).
    other_sessions = await db.execute(
        select(Session).where(Session.user_id == user.id, Session.id != keep_session.id)
    )
    for session_row in other_sessions.scalars().all():
        await db.delete(session_row)

    await db.commit()


async def list_sessions(db: AsyncSession, user: User) -> list[Session]:
    result = await db.execute(
        select(Session).where(Session.user_id == user.id).order_by(Session.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_session(db: AsyncSession, user: User, session_id: uuid.UUID) -> None:
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user.id)
    )
    session_row = result.scalar_one_or_none()
    if session_row is None:
        raise SessionNotFoundError

    await db.delete(session_row)
    await db.commit()


async def delete_account(
    db: AsyncSession, user: User, password: str, storage: StorageBackend
) -> None:
    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError

    if user.avatar_key is not None:
        await storage.delete(user.avatar_key)

    # Sessions, jetons d'e-mail et clés IA suivent par `ondelete="CASCADE"` (voir
    # `pbm_api.models.users`) — un seul `DELETE` couvre tout le compte.
    await db.delete(user)
    await db.commit()
