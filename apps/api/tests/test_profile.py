"""Page profil (lot v1-profil) : pseudo, avatar, changement d'e-mail, mot de passe, sessions
actives, suppression du compte.

Avant ce lot, aucune de ces routes n'existait (404 sur `/me`, `/me/avatar`, etc.) : chacun de
ces tests échoue sur `main.py` sans le routeur `profile` et passe une fois branché.
"""

import io
import re
import uuid

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from pbm_api.config import settings
from pbm_api.main import app as fastapi_app
from pbm_api.models import Session, User
from pbm_api.routers.profile import get_storage
from pbm_api.security.csrf import CSRF_HEADER_NAME
from pbm_api.storage.local import LocalObjectStorage

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "another horse battery staple 2"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _jpeg_bytes(width: int = 600, height: int = 300) -> bytes:
    image = Image.new("RGB", (width, height), color=(10, 120, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
    """Inscrit, vérifie et connecte un utilisateur ; renvoie le jeton CSRF de sa session."""
    response = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 202, response.text
    sent = client.email_sender.sent  # type: ignore[attr-defined]
    match = re.search(r"token=(\S+)", sent[-1]["body"])
    assert match
    await client.post("/auth/verify-email", json={"token": match.group(1)})
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client.cookies.get(settings.csrf_cookie_name)


@pytest.fixture(autouse=True)
def _local_photo_storage(tmp_path):
    """Backend `local` pour toute la suite : preuve indépendante de MinIO que la route
    `/me/avatar` fonctionne aussi sur la cible retenue pour l'UAT/PROD sans Docker (voir
    `pbm_api.storage`, lot `v3-upload`). Comme `tests/test_uploads.py`."""
    storage = LocalObjectStorage(root=str(tmp_path))
    fastapi_app.dependency_overrides[get_storage] = lambda: storage
    yield storage
    fastapi_app.dependency_overrides.pop(get_storage, None)


# --- Authentification requise ------------------------------------------------------------


async def test_profile_routes_require_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/me")
    assert response.status_code == 401


# --- Pseudo --------------------------------------------------------------------------------


async def test_patch_me_sets_the_pseudo(api_client: httpx.AsyncClient) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("profil-pseudo"))

    response = await api_client.patch(
        "/me", json={"pseudo": "dresseur_jf"}, headers={CSRF_HEADER_NAME: csrf}
    )

    assert response.status_code == 200, response.text
    assert response.json()["pseudo"] == "dresseur_jf"


async def test_patch_me_rejects_a_pseudo_already_taken(api_client: httpx.AsyncClient) -> None:
    csrf_a = await _register_verify_login(api_client, _unique_email("profil-pseudo-a"))
    await api_client.patch("/me", json={"pseudo": "sacha"}, headers={CSRF_HEADER_NAME: csrf_a})

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b:
        client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        csrf_b = await _register_verify_login(client_b, _unique_email("profil-pseudo-b"))

        response = await client_b.patch(
            "/me", json={"pseudo": "sacha"}, headers={CSRF_HEADER_NAME: csrf_b}
        )
        assert response.status_code == 409


async def test_patch_me_requires_csrf_token(api_client: httpx.AsyncClient) -> None:
    await _register_verify_login(api_client, _unique_email("profil-pseudo-nocsrf"))
    response = await api_client.patch("/me", json={"pseudo": "sacha"})
    assert response.status_code == 403


# --- Avatar --------------------------------------------------------------------------------


async def test_upload_avatar_crops_it_square_and_makes_it_retrievable(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("profil-avatar"))

    upload = await api_client.post(
        "/me/avatar",
        files={"file": ("photo.jpg", _jpeg_bytes(800, 400), "image/jpeg")},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["has_avatar"] is True

    fetched = await api_client.get("/me/avatar")
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(fetched.content)) as image:
        assert image.size[0] == image.size[1]


async def test_get_avatar_returns_404_before_any_upload(api_client: httpx.AsyncClient) -> None:
    await _register_verify_login(api_client, _unique_email("profil-avatar-missing"))
    response = await api_client.get("/me/avatar")
    assert response.status_code == 404


async def test_upload_avatar_rejects_a_non_image_file(api_client: httpx.AsyncClient) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("profil-avatar-bad"))

    response = await api_client.post(
        "/me/avatar",
        files={"file": ("notes.txt", b"pas une image", "text/plain")},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 400


# --- Changement d'e-mail --------------------------------------------------------------------


async def test_change_email_sends_a_confirmation_to_the_new_address(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("profil-email"))
    new_email = _unique_email("profil-email-nouveau")

    response = await api_client.post(
        "/me/email", json={"email": new_email}, headers={CSRF_HEADER_NAME: csrf}
    )
    assert response.status_code == 200

    sent = api_client.email_sender.sent  # type: ignore[attr-defined]
    assert sent[-1]["to"] == new_email
    assert "token=" in sent[-1]["body"]


async def test_confirm_email_change_applies_the_new_address_and_notifies_the_old_one(
    api_client: httpx.AsyncClient, db_session
) -> None:
    old_email = _unique_email("profil-email-confirm-old")
    csrf = await _register_verify_login(api_client, old_email)
    new_email = _unique_email("profil-email-confirm-new")

    await api_client.post(
        "/me/email", json={"email": new_email}, headers={CSRF_HEADER_NAME: csrf}
    )
    sent = api_client.email_sender.sent  # type: ignore[attr-defined]
    match = re.search(r"token=(\S+)", sent[-1]["body"])
    assert match

    confirm = await api_client.post("/me/email/confirm", json={"token": match.group(1)})
    assert confirm.status_code == 200, confirm.text

    result = await db_session.execute(select(User).where(User.email == new_email))
    user = result.scalar_one()
    assert user.pending_email is None
    assert user.email_verified_at is not None

    notice = api_client.email_sender.sent[-1]  # type: ignore[attr-defined]
    assert notice["to"] == old_email


async def test_change_email_gives_the_same_response_whether_the_address_is_taken_or_not(
    api_client: httpx.AsyncClient,
) -> None:
    """Anti-énumération, comme `POST /auth/register` : un attaquant connecté ne doit pas
    pouvoir sonder les adresses déjà utilisées via cette route."""
    other_email = _unique_email("profil-email-taken")
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as other:
        other.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        await _register_verify_login(other, other_email)

    csrf = await _register_verify_login(api_client, _unique_email("profil-email-taken-actor"))
    emails_sent_before = len(api_client.email_sender.sent)  # type: ignore[attr-defined]

    taken = await api_client.post(
        "/me/email", json={"email": other_email}, headers={CSRF_HEADER_NAME: csrf}
    )
    free = await api_client.post(
        "/me/email",
        json={"email": _unique_email("profil-email-free")},
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert taken.status_code == free.status_code == 200
    assert taken.json() == free.json()
    # Aucun e-mail envoyé pour l'adresse déjà prise (contrairement à l'adresse libre).
    assert len(api_client.email_sender.sent) == emails_sent_before + 1  # type: ignore[attr-defined]


# --- Mot de passe ----------------------------------------------------------------------------


async def test_change_password_requires_the_current_one(api_client: httpx.AsyncClient) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("profil-pwd-wrong"))

    response = await api_client.post(
        "/me/password",
        json={"current_password": "ce-nest-pas-le-bon", "new_password": NEW_PASSWORD},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 401


async def test_change_password_updates_it_and_keeps_the_current_session(
    api_client: httpx.AsyncClient,
) -> None:
    email = _unique_email("profil-pwd-ok")
    csrf = await _register_verify_login(api_client, email)

    response = await api_client.post(
        "/me/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 200, response.text

    # La session courante reste valide (pas de déconnexion forcée).
    still_authenticated = await api_client.get("/me")
    assert still_authenticated.status_code == 200

    # L'ancien mot de passe ne fonctionne plus, le nouveau si.
    old_login = await api_client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert old_login.status_code == 401
    new_login = await api_client.post(
        "/auth/login", json={"email": email, "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200


async def test_change_password_revokes_other_sessions(
    api_client: httpx.AsyncClient, db_session
) -> None:
    email = _unique_email("profil-pwd-revoke")
    csrf = await _register_verify_login(api_client, email)

    other_login = await api_client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert other_login.status_code == 200
    # La connexion a fait tourner le cookie de session (et donc celui du CSRF, son HMAC) :
    # reprendre celui de la session désormais active, pas celui capturé avant.
    csrf = api_client.cookies.get(settings.csrf_cookie_name)
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    sessions_before = (
        await db_session.execute(select(Session).where(Session.user_id == user.id))
    ).scalars().all()
    assert len(sessions_before) == 2

    await api_client.post(
        "/me/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers={CSRF_HEADER_NAME: csrf},
    )

    sessions_after = (
        await db_session.execute(select(Session).where(Session.user_id == user.id))
    ).scalars().all()
    assert len(sessions_after) == 1


# --- Sessions actives ------------------------------------------------------------------------


async def test_list_sessions_flags_the_current_one(api_client: httpx.AsyncClient) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("profil-sessions-list"))

    response = await api_client.get("/me/sessions", headers={CSRF_HEADER_NAME: csrf})
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 1
    assert sessions[0]["current"] is True


async def test_revoke_session_removes_it(api_client: httpx.AsyncClient) -> None:
    email = _unique_email("profil-sessions-revoke")
    csrf = await _register_verify_login(api_client, email)
    await api_client.post("/auth/login", json={"email": email, "password": PASSWORD})
    csrf = api_client.cookies.get(settings.csrf_cookie_name)

    sessions = (await api_client.get("/me/sessions")).json()
    other_session = next(s for s in sessions if not s["current"])

    response = await api_client.delete(
        f"/me/sessions/{other_session['id']}", headers={CSRF_HEADER_NAME: csrf}
    )
    assert response.status_code == 204

    remaining = (await api_client.get("/me/sessions")).json()
    assert len(remaining) == 1


async def test_revoke_session_returns_404_for_an_unknown_session(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("profil-sessions-404"))
    response = await api_client.delete(
        f"/me/sessions/{uuid.uuid4()}", headers={CSRF_HEADER_NAME: csrf}
    )
    assert response.status_code == 404


# --- Suppression du compte -------------------------------------------------------------------


async def test_delete_account_requires_the_password(api_client: httpx.AsyncClient) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("profil-delete-wrong"))

    response = await api_client.request(
        "DELETE",
        "/me",
        json={"password": "ce-nest-pas-le-bon"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 401


async def test_delete_account_removes_the_user_and_clears_cookies(
    api_client: httpx.AsyncClient, db_session
) -> None:
    email = _unique_email("profil-delete-ok")
    csrf = await _register_verify_login(api_client, email)

    response = await api_client.request(
        "DELETE", "/me", json={"password": PASSWORD}, headers={CSRF_HEADER_NAME: csrf}
    )
    assert response.status_code == 204
    assert settings.session_cookie_name not in api_client.cookies

    result = await db_session.execute(select(User).where(User.email == email))
    assert result.scalar_one_or_none() is None

    still_authenticated = await api_client.get("/me")
    assert still_authenticated.status_code == 401


# --- Isolation entre utilisateurs (test d'accès croisé) ---------------------------------------


async def test_cross_user_isolation_on_sessions(
    api_client: httpx.AsyncClient, db_session
) -> None:
    """B ne voit ni ne peut révoquer les sessions de A, même en devinant leur identifiant —
    comme `test_cross_user_isolation_on_ai_keys` (lot v1-byok)."""
    csrf_a = await _register_verify_login(api_client, _unique_email("iso-sessions-a"))
    sessions_a = (await api_client.get("/me/sessions", headers={CSRF_HEADER_NAME: csrf_a})).json()
    session_a_id = sessions_a[0]["id"]

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b:
        client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        csrf_b = await _register_verify_login(client_b, _unique_email("iso-sessions-b"))

        list_b = await client_b.get("/me/sessions")
        assert session_a_id not in {s["id"] for s in list_b.json()}

        delete_b = await client_b.delete(
            f"/me/sessions/{session_a_id}", headers={CSRF_HEADER_NAME: csrf_b}
        )
        assert delete_b.status_code == 404

    still_there = await api_client.get("/me/sessions")
    assert len(still_there.json()) == 1


async def test_cross_user_isolation_on_pseudo_update(api_client: httpx.AsyncClient) -> None:
    """B ne peut pas modifier le profil de A : `PATCH /me` ne dérive jamais d'un identifiant
    fourni par le client, seulement du cookie de session de l'appelant."""
    csrf_a = await _register_verify_login(api_client, _unique_email("iso-pseudo-a"))
    await api_client.patch(
        "/me", json={"pseudo": "gardien_a"}, headers={CSRF_HEADER_NAME: csrf_a}
    )

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b:
        client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        csrf_b = await _register_verify_login(client_b, _unique_email("iso-pseudo-b"))
        await client_b.patch(
            "/me", json={"pseudo": "gardien_b"}, headers={CSRF_HEADER_NAME: csrf_b}
        )

    profile_a = await api_client.get("/me")
    assert profile_a.json()["pseudo"] == "gardien_a"
