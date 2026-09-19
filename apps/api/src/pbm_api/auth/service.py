"""Logique métier de l'authentification — indépendante de FastAPI (testable directement).

Aucune route ne reçoit d'identifiant utilisateur du client : toute lecture/écriture ici
part d'un jeton (session, e-mail) ou d'un e-mail fourni, jamais d'un `user_id` en entrée.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.errors import (
    InvalidCredentialsError,
    InvalidTokenError,
    PasswordCompromisedError,
    PasswordTooShortError,
    TokenAlreadyUsedError,
    TokenExpiredError,
)
from pbm_api.config import settings
from pbm_api.email import EmailSender
from pbm_api.models import EmailToken, EmailTokenKind, Session, User
from pbm_api.security.compromised import CompromisedPasswordChecker
from pbm_api.security.passwords import hash_password, is_password_long_enough, verify_password
from pbm_api.security.tokens import generate_opaque_token, hash_token

VERIFY_EMAIL_SUBJECT = "Vérifiez votre adresse PokeBoyManager"
RESET_PASSWORD_SUBJECT = "Réinitialisation de votre mot de passe PokeBoyManager"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _utc_now_naive() -> datetime:
    """`sessions.expires_at`/`email_tokens.*` sont `TIMESTAMP WITHOUT TIME ZONE` : toutes
    les valeurs comparées/stockées ici sont en UTC, sans `tzinfo` (asyncpg rejette un
    datetime "aware" sur une colonne sans fuseau)."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _check_password_policy(
    password: str, compromised_checker: CompromisedPasswordChecker
) -> None:
    if not is_password_long_enough(password):
        raise PasswordTooShortError
    if await compromised_checker.is_compromised(password):
        raise PasswordCompromisedError


async def _issue_email_token(
    db: AsyncSession, user: User, kind: EmailTokenKind
) -> str:
    raw_token = generate_opaque_token()
    db.add(
        EmailToken(
            user_id=user.id,
            kind=kind,
            token_hash=hash_token(raw_token),
            expires_at=_utc_now_naive() + timedelta(minutes=settings.email_token_ttl_minutes),
        )
    )
    return raw_token


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    compromised_checker: CompromisedPasswordChecker,
    email_sender: EmailSender,
) -> None:
    """Toujours la même issue observable, que l'e-mail soit déjà pris ou non (anti-énumération)."""
    await _check_password_policy(password, compromised_checker)

    normalized = normalize_email(email)
    existing = await db.execute(select(User).where(User.email == normalized))
    if existing.scalar_one_or_none() is not None:
        return

    user = User(email=normalized, password_hash=hash_password(password))
    db.add(user)
    await db.flush()

    raw_token = await _issue_email_token(db, user, EmailTokenKind.verify_email)
    await db.commit()

    link = f"{settings.app_public_url}/verifier?token={raw_token}"
    await email_sender.send(
        normalized,
        VERIFY_EMAIL_SUBJECT,
        f"Bienvenue sur PokeBoyManager !\n\nConfirmez votre adresse : {link}\n"
        f"Ce lien expire dans {settings.email_token_ttl_minutes} minutes.",
    )


async def _consume_email_token(
    db: AsyncSession, token: str, kind: EmailTokenKind
) -> EmailToken:
    result = await db.execute(
        select(EmailToken).where(
            EmailToken.token_hash == hash_token(token), EmailToken.kind == kind
        )
    )
    email_token = result.scalar_one_or_none()
    if email_token is None:
        raise InvalidTokenError
    if email_token.used_at is not None:
        raise TokenAlreadyUsedError
    if email_token.expires_at < _utc_now_naive():
        raise TokenExpiredError
    return email_token


async def verify_email(db: AsyncSession, token: str) -> None:
    email_token = await _consume_email_token(db, token, EmailTokenKind.verify_email)
    user = await db.get(User, email_token.user_id)
    if user is None:
        raise InvalidTokenError

    email_token.used_at = _utc_now_naive()
    user.email_verified_at = _utc_now_naive()
    await db.commit()


async def authenticate_and_create_session(
    db: AsyncSession, email: str, password: str, ip_address: str | None, user_agent: str | None
) -> tuple[User, str]:
    """Vérifie les identifiants puis crée une session neuve (rotation à la connexion)."""
    normalized = normalize_email(email)
    result = await db.execute(select(User).where(User.email == normalized))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError

    raw_token = generate_opaque_token()
    db.add(
        Session(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            user_agent=user_agent[:255] if user_agent else None,
            ip_address=ip_address,
            expires_at=_utc_now_naive() + timedelta(days=settings.session_ttl_days),
        )
    )
    await db.commit()
    return user, raw_token


async def logout(db: AsyncSession, session_row: Session) -> None:
    await db.delete(session_row)
    await db.commit()


async def request_password_reset(
    db: AsyncSession, email: str, email_sender: EmailSender
) -> None:
    """Réponse toujours identique côté appelant, que l'e-mail existe ou non."""
    normalized = normalize_email(email)
    result = await db.execute(select(User).where(User.email == normalized))
    user = result.scalar_one_or_none()
    if user is None:
        return

    raw_token = await _issue_email_token(db, user, EmailTokenKind.reset_password)
    await db.commit()

    link = f"{settings.app_public_url}/reinitialiser?token={raw_token}"
    await email_sender.send(
        normalized,
        RESET_PASSWORD_SUBJECT,
        f"Une réinitialisation de mot de passe a été demandée pour ce compte.\n\n"
        f"Si c'est vous : {link}\nSinon, ignorez cet e-mail.\n"
        f"Ce lien expire dans {settings.email_token_ttl_minutes} minutes.",
    )


async def reset_password(
    db: AsyncSession,
    token: str,
    new_password: str,
    compromised_checker: CompromisedPasswordChecker,
) -> None:
    await _check_password_policy(new_password, compromised_checker)

    email_token = await _consume_email_token(db, token, EmailTokenKind.reset_password)
    user = await db.get(User, email_token.user_id)
    if user is None:
        raise InvalidTokenError

    email_token.used_at = _utc_now_naive()
    user.password_hash = hash_password(new_password)

    # Un mot de passe changé invalide toute session active (y compris celle de l'attaquant
    # si le compte avait été compromis).
    existing_sessions = await db.execute(select(Session).where(Session.user_id == user.id))
    for session_row in existing_sessions.scalars().all():
        await db.delete(session_row)

    await db.commit()
