"""Cycle de vie des jobs de reconnaissance (lot `pbm-parcours-validation`, mission points 5 & 6) :
délai maximal par job → échec EXPLICITE relançable, reprise au démarrage des jobs restés
« running », reprise sans re-découpe, et un lot de plusieurs photos qui ne se bloque pas.

Les tests de délai/concurrence exercent `_run_detect_cards` de bout en bout : il ouvre sa propre
session (`async_session_factory`) comme en production. Pour rester sur la boucle asyncio du test
(le moteur global est lié à la boucle de son premier usage), la fixture `worker_factory` substitue
un moteur créé sur la boucle courante et supprime ses lignes en fin de test.
"""

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

import cv2
import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pbm_api import worker
from pbm_api.config import settings
from pbm_api.models import Detection, DetectionStatus, Job, JobStatus, Upload, UploadStatus, User
from pbm_api.s3 import ObjectStorage
from pbm_api.worker import _detect_identify_state, reap_stale_jobs_in_session

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v2_catalogue_complet_test",
)


def _utc_now() -> datetime:
    """Naïf en UTC, comme `pbm_api.worker._now_naive_utc` (les colonnes `jobs.*_at` sont sans
    fuseau) — surtout pas `datetime.now()`, qui serait en heure de Paris (TZ des tests)."""
    return datetime.now(UTC).replace(tzinfo=None)


def test_worker_import_enables_pbm_api_info_logging():
    """Mission point 5 : importer le worker doit rendre visibles les logs INFO de `pbm_api`
    (début/fin de chaque job). Sans ça, `journalctl` ne montrait que les démarrages du service."""
    pbm_logger = logging.getLogger("pbm_api")
    assert pbm_logger.isEnabledFor(logging.INFO)
    assert any(getattr(handler, "_pbm_worker_handler", False) for handler in pbm_logger.handlers)


# --- Reprise au démarrage : un job resté « running » trop longtemps repasse en échec ----------


async def test_reap_marks_only_long_running_jobs_as_failed(db_session):
    stale = Job(
        type="detect_cards",
        status=JobStatus.running,
        started_at=_utc_now() - timedelta(seconds=settings.stale_job_timeout_seconds + 120),
        payload={"upload_id": str(uuid.uuid4())},
    )
    fresh = Job(
        type="detect_cards",
        status=JobStatus.running,
        started_at=_utc_now(),
        payload={"upload_id": str(uuid.uuid4())},
    )
    db_session.add_all([stale, fresh])
    await db_session.flush()

    reaped = await reap_stale_jobs_in_session(db_session)

    assert reaped == 1
    await db_session.refresh(stale)
    await db_session.refresh(fresh)
    assert stale.status == JobStatus.failed
    assert "Relance la reconnaissance" in stale.error
    assert stale.finished_at is not None
    assert fresh.status == JobStatus.running  # job récent, encore possiblement vivant : intact


# --- Reprise sans re-découpe : un envoi déjà découpé n'ajoute pas de doublons -----------------


@pytest.fixture
async def storage():
    object_storage = ObjectStorage()
    await object_storage.ensure_bucket()
    return object_storage


async def test_detect_identify_state_skips_detection_when_crops_already_exist(db_session, storage):
    user = User(
        email=f"reprise-{uuid.uuid4()}@example.com",
        password_hash="x",
        last_name="Test",
        birth_date=datetime(2000, 1, 1).date(),
        terms_version="test",
        terms_accepted_at=datetime(2000, 1, 1),
    )
    db_session.add(user)
    await db_session.flush()
    upload = Upload(
        user_id=user.id,
        s3_key=f"uploads/{user.id}/{uuid.uuid4()}/original",
        original_filename="photo.jpg",
        content_type="image/jpeg",
        size_bytes=1,
        status=UploadStatus.processed,
    )
    db_session.add(upload)
    await db_session.flush()

    crop_key = f"uploads/{user.id}/{upload.id}/detections/0.jpg"
    ok, buf = cv2.imencode(".jpg", np.zeros((880, 630, 3), dtype=np.uint8))
    assert ok
    await storage.put(crop_key, buf.tobytes(), "image/jpeg")
    db_session.add(
        Detection(
            upload_id=upload.id,
            bbox={"reading_order": 0, "points": [[0, 0], [1, 0], [1, 1], [0, 1]]},
            crop_s3_key=crop_key,
            status=DetectionStatus.pending,
        )
    )
    await db_session.flush()

    report = await _detect_identify_state(db_session, storage, upload)

    assert report["method"] == "reprise"
    assert report["detections_count"] == 1
    rows = (
        (await db_session.execute(select(Detection).where(Detection.upload_id == upload.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1  # aucune détection dupliquée par la reprise


# --- Délai maximal & concurrence : `_run_detect_cards` de bout en bout, moteur sur cette boucle -


@pytest_asyncio.fixture
async def worker_factory(monkeypatch):
    engine = create_async_engine(TEST_DATABASE_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("pbm_api.worker.async_session_factory", factory)
    created_users: list[uuid.UUID] = []
    yield factory, created_users
    async with factory() as session:
        for user_id in created_users:
            user = await session.get(User, user_id)
            if user is not None:
                await session.delete(user)  # cascade -> uploads, jobs, detections
        await session.commit()
    await engine.dispose()


async def _seed_job(factory, created_users: list) -> str:
    async with factory() as session:
        user = User(
            email=f"job-{uuid.uuid4()}@example.com",
            password_hash="x",
            last_name="Test",
            birth_date=datetime(2000, 1, 1).date(),
            terms_version="test",
            terms_accepted_at=datetime(2000, 1, 1),
        )
        session.add(user)
        await session.flush()
        upload = Upload(
            user_id=user.id,
            s3_key=f"uploads/{user.id}/{uuid.uuid4()}/original",
            original_filename="p.jpg",
            content_type="image/jpeg",
            size_bytes=1,
            status=UploadStatus.processed,
        )
        session.add(upload)
        await session.flush()
        job = Job(
            type="detect_cards",
            status=JobStatus.queued,
            user_id=user.id,
            payload={"upload_id": str(upload.id)},
        )
        session.add(job)
        await session.commit()
        created_users.append(user.id)
        return str(job.id)


async def test_run_detect_cards_times_out_and_fails_explicitly(worker_factory, monkeypatch):
    factory, created_users = worker_factory
    monkeypatch.setattr(settings, "detect_job_timeout_seconds", 0.05)

    async def _slow(session, storage, upload):
        await asyncio.sleep(1.0)
        return {}

    monkeypatch.setattr("pbm_api.worker._detect_identify_state", _slow)

    job_id = await _seed_job(factory, created_users)
    report = await worker._run_detect_cards(job_id)

    assert report.get("timeout") is True
    async with factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        assert job.status == JobStatus.failed
        assert "délai" in job.error
        assert job.finished_at is not None


async def test_four_detect_jobs_run_concurrently_without_blocking(worker_factory, monkeypatch):
    """Mission point 6 : un lot de photos ne se bloque pas. Les quatre jobs démarrent avant que
    le premier ne se termine (jamais sérialisés), chacun sur sa propre session."""
    factory, created_users = worker_factory
    events: list[tuple[str, str]] = []

    async def _stub(session, storage, upload):
        events.append(("start", str(upload.id)))
        await asyncio.sleep(0.15)
        events.append(("end", str(upload.id)))
        return {"detections_count": 0, "method": "opencv"}

    monkeypatch.setattr("pbm_api.worker._detect_identify_state", _stub)

    job_ids = [await _seed_job(factory, created_users) for _ in range(4)]
    await asyncio.gather(*(worker._run_detect_cards(job_id) for job_id in job_ids))

    async with factory() as session:
        for job_id in job_ids:
            job = await session.get(Job, uuid.UUID(job_id))
            assert job.status == JobStatus.succeeded

    starts = [i for i, (kind, _) in enumerate(events) if kind == "start"]
    first_end = next(i for i, (kind, _) in enumerate(events) if kind == "end")
    assert len(starts) == 4
    assert max(starts) < first_end  # les 4 ont démarré avant que le premier ne finisse
