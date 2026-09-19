"""Fournisseur OpenAI — Chat Completions (`POST /v1/chat/completions`), sortie structurée
native via `response_format` en mode strict, vision par `image_url` en data URI base64."""

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

_URL = "https://api.openai.com/v1/chat/completions"
_MAX_TOKENS = 4096


class OpenAiProvider(AIProvider):
    PROVIDER: ClassVar[AiProviderEnum] = AiProviderEnum.openai
    DEFAULT_MODEL: ClassVar[str] = "gpt-4o"

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
                "type": "image_url",
                "image_url": {"url": _data_uri(image)},
            }
            for image in images
        ]
        content.append({"type": "text", "text": _prompt_with_retry(prompt, retry_hint)})

        body = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "messages": [{"role": "user", "content": content}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": to_strict_schema(schema),
                    "strict": True,
                },
            },
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "content-type": "application/json"}

        try:
            response = await self._client.post(_URL, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderUnreachableError(str(exc)) from exc

        raise_for_status(response)
        data = response.json()

        choice = data["choices"][0]
        if choice.get("finish_reason") == "content_filter":
            raise ContentRefusedError(str(choice))

        text = choice.get("message", {}).get("content")
        if text is None:
            raise InvalidExtractionResponseError("Aucun contenu dans la réponse OpenAI.")

        usage = data.get("usage", {})
        return text, ExtractionUsage(
            provider=self.PROVIDER,
            model=model,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )


def _data_uri(image: ImageInput) -> str:
    encoded = base64.b64encode(image.data).decode("ascii")
    return f"data:{image.media_type};base64,{encoded}"


def _prompt_with_retry(prompt: str, retry_hint: str | None) -> str:
    if retry_hint is None:
        return prompt
    return (
        f"{prompt}\n\nTa réponse précédente ne respectait pas le schéma attendu : {retry_hint}\n"
        "Renvoie uniquement un JSON valide conforme au schéma."
    )
