"""Coffre de clés IA : ajouter/tester/remplacer/supprimer une clé par fournisseur, choisir le
fournisseur par défaut, lire l'usage.

Avant ce lot, aucune de ces routes n'existait (404 sur `/me/ai-keys` et consorts) : chacun de
ces tests échoue sur `main.py` sans le routeur `ai_keys` et passe une fois branché.
"""

import re
import uuid
from datetime import date, timedelta

import httpx
from sqlalchemy import func, select

from pbm_api.ai.providers import ProviderKeyTester, get_provider_key_tester
from pbm_api.config import settings
from pbm_api.main import app as fastapi_app
from pbm_api.models import AiCredential, AiProvider, AiUsageMonthly, User
from pbm_api.security.crypto import decrypt_api_key
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
ANTHROPIC_KEY = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"
OTHER_ANTHROPIC_KEY = "sk-ant-api03-zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"


def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


class FakeProviderKeyTester(ProviderKeyTester):
    """Aucune clé IA réelle n'est disponible sur cette machine : ce double déterministe
    remplace l'appel réseau (voir `scripts/test_ai_key_manual.py` pour l'essai avec une
    vraie clé). Enregistre la clé reçue pour vérifier qu'elle a bien été déchiffrée."""

    def __init__(self, valid_keys: frozenset[str] = frozenset({ANTHROPIC_KEY})) -> None:
        self._valid_keys = valid_keys
        self.received_keys: list[str] = []

    async def test(self, provider: AiProvider, api_key: str) -> tuple[bool, str]:
        self.received_keys.append(api_key)
        if api_key in self._valid_keys:
            return True, "Clé valide."
        return False, "Clé refusée par le fournisseur."


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
    """Inscrit, vérifie et connecte un utilisateur ; renvoie le jeton CSRF de sa session."""
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


# --- Ajouter / lister / remplacer / supprimer une clé -------------------------------------


async def test_ai_keys_routes_require_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/me/ai-keys")
    assert response.status_code == 401


async def test_put_ai_key_stores_it_encrypted_and_never_returns_the_raw_key(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("byok-put"))

    response = await api_client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": ANTHROPIC_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "anthropic"
    assert ANTHROPIC_KEY not in response.text
    assert body["key_mask"] != ANTHROPIC_KEY
    assert body["key_mask"].startswith("sk-ant-a")

    credential = (
        await db_session.execute(select(AiCredential).where(AiCredential.provider == "anthropic"))
    ).scalar_one()
    assert ANTHROPIC_KEY.encode("utf-8") not in credential.encrypted_key
    assert decrypt_api_key(credential.encrypted_key, credential.nonce, credential.user_id) == (
        ANTHROPIC_KEY
    )


async def test_put_ai_key_never_echoes_a_rejected_raw_key_in_the_422_body(
    api_client: httpx.AsyncClient,
) -> None:
    """FastAPI renvoie par défaut la valeur soumise dans `detail[].input` sur une erreur de
    validation : sans le redacteur global (`pbm_api.security.validation_errors`), une clé
    trop courte reviendrait en clair dans la réponse."""
    csrf = await _register_verify_login(api_client, _unique_email("byok-422"))
    too_short_key = "sk-an"

    response = await api_client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": too_short_key},
        headers={CSRF_HEADER_NAME: csrf},
    )

    assert response.status_code == 422
    assert too_short_key not in response.text
    assert response.json()["detail"][0]["input"] == "***"


async def test_put_ai_key_requires_csrf_token(api_client: httpx.AsyncClient) -> None:
    await _register_verify_login(api_client, _unique_email("byok-nocsrf"))

    response = await api_client.put("/me/ai-keys/anthropic", json={"api_key": ANTHROPIC_KEY})
    assert response.status_code == 403


async def test_put_ai_key_replaces_the_previous_key_for_the_same_provider(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("byok-replace"))

    await api_client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": ANTHROPIC_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )
    await api_client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": OTHER_ANTHROPIC_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )

    count = await db_session.scalar(
        select(func.count()).select_from(AiCredential).where(AiCredential.provider == "anthropic")
    )
    assert count == 1
    credential = (
        await db_session.execute(select(AiCredential).where(AiCredential.provider == "anthropic"))
    ).scalar_one()
    assert decrypt_api_key(credential.encrypted_key, credential.nonce, credential.user_id) == (
        OTHER_ANTHROPIC_KEY
    )


async def test_get_ai_keys_lists_only_masks(api_client: httpx.AsyncClient) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("byok-list"))
    await api_client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": ANTHROPIC_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )

    response = await api_client.get("/me/ai-keys")
    assert response.status_code == 200
    keys = response.json()
    assert len(keys) == 1
    assert keys[0]["provider"] == "anthropic"
    assert ANTHROPIC_KEY not in response.text


async def test_delete_ai_key_removes_it(api_client: httpx.AsyncClient, db_session) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("byok-delete"))
    await api_client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": ANTHROPIC_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )

    response = await api_client.delete("/me/ai-keys/anthropic", headers={CSRF_HEADER_NAME: csrf})
    assert response.status_code == 204

    remaining = await api_client.get("/me/ai-keys")
    assert remaining.json() == []


async def test_delete_ai_key_returns_404_when_no_key_is_stored(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("byok-delete-missing"))

    response = await api_client.delete("/me/ai-keys/openai", headers={CSRF_HEADER_NAME: csrf})
    assert response.status_code == 404


# --- Tester une clé --------------------------------------------------------------------


async def test_test_route_validates_a_key_not_yet_saved(api_client: httpx.AsyncClient) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("byok-test"))
    fastapi_app.dependency_overrides[get_provider_key_tester] = lambda: FakeProviderKeyTester()

    try:
        valid = await api_client.post(
            "/me/ai-keys/anthropic/test",
            json={"api_key": ANTHROPIC_KEY},
            headers={CSRF_HEADER_NAME: csrf},
        )
        invalid = await api_client.post(
            "/me/ai-keys/anthropic/test",
            json={"api_key": "sk-ant-not-the-right-one"},
            headers={CSRF_HEADER_NAME: csrf},
        )
    finally:
        del fastapi_app.dependency_overrides[get_provider_key_tester]

    assert valid.status_code == 200
    assert valid.json() == {"valid": True, "message": "Clé valide."}
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False


async def test_test_route_tests_the_stored_key_when_none_is_given(
    api_client: httpx.AsyncClient,
) -> None:
    """Le fournisseur reçoit la clé déchiffrée, pas le chiffré ni le masque."""
    csrf = await _register_verify_login(api_client, _unique_email("byok-test-stored"))
    await api_client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": ANTHROPIC_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )
    tester = FakeProviderKeyTester()
    fastapi_app.dependency_overrides[get_provider_key_tester] = lambda: tester

    try:
        response = await api_client.post(
            "/me/ai-keys/anthropic/test", json={}, headers={CSRF_HEADER_NAME: csrf}
        )
    finally:
        del fastapi_app.dependency_overrides[get_provider_key_tester]

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert tester.received_keys == [ANTHROPIC_KEY]


async def test_test_route_returns_404_without_a_stored_key_and_none_given(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("byok-test-missing"))
    fastapi_app.dependency_overrides[get_provider_key_tester] = lambda: FakeProviderKeyTester()

    try:
        response = await api_client.post(
            "/me/ai-keys/openai/test", json={}, headers={CSRF_HEADER_NAME: csrf}
        )
    finally:
        del fastapi_app.dependency_overrides[get_provider_key_tester]

    assert response.status_code == 404


# --- Fournisseur et modèle par défaut ----------------------------------------------------


async def test_get_ai_settings_defaults_to_null(api_client: httpx.AsyncClient) -> None:
    await _register_verify_login(api_client, _unique_email("byok-settings-default"))

    response = await api_client.get("/me/ai-settings")
    assert response.status_code == 200
    assert response.json() == {"default_provider": None, "default_model": None}


async def test_patch_ai_settings_rejects_default_provider_without_a_stored_key(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("byok-settings-nokey"))

    response = await api_client.patch(
        "/me/ai-settings",
        json={"default_provider": "anthropic"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 400


async def test_patch_ai_settings_updates_default_provider_and_model_independently(
    api_client: httpx.AsyncClient,
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("byok-settings-ok"))
    await api_client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": ANTHROPIC_KEY},
        headers={CSRF_HEADER_NAME: csrf},
    )

    set_provider = await api_client.patch(
        "/me/ai-settings",
        json={"default_provider": "anthropic"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert set_provider.status_code == 200
    assert set_provider.json() == {"default_provider": "anthropic", "default_model": None}

    set_model = await api_client.patch(
        "/me/ai-settings",
        json={"default_model": "claude-haiku-4-5"},
        headers={CSRF_HEADER_NAME: csrf},
    )
    assert set_model.status_code == 200
    # Le fournisseur par défaut, non renvoyé dans cette requête, reste inchangé (sémantique PATCH).
    assert set_model.json() == {
        "default_provider": "anthropic",
        "default_model": "claude-haiku-4-5",
    }


# --- Usage -------------------------------------------------------------------------------


async def test_get_ai_usage_returns_entries_for_the_current_user(
    api_client: httpx.AsyncClient, db_session
) -> None:
    csrf = await _register_verify_login(api_client, _unique_email("byok-usage"))
    me = await api_client.get("/me/ai-settings", headers={CSRF_HEADER_NAME: csrf})
    assert me.status_code == 200

    result = await db_session.execute(select(User).where(User.email.like("byok-usage-%")))
    user = result.scalar_one()
    db_session.add(
        AiUsageMonthly(
            user_id=user.id,
            provider=AiProvider.anthropic,
            period=date.today().replace(day=1),
            calls_count=3,
            tokens_count=1200,
            estimated_cost_eur="0.0450",
        )
    )
    await db_session.flush()

    response = await api_client.get("/me/ai-usage")
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["provider"] == "anthropic"
    assert entries[0]["calls_count"] == 3
    assert entries[0]["tokens_count"] == 1200


# --- Isolation entre utilisateurs (test d'accès croisé) -----------------------------------


async def test_cross_user_isolation_on_ai_keys(api_client: httpx.AsyncClient, db_session) -> None:
    """Test d'accès croisé : `get_current_user` dérive uniquement du cookie de session de
    l'appelant, jamais d'un identifiant fourni par le client — B ne voit ni ne peut agir sur
    les clés de A, même en ciblant le même fournisseur."""
    csrf_a = await _register_verify_login(api_client, _unique_email("iso-a"))
    await api_client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": ANTHROPIC_KEY},
        headers={CSRF_HEADER_NAME: csrf_a},
    )

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b:
        client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        csrf_b = await _register_verify_login(client_b, _unique_email("iso-b"))

        # B ne voit aucune clé : les siennes seulement, jamais celles de A.
        list_b = await client_b.get("/me/ai-keys")
        assert list_b.json() == []

        # B ne peut pas supprimer la clé de A en visant le même fournisseur : 404, pas 204.
        delete_b = await client_b.delete(
            "/me/ai-keys/anthropic", headers={CSRF_HEADER_NAME: csrf_b}
        )
        assert delete_b.status_code == 404

    # La clé de A n'a pas bougé (le client de A n'a jamais changé de cookies).
    still_there = await api_client.get("/me/ai-keys")
    assert len(still_there.json()) == 1


async def test_test_route_returns_404_for_another_users_key(
    api_client: httpx.AsyncClient,
) -> None:
    """B ne peut pas faire tester la clé enregistrée de A en visant le même fournisseur sans
    fournir de clé : `_get_credential` filtre par `user_id`, B n'en a pas — 404, jamais la clé
    de A envoyée au fournisseur en son nom."""
    csrf_a = await _register_verify_login(api_client, _unique_email("byok-test-iso-a"))
    await api_client.put(
        "/me/ai-keys/anthropic",
        json={"api_key": ANTHROPIC_KEY},
        headers={CSRF_HEADER_NAME: csrf_a},
    )

    transport = httpx.ASGITransport(app=fastapi_app)
    tester = FakeProviderKeyTester()
    fastapi_app.dependency_overrides[get_provider_key_tester] = lambda: tester
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="https://testserver"
        ) as client_b:
            client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
            csrf_b = await _register_verify_login(client_b, _unique_email("byok-test-iso-b"))

            response = await client_b.post(
                "/me/ai-keys/anthropic/test", json={}, headers={CSRF_HEADER_NAME: csrf_b}
            )
    finally:
        del fastapi_app.dependency_overrides[get_provider_key_tester]

    assert response.status_code == 404
    assert tester.received_keys == []


async def test_cross_user_isolation_on_ai_usage(api_client: httpx.AsyncClient, db_session) -> None:
    email_a = _unique_email("usage-iso-a")
    await _register_verify_login(api_client, email_a)
    user_a = (await db_session.execute(select(User).where(User.email == email_a))).scalar_one()
    db_session.add(
        AiUsageMonthly(
            user_id=user_a.id,
            provider=AiProvider.anthropic,
            period=date.today().replace(day=1) - timedelta(days=31),
            calls_count=42,
            tokens_count=9000,
            estimated_cost_eur="1.2300",
        )
    )
    await db_session.flush()

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client_b:
        client_b.email_sender = api_client.email_sender  # type: ignore[attr-defined]
        await _register_verify_login(client_b, _unique_email("usage-iso-b"))

        response = await client_b.get("/me/ai-usage")
        assert response.status_code == 200
        assert response.json() == []
