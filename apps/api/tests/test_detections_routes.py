"""`GET /uploads/{id}/detections` et `GET /uploads/{id}/detections/{detection_id}/crop`
(mission `v3-detection`) : consultation des cartes détectées sur un envoi, bornée à son
propriétaire — préalable à la validation humaine (identification, lot ultérieur).

Avant ce lot, ces deux routes n'existaient pas (404) : chacun de ces tests échoue sur
`routers/uploads.py` sans elles et passe une fois branchées. Le worker arq n'est pas démarré
pendant les tests (comme pour les autres jobs du dépôt, mission `v3-detection` § clôture) :
`run_detection_for_upload` est appelé directement, comme le ferait `detect_cards_task`.
"""

import re
import uuid

import cv2
import httpx
import pytest
from sqlalchemy import select

from pbm_api.config import settings
from pbm_api.detection.service import run_detection_for_upload
from pbm_api.detection.synthetic import make_single_card
from pbm_api.models import Upload
from pbm_api.s3 import ObjectStorage
from pbm_api.security.csrf import CSRF_HEADER_NAME

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


async def _upload_and_complete(api_client, csrf, image_bytes: bytes) -> uuid.UUID:
    file_entry = {"filename": "a.jpg", "content_type": "image/jpeg", "size_bytes": len(image_bytes)}
    created = await api_client.post(
        "/uploads", json={"files": [file_entry]}, headers={CSRF_HEADER_NAME: csrf}
    )
    assert created.status_code == 200, created.text
    target = created.json()["uploads"][0]

    async with httpx.AsyncClient() as raw_client:
        put = await raw_client.put(target["url"], content=image_bytes, headers=target["headers"])
    assert put.status_code in (200, 204), put.text

    complete = await api_client.post(
        f"/uploads/{target['upload_id']}/complete", headers={CSRF_HEADER_NAME: csrf}
    )
    assert complete.status_code == 200, complete.text
    return uuid.UUID(target["upload_id"])


@pytest.fixture
async def storage():
    object_storage = ObjectStorage()
    await object_storage.ensure_bucket()
    return object_storage


def _encode(image) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


async def _run_worker_detection(db_session, storage, upload_id: uuid.UUID) -> None:
    """Simule `detect_cards_task` (le worker arq n'est pas démarré pendant les tests, comme les
    autres jobs du dépôt)."""
    result = await db_session.execute(select(Upload).where(Upload.id == upload_id))
    upload = result.scalar_one()
    await run_detection_for_upload(db_session, storage, upload)


async def test_list_detections_returns_crops_for_owner(api_client, db_session, storage):
    csrf = await _register_verify_login(api_client, _unique_email("det-list"))
    photo = make_single_card(seed=1, index=0)
    upload_id = await _upload_and_complete(api_client, csrf, _encode(photo.image))
    await _run_worker_detection(db_session, storage, upload_id)

    response = await api_client.get(f"/uploads/{upload_id}/detections")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["upload_id"] == str(upload_id)
    assert len(body["detections"]) == 1
    detection = body["detections"][0]
    assert detection["status"] == "pending"
    assert detection["crop_url"] == f"/uploads/{upload_id}/detections/{detection['id']}/crop"

    crop_response = await api_client.get(detection["crop_url"])
    assert crop_response.status_code == 200
    assert crop_response.headers["content-type"] == "image/jpeg"
    assert len(crop_response.content) > 0


async def test_list_detections_returns_404_for_another_users_upload(
    api_client, db_session, storage
):
    csrf_a = await _register_verify_login(api_client, _unique_email("det-iso-a"))
    photo = make_single_card(seed=1, index=1)
    upload_id = await _upload_and_complete(api_client, csrf_a, _encode(photo.image))
    await _run_worker_detection(db_session, storage, upload_id)

    detections = (await api_client.get(f"/uploads/{upload_id}/detections")).json()["detections"]
    detection_id = detections[0]["id"]

    await _register_verify_login(api_client, _unique_email("det-iso-b"))

    list_response = await api_client.get(f"/uploads/{upload_id}/detections")
    assert list_response.status_code == 404

    crop_response = await api_client.get(f"/uploads/{upload_id}/detections/{detection_id}/crop")
    assert crop_response.status_code == 404


async def test_list_detections_returns_404_for_unknown_upload(api_client):
    await _register_verify_login(api_client, _unique_email("det-unknown"))

    response = await api_client.get(f"/uploads/{uuid.uuid4()}/detections")

    assert response.status_code == 404
