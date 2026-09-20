"""Worker arq : import du catalogue (déclenché) et sa reprise hebdomadaire (mission point 4).

Lancement : `uv run arq pbm_api.worker.WorkerSettings`.

Traitements lourds vs court (lot `pbm-jobs-flotte`) : sur un nœud où `settings.heavy_jobs_allowed`
est faux (PROD, la machine qui sert), les jobs qui balaient tout le catalogue (relevé de prix,
import du catalogue, relevé de tournoi, taux de change) NE sont ni planifiés (aucun `cron` posé,
voir `_heavy_cron_jobs`) ni exécutés (ils REFUSENT explicitement, voir `_refuse_heavy_job`). Ils
tournent sur la flotte (chimera) et seul le résultat est importé — voir docs/infra/JOBS-LOURDS.md.
"""

import logging
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
from pbm_api.ingame.tournaments import LimitlessTcgClient
from pbm_api.ingame.tournaments_job import refresh_tournament_presence
from pbm_api.models import DataExport, Job, JobStatus, Upload, User
from pbm_api.pricing.exchange_rates import EcbClient, store_daily_rates
from pbm_api.pricing.service import collect_daily_prices
from pbm_api.ranking.service import refresh_card_value_rank
from pbm_api.state.service import run_state_estimation_for_upload
from pbm_api.storage import build_storage

logger = logging.getLogger(__name__)

JOB_TYPE = "import_catalogue"
PRICE_JOB_TYPE = "daily_prices"
EXCHANGE_RATE_JOB_TYPE = "daily_exchange_rates"
TOURNAMENT_PRESENCE_JOB_TYPE = "weekly_tournament_presence"

# Traitements lourds (balayent tout le catalogue / dépendent d'un débit réseau soutenu) : jamais
# sur la machine qui sert. Les jobs COURTS gardés en PROD (`detect_cards`, `export_user_data`) ne
# sont pas dans cet ensemble — ils sont enfilés à la demande depuis une route HTTP, bornés à un
# envoi ou un utilisateur, et n'ont rien à voir avec le catalogue entier.
HEAVY_JOB_TYPES = frozenset(
    {JOB_TYPE, PRICE_JOB_TYPE, EXCHANGE_RATE_JOB_TYPE, TOURNAMENT_PRESENCE_JOB_TYPE}
)


def _now_naive_utc() -> datetime:
    """`jobs.started_at`/`finished_at` sont des TIMESTAMP WITHOUT TIME ZONE (voir migration
    initiale) : leur passer un datetime "aware" fait échouer asyncpg (`can't subtract
    offset-naive and offset-aware datetimes`)."""
    return datetime.now(UTC).replace(tzinfo=None)


async def _refuse_heavy_job(job_type: str, payload: dict | None = None) -> dict:
    """Refus EXPLICITE d'un traitement lourd sur un nœud qui ne doit pas le faire (PROD) : écrit un
    `Job` en échec avec un message clair dans `jobs.error`, jamais une exécution à moitié (mission
    `pbm-jobs-flotte` point 1). Aucune requête réseau, aucune écriture catalogue n'est tentée."""
    message = (
        f"Traitement lourd « {job_type} » refusé sur ce nœud : HEAVY_JOBS_ENABLED est faux "
        f"(app_env={settings.app_env}). Les traitements lourds tournent sur la flotte (chimera), "
        f"pas sur la machine qui sert ; seul le résultat est importé en PROD "
        f"(voir docs/infra/JOBS-LOURDS.md)."
    )
    logger.warning(message)
    async with async_session_factory() as session:
        now = _now_naive_utc()
        session.add(
            Job(
                type=job_type,
                status=JobStatus.failed,
                payload=payload,
                error=message,
                started_at=now,
                finished_at=now,
            )
        )
        await session.commit()
    return {"error": message, "refused": True}


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
    if not settings.heavy_jobs_allowed:
        return await _refuse_heavy_job(
            JOB_TYPE, {"mode": mode, "languages": languages, "set_ids": set_ids}
        )
    langs = tuple(languages) if languages else ("fr", "en")
    return await _run_import(mode, langs, set_ids)


async def weekly_incremental_import(ctx: dict) -> dict:
    """Cron hebdomadaire : n'importe que les extensions absentes de la base (nouveautés)."""
    if not settings.heavy_jobs_allowed:
        return await _refuse_heavy_job(JOB_TYPE, {"mode": "incremental"})
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
    if not settings.heavy_jobs_allowed:
        return await _refuse_heavy_job(PRICE_JOB_TYPE)
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
    `valuation` pour convertir une tendance TCGplayer (USD) en euros. Fournis avec les prix par le
    bundle de la flotte (mission `pbm-jobs-flotte`) : hors PROD sur un nœud à jobs lourds."""
    if not settings.heavy_jobs_allowed:
        return await _refuse_heavy_job(EXCHANGE_RATE_JOB_TYPE)
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
            # État (mission `v3-etat`) chaîné après l'identification, dans le même job : le
            # centrage se mesure sur le recadrage déjà en stockage, coins/bords/surface/
            # contrefaçon viennent de l'extraction que l'identification vient d'écrire (fraîche
            # ou réutilisée du cache) — jamais un appel IA de plus.
            state_summary = await run_state_estimation_for_upload(session, storage, upload)
            report = {
                "detections_count": summary.detections_count,
                "method": summary.method,
                "identified_count": id_summary.identified_count,
                "identification_cache_hits": id_summary.cache_hits,
                "identification_ai_calls": id_summary.ai_calls,
                "identification_visual_matches": id_summary.visual_matches,
                "state_assessed_count": state_summary.assessed_count,
                "state_counterfeit_flagged_count": state_summary.counterfeit_flagged_count,
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


async def _run_weekly_tournament_presence() -> dict:
    async with async_session_factory() as session:
        job = Job(
            type=TOURNAMENT_PRESENCE_JOB_TYPE, status=JobStatus.running, started_at=_now_naive_utc()
        )
        session.add(job)
        await session.commit()

        async with httpx.AsyncClient(
            timeout=20.0, headers={"User-Agent": "PokeBoyManager/1.0 (+https://pokeboy.life)"}
        ) as limitless_http:
            client = LimitlessTcgClient(http_client=limitless_http)
            try:
                report = await refresh_tournament_presence(session, client)
                job.status = JobStatus.succeeded
                job.result = report
            except Exception as exc:
                # Un blocage du site (403/429, `LimitlessBlockedError`) ou toute autre panne
                # devient un Job en échec — la section reste "unavailable" côté fiche jusqu'au
                # prochain relevé, jamais une carte "probable" (mission point 2).
                job.status = JobStatus.failed
                job.error = str(exc)
                report = {"error": str(exc)}
            job.finished_at = _now_naive_utc()
            await session.commit()
    return report


async def weekly_tournament_presence_task(ctx: dict) -> dict:
    """Relevé hebdomadaire de présence en tournoi (mission `v4-jeu` point 2), source publique
    Limitless TCG — bridé aux cartes légales dans au moins un format. Scrutation d'un site tiers
    (lente, concurrence=1) : lourde pour la machine qui sert, elle tourne sur la flotte."""
    if not settings.heavy_jobs_allowed:
        return await _refuse_heavy_job(TOURNAMENT_PRESENCE_JOB_TYPE)
    return await _run_weekly_tournament_presence()


def _heavy_cron_jobs() -> list:
    """Les crons des traitements lourds — posés UNIQUEMENT sur un nœud qui a le droit de les
    exécuter (`settings.heavy_jobs_allowed`). En PROD, cette liste est vide : le worker ne planifie
    aucun relevé de prix ni import (mission `pbm-jobs-flotte` point 1) ; c'est la flotte (chimera)
    qui les fait, pilotée par des agents launchd sur devAI (voir docs/infra/JOBS-LOURDS.md). Les
    jobs courts (`detect_cards`, `export_user_data`) ne sont pas des crons : ils sont enfilés à la
    demande depuis l'API et restent servis en PROD quoi qu'il arrive."""
    if not settings.heavy_jobs_allowed:
        return []
    return [
        cron(weekly_incremental_import, weekday=0, hour=6, minute=0),
        cron(daily_prices_task, hour=6, minute=0),
        cron(daily_exchange_rates_task, hour=6, minute=0),
        # Décalé du reste (Lundi 06:00) pour ne pas cumuler le relevé de prix (tout le
        # catalogue) et le relevé de tournoi (site tiers plus lent, concurrence=1) sur la même
        # fenêtre — chimera comme Limitless TCG restent réactifs pendant les deux.
        cron(weekly_tournament_presence_task, weekday=0, hour=8, minute=0),
    ]


class WorkerSettings:
    # Toutes les fonctions restent enregistrées, même les lourdes : si un job lourd est malgré tout
    # enfilé vers un worker de PROD, il est pris en charge et REFUSÉ proprement
    # (`_refuse_heavy_job`) plutôt que de finir en « function not found ».
    functions = [
        import_catalogue_task,
        daily_prices_task,
        daily_exchange_rates_task,
        detect_cards_task,
        export_user_data_task,
        weekly_tournament_presence_task,
    ]
    cron_jobs = _heavy_cron_jobs()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    queue_name = f"{settings.redis_prefix}queue"
