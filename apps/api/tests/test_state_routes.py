"""`GET /uploads/{id}/detections` expose désormais l'état estimé (mission `v3-etat`), sur la
même route posée par `v3-detection` et déjà étendue par `v3-identification` — bornée au
propriétaire de l'envoi comme le reste de la réponse (voir `test_detections_routes.py`).
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
from pbm_api.state.service import run_state_estimation_for_upload

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


async def _run_worker_pipeline(db_session, storage, upload_id: uuid.UUID) -> None:
    """Simule `detect_cards_task` sans identification IA (pas de clé configurée dans ces tests,
    D4) : détection puis estimation d'état — le centrage se mesure sans jamais dépendre d'une
    clé IA."""
    upload = (
        await db_session.execute(select(Upload).where(Upload.id == upload_id))
    ).scalar_one()
    await run_detection_for_upload(db_session, storage, upload)
    await run_state_estimation_for_upload(db_session, storage, upload)


async def test_list_detections_exposes_condition_for_owner(api_client, db_session, storage):
    csrf = await _register_verify_login(api_client, _unique_email("etat-list"))
    photo = make_single_card(seed=1, index=0)
    upload_id = await _upload_and_complete(api_client, csrf, _encode(photo.image))
    await _run_worker_pipeline(db_session, storage, upload_id)

    response = await api_client.get(f"/uploads/{upload_id}/detections")

    assert response.status_code == 200, response.text
    detection = response.json()["detections"][0]
    # Pas d'extraction IA (D4, aucune clé) : le centrage reste présent, coins/bords/surface non.
    assert detection["condition"] is not None
    assert "disclaimer" in detection["condition"]
    assert detection["condition"]["corners"] is None


async def test_list_detections_hides_condition_of_another_users_upload(
    api_client, db_session, storage
):
    csrf_a = await _register_verify_login(api_client, _unique_email("etat-iso-a"))
    photo = make_single_card(seed=1, index=1)
    upload_id = await _upload_and_complete(api_client, csrf_a, _encode(photo.image))
    await _run_worker_pipeline(db_session, storage, upload_id)

    await _register_verify_login(api_client, _unique_email("etat-iso-b"))

    response = await api_client.get(f"/uploads/{upload_id}/detections")
    assert response.status_code == 404
