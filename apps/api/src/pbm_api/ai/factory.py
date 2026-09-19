"""Fabrique un `AIProvider` à partir de l'énumération `AiProvider` — un seul point de
correspondance fournisseur -> implémentation (mission `v3-ia-providers` point 1 : changer de
fournisseur ne touche aucune fonctionnalité en aval)."""

import httpx

from pbm_api.ai.anthropic_provider import AnthropicProvider
from pbm_api.ai.base import AIProvider
from pbm_api.ai.gemini_provider import GeminiProvider
from pbm_api.ai.openai_provider import OpenAiProvider
from pbm_api.models import AiProvider as AiProviderEnum

_PROVIDER_CLASSES: dict[AiProviderEnum, type[AIProvider]] = {
    AiProviderEnum.anthropic: AnthropicProvider,
    AiProviderEnum.gemini: GeminiProvider,
    AiProviderEnum.openai: OpenAiProvider,
}


def create_provider(
    provider: AiProviderEnum, api_key: str, *, http_client: httpx.AsyncClient | None = None
) -> AIProvider:
    return _PROVIDER_CLASSES[provider](api_key, http_client=http_client)
