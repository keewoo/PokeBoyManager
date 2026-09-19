import uuid

from pydantic import BaseModel, Field

from pbm_api.models.collection import DetectionStatus, UploadStatus
from pbm_api.models.jobs import JobStatus


class UploadFileRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(gt=0)


class CreateUploadsRequest(BaseModel):
    files: list[UploadFileRequest] = Field(min_length=1)


class UploadTarget(BaseModel):
    upload_id: uuid.UUID
    method: str
    url: str
    headers: dict[str, str]


class CreateUploadsResponse(BaseModel):
    uploads: list[UploadTarget]


class CompleteUploadResponse(BaseModel):
    upload_id: uuid.UUID
    status: UploadStatus
    content_type: str
    size_bytes: int
    recognition_enabled: bool
    job_id: uuid.UUID | None


class DetectionResponse(BaseModel):
    id: uuid.UUID
    reading_order: int
    status: DetectionStatus
    crop_url: str
    extraction: dict | None
    candidates: list | None
    condition: dict | None


class ListDetectionsResponse(BaseModel):
    upload_id: uuid.UUID
    detections: list[DetectionResponse]


class UploadDetailResponse(BaseModel):
    """`GET /uploads/{id}` (mission `v3-validation` point 1) : état de l'envoi et de sa
    reconnaissance — chargement initial de l'écran de validation, et forme des instantanés du
    flux SSE `GET /uploads/{id}/events`."""

    upload_id: uuid.UUID
    status: UploadStatus
    # `None` : aucune clé IA au moment de l'envoi (D4), la reconnaissance n'a jamais été mise en
    # file — l'ajout manuel reste possible mais il n'y a rien à valider ici.
    job_status: JobStatus | None
    job_error: str | None
    detections: list[DetectionResponse]
