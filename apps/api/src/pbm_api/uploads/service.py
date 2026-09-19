"""Logique métier de l'envoi de photos (mission `v3-upload`), indépendante de FastAPI.

`create_uploads` ne trouve jamais l'existence d'un envoi d'un autre utilisateur : toute
lecture/écriture passe par `user_id` du `User` déjà authentifié par la dépendance de session,
jamais par un identifiant fourni tel quel par l'appelant.
"""

import uuid

from arq.connections import ArqRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.ai.service import list_keys as list_ai_keys
from pbm_api.config import settings
from pbm_api.models import Detection, Job, JobStatus, Upload, UploadStatus, User
from pbm_api.security.upload_tokens import generate_upload_token
from pbm_api.storage import LocalObjectStorage, StorageBackend
from pbm_api.uploads.errors import (
    DetectionCropMissingError,
    DetectionNotFoundError,
    InvalidFileError,
    TooManyFilesError,
    UploadAlreadyProcessedError,
    UploadNotFoundError,
    UploadRawMissingError,
)
from pbm_api.uploads.processing import UnsupportedImageError, process_uploaded_image
from pbm_api.uploads.schemas import UploadFileRequest, UploadTarget

# Types déclarés acceptés à la création (mission point 2) — le type réel (magic bytes) est
# revérifié à `complete_upload` via `pbm_api.uploads.processing`, jamais fait confiance seul.
ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/heic", "image/heif"})

JOB_TYPE = "detect_cards"


def _validate_file(file: UploadFileRequest) -> None:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidFileError(file.filename, f"type non accepté : {file.content_type}")
    if file.size_bytes > settings.upload_max_size_bytes:
        max_mo = settings.upload_max_size_bytes // (1024 * 1024)
        raise InvalidFileError(file.filename, f"dépasse la taille maximale de {max_mo} Mo")


async def create_uploads(
    db: AsyncSession, user: User, storage: StorageBackend, files: list[UploadFileRequest]
) -> list[tuple[Upload, UploadTarget]]:
    if len(files) > settings.upload_max_files_per_batch:
        raise TooManyFilesError(
            f"{len(files)} fichiers, maximum {settings.upload_max_files_per_batch} par envoi"
        )
    for file in files:
        _validate_file(file)

    await storage.ensure_bucket()

    results: list[tuple[Upload, UploadTarget]] = []
    for file in files:
        upload_id = uuid.uuid4()
        s3_key = f"uploads/{user.id}/{upload_id}/original"
        upload = Upload(
            id=upload_id,
            user_id=user.id,
            s3_key=s3_key,
            original_filename=file.filename,
            content_type=file.content_type,
            size_bytes=file.size_bytes,
            status=UploadStatus.pending,
        )
        db.add(upload)
        target = await _build_upload_target(storage, upload, file.content_type)
        results.append((upload, target))

    await db.commit()
    return results


async def _build_upload_target(
    storage: StorageBackend, upload: Upload, content_type: str
) -> UploadTarget:
    if isinstance(storage, LocalObjectStorage):
        # Pas de service de stockage à qui déléguer un présignage : l'API se présigne une URL
        # vers sa propre route `PUT /uploads/{id}/raw`, jeton signé à durée limitée (voir
        # `pbm_api.security.upload_tokens`) — même contrat d'usage qu'un présignage S3.
        token = generate_upload_token(upload.id)
        return UploadTarget(
            upload_id=upload.id,
            method="PUT",
            url=f"/uploads/{upload.id}/raw?token={token}",
            headers={},
        )
    url = await storage.presign_put(upload.s3_key, content_type)
    return UploadTarget(
        upload_id=upload.id, method="PUT", url=url, headers={"Content-Type": content_type}
    )


async def _get_owned_upload(db: AsyncSession, user: User, upload_id: uuid.UUID) -> Upload:
    result = await db.execute(
        select(Upload).where(Upload.id == upload_id, Upload.user_id == user.id)
    )
    upload = result.scalar_one_or_none()
    if upload is None:
        raise UploadNotFoundError
    return upload


async def store_raw_bytes(
    db: AsyncSession,
    storage: StorageBackend,
    upload_id: uuid.UUID,
    data: bytes,
    content_type: str,
) -> Upload:
    """Reçoit les octets bruts pour le backend `local` (jeton signé, pas de session)."""
    result = await db.execute(select(Upload).where(Upload.id == upload_id))
    upload = result.scalar_one_or_none()
    if upload is None:
        raise UploadNotFoundError
    if upload.status != UploadStatus.pending:
        raise UploadAlreadyProcessedError

    await storage.put(upload.s3_key, data, content_type)
    upload.size_bytes = len(data)
    await db.commit()
    return upload


async def complete_upload(
    db: AsyncSession,
    user: User,
    storage: StorageBackend,
    arq_pool: ArqRedis,
    upload_id: uuid.UUID,
) -> tuple[Upload, Job | None]:
    upload = await _get_owned_upload(db, user, upload_id)
    if upload.status != UploadStatus.pending:
        raise UploadAlreadyProcessedError

    raw = await storage.get(upload.s3_key)
    if raw is None:
        raise UploadRawMissingError

    try:
        processed = process_uploaded_image(raw)
    except UnsupportedImageError:
        upload.status = UploadStatus.failed
        await db.commit()
        raise

    await storage.put(upload.s3_key, processed.data, processed.content_type)
    upload.content_type = processed.content_type
    upload.size_bytes = len(processed.data)
    upload.status = UploadStatus.processed

    # D4 : sans clé IA personnelle, la reconnaissance reste désactivée mais la photo est
    # tout de même conservée — l'ajout manuel au catalogue reste possible (hors de ce lot).
    has_ai_key = bool(await list_ai_keys(db, user))
    job: Job | None = None
    if has_ai_key:
        job = Job(
            type=JOB_TYPE,
            status=JobStatus.queued,
            user_id=user.id,
            payload={"upload_id": str(upload.id)},
        )
        db.add(job)

    await db.commit()
    if job is not None:
        await db.refresh(job)
        # Mise en file réelle du job de détection (mission `v3-detection`) : la ligne `Job`
        # seule (mission `v3-upload`) ne déclenchait encore rien côté worker. Le nom doit
        # correspondre à la fonction enregistrée dans `pbm_api.worker.WorkerSettings.functions`.
        await arq_pool.enqueue_job("detect_cards_task", str(job.id))
    return upload, job


async def list_detections(db: AsyncSession, user: User, upload_id: uuid.UUID) -> list[Detection]:
    """Détections d'un envoi (mission `v3-detection`) : l'appartenance de l'envoi à `user`
    borne toute la requête, jamais un `upload_id` seul fourni par l'appelant."""
    await _get_owned_upload(db, user, upload_id)
    result = await db.execute(select(Detection).where(Detection.upload_id == upload_id))
    detections = list(result.scalars().all())
    # Tri par ordre de lecture (mission point 1), pas par insertion : plus fiable qu'un
    # horodatage dont la précision peut être insuffisante pour départager des lignes créées
    # dans la même transaction.
    detections.sort(key=lambda d: d.bbox.get("reading_order", 0))
    return detections


async def get_detection_crop(
    db: AsyncSession,
    storage: StorageBackend,
    user: User,
    upload_id: uuid.UUID,
    detection_id: uuid.UUID,
) -> bytes:
    await _get_owned_upload(db, user, upload_id)
    result = await db.execute(
        select(Detection).where(Detection.id == detection_id, Detection.upload_id == upload_id)
    )
    detection = result.scalar_one_or_none()
    if detection is None or detection.crop_s3_key is None:
        raise DetectionNotFoundError
    data = await storage.get(detection.crop_s3_key)
    if data is None:
        raise DetectionCropMissingError
    return data
