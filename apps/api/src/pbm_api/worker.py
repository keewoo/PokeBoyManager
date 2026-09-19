"""Worker arq : import du catalogue (déclenché) et sa reprise hebdomadaire (mission point 4).

Lancement : `uv run arq pbm_api.worker.WorkerSettings`.
"""

import uuid
from datetime import UTC, datetime

import httpx
from arq.connections import RedisSettings
from arq.cron import cron

from pbm_api.ai.errors import AIProviderError
from pbm_api.catalog.import_service import import_catalogue
from pbm_api.catalog.ptcg_client import PtcgClient
from pbm_api.catalog.tcgdex_client import TcgdexClient
from pbm_api.config import settings
from pbm_api.db import async_session_factory
from pbm_api.detection.service import run_detection_for_upload
from pbm_api.email import get_email_sender
from pbm_api.export.service import run_export
from pbm_api.identification.service import run_identification_for_upload
from pbm_api.models import DataExport, Job, JobStatus, Upload, User
from pbm_api.pricing.exchange_rates import EcbClient, store_daily_rates
from pbm_api.pricing.service import collect_daily_prices
from pbm_api.ranking.service import refresh_card_value_rank
from pbm_api.storage import build_storage

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
                # Mission `v4-ranking` point 1 : la vue matérialisée `card_value_rank` se
                # rafraîchit juste après un relevé réussi — jamais sur un relevé vide/en échec,
                # elle refléterait alors des prix qui n'ont pas bougé pour rien.
                await refresh_card_value_rank(session)
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


async def _run_detect_cards(job_id: str) -> dict:
    async with async_session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            # Ne peut arriver qu'avec un job créé puis effacé entre l'enfilage et l'exécution
            # (aucune suppression de `Job` n'existe dans ce dépôt) : signalé, jamais avalé.
            raise LookupError(f"job {job_id} introuvable")

        job.status = JobStatus.running
        job.started_at = _now_naive_utc()
        await session.commit()

        upload_id = uuid.UUID(job.payload["upload_id"])
        upload = await session.get(Upload, upload_id)
        storage = build_storage()
        try:
            if upload is None:
                raise LookupError(f"upload {upload_id} introuvable")
            summary = await run_detection_for_upload(session, storage, upload)
            # Identification (mission `v3-identification`) chaînée dans le même job que la
            # détection : un seul aller-retour par la file par photo, et le principe cadre « un
            # appel IA par carte, dès le premier tir » veut dire un appel par carte détectée,
            # pas un job de plus par carte.
            id_summary = await run_identification_for_upload(session, storage, upload)
            report = {
                "detections_count": summary.detections_count,
                "method": summary.method,
                "identified_count": id_summary.identified_count,
                "identification_cache_hits": id_summary.cache_hits,
                "identification_ai_calls": id_summary.ai_calls,
            }
            job.status = JobStatus.succeeded
            job.result = report
        except AIProviderError as exc:
            # `user_message` est le texte normalisé prêt à consigner sur le `Job` (mission
            # `v3-ia-providers` point 3) ; `detail` (brut, potentiellement technique) ne part
            # que dans les journaux serveur, jamais sur une ligne visible depuis l'API.
            job.status = JobStatus.failed
            job.error = exc.user_message
            report = {"error": exc.user_message}
        except Exception as exc:
            job.status = JobStatus.failed
            job.error = str(exc)
            report = {"error": str(exc)}
        job.finished_at = _now_naive_utc()
        await session.commit()
    return report


async def detect_cards_task(ctx: dict, job_id: str) -> dict:
    """Détection des cartes d'une photo (mission `v3-detection`) : contours OpenCV + repli par
    boîtes englobantes LLM, un `Job` par envoi complété (`POST /uploads/{id}/complete`, D4 —
    déclenché seulement si l'utilisateur a une clé IA, sinon l'ajout manuel reste possible)."""
    return await _run_detect_cards(job_id)


async def _run_export(export_id: str) -> dict:
    async with async_session_factory() as session:
        export = await session.get(DataExport, uuid.UUID(export_id))
        if export is None:
            # Comme `_run_detect_cards` : ne peut arriver qu'entre l'enfilage et l'exécution
            # (aucune suppression de `DataExport` n'existe hors suppression du compte).
            raise LookupError(f"export {export_id} introuvable")

        user = await session.get(User, export.user_id)
        if user is None:
            raise LookupError(f"utilisateur {export.user_id} introuvable")

        storage = build_storage()
        export = await run_export(session, storage, get_email_sender(), user, export)
        return {"status": export.status.value}


async def export_user_data_task(ctx: dict, export_id: str) -> dict:
    """Export RGPD de la collection (mission `v5-rgpd` point 1) : un `DataExport` par demande
    (`POST /me/export`), archive ZIP + lien de téléchargement signé envoyé par e-mail."""
    return await _run_export(export_id)


class WorkerSettings:
    functions = [
        import_catalogue_task,
        daily_prices_task,
        daily_exchange_rates_task,
        detect_cards_task,
        export_user_data_task,
    ]
    cron_jobs = [
        cron(weekly_incremental_import, weekday=0, hour=6, minute=0),
        cron(daily_prices_task, hour=6, minute=0),
        cron(daily_exchange_rates_task, hour=6, minute=0),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = f"{settings.redis_prefix}queue"
