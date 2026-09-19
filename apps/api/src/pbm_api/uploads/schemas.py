import uuid

from pydantic import BaseModel, Field

from pbm_api.models.collection import DetectionStatus, UploadStatus


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


class ListDetectionsResponse(BaseModel):
    upload_id: uuid.UUID
    detections: list[DetectionResponse]
