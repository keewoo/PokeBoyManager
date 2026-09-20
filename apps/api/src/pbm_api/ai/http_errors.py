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


def _provider_error_message(response: httpx.Response) -> str | None:
    """Le corps d'erreur d'Anthropic/OpenAI est `{"error": {"message": "...", ...}}` — jamais
    la clé (ni l'un ni l'autre ne l'échoue en retour). Absent/illisible seulement sur une
    réponse qui n'est pas du JSON (proxy, coupure réseau)."""
    try:
        payload = response.json()
    except ValueError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    return message if isinstance(message, str) and message else None


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
    # des quatre cas normalisés attendus par la mission — remonté avec le message exact du
    # fournisseur (`pbm-hotfix-reconnaissance` : un `Job` en échec sans un mot exploitable a fait
    # perdre du temps de diagnostic en PROD), jamais réduit au seul code HTTP.
    provider_message = _provider_error_message(response) or detail
    message = f"Le fournisseur IA a refusé la requête ({response.status_code}) : {provider_message}"
    raise AIProviderError(message, detail=detail)
