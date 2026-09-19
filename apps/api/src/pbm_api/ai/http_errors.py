"""Correspondance code HTTP -> erreur normalisée, commune à Anthropic et OpenAI (401/429/5xx
classiques). Gemini a sa propre correspondance (`error.status` JSON plutôt que le code HTTP
seul — un 400 y couvre aussi bien une clé invalide qu'une requête malformée) : voir
`gemini_provider.py`."""

import httpx

from pbm_api.ai.errors import (
    AIProviderError,
    InvalidApiKeyError,
    ProviderOverloadedError,
    QuotaExceededError,
)


def raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    detail = response.text[:500]
    if response.status_code in (401, 403):
        raise InvalidApiKeyError(detail)
    if response.status_code == 429:
        raise QuotaExceededError(detail)
    if response.status_code >= 500:
        raise ProviderOverloadedError(detail)
    # Un 4xx hors clé/quota (ex. 400 sur une requête malformée) est une vraie panne, pas l'un
    # des quatre cas normalisés attendus par la mission — remonté tel quel plutôt que
    # rattaché arbitrairement à un des quatre buckets.
    message = f"Erreur inattendue du fournisseur ({response.status_code})."
    raise AIProviderError(message, detail=detail)
