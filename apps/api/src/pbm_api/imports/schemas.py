import uuid

from pydantic import BaseModel

from pbm_api.models.jobs import JobStatus


class ImportCsvResponse(BaseModel):
    upload_id: uuid.UUID
    job_id: uuid.UUID
    status: JobStatus
