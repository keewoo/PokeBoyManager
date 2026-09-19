from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from pbm_api.models import AiProvider

# Champs dont la valeur soumise ne doit jamais revenir dans une réponse 422 : voir
# `pbm_api.security.validation_errors` (`hide_input_in_errors` de pydantic ne redacte que la
# représentation texte de l'exception, pas les dictionnaires structurés que FastAPI sérialise).
SENSITIVE_FIELD_NAMES = frozenset({"api_key"})


class AiKeyUpsertRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)


class AiKeyTestRequest(BaseModel):
    api_key: str | None = Field(default=None, min_length=8, max_length=512)


class AiKeyTestResponse(BaseModel):
    valid: bool
    message: str


class AiKeyResponse(BaseModel):
    provider: AiProvider
    key_mask: str
    created_at: datetime
    updated_at: datetime


class AiSettingsResponse(BaseModel):
    default_provider: AiProvider | None
    default_model: str | None


class AiSettingsUpdateRequest(BaseModel):
    default_provider: AiProvider | None = None
    default_model: str | None = None


class AiUsageEntry(BaseModel):
    provider: AiProvider
    period: date
    calls_count: int
    tokens_count: int
    estimated_cost_eur: Decimal
