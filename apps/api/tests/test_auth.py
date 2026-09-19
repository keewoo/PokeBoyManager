"""Comptes : inscription, connexion, vérification d'e-mail, mot de passe oublié.

Avant ce lot, aucune de ces routes n'existait (404 sur `/auth/*`) : chacun de ces tests
échoue sur `main.py` sans le routeur `auth` et passe une fois branché.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta

import httpx

from pbm_api.config import settings
from pbm_api.main import app as fastapi_app
from pbm_api.models import EmailToken, EmailTokenKind, Session, User
from pbm_api.security.csrf import CSRF_HEADER_NAME
from pbm_api.security.tokens import generate_opaque_token, hash_token

PASSWORD = "correct horse battery staple"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _extract_token(body: str) -> str:
    match = re.search(r"token=(\S+)", body)
    assert match, f"aucun jeton trouvé dans le corps de l'e-mail : {body!r}"
    return match.group(1)


async def _register_and_verify(
    client: httpx.AsyncClient, email: str, password: str = PASSWORD
) -> None:
    response = await client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 202, response.text
    sent = client.email_sender.sent  # type: ignore[attr-defined]
    token = _extract_token(sent[-1]["body"])
    response = await client.post("/auth/verify-email", json={"token": token})
    assert response.status_code == 200, response.text


# --- Inscription -----------------------------------------------------------------------


async def test_register_sends_verification_email(api_client: httpx.AsyncClient) -> None:
    email = _unique_email("register")
    response = await api_client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )

    assert response.status_code == 202
    sent = api_client.email_sender.sent  # type: ignore[attr-defined]
    assert len(sent) == 1
    assert sent[0]["to"] == email
    assert "vérif" in sent[0]["subject"].lower()


async def test_register_does_not_create_duplicate_or_leak_that_email_exists(
    api_client: httpx.AsyncClient, db_session
) -> None:
    email = _unique_email("dupe")
    first = await api_client.post("/auth/register", json={"email": email, "password": PASSWORD})
    second = await api_client.post("/auth/register", json={"email": email, "password": PASSWORD})

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    # Un seul e-mail envoyé : la deuxième tentative n'a pas recréé de jeton de vérification.
    assert len(api_client.email_sender.sent) == 1  # type: ignore[attr-defined]

    from sqlalchemy import func, select

    count = await db_session.scalar(
        select(func.count()).select_from(User).where(User.email == email)
    )
    assert count == 1


async def test_register_rejects_password_too_short(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(
        "/auth/register", json={"email": _unique_email("short"), "password": "short1"}
    )
    assert response.status_code == 400
    assert not api_client.email_sender.sent  # type: ignore[attr-defined]


async def test_register_rejects_compromised_password(api_client: httpx.AsyncClient) -> None:
    api_client.compromised_checker._compromised = frozenset({PASSWORD})  # type: ignore[attr-defined]
    response = await api_client.post(
        "/auth/register", json={"email": _unique_email("pwned"), "password": PASSWORD}
    )
    assert response.status_code == 400
    assert "fuite" in response.json()["detail"].lower()


# --- Vérification d'e-mail --------------------------------------------------------------


async def test_verify_email_activates_account(api_client: httpx.AsyncClient, db_session) -> None:
    email = _unique_email("verify")
    await _register_and_verify(api_client, email)

    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    assert user.email_verified_at is not None


async def test_verify_email_rejects_unknown_token(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post("/auth/verify-email", json={"token": "not-a-real-token"})
    assert response.status_code == 400


async def test_verify_email_rejects_reused_token(api_client: httpx.AsyncClient) -> None:
    email = _unique_email("reuse")
    response = await api_client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 202
    token = _extract_token(api_client.email_sender.sent[-1]["body"])  # type: ignore[attr-defined]

    first = await api_client.post("/auth/verify-email", json={"token": token})
    second = await api_client.post("/auth/verify-email", json={"token": token})

    assert first.status_code == 200
    assert second.status_code == 400
    assert "déjà" in second.json()["detail"].lower()


async def test_verify_email_rejects_expired_token(
    api_client: httpx.AsyncClient, db_session
) -> None:
    user = User(email=_unique_email("expired"), password_hash="x")
    db_session.add(user)
    await db_session.flush()

    raw_token = generate_opaque_token()
    db_session.add(
        EmailToken(
            user_id=user.id,
            kind=EmailTokenKind.verify_email,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1),
        )
    )
    await db_session.flush()

    response = await api_client.post("/auth/verify-email", json={"token": raw_token})
    assert response.status_code == 400
    assert "expiré" in response.json()["detail"].lower()


# --- Connexion ---------------------------------------------------------------------------


async def test_login_succeeds_and_sets_session_and_csrf_cookies(
    api_client: httpx.AsyncClient,
) -> None:
    email = _unique_email("login")
    await _register_and_verify(api_client, email)

    response = await api_client.post("/auth/login", json={"email": email, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["email"] == email
    assert response.json()["email_verified"] is True
    assert api_client.cookies.get(settings.session_cookie_name)
    assert api_client.cookies.get(settings.csrf_cookie_name)


async def test_login_rejects_unknown_email_and_wrong_password_identically(
    api_client: httpx.AsyncClient,
) -> None:
    email = _unique_email("wrongpw")
    await _register_and_verify(api_client, email)

    wrong_password_resp = await api_client.post(
        "/auth/login", json={"email": email, "password": "not the right password"}
    )
    unknown_email_resp = await api_client.post(
        "/auth/login", json={"email": _unique_email("ghost"), "password": PASSWORD}
    )

    assert wrong_password_resp.status_code == unknown_email_resp.status_code == 401
    assert wrong_password_resp.json() == unknown_email_resp.json()


async def test_login_rotates_session_on_each_successful_login(
    api_client: httpx.AsyncClient, db_session
) -> None:
    email = _unique_email("rotate")
    await _register_and_verify(api_client, email)

    first_login = await api_client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    first_cookie = api_client.cookies.get(settings.session_cookie_name)
    second_login = await api_client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    second_cookie = api_client.cookies.get(settings.session_cookie_name)

    assert first_login.status_code == second_login.status_code == 200
    assert first_cookie != second_cookie

    from sqlalchemy import func, select

    user_id = uuid.UUID(first_login.json()["id"])
    count = await db_session.scalar(
        select(func.count()).select_from(Session).where(Session.user_id == user_id)
    )
    assert count == 2  # sessions multiples : l'ancienne n'est pas révoquée à la connexion


async def test_login_is_rate_limited_after_five_failed_attempts(
    api_client: httpx.AsyncClient,
) -> None:
    email = _unique_email("bruteforce")
    await _register_and_verify(api_client, email)

    for _ in range(5):
        response = await api_client.post(
            "/auth/login", json={"email": email, "password": "wrong password"}
        )
        assert response.status_code == 401

    blocked = await api_client.post(
        "/auth/login", json={"email": email, "password": "wrong password"}
    )
    assert blocked.status_code == 429

    # Même avec le bon mot de passe : la limite s'applique avant la vérification du mot de passe.
    still_blocked = await api_client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert still_blocked.status_code == 429


# --- Déconnexion -------------------------------------------------------------------------


async def test_logout_requires_csrf_header(api_client: httpx.AsyncClient) -> None:
    email = _unique_email("nocsrf")
    await _register_and_verify(api_client, email)
    await api_client.post("/auth/login", json={"email": email, "password": PASSWORD})

    response = await api_client.post("/auth/logout")
    assert response.status_code == 403


async def test_logout_revokes_the_session(api_client: httpx.AsyncClient, db_session) -> None:
    email = _unique_email("logout")
    await _register_and_verify(api_client, email)
    await api_client.post("/auth/login", json={"email": email, "password": PASSWORD})
    csrf_token = api_client.cookies.get(settings.csrf_cookie_name)

    response = await api_client.post("/auth/logout", headers={CSRF_HEADER_NAME: csrf_token})
    assert response.status_code == 204

    # La session révoquée n'authentifie plus rien : rejouer /auth/logout échoue désormais.
    replay = await api_client.post("/auth/logout", headers={CSRF_HEADER_NAME: csrf_token})
    assert replay.status_code == 401


async def test_logout_only_revokes_the_caller_session_not_another_users(
    api_client: httpx.AsyncClient, db_session
) -> None:
    """Test d'accès croisé : la déconnexion de l'utilisateur A n'affecte jamais la session
    de l'utilisateur B — `current_user`/`current_session` ne dérivent que du cookie du
    client, jamais d'un identifiant fourni par le client."""
    email_a, email_b = _unique_email("cross-a"), _unique_email("cross-b")
    await _register_and_verify(api_client, email_a)
    await _register_and_verify(api_client, email_b)

    transport = httpx.ASGITransport(app=fastapi_app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_a,
        httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b,
    ):
        await client_a.post("/auth/login", json={"email": email_a, "password": PASSWORD})
        login_b = await client_b.post(
            "/auth/login", json={"email": email_b, "password": PASSWORD}
        )
        user_b_id = uuid.UUID(login_b.json()["id"])

        csrf_a = client_a.cookies.get(settings.csrf_cookie_name)
        logout_a = await client_a.post("/auth/logout", headers={CSRF_HEADER_NAME: csrf_a})
        assert logout_a.status_code == 204

        from sqlalchemy import func, select

        remaining_for_b = await db_session.scalar(
            select(func.count()).select_from(Session).where(Session.user_id == user_b_id)
        )
        assert remaining_for_b == 1

        # La session de B reste utilisable.
        csrf_b = client_b.cookies.get(settings.csrf_cookie_name)
        logout_b = await client_b.post("/auth/logout", headers={CSRF_HEADER_NAME: csrf_b})
        assert logout_b.status_code == 204


# --- Mot de passe oublié ------------------------------------------------------------------


async def test_forgot_password_gives_identical_response_known_or_unknown_email(
    api_client: httpx.AsyncClient,
) -> None:
    email = _unique_email("forgot")
    await _register_and_verify(api_client, email)
    api_client.email_sender.sent.clear()  # type: ignore[attr-defined]

    known = await api_client.post("/auth/forgot", json={"email": email})
    unknown = await api_client.post(
        "/auth/forgot", json={"email": _unique_email("ghost-forgot")}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    # Un seul e-mail envoyé : uniquement pour le compte qui existe réellement.
    assert len(api_client.email_sender.sent) == 1  # type: ignore[attr-defined]


async def test_reset_password_updates_password_and_revokes_all_sessions(
    api_client: httpx.AsyncClient, db_session
) -> None:
    email = _unique_email("reset")
    await _register_and_verify(api_client, email)
    await api_client.post("/auth/login", json={"email": email, "password": PASSWORD})
    old_csrf = api_client.cookies.get(settings.csrf_cookie_name)

    api_client.email_sender.sent.clear()  # type: ignore[attr-defined]
    await api_client.post("/auth/forgot", json={"email": email})
    reset_token = _extract_token(api_client.email_sender.sent[-1]["body"])  # type: ignore[attr-defined]

    new_password = "an entirely different passphrase"
    reset_response = await api_client.post(
        "/auth/reset", json={"token": reset_token, "password": new_password}
    )
    assert reset_response.status_code == 200

    # La session active avant la réinitialisation est révoquée.
    replay = await api_client.post("/auth/logout", headers={CSRF_HEADER_NAME: old_csrf})
    assert replay.status_code == 401

    old_login = await api_client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert old_login.status_code == 401

    new_login = await api_client.post(
        "/auth/login", json={"email": email, "password": new_password}
    )
    assert new_login.status_code == 200


async def test_reset_password_rejects_reused_token(api_client: httpx.AsyncClient) -> None:
    email = _unique_email("reset-reuse")
    await _register_and_verify(api_client, email)
    await api_client.post("/auth/forgot", json={"email": email})
    token = _extract_token(api_client.email_sender.sent[-1]["body"])  # type: ignore[attr-defined]

    first = await api_client.post(
        "/auth/reset", json={"token": token, "password": "first new password"}
    )
    second = await api_client.post(
        "/auth/reset", json={"token": token, "password": "second new password"}
    )

    assert first.status_code == 200
    assert second.status_code == 400
    assert "déjà" in second.json()["detail"].lower()


async def test_reset_password_rejects_expired_token(
    api_client: httpx.AsyncClient, db_session
) -> None:
    user = User(email=_unique_email("reset-expired"), password_hash="x")
    db_session.add(user)
    await db_session.flush()

    raw_token = generate_opaque_token()
    db_session.add(
        EmailToken(
            user_id=user.id,
            kind=EmailTokenKind.reset_password,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1),
        )
    )
    await db_session.flush()

    response = await api_client.post(
        "/auth/reset", json={"token": raw_token, "password": "some new password"}
    )
    assert response.status_code == 400
    assert "expiré" in response.json()["detail"].lower()


async def test_reset_password_rejects_short_or_compromised_password(
    api_client: httpx.AsyncClient,
) -> None:
    email = _unique_email("reset-weak")
    await _register_and_verify(api_client, email)
    await api_client.post("/auth/forgot", json={"email": email})
    token = _extract_token(api_client.email_sender.sent[-1]["body"])  # type: ignore[attr-defined]

    response = await api_client.post(
        "/auth/reset", json={"token": token, "password": "short1"}
    )
    assert response.status_code == 400
