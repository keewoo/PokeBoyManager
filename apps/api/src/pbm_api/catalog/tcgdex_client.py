"""Client TCGdex (https://api.tcgdex.net) — source principale du catalogue (D3)."""

from urllib.parse import quote

import httpx

TCGDEX_BASE_URL = "https://api.tcgdex.net/v2"


def _segment(value: str) -> str:
    """Encode un identifiant pour l'insérer dans un chemin d'URL.

    Indispensable parce que TCGdex publie certains identifiants **déjà** percent-encodés dans
    ses propres données : le Zarbi « ? » de l'extension `exu` a `id="exu-%3F"`. Repasser cette
    chaîne telle quelle dans l'URL donne `/cards/exu-%3F`, que l'API décode en `exu-?` et ne
    reconnaît pas (404 vérifié le 2026-09-22) ; il faut encoder le `%` lui-même, donc demander
    `/cards/exu-%253F`, qui répond 200. Sans ça cette carte manquait en base, seule des ~22 000.
    Les identifiants ordinaires (`sv03.5-006`, `swsh4-21`) traversent `quote` inchangés.
    """
    return quote(value, safe="")


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
        response = await self._client.get(f"{self._base_url}/{lang}/sets/{_segment(set_id)}")
        response.raise_for_status()
        return response.json()

    async def get_card(self, lang: str, card_id: str) -> dict:
        """Détail complet d'une carte (attaques, talents, illustrateur, légalités, rareté...)."""
        response = await self._client.get(f"{self._base_url}/{lang}/cards/{_segment(card_id)}")
        response.raise_for_status()
        return response.json()

    async def fetch_image_bytes(self, image_base_url: str, size: str) -> bytes:
        """Télécharge l'image officielle (`size` = "high" ou "low") — utilisé par le proxy."""
        response = await self._client.get(f"{image_base_url}/{size}.webp")
        response.raise_for_status()
        return response.content
