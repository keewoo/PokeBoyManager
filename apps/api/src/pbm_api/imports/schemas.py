"""Schémas HTTP de l'import CSV : réponse de la route de dépôt du fichier."""

import uuid

from pydantic import BaseModel

from pbm_api.models.jobs import JobStatus


class ImportCsvResponse(BaseModel):
    """Accusé de dépôt d'un CSV : l'envoi et le job créés, à suivre par `job_id`."""

    upload_id: uuid.UUID
    job_id: uuid.UUID
    status: JobStatus
