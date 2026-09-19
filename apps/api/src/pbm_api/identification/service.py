"""Orchestration DB/stockage de l'identification (mission `v3-identification`), appelée par le
worker juste après la détection (`pbm_api.worker.detect_cards_task`) — même job, pas un second
aller-retour par la file : les deux étapes du pipeline de reconnaissance partagent le
fournisseur IA de l'utilisateur déjà déchiffré pour la photo, et « un seul appel IA par carte,
dès le premier tir » (principe cadre) veut dire un appel par carte détectée, pas un job de plus.

Pour chaque détection en attente : empreinte perceptuelle du recadrage (mission point 4) —
touchée, le cache partagé répond sans appeler l'IA ; sinon un appel `AIProvider.extract`, puis
rapprochement catalogue (mission point 2), résultat écrit sur la `Detection` et mis en cache.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput
from pbm_api.ai.factory import create_provider
from pbm_api.ai.service import get_default_credential, record_usage
from pbm_api.identification.cache import find_cached, store_cache
from pbm_api.identification.extraction import extract_card
from pbm_api.identification.fingerprint import compute_phash
from pbm_api.identification.reconciliation import reconcile
from pbm_api.models import Detection, DetectionStatus, Upload, User
from pbm_api.storage import StorageBackend

_CROP_MEDIA_TYPE = "image/jpeg"  # tous les recadrages sont encodés en JPEG (detection/annotate.py)


@dataclass(frozen=True)
class IdentificationRunSummary:
    identified_count: int
    cache_hits: int
    ai_calls: int


async def _identify_one(
    session: AsyncSession,
    storage: StorageBackend,
    detection: Detection,
    ai_provider: AIProvider | None,
    ai_model: str | None,
) -> ExtractionUsage | None:
    crop_bytes = await storage.get(detection.crop_s3_key)
    if crop_bytes is None:
        return None

    crop = cv2.imdecode(np.frombuffer(crop_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    phash = compute_phash(crop)

    cached = await find_cached(session, phash)
    if cached is not None:
        detection.extraction = cached.extraction
        detection.candidates = cached.candidates
        return None

    if ai_provider is None:
        return None

    extraction, usage = await extract_card(
        ai_provider, ImageInput(data=crop_bytes, media_type=_CROP_MEDIA_TYPE), model=ai_model
    )
    result = await reconcile(session, extraction)
    candidates_payload = [c.model_dump(mode="json") for c in result.candidates]

    detection.extraction = extraction.model_dump(mode="json")
    detection.candidates = candidates_payload
    await store_cache(session, phash, extraction, candidates_payload, result.tier)
    return usage


async def run_identification_for_upload(
    db: AsyncSession, storage: StorageBackend, upload: Upload
) -> IdentificationRunSummary:
    result = await db.execute(
        select(Detection).where(
            Detection.upload_id == upload.id, Detection.status == DetectionStatus.pending
        )
    )
    detections = list(result.scalars().all())
    if not detections:
        return IdentificationRunSummary(identified_count=0, cache_hits=0, ai_calls=0)

    user = await db.get(User, upload.user_id)
    assert user is not None  # FK NOT NULL sur uploads.user_id : ne peut pas manquer ici

    ai_provider: AIProvider | None = None
    ai_model = user.ai_default_model
    credential = await get_default_credential(db, user)
    if credential is not None:
        provider_enum, api_key = credential
        ai_provider = create_provider(provider_enum, api_key)

    identified = 0
    cache_hits = 0
    ai_calls = 0
    try:
        for detection in detections:
            had_extraction_before = detection.extraction is not None
            usage = await _identify_one(db, storage, detection, ai_provider, ai_model)
            if detection.extraction is not None:
                identified += 1
                if usage is not None:
                    ai_calls += 1
                    await record_usage(db, user, usage)
                elif not had_extraction_before:
                    cache_hits += 1
    finally:
        if ai_provider is not None:
            await ai_provider.aclose()

    await db.commit()
    return IdentificationRunSummary(
        identified_count=identified, cache_hits=cache_hits, ai_calls=ai_calls
    )
