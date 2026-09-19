"""Étude d'utilisation en jeu d'une carte (mission `v4-jeu`).

Avant ce lot, `/cards/{id}/in-game-study` n'existait pas (`404 Not Found` faute de routeur) :
`test_get_in_game_study_requires_authentication`/`test_get_in_game_study_returns_404_for_
unknown_card` échouent sans ce lot et passent une fois branché.

`test_get_in_game_study_without_default_key_still_exposes_deterministic_data` est la preuve
ciblée d'un choix de conception explicite (§ `pbm_api.ingame.service`) : contrairement aux
anecdotes (où D4 masque tout), l'absence de clé IA ne masque ici que la synthèse — légalités,
règle des Prix et présence en tournoi restent déterministes et ne dépendent d'aucune clé.

`test_get_in_game_study_regenerates_the_study_after_a_newer_tournament_refresh` est la preuve
ciblée du risque « étude figée » : sans la comparaison `tournament_checked_at >
game_study_generated_at` dans `pbm_api.ingame.service._study_fresh`, ce test échouerait en
recevant l'ancienne synthèse malgré un relevé de tournoi plus récent.

Aucune clé IA réelle sur chimera : le fournisseur (`get_ai_provider_factory`) est remplacé par
un double déterministe, comme pour les anecdotes."""

import re
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select

from pbm_api.ai.base import ExtractionUsage
from pbm_api.config import settings
from pbm_api.main import app as fastapi_app
from pbm_api.models import (
    AiProvider,
    Card,
    CardInsight,
    CardTournamentPresence,
    Set,
    TournamentPresenceStatus,
)
from pbm_api.routers.in_game_study import get_ai_provider_factory
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
ANTHROPIC_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"
MEW_RELEASE = date(2023, 9, 22)


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


async def _make_card(
    db_session,
    *,
    name: str = "Dracaufeu-ex",
    supertype: str = "Pokemon",
    legal_standard: bool | None = False,
    legal_expanded: bool | None = True,
) -> Card:
    suffix = uuid.uuid4().hex[:8]
    set_row = Set(code=f"jeu-{suffix}", name="Extension de test", release_date=MEW_RELEASE)
    db_session.add(set_row)
    await db_session.flush()
    card = Card(
        set_id=set_row.id,
        number="1",
        name=name,
        supertype=supertype,
        legal_standard=legal_standard,
        legal_expanded=legal_expanded,
        attacks=[{"name": "Vortex Explosif", "damage": 330}],
    )
    db_session.add(card)
    await db_session.flush()
    return card


async def _add_tournament_presence(
    db_session,
    card_id: uuid.UUID,
    *,
    status: TournamentPresenceStatus = TournamentPresenceStatus.checked,
    decks: list[dict] | None = None,
    checked_at: datetime | None = None,
) -> CardTournamentPresence:
    presence = CardTournamentPresence(
        card_id=card_id,
        status=status,
        source_url="https://limitlesstcg.com/cards/MEW/6" if status.value == "checked" else None,
        decks=decks,
        checked_at=checked_at or datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(presence)
    await db_session.flush()
    return presence


class FakeAIProvider:
    DEFAULT_MODEL = "fake-ingame-model"

    def __init__(self, extraction: dict) -> None:
        self._extraction = extraction
        self.calls = 0
        self.last_prompt: str | None = None

    async def extract(self, images, schema, prompt, *, model=None):
        self.calls += 1
        self.last_prompt = prompt
        result = schema(**self._extraction)
        usage = ExtractionUsage(
            provider=AiProvider.anthropic,
            model=model or self.DEFAULT_MODEL,
            input_tokens=10,
            output_tokens=10,
        )
        return result, usage

    async def aclose(self) -> None:
        return None


DEFAULT_EXTRACTION = {
    "role": "Attaquant principal",
    "strengths": "Gros dégâts en fin de partie.",
    "weaknesses": "Fragile face à l'eau.",
    "related_cards": ["Pidgeot ex"],
    "playability_note": "Solide en Étendu.",
}


def _override_provider_factory(extraction: dict = DEFAULT_EXTRACTION) -> list[FakeAIProvider]:
    created: list[FakeAIProvider] = []

    def factory(provider, api_key):
        instance = FakeAIProvider(extraction)
        created.append(instance)
        return instance

    fastapi_app.dependency_overrides[get_ai_provider_factory] = lambda: factory
    return created


async def _clear_overrides():
    fastapi_app.dependency_overrides.pop(get_ai_provider_factory, None)


# --- Authentification et carte inconnue ----------------------------------------------------


async def test_get_in_game_study_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(f"/cards/{uuid.uuid4()}/in-game-study")
    assert response.status_code == 401


async def test_get_in_game_study_returns_404_for_unknown_card(
    api_client: httpx.AsyncClient,
) -> None:
    await _register_verify_login(api_client, _unique_email("jeu-404"))
    response = await api_client.get(f"/cards/{uuid.uuid4()}/in-game-study")
    assert response.status_code == 404


# --- Légalités et règle des Prix : déterministe, jamais dépendant de la clé IA -------------


async def test_get_in_game_study_without_default_key_still_exposes_deterministic_data(
    api_client: httpx.AsyncClient, db_session
) -> None:
    await _register_verify_login(api_client, _unique_email("jeu-nokey"))
    card = await _make_card(db_session)
    await _add_tournament_presence(db_session, card.id, decks=[])
    await db_session.commit()

    response = await api_client.get(f"/cards/{card.id}/in-game-study")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["legalities"] == {"standard": False, "expanded": True}
    assert body["prize_rule"] == {"applies": True, "prizes_taken": 2, "label": "2 Prix (carte ex)"}
    assert body["attacks"] == [{"name": "Vortex Explosif", "damage": 330}]
    assert body["tournament_presence"]["status"] == "checked"
    assert body["study"]["status"] == "no_ai_key"
    assert body["study"]["text"] is None


async def test_get_in_game_study_reports_unavailable_tournament_presence_when_never_checked(
    api_client: httpx.AsyncClient, db_session
) -> None:
    await _register_verify_login(api_client, _unique_email("jeu-notournament"))
    card = await _make_card(db_session)
    await db_session.commit()

    response = await api_client.get(f"/cards/{card.id}/in-game-study")

    assert response.status_code == 200, response.text
    assert response.json()["tournament_presence"] == {
        "status": "unavailable",
        "source_url": None,
        "checked_at": None,
        "decks": [],
    }


# --- Synthèse IA, cache -----------------------------------------------------------------


async def test_get_in_game_study_generates_and_caches_the_study(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("jeu-generate"))
    await _set_default_anthropic_key(api_client, csrf)
    card = await _make_card(db_session)
    decks = [
        {
            "deck_name": "Charizard Pidgeot",
            "tournament_name": "Regional Lille",
            "tournament_url": "https://limitlesstcg.com/tournaments/1",
            "placement": "229th",
        }
    ]
    await _add_tournament_presence(db_session, card.id, decks=decks)
    await db_session.commit()

    created = _override_provider_factory()
    try:
        response = await api_client.get(f"/cards/{card.id}/in-game-study")
    finally:
        await _clear_overrides()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["study"]["status"] == "ready"
    assert "Attaquant principal" in body["study"]["text"]
    assert len(created) == 1
    assert "Regional Lille" in created[0].last_prompt

    stored = (
        await db_session.execute(select(CardInsight).where(CardInsight.card_id == card.id))
    ).scalar_one()
    assert stored.game_study_source_model == "anthropic:fake-ingame-model"


async def test_get_in_game_study_uses_cache_on_second_call_without_calling_ai_again(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("jeu-cache"))
    await _set_default_anthropic_key(api_client, csrf)
    card = await _make_card(db_session)
    await _add_tournament_presence(db_session, card.id, decks=[])
    await db_session.commit()

    created = _override_provider_factory()
    try:
        first = await api_client.get(f"/cards/{card.id}/in-game-study")
        second = await api_client.get(f"/cards/{card.id}/in-game-study")
    finally:
        await _clear_overrides()

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["study"]["text"] == second.json()["study"]["text"]
    assert len(created) == 1, "le fournisseur IA n'est appelé qu'une fois, au premier tir"


async def test_get_in_game_study_regenerates_the_study_after_a_newer_tournament_refresh(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("jeu-stale"))
    await _set_default_anthropic_key(api_client, csrf)
    card = await _make_card(db_session)
    await _add_tournament_presence(db_session, card.id, decks=[])
    await db_session.commit()

    _override_provider_factory({**DEFAULT_EXTRACTION, "role": "Rôle initial"})
    try:
        first = await api_client.get(f"/cards/{card.id}/in-game-study")
    finally:
        await _clear_overrides()
    assert "Rôle initial" in first.json()["study"]["text"]

    # Le relevé de tournoi est rafraîchi après la génération : une synthèse qui l'ignorerait
    # resterait fausse (elle pourrait par exemple continuer d'affirmer une absence de
    # présence en tournoi devenue inexacte).
    presence = (
        await db_session.execute(
            select(CardTournamentPresence).where(CardTournamentPresence.card_id == card.id)
        )
    ).scalar_one()
    presence.checked_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
    await db_session.commit()

    created = _override_provider_factory({**DEFAULT_EXTRACTION, "role": "Rôle mis à jour"})
    try:
        second = await api_client.get(f"/cards/{card.id}/in-game-study")
    finally:
        await _clear_overrides()

    assert "Rôle mis à jour" in second.json()["study"]["text"]
    assert len(created) == 1


async def test_second_user_reads_the_shared_study_cache_without_owning_a_key(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf_a = await _register_verify_login(api_client, _unique_email("jeu-user-a"))
    await _set_default_anthropic_key(api_client, csrf_a)
    card = await _make_card(db_session)
    await _add_tournament_presence(db_session, card.id, decks=[])
    await db_session.commit()

    _override_provider_factory()
    try:
        first = await api_client.get(f"/cards/{card.id}/in-game-study")
    finally:
        await _clear_overrides()
    assert first.status_code == 200 and first.json()["study"]["status"] == "ready"

    await api_client.post("/auth/logout", headers={CSRF_HEADER_NAME: csrf_a})
    await _register_verify_login(api_client, _unique_email("jeu-user-b"))
    # B n'a jamais posé de clé IA — si la route en exigeait une pour une carte déjà en cache,
    # ce test échouerait avec `study.status == "no_ai_key"`.

    second = await api_client.get(f"/cards/{card.id}/in-game-study")
    assert second.status_code == 200, second.text
    assert second.json()["study"]["status"] == "ready"
    assert second.json()["study"]["text"] == first.json()["study"]["text"]
