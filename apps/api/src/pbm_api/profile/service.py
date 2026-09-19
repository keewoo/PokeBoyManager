"""Logique métier de la page profil — indépendante de FastAPI (testable directement).

Comme `pbm_api.auth.service` : toute route dérive l'utilisateur du cookie de session, jamais
d'un identifiant fourni par le client.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.errors import UnsupportedImageFormatError
from pbm_api.ai.images import detect_media_type
from pbm_api.auth.errors import (
    InvalidBirthDateError,
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
from pbm_api.models import (
    CollectionItem,
    DataExport,
    Detection,
    EmailToken,
    EmailTokenKind,
    Session,
    Upload,
    User,
)
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


async def update_identity(
    db: AsyncSession,
    user: User,
    pseudo: str,
    first_name: str | None,
    last_name: str,
    birth_date: date,
) -> User:
    existing = await db.execute(
        select(User).where(User.pseudo == pseudo, User.id != user.id)
    )
    if existing.scalar_one_or_none() is not None:
        raise PseudoAlreadyTakenError

    # Pas de contrôle d'âge minimum ici : celui-ci ne s'applique qu'à l'inscription libre
    # (`pbm_api.auth.service.register_user`) — un compte existant (y compris créé par
    # l'administrateur pour un mineur, consentement du parent porté par JF) reste éditable.
    if birth_date >= date.today():
        raise InvalidBirthDateError

    user.pseudo = pseudo
    user.first_name = first_name
    user.last_name = last_name
    user.birth_date = birth_date
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
    user.must_change_password = False

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


async def _storage_keys_to_purge(db: AsyncSession, user: User) -> list[str]:
    """Toutes les clés de stockage d'un utilisateur — risque documenté du lot `v5-rgpd`
    (« suppression incomplète : photos dans le stockage objet ») : la ligne en base disparaît
    par cascade, mais l'objet dans le stockage ne suit pas une contrainte SQL et doit être
    effacé explicitement, ici, avant que l'identifiant du propriétaire ne disparaisse."""
    keys: list[str] = []
    if user.avatar_key is not None:
        keys.append(user.avatar_key)

    collection_photos = await db.execute(
        select(CollectionItem.photo_s3_key).where(
            CollectionItem.user_id == user.id, CollectionItem.photo_s3_key.is_not(None)
        )
    )
    keys.extend(collection_photos.scalars().all())

    uploads = await db.execute(select(Upload.s3_key).where(Upload.user_id == user.id))
    keys.extend(uploads.scalars().all())

    crops = await db.execute(
        select(Detection.crop_s3_key)
        .join(Upload, Upload.id == Detection.upload_id)
        .where(Upload.user_id == user.id, Detection.crop_s3_key.is_not(None))
    )
    keys.extend(crops.scalars().all())

    exports = await db.execute(
        select(DataExport.storage_key).where(
            DataExport.user_id == user.id, DataExport.storage_key.is_not(None)
        )
    )
    keys.extend(exports.scalars().all())

    return keys


async def delete_account(
    db: AsyncSession, user: User, password: str, storage: StorageBackend
) -> None:
    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError

    for key in await _storage_keys_to_purge(db, user):
        await storage.delete(key)

    # Sessions, jetons d'e-mail, clés IA, exemplaires de collection, envois et exports suivent
    # par `ondelete="CASCADE"` (voir `pbm_api.models`) — un seul `DELETE` couvre tout le compte
    # côté base ; le stockage objet, lui, vient d'être purgé explicitement ci-dessus.
    await db.delete(user)
    await db.commit()
