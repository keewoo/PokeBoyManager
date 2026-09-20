"""Garde des traitements lourds (lot `pbm-jobs-flotte`) : sur un nœud où `HEAVY_JOBS_ENABLED` est
faux (PROD, la machine qui sert), le worker ne planifie NI n'exécute les jobs qui balaient tout le
catalogue (relevé de prix, import, taux de change, tournoi). S'ils sont réclamés malgré tout, ils
refusent explicitement (message clair dans `jobs.error`) au lieu de s'exécuter à moitié — c'est
exactement la faute d'architecture que ce lot corrige (1 h 20 pour zéro prix écrit sur kailo-srv).

Aucune dépendance à une base réelle ni au réseau : `heavy_jobs_allowed` est pur, le chemin de
refus écrit son `Job` via une fabrique de session simulée, et le chemin autorisé est vérifié en
substituant le vrai traitement par une sentinelle.
"""

import pytest

from pbm_api import worker
from pbm_api.config import Settings, settings
from pbm_api.models import JobStatus

_REAL_SECRET = "x" * 40
_REAL_AI_KEY = "y" * 44


def _prod(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        secret_key=_REAL_SECRET,
        ai_key_encryption_key=_REAL_AI_KEY,
        **overrides,
    )


# --- heavy_jobs_allowed : le défaut est FAUX en production, VRAI hors production --------------


def test_default_is_false_in_production():
    assert _prod().heavy_jobs_allowed is False


def test_default_is_true_in_development():
    assert Settings(_env_file=None, app_env="development").heavy_jobs_allowed is True


def test_explicit_true_overrides_production_default():
    assert _prod(heavy_jobs_enabled=True).heavy_jobs_allowed is True


def test_explicit_false_overrides_development_default():
    s = Settings(_env_file=None, app_env="development", heavy_jobs_enabled=False)
    assert s.heavy_jobs_allowed is False


# --- planification : aucun cron lourd quand c'est interdit -----------------------------------


def test_no_heavy_crons_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "heavy_jobs_enabled", False)
    assert worker._heavy_cron_jobs() == []


def test_all_heavy_crons_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "heavy_jobs_enabled", True)
    crons = worker._heavy_cron_jobs()
    # prix, taux de change, import hebdo, tournoi hebdo — les quatre traitements de fond.
    assert len(crons) == 4


# --- exécution : refus explicite, jamais à moitié --------------------------------------------


class _FakeSession:
    """Fabrique de session simulée : capture les `Job` ajoutés sans toucher à une base réelle."""

    def __init__(self, store: list) -> None:
        self._store = store

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def add(self, obj) -> None:
        self._store.append(obj)

    async def commit(self) -> None:
        return None


@pytest.fixture
def captured_jobs(monkeypatch):
    store: list = []
    monkeypatch.setattr(worker, "async_session_factory", lambda: _FakeSession(store))
    return store


HEAVY_TASKS = [
    ("daily_prices_task", worker.PRICE_JOB_TYPE),
    ("daily_exchange_rates_task", worker.EXCHANGE_RATE_JOB_TYPE),
    ("weekly_incremental_import", worker.JOB_TYPE),
    ("import_catalogue_task", worker.JOB_TYPE),
    ("weekly_tournament_presence_task", worker.TOURNAMENT_PRESENCE_JOB_TYPE),
]


@pytest.mark.parametrize("task_name,job_type", HEAVY_TASKS)
async def test_heavy_task_refuses_when_disabled(task_name, job_type, monkeypatch, captured_jobs):
    monkeypatch.setattr(settings, "heavy_jobs_enabled", False)
    # Si le garde laissait passer, le vrai traitement ferait un appel réseau : on le remplace par
    # une bombe pour prouver qu'il n'est JAMAIS atteint.
    for internal in ("_run_daily_prices", "_run_daily_exchange_rates", "_run_import",
                     "_run_weekly_tournament_presence"):
        async def _boom(*a, **k):
            raise AssertionError("le traitement lourd n'aurait pas dû démarrer")
        monkeypatch.setattr(worker, internal, _boom)

    result = await getattr(worker, task_name)({})

    assert result["refused"] is True
    assert "refusé" in result["error"]
    assert len(captured_jobs) == 1
    job = captured_jobs[0]
    assert job.type == job_type
    assert job.status == JobStatus.failed
    assert job.error and "HEAVY_JOBS_ENABLED" in job.error
    assert job.finished_at is not None  # borné : ni « running » perpétuel, ni à moitié


async def test_heavy_task_runs_when_enabled(monkeypatch):
    """Quand c'est autorisé (chimera/dev), le garde laisse passer vers le vrai traitement."""
    monkeypatch.setattr(settings, "heavy_jobs_enabled", True)
    sentinel = {"day": "2026-09-20", "prices_written_cardmarket": 42}

    async def _fake_run():
        return sentinel

    monkeypatch.setattr(worker, "_run_daily_prices", _fake_run)
    assert await worker.daily_prices_task({}) is sentinel
