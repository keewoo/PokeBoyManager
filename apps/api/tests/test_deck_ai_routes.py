"""`POST /me/decks/{id}/propose` — assistant IA de construction (mission `v7-deck-ia`).

Avant ce lot, la route n'existe pas : chaque test échoue en `404`/`405` et passe une fois la
route branchée. Un seul appel IA par proposition (principe « dès le premier tir »), la proposition
est corrigée avant d'être écrite (jamais montrée telle quelle), la légalité est recalculée côté
serveur, et l'accès croisé est vérifié (utilisateur B -> 404 sur le deck de A).

Aucune clé IA réelle sur chimera : le fournisseur est injecté par dépendance FastAPI
(`get_deck_ai_provider_factory`) et remplacé ici par un double déterministe, comme pour les
anecdotes (`test_card_insights`).
"""

import re
import uuid

import httpx
import pytest

from pbm_api.ai.base import ExtractionUsage
from pbm_api.config import settings
from pbm_api.main import app as fastapi_app
from pbm_api.models import AiProvider, Card, Set
from pbm_api.models.collection import CollectionItem
from pbm_api.routers.decks import get_deck_ai_provider_factory
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
ANTHROPIC_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> tuple[str, str]:
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
    return login.json()["id"], client.cookies.get(settings.csrf_cookie_name)


def _csrf(token: str) -> dict[str, str]:
    return {CSRF_HEADER_NAME: token}


async def _set_default_anthropic_key(client: httpx.AsyncClient, csrf: str) -> None:
    put = await client.put(
        "/me/ai-keys/anthropic", json={"api_key": ANTHROPIC_KEY}, headers=_csrf(csrf)
    )
    assert put.status_code == 200, put.text
    patch = await client.patch(
        "/me/ai-settings", json={"default_provider": "anthropic"}, headers=_csrf(csrf)
    )
    assert patch.status_code == 200, patch.text


async def _make_card(
    db_session,
    *,
    name: str,
    supertype: str = "Pokémon",
    stage: str | None = "Base",
    element_type: str | None = "fire",
    energy_type: str | None = None,
    legal_standard: bool | None = True,
) -> Card:
    set_row = Set(code=f"deckia-{uuid.uuid4().hex[:8]}", name="Set deck IA", series="Série test")
    db_session.add(set_row)
    await db_session.flush()
    card = Card(
        set_id=set_row.id,
        number="1",
        name=name,
        supertype=supertype,
        stage=stage,
        element_type=element_type,
        energy_type=energy_type,
        legal_standard=legal_standard,
        attacks=[{"name": "Éclair", "cost": ["fire"]}],
    )
    db_session.add(card)
    await db_session.flush()
    return card


async def _own(db_session, user_id: str, card: Card, count: int) -> None:
    db_session.add_all(
        [CollectionItem(user_id=uuid.UUID(user_id), card_id=card.id) for _ in range(count)]
    )
    await db_session.flush()


class FakeDeckAIProvider:
    """Double du fournisseur IA : renvoie une proposition figée (par `ref`) sans réseau ni clé."""

    DEFAULT_MODEL = "fake-deck-model"

    def __init__(self, cards: list[dict], summary: str | None) -> None:
        self._cards = cards
        self._summary = summary
        self.calls = 0
        self.last_prompt: str | None = None

    async def extract(self, images, schema, prompt, *, model=None):
        self.calls += 1
        self.last_prompt = prompt
        result = schema(cards=self._cards, summary=self._summary)
        usage = ExtractionUsage(
            provider=AiProvider.anthropic,
            model=model or self.DEFAULT_MODEL,
            input_tokens=1200,
            output_tokens=300,
        )
        return result, usage

    async def aclose(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    fastapi_app.dependency_overrides.pop(get_deck_ai_provider_factory, None)


def _override_provider(
    cards: list[dict], summary: str | None = "Deck Feu."
) -> list[FakeDeckAIProvider]:
    created: list[FakeDeckAIProvider] = []

    def factory(provider, api_key):
        instance = FakeDeckAIProvider(cards, summary)
        created.append(instance)
        return instance

    fastapi_app.dependency_overrides[get_deck_ai_provider_factory] = lambda: factory
    return created


async def _create_deck(client: httpx.AsyncClient, csrf: str, name: str = "Deck IA") -> str:
    created = await client.post("/me/decks", json={"name": name}, headers=_csrf(csrf))
    assert created.status_code == 201, created.text
    return created.json()["id"]


# --------------------------------------------------------------------------------- authentification
async def test_propose_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(f"/me/decks/{uuid.uuid4()}/propose", json={})
    assert response.status_code == 401


async def test_propose_unknown_deck_returns_404(api_client: httpx.AsyncClient) -> None:
    _uid, csrf = await _register_verify_login(api_client, _unique_email("deckia-404"))
    await _set_default_anthropic_key(api_client, csrf)
    _override_provider([{"ref": 0, "quantity": 1, "reason": "x"}])
    response = await api_client.post(
        f"/me/decks/{uuid.uuid4()}/propose", json={}, headers=_csrf(csrf)
    )
    assert response.status_code == 404


# ---- clé IA absente / collection vide ----
async def test_propose_without_ai_key_returns_409(
    api_client: httpx.AsyncClient, db_session
) -> None:
    _uid, csrf = await _register_verify_login(api_client, _unique_email("deckia-nokey"))
    deck_id = await _create_deck(api_client, csrf)
    response = await api_client.post(f"/me/decks/{deck_id}/propose", json={}, headers=_csrf(csrf))
    assert response.status_code == 409, response.text


async def test_propose_with_empty_collection_returns_409(
    api_client: httpx.AsyncClient, db_session
) -> None:
    _uid, csrf = await _register_verify_login(api_client, _unique_email("deckia-empty"))
    await _set_default_anthropic_key(api_client, csrf)
    deck_id = await _create_deck(api_client, csrf)
    _override_provider([{"ref": 0, "quantity": 1, "reason": "x"}])
    response = await api_client.post(f"/me/decks/{deck_id}/propose", json={}, headers=_csrf(csrf))
    assert response.status_code == 409, response.text


# ---- proposition légale complète ----
async def test_propose_builds_a_legal_deck_from_owned_cards(
    api_client: httpx.AsyncClient, db_session
) -> None:
    uid, csrf = await _register_verify_login(api_client, _unique_email("deckia-ok"))
    await _set_default_anthropic_key(api_client, csrf)
    pika = await _make_card(db_session, name="Pikachu")
    await _make_card(db_session, name="Énergie Feu", supertype="Énergie", stage=None,
                     element_type=None, energy_type="Normal", legal_standard=None)
    await _own(db_session, uid, pika, 4)
    deck_id = await _create_deck(api_client, csrf)

    providers = _override_provider(
        [{"ref": 0, "quantity": 4, "reason": "Attaquant principal."}], summary="Deck Feu agressif."
    )
    response = await api_client.post(
        f"/me/decks/{deck_id}/propose",
        json={"types": [{"type": "fire", "share": 100}], "style": "agressif", "size": 60},
        headers=_csrf(csrf),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # un SEUL appel IA (principe « dès le premier tir » + mesure du coût)
    assert providers[0].calls == 1
    assert body["input_tokens"] == 1200 and body["output_tokens"] == 300
    assert body["summary"] == "Deck Feu agressif."
    # deck légal : 60 cartes, possédées, Pokémon de base, complété en Énergies
    assert body["deck"]["legality"]["card_count"] == 60
    assert body["deck"]["legality"]["legal"] is True
    # une explication d'une ligne par carte
    names = {e["card_name"] for e in body["explanations"]}
    assert "Pikachu" in names
    assert all(e["reason"] for e in body["explanations"])
    # la trace des corrections mentionne le complètement en Énergies
    assert any(c["code"] == "energy_fill" for c in body["corrections"])


async def test_propose_corrects_overquantity_and_surfaces_trace(
    api_client: httpx.AsyncClient, db_session
) -> None:
    uid, csrf = await _register_verify_login(api_client, _unique_email("deckia-cap"))
    await _set_default_anthropic_key(api_client, csrf)
    pika = await _make_card(db_session, name="Pikachu")
    await _make_card(db_session, name="Énergie Feu", supertype="Énergie", stage=None,
                     element_type=None, energy_type="Normal", legal_standard=None)
    await _own(db_session, uid, pika, 6)
    deck_id = await _create_deck(api_client, csrf)

    # Le modèle propose 6 exemplaires : la règle des 4 doit ramener à 4, et le tracer.
    _override_provider([{"ref": 0, "quantity": 6, "reason": "Trop d'exemplaires."}])
    response = await api_client.post(f"/me/decks/{deck_id}/propose", json={}, headers=_csrf(csrf))

    assert response.status_code == 200, response.text
    body = response.json()
    pika_card = next(c for c in body["deck"]["cards"] if c["card_name"] == "Pikachu")
    assert pika_card["quantity"] == 4
    assert any(c["code"] == "copy_cap" for c in body["corrections"])


# ------------------------------------------------------------------------------------ accès croisé
async def test_propose_cross_access_is_forbidden(api_client: httpx.AsyncClient, db_session) -> None:
    # Utilisateur A crée un deck ; l'utilisateur B, connecté, ne doit pas pouvoir le proposer.
    uid_a, csrf_a = await _register_verify_login(api_client, _unique_email("deckia-a"))
    await _set_default_anthropic_key(api_client, csrf_a)
    pika = await _make_card(db_session, name="Pikachu")
    await _own(db_session, uid_a, pika, 4)
    deck_a = await _create_deck(api_client, csrf_a)

    # bascule sur l'utilisateur B (nouvelle session dans le même client)
    _uid_b, csrf_b = await _register_verify_login(api_client, _unique_email("deckia-b"))
    await _set_default_anthropic_key(api_client, csrf_b)
    _override_provider([{"ref": 0, "quantity": 4, "reason": "x"}])

    response = await api_client.post(
        f"/me/decks/{deck_a}/propose", json={}, headers=_csrf(csrf_b)
    )
    assert response.status_code == 404, response.text
