from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth import service
from pbm_api.auth.dependencies import get_current_session, get_current_user, require_csrf
from pbm_api.auth.errors import (
    InvalidCredentialsError,
    InvalidTokenError,
    PasswordCompromisedError,
    PasswordTooShortError,
    TokenAlreadyUsedError,
    TokenExpiredError,
)
from pbm_api.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
    VerifyEmailRequest,
)
from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.email import EmailSender, get_email_sender
from pbm_api.models import Session, User
from pbm_api.security.compromised import CompromisedPasswordChecker, get_compromised_checker
from pbm_api.security.csrf import compute_csrf_token
from pbm_api.security.rate_limit import RateLimiter, get_login_rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_REGISTER_MESSAGE = (
    "Si cette adresse n'est pas déjà utilisée, un e-mail de vérification vient d'être envoyé."
)
GENERIC_FORGOT_MESSAGE = (
    "Si un compte existe pour cette adresse, un e-mail de réinitialisation vient d'être envoyé."
)
INVALID_CREDENTIALS_MESSAGE = "E-mail ou mot de passe incorrect."
TOO_MANY_ATTEMPTS_MESSAGE = "Trop de tentatives. Réessayez plus tard."
PASSWORD_TOO_SHORT_MESSAGE = "Le mot de passe doit contenir au moins 10 caractères."
PASSWORD_COMPROMISED_MESSAGE = (
    "Ce mot de passe apparaît dans une fuite de données connue : choisissez-en un autre."
)
INVALID_TOKEN_MESSAGE = "Jeton invalide."
TOKEN_EXPIRED_MESSAGE = "Ce lien a expiré."
TOKEN_ALREADY_USED_MESSAGE = "Ce lien a déjà été utilisé."


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_auth_cookies(response: Response, raw_session_token: str) -> None:
    max_age = settings.session_ttl_days * 24 * 3600
    response.set_cookie(
        settings.session_cookie_name,
        raw_session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=max_age,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        compute_csrf_token(raw_session_token),
        httponly=False,
        secure=True,
        samesite="lax",
        max_age=max_age,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name)
    response.delete_cookie(settings.csrf_cookie_name)


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_session),
    compromised_checker: CompromisedPasswordChecker = Depends(get_compromised_checker),
    email_sender: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    try:
        await service.register_user(
            db, payload.email, payload.password, compromised_checker, email_sender
        )
    except PasswordTooShortError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, PASSWORD_TOO_SHORT_MESSAGE) from None
    except PasswordCompromisedError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, PASSWORD_COMPROMISED_MESSAGE) from None
    return MessageResponse(message=GENERIC_REGISTER_MESSAGE)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    payload: VerifyEmailRequest, db: AsyncSession = Depends(get_session)
) -> MessageResponse:
    try:
        await service.verify_email(db, payload.token)
    except InvalidTokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_TOKEN_MESSAGE) from None
    except TokenExpiredError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, TOKEN_EXPIRED_MESSAGE) from None
    except TokenAlreadyUsedError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, TOKEN_ALREADY_USED_MESSAGE) from None
    return MessageResponse(message="Adresse e-mail vérifiée.")


@router.post("/login", response_model=UserResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
    limiter: RateLimiter = Depends(get_login_rate_limiter),
) -> UserResponse:
    normalized_email = service.normalize_email(payload.email)
    ip_address = _client_ip(request)

    allowed_by_email = await limiter.hit("login:email", normalized_email)
    allowed_by_ip = await limiter.hit("login:ip", ip_address)
    if not allowed_by_email or not allowed_by_ip:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_ATTEMPTS_MESSAGE)

    try:
        user, raw_session_token = await service.authenticate_and_create_session(
            db,
            payload.email,
            payload.password,
            ip_address,
            request.headers.get("user-agent"),
        )
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS_MESSAGE) from None

    await limiter.reset("login:email", normalized_email)
    await limiter.reset("login:ip", ip_address)

    _set_auth_cookies(response, raw_session_token)
    return UserResponse(
        id=str(user.id), email=user.email, email_verified=user.email_verified_at is not None
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    current_session: tuple[Session, str] = Depends(get_current_session),
    _csrf: None = Depends(require_csrf),
) -> None:
    session_row, _ = current_session
    await service.logout(db, session_row)
    _clear_auth_cookies(response)


@router.post("/forgot", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
    email_sender: EmailSender = Depends(get_email_sender),
    limiter: RateLimiter = Depends(get_login_rate_limiter),
) -> MessageResponse:
    normalized_email = service.normalize_email(payload.email)
    ip_address = _client_ip(request)

    allowed_by_email = await limiter.hit("forgot:email", normalized_email)
    allowed_by_ip = await limiter.hit("forgot:ip", ip_address)
    if not allowed_by_email or not allowed_by_ip:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY_ATTEMPTS_MESSAGE)

    await service.request_password_reset(db, payload.email, email_sender)
    return MessageResponse(message=GENERIC_FORGOT_MESSAGE)


@router.post("/reset", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_session),
    compromised_checker: CompromisedPasswordChecker = Depends(get_compromised_checker),
) -> MessageResponse:
    try:
        await service.reset_password(db, payload.token, payload.password, compromised_checker)
    except PasswordTooShortError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, PASSWORD_TOO_SHORT_MESSAGE) from None
    except PasswordCompromisedError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, PASSWORD_COMPROMISED_MESSAGE) from None
    except InvalidTokenError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_TOKEN_MESSAGE) from None
    except TokenExpiredError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, TOKEN_EXPIRED_MESSAGE) from None
    except TokenAlreadyUsedError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, TOKEN_ALREADY_USED_MESSAGE) from None
    return MessageResponse(message="Mot de passe mis à jour.")
