"""Essai manuel réel du job d'import (échantillon, réseau chimera ~250 ko/s — voir compte rendu).

Ne consomme aucune clé IA : TCGdex et Pokémon TCG API sont publics et sans clé. Usage :
    uv run python scripts/run_sample_import.py hgssp base1
"""

import asyncio
import json
import sys

import httpx

from pbm_api.catalog.import_service import import_catalogue
from pbm_api.catalog.ptcg_client import PtcgClient
from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.db import async_session_factory


async def main(set_ids: list[str]) -> None:
    async with (
        httpx.AsyncClient(timeout=30.0) as tcgdex_http,
        httpx.AsyncClient(timeout=20.0) as ptcg_http,
        async_session_factory() as session,
    ):
        tcgdex = TcgdexClient(http_client=tcgdex_http)
        ptcg = PtcgClient(http_client=ptcg_http)
        report = await import_catalogue(
            session, tcgdex, ptcg, languages=("fr", "en"), set_ids=set_ids, mode="full"
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
