"""Étape LOURDE quotidienne, à lancer sur la flotte (chimera) contre `pbm_catalogue_ref` — jamais
sur la machine qui sert (lot `pbm-jobs-flotte`). Relève, pour TOUTES les cartes, les prix du jour
(Cardmarket via TCGdex + TCGplayer via Pokémon TCG API) et les taux de change BCE, dans la base
pointée par `DATABASE_URL`. Le RÉSULTAT (lignes du jour) est ensuite exporté puis importé en PROD
par une commande courte (voir `infra/fleet/`), sans jamais rejouer ce relevé sur le serveur.

Rien de neuf ici : réutilise `collect_daily_prices` (mission `v2-prix`) et le relevé de taux BCE
déjà écrits — c'est leur LIEU d'exécution qui change, pas leur logique. `card_value_rank` n'est
PAS rafraîchie ici (la base de référence n'est pas servie) : elle l'est côté PROD après l'import.

Usage :
    DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_catalogue_ref \
        uv run python scripts/fleet_reference_daily.py
Sortie : un rapport JSON sur stdout (dernière ligne = objet JSON, parsable par l'orchestrateur).
"""

import asyncio
import json
import time
from datetime import UTC, datetime

import httpx

from pbm_api.catalog.ptcg_client import PtcgClient
from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.db import async_session_factory
from pbm_api.pricing.exchange_rates import EcbClient, store_daily_rates
from pbm_api.pricing.service import EmptyPriceRunError, collect_daily_prices

PROGRESS_EVERY = 500


def _log(message: str) -> None:
    print(f"{datetime.now(UTC).isoformat()} {message}", flush=True)


async def _collect_rates(report: dict) -> None:
    """Taux BCE d'abord : rapides et indépendants du catalogue. Une panne ici n'empêche pas le
    relevé de prix (mais est consignée, jamais avalée) — les prix EUR (Cardmarket) n'en dépendent
    pas ; seule la conversion USD→EUR (TCGplayer) s'appuie sur le taux le plus récent connu."""
    async with httpx.AsyncClient(timeout=20.0) as ecb_http:
        ecb = EcbClient(http_client=ecb_http)
        try:
            published_day, rates = await ecb.fetch_daily_rates()
            async with async_session_factory() as session:
                written = await store_daily_rates(session, published_day, rates)
            report["exchange_rates_day"] = published_day.isoformat()
            report["exchange_rates_written"] = written
            _log(f"taux BCE {published_day.isoformat()} : {written} devises")
        except Exception as exc:  # noqa: BLE001 — consigné, non fatal pour le relevé de prix
            report["exchange_rates_error"] = str(exc)
            _log(f"⚠ taux BCE en échec : {exc}")


async def main() -> None:
    start = time.monotonic()
    report: dict = {"started_at": datetime.now(UTC).isoformat()}

    await _collect_rates(report)

    def on_progress(done: int, total: int) -> None:
        if done % PROGRESS_EVERY == 0 or done == total:
            elapsed = time.monotonic() - start
            rate = done / elapsed if elapsed > 0 else 0
            _log(f"prix cardmarket {done}/{total} — {rate:.1f} cartes/s — écoulé {elapsed:.0f}s")

    async with (
        httpx.AsyncClient(timeout=30.0) as tcgdex_http,
        httpx.AsyncClient(timeout=20.0) as ptcg_http,
        async_session_factory() as session,
    ):
        tcgdex = TcgdexClient(http_client=tcgdex_http)
        ptcg = PtcgClient(http_client=ptcg_http)
        _log("relevé de prix complet démarré (Cardmarket + TCGplayer)")
        try:
            price_report = await collect_daily_prices(
                session, tcgdex, ptcg, progress_callback=on_progress
            )
        except EmptyPriceRunError as exc:
            # Relevé vide alors que le catalogue contient des cartes : PANNE, jamais un succès
            # silencieux — l'orchestrateur ne doit pas exporter/importer un bundle vide.
            report["error"] = str(exc)
            _log(f"⛔ relevé vide : {exc}")
            print(json.dumps(report, ensure_ascii=False))
            raise SystemExit(1) from exc
    report.update(price_report)
    report["duration_seconds"] = round(time.monotonic() - start, 1)
    _log(f"relevé terminé en {report['duration_seconds']:.0f}s")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
