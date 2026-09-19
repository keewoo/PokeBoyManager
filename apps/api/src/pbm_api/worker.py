"""Worker arq : import du catalogue (déclenché) et sa reprise hebdomadaire (mission point 4).

Lancement : `uv run arq pbm_api.worker.WorkerSettings`.
"""

from datetime import UTC, datetime

import httpx
from arq.connections import RedisSettings
from arq.cron import cron

from pbm_api.catalog.import_service import import_catalogue
from pbm_api.catalog.ptcg_client import PtcgClient
from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.config import settings
from pbm_api.db import async_session_factory
from pbm_api.models import Job, JobStatus
from pbm_api.pricing.exchange_rates import EcbClient, store_daily_rates
from pbm_api.pricing.service import collect_daily_prices

JOB_TYPE = "import_catalogue"
PRICE_JOB_TYPE = "daily_prices"
EXCHANGE_RATE_JOB_TYPE = "daily_exchange_rates"


def _now_naive_utc() -> datetime:
    """`jobs.started_at`/`finished_at` sont des TIMESTAMP WITHOUT TIME ZONE (voir migration
    initiale) : leur passer un datetime "aware" fait échouer asyncpg (`can't subtract
    offset-naive and offset-aware datetimes`)."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _run_import(mode: str, languages: tuple[str, ...], set_ids: list[str] | None) -> dict:
    async with async_session_factory() as session:
        job = Job(
            type=JOB_TYPE,
            status=JobStatus.running,
            payload={"mode": mode, "languages": list(languages), "set_ids": set_ids},
            started_at=_now_naive_utc(),
        )
        session.add(job)
        await session.commit()

        async with (
            httpx.AsyncClient(timeout=30.0) as tcgdex_http,
            httpx.AsyncClient(timeout=20.0) as ptcg_http,
        ):
            tcgdex = TcgdexClient(http_client=tcgdex_http)
            ptcg = PtcgClient(http_client=ptcg_http)
            try:
                report = await import_catalogue(
                    session, tcgdex, ptcg, languages=languages, set_ids=set_ids, mode=mode
                )
                job.status = JobStatus.succeeded
                job.result = report
            except Exception as exc:
                job.status = JobStatus.failed
                job.error = str(exc)
                report = {"error": str(exc)}
            job.finished_at = _now_naive_utc()
            await session.commit()
    return report


async def import_catalogue_task(
    ctx: dict,
    languages: list[str] | None = None,
    set_ids: list[str] | None = None,
    mode: str = "full",
) -> dict:
    langs = tuple(languages) if languages else ("fr", "en")
    return await _run_import(mode, langs, set_ids)


async def weekly_incremental_import(ctx: dict) -> dict:
    """Cron hebdomadaire : n'importe que les extensions absentes de la base (nouveautés)."""
    return await _run_import("incremental", ("fr", "en"), None)


async def _run_daily_prices() -> dict:
    async with async_session_factory() as session:
        job = Job(type=PRICE_JOB_TYPE, status=JobStatus.running, started_at=_now_naive_utc())
        session.add(job)
        await session.commit()

        async with (
            httpx.AsyncClient(timeout=30.0) as tcgdex_http,
            httpx.AsyncClient(timeout=20.0) as ptcg_http,
        ):
            tcgdex = TcgdexClient(http_client=tcgdex_http)
            ptcg = PtcgClient(http_client=ptcg_http)
            try:
                report = await collect_daily_prices(session, tcgdex, ptcg)
                job.status = JobStatus.succeeded
                job.result = report
            except Exception as exc:
                # Sonde mission point 4 : un relevé vide (EmptyPriceRunError) ou toute autre
                # panne devient un Job en échec, jamais un succès silencieux.
                job.status = JobStatus.failed
                job.error = str(exc)
                report = {"error": str(exc)}
            job.finished_at = _now_naive_utc()
            await session.commit()
    return report


async def daily_prices_task(ctx: dict) -> dict:
    """Relevé quotidien 06:00 Europe/Paris (mission `v2-prix` point 1) : prix de toutes les
    cartes, source Cardmarket (TCGdex) + TCGplayer (Pokémon TCG API)."""
    return await _run_daily_prices()


async def _run_daily_exchange_rates() -> dict:
    async with async_session_factory() as session:
        job = Job(
            type=EXCHANGE_RATE_JOB_TYPE, status=JobStatus.running, started_at=_now_naive_utc()
        )
        session.add(job)
        await session.commit()

        async with httpx.AsyncClient(timeout=20.0) as ecb_http:
            ecb = EcbClient(http_client=ecb_http)
            try:
                published_day, rates = await ecb.fetch_daily_rates()
                written = await store_daily_rates(session, published_day, rates)
                report = {"day": published_day.isoformat(), "rates_written": written}
                job.status = JobStatus.succeeded
                job.result = report
            except Exception as exc:
                job.status = JobStatus.failed
                job.error = str(exc)
                report = {"error": str(exc)}
            job.finished_at = _now_naive_utc()
            await session.commit()
    return report


async def daily_exchange_rates_task(ctx: dict) -> dict:
    """Taux de change BCE quotidiens (mission `v2-prix` point 2), consommés par le service
    `valuation` pour convertir une tendance TCGplayer (USD) en euros."""
    return await _run_daily_exchange_rates()


class WorkerSettings:
    functions = [import_catalogue_task, daily_prices_task, daily_exchange_rates_task]
    cron_jobs = [
        cron(weekly_incremental_import, weekday=0, hour=6, minute=0),
        cron(daily_prices_task, hour=6, minute=0),
        cron(daily_exchange_rates_task, hour=6, minute=0),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = f"{settings.redis_prefix}queue"
