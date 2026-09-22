"""Orchestration DB/stockage de la détection pour un envoi (mission `v3-detection`), appelée
par le worker (`pbm_api.worker.detect_cards_task`) — logique indépendante d'arq, testable
directement.
"""

from dataclasses import dataclass

from sqlalchemy import delete
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
    db: AsyncSession, storage: StorageBackend, upload: Upload, *, force_ai: bool = False
) -> DetectionRunSummary:
    """`force_ai` : seconde passe (lot `h1-seconde-passe-ia`).

    Les détections EN ATTENTE du premier passage sont remplacées — sinon l'écran de validation
    afficherait les deux découpes côte à côte. Celles déjà validées ou rejetées par
    l'utilisateur ne sont jamais touchées : son geste prime sur notre remords.

    L'effacement n'a lieu qu'UNE FOIS la nouvelle découpe obtenue. Dans l'autre ordre, une IA
    en échec (clé épuisée, aucune boîte trouvée) laissait l'écran de validation vide après
    avoir détruit une découpe imparfaite mais utilisable.
    """
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
            force_ai=force_ai,
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_media_type=upload.content_type,
        )
    finally:
        if ai_provider is not None:
            await ai_provider.aclose()

    if result.ai_usage is not None:
        await record_usage(db, user, result.ai_usage)

    if force_ai and not result.quads:
        # Rien de neuf : on garde la découpe précédente plutôt que de laisser l'écran vide.
        await db.commit()
        return DetectionRunSummary(detections_count=0, method="seconde_passe_sans_resultat")

    if force_ai:
        await db.execute(
            delete(Detection).where(
                Detection.upload_id == upload.id, Detection.status == DetectionStatus.pending
            )
        )
        await db.commit()

    await storage.put(_control_key(upload), result.annotated_jpeg, "image/jpeg")

    for index, (quad, crop, quality) in enumerate(
        zip(result.quads, result.crops, result.qualities, strict=True)
    ):
        crop_key = _crop_key(upload, index)
        await storage.put(crop_key, encode_jpeg(crop), "image/jpeg")
        db.add(
            Detection(
                upload_id=upload.id,
                # `crop_quality` voyage dans `bbox`, qui est déjà le sac de métadonnées de
                # découpe : pas de migration pour un champ que seul l'écran de validation lit.
                bbox={
                    "reading_order": index,
                    "points": quad.tolist(),
                    "crop_quality": quality.as_dict(),
                },
                crop_s3_key=crop_key,
                status=DetectionStatus.pending,
            )
        )
        # Commit par carte, pas un seul à la fin : le flux SSE de progression (lot
        # `v3-validation`) voit les détections apparaître au fil de l'eau, et un job interrompu
        # après quelques cartes garde celles déjà découpées.
        await db.commit()

    return DetectionRunSummary(detections_count=len(result.quads), method=result.method)
