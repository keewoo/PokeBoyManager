"""Écran de validation (lot `v3-validation`) : `GET /uploads/{id}`, le flux SSE
`GET /uploads/{id}/events`, `POST /detections/{id}/confirm`, `/reject` et
`POST /uploads/{id}/confirm-all`.

Avant ce lot, aucune de ces routes n'existait (404 pour toutes) : chacun de ces tests échoue à
la collection et passe une fois branché. Le worker arq n'est pas démarré pendant les tests (comme
`test_detections_routes.py`) : la détection puis l'identification sont appelées directement,
comme le ferait `detect_cards_task`, et le `Job` créé par `POST /uploads/{id}/complete` est
transité à la main (`_simulate_worker`) pour reproduire ce que `worker._run_detect_cards` ferait.
"""

import json
import re
import uuid
from datetime import UTC, datetime

import cv2
import httpx
import pytest
from sqlalchemy import select

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput, T
from pbm_api.config import settings
from pbm_api.detection.service import run_detection_for_upload
from pbm_api.detection.synthetic import make_single_card
from pbm_api.identification.service import run_identification_for_upload
from pbm_api.models import (
    AiProvider,
    Card,
    CardName,
    CollectionItem,
    Detection,
    IdentificationCorrection,
    Job,
    JobStatus,
    Set,
    Upload,
)
from pbm_api.s3 import ObjectStorage
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
AI_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"

STUB_PAYLOAD = {
    "name": "Sarmuraï",
    "name_confidence": 0.95,
    "number": "1",
    "number_confidence": 0.95,
    # `total` = `total_cards` du set semé par `_seed_sarmurai` (198) : sans ce bonus de score
    # (`pbm_api.identification.reconciliation`, `Set.total_cards == total` -> +0.1), le score
    # combiné du candidat plafonne à 0.9 (0.5 nom + 0.4 numéro) et n'est jamais strictement
    # présélectionné (`PRESELECTION_THRESHOLD`), même à confiance parfaite.
    "total": 198,
    "total_confidence": 0.9,
    "set_code": None,
    "set_code_confidence": 0.0,
    "language": "fr",
    "language_confidence": 0.9,
    "hp": 60,
    "hp_confidence": 0.8,
    "card_type": "Pokémon",
    "card_type_confidence": 0.7,
    "variant": "normal",
    "variant_confidence": 0.6,
}


class _StubCardExtractionProvider(AIProvider):
    PROVIDER = AiProvider.anthropic
    DEFAULT_MODEL = "stub-vision"

    def __init__(self, payload: dict, **_ignored) -> None:
        super().__init__(api_key="unused")
        self._payload = payload

    async def _call(
        self, images: list[ImageInput], schema: type[T], prompt: str, model: str, retry_hint
    ) -> tuple[str, ExtractionUsage]:
        return (
            json.dumps(self._payload),
            ExtractionUsage(provider=self.PROVIDER, model=model, input_tokens=40, output_tokens=20),
        )


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


def _encode(image) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


@pytest.fixture
async def storage():
    object_storage = ObjectStorage()
    await object_storage.ensure_bucket()
    return object_storage


async def _seed_sarmurai(db_session) -> Card:
    suffix = uuid.uuid4().hex[:8]
    set_row = Set(code=f"sv01-{suffix}", name="Écarlate et Violet", total_cards=198)
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="1", name="Sarmuraï")
    db_session.add(card)
    await db_session.flush()
    db_session.add_all(
        [
            CardName(card_id=card.id, language="fr", name="Sarmuraï"),
            CardName(card_id=card.id, language="en", name="Sprigatito"),
        ]
    )
    await db_session.flush()
    return card


async def _upload_and_complete_with_ai_key(
    api_client: httpx.AsyncClient, csrf: str, image_bytes: bytes
) -> tuple[uuid.UUID, uuid.UUID]:
    """Envoie une photo pour un utilisateur qui a déjà une clé IA (D4) : `complete` met un job en
    file. Renvoie `(upload_id, job_id)`."""
    key_response = await api_client.put(
        f"/me/ai-keys/{AiProvider.anthropic.value}",
        json={"api_key": AI_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert key_response.status_code == 200, key_response.text

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
    body = complete.json()
    assert body["job_id"] is not None
    return uuid.UUID(target["upload_id"]), uuid.UUID(body["job_id"])


async def _simulate_worker(
    db_session, storage, upload_id: uuid.UUID, job_id: uuid.UUID, monkeypatch, payload: dict
) -> None:
    """Reproduit `worker._run_detect_cards` sans passer par arq (pas de worker démarré pendant
    les tests, voir `test_detections_routes.py`) : détection puis identification enchaînées dans
    le même job, `Job.status` transité comme le ferait le worker réel."""
    stub = _StubCardExtractionProvider(payload)
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    job = await db_session.get(Job, job_id)
    job.status = JobStatus.running
    job.started_at = datetime.now(UTC).replace(tzinfo=None)
    await db_session.commit()

    upload = await db_session.get(Upload, upload_id)
    await run_detection_for_upload(db_session, storage, upload)
    await run_identification_for_upload(db_session, storage, upload)

    job.status = JobStatus.succeeded
    job.finished_at = datetime.now(UTC).replace(tzinfo=None)
    await db_session.commit()


async def _first_detection(api_client: httpx.AsyncClient, upload_id: uuid.UUID) -> dict:
    response = await api_client.get(f"/uploads/{upload_id}/detections")
    assert response.status_code == 200, response.text
    detections = response.json()["detections"]
    assert len(detections) == 1
    return detections[0]


async def test_get_upload_returns_status_job_and_detections(
    api_client, db_session, storage, monkeypatch
):
    card = await _seed_sarmurai(db_session)
    csrf = await _register_verify_login(api_client, _unique_email("val-get"))
    photo = make_single_card(seed=21, index=0)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)

    response = await api_client.get(f"/uploads/{upload_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["upload_id"] == str(upload_id)
    assert body["status"] == "processed"
    assert body["job_status"] == "succeeded"
    assert len(body["detections"]) == 1
    detection = body["detections"][0]
    assert detection["status"] == "pending"
    assert detection["extraction"]["name"] == "Sarmuraï"
    assert detection["candidates"][0]["card_id"] == str(card.id)


async def test_get_upload_returns_404_for_another_users_upload(
    api_client, db_session, storage, monkeypatch
):
    await _seed_sarmurai(db_session)
    csrf_a = await _register_verify_login(api_client, _unique_email("val-get-iso-a"))
    photo = make_single_card(seed=22, index=1)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf_a, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)

    await _register_verify_login(api_client, _unique_email("val-get-iso-b"))

    response = await api_client.get(f"/uploads/{upload_id}")
    assert response.status_code == 404


async def test_stream_upload_events_emits_snapshot_then_done(
    api_client, db_session, storage, monkeypatch
):
    """La suite de tests partage une seule `AsyncSession` par test (`tests/conftest.py`) : on ne
    peut pas y exécuter le "worker" et consommer le flux SSE en vraie concurrence (usage
    concurrent d'une session SQLAlchemy non permis). Ce test couvre donc le contrat HTTP once le
    job déjà terminé — un instantané `snapshot` avec les détections, puis `done` — pas
    l'entrelacement réel des événements, vérifié manuellement (voir le compte rendu)."""
    await _seed_sarmurai(db_session)
    csrf = await _register_verify_login(api_client, _unique_email("val-sse"))
    photo = make_single_card(seed=23, index=0)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)

    events: list[tuple[str, dict]] = []
    async with api_client.stream("GET", f"/uploads/{upload_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        event_name = None
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event_name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((event_name, json.loads(line.removeprefix("data: "))))
            elif line == "" and event_name == "done":
                break

    names = [name for name, _ in events]
    assert names == ["snapshot", "done"]
    snapshot = events[0][1]
    assert snapshot["job_status"] == "succeeded"
    assert len(snapshot["detections"]) == 1
    assert snapshot["detections"][0]["extraction"]["name"] == "Sarmuraï"


async def test_stream_upload_events_returns_404_for_another_users_upload(api_client, db_session):
    csrf_a = await _register_verify_login(api_client, _unique_email("val-sse-iso-a"))
    file_entry = {"filename": "a.jpg", "content_type": "image/jpeg", "size_bytes": 10}
    created = await api_client.post(
        "/uploads", json={"files": [file_entry]}, headers={CSRF_HEADER_NAME: csrf_a}
    )
    upload_id = created.json()["uploads"][0]["upload_id"]

    await _register_verify_login(api_client, _unique_email("val-sse-iso-b"))
    response = await api_client.get(f"/uploads/{upload_id}/events")
    assert response.status_code == 404


async def test_confirm_detection_creates_collection_items_and_logs_correction(
    api_client, db_session, storage, monkeypatch
):
    card = await _seed_sarmurai(db_session)
    csrf = await _register_verify_login(api_client, _unique_email("val-confirm"))
    photo = make_single_card(seed=31, index=0)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)
    detection = await _first_detection(api_client, upload_id)

    response = await api_client.post(
        f"/detections/{detection['id']}/confirm",
        json={
            "card_id": str(card.id),
            "language": "fr",
            "variant": "holo",
            "quantity": 2,
            "condition_grade": "near mint",
            "purchase_price": "12.50",
            "purchase_currency": "EUR",
        },
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "validated"
    assert len(body["collection_item_ids"]) == 2

    items_result = await db_session.execute(
        select(CollectionItem).where(CollectionItem.detection_id == uuid.UUID(detection["id"]))
    )
    items = items_result.scalars().all()
    assert len(items) == 2
    assert {item.variant.value for item in items} == {"holo"}
    assert {str(item.card_id) for item in items} == {str(card.id)}

    detection_result = await db_session.execute(
        select(Detection).where(Detection.id == uuid.UUID(detection["id"]))
    )
    stored_detection = detection_result.scalar_one()
    assert stored_detection.status.value == "validated"
    assert stored_detection.selected_card_id == card.id

    correction_result = await db_session.execute(
        select(IdentificationCorrection).where(
            IdentificationCorrection.detection_id == uuid.UUID(detection["id"])
        )
    )
    correction = correction_result.scalar_one()
    assert correction.proposed_card_id == card.id
    assert correction.chosen_card_id == card.id


async def test_confirm_detection_carries_counterfeit_flag_to_collection_item(
    api_client, db_session, storage, monkeypatch
):
    """`Detection.condition_assessment` (mission `v3-etat` point 3) signale une contrefaçon
    probable : `confirm` doit reprendre ce drapeau sur `CollectionItem.counterfeit_suspected`,
    jamais valoriser une contrefaçon probable comme l'originale
    (`pbm_api.pricing.valuation.item_value`)."""
    card = await _seed_sarmurai(db_session)
    csrf = await _register_verify_login(api_client, _unique_email("val-confirm-counterfeit"))
    photo = make_single_card(seed=38, index=0)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)
    detection = await _first_detection(api_client, upload_id)

    stored_detection = await db_session.get(Detection, uuid.UUID(detection["id"]))
    stored_detection.condition_assessment = {
        "counterfeit_suspected": True,
        "counterfeit_reasons": ["x"],
    }
    await db_session.commit()

    response = await api_client.post(
        f"/detections/{detection['id']}/confirm",
        json={"card_id": str(card.id)},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 200, response.text

    items_result = await db_session.execute(
        select(CollectionItem).where(CollectionItem.detection_id == uuid.UUID(detection["id"]))
    )
    item = items_result.scalar_one()
    assert item.counterfeit_suspected is True


async def test_confirm_detection_with_different_card_logs_a_real_correction(
    api_client, db_session, storage, monkeypatch
):
    """Le candidat choisi diffère du candidat proposé : c'est exactement le cas que le jeu de
    régression de l'identification (mission point 3) doit pouvoir distinguer d'une confirmation
    simple."""
    await _seed_sarmurai(db_session)
    other_set = Set(code=f"other-{uuid.uuid4().hex[:8]}", name="Autre extension")
    db_session.add(other_set)
    await db_session.flush()
    other_card = Card(set_id=other_set.id, number="99", name="Autre carte")
    db_session.add(other_card)
    await db_session.flush()

    csrf = await _register_verify_login(api_client, _unique_email("val-correct"))
    photo = make_single_card(seed=32, index=0)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)
    detection = await _first_detection(api_client, upload_id)
    proposed_card_id = detection["candidates"][0]["card_id"]
    assert proposed_card_id != str(other_card.id)

    response = await api_client.post(
        f"/detections/{detection['id']}/confirm",
        json={"card_id": str(other_card.id)},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 200, response.text

    correction_result = await db_session.execute(
        select(IdentificationCorrection).where(
            IdentificationCorrection.detection_id == uuid.UUID(detection["id"])
        )
    )
    correction = correction_result.scalar_one()
    assert str(correction.proposed_card_id) == proposed_card_id
    assert correction.chosen_card_id == other_card.id


async def test_confirm_detection_returns_404_for_another_users_detection(
    api_client, db_session, storage, monkeypatch
):
    card = await _seed_sarmurai(db_session)
    csrf_a = await _register_verify_login(api_client, _unique_email("val-confirm-iso-a"))
    photo = make_single_card(seed=33, index=1)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf_a, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)
    detection = await _first_detection(api_client, upload_id)

    csrf_b = await _register_verify_login(api_client, _unique_email("val-confirm-iso-b"))

    response = await api_client.post(
        f"/detections/{detection['id']}/confirm",
        json={"card_id": str(card.id)},
        headers={CSRF_HEADER_NAME: csrf_b},
    )
    assert response.status_code == 404

    items = await db_session.execute(
        select(CollectionItem).where(CollectionItem.detection_id == uuid.UUID(detection["id"]))
    )
    assert items.scalars().all() == []


async def test_reject_detection_returns_404_for_another_users_detection(
    api_client, db_session, storage, monkeypatch
):
    await _seed_sarmurai(db_session)
    csrf_a = await _register_verify_login(api_client, _unique_email("val-reject-iso-a"))
    photo = make_single_card(seed=37, index=1)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf_a, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)
    detection = await _first_detection(api_client, upload_id)

    csrf_b = await _register_verify_login(api_client, _unique_email("val-reject-iso-b"))

    response = await api_client.post(
        f"/detections/{detection['id']}/reject", headers={CSRF_HEADER_NAME: csrf_b}
    )
    assert response.status_code == 404

    correction_result = await db_session.execute(
        select(IdentificationCorrection).where(
            IdentificationCorrection.detection_id == uuid.UUID(detection["id"])
        )
    )
    assert correction_result.scalar_one_or_none() is None


async def test_confirm_detection_twice_returns_409(api_client, db_session, storage, monkeypatch):
    card = await _seed_sarmurai(db_session)
    csrf = await _register_verify_login(api_client, _unique_email("val-confirm-twice"))
    photo = make_single_card(seed=34, index=0)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)
    detection = await _first_detection(api_client, upload_id)

    first = await api_client.post(
        f"/detections/{detection['id']}/confirm",
        json={"card_id": str(card.id)},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert first.status_code == 200, first.text

    second = await api_client.post(
        f"/detections/{detection['id']}/confirm",
        json={"card_id": str(card.id)},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert second.status_code == 409


async def test_confirm_detection_returns_404_for_unknown_card(
    api_client, db_session, storage, monkeypatch
):
    await _seed_sarmurai(db_session)
    csrf = await _register_verify_login(api_client, _unique_email("val-confirm-unknown"))
    photo = make_single_card(seed=35, index=0)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)
    detection = await _first_detection(api_client, upload_id)

    response = await api_client.post(
        f"/detections/{detection['id']}/confirm",
        json={"card_id": str(uuid.uuid4())},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 404


async def test_reject_detection_marks_rejected_without_collection_item(
    api_client, db_session, storage, monkeypatch
):
    await _seed_sarmurai(db_session)
    csrf = await _register_verify_login(api_client, _unique_email("val-reject"))
    photo = make_single_card(seed=36, index=0)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)
    detection = await _first_detection(api_client, upload_id)

    response = await api_client.post(
        f"/detections/{detection['id']}/reject", headers={CSRF_HEADER_NAME: csrf}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"

    items = await db_session.execute(
        select(CollectionItem).where(CollectionItem.detection_id == uuid.UUID(detection["id"]))
    )
    assert items.scalars().all() == []

    correction_result = await db_session.execute(
        select(IdentificationCorrection).where(
            IdentificationCorrection.detection_id == uuid.UUID(detection["id"])
        )
    )
    correction = correction_result.scalar_one()
    assert correction.chosen_card_id is None


async def test_confirm_all_uses_preselected_candidate_and_skips_the_rest(
    api_client, db_session, storage, monkeypatch
):
    card = await _seed_sarmurai(db_session)
    csrf = await _register_verify_login(api_client, _unique_email("val-confirm-all"))
    photo = make_single_card(seed=37, index=0)
    upload_id, job_id = await _upload_and_complete_with_ai_key(
        api_client, csrf, _encode(photo.image)
    )
    await _simulate_worker(db_session, storage, upload_id, job_id, monkeypatch, STUB_PAYLOAD)
    detection = await _first_detection(api_client, upload_id)
    assert detection["candidates"][0]["preselected"] is True

    upload = await db_session.get(Upload, upload_id)
    unmatched = Detection(
        upload_id=upload.id,
        bbox={"reading_order": 1, "points": []},
        crop_s3_key=None,
        extraction=None,
        candidates=None,
    )
    db_session.add(unmatched)
    await db_session.commit()

    response = await api_client.post(
        f"/uploads/{upload_id}/confirm-all", headers={CSRF_HEADER_NAME: csrf}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["confirmed"] == [detection["id"]]
    assert body["skipped"] == [str(unmatched.id)]

    items = await db_session.execute(
        select(CollectionItem).where(CollectionItem.detection_id == uuid.UUID(detection["id"]))
    )
    confirmed_items = items.scalars().all()
    assert len(confirmed_items) == 1
    assert confirmed_items[0].card_id == card.id
    assert confirmed_items[0].language == "fr"
    assert confirmed_items[0].variant.value == "normal"

    unmatched_result = await db_session.execute(
        select(Detection).where(Detection.id == unmatched.id)
    )
    assert unmatched_result.scalar_one().status.value == "pending"


async def test_confirm_all_recomputes_preselection_for_pre_lot_detections(
    api_client, db_session, storage
):
    """Régression `pbm-parcours-validation` : une détection identifiée AVANT ce lot a son drapeau
    `preselected` figé sous l'ancien seuil de 0,9 (les 143 d'Aymeric, ou une entrée du cache
    partagé). L'API doit ré-appliquer le seuil courant (0,6) aux `combined_score` stockés — au
    service comme dans « Tout ajouter » — sinon la carte n'est jamais proposée ni ajoutée."""
    card = await _seed_sarmurai(db_session)
    csrf = await _register_verify_login(api_client, _unique_email("val-recompute"))
    photo = make_single_card(seed=91, index=0)
    upload_id, _job = await _upload_and_complete_with_ai_key(api_client, csrf, _encode(photo.image))

    legacy = Detection(
        upload_id=upload_id,
        bbox={"reading_order": 0, "points": []},
        crop_s3_key="legacy-crop",
        extraction={"name": "Sarmuraï", "number": "1"},
        candidates=[
            {
                "card_id": str(card.id),
                "set_id": str(card.set_id),
                "name": "Sarmuraï",
                "number": "1",
                "set_name": "Écarlate et Violet",
                "set_code": "sv01",
                "catalog_score": 0.9,
                "combined_score": 0.82,
                "preselected": False,  # figé sous l'ancien seuil de 0,9
            }
        ],
    )
    db_session.add(legacy)
    await db_session.commit()

    # Servie : la présélection est ré-appliquée (0,82 > 0,6, candidat unique) → True malgré le
    # drapeau figé à False.
    served = await _first_detection(api_client, upload_id)
    assert served["candidates"][0]["preselected"] is True

    response = await api_client.post(
        f"/uploads/{upload_id}/confirm-all", headers={CSRF_HEADER_NAME: csrf}
    )
    assert response.status_code == 200, response.text
    assert response.json()["confirmed"] == [str(legacy.id)]

    items = (
        await db_session.execute(
            select(CollectionItem).where(CollectionItem.detection_id == legacy.id)
        )
    ).scalars().all()
    assert len(items) == 1
    assert items[0].card_id == card.id


async def test_confirm_all_returns_404_for_another_users_upload(api_client, db_session):
    csrf_a = await _register_verify_login(api_client, _unique_email("val-confirm-all-iso-a"))
    file_entry = {"filename": "a.jpg", "content_type": "image/jpeg", "size_bytes": 10}
    created = await api_client.post(
        "/uploads", json={"files": [file_entry]}, headers={CSRF_HEADER_NAME: csrf_a}
    )
    upload_id = created.json()["uploads"][0]["upload_id"]

    csrf_b = await _register_verify_login(api_client, _unique_email("val-confirm-all-iso-b"))
    response = await api_client.post(
        f"/uploads/{upload_id}/confirm-all", headers={CSRF_HEADER_NAME: csrf_b}
    )
    assert response.status_code == 404
