"""Envoi de photos (lot `v3-upload`) : `POST /uploads` renvoie une cible d'envoi par fichier
(URL présignée S3, ou route locale signée en backend `local` — D7) ; le navigateur y envoie
les octets directement ; `POST /uploads/{id}/complete` vérifie le type réel, supprime l'EXIF,
convertit le HEIC en JPEG et crée le job de reconnaissance si une clé IA est configurée.
"""

import uuid
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.models import User
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
)

router = APIRouter(prefix="/uploads", tags=["uploads"])

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
    """Cartes détectées sur un envoi (mission `v3-detection`) : préalable à la validation
    humaine (identification, lot ultérieur)."""
    try:
        detections = await service.list_detections(db, current_user, upload_id)
    except UploadNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "envoi introuvable") from None

    return ListDetectionsResponse(
        upload_id=upload_id,
        detections=[
            DetectionResponse(
                id=detection.id,
                reading_order=detection.bbox.get("reading_order", 0),
                status=detection.status,
                crop_url=f"/uploads/{upload_id}/detections/{detection.id}/crop",
                candidates=detection.candidates,
            )
            for detection in detections
        ],
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
