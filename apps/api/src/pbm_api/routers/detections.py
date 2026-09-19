"""`POST /detections/{id}/confirm` et `/reject` (lot `v3-validation`, mission point 1) : décision
humaine sur une détection déjà identifiée (ou non). Route au niveau racine, pas nichée sous
`/uploads/{upload_id}/...` comme les routes de consultation (`routers/uploads.py`) — l'écran de
validation n'a besoin que du `detection_id` pour agir, l'appartenance est vérifiée par jointure
sur `Upload.user_id` (`pbm_api.validation.service`), jamais par un `upload_id` fourni en plus.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import get_current_user, require_csrf
from pbm_api.db import get_session
from pbm_api.models import User
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
    _csrf: Annotated[None, Depends(require_csrf)],
) -> ConfirmDetectionResponse:
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
    try:
        detection = await service.reject_detection(db, current_user, detection_id)
    except DetectionNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "détection introuvable") from None
    except DetectionAlreadyProcessedError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "cette détection a déjà été validée ou rejetée"
        ) from None

    return RejectDetectionResponse(detection_id=detection.id, status=detection.status)
