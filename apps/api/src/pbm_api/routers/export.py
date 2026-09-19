"""Export RGPD de la collection (lot `v5-rgpd`) : `POST /me/export` crée le `DataExport` et
l'enfile vers le worker arq (comme `POST /uploads/{id}/complete`, mission `v3-detection`, pour
`detect_cards_task` — `pbm_api.export.service.run_export` fait le travail réel, appelé depuis
`pbm_api.worker.export_user_data_task`), `GET /me/export/{id}` en suit le statut, `GET
/export/download` sert l'archive à qui détient le jeton reçu par e-mail — jamais par cookie de
session, le lien doit fonctionner même ouvert depuis un autre navigateur."""

import uuid
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.export import service
from pbm_api.export.errors import (
    ExportArchiveMissingError,
    ExportNotFoundError,
    ExportTokenInvalidError,
)
from pbm_api.export.schemas import ExportResponse
from pbm_api.models import User
from pbm_api.queue import get_arq_pool
from pbm_api.storage import StorageBackend, build_storage

router = APIRouter(tags=["export"])

_storage = build_storage()

EXPORT_NOT_FOUND_MESSAGE = "Export introuvable."
TOKEN_INVALID_MESSAGE = "Lien de téléchargement invalide ou expiré."
ARCHIVE_MISSING_MESSAGE = "Archive introuvable — réessaie de préparer un nouvel export."


def get_storage() -> StorageBackend:
    return _storage


def _to_response(export) -> ExportResponse:
    return ExportResponse(
        id=export.id,
        status=export.status,
        requested_at=export.created_at,
        completed_at=export.completed_at,
    )


@router.post("/me/export", response_model=ExportResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_export(
    db: Annotated[AsyncSession, Depends(get_session)],
    arq_pool: Annotated[ArqRedis, Depends(get_arq_pool)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> ExportResponse:
    export = await service.create_export(db, current_user)
    await arq_pool.enqueue_job("export_user_data_task", str(export.id))
    return _to_response(export)


@router.get("/me/export/{export_id}", response_model=ExportResponse)
async def get_export(
    export_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ExportResponse:
    try:
        export = await service.get_owned_export(db, current_user, export_id)
    except ExportNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, EXPORT_NOT_FOUND_MESSAGE) from None
    return _to_response(export)


@router.get("/export/download")
async def download_export(
    db: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
    token: str = Query(...),
) -> Response:
    try:
        export, data = await service.download_by_token(db, storage, token)
    except ExportTokenInvalidError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TOKEN_INVALID_MESSAGE) from None
    except ExportArchiveMissingError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ARCHIVE_MISSING_MESSAGE) from None
    filename = f"pokeboymanager-export-{export.id}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
