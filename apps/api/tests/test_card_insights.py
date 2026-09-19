"""Anecdotes sourcées d'une carte (mission `v4-anecdotes`).

Avant ce lot, aucune de ces routes n'existait (`404 Not Found` sur `/cards/{id}/insights` et
consorts) : chaque test échoue sur `main.py` sans le routeur `card_insights` et passe une fois
branché. `test_get_insights_filters_out_anecdotes_without_a_source_in_context` est la preuve
ciblée du risque « hallucinations » de la mission (point 2, point 4) : sans le filtre sur
`allowed_urls` dans `pbm_api.insights.service`, elle échoue en recevant deux anecdotes au lieu
d'une (l'URL inventée n'est rejetée que par ce filtre, le prompt seul ne suffit pas à s'en
protéger dans un test hors ligne).

Aucun wiki ni clé IA réelle sur chimera : les collaborateurs réseau
(`get_pokepedia_client`/`get_bulbapedia_client`/`get_ai_provider_factory`, injectés par
dépendance FastAPI comme `ProviderKeyTester` pour le coffre de clés) sont remplacés par des
doubles déterministes.
"""

import re
import uuid

import httpx
import pytest
from sqlalchemy import select

from pbm_api.ai.base import ExtractionUsage
from pbm_api.config import settings
from pbm_api.insights.context import BULBAPEDIA_API_URL, POKEPEDIA_API_URL, MediaWikiClient
from pbm_api.main import app as fastapi_app
from pbm_api.models import AiProvider, Card, CardInsight, CardInsightReport, CardName, Set
from pbm_api.routers.card_insights import (
    get_ai_provider_factory,
    get_bulbapedia_client,
    get_pokepedia_client,
)
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
ANTHROPIC_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"

POKEPEDIA_PAGE_URL = "https://www.pokepedia.fr/Dracaufeu-Test"
BULBAPEDIA_PAGE_URL = "https://bulbapedia.bulbagarden.net/wiki/Charizard-Test"
HALLUCINATED_URL = "https://evil.example.com/invente"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "last_name": "Dresseur",
            "birth_date": "2000-01-01",
            "accept_terms": True,
        },
    )
    assert response.status_code == 202, response.text
    sent = client.email_sender.sent  # type: ignore[attr-defined]
    match = re.search(r"token=(\S+)", sent[-1]["body"])
    assert match
    await client.post("/auth/verify-email", json={"token": match.group(1)})
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client.cookies.get(settings.csrf_cookie_name)


async def _set_default_anthropic_key(client: httpx.AsyncClient, csrf: str) -> None:
    put = await client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": ANTHROPIC_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert put.status_code == 200, put.text
    patch = await client.patch(
        "/me/ai-settings",
        json={"default_provider": "anthropic"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert patch.status_code == 200, patch.text


async def _make_card(db_session) -> Card:
    suffix = uuid.uuid4().hex[:8]
    set_row = Set(code=f"insights-{suffix}", name="Extension de test")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(set_id=set_row.id, number="1", name="Dracaufeu-Test")
    db_session.add(card)
    await db_session.flush()
    db_session.add(CardName(card_id=card.id, language="en", name="Charizard-Test"))
    await db_session.flush()
    return card


def _mediawiki_handler(*, title: str, url: str, text: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("list") == "search":
            return httpx.Response(200, json={"query": {"search": [{"title": title}]}})
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": {
                        "1": {"title": title, "fullurl": url, "extract": text},
                    }
                }
            },
        )

    return httpx.MockTransport(handler)


def _empty_mediawiki_handler() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"search": []}})

    return httpx.MockTransport(handler)


def _pokepedia_client(*, empty: bool = False) -> MediaWikiClient:
    transport = (
        _empty_mediawiki_handler()
        if empty
        else _mediawiki_handler(
            title="Dracaufeu-Test", url=POKEPEDIA_PAGE_URL, text="Anecdote française sourcée."
        )
    )
    return MediaWikiClient(POKEPEDIA_API_URL, http_client=httpx.AsyncClient(transport=transport))


def _bulbapedia_client(*, empty: bool = False) -> MediaWikiClient:
    transport = (
        _empty_mediawiki_handler()
        if empty
        else _mediawiki_handler(
            title="Charizard-Test", url=BULBAPEDIA_PAGE_URL, text="English sourced anecdote."
        )
    )
    return MediaWikiClient(BULBAPEDIA_API_URL, http_client=httpx.AsyncClient(transport=transport))


class FakeAIProvider:
    """Double du fournisseur IA — aucune clé réelle sur chimera (voir
    `scripts/test_ai_extraction_manual.py` pour l'essai avec une vraie clé)."""

    DEFAULT_MODEL = "fake-anecdotes-model"

    def __init__(self, anecdotes: list[dict]) -> None:
        self._anecdotes = anecdotes
        self.calls = 0
        self.last_prompt: str | None = None

    async def extract(self, images, schema, prompt, *, model=None):
        self.calls += 1
        self.last_prompt = prompt
        result = schema(anecdotes=self._anecdotes)
        usage = ExtractionUsage(
            provider=AiProvider.anthropic,
            model=model or self.DEFAULT_MODEL,
            input_tokens=10,
            output_tokens=10,
        )
        return result, usage

    async def aclose(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    fastapi_app.dependency_overrides.pop(get_pokepedia_client, None)
    fastapi_app.dependency_overrides.pop(get_bulbapedia_client, None)
    fastapi_app.dependency_overrides.pop(get_ai_provider_factory, None)


def _override_wikis(*, empty: bool = False) -> None:
    fastapi_app.dependency_overrides[get_pokepedia_client] = lambda: _pokepedia_client(empty=empty)
    fastapi_app.dependency_overrides[get_bulbapedia_client] = lambda: _bulbapedia_client(
        empty=empty
    )


def _override_provider_factory(anecdotes: list[dict]) -> list[FakeAIProvider]:
    created: list[FakeAIProvider] = []

    def factory(provider, api_key):
        instance = FakeAIProvider(anecdotes)
        created.append(instance)
        return instance

    fastapi_app.dependency_overrides[get_ai_provider_factory] = lambda: factory
    return created


# --- Authentification et carte inconnue ----------------------------------------------------


async def test_get_insights_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(f"/cards/{uuid.uuid4()}/insights")
    assert response.status_code == 401


async def test_get_insights_returns_404_for_unknown_card(api_client: httpx.AsyncClient) -> None:
    await _register_verify_login(api_client, _unique_email("insights-404"))
    response = await api_client.get(f"/cards/{uuid.uuid4()}/insights")
    assert response.status_code == 404


# --- D4 : sans clé IA par défaut ------------------------------------------------------------


async def test_get_insights_without_default_key_returns_no_ai_key_status(
    api_client: httpx.AsyncClient, db_session
) -> None:
    await _register_verify_login(api_client, _unique_email("insights-nokey"))
    card = await _make_card(db_session)

    response = await api_client.get(f"/cards/{card.id}/insights")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "card_id": str(card.id),
        "status": "no_ai_key",
        "anecdotes": [],
        "generated_at": None,
    }


# --- Génération, filtrage des sources, cache -------------------------------------------------


async def test_get_insights_filters_out_anecdotes_without_a_source_in_context(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("insights-filter"))
    await _set_default_anthropic_key(api_client, csrf)
    card = await _make_card(db_session)

    _override_wikis()
    _override_provider_factory(
        [
            {"text": "Anecdote correctement sourcée.", "source_url": POKEPEDIA_PAGE_URL},
            {"text": "Anecdote inventée, URL absente du contexte.", "source_url": HALLUCINATED_URL},
        ]
    )

    response = await api_client.get(f"/cards/{card.id}/insights")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["anecdotes"] == [
        {"text": "Anecdote correctement sourcée.", "source_url": POKEPEDIA_PAGE_URL}
    ]

    result = await db_session.execute(select(CardInsight).where(CardInsight.card_id == card.id))
    stored = result.scalar_one()
    assert stored.anecdotes == [
        {"text": "Anecdote correctement sourcée.", "source_url": POKEPEDIA_PAGE_URL}
    ]
    assert stored.source_model == "anthropic:fake-anecdotes-model"


async def test_get_insights_uses_cache_on_second_call_without_calling_ai_again(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("insights-cache"))
    await _set_default_anthropic_key(api_client, csrf)
    card = await _make_card(db_session)

    _override_wikis()
    created = _override_provider_factory(
        [{"text": "Anecdote sourcée.", "source_url": POKEPEDIA_PAGE_URL}]
    )

    first = await api_client.get(f"/cards/{card.id}/insights")
    second = await api_client.get(f"/cards/{card.id}/insights")

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["anecdotes"] == second.json()["anecdotes"]
    assert len(created) == 1, "le fournisseur IA n'est appelé qu'une fois, au premier tir"


async def test_get_insights_without_any_context_page_returns_no_context_status(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("insights-nocontext"))
    await _set_default_anthropic_key(api_client, csrf)
    card = await _make_card(db_session)

    _override_wikis(empty=True)
    created = _override_provider_factory([])

    response = await api_client.get(f"/cards/{card.id}/insights")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "no_context"
    assert response.json()["anecdotes"] == []
    assert created == [], "aucun appel IA sans contexte à lui soumettre"


async def test_second_user_reads_the_shared_cache_without_owning_a_key(
    api_client: httpx.AsyncClient, db_session
) -> None:
    """Cache partagé (`card_insights`, une ligne par carte) : un utilisateur B sans clé IA lit
    les anecdotes générées par un utilisateur A — équivalent, pour cette donnée partagée, du
    test d'accès croisé (aucune fuite de la clé/du fournisseur de A vers B)."""
    csrf_a = await _register_verify_login(api_client, _unique_email("insights-user-a"))
    await _set_default_anthropic_key(api_client, csrf_a)
    card = await _make_card(db_session)

    _override_wikis()
    _override_provider_factory([{"text": "Anecdote sourcée.", "source_url": POKEPEDIA_PAGE_URL}])

    first = await api_client.get(f"/cards/{card.id}/insights")
    assert first.status_code == 200 and first.json()["status"] == "ready"

    # Logout implicite : une seconde connexion pose un nouveau cookie de session pour B.
    await api_client.post("/auth/logout", headers={CSRF_HEADER_NAME: csrf_a})
    await _register_verify_login(api_client, _unique_email("insights-user-b"))
    # B n'a jamais posé de clé IA — si la route en exigeait une pour une carte déjà en cache,
    # ce test échouerait avec `status == "no_ai_key"`.

    second = await api_client.get(f"/cards/{card.id}/insights")
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "ready"
    assert second.json()["anecdotes"] == first.json()["anecdotes"]
    assert "source_model" not in second.json()
    assert "provider" not in second.json()


# --- Bouton « Signaler une erreur » ---------------------------------------------------------


async def test_report_card_insight_requires_csrf(api_client: httpx.AsyncClient, db_session) -> None:
    await _register_verify_login(api_client, _unique_email("insights-report-csrf"))
    card = await _make_card(db_session)

    response = await api_client.post(f"/cards/{card.id}/insights/report", json={})
    assert response.status_code == 403


async def test_report_card_insight_upserts_a_single_row_per_user_and_card(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("insights-report"))
    card = await _make_card(db_session)

    first = await api_client.post(
        f"/cards/{card.id}/insights/report",
        json={"reason": "Anecdote fausse"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert first.status_code == 204

    second = await api_client.post(
        f"/cards/{card.id}/insights/report",
        json={"reason": "En fait, l'URL est cassée"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert second.status_code == 204

    result = await db_session.execute(
        select(CardInsightReport).where(CardInsightReport.card_id == card.id)
    )
    reports = result.scalars().all()
    assert len(reports) == 1
    assert reports[0].reason == "En fait, l'URL est cassée"


async def test_report_card_insight_is_scoped_per_user(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf_a = await _register_verify_login(api_client, _unique_email("insights-report-a"))
    card = await _make_card(db_session)
    report_a = await api_client.post(
        f"/cards/{card.id}/insights/report",
        json={"reason": "Vu par A"},
        headers={CSRF_HEADER_NAME: csrf_a},
    )
    assert report_a.status_code == 204

    await api_client.post("/auth/logout", headers={CSRF_HEADER_NAME: csrf_a})
    csrf_b = await _register_verify_login(api_client, _unique_email("insights-report-b"))
    report_b = await api_client.post(
        f"/cards/{card.id}/insights/report",
        json={"reason": "Vu par B"},
        headers={CSRF_HEADER_NAME: csrf_b},
    )
    assert report_b.status_code == 204

    result = await db_session.execute(
        select(CardInsightReport.user_id, CardInsightReport.reason).where(
            CardInsightReport.card_id == card.id
        )
    )
    rows = {user_id: reason for user_id, reason in result.all()}
    assert len(rows) == 2
    assert set(rows.values()) == {"Vu par A", "Vu par B"}


async def test_report_card_insight_returns_404_for_unknown_card(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("insights-report-404"))
    response = await api_client.post(
        f"/cards/{uuid.uuid4()}/insights/report",
        json={},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 404
