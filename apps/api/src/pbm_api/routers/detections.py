"""`POST /detections/{id}/confirm` et `/reject` (lot `v3-validation`, mission point 1) : décision
humaine sur une détection déjà identifiée (ou non). Route au niveau racine, pas nichée sous
`/uploads/{upload_id}/...` comme les routes de consultation (`routers/uploads.py`) — l'écran de
validation n'a besoin que du `detection_id` pour agir, l'appartenance est vérifiée par jointure
sur `Upload.user_id` (`pbm_api.validation.service`), jamais par un `upload_id` fourni en plus.
"""

import uuid
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.models import User
from pbm_api.queue import get_arq_pool
from pbm_api.validation import service
from pbm_api.validation.errors import (
    CardNotFoundError,
    DetectionAlreadyProcessedError,
    DetectionNotFoundError,
)
from pbm_api.validation.schemas import (
    ConfirmDetectionRequest,
    ConfirmDetectionResponse,
    RejectDetectionResponse,
)

router = APIRouter(prefix="/detections", tags=["detections"])


@router.post("/{detection_id}/confirm", response_model=ConfirmDetectionResponse)
async def confirm_detection(
    detection_id: uuid.UUID,
    payload: ConfirmDetectionRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    arq_pool: Annotated[ArqRedis, Depends(get_arq_pool)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> ConfirmDetectionResponse:
    """Valide une détection et crée l'exemplaire correspondant en collection ; appartenance
    vérifiée par jointure sur `Upload.user_id`. Lève 404 si la détection ou la carte au
    catalogue est introuvable, 409 si déjà traitée.

    Enfile ensuite la préparation des **variantes de jeu** du compte (lot `j-assets-pipeline`) :
    c'est le moment « à l'ajout en collection », et il est hors de la requête du joueur — décoder
    la photo et encoder deux WebP ici l'aurait fait attendre sans raison."""
    try:
        detection, items = await service.confirm_detection(db, current_user, detection_id, payload)
    except DetectionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "détection introuvable") from None
    except DetectionAlreadyProcessedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "cette détection a déjà été validée ou rejetée"
        ) from None
    except CardNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "carte introuvable au catalogue") from None

    # Le nom doit correspondre à la fonction enregistrée dans `pbm_api.worker.WorkerSettings`.
    await arq_pool.enqueue_job("preparer_variantes_jeu_task", str(current_user.id))
    return ConfirmDetectionResponse(
        detection_id=detection.id,
        status=detection.status,
        collection_item_ids=[item.id for item in items],
    )


@router.post("/{detection_id}/reject", response_model=RejectDetectionResponse)
async def reject_detection(
    detection_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[None, Depends(require_csrf)],
) -> RejectDetectionResponse:
    """Rejette une détection, sans écrire d'exemplaire en collection ; lève 404 si introuvable,
    409 si déjà traitée."""
    try:
        detection = await service.reject_detection(db, current_user, detection_id)
    except DetectionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "détection introuvable") from None
    except DetectionAlreadyProcessedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "cette détection a déjà été validée ou rejetée"
        ) from None

    return RejectDetectionResponse(detection_id=detection.id, status=detection.status)
