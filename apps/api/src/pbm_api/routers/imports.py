"""`POST /me/imports` — import CSV de la collection (mission `v6-import-export` point 1) : un
`Job` par fichier déposé, une `Detection` par ligne rapprochée du catalogue — l'écran de
validation existant (`GET /uploads/{id}`, `/ajouter/validation`, lot `v3-validation`) affiche et
confirme les lignes exactement comme des cartes photographiées, sans route ni écran de plus.
"""

from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.config import settings
from pbm_api.db import get_session
from pbm_api.imports import service
from pbm_api.imports.errors import ImportFileTooLargeError
from pbm_api.imports.schemas import ImportCsvResponse
from pbm_api.imports.service import ALLOWED_CONTENT_TYPES
from pbm_api.models import User
from pbm_api.queue import get_arq_pool
from pbm_api.storage import StorageBackend, build_storage

router = APIRouter(prefix="/me/imports", tags=["imports"])

_storage = build_storage()


def get_storage() -> StorageBackend:
    return _storage


@router.post("", response_model=ImportCsvResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_import(
    db: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    arq_pool: Annotated[ArqRedis, Depends(get_arq_pool)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
    file: Annotated[UploadFile, File()],
) -> ImportCsvResponse:
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"type de fichier non accepté : {file.content_type}"
        )
    data = await file.read()
    try:
        upload, job = await service.create_import(
            db, current_user, storage, file.filename or "import.csv", data
        )
    except ImportFileTooLargeError:
        max_mo = settings.import_csv_max_size_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"dépasse la taille maximale de {max_mo} Mo",
        ) from None

    # Mise en file réelle du job d'analyse (même mécanisme que `POST /uploads/{id}/complete` pour
    # `detect_cards_task`) : `service.create_import` ne fait que poser les lignes `Upload`/`Job`.
    await arq_pool.enqueue_job("import_csv_task", str(job.id))
    return ImportCsvResponse(upload_id=upload.id, job_id=job.id, status=job.status)
