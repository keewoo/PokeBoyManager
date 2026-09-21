"""Export RGPD de la collection (lot `v5-rgpd`, mission point 1) : `POST /me/export` crée un
`DataExport` et l'enfile vers le worker arq (comme `POST /uploads/{id}/complete` pour
`detect_cards_task`, mission `v3-detection`) ; le worker construit l'archive ZIP (collection
JSON + CSV, photos), envoie un e-mail avec un lien de téléchargement signé valable 24 h, servi
sans cookie de session par `GET /export/download`.

Le worker arq n'est pas démarré pendant les tests (comme pour `detect_cards_task`,
`tests/test_detections_routes.py`) : `export.service.run_export` est appelé directement pour
simuler ce que ferait `pbm_api.worker.export_user_data_task`.

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
from pbm_api.export.service import run_export
from pbm_api.main import app as fastapi_app
from pbm_api.models import Card, DataExport, PriceVariant, Set, User
from pbm_api.models.collection import CollectionItem
from pbm_api.routers.export import get_storage
from pbm_api.security.csrf import CSRF_HEADER_NAME
from pbm_api.storage.local import LocalObjectStorage

PASSWORD = "correct horse battery staple"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
    """Inscrit, vérifie et connecte un utilisateur ; renvoie le jeton CSRF de sa session."""
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "last_name": "Dresseur",
            "birth_date": "2000-01-01",
            "accept_terms": True,
        },
    )
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


async def _request_and_simulate_worker(
    api_client: httpx.AsyncClient, db_session, storage: LocalObjectStorage, csrf: str
) -> DataExport:
    """`POST /me/export` enfile un job réel (Redis, comme `detect_cards_task`) que rien ne
    consomme en tests : on simule directement ce que ferait `export_user_data_task`."""
    created = await api_client.post("/me/export", headers={CSRF_HEADER_NAME: csrf})
    assert created.status_code == 202, created.text
    assert created.json()["status"] == "queued"

    export_id = uuid.UUID(created.json()["id"])
    result = await db_session.execute(select(DataExport).where(DataExport.id == export_id))
    export = result.scalar_one()
    result = await db_session.execute(select(User).where(User.id == export.user_id))
    user = result.scalar_one()

    return await run_export(db_session, storage, api_client.email_sender, user, export)  # type: ignore[attr-defined]


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


async def test_request_export_returns_a_queued_job_immediately(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("export-queued"))
    response = await api_client.post("/me/export", headers={CSRF_HEADER_NAME: csrf})
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["completed_at"] is None


# --- Cycle complet (worker simulé) --------------------------------------------------------


async def test_export_builds_archive_and_emails_a_download_link(
    api_client: httpx.AsyncClient, db_session, _local_photo_storage
) -> None:
    email = _unique_email("export-ok")
    csrf = await _register_verify_login(api_client, email)
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    item, card = await _add_collection_item_with_photo(
        db_session, str(user.id), _local_photo_storage
    )

    export = await _request_and_simulate_worker(api_client, db_session, _local_photo_storage, csrf)
    assert export.status.value == "succeeded"
    assert export.completed_at is not None

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


async def test_export_without_any_collection_item_still_succeeds(
    api_client: httpx.AsyncClient, db_session, _local_photo_storage
) -> None:
    """Une collection vide n'est pas une panne — comme le veut `CLAUDE.md` (« un relevé ou un
    lot sans compte rendu est une panne », pas « une collection vide »)."""
    csrf = await _register_verify_login(api_client, _unique_email("export-empty"))

    export = await _request_and_simulate_worker(api_client, db_session, _local_photo_storage, csrf)
    assert export.status.value == "succeeded"

    sent = api_client.email_sender.sent  # type: ignore[attr-defined]
    token = _extract_download_token(sent[-1]["body"])
    download = await api_client.get(f"/export/download?token={token}")
    assert download.status_code == 200

    with ZipFile(io.BytesIO(download.content)) as archive:
        collection = archive.read(COLLECTION_JSON_NAME).decode()
        assert '"cartes": []' in collection


# --- Statut ------------------------------------------------------------------------------


async def test_get_export_status_reflects_worker_completion(
    api_client: httpx.AsyncClient, db_session, _local_photo_storage
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("export-status"))
    export = await _request_and_simulate_worker(api_client, db_session, _local_photo_storage, csrf)

    response = await api_client.get(f"/me/export/{export.id}")
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


# --- Jeton de téléchargement -------------------------------------------------------------


async def test_download_export_rejects_an_unknown_token(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/export/download?token=inconnu")
    assert response.status_code == 404


async def test_download_export_rejects_an_expired_token(
    api_client: httpx.AsyncClient, db_session, _local_photo_storage
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("export-expired"))
    export = await _request_and_simulate_worker(api_client, db_session, _local_photo_storage, csrf)

    sent = api_client.email_sender.sent  # type: ignore[attr-defined]
    token = _extract_download_token(sent[-1]["body"])

    export.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    await db_session.commit()

    response = await api_client.get(f"/export/download?token={token}")
    assert response.status_code == 404


# --- Export CSV synchrone (mission `v6-import-export`) -----------------------------------


async def test_export_csv_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/me/export/collection.csv")
    assert response.status_code == 401


async def test_export_csv_returns_the_same_rows_as_the_rgpd_archive(
    api_client: httpx.AsyncClient, db_session, _local_photo_storage
) -> None:
    """Route synchrone (mission point 1) : pas de job, pas de ZIP — le même relevé que
    `collection.csv` dans l'export RGPD. Avant ce lot, `GET /me/export/collection.csv` n'existait
    pas (404) : ce test échoue sans la route et passe avec."""
    email = _unique_email("export-csv")
    await _register_verify_login(api_client, email)
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    item, card = await _add_collection_item_with_photo(
        db_session, str(user.id), _local_photo_storage, photo=None
    )

    response = await api_client.get("/me/export/collection.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "collection.csv" in response.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["item_id"] == str(item.id)
    assert rows[0]["carte"] == card.name
    assert rows[0]["photo"] == ""


async def test_export_csv_is_scoped_to_the_current_user(
    api_client: httpx.AsyncClient, db_session, _local_photo_storage
) -> None:
    """B n'a jamais les lignes de A dans son propre export — même garantie que le reste de la
    collection (`GET /me/collection`), pas un id à deviner ici, juste la session courante."""
    email_a = _unique_email("export-csv-a")
    await _register_verify_login(api_client, email_a)
    result = await db_session.execute(select(User).where(User.email == email_a))
    user_a = result.scalar_one()
    await _add_collection_item_with_photo(
        db_session, str(user_a.id), _local_photo_storage, photo=None
    )

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b:
        client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        await _register_verify_login(client_b, _unique_email("export-csv-b"))

        response = await client_b.get("/me/export/collection.csv")
        assert response.status_code == 200
        rows = list(csv.DictReader(io.StringIO(response.text)))
        assert rows == []


async def test_a_still_queued_export_has_no_download_token_yet(
    api_client: httpx.AsyncClient,
) -> None:
    """Un export `queued` n'a pas encore de jeton — un `None` explicite dans
    `data_exports.token_hash`, jamais un jeton devinable avant que l'archive n'existe."""
    csrf = await _register_verify_login(api_client, _unique_email("export-running"))
    created = await api_client.post("/me/export", headers={CSRF_HEADER_NAME: csrf})
    assert created.json()["status"] == "queued"

    guessed = await api_client.get("/export/download?token=un-jeton-au-hasard")
    assert guessed.status_code == 404
