"""Schémas Pydantic exposés par `pbm_api.routers.export`."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from pbm_api.models import JobStatus


class ExportResponse(BaseModel):
    """État d'une demande d'export RGPD, renvoyé après la création et en consultation."""

    id: uuid.UUID
    status: JobStatus
    requested_at: datetime
    completed_at: datetime | None
