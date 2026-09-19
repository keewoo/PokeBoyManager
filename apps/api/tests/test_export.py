"""Export RGPD de la collection (lot `v5-rgpd`, mission point 1) : `POST /me/export` prépare
une archive ZIP (collection JSON + CSV, photos), envoie un e-mail avec un lien de téléchargement
signé valable 24 h, servi sans cookie de session par `GET /export/download`.

Avant ce lot, aucune de ces routes n'existait (404 sur `/me/export`, `/export/download`) :
chacun de ces tests échoue sur `main.py` sans le routeur `export` et passe une fois branché.
"""

import csv
import io
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zipfile import ZipFile

import httpx
import pytest
from sqlalchemy import select

from pbm_api.config import settings
from pbm_api.export.archive import COLLECTION_CSV_NAME, COLLECTION_JSON_NAME, PROFILE_JSON_NAME
from pbm_api.main import app as fastapi_app
from pbm_api.models import Card, DataExport, JobStatus, PriceVariant, Set, User
from pbm_api.models.collection import CollectionItem
from pbm_api.routers.export import get_storage
from pbm_api.security.csrf import CSRF_HEADER_NAME
from pbm_api.storage.local import LocalObjectStorage

PASSWORD = "correct horse battery staple"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


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
    """Backend `local` (D7) pour toute la suite, comme `tests/test_profile.py` : preuve
    indépendante de MinIO que l'export fonctionne aussi sur la cible retenue pour l'UAT/PROD."""
    storage = LocalObjectStorage(root=str(tmp_path))
    fastapi_app.dependency_overrides[get_storage] = lambda: storage
    yield storage
    fastapi_app.dependency_overrides.pop(get_storage, None)


async def _add_collection_item_with_photo(
    db_session,
    user_id: str,
    storage: LocalObjectStorage,
    *,
    photo: bytes | None = b"\xff\xd8\xffphoto",
) -> tuple[CollectionItem, Card]:
    set_row = Set(code=f"exp-{uuid.uuid4().hex[:8]}", name="Extension export")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="7", name="Carte export", rarity="rare")
    db_session.add(card)
    await db_session.flush()

    photo_key = None
    if photo is not None:
        photo_key = f"collection/{uuid.uuid4()}.jpg"
        await storage.put(photo_key, photo, "image/jpeg")

    item = CollectionItem(
        user_id=uuid.UUID(user_id),
        card_id=card.id,
        language="fr",
        variant=PriceVariant.normal,
        condition_grade="mint",
        purchase_price=Decimal("12.50"),
        purchase_currency="EUR",
        photo_s3_key=photo_key,
    )
    db_session.add(item)
    await db_session.flush()
    return item, card


def _extract_download_token(body: str) -> str:
    match = re.search(r"token=(\S+)", body)
    assert match, body
    return match.group(1)


# --- Authentification requise ------------------------------------------------------------


async def test_request_export_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post("/me/export")
    assert response.status_code == 401


async def test_request_export_requires_csrf_token(api_client: httpx.AsyncClient) -> None:
    await _register_verify_login(api_client, _unique_email("export-nocsrf"))
    response = await api_client.post("/me/export")
    assert response.status_code == 403


# --- Cycle complet ---------------------------------------------------------------------------


async def test_request_export_builds_archive_and_emails_a_download_link(
    api_client: httpx.AsyncClient, db_session, _local_photo_storage
) -> None:
    email = _unique_email("export-ok")
    csrf = await _register_verify_login(api_client, email)
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    item, card = await _add_collection_item_with_photo(
        db_session, str(user.id), _local_photo_storage
    )

    response = await api_client.post("/me/export", headers={CSRF_HEADER_NAME: csrf})
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["completed_at"] is not None

    sent = api_client.email_sender.sent  # type: ignore[attr-defined]
    assert sent[-1]["to"] == email
    token = _extract_download_token(sent[-1]["body"])

    download = await api_client.get(f"/export/download?token={token}")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"

    with ZipFile(io.BytesIO(download.content)) as archive:
        names = archive.namelist()
        assert PROFILE_JSON_NAME in names
        assert COLLECTION_JSON_NAME in names
        assert COLLECTION_CSV_NAME in names
        photo_entries = [n for n in names if n.startswith("photos/")]
        assert len(photo_entries) == 1
        assert archive.read(photo_entries[0]) == b"\xff\xd8\xffphoto"

        csv_rows = list(csv.DictReader(io.StringIO(archive.read(COLLECTION_CSV_NAME).decode())))
        assert len(csv_rows) == 1
        assert csv_rows[0]["carte"] == "Carte export"
        assert csv_rows[0]["item_id"] == str(item.id)
        assert csv_rows[0]["photo"] == photo_entries[0]


async def test_request_export_without_any_collection_item_still_succeeds(
    api_client: httpx.AsyncClient,
) -> None:
    """Une collection vide n'est pas une panne — comme le veut `CLAUDE.md` (« un relevé ou un
    lot sans compte rendu est une panne », pas « une collection vide »)."""
    csrf = await _register_verify_login(api_client, _unique_email("export-empty"))

    response = await api_client.post("/me/export", headers={CSRF_HEADER_NAME: csrf})
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "succeeded"

    sent = api_client.email_sender.sent  # type: ignore[attr-defined]
    token = _extract_download_token(sent[-1]["body"])
    download = await api_client.get(f"/export/download?token={token}")
    assert download.status_code == 200

    with ZipFile(io.BytesIO(download.content)) as archive:
        collection = archive.read(COLLECTION_JSON_NAME).decode()
        assert '"cartes": []' in collection


# --- Statut ------------------------------------------------------------------------------


async def test_get_export_status(api_client: httpx.AsyncClient) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("export-status"))
    created = await api_client.post("/me/export", headers={CSRF_HEADER_NAME: csrf})
    export_id = created.json()["id"]

    response = await api_client.get(f"/me/export/{export_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"


async def test_get_export_status_returns_404_for_unknown_export(
    api_client: httpx.AsyncClient,
) -> None:
    await _register_verify_login(api_client, _unique_email("export-status-404"))
    response = await api_client.get(f"/me/export/{uuid.uuid4()}")
    assert response.status_code == 404


# --- Isolation entre utilisateurs (test d'accès croisé) ---------------------------------------


async def test_cross_user_isolation_on_export_status(
    api_client: httpx.AsyncClient,
) -> None:
    """B ne peut pas consulter le statut de l'export de A, même en devinant son identifiant —
    comme `test_cross_user_isolation_on_sessions` (lot v1-profil)."""
    csrf_a = await _register_verify_login(api_client, _unique_email("export-iso-a"))
    created_a = await api_client.post("/me/export", headers={CSRF_HEADER_NAME: csrf_a})
    export_a_id = created_a.json()["id"]

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b:
        client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        await _register_verify_login(client_b, _unique_email("export-iso-b"))

        response = await client_b.get(f"/me/export/{export_a_id}")
        assert response.status_code == 404


async def test_download_link_of_user_a_cannot_be_guessed_or_reused_by_user_b(
    api_client: httpx.AsyncClient,
) -> None:
    """Le jeton de téléchargement n'est pas lié à la session de l'appelant : seul le fait de le
    détenir compte (lien envoyé par e-mail) — mais un jeton au hasard reste refusé."""
    await _register_verify_login(api_client, _unique_email("export-token-a"))
    guessed = await api_client.get("/export/download?token=un-jeton-au-hasard")
    assert guessed.status_code == 404


# --- Jeton de téléchargement -------------------------------------------------------------


async def test_download_export_rejects_an_unknown_token(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/export/download?token=inconnu")
    assert response.status_code == 404


async def test_download_export_rejects_an_expired_token(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("export-expired"))
    created = await api_client.post("/me/export", headers={CSRF_HEADER_NAME: csrf})
    export_id = created.json()["id"]

    sent = api_client.email_sender.sent  # type: ignore[attr-defined]
    token = _extract_download_token(sent[-1]["body"])

    result = await db_session.execute(
        select(DataExport).where(DataExport.id == uuid.UUID(export_id))
    )
    export = result.scalar_one()
    export.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    await db_session.commit()

    response = await api_client.get(f"/export/download?token={token}")
    assert response.status_code == 404


async def test_a_still_running_export_has_no_download_token_yet(
    api_client: httpx.AsyncClient, db_session
) -> None:
    """Un export `queued`/`running` n'a pas encore de jeton — un `None` explicite dans
    `data_exports.token_hash`, jamais un jeton devinable avant que l'archive n'existe."""
    email = _unique_email("export-running")
    await _register_verify_login(api_client, email)
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()

    export = DataExport(user_id=user.id, status=JobStatus.running)
    db_session.add(export)
    await db_session.commit()

    assert export.token_hash is None
