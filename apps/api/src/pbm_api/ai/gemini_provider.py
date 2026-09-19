"""Fournisseur Google Gemini — `generateContent`, sortie structurée native via
`generationConfig.responseSchema`, vision par `inline_data` en base64.

Gemini n'utilise pas de codes HTTP standards pour distinguer ses erreurs : un 400 couvre
aussi bien une clé invalide (`API_KEY_INVALID`) qu'une requête malformée
(`INVALID_ARGUMENT`) — la correspondance se fait sur `error.status` du corps JSON, pas sur le
seul code HTTP (voir `pbm_api.ai.providers.ProviderKeyTester`, qui a le même constat pour le
test de clé)."""

import base64
from typing import ClassVar

import httpx

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput, T
from pbm_api.ai.errors import (
    AIProviderError,
    ContentRefusedError,
    InvalidApiKeyError,
    InvalidExtractionResponseError,
    ProviderOverloadedError,
    ProviderUnreachableError,
    QuotaExceededError,
)
from pbm_api.ai.json_schema import to_gemini_schema
from pbm_api.models import AiProvider as AiProviderEnum

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_REFUSAL_FINISH_REASONS = frozenset(
    {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
)


class GeminiProvider(AIProvider):
    PROVIDER: ClassVar[AiProviderEnum] = AiProviderEnum.gemini
    DEFAULT_MODEL: ClassVar[str] = "gemini-2.5-flash"

    async def _call(
        self,
        images: list[ImageInput],
        schema: type[T],
        prompt: str,
        model: str,
        retry_hint: str | None,
    ) -> tuple[str, ExtractionUsage]:
        parts: list[dict] = [
            {
                "inline_data": {
                    "mime_type": image.media_type,
                    "data": base64.b64encode(image.data).decode("ascii"),
                }
            }
            for image in images
        ]
        parts.append({"text": _prompt_with_retry(prompt, retry_hint)})

        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": to_gemini_schema(schema),
            },
        }
        headers = {"x-goog-api-key": self._api_key, "content-type": "application/json"}
        url = f"{_BASE_URL}/{model}:generateContent"

        try:
            response = await self._client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderUnreachableError(str(exc)) from exc

        if response.status_code >= 400:
            _raise_for_gemini_error(response)

        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise InvalidExtractionResponseError("Aucun candidat dans la réponse Gemini.")
        candidate = candidates[0]

        finish_reason = candidate.get("finishReason")
        if finish_reason in _REFUSAL_FINISH_REASONS:
            raise ContentRefusedError(str(finish_reason))

        text_parts = candidate.get("content", {}).get("parts", [])
        text = next((part["text"] for part in text_parts if "text" in part), None)
        if text is None:
            raise InvalidExtractionResponseError("Aucun texte dans la réponse Gemini.")

        usage = data.get("usageMetadata", {})
        return text, ExtractionUsage(
            provider=self.PROVIDER,
            model=model,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
        )


def _raise_for_gemini_error(response: httpx.Response) -> None:
    detail = response.text[:500]
    try:
        status = response.json().get("error", {}).get("status")
    except ValueError:
        status = None

    invalid_key = status == "PERMISSION_DENIED" or (
        status == "INVALID_ARGUMENT" and "API key not valid" in detail
    )
    if invalid_key:
        raise InvalidApiKeyError(detail)
    if status == "RESOURCE_EXHAUSTED":
        raise QuotaExceededError(detail)
    if status == "UNAVAILABLE" or response.status_code >= 500:
        raise ProviderOverloadedError(detail)
    message = f"Erreur inattendue du fournisseur ({response.status_code})."
    raise AIProviderError(message, detail=detail)


def _prompt_with_retry(prompt: str, retry_hint: str | None) -> str:
    if retry_hint is None:
        return prompt
    return (
        f"{prompt}\n\nTa réponse précédente ne respectait pas le schéma attendu : {retry_hint}\n"
        "Renvoie uniquement un JSON valide conforme au schéma."
    )
