"""Orchestration DB/stockage de la détection pour un envoi (mission `v3-detection`), appelée
par le worker (`pbm_api.worker.detect_cards_task`) — logique indépendante d'arq, testable
directement.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.factory import create_provider
from pbm_api.ai.service import get_default_credential, record_usage
from pbm_api.detection.annotate import encode_jpeg
from pbm_api.detection.errors import DetectionSourceMissingError
from pbm_api.detection.pipeline import run_detection
from pbm_api.models import Detection, DetectionStatus, Upload, User
from pbm_api.storage import StorageBackend


@dataclass(frozen=True)
class DetectionRunSummary:
    detections_count: int
    method: str


def _control_key(upload: Upload) -> str:
    return f"uploads/{upload.user_id}/{upload.id}/control.jpg"


def _crop_key(upload: Upload, index: int) -> str:
    return f"uploads/{upload.user_id}/{upload.id}/detections/{index}.jpg"


async def run_detection_for_upload(
    db: AsyncSession, storage: StorageBackend, upload: Upload
) -> DetectionRunSummary:
    raw = await storage.get(upload.s3_key)
    if raw is None:
        raise DetectionSourceMissingError(upload.s3_key)

    user = await db.get(User, upload.user_id)
    assert user is not None  # FK NOT NULL sur uploads.user_id : ne peut pas manquer ici

    ai_provider = None
    ai_model = user.ai_default_model
    credential = await get_default_credential(db, user)
    if credential is not None:
        provider_enum, api_key = credential
        ai_provider = create_provider(provider_enum, api_key)

    try:
        result = await run_detection(
            raw,
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_media_type=upload.content_type,
        )
    finally:
        if ai_provider is not None:
            await ai_provider.aclose()

    if result.ai_usage is not None:
        await record_usage(db, user, result.ai_usage)

    await storage.put(_control_key(upload), result.annotated_jpeg, "image/jpeg")

    for index, (quad, crop) in enumerate(zip(result.quads, result.crops, strict=True)):
        crop_key = _crop_key(upload, index)
        await storage.put(crop_key, encode_jpeg(crop), "image/jpeg")
        db.add(
            Detection(
                upload_id=upload.id,
                bbox={"reading_order": index, "points": quad.tolist()},
                crop_s3_key=crop_key,
                status=DetectionStatus.pending,
            )
        )

    await db.commit()
    return DetectionRunSummary(detections_count=len(result.quads), method=result.method)
