"""Client TCGdex (https://api.tcgdex.net) — source principale du catalogue (D3)."""

import httpx

TCGDEX_BASE_URL = "https://api.tcgdex.net/v2"


class TcgdexClient:
    """Enveloppe fine autour de l'API TCGdex v2, sans clé (service public)."""

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        base_url: str = TCGDEX_BASE_URL,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(timeout=30.0)
        self._base_url = base_url
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def list_sets(self, lang: str) -> list[dict]:
        """Résumé de toutes les extensions dans une langue (id, name, cardCount)."""
        response = await self._client.get(f"{self._base_url}/{lang}/sets")
        response.raise_for_status()
        return response.json()

    async def get_set(self, lang: str, set_id: str) -> dict:
        """Détail d'une extension, avec le résumé de ses cartes (id, localId, name, image)."""
        response = await self._client.get(f"{self._base_url}/{lang}/sets/{set_id}")
        response.raise_for_status()
        return response.json()

    async def get_card(self, lang: str, card_id: str) -> dict:
        """Détail complet d'une carte (attaques, talents, illustrateur, légalités, rareté...)."""
        response = await self._client.get(f"{self._base_url}/{lang}/cards/{card_id}")
        response.raise_for_status()
        return response.json()

    async def fetch_image_bytes(self, image_base_url: str, size: str) -> bytes:
        """Télécharge l'image officielle (`size` = "high" ou "low") — utilisé par le proxy."""
        response = await self._client.get(f"{image_base_url}/{size}.webp")
        response.raise_for_status()
        return response.content
