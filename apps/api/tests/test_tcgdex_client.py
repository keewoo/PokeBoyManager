"""Client TCGdex — construction des URL, sans réseau (transport simulé httpx).

Le cas qui motive ce fichier : TCGdex publie certains identifiants **déjà** percent-encodés dans
ses propres données. Le Zarbi « ? » de l'extension `exu` a `id="exu-%3F"` ; redemander cette
chaîne telle quelle donne un 404 (vérifié en direct le 2026-09-22), et cette carte manquait en
base — seule des ~22 000, donc parfaitement invisible sans un contrôle dédié.
"""

import httpx

from pbm_api.catalog.tcgdex_client import TcgdexClient


def _recording_client(seen: list[str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"id": "x", "localId": "1", "name": "X"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_get_card_percent_encodes_an_already_encoded_id():
    seen: list[str] = []
    async with _recording_client(seen) as http:
        await TcgdexClient(http_client=http).get_card("fr", "exu-%3F")

    assert "exu-%253F" in seen[0], seen
    # La forme naïve est justement celle que l'API refuse : elle ne doit pas être émise.
    assert "exu-%3F" not in seen[0], seen


async def test_get_card_leaves_ordinary_ids_untouched():
    seen: list[str] = []
    async with _recording_client(seen) as http:
        await TcgdexClient(http_client=http).get_card("fr", "sv03.5-006")

    assert seen[0].endswith("/v2/fr/cards/sv03.5-006"), seen


async def test_get_set_leaves_ordinary_ids_untouched():
    seen: list[str] = []
    async with _recording_client(seen) as http:
        await TcgdexClient(http_client=http).get_set("en", "sv03.5")

    assert seen[0].endswith("/v2/en/sets/sv03.5"), seen
