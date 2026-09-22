import uuid
from datetime import datetime

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
    # "visuel" (index visuel, aucun appel IA), "ia", "aucun" ou `None` (pas encore traitée) —
    # mission `v3-identification-visuelle` : sert uniquement au badge « reconnue sans IA ».
    identification_method: str | None
    # `{"seam": bool, "score": float, "axis": str|None}` (lot `h1-decoupe-fiable`) — `None` pour
    # les détections antérieures au lot et pour les lignes d'import CSV, qui n'ont pas de photo.
    crop_quality: dict | None = None


class ListDetectionsResponse(BaseModel):
    upload_id: uuid.UUID
    detections: list[DetectionResponse]


class PendingUploadItem(BaseModel):
    upload_id: uuid.UUID
    created_at: datetime
    pending_count: int
    total_count: int


class PendingUploadsResponse(BaseModel):
    """`GET /uploads/pending-validation` (lot `pbm-parcours-validation`, mission point 2) : les
    envois de l'utilisateur qui ont encore des cartes à valider — point d'entrée de reprise depuis
    « Ajouter des photos »."""

    uploads: list[PendingUploadItem]


class RetryRecognitionResponse(BaseModel):
    upload_id: uuid.UUID
    job_id: uuid.UUID
    status: JobStatus


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
