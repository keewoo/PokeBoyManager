"""Schémas Pydantic des routes du coffre de clés IA (`/me/ai-keys`, `/me/ai-settings`,
`/me/ai-usage`)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from pbm_api.models import AiProvider

# Champs dont la valeur soumise ne doit jamais revenir dans une réponse 422 : voir
# `pbm_api.security.validation_errors` (`hide_input_in_errors` de pydantic ne redacte que la
# représentation texte de l'exception, pas les dictionnaires structurés que FastAPI sérialise).
SENSITIVE_FIELD_NAMES = frozenset({"api_key"})


class AiKeyUpsertRequest(BaseModel):
    """Corps de `PUT /me/ai-keys/{provider}` — la clé en clair, jamais renvoyée ensuite."""

    api_key: str = Field(min_length=8, max_length=512)


class AiKeyTestRequest(BaseModel):
    """Corps de `POST /me/ai-keys/{provider}/test` — clé à tester, ou absente pour tester celle
    déjà enregistrée."""

    api_key: str | None = Field(default=None, min_length=8, max_length=512)


class AiKeyTestResponse(BaseModel):
    """Résultat du test de clé (`ProviderKeyTester.test`) : validité et message à afficher."""

    valid: bool
    message: str


class AiKeyResponse(BaseModel):
    """Clé enregistrée exposée à l'utilisateur — masquée (`key_mask`), jamais en clair."""

    provider: AiProvider
    key_mask: str
    created_at: datetime
    updated_at: datetime


class AiSettingsResponse(BaseModel):
    """Fournisseur, modèle IA par défaut et activation du coach de l'utilisateur."""

    default_provider: AiProvider | None
    default_model: str | None
    # Coach IA activé (lot `j-coach-ia`) : conseils en partie + bilan de fin. Vrai par défaut.
    coach_actif: bool = True


class AiSettingsUpdateRequest(BaseModel):
    """Corps de `PATCH /me/ai-settings` — `None` explicite efface le réglage."""

    default_provider: AiProvider | None = None
    default_model: str | None = None
    # Activer/désactiver le coach IA (lot `j-coach-ia`) ; absent = inchangé.
    coach_actif: bool | None = None


class AiUsageEntry(BaseModel):
    """Compteurs d'usage IA d'un fournisseur pour une période mensuelle donnée."""

    provider: AiProvider
    period: date
    calls_count: int
    tokens_count: int
    estimated_cost_eur: Decimal
