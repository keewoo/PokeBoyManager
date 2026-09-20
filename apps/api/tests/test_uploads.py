"""Envoi de photos (mission `v3-upload`) : cible d'envoi par fichier, envoi direct au stockage,
vérification du type réel (magic bytes), suppression de l'EXIF, conversion HEIC → JPEG, job de
reconnaissance conditionné à une clé IA (D4).

Avant ce lot, `POST /uploads` n'existait pas (404) : chacun de ces tests échoue sur `main.py`
sans le routeur `uploads` et passe une fois branché.
"""

import io
import re
import uuid

import httpx
import pillow_heif
import pytest
from PIL import Image
from PIL.ExifTags import IFD
from sqlalchemy import select

from pbm_api.config import settings
from pbm_api.models import (
    AiProvider,
    Detection,
    DetectionStatus,
    Job,
    JobStatus,
    Upload,
    UploadStatus,
)
from pbm_api.routers.uploads import get_storage
from pbm_api.s3 import ObjectStorage
from pbm_api.security.csrf import CSRF_HEADER_NAME
from pbm_api.security.upload_tokens import generate_upload_token
from pbm_api.storage.local import LocalObjectStorage

PASSWORD = "correct horse battery staple"
AI_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"

pillow_heif.register_heif_opener()


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


def _jpeg_with_gps_exif(color: str = "red") -> bytes:
    image = Image.new("RGB", (32, 32), color)
    exif = image.getexif()
    exif[IFD.GPSInfo] = {1: "N", 2: (48, 0, 0), 3: "E", 4: (2, 0, 0)}
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _png_bytes() -> bytes:
    image = Image.new("RGB", (16, 16), "blue")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _heic_bytes() -> bytes:
    image = Image.new("RGB", (16, 16), "green")
    buf = io.BytesIO()
    image.save(buf, format="HEIF")
    return buf.getvalue()


def _mpo_bytes() -> bytes:
    """MPO = JPEG multi-images des modes portrait/HDR des téléphones (correctif
    `pbm-hotfix-formats-image`). Le navigateur l'annonce en `image/jpeg`."""
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), "red").save(
        buf, format="MPO", append_images=[Image.new("RGB", (32, 24), "blue")]
    )
    return buf.getvalue()


def _webp_bytes() -> bytes:
    image = Image.new("RGB", (16, 16), (200, 100, 50))
    buf = io.BytesIO()
    image.save(buf, format="WEBP")
    return buf.getvalue()


@pytest.fixture
async def storage():
    object_storage = ObjectStorage()
    await object_storage.ensure_bucket()
    return object_storage


@pytest.fixture(autouse=True)
def _clear_overrides():
    from pbm_api.main import app

    yield
    app.dependency_overrides.pop(get_storage, None)


async def _create_one(
    api_client, csrf, *, content_type="image/jpeg", size_bytes=5000, filename="a.jpg"
):
    file_entry = {"filename": filename, "content_type": content_type, "size_bytes": size_bytes}
    response = await api_client.post(
        "/uploads", json={"files": [file_entry]}, headers={CSRF_HEADER_NAME: csrf}
    )
    assert response.status_code == 200, response.text
    return response.json()["uploads"][0]


async def _put_to_s3(target: dict, data: bytes) -> None:
    async with httpx.AsyncClient() as raw_client:
        response = await raw_client.put(target["url"], content=data, headers=target["headers"])
    assert response.status_code in (200, 204), response.text


async def _local_client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="https://testserver")


# --- Création des cibles d'envoi -----------------------------------------------------------


async def test_create_uploads_returns_one_presigned_target_per_file(api_client, storage):
    csrf = await _register_verify_login(api_client, _unique_email("up-create"))
    response = await api_client.post(
        "/uploads",
        json={
            "files": [
                {"filename": "a.jpg", "content_type": "image/jpeg", "size_bytes": 1000},
                {"filename": "b.png", "content_type": "image/png", "size_bytes": 2000},
            ]
        },
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["uploads"]) == 2
    for target in body["uploads"]:
        assert target["method"] == "PUT"
        assert target["url"].startswith(settings.s3_endpoint_url)
        assert "Content-Type" in target["headers"]


async def test_create_uploads_rejects_too_many_files(api_client):
    csrf = await _register_verify_login(api_client, _unique_email("up-toomany"))
    files = [
        {"filename": f"f{i}.jpg", "content_type": "image/jpeg", "size_bytes": 100}
        for i in range(31)
    ]
    response = await api_client.post(
        "/uploads", json={"files": files}, headers={CSRF_HEADER_NAME: csrf}
    )
    assert response.status_code == 400


async def test_create_uploads_rejects_disallowed_content_type(api_client):
    csrf = await _register_verify_login(api_client, _unique_email("up-badtype"))
    response = await api_client.post(
        "/uploads",
        json={"files": [{"filename": "a.gif", "content_type": "image/gif", "size_bytes": 100}]},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 400


async def test_create_uploads_rejects_oversized_file(api_client):
    csrf = await _register_verify_login(api_client, _unique_email("up-oversized"))
    response = await api_client.post(
        "/uploads",
        json={
            "files": [
                {
                    "filename": "a.jpg",
                    "content_type": "image/jpeg",
                    "size_bytes": settings.upload_max_size_bytes + 1,
                }
            ]
        },
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 400


async def test_create_uploads_requires_csrf_token(api_client):
    await _register_verify_login(api_client, _unique_email("up-nocsrf"))
    response = await api_client.post(
        "/uploads",
        json={"files": [{"filename": "a.jpg", "content_type": "image/jpeg", "size_bytes": 100}]},
    )
    assert response.status_code == 403


# --- Bout en bout : envoi réel vers MinIO, complétion, EXIF, HEIC -------------------------


async def test_upload_end_to_end_strips_exif_and_marks_processed(api_client, db_session, storage):
    csrf = await _register_verify_login(api_client, _unique_email("up-e2e"))
    target = await _create_one(api_client, csrf, filename="classeur.jpg")
    await _put_to_s3(target, _jpeg_with_gps_exif())

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    assert complete.status_code == 200, complete.text
    body = complete.json()
    assert body["status"] == "processed"
    assert body["content_type"] == "image/jpeg"
    assert body["recognition_enabled"] is False, "aucune clé IA enregistrée pour cet utilisateur"
    assert body["job_id"] is None

    result = await db_session.execute(
        select(Upload).where(Upload.id == uuid.UUID(target["upload_id"]))
    )
    upload_row = result.scalar_one()
    assert upload_row.status == UploadStatus.processed

    stored_bytes = await storage.get(upload_row.s3_key)
    assert stored_bytes is not None
    processed_image = Image.open(io.BytesIO(stored_bytes))
    assert dict(processed_image.getexif()) == {}, "l'EXIF (dont la position GPS) doit être supprimé"


async def test_heic_upload_is_converted_to_jpeg(api_client, storage):
    csrf = await _register_verify_login(api_client, _unique_email("up-heic"))
    target = await _create_one(
        api_client, csrf, content_type="image/heic", filename="IMG_2044.heic"
    )
    await _put_to_s3(target, _heic_bytes())

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    assert complete.status_code == 200, complete.text
    assert complete.json()["content_type"] == "image/jpeg"


async def test_mpo_upload_is_converted_to_jpeg(api_client, storage):
    """Le défaut de production : un MPO (photo portrait/HDR) était rejeté « format non accepté »
    alors que c'est un JPEG lisible. Le navigateur l'annonce en `image/jpeg`."""
    csrf = await _register_verify_login(api_client, _unique_email("up-mpo"))
    target = await _create_one(
        api_client, csrf, content_type="image/jpeg", filename="IMG_portrait.jpg"
    )
    await _put_to_s3(target, _mpo_bytes())

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    assert complete.status_code == 200, complete.text
    assert complete.json()["content_type"] == "image/jpeg"


async def test_webp_upload_is_converted_to_jpeg(api_client, storage):
    csrf = await _register_verify_login(api_client, _unique_email("up-webp"))
    target = await _create_one(
        api_client, csrf, content_type="image/webp", filename="carte.webp"
    )
    await _put_to_s3(target, _webp_bytes())

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    assert complete.status_code == 200, complete.text
    assert complete.json()["content_type"] == "image/jpeg"


async def test_png_upload_stays_png_without_exif(api_client, storage):
    csrf = await _register_verify_login(api_client, _unique_email("up-png"))
    target = await _create_one(api_client, csrf, content_type="image/png", filename="a.png")
    await _put_to_s3(target, _png_bytes())

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    assert complete.status_code == 200, complete.text
    assert complete.json()["content_type"] == "image/png"


async def test_complete_rejects_bytes_that_are_not_really_an_image(api_client, storage):
    csrf = await _register_verify_login(api_client, _unique_email("up-fake"))
    target = await _create_one(api_client, csrf, filename="not-an-image.jpg")
    await _put_to_s3(target, b"ceci n'est pas une image, juste du texte" * 20)

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    assert complete.status_code == 400, complete.text


async def test_complete_rejects_an_object_bigger_than_declared_at_creation(
    api_client, db_session, storage
):
    """Mission `v5-securite` point 2 : une URL présignée S3 (`generate_presigned_url`, pas de
    présignage POST) n'impose aucune limite de taille au navigateur — `size_bytes` déclaré à
    `POST /uploads` n'est qu'une métadonnée, jamais appliquée par MinIO/S3 lui-même. Simule
    l'écart : un dépôt réel plus gros que `upload_max_size_bytes`, jamais lu en mémoire
    entièrement (`storage.head` avant `storage.get`), objet supprimé du stockage."""
    csrf = await _register_verify_login(api_client, _unique_email("up-oversized"))
    target = await _create_one(api_client, csrf, size_bytes=1000)
    oversized = b"x" * (settings.upload_max_size_bytes + 1)
    await _put_to_s3(target, oversized)

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    assert complete.status_code == 413, complete.text

    upload = (
        await db_session.execute(select(Upload).where(Upload.id == uuid.UUID(target["upload_id"])))
    ).scalar_one()
    assert upload.status == UploadStatus.failed
    assert await storage.get(upload.s3_key) is None


async def test_complete_requires_raw_bytes_to_have_been_received(api_client):
    csrf = await _register_verify_login(api_client, _unique_email("up-noraw"))
    target = await _create_one(api_client, csrf)

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    assert complete.status_code == 409


async def test_complete_is_not_replayable(api_client, storage):
    csrf = await _register_verify_login(api_client, _unique_email("up-replay"))
    target = await _create_one(api_client, csrf)
    await _put_to_s3(target, _jpeg_with_gps_exif())

    first = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )
    second = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 409


async def test_complete_creates_job_when_ai_key_present(api_client, db_session, storage):
    csrf = await _register_verify_login(api_client, _unique_email("up-withkey"))
    key_response = await api_client.put(
        f"/me/ai-keys/{AiProvider.anthropic.value}",
        json={"api_key": AI_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert key_response.status_code == 200, key_response.text

    target = await _create_one(api_client, csrf)
    await _put_to_s3(target, _jpeg_with_gps_exif())

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    assert complete.status_code == 200, complete.text
    body = complete.json()
    assert body["recognition_enabled"] is True
    assert body["job_id"] is not None

    result = await db_session.execute(select(Job).where(Job.id == uuid.UUID(body["job_id"])))
    job = result.scalar_one()
    assert job.type == "detect_cards"
    assert job.status == JobStatus.queued
    assert job.payload == {"upload_id": target["upload_id"]}


# --- Isolation par utilisateur ---------------------------------------------------------------


async def test_complete_returns_404_for_another_users_upload(api_client, storage):
    csrf_a = await _register_verify_login(api_client, _unique_email("up-iso-a"))
    target = await _create_one(api_client, csrf_a)
    await _put_to_s3(target, _jpeg_with_gps_exif())

    csrf_b = await _register_verify_login(api_client, _unique_email("up-iso-b"))
    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf_b}
    )

    assert complete.status_code == 404


# --- Reprise d'un envoi à valider (mission `pbm-parcours-validation` points 2 & 6) -----------


async def _seed_pending_detection(db_session, upload_id: uuid.UUID) -> None:
    db_session.add(
        Detection(
            upload_id=upload_id,
            bbox={"reading_order": 0, "points": []},
            crop_s3_key="crop-key",
            status=DetectionStatus.pending,
        )
    )
    await db_session.flush()


async def test_pending_validation_lists_uploads_with_pending_detections(
    api_client, db_session, storage
):
    csrf = await _register_verify_login(api_client, _unique_email("pv"))
    target = await _create_one(api_client, csrf)
    await _put_to_s3(target, _jpeg_with_gps_exif())
    await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )
    await _seed_pending_detection(db_session, uuid.UUID(target["upload_id"]))

    response = await api_client.get("/uploads/pending-validation")

    assert response.status_code == 200, response.text
    items = response.json()["uploads"]
    match = next((u for u in items if u["upload_id"] == target["upload_id"]), None)
    assert match is not None, "l'envoi avec une détection en attente doit être proposé à la reprise"
    assert match["pending_count"] == 1
    assert match["total_count"] == 1


async def test_pending_validation_is_scoped_to_current_user(api_client, db_session, storage):
    csrf_a = await _register_verify_login(api_client, _unique_email("pv-a"))
    target = await _create_one(api_client, csrf_a)
    await _put_to_s3(target, _jpeg_with_gps_exif())
    await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf_a}
    )
    await _seed_pending_detection(db_session, uuid.UUID(target["upload_id"]))

    await _register_verify_login(api_client, _unique_email("pv-b"))
    response = await api_client.get("/uploads/pending-validation")

    assert response.status_code == 200
    assert all(u["upload_id"] != target["upload_id"] for u in response.json()["uploads"])


async def _complete_with_key(api_client, csrf) -> dict:
    await api_client.put(
        f"/me/ai-keys/{AiProvider.anthropic.value}",
        json={"api_key": AI_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )
    target = await _create_one(api_client, csrf)
    await _put_to_s3(target, _jpeg_with_gps_exif())
    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )
    assert complete.status_code == 200, complete.text
    return {"target": target, "complete": complete.json()}


async def test_retry_recognition_enqueues_a_new_job_after_failure(api_client, db_session, storage):
    csrf = await _register_verify_login(api_client, _unique_email("retry"))
    seeded = await _complete_with_key(api_client, csrf)
    first_job_id = seeded["complete"]["job_id"]

    # Le premier job doit être terminal pour qu'une relance soit permise (sinon 409 en cours).
    job = (
        await db_session.execute(select(Job).where(Job.id == uuid.UUID(first_job_id)))
    ).scalar_one()
    job.status = JobStatus.failed
    await db_session.flush()

    response = await api_client.post(
        f"/uploads/{seeded['target']['upload_id']}/retry-recognition",
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["job_id"] != first_job_id


async def test_retry_recognition_conflicts_when_a_job_is_still_in_progress(api_client, storage):
    csrf = await _register_verify_login(api_client, _unique_email("retry-busy"))
    seeded = await _complete_with_key(api_client, csrf)  # job left 'queued'

    response = await api_client.post(
        f"/uploads/{seeded['target']['upload_id']}/retry-recognition",
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 409


async def test_retry_recognition_requires_an_ai_key(api_client, storage):
    csrf = await _register_verify_login(api_client, _unique_email("retry-nokey"))
    target = await _create_one(api_client, csrf)
    await _put_to_s3(target, _jpeg_with_gps_exif())
    await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )

    response = await api_client.post(
        f"/uploads/{target['upload_id']}/retry-recognition", headers={CSRF_HEADER_NAME: csrf}
    )

    assert response.status_code == 400


async def test_retry_recognition_404_for_another_users_upload(api_client, storage):
    csrf_a = await _register_verify_login(api_client, _unique_email("retry-iso-a"))
    seeded = await _complete_with_key(api_client, csrf_a)

    csrf_b = await _register_verify_login(api_client, _unique_email("retry-iso-b"))
    response = await api_client.post(
        f"/uploads/{seeded['target']['upload_id']}/retry-recognition",
        headers={CSRF_HEADER_NAME: csrf_b},
    )

    assert response.status_code == 404


# --- Backend local (D7) : cible d'envoi signée, sans session ---------------------------------


async def test_local_backend_upload_flow_writes_to_disk(api_client, tmp_path):
    from pbm_api.main import app

    local_storage = LocalObjectStorage(root=str(tmp_path))
    app.dependency_overrides[get_storage] = lambda: local_storage

    csrf = await _register_verify_login(api_client, _unique_email("up-local"))
    target = await _create_one(api_client, csrf, filename="local.jpg")
    assert target["url"].startswith(f"/uploads/{target['upload_id']}/raw?token=")

    async with await _local_client(app) as raw_client:
        put_response = await raw_client.put(target["url"], content=_jpeg_with_gps_exif())
    assert put_response.status_code == 204, put_response.text

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["content_type"] == "image/jpeg"

    stored_files = list(tmp_path.rglob("*"))
    assert any(f.is_file() for f in stored_files), "les octets doivent atterrir sur le disque local"


async def test_local_backend_raw_upload_rejects_invalid_token(api_client, tmp_path):
    from pbm_api.main import app

    local_storage = LocalObjectStorage(root=str(tmp_path))
    app.dependency_overrides[get_storage] = lambda: local_storage

    csrf = await _register_verify_login(api_client, _unique_email("up-badtoken"))
    target = await _create_one(api_client, csrf)

    async with await _local_client(app) as raw_client:
        response = await raw_client.put(
            f"/uploads/{target['upload_id']}/raw?token=0.deadbeef", content=b"data"
        )
    assert response.status_code == 403


async def test_local_backend_raw_upload_rejects_token_for_another_upload(api_client, tmp_path):
    from pbm_api.main import app

    local_storage = LocalObjectStorage(root=str(tmp_path))
    app.dependency_overrides[get_storage] = lambda: local_storage

    csrf = await _register_verify_login(api_client, _unique_email("up-crosstoken"))
    target_a = await _create_one(api_client, csrf, filename="a.jpg")
    target_b = await _create_one(api_client, csrf, filename="b.jpg")
    token_for_a = target_a["url"].split("token=", 1)[1]

    async with await _local_client(app) as raw_client:
        response = await raw_client.put(
            f"/uploads/{target_b['upload_id']}/raw?token={token_for_a}", content=b"data"
        )
    assert response.status_code == 403


async def test_local_backend_raw_upload_rejects_expired_token(api_client, tmp_path):
    from pbm_api.main import app

    local_storage = LocalObjectStorage(root=str(tmp_path))
    app.dependency_overrides[get_storage] = lambda: local_storage

    csrf = await _register_verify_login(api_client, _unique_email("up-expired"))
    target = await _create_one(api_client, csrf)
    upload_id = uuid.UUID(target["upload_id"])
    expired_token = generate_upload_token(upload_id, expires_in=-1)

    async with await _local_client(app) as raw_client:
        response = await raw_client.put(
            f"/uploads/{upload_id}/raw?token={expired_token}", content=b"data"
        )
    assert response.status_code == 403
