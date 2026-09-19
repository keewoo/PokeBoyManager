"""Page profil (lot v1-profil) : identité (pseudo, avatar, e-mail), sécurité (mot de passe,
sessions actives) et suppression du compte. Comme `pbm_api.routers.ai_keys` : l'utilisateur
vient toujours du cookie de session (`get_current_user`), jamais d'un identifiant fourni par
le client ; toute écriture exige le jeton CSRF (`require_csrf`)."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import Response as RawResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.errors import UnsupportedImageFormatError
from pbm_api.auth.dependencies import get_current_session, get_current_user, require_csrf
from pbm_api.auth.errors import (
    InvalidBirthDateError,
    InvalidCredentialsError,
    InvalidTokenError,
    PasswordCompromisedError,
    PasswordTooShortError,
    TokenAlreadyUsedError,
    TokenExpiredError,
)
from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.email import EmailSender, get_email_sender
from pbm_api.models import Session, User
from pbm_api.profile import service
from pbm_api.profile.avatar import AvatarTooLargeError
from pbm_api.profile.errors import (
    AvatarNotFoundError,
    PseudoAlreadyTakenError,
    SessionNotFoundError,
)
from pbm_api.profile.schemas import (
    ChangeEmailRequest,
    ChangePasswordRequest,
    ConfirmEmailChangeRequest,
    DeleteAccountRequest,
    MessageResponse,
    ProfileResponse,
    SessionResponse,
    UpdateProfileRequest,
)
from pbm_api.security.compromised import CompromisedPasswordChecker, get_compromised_checker
from pbm_api.storage import StorageBackend, build_storage

router = APIRouter(prefix="/me", tags=["profile"])

# Même stockage que `pbm_api.routers.uploads` (photos de cartes) : un seul répertoire/bucket
# `STORAGE_BACKEND`, l'avatar utilisateur n'a pas de préoccupation de stockage distincte.
_storage = build_storage()


def get_storage() -> StorageBackend:
    return _storage


PSEUDO_TAKEN_MESSAGE = "Ce pseudo est déjà utilisé."
INVALID_BIRTH_DATE_MESSAGE = "Date de naissance invalide."
UNSUPPORTED_IMAGE_MESSAGE = "Format d'image non reconnu (JPEG ou PNG attendus)."
AVATAR_TOO_LARGE_MESSAGE = "Photo trop volumineuse (5 Mo maximum)."
AVATAR_NOT_FOUND_MESSAGE = "Aucun avatar enregistré."
GENERIC_EMAIL_CHANGE_MESSAGE = (
    "Si cette adresse n'est pas déjà utilisée par un autre compte, un e-mail de confirmation "
    "vient d'être envoyé."
)
INVALID_TOKEN_MESSAGE = "Jeton invalide."
TOKEN_EXPIRED_MESSAGE = "Ce lien a expiré."
TOKEN_ALREADY_USED_MESSAGE = "Ce lien a déjà été utilisé."
INVALID_CURRENT_PASSWORD_MESSAGE = "Mot de passe actuel incorrect."
PASSWORD_TOO_SHORT_MESSAGE = "Le mot de passe doit contenir au moins 10 caractères."
PASSWORD_COMPROMISED_MESSAGE = (
    "Ce mot de passe apparaît dans une fuite de données connue : choisissez-en un autre."
)
SESSION_NOT_FOUND_MESSAGE = "Session introuvable."
INVALID_PASSWORD_MESSAGE = "Mot de passe incorrect."


def _to_profile_response(user: User) -> ProfileResponse:
    return ProfileResponse(
        id=str(user.id),
        email=user.email,
        email_verified=user.email_verified_at is not None,
        pending_email=user.pending_email,
        pseudo=user.pseudo,
        has_avatar=user.avatar_key is not None,
        first_name=user.first_name,
        last_name=user.last_name,
        birth_date=user.birth_date,
    )


def _to_session_response(session_row: Session, current_session_id: uuid.UUID) -> SessionResponse:
    return SessionResponse(
        id=str(session_row.id),
        user_agent=session_row.user_agent,
        ip_address=session_row.ip_address,
        created_at=session_row.created_at,
        current=session_row.id == current_session_id,
    )


@router.get("", response_model=ProfileResponse)
async def get_profile(current_user: User = Depends(get_current_user)) -> ProfileResponse:
    return _to_profile_response(current_user)


@router.patch("", response_model=ProfileResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> ProfileResponse:
    try:
        user = await service.update_identity(
            db,
            current_user,
            payload.pseudo,
            payload.first_name,
            payload.last_name,
            payload.birth_date,
        )
    except PseudoAlreadyTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, PSEUDO_TAKEN_MESSAGE) from None
    except InvalidBirthDateError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_BIRTH_DATE_MESSAGE) from None
    return _to_profile_response(user)


@router.post("/avatar", response_model=ProfileResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage),
    _csrf: None = Depends(require_csrf),
) -> ProfileResponse:
    data = await file.read()
    try:
        user = await service.set_avatar(db, current_user, storage, data)
    except UnsupportedImageFormatError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, UNSUPPORTED_IMAGE_MESSAGE) from None
    except AvatarTooLargeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, AVATAR_TOO_LARGE_MESSAGE) from None
    return _to_profile_response(user)


@router.get("/avatar")
async def get_avatar(
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage),
) -> Response:
    try:
        data = await service.get_avatar_bytes(current_user, storage)
    except AvatarNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, AVATAR_NOT_FOUND_MESSAGE) from None
    return RawResponse(content=data, media_type="image/jpeg")


@router.post("/email", response_model=MessageResponse)
async def change_email(
    payload: ChangeEmailRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    email_sender: EmailSender = Depends(get_email_sender),
    _csrf: None = Depends(require_csrf),
) -> MessageResponse:
    await service.request_email_change(db, current_user, payload.email, email_sender)
    return MessageResponse(message=GENERIC_EMAIL_CHANGE_MESSAGE)


@router.post("/email/confirm", response_model=MessageResponse)
async def confirm_email_change(
    payload: ConfirmEmailChangeRequest,
    db: AsyncSession = Depends(get_session),
    email_sender: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    try:
        await service.confirm_email_change(db, payload.token, email_sender)
    except InvalidTokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_TOKEN_MESSAGE) from None
    except TokenExpiredError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, TOKEN_EXPIRED_MESSAGE) from None
    except TokenAlreadyUsedError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, TOKEN_ALREADY_USED_MESSAGE) from None
    return MessageResponse(message="Adresse e-mail mise à jour.")


@router.post("/password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    current_session: tuple[Session, str] = Depends(get_current_session),
    compromised_checker: CompromisedPasswordChecker = Depends(get_compromised_checker),
    _csrf: None = Depends(require_csrf),
) -> MessageResponse:
    session_row, _ = current_session
    try:
        await service.change_password(
            db,
            current_user,
            payload.current_password,
            payload.new_password,
            compromised_checker,
            session_row,
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, INVALID_CURRENT_PASSWORD_MESSAGE
        ) from None
    except PasswordTooShortError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, PASSWORD_TOO_SHORT_MESSAGE) from None
    except PasswordCompromisedError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, PASSWORD_COMPROMISED_MESSAGE) from None
    return MessageResponse(message="Mot de passe mis à jour.")


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    current_session: tuple[Session, str] = Depends(get_current_session),
) -> list[SessionResponse]:
    session_row, _ = current_session
    sessions = await service.list_sessions(db, current_user)
    return [_to_session_response(s, session_row.id) for s in sessions]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> None:
    try:
        await service.revoke_session(db, current_user, session_id)
    except SessionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, SESSION_NOT_FOUND_MESSAGE) from None


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    payload: DeleteAccountRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage),
    _csrf: None = Depends(require_csrf),
) -> None:
    try:
        await service.delete_account(db, current_user, payload.password, storage)
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_PASSWORD_MESSAGE) from None
    response.delete_cookie(settings.session_cookie_name)
    response.delete_cookie(settings.csrf_cookie_name)
