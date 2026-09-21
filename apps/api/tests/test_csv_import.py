"""Import CSV de la collection (mission `v6-import-export` point 1) : `POST /me/imports` crée un
`Job` (comme `POST /uploads/{id}/complete` pour `detect_cards_task`) ; le worker
(`pbm_api.imports.service.run_import_for_upload`) rapproche chaque ligne du catalogue avec le
même moteur que l'identification photo (`pbm_api.identification.reconciliation.reconcile`) et
crée une `Detection` par ligne — l'écran de validation existant (confirm/reject/GET) les traite
sans le moindre changement. Avant ce lot, `POST /me/imports` n'existait pas (404) : chacun de ces
tests échoue sans lui et passe avec.

Le worker arq n'est pas démarré pendant les tests (comme `test_validation_routes.py`) :
`run_import_for_upload` est appelée directement pour simuler `worker.import_csv_task`.
"""

import re
import uuid

import httpx
import pytest

from pbm_api.config import settings
from pbm_api.imports.errors import ImportFileEmptyError, ImportTooManyRowsError
from pbm_api.imports.parser import parse_csv
from pbm_api.imports.service import run_import_for_upload
from pbm_api.main import app as fastapi_app
from pbm_api.models import Card, CardName, Set, Upload
from pbm_api.routers.imports import get_storage
from pbm_api.security.csrf import CSRF_HEADER_NAME
from pbm_api.storage.local import LocalObjectStorage

PASSWORD = "correct horse battery staple"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
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


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _make_card(db_session, *, name: str, number: str) -> Card:
    set_row = Set(code=f"imp-{uuid.uuid4().hex[:8]}", name="Set import")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number=number, name=name, rarity="rare")
    db_session.add(card)
    await db_session.flush()
    # Le rapprochement par nom (`pbm_api.catalog.search.match_candidates`) cherche dans
    # `card_names`, jamais `cards.name` directement — sans cette ligne, une carte réellement
    # présente au catalogue resterait sans candidat.
    db_session.add(CardName(card_id=card.id, language="fr", name=name))
    await db_session.flush()
    return card


async def _post_csv(
    api_client: httpx.AsyncClient, csrf: str, content: bytes, filename: str = "import.csv"
) -> httpx.Response:
    return await api_client.post(
        "/me/imports",
        files={"file": (filename, content, "text/csv")},
        headers=_csrf(csrf),
    )


async def _simulate_import_worker(db_session, storage: LocalObjectStorage, upload_id: uuid.UUID):
    upload = await db_session.get(Upload, upload_id)
    return await run_import_for_upload(db_session, storage, upload)


@pytest.fixture(autouse=True)
def _local_import_storage(tmp_path):
    """Backend `local` (D7), comme `test_export.py` : preuve indépendante de MinIO."""
    storage = LocalObjectStorage(root=str(tmp_path))
    fastapi_app.dependency_overrides[get_storage] = lambda: storage
    yield storage
    fastapi_app.dependency_overrides.pop(get_storage, None)


# ----------------------------------------------------------------------------------- parsing
def test_parse_csv_recognizes_our_own_export_headers():
    csv_bytes = (
        b"carte,extension,numero,langue,variante\r\n"
        b"Dracaufeu,Set import (imp-1),6,fr,holo\r\n"
    )
    result = parse_csv(csv_bytes, max_rows=100)
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.name == "Dracaufeu"
    assert row.number == "6"
    assert row.language == "fr"
    assert row.variant == "holo"


def test_parse_csv_recognizes_common_english_aliases():
    csv_bytes = b"Card Name,Card Number,Qty\r\nPikachu,25,3\r\n"
    result = parse_csv(csv_bytes, max_rows=100)
    assert len(result.rows) == 1
    assert result.rows[0].name == "Pikachu"
    assert result.rows[0].number == "25"
    assert result.rows[0].quantity == 3


def test_parse_csv_handles_bom_and_semicolon_delimiter():
    """Excel en France enregistre un CSV avec BOM UTF-8 et `;` comme séparateur."""
    csv_bytes = "﻿carte;numero\r\nBulbizarre;1\r\n".encode()
    result = parse_csv(csv_bytes, max_rows=100)
    assert len(result.rows) == 1
    assert result.rows[0].name == "Bulbizarre"


def test_parse_csv_ignores_blank_lines_without_treating_them_as_rows():
    csv_bytes = b"carte,numero\r\nPikachu,25\r\n\r\n"
    result = parse_csv(csv_bytes, max_rows=100)
    assert len(result.rows) == 1
    assert result.ignored == []


def test_parse_csv_reports_rows_with_neither_name_nor_number_as_ignored():
    csv_bytes = b"carte,numero,langue\r\n,,fr\r\n"
    result = parse_csv(csv_bytes, max_rows=100)
    assert result.rows == []
    assert len(result.ignored) == 1
    assert result.ignored[0][0] == 2


def test_parse_csv_with_only_a_header_raises_empty_error():
    with pytest.raises(ImportFileEmptyError):
        parse_csv(b"carte,numero\r\n", max_rows=100)


def test_parse_csv_beyond_max_rows_raises_too_many_rows():
    csv_bytes = b"carte,numero\r\n" + b"".join(f"Carte {i},{i}\r\n".encode() for i in range(5))
    with pytest.raises(ImportTooManyRowsError):
        parse_csv(csv_bytes, max_rows=2)


# ----------------------------------------------------------------------------------- route
async def test_import_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(
        "/me/imports", files={"file": ("x.csv", b"a,b\r\n", "text/csv")}
    )
    assert response.status_code == 401


async def test_import_requires_csrf(api_client: httpx.AsyncClient) -> None:
    await _register_verify_login(api_client, _unique_email("import-nocsrf"))
    response = await api_client.post(
        "/me/imports", files={"file": ("x.csv", b"a,b\r\n", "text/csv")}
    )
    assert response.status_code == 403


async def test_import_queues_a_job(api_client: httpx.AsyncClient) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("import-queue"))
    response = await _post_csv(api_client, csrf, b"carte,numero\r\nPikachu,25\r\n")
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["upload_id"]
    assert body["job_id"]


# ----------------------------------------------------------------------- validation réutilisée
async def test_import_worker_matches_catalog_and_reuses_validation_screen(
    api_client: httpx.AsyncClient, db_session, _local_import_storage
) -> None:
    """Preuve bout en bout du point 1 de la mission : le worker d'import crée une `Detection`
    exploitable par le MÊME écran de validation (`GET /uploads/{id}`, `POST /detections/{id}/
    confirm`) que la reconnaissance photo — aucune route ni aucun écran supplémentaire."""
    csrf = await _register_verify_login(api_client, _unique_email("import-match"))
    card = await _make_card(db_session, name="Dracaufeu", number="6")

    created = await _post_csv(api_client, csrf, b"carte,numero\r\nDracaufeu,6\r\n")
    upload_id = uuid.UUID(created.json()["upload_id"])

    summary = await _simulate_import_worker(db_session, _local_import_storage, upload_id)
    assert summary.detections_count == 1
    assert summary.rows_parsed == 1

    detail = await api_client.get(f"/uploads/{upload_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["detections"]) == 1
    detection = body["detections"][0]
    assert detection["identification_method"] == "import"
    assert detection["candidates"][0]["card_id"] == str(card.id)

    confirm = await api_client.post(
        f"/detections/{detection['id']}/confirm",
        json={"card_id": str(card.id), "quantity": 1},
        headers=_csrf(csrf),
    )
    assert confirm.status_code == 200, confirm.text
    assert len(confirm.json()["collection_item_ids"]) == 1


async def test_import_preserves_quantity_and_purchase_details_for_the_validation_screen(
    api_client: httpx.AsyncClient, db_session, _local_import_storage
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("import-defaults"))
    await _make_card(db_session, name="Pikachu", number="25")

    created = await _post_csv(
        api_client,
        csrf,
        b"carte,numero,quantite,prix_achat,acquis_le\r\nPikachu,25,3,4.50,2026-01-15\r\n",
    )
    upload_id = uuid.UUID(created.json()["upload_id"])
    await _simulate_import_worker(db_session, _local_import_storage, upload_id)

    detail = await api_client.get(f"/uploads/{upload_id}")
    extraction = detail.json()["detections"][0]["extraction"]
    assert extraction["import_defaults"]["quantity"] == 3
    assert extraction["import_defaults"]["purchase_price"] == "4.50"
    assert extraction["import_defaults"]["acquired_at"] == "2026-01-15"


async def test_import_row_without_catalog_match_stays_pending_with_no_candidates(
    api_client: httpx.AsyncClient, db_session, _local_import_storage
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("import-nomatch"))
    created = await _post_csv(api_client, csrf, b"carte,numero\r\nCarte inexistante,999\r\n")
    upload_id = uuid.UUID(created.json()["upload_id"])
    await _simulate_import_worker(db_session, _local_import_storage, upload_id)

    detail = await api_client.get(f"/uploads/{upload_id}")
    detection = detail.json()["detections"][0]
    assert detection["status"] == "pending"
    assert detection["candidates"] == []


# ----------------------------------------------------------------------- accès croisé (B/A)
async def test_import_upload_is_isolated_by_user(
    api_client: httpx.AsyncClient, db_session, _local_import_storage
) -> None:
    csrf_a = await _register_verify_login(api_client, _unique_email("import-iso-a"))
    created = await _post_csv(api_client, csrf_a, b"carte,numero\r\nPikachu,25\r\n")
    upload_id = created.json()["upload_id"]

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b:
        client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        await _register_verify_login(client_b, _unique_email("import-iso-b"))

        response = await client_b.get(f"/uploads/{upload_id}")
        assert response.status_code == 404
