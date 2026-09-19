import uuid
from datetime import datetime

from pydantic import BaseModel

from pbm_api.models import JobStatus


class ExportResponse(BaseModel):
    id: uuid.UUID
    status: JobStatus
    requested_at: datetime
    completed_at: datetime | None
