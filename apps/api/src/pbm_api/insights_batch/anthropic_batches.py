"""Client fin pour la Message Batches API d'Anthropic (`/v1/messages/batches`) — asynchrone,
moitié prix, jusqu'à 100 000 requêtes ou 256 Mo par lot (vérifié le 20/09/2026 sur
https://platform.claude.com/docs/en/build-with-claude/batch-processing). Aucun autre module de
`pbm_api.ai` ne couvre cette API : `AIProvider.extract` (mission `v3-ia-providers`) est
volontairement synchrone, un aller-retour immédiat par appel — un fournisseur de plus ici
casserait cette hypothèse pour tout le reste du dépôt.

`custom_id` porte l'UUID de la carte (regex Anthropic `^[a-zA-Z0-9_-]{1,64}$` — un UUID avec
tirets tient dans les 64 caractères) : les résultats reviennent dans un ordre non garanti,
`custom_id` est la seule clé de rapprochement fiable (documenté par Anthropic).
"""

import json
from dataclasses import dataclass
from typing import Any

import httpx

_URL = "https://api.anthropic.com/v1/messages/batches"
_ANTHROPIC_VERSION = "2023-06-01"


class BatchApiError(Exception):
    """Réponse HTTP en échec de la Message Batches API — jamais avalée, le lot s'arrête."""


@dataclass
class BatchStatus:
    batch_id: str
    processing_status: str  # "in_progress" | "canceling" | "ended"
    request_counts: dict[str, int]
    results_url: str | None


@dataclass
class BatchResultItem:
    custom_id: str
    result_type: str  # "succeeded" | "errored" | "canceled" | "expired"
    text: str | None
    input_tokens: int
    output_tokens: int
    error: str | None


def build_batch_request(
    *, custom_id: str, model: str, max_tokens: int, prompt: str, json_schema: dict[str, Any]
) -> dict[str, Any]:
    return {
        "custom_id": custom_id,
        "params": {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"format": {"type": "json_schema", "schema": json_schema}},
        },
    }


class AnthropicBatchClient:
    def __init__(self, api_key: str, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._headers = {
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        self._client = http_client or httpx.AsyncClient(timeout=60.0)
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def create_batch(self, requests: list[dict[str, Any]]) -> BatchStatus:
        try:
            response = await self._client.post(
                _URL, json={"requests": requests}, headers=self._headers
            )
        except httpx.HTTPError as exc:
            raise BatchApiError(f"création du lot Anthropic injoignable : {exc}") from exc
        if response.status_code >= 400:
            raise BatchApiError(
                f"création du lot Anthropic en échec ({response.status_code}) : {response.text}"
            )
        return _status_from_json(response.json())

    async def get_batch(self, batch_id: str) -> BatchStatus:
        try:
            response = await self._client.get(f"{_URL}/{batch_id}", headers=self._headers)
        except httpx.HTTPError as exc:
            raise BatchApiError(f"suivi du lot Anthropic injoignable : {exc}") from exc
        if response.status_code >= 400:
            raise BatchApiError(
                f"suivi du lot Anthropic en échec ({response.status_code}) : {response.text}"
            )
        return _status_from_json(response.json())

    async def iter_results(self, results_url: str) -> list[BatchResultItem]:
        """Le flux est un `.jsonl` (une ligne = un résultat) — pas de pagination côté Anthropic,
        toute la liste tient en mémoire (au plus `insights_batch_chunk_size` lignes par lot,
        bien en-deçà de la limite de 100 000 requêtes)."""
        items: list[BatchResultItem] = []
        try:
            async with self._client.stream(
                "GET", results_url, headers=self._headers
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    raise BatchApiError(
                        f"résultats du lot Anthropic en échec ({response.status_code}) : "
                        f"{body.decode(errors='replace')}"
                    )
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    items.append(_result_item_from_json(json.loads(line)))
        except httpx.HTTPError as exc:
            raise BatchApiError(f"résultats du lot Anthropic injoignables : {exc}") from exc
        return items


def _status_from_json(data: dict[str, Any]) -> BatchStatus:
    return BatchStatus(
        batch_id=data["id"],
        processing_status=data["processing_status"],
        request_counts=data.get("request_counts", {}),
        results_url=data.get("results_url"),
    )


def _result_item_from_json(data: dict[str, Any]) -> BatchResultItem:
    custom_id = data["custom_id"]
    result = data.get("result", {})
    result_type = result.get("type", "errored")

    text: str | None = None
    input_tokens = 0
    output_tokens = 0
    error: str | None = None

    if result_type == "succeeded":
        message = result.get("message", {})
        text = next(
            (block["text"] for block in message.get("content", []) if block.get("type") == "text"),
            None,
        )
        usage = message.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
    else:
        error = json.dumps(result.get("error", result))

    return BatchResultItem(
        custom_id=custom_id,
        result_type=result_type,
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=error,
    )
