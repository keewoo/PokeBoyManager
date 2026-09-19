"""Import COMPLET du catalogue TCGdex (FR+EN, toutes extensions) — mission `v2-catalogue-complet`
point 2. Cible la base pointée par `DATABASE_URL` (`pbm_catalogue_ref` sur l'infra partagée) ;
idempotent et reprenable (`import_catalogue` commit par extension) — un arrêt en cours de route
ne perd pas le travail déjà validé, relancer ce script reprend en mettant à jour les extensions
déjà vues et en complétant les nouvelles.

Usage :
    DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_catalogue_ref \
        uv run python scripts/import_full_catalogue.py

Journal de progression (une ligne par extension, horodatée) sur stdout — à rediriger vers un
fichier pour un import de plusieurs dizaines de minutes.
"""

import asyncio
import json
import time
from datetime import UTC, datetime

import httpx

from pbm_api.catalog.import_service import import_catalogue
from pbm_api.catalog.ptcg_client import PtcgClient
from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.db import async_session_factory


def _log(message: str) -> None:
    print(f"{datetime.now(UTC).isoformat()} {message}", flush=True)


async def main() -> None:
    start = time.monotonic()
    sets_done = 0

    def on_set_done(tcgdex_set_id: str, report: dict) -> None:
        nonlocal sets_done
        sets_done += 1
        elapsed = time.monotonic() - start
        _log(
            f"[{sets_done}/{report['sets_seen']}] {tcgdex_set_id} — "
            f"cartes créées={report['cards_created']} maj={report['cards_updated']} "
            f"erreurs={len(report['errors'])} — écoulé {elapsed:.0f}s"
        )

    async with (
        httpx.AsyncClient(timeout=30.0) as tcgdex_http,
        httpx.AsyncClient(timeout=20.0) as ptcg_http,
        async_session_factory() as session,
    ):
        tcgdex = TcgdexClient(http_client=tcgdex_http)
        ptcg = PtcgClient(http_client=ptcg_http)
        _log("import complet démarré (FR+EN, toutes extensions)")
        report = await import_catalogue(
            session,
            tcgdex,
            ptcg,
            languages=("fr", "en"),
            set_ids=None,
            mode="full",
            progress_callback=on_set_done,
        )

    elapsed = time.monotonic() - start
    report["duration_seconds"] = round(elapsed, 1)
    _log(f"import complet terminé en {elapsed:.0f}s")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
