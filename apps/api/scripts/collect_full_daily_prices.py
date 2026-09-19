"""Relevé de prix sur TOUTES les cartes de la base pointée par `DATABASE_URL` — mission
`v2-catalogue-complet` point 3 (à lancer après `import_full_catalogue.py`, sur `pbm_catalogue_ref`
en général). Mesure la durée et le nombre d'appels, journal de progression périodique — pour
ajuster `pbm_api.pricing.service.TCGDEX_CONCURRENCY` si un relevé complet ne tient pas largement
dans la nuit en PROD (mission risque réseau, budget cron 06:00).

Usage :
    DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_catalogue_ref \
        uv run python scripts/collect_full_daily_prices.py
"""

import asyncio
import json
import time
from datetime import UTC, datetime

import httpx

from pbm_api.catalog.ptcg_client import PtcgClient
from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.db import async_session_factory
from pbm_api.pricing.service import EmptyPriceRunError, collect_daily_prices

PROGRESS_EVERY = 200


def _log(message: str) -> None:
    print(f"{datetime.now(UTC).isoformat()} {message}", flush=True)


async def main() -> None:
    start = time.monotonic()

    def on_progress(done: int, total: int) -> None:
        if done % PROGRESS_EVERY == 0 or done == total:
            elapsed = time.monotonic() - start
            rate = done / elapsed if elapsed > 0 else 0
            _log(f"cardmarket {done}/{total} — {rate:.1f} cartes/s — écoulé {elapsed:.0f}s")

    async with (
        httpx.AsyncClient(timeout=30.0) as tcgdex_http,
        httpx.AsyncClient(timeout=20.0) as ptcg_http,
        async_session_factory() as session,
    ):
        tcgdex = TcgdexClient(http_client=tcgdex_http)
        ptcg = PtcgClient(http_client=ptcg_http)
        _log("relevé complet démarré (Cardmarket + TCGplayer)")
        try:
            report = await collect_daily_prices(
                session, tcgdex, ptcg, progress_callback=on_progress
            )
        except EmptyPriceRunError as exc:
            _log(f"relevé vide : {exc}")
            raise

    elapsed = time.monotonic() - start
    report["duration_seconds"] = round(elapsed, 1)
    _log(f"relevé complet terminé en {elapsed:.0f}s")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
