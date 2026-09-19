"""Orchestration du lot (mission `v4-insights-batch`) — `pbm_api.insights_batch.runner`.

Avant ce lot, `pbm_api.insights_batch` n'existait pas : ce module échoue entièrement à la
collection (`ModuleNotFoundError`) et passe une fois le paquet ajouté.
`test_run_once_stays_under_the_remaining_budget_and_says_so` est la preuve ciblée du risque
« budget dépassé » (mission point 2) : sans le tri par coût estimé avant soumission, ce test
échouerait en soumettant toutes les cartes candidates plutôt que de s'arrêter avant le plafond.
`test_run_once_rejects_anecdote_with_url_outside_context` est la même défense en profondeur que
`pbm_api.insights.service` (v4-anecdotes) appliquée au lot : une anecdote qui cite une URL hors
contexte est rejetée même si le modèle a mal respecté la consigne.

Aucune clé Anthropic réelle sur chimera (D4) : `FakeBatchClient`/`RaisingBatchClient` simulent
la Message Batches API, `MediaWikiClient` reçoit un transport HTTP enregistré (même méthode que
`tests/test_card_insights.py`).

Pas de route HTTP dans ce lot (script/cron interne, voir `scripts/run_insights_batch.py`) :
aucun test d'accès croisé utilisateur ici — `card_insights` est déjà un cache partagé entre
utilisateurs (aucune notion de propriétaire), couvert par `tests/test_card_insights.py` et
`tests/test_in_game_study.py` pour les routes qui, elles, exigent une session.
"""

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pbm_api.config import settings
from pbm_api.insights.context import BULBAPEDIA_API_URL, POKEPEDIA_API_URL, MediaWikiClient
from pbm_api.insights_batch.anthropic_batches import BatchStatus, _result_item_from_json
from pbm_api.insights_batch.ledger import InFlightBatch, Ledger, save_ledger
from pbm_api.insights_batch.runner import run_once, source_marker
from pbm_api.models import Card, CardInsight, CardName, ExchangeRateDaily, Set

POKEPEDIA_PAGE_URL = "https://www.pokepedia.fr/Dracaufeu-Test"
BULBAPEDIA_PAGE_URL = "https://bulbapedia.bulbagarden.net/wiki/Charizard-Test"
MODEL = "claude-haiku-4-5"


def _mediawiki_handler(*, title: str, url: str, text: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": [{"title": title}]}})
        return httpx.Response(
            200, json={"query": {"pages": {"1": {"title": title, "fullurl": url, "extract": text}}}}
        )

    return httpx.MockTransport(handler)


def _pokepedia_client() -> MediaWikiClient:
    transport = _mediawiki_handler(
        title="Dracaufeu-Test", url=POKEPEDIA_PAGE_URL, text="Anecdote française sourcée."
    )
    return MediaWikiClient(POKEPEDIA_API_URL, http_client=httpx.AsyncClient(transport=transport))


def _bulbapedia_client() -> MediaWikiClient:
    transport = _mediawiki_handler(
        title="Charizard-Test", url=BULBAPEDIA_PAGE_URL, text="English sourced anecdote."
    )
    return MediaWikiClient(BULBAPEDIA_API_URL, http_client=httpx.AsyncClient(transport=transport))


def _empty_mediawiki_client(api_url: str) -> MediaWikiClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"search": []}})

    transport = httpx.MockTransport(handler)
    return MediaWikiClient(api_url, http_client=httpx.AsyncClient(transport=transport))


async def _make_card(db_session, *, name: str = "Dracaufeu") -> Card:
    suffix = uuid.uuid4().hex[:8]
    set_row = Set(code=f"ib-{suffix}", name="Extension de test", release_date=date(2023, 9, 22))
    db_session.add(set_row)
    await db_session.flush()
    card = Card(
        set_id=set_row.id,
        number="1",
        name=name,
        supertype="Pokemon",
        legal_standard=True,
        legal_expanded=True,
        attacks=[{"name": "Lance-Flammes", "damage": 150}],
    )
    db_session.add(card)
    await db_session.flush()
    db_session.add(CardName(card_id=card.id, language="en", name="Charizard"))
    await db_session.flush()
    return card


async def _seed_usd_rate(db_session, *, rate: str = "1.08") -> None:
    # Le lot compare toujours en date UTC (`runner._now_naive().date()`) — semer avec la date
    # locale (Europe/Paris, en avance sur UTC une partie de la nuit) ferait manquer le taux.
    db_session.add(
        ExchangeRateDaily(day=datetime.now(UTC).date(), currency="USD", rate=Decimal(rate))
    )
    await db_session.flush()


def _succeeded_result(
    custom_id: str, extraction: dict, *, input_tokens=500, output_tokens=300
) -> dict:
    return {
        "custom_id": custom_id,
        "result": {
            "type": "succeeded",
            "message": {
                "content": [{"type": "text", "text": json.dumps(extraction)}],
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            },
        },
    }


def _extraction_payload(*, extra_source_url: str | None = None) -> dict:
    anecdote_fr = {"text": "Fait notable en français.", "source_url": POKEPEDIA_PAGE_URL}
    anecdote_en = {"text": "Notable fact in English.", "source_url": BULBAPEDIA_PAGE_URL}
    anecdotes_fr = [anecdote_fr]
    anecdotes_en = [anecdote_en]
    if extra_source_url:
        anecdotes_fr = [*anecdotes_fr, {"text": "Fait inventé.", "source_url": extra_source_url}]
    return {
        "anecdotes_fr": anecdotes_fr,
        "anecdotes_en": anecdotes_en,
        "game_study": {
            "role": "Attaquant principal",
            "strengths": "Dégâts élevés",
            "weaknesses": "Fragile face au Type Eau",
            "related_cards": ["Dracaufeu V"],
            "playability_note": "Solide en Standard",
        },
    }


class FakeBatchClient:
    """Simule la Message Batches API — `statuses` rejoue les `processing_status` successifs
    renvoyés par `get_batch` (le dernier se répète), comme `_RecordingTransport` dans
    `tests/test_ai_providers.py`."""

    def __init__(self, *, statuses: list[str] | None = None, results: list[dict] | None = None):
        self.created_requests: list[dict] | None = None
        self._batch_id = "msgbatch_test_01"
        self._statuses = statuses or ["ended"]
        self._get_batch_calls = 0
        self._results = results or []
        self.results_url_requested: str | None = None

    async def create_batch(self, requests: list[dict]) -> BatchStatus:
        self.created_requests = requests
        return BatchStatus(
            batch_id=self._batch_id,
            processing_status="in_progress",
            request_counts={},
            results_url=None,
        )

    async def get_batch(self, batch_id: str) -> BatchStatus:
        index = min(self._get_batch_calls, len(self._statuses) - 1)
        self._get_batch_calls += 1
        status = self._statuses[index]
        return BatchStatus(
            batch_id=batch_id,
            processing_status=status,
            request_counts={"processing": 0 if status == "ended" else 1},
            results_url="https://api.anthropic.test/results.jsonl" if status == "ended" else None,
        )

    async def iter_results(self, results_url: str):
        self.results_url_requested = results_url
        return [_result_item_from_json(item) for item in self._results]

    async def aclose(self) -> None:
        pass


class RaisingBatchClient:
    """Preuve qu'aucun appel Anthropic n'est tenté (budget épuisé, taux manquant, dry-run)."""

    async def create_batch(self, requests):
        raise AssertionError("create_batch ne doit pas être appelé ici")

    async def get_batch(self, batch_id):
        raise AssertionError("get_batch ne doit pas être appelé ici")

    async def iter_results(self, results_url):
        raise AssertionError("iter_results ne doit pas être appelé ici")

    async def aclose(self) -> None:
        pass


@pytest.fixture
def ledger_path(tmp_path) -> Path:
    return tmp_path / "ledger.json"


async def test_run_once_without_platform_key_refuses_to_run(monkeypatch, db_session, ledger_path):
    monkeypatch.setattr(settings, "platform_anthropic_api_key", "")
    report = await run_once(db_session, batch_client=RaisingBatchClient(), ledger_path=ledger_path)
    assert report.status == "pas_de_cle_plateforme"


async def test_run_once_stops_when_budget_already_exhausted(monkeypatch, db_session, ledger_path):
    monkeypatch.setattr(settings, "platform_anthropic_api_key", "sk-ant-platform-test")
    monkeypatch.setattr(settings, "insights_budget_eur", 1.0)
    save_ledger(Ledger(total_spent_eur="1.0"), ledger_path)

    report = await run_once(db_session, batch_client=RaisingBatchClient(), ledger_path=ledger_path)

    assert report.status == "budget_epuise"


async def test_run_once_refuses_silently_defaulting_cost_when_no_exchange_rate(
    monkeypatch, db_session, ledger_path
):
    """Aucune ligne `exchange_rates_daily` en base : le lot doit s'arrêter plutôt que de traiter
    un coût USD comme gratuit (`InFlightBatch.usd_to_eur_rate`, jamais inventé à 0)."""
    monkeypatch.setattr(settings, "platform_anthropic_api_key", "sk-ant-platform-test")
    monkeypatch.setattr(settings, "insights_budget_eur", 100.0)
    await _make_card(db_session)

    report = await run_once(db_session, batch_client=RaisingBatchClient(), ledger_path=ledger_path)

    assert report.status == "taux_de_change_indisponible"


async def test_run_once_dry_run_prepares_requests_without_calling_anthropic(
    monkeypatch, db_session, ledger_path
):
    monkeypatch.setattr(settings, "insights_budget_eur", 100.0)
    monkeypatch.setattr(settings, "insights_batch_model", MODEL)
    await _make_card(db_session)
    await _seed_usd_rate(db_session)

    report = await run_once(
        db_session,
        dry_run=True,
        pokepedia_client=_pokepedia_client(),
        bulbapedia_client=_bulbapedia_client(),
        batch_client=RaisingBatchClient(),
        ledger_path=ledger_path,
    )

    assert report.status == "dry_run"
    assert report.cards_selected == 1
    assert report.outcomes[0].status == "prepared"  # contexte wiki trouvé pour cette carte
    assert report.cost_usd > 0  # coût ESTIMÉ (aucun appel réel) — voir docstring de RunReport
    assert not ledger_path.exists()  # aucune dépense engagée, rien à journaliser


async def test_run_once_dry_run_ignores_a_zero_budget(monkeypatch, db_session, ledger_path):
    """`INSIGHTS_BUDGET_EUR` calibre un passage RÉEL ; la mesure sur 100 cartes qui sert
    justement à le calibrer (mission point 3) ne doit pas en dépendre — sans ce garde-fou,
    `scripts/measure_insights_batch_cost.py` échouerait toujours sur la valeur de dev (0)."""
    monkeypatch.setattr(settings, "insights_budget_eur", 0.0)
    monkeypatch.setattr(settings, "insights_batch_model", MODEL)
    await _make_card(db_session)
    await _seed_usd_rate(db_session)

    report = await run_once(
        db_session,
        dry_run=True,
        pokepedia_client=_pokepedia_client(),
        bulbapedia_client=_bulbapedia_client(),
        batch_client=RaisingBatchClient(),
        ledger_path=ledger_path,
    )

    assert report.status == "dry_run"
    assert report.cards_selected == 1


async def test_run_once_submits_applies_results_and_updates_ledger(
    monkeypatch, db_session, ledger_path
):
    monkeypatch.setattr(settings, "platform_anthropic_api_key", "sk-ant-platform-test")
    monkeypatch.setattr(settings, "insights_budget_eur", 100.0)
    monkeypatch.setattr(settings, "insights_batch_model", MODEL)
    card = await _make_card(db_session)
    await _seed_usd_rate(db_session)

    custom_id = str(card.id)
    fake_client = FakeBatchClient(
        results=[_succeeded_result(custom_id, _extraction_payload())]
    )

    report = await run_once(
        db_session,
        pokepedia_client=_pokepedia_client(),
        bulbapedia_client=_bulbapedia_client(),
        batch_client=fake_client,
        ledger_path=ledger_path,
    )

    assert report.status == "termine"
    assert report.cards_applied == 1
    assert report.cost_eur > 0
    assert fake_client.created_requests is not None
    assert fake_client.created_requests[0]["custom_id"] == custom_id
    assert fake_client.created_requests[0]["params"]["model"] == MODEL

    result = await db_session.execute(select(CardInsight).where(CardInsight.card_id == card.id))
    row = result.scalar_one()
    assert row.anecdotes == [
        {"text": "Fait notable en français.", "source_url": POKEPEDIA_PAGE_URL}
    ]
    assert row.anecdotes_en == [
        {"text": "Notable fact in English.", "source_url": BULBAPEDIA_PAGE_URL}
    ]
    assert "Attaquant principal" in row.in_game_study
    assert row.source_model == source_marker(MODEL)
    assert row.game_study_source_model == source_marker(MODEL)

    ledger = Ledger.from_json(json.loads(ledger_path.read_text()))
    assert ledger.in_flight_batch is None
    assert Decimal(ledger.total_spent_eur) > 0
    assert ledger.completed_batch_ids == ["msgbatch_test_01"]


async def test_run_once_rejects_anecdote_with_url_outside_context(
    monkeypatch, db_session, ledger_path
):
    monkeypatch.setattr(settings, "platform_anthropic_api_key", "sk-ant-platform-test")
    monkeypatch.setattr(settings, "insights_budget_eur", 100.0)
    monkeypatch.setattr(settings, "insights_batch_model", MODEL)
    card = await _make_card(db_session)
    await _seed_usd_rate(db_session)

    custom_id = str(card.id)
    payload = _extraction_payload(extra_source_url="https://hors-contexte.example/")
    fake_client = FakeBatchClient(results=[_succeeded_result(custom_id, payload)])

    report = await run_once(
        db_session,
        pokepedia_client=_pokepedia_client(),
        bulbapedia_client=_bulbapedia_client(),
        batch_client=fake_client,
        ledger_path=ledger_path,
    )

    assert report.anecdotes_rejected_out_of_context == 1
    result = await db_session.execute(select(CardInsight).where(CardInsight.card_id == card.id))
    row = result.scalar_one()
    assert len(row.anecdotes) == 1  # seule l'anecdote sourcée a survécu au filtre
    assert row.anecdotes[0]["source_url"] == POKEPEDIA_PAGE_URL


async def test_run_once_second_pass_finds_nothing_left_to_cover(
    monkeypatch, db_session, ledger_path
):
    """Idempotence : une carte déjà couverte par un premier passage ne redevient pas candidate."""
    monkeypatch.setattr(settings, "platform_anthropic_api_key", "sk-ant-platform-test")
    monkeypatch.setattr(settings, "insights_budget_eur", 100.0)
    monkeypatch.setattr(settings, "insights_batch_model", MODEL)
    card = await _make_card(db_session)
    await _seed_usd_rate(db_session)

    fake_client = FakeBatchClient(results=[_succeeded_result(str(card.id), _extraction_payload())])
    first = await run_once(
        db_session,
        pokepedia_client=_pokepedia_client(),
        bulbapedia_client=_bulbapedia_client(),
        batch_client=fake_client,
        ledger_path=ledger_path,
    )
    assert first.status == "termine"

    second = await run_once(db_session, batch_client=RaisingBatchClient(), ledger_path=ledger_path)
    assert second.status == "catalogue_couvert"


async def test_run_once_resumes_an_in_flight_batch_still_processing(
    monkeypatch, db_session, ledger_path
):
    """Un lot déjà soumis (script précédent) et toujours en traitement se contente d'un seul
    sondage — jamais un nouveau lot resoumis, jamais une boucle bloquante côté appelant."""
    monkeypatch.setattr(settings, "platform_anthropic_api_key", "sk-ant-platform-test")

    save_ledger(
        Ledger(
            in_flight_batch=InFlightBatch(
                batch_id="msgbatch_resume",
                model=MODEL,
                usd_to_eur_rate="1.08",
                custom_id_to_card_id={"c1": str(uuid.uuid4())},
                allowed_urls={"c1": []},
            )
        ),
        ledger_path,
    )

    report = await run_once(
        db_session,
        batch_client=FakeBatchClient(statuses=["in_progress"]),
        ledger_path=ledger_path,
    )

    assert report.status == "en_cours"
    assert report.batch_id == "msgbatch_resume"
    # Le lot en cours reste en attente pour le prochain passage, jamais resoumis.
    resumed = Ledger.from_json(json.loads(ledger_path.read_text()))
    assert resumed.in_flight_batch is not None
    assert resumed.in_flight_batch.batch_id == "msgbatch_resume"


async def test_run_once_dry_run_flags_cards_without_any_wiki_context(
    monkeypatch, db_session, ledger_path
):
    """Mesure exigée par la mission (point 3) : le taux d'anecdotes rejetées faute de source
    doit être observable même sans appel Anthropic réel — `prepared_no_context` le porte."""
    monkeypatch.setattr(settings, "insights_budget_eur", 100.0)
    monkeypatch.setattr(settings, "insights_batch_model", MODEL)
    await _make_card(db_session)
    await _seed_usd_rate(db_session)

    report = await run_once(
        db_session,
        dry_run=True,
        pokepedia_client=_empty_mediawiki_client(POKEPEDIA_API_URL),
        bulbapedia_client=_empty_mediawiki_client(BULBAPEDIA_API_URL),
        batch_client=RaisingBatchClient(),
        ledger_path=ledger_path,
    )

    assert report.outcomes[0].status == "prepared_no_context"


async def test_run_once_stays_under_the_remaining_budget_and_says_so(
    monkeypatch, db_session, ledger_path
):
    """Un budget très serré ne doit soumettre aucune carte dont le coût estimé le dépasse déjà,
    plutôt que de spéculer sur un coût réel plus faible."""
    monkeypatch.setattr(settings, "platform_anthropic_api_key", "sk-ant-platform-test")
    monkeypatch.setattr(settings, "insights_budget_eur", 0.0000001)
    monkeypatch.setattr(settings, "insights_batch_model", MODEL)
    await _make_card(db_session)
    await _seed_usd_rate(db_session)

    report = await run_once(
        db_session,
        pokepedia_client=_pokepedia_client(),
        bulbapedia_client=_bulbapedia_client(),
        batch_client=RaisingBatchClient(),
        ledger_path=ledger_path,
    )

    assert report.status == "budget_insuffisant"
