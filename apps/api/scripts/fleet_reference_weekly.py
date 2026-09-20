"""Étape LOURDE hebdomadaire, à lancer sur la flotte (chimera) contre `pbm_catalogue_ref` — jamais
sur la machine qui sert (lot `pbm-jobs-flotte`). Deux traitements de fond, dans l'ordre :

1. Import INCRÉMENTAL du catalogue (`import_catalogue(mode="incremental")`) : n'ajoute que les
   extensions/cartes absentes de la base (nouveautés TCGdex), ne réécrit pas l'existant.
2. Relevé de présence en tournoi (`refresh_tournament_presence`, source Limitless TCG) — bridé aux
   cartes légales dans au moins un format. Best-effort : un blocage du site (403/429) est consigné,
   il n'empêche pas la partie catalogue (déjà validée) d'être exportée.

Le RÉSULTAT est ensuite exporté (sets/cards/card_names/tournament) puis importé en PROD par
`infra/fleet/import_weekly.sql` (INSERT-only côté catalogue, upsert côté tournoi). Voir
docs/infra/JOBS-LOURDS.md.

Usage :
    DATABASE_URL=postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_catalogue_ref \
        uv run python scripts/fleet_reference_weekly.py
Sortie : rapport JSON sur stdout (dernière ligne).
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
from pbm_api.ingame.tournaments import LimitlessTcgClient
from pbm_api.ingame.tournaments_job import refresh_tournament_presence


def _log(message: str) -> None:
    print(f"{datetime.now(UTC).isoformat()} {message}", flush=True)


async def main() -> None:
    start = time.monotonic()
    report: dict = {"started_at": datetime.now(UTC).isoformat()}

    async with (
        httpx.AsyncClient(timeout=30.0) as tcgdex_http,
        httpx.AsyncClient(timeout=20.0) as ptcg_http,
        async_session_factory() as session,
    ):
        tcgdex = TcgdexClient(http_client=tcgdex_http)
        ptcg = PtcgClient(http_client=ptcg_http)
        _log("import incrémental du catalogue démarré (FR+EN, nouveautés seulement)")
        catalogue = await import_catalogue(
            session, tcgdex, ptcg, languages=("fr", "en"), set_ids=None, mode="incremental"
        )
        report["catalogue"] = {
            "sets_seen": catalogue.get("sets_seen"),
            "cards_created": catalogue.get("cards_created"),
            "cards_updated": catalogue.get("cards_updated"),
            "errors": len(catalogue.get("errors", [])),
        }
        _log(f"catalogue : {report['catalogue']}")

    # Tournoi : best-effort, ne doit jamais faire échouer l'export du catalogue.
    async with httpx.AsyncClient(
        timeout=20.0, headers={"User-Agent": "PokeBoyManager/1.0 (+https://pokeboy.life)"}
    ) as limitless_http:
        client = LimitlessTcgClient(http_client=limitless_http)
        async with async_session_factory() as session:
            try:
                tournament = await refresh_tournament_presence(session, client)
                report["tournament"] = tournament
                _log(f"tournoi : {tournament}")
            except Exception as exc:  # noqa: BLE001 — consigné, non fatal
                report["tournament_error"] = str(exc)
                _log(f"⚠ relevé de tournoi en échec (non fatal) : {exc}")

    report["duration_seconds"] = round(time.monotonic() - start, 1)
    _log(f"étape hebdo terminée en {report['duration_seconds']:.0f}s")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
