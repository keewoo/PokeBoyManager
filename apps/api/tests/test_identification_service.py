"""`pbm_api.identification.service.run_identification_for_upload` (mission `v3-identification`) :
orchestration DB/stockage appelée par le worker juste après la détection
(`pbm_api.worker.detect_cards_task`) — logique indépendante d'arq, testable directement, comme
`pbm_api.detection.service.run_detection_for_upload`.

Avant ce lot, `pbm_api.identification.service` n'existait pas : chacun de ces tests échoue à la
collection et passe une fois le fichier ajouté.
"""

import json
import uuid

import cv2
import pytest
from sqlalchemy import select

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput, T
from pbm_api.ai.service import upsert_key
from pbm_api.detection.service import run_detection_for_upload
from pbm_api.detection.synthetic import make_single_card
from pbm_api.identification.service import run_identification_for_upload
from pbm_api.models import (
    AiProvider,
    AiUsageMonthly,
    Card,
    CardName,
    Detection,
    Set,
    Upload,
    UploadStatus,
    User,
)
from pbm_api.s3 import ObjectStorage

AI_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"

STUB_PAYLOAD = {
    "name": "Sarmuraï",
    "name_confidence": 0.9,
    "number": "1",
    "number_confidence": 0.9,
    "total": None,
    "total_confidence": 0.0,
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
        self.calls = 0

    async def _call(
        self, images: list[ImageInput], schema: type[T], prompt: str, model: str, retry_hint
    ) -> tuple[str, ExtractionUsage]:
        self.calls += 1
        return (
            json.dumps(self._payload),
            ExtractionUsage(provider=self.PROVIDER, model=model, input_tokens=40, output_tokens=20),
        )


def _encode(image) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


@pytest.fixture
async def storage():
    object_storage = ObjectStorage()
    await object_storage.ensure_bucket()
    return object_storage


async def _make_upload(db_session, storage, image_bytes: bytes) -> tuple[Upload, User]:
    user = User(email=f"ident-{uuid.uuid4()}@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    upload = Upload(
        user_id=user.id,
        s3_key=f"uploads/{user.id}/{uuid.uuid4()}/original",
        original_filename="photo.jpg",
        content_type="image/jpeg",
        size_bytes=len(image_bytes),
        status=UploadStatus.processed,
    )
    db_session.add(upload)
    await db_session.flush()
    await storage.put(upload.s3_key, image_bytes, "image/jpeg")
    return upload, user


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


async def test_run_identification_for_upload_calls_ai_and_stores_result(
    db_session, storage, monkeypatch
):
    card = await _seed_sarmurai(db_session)
    photo = make_single_card(seed=7, index=0)
    upload, user = await _make_upload(db_session, storage, _encode(photo.image))
    await upsert_key(db_session, user, AiProvider.anthropic, AI_KEY)
    await run_detection_for_upload(db_session, storage, upload)

    stub = _StubCardExtractionProvider(STUB_PAYLOAD)
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert summary.identified_count == 1
    assert summary.ai_calls == 1
    assert summary.cache_hits == 0
    assert stub.calls == 1

    result = await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    detection = result.scalar_one()
    assert detection.extraction["name"] == "Sarmuraï"
    assert detection.candidates
    assert detection.candidates[0]["card_id"] == str(card.id)

    usage_result = await db_session.execute(
        select(AiUsageMonthly).where(AiUsageMonthly.user_id == user.id)
    )
    usage = usage_result.scalar_one()
    assert usage.calls_count == 1
    assert usage.tokens_count == 60


async def test_run_identification_for_upload_reuses_cache_for_same_crop(
    db_session, storage, monkeypatch
):
    """Mission point 4 : la même carte rephotographiée (empreinte identique du recadrage) ne
    rappelle jamais l'IA, même pour un envoi et un utilisateur différents (cache partagé, comme
    `card_insights`)."""
    await _seed_sarmurai(db_session)
    photo = make_single_card(seed=11, index=0)
    image_bytes = _encode(photo.image)

    stub = _StubCardExtractionProvider(STUB_PAYLOAD)
    monkeypatch.setattr(
        "pbm_api.identification.service.create_provider", lambda *args, **kwargs: stub
    )

    upload_1, user_1 = await _make_upload(db_session, storage, image_bytes)
    await upsert_key(db_session, user_1, AiProvider.anthropic, AI_KEY)
    await run_detection_for_upload(db_session, storage, upload_1)
    summary_1 = await run_identification_for_upload(db_session, storage, upload_1)
    assert summary_1.ai_calls == 1

    upload_2, user_2 = await _make_upload(db_session, storage, image_bytes)
    await upsert_key(db_session, user_2, AiProvider.anthropic, AI_KEY)
    await run_detection_for_upload(db_session, storage, upload_2)
    summary_2 = await run_identification_for_upload(db_session, storage, upload_2)

    assert summary_2.ai_calls == 0
    assert summary_2.cache_hits == 1
    assert stub.calls == 1  # un seul appel IA au total pour les deux envois

    result = await db_session.execute(select(Detection).where(Detection.upload_id == upload_2.id))
    detection_2 = result.scalar_one()
    assert detection_2.extraction["name"] == "Sarmuraï"


async def test_run_identification_for_upload_without_ai_key_leaves_detection_unidentified(
    db_session, storage
):
    """D4 : sans clé IA, la reconnaissance reste désactivée — `detect_cards` n'est jamais mis en
    file dans ce cas (`pbm_api.uploads.service.complete_upload`), mais si ce service était tout
    de même appelé (ex: clé retirée entre la détection et l'identification), il ne doit jamais
    lever, juste ne rien identifier."""
    photo = make_single_card(seed=13, index=0)
    upload, _user = await _make_upload(db_session, storage, _encode(photo.image))
    await run_detection_for_upload(db_session, storage, upload)

    summary = await run_identification_for_upload(db_session, storage, upload)

    assert summary == type(summary)(identified_count=0, cache_hits=0, ai_calls=0)
    result = await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    detection = result.scalar_one()
    assert detection.extraction is None
    assert detection.candidates is None
