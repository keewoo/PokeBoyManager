"""Fournisseur Anthropic — Messages API (`POST /v1/messages`), sortie structurée native via
`output_config.format` (JSON Schema), vision par blocs `image` en base64."""

import base64
from typing import ClassVar

import httpx

from pbm_api.ai.base import AIProvider, ExtractionUsage, ImageInput, T
from pbm_api.ai.errors import (
    ContentRefusedError,
    InvalidExtractionResponseError,
    ProviderUnreachableError,
)
from pbm_api.ai.http_errors import raise_for_status
from pbm_api.ai.json_schema import to_strict_schema
from pbm_api.models import AiProvider as AiProviderEnum

_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_TOKENS = 4096


class AnthropicProvider(AIProvider):
    PROVIDER: ClassVar[AiProviderEnum] = AiProviderEnum.anthropic
    DEFAULT_MODEL: ClassVar[str] = "claude-sonnet-5"
    ECONOMY_MODEL: ClassVar[str | None] = "claude-haiku-4-5"

    async def _call(
        self,
        images: list[ImageInput],
        schema: type[T],
        prompt: str,
        model: str,
        retry_hint: str | None,
    ) -> tuple[str, ExtractionUsage]:
        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.media_type,
                    "data": base64.b64encode(image.data).decode("ascii"),
                },
            }
            for image in images
        ]
        content.append({"type": "text", "text": _prompt_with_retry(prompt, retry_hint)})

        body = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "messages": [{"role": "user", "content": content}],
            "output_config": {
                "format": {"type": "json_schema", "schema": to_strict_schema(schema)}
            },
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            response = await self._client.post(_URL, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderUnreachableError(str(exc)) from exc

        raise_for_status(response)
        data = response.json()

        if data.get("stop_reason") == "refusal":
            stop_details = data.get("stop_details") or {}
            raise ContentRefusedError(str(stop_details))

        text = next(
            (block["text"] for block in data.get("content", []) if block.get("type") == "text"),
            None,
        )
        if text is None:
            raise InvalidExtractionResponseError("Aucun bloc texte dans la réponse Anthropic.")

        usage = data.get("usage", {})
        return text, ExtractionUsage(
            provider=self.PROVIDER,
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )


def _prompt_with_retry(prompt: str, retry_hint: str | None) -> str:
    if retry_hint is None:
        return prompt
    return (
        f"{prompt}\n\nTa réponse précédente ne respectait pas le schéma attendu : {retry_hint}\n"
        "Renvoie uniquement un JSON valide conforme au schéma."
    )
