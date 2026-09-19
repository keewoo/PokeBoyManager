"""Envoi de photos (lot `v3-upload`) : `POST /uploads` renvoie une cible d'envoi par fichier
(URL présignée S3, ou route locale signée en backend `local` — D7) ; le navigateur y envoie
les octets directement ; `POST /uploads/{id}/complete` vérifie le type réel, supprime l'EXIF,
convertit le HEIC en JPEG et crée le job de reconnaissance si une clé IA est configurée.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.models import Detection, Job, JobStatus, UploadStatus, User
from pbm_api.queue import get_arq_pool
from pbm_api.security.upload_tokens import verify_upload_token
from pbm_api.storage import StorageBackend, build_storage
from pbm_api.uploads import service
from pbm_api.uploads.errors import (
    DetectionCropMissingError,
    DetectionNotFoundError,
    InvalidFileError,
    TooManyFilesError,
    UploadAlreadyProcessedError,
    UploadNotFoundError,
    UploadRawMissingError,
)
from pbm_api.uploads.processing import UnsupportedImageError
from pbm_api.uploads.schemas import (
    CompleteUploadResponse,
    CreateUploadsRequest,
    CreateUploadsResponse,
    DetectionResponse,
    ListDetectionsResponse,
    UploadDetailResponse,
)
from pbm_api.validation.schemas import ConfirmAllResponse
from pbm_api.validation.service import confirm_all

router = APIRouter(prefix="/uploads", tags=["uploads"])

# Bornes du flux SSE de progression (mission point 1) : un intervalle court car l'écran de
# validation affiche la reconnaissance carte par carte, un plafond de durée pour ne jamais
# laisser une connexion ouverte indéfiniment si le job reste bloqué (worker arrêté, job perdu).
_SSE_POLL_INTERVAL_SECONDS = 0.7
_SSE_MAX_DURATION_SECONDS = 300


def _detection_response(upload_id: uuid.UUID, detection: Detection) -> DetectionResponse:
    return DetectionResponse(
        id=detection.id,
        reading_order=detection.bbox.get("reading_order", 0),
        status=detection.status,
        crop_url=f"/uploads/{upload_id}/detections/{detection.id}/crop",
        extraction=detection.extraction,
        candidates=detection.candidates,
        condition=detection.condition_assessment,
        identification_method=detection.identification_method,
    )

_storage = build_storage()


def get_storage() -> StorageBackend:
    return _storage


@router.post("", response_model=CreateUploadsResponse)
async def create_uploads(
    payload: CreateUploadsRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> CreateUploadsResponse:
    try:
        created = await service.create_uploads(db, current_user, storage, payload.files)
    except TooManyFilesError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    except InvalidFileError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return CreateUploadsResponse(uploads=[target for _upload, target in created])


@router.put("/{upload_id}/raw", status_code=status.HTTP_204_NO_CONTENT)
async def put_raw_upload(
    upload_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    token: str = Query(...),
) -> None:
    """Cible d'envoi du backend `local` (D7) : jeton signé à durée limitée, pas de session —
    même contrat d'usage qu'une URL présignée S3, que cette route remplace dans ce backend."""
    if not verify_upload_token(upload_id, token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "jeton d'envoi invalide ou expiré")

    content_length = request.headers.get("content-length")
    if content_length is None or int(content_length) > settings.upload_max_size_bytes:
        max_mo = settings.upload_max_size_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"dépasse la taille maximale de {max_mo} Mo"
        )

    data = await request.body()
    if len(data) > settings.upload_max_size_bytes:
        max_mo = settings.upload_max_size_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"dépasse la taille maximale de {max_mo} Mo"
        )

    content_type = request.headers.get("content-type", "application/octet-stream")
    try:
        await service.store_raw_bytes(db, storage, upload_id, data, content_type)
    except UploadNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "envoi introuvable") from None
    except UploadAlreadyProcessedError:
        raise HTTPException(status.HTTP_409_CONFLICT, "cet envoi a déjà été traité") from None


@router.post("/{upload_id}/complete", response_model=CompleteUploadResponse)
async def complete_upload(
    upload_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    arq_pool: Annotated[ArqRedis, Depends(get_arq_pool)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> CompleteUploadResponse:
    try:
        upload, job = await service.complete_upload(
            db, current_user, storage, arq_pool, upload_id
        )
    except UploadNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "envoi introuvable") from None
    except UploadAlreadyProcessedError:
        raise HTTPException(status.HTTP_409_CONFLICT, "cet envoi a déjà été traité") from None
    except UploadRawMissingError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "aucune donnée reçue pour cet envoi"
        ) from None
    except UnsupportedImageError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None

    return CompleteUploadResponse(
        upload_id=upload.id,
        status=upload.status,
        content_type=upload.content_type,
        size_bytes=upload.size_bytes,
        recognition_enabled=job is not None,
        job_id=job.id if job is not None else None,
    )


@router.get("/{upload_id}/detections", response_model=ListDetectionsResponse)
async def list_detections(
    upload_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ListDetectionsResponse:
    """Cartes détectées sur un envoi (mission `v3-detection`), avec leur extraction, leurs
    candidats catalogue une fois identifiées (mission `v3-identification`) et leur état estimé
    (mission `v3-etat`) : préalable à la validation humaine (lot `v3-validation`)."""
    try:
        detections = await service.list_detections(db, current_user, upload_id)
    except UploadNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "envoi introuvable") from None

    return ListDetectionsResponse(
        upload_id=upload_id,
        detections=[_detection_response(upload_id, detection) for detection in detections],
    )


@router.get("/{upload_id}", response_model=UploadDetailResponse)
async def get_upload(
    upload_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UploadDetailResponse:
    """État + détections d'un envoi (mission `v3-validation` point 1) : chargement initial de
    l'écran de validation, avant de bascule sur le flux SSE pour la suite de la progression."""
    try:
        upload, job, detections = await service.get_upload_detail(db, current_user, upload_id)
    except UploadNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "envoi introuvable") from None

    return UploadDetailResponse(
        upload_id=upload.id,
        status=upload.status,
        job_status=job.status if job is not None else None,
        job_error=job.error if job is not None else None,
        detections=[_detection_response(upload_id, detection) for detection in detections],
    )


def _upload_snapshot_payload(
    upload_id: uuid.UUID, upload_status: UploadStatus, job: Job | None, detections: list[Detection]
) -> dict:
    return UploadDetailResponse(
        upload_id=upload_id,
        status=upload_status,
        job_status=job.status if job is not None else None,
        job_error=job.error if job is not None else None,
        detections=[_detection_response(upload_id, detection) for detection in detections],
    ).model_dump(mode="json")


def _job_is_terminal(job: Job | None) -> bool:
    # `None` : pas de reconnaissance en file pour cet envoi (D4, pas de clé IA) — rien à
    # attendre, le premier instantané suffit.
    return job is None or job.status in (JobStatus.succeeded, JobStatus.failed)


async def _upload_events(
    db: AsyncSession, current_user: User, upload_id: uuid.UUID
) -> AsyncIterator[str]:
    """Poll plutôt que pub/sub Redis : `pbm_api.identification.service` et
    `pbm_api.detection.service` commitent au fil de l'eau (une détection à la fois) précisément
    pour que ce polling voie une progression réelle, pas seulement l'état final — même session
    réutilisée à chaque tour (isolation `READ COMMITTED` de Postgres). Seuls `upload`/`job`/
    `detections` sont expirés avant chaque lecture (jamais `db.expire_all()` : ça expirerait
    aussi `current_user`, dont l'accès à `.id` hors requête déclencherait un rechargement
    implicite hors du pont greenlet de SQLAlchemy async — `MissingGreenlet`)."""
    upload = await service.get_owned_upload(db, current_user, upload_id)
    job: Job | None = None
    detections: list[Detection] = []
    elapsed = 0.0
    last_payload: str | None = None
    while elapsed <= _SSE_MAX_DURATION_SECONDS:
        db.expire(upload)
        if job is not None:
            db.expire(job)
        for detection in detections:
            db.expire(detection)

        job = await service.get_latest_recognition_job(db, upload_id)
        detections = await service.list_detections(db, current_user, upload_id)
        payload = json.dumps(
            _upload_snapshot_payload(upload_id, upload.status, job, detections)
        )
        if payload != last_payload:
            last_payload = payload
            yield f"event: snapshot\ndata: {payload}\n\n"
        if _job_is_terminal(job):
            yield "event: done\ndata: {}\n\n"
            return
        await asyncio.sleep(_SSE_POLL_INTERVAL_SECONDS)
        elapsed += _SSE_POLL_INTERVAL_SECONDS
    yield "event: timeout\ndata: {}\n\n"


@router.get("/{upload_id}/events")
async def stream_upload_events(
    upload_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    try:
        await service.get_owned_upload(db, current_user, upload_id)
    except UploadNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "envoi introuvable") from None

    return StreamingResponse(
        _upload_events(db, current_user, upload_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{upload_id}/confirm-all", response_model=ConfirmAllResponse)
async def confirm_all_detections(
    upload_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> ConfirmAllResponse:
    """« Tout ajouter » (mission point 2) : ajoute à la collection les détections dont le
    premier candidat est présélectionné, laisse `pending` (dans `skipped`) tout le reste."""
    try:
        result = await confirm_all(db, current_user, upload_id)
    except UploadNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "envoi introuvable") from None

    return ConfirmAllResponse(
        upload_id=upload_id, confirmed=result.confirmed, skipped=result.skipped
    )


@router.get("/{upload_id}/detections/{detection_id}/crop")
async def get_detection_crop(
    upload_id: uuid.UUID,
    detection_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    try:
        data = await service.get_detection_crop(db, storage, current_user, upload_id, detection_id)
    except UploadNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "envoi introuvable") from None
    except DetectionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "détection introuvable") from None
    except DetectionCropMissingError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "recadrage introuvable dans le stockage"
        ) from None
    return Response(content=data, media_type="image/jpeg")
