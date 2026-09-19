"""Identité du compte (lot `v1-identite`) : prénom, nom, date de naissance, acceptation des
conditions, commande d'administration `create-user`.

Avant ce lot, `POST /auth/register` n'exigeait ni nom, ni date de naissance, ni acceptation des
conditions ; chacun de ces tests échoue sans les validations ajoutées ici et passe une fois
branché.
"""

import os
import re
import subprocess
import uuid
from datetime import date, timedelta

import httpx
from sqlalchemy import select

from pbm_api.config import settings
from pbm_api.legal import CURRENT_TERMS_VERSION, MINIMUM_AGE_YEARS
from pbm_api.main import app as fastapi_app
from pbm_api.models import User
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v3_detection_test",
)


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _birth_date_for_age(years: int) -> str:
    """Date de naissance donnant très exactement `years` années révolues aujourd'hui."""
    today = date.today()
    return date(today.year - years, today.month, today.day).isoformat()


def _register_payload(email: str, **overrides: object) -> dict:
    payload = {
        "email": email,
        "password": PASSWORD,
        "last_name": "Dresseur",
        "birth_date": _birth_date_for_age(20),
        "accept_terms": True,
    }
    payload.update(overrides)
    return payload


# --- Inscription : conditions et âge -------------------------------------------------------


async def test_register_rejects_missing_terms_acceptance(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(
        "/auth/register", json=_register_payload(_unique_email("noterms"), accept_terms=False)
    )
    assert response.status_code == 400
    assert "condition" in response.json()["detail"].lower()
    assert not api_client.email_sender.sent  # type: ignore[attr-defined]


async def test_register_rejects_a_birth_date_in_the_future(
    api_client: httpx.AsyncClient,
) -> None:
    future = (date.today() + timedelta(days=1)).isoformat()
    response = await api_client.post(
        "/auth/register", json=_register_payload(_unique_email("futuredob"), birth_date=future)
    )
    assert response.status_code == 400
    assert not api_client.email_sender.sent  # type: ignore[attr-defined]


async def test_register_rejects_registration_under_the_minimum_age(
    api_client: httpx.AsyncClient,
) -> None:
    underage = _birth_date_for_age(MINIMUM_AGE_YEARS - 1)
    response = await api_client.post(
        "/auth/register", json=_register_payload(_unique_email("underage"), birth_date=underage)
    )
    assert response.status_code == 400
    assert "15" in response.json()["detail"]
    assert not api_client.email_sender.sent  # type: ignore[attr-defined]


async def test_register_accepts_exactly_the_minimum_age(api_client: httpx.AsyncClient) -> None:
    exactly_minimum = _birth_date_for_age(MINIMUM_AGE_YEARS)
    response = await api_client.post(
        "/auth/register",
        json=_register_payload(_unique_email("exactly15"), birth_date=exactly_minimum),
    )
    assert response.status_code == 202, response.text


async def test_register_stores_identity_fields_and_terms_acceptance(
    api_client: httpx.AsyncClient, db_session
) -> None:
    email = _unique_email("identity")
    response = await api_client.post(
        "/auth/register",
        json=_register_payload(email, first_name="Sacha"),
    )
    assert response.status_code == 202, response.text

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    assert user.first_name == "Sacha"
    assert user.last_name == "Dresseur"
    assert user.birth_date.isoformat() == _birth_date_for_age(20)
    assert user.terms_version == CURRENT_TERMS_VERSION
    assert user.terms_accepted_at is not None
    assert user.must_change_password is False


async def test_register_first_name_is_optional(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(
        "/auth/register", json=_register_payload(_unique_email("nofirstname"))
    )
    assert response.status_code == 202, response.text


# --- PATCH /me : édition de l'identité ------------------------------------------------------


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
    response = await client.post("/auth/register", json=_register_payload(email))
    assert response.status_code == 202, response.text
    sent = client.email_sender.sent  # type: ignore[attr-defined]
    match = re.search(r"token=(\S+)", sent[-1]["body"])
    assert match
    await client.post("/auth/verify-email", json={"token": match.group(1)})
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client.cookies.get(settings.csrf_cookie_name)


async def test_patch_me_updates_first_last_name_and_birth_date(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("patch-identity"))
    new_birth_date = _birth_date_for_age(25)

    response = await api_client.patch(
        "/me",
        json={
            "pseudo": "sacha_ketchum",
            "first_name": "Sacha",
            "last_name": "Ketchum",
            "birth_date": new_birth_date,
        },
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["first_name"] == "Sacha"
    assert body["last_name"] == "Ketchum"
    assert body["birth_date"] == new_birth_date


async def test_patch_me_rejects_a_birth_date_in_the_future(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("patch-future-dob"))
    future = (date.today() + timedelta(days=1)).isoformat()

    response = await api_client.patch(
        "/me",
        json={"pseudo": "voyageur", "last_name": "Dresseur", "birth_date": future},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 400


async def test_cross_user_isolation_on_identity_update(api_client: httpx.AsyncClient) -> None:
    """B ne peut pas modifier l'identité de A : comme `test_profile.
    test_cross_user_isolation_on_pseudo_update`, `PATCH /me` ne dérive jamais d'un identifiant
    fourni par le client."""
    csrf_a = await _register_verify_login(api_client, _unique_email("iso-identity-a"))
    await api_client.patch(
        "/me",
        json={"pseudo": "gardien_a", "last_name": "Gardien A", "birth_date": "1990-01-01"},
        headers={CSRF_HEADER_NAME: csrf_a},
    )

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b:
        client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        csrf_b = await _register_verify_login(client_b, _unique_email("iso-identity-b"))
        await client_b.patch(
            "/me",
            json={"pseudo": "gardien_b", "last_name": "Gardien B", "birth_date": "1991-02-02"},
            headers={CSRF_HEADER_NAME: csrf_b},
        )

    profile_a = await api_client.get("/me")
    assert profile_a.json()["last_name"] == "Gardien A"


# --- Changement de mot de passe forcé --------------------------------------------------------


async def test_login_reports_must_change_password(api_client: httpx.AsyncClient) -> None:
    email = _unique_email("must-change")
    await _register_verify_login(api_client, email)

    login = await api_client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    assert login.json()["must_change_password"] is False


async def test_change_password_clears_must_change_password(
    api_client: httpx.AsyncClient, db_session
) -> None:
    email = _unique_email("clears-must-change")
    csrf = await _register_verify_login(api_client, email)

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.must_change_password = True
    await db_session.commit()

    response = await api_client.post(
        "/me/password",
        json={"current_password": PASSWORD, "new_password": "un tout autre mot de passe"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 200, response.text

    await db_session.refresh(user)
    assert user.must_change_password is False


# --- Commande d'administration `create-user` ------------------------------------------------


def _run_admin_create_user(
    *extra_args: str, stdin_password: str | None = None
) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    return subprocess.run(
        ["uv", "run", "python", "-m", "pbm_api.admin", "create-user", *extra_args],
        input=stdin_password,
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        timeout=60,
    )


async def test_admin_create_user_creates_a_verified_account(db_session) -> None:
    email = _unique_email("admin-created")
    result = _run_admin_create_user(
        "--email",
        email,
        "--pseudo",
        f"aymeric-{uuid.uuid4().hex[:6]}",
        "--first-name",
        "Aymeric",
        "--last-name",
        "Fontaine",
        "--birth-date",
        "1990-05-12",
        "--accept-terms",
        "--password-stdin",
        "--must-change-password",
        stdin_password="un-mot-de-passe-temporaire\n",
    )
    assert result.returncode == 0, result.stderr
    assert "un-mot-de-passe-temporaire" not in result.stdout

    row = await db_session.execute(select(User).where(User.email == email))
    user = row.scalar_one()
    assert user.email_verified_at is not None
    assert user.must_change_password is True
    assert user.first_name == "Aymeric"
    assert user.last_name == "Fontaine"
    assert user.terms_version == CURRENT_TERMS_VERSION


async def test_admin_create_user_generates_a_password_when_not_given_on_stdin(
    db_session,
) -> None:
    email = _unique_email("admin-generated-pw")
    result = _run_admin_create_user(
        "--email",
        email,
        "--pseudo",
        f"genere-{uuid.uuid4().hex[:6]}",
        "--last-name",
        "Genere",
        "--birth-date",
        "1990-05-12",
        "--accept-terms",
    )
    assert result.returncode == 0, result.stderr
    assert "Mot de passe généré" in result.stdout

    row = await db_session.execute(select(User).where(User.email == email))
    assert row.scalar_one_or_none() is not None


async def test_admin_create_user_requires_accepting_terms() -> None:
    result = _run_admin_create_user(
        "--email",
        _unique_email("admin-noterms"),
        "--pseudo",
        f"sans-conditions-{uuid.uuid4().hex[:6]}",
        "--last-name",
        "X",
        "--birth-date",
        "1990-05-12",
    )
    assert result.returncode == 1
    assert "accept-terms" in result.stderr


async def test_admin_create_user_bypasses_the_minimum_age_for_a_minor(db_session) -> None:
    """Consentement du parent porté par JF (mission `v1-identite` § Risques) : contrairement à
    `POST /auth/register`, la commande d'administration accepte un compte de moins de 15 ans."""
    email = _unique_email("admin-minor")
    minor_birth_date = _birth_date_for_age(10)
    result = _run_admin_create_user(
        "--email",
        email,
        "--pseudo",
        f"mineur-{uuid.uuid4().hex[:6]}",
        "--last-name",
        "Mineur",
        "--birth-date",
        minor_birth_date,
        "--accept-terms",
        "--password-stdin",
        stdin_password="un-mot-de-passe-du-parent\n",
    )
    assert result.returncode == 0, result.stderr

    row = await db_session.execute(select(User).where(User.email == email))
    assert row.scalar_one_or_none() is not None
