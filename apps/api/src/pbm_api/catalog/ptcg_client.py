"""Client Pokémon TCG API (https://api.pokemontcg.io) — rapprochement (ptcg_id, légalités).

Observé flaky le 2026-09-19 (500/502 par intermittence, y compris sur `/sets` en pleine liste) :
le client réessaie avec un backoff, et lève `PtcgUnavailableError` plutôt que d'avaler l'échec —
l'appelant (import_service) dégrade alors explicitement plutôt que d'inventer un rapprochement.
"""

import asyncio

import httpx

PTCG_BASE_URL = "https://api.pokemontcg.io/v2"


class PtcgUnavailableError(RuntimeError):
    """L'API Pokémon TCG n'a pas répondu correctement après toutes les tentatives."""


class PtcgClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = PTCG_BASE_URL,
        max_attempts: int = 3,
        backoff_seconds: float = 2.0,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(timeout=20.0)
        self._base_url = base_url
        self._owns_client = http_client is None
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.get(f"{self._base_url}{path}", params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_error = exc
                if attempt < self._max_attempts:
                    await asyncio.sleep(self._backoff_seconds * attempt)
        raise PtcgUnavailableError(
            f"Pokémon TCG API indisponible après {self._max_attempts} tentatives sur {path} : "
            f"{last_error}"
        ) from last_error

    async def list_sets(self) -> list[dict]:
        data = await self._get("/sets", params={"pageSize": 250})
        return data["data"]

    async def list_cards_in_set(self, ptcg_set_id: str) -> list[dict]:
        data = await self._get(
            "/cards", params={"q": f"set.id:{ptcg_set_id}", "pageSize": 250}
        )
        return data["data"]
