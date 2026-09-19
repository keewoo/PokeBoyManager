"""Orchestration DB/stockage de la détection (mission `v3-detection`) : `run_detection_for_upload`
écrit les `Detection`, les recadrages et l'image de contrôle dans le stockage, et alimente
`ai_usage_monthly` quand le repli LLM a été utilisé.

Avant ce lot, `pbm_api.detection.service` n'existait pas : ce module échoue à la collection et
passe une fois le fichier ajouté.
"""

import json
import uuid
from datetime import date, datetime

import cv2
import numpy as np
import pytest
from sqlalchemy import select

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput, T
from pbm_api.ai.service import upsert_key
from pbm_api.detection.geometry import CARD_HEIGHT_PX, CARD_WIDTH_PX
from pbm_api.detection.service import run_detection_for_upload
from pbm_api.detection.synthetic import make_single_card, make_table_scatter
from pbm_api.models import (
    AiProvider,
    AiUsageMonthly,
    Detection,
    Upload,
    UploadStatus,
    User,
)
from pbm_api.s3 import ObjectStorage

AI_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"


class _GroundTruthBoxProvider(AIProvider):
    PROVIDER = AiProvider.anthropic
    DEFAULT_MODEL = "ground-truth-stub"

    def __init__(self, boxes: list[dict], **_ignored) -> None:
        super().__init__(api_key="unused")
        self._boxes = boxes

    async def _call(
        self, images: list[ImageInput], schema: type[T], prompt: str, model: str, retry_hint
    ) -> tuple[str, ExtractionUsage]:
        return (
            json.dumps({"boxes": self._boxes}),
            ExtractionUsage(provider=self.PROVIDER, model=model, input_tokens=50, output_tokens=10),
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


async def _make_upload(db_session, storage, image_bytes: bytes) -> Upload:
    user = User(
        email=f"det-{uuid.uuid4()}@example.com",
        password_hash="x",
        last_name="Test",
        birth_date=date(2000, 1, 1),
        terms_version="test",
        terms_accepted_at=datetime(2000, 1, 1),
    )
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


async def test_run_detection_for_upload_stores_detections_and_crops(db_session, storage):
    photo = make_single_card(seed=1, index=0)
    upload, _user = await _make_upload(db_session, storage, _encode(photo.image))

    summary = await run_detection_for_upload(db_session, storage, upload)

    assert summary.detections_count == 1
    assert summary.method == "opencv"

    result = await db_session.execute(select(Detection).where(Detection.upload_id == upload.id))
    detections = list(result.scalars().all())
    assert len(detections) == 1
    crop_bytes = await storage.get(detections[0].crop_s3_key)
    assert crop_bytes is not None
    crop_image = cv2.imdecode(np.frombuffer(crop_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert crop_image.shape == (CARD_HEIGHT_PX, CARD_WIDTH_PX, 3)

    control_bytes = await storage.get(f"uploads/{upload.user_id}/{upload.id}/control.jpg")
    assert control_bytes is not None


async def test_run_detection_for_upload_uses_llm_fallback_and_records_usage(
    db_session, storage, monkeypatch
):
    photo = make_table_scatter(seed=300, index=0, count=2)
    upload, user = await _make_upload(db_session, storage, _encode(photo.image))
    await upsert_key(db_session, user, AiProvider.anthropic, AI_KEY)

    height, width = photo.image.shape[:2]
    boxes = [
        {
            "x_min": max(0.0, float(q[:, 0].min() / width)),
            "y_min": max(0.0, float(q[:, 1].min() / height)),
            "x_max": min(1.0, float(q[:, 0].max() / width)),
            "y_max": min(1.0, float(q[:, 1].max() / height)),
        }
        for q in photo.ground_truth_quads
    ]
    monkeypatch.setattr(
        "pbm_api.detection.service.create_provider",
        lambda provider, api_key, **kwargs: _GroundTruthBoxProvider(boxes),
    )

    summary = await run_detection_for_upload(db_session, storage, upload)

    assert summary.detections_count == 2
    assert summary.method == "llm_fallback"

    usage_result = await db_session.execute(
        select(AiUsageMonthly).where(AiUsageMonthly.user_id == user.id)
    )
    usage = usage_result.scalar_one()
    assert usage.calls_count == 1
    assert usage.tokens_count == 60
