"""Les trois fournisseurs IA derrière `AIProvider.extract` (mission `v3-ia-providers` §3, §6) —
réponses enregistrées via `httpx.MockTransport` (même méthode que `tests/test_exchange_rates.py`
pour `EcbClient`), aucun appel réseau réel : sortie structurée validée + usage, une nouvelle
tentative guidée sur JSON invalide, erreurs normalisées (clé invalide, quota, surcharge,
contenu refusé).

Avant ce lot, `pbm_api.ai.base`/`anthropic_provider`/`openai_provider`/`gemini_provider`/
`factory` n'existaient pas : ce module échoue à la collection (`ModuleNotFoundError`) et passe
une fois ces fichiers ajoutés. La preuve ciblée sur le comportement de nouvelle tentative
(`test_extract_retries_once_then_succeeds_on_invalid_json`) est dans le compte rendu : la
désactiver dans `pbm_api/ai/base.py` fait échouer ce test précis (et lui seul) sans toucher au
reste de la suite.

Pas de test d'accès croisé (§6) : ce module ne reçoit qu'une clé déjà résolue pour
l'utilisateur courant (`user_id` n'existe pas à ce niveau) — l'isolation par utilisateur est
couverte en amont dans `tests/test_ai_keys.py` (coffre de clés, lot `v1-byok`).
"""

import json

import httpx
import pytest
from pydantic import BaseModel

from pbm_api.ai.anthropic_provider import AnthropicProvider
from pbm_api.ai.base import ImageInput
from pbm_api.ai.errors import (
    AIProviderError,
    ContentRefusedError,
    InvalidApiKeyError,
    InvalidExtractionResponseError,
    ProviderOverloadedError,
    QuotaExceededError,
)
from pbm_api.ai.factory import create_provider
from pbm_api.ai.gemini_provider import GeminiProvider
from pbm_api.ai.openai_provider import OpenAiProvider
from pbm_api.ai.simulated_provider import SimulatedProvider, UnsimulatedSchemaError
from pbm_api.identification.schemas import CardExtraction
from pbm_api.models import AiProvider
from pbm_api.seed import DEMO_CARDS

_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8ffff3f0005fe02fea739666500000000"
    "49454e44ae426082"
)


class _CardExtraction(BaseModel):
    name: str
    number: str


def _image() -> ImageInput:
    return ImageInput(data=_ONE_PIXEL_PNG, media_type="image/png")


class _RecordingTransport:
    """Rejoue `responses` dans l'ordre des appels — la dernière est répétée si l'appelant en
    fait plus que prévu, pour ne pas planter sur un appel de trop plutôt que masquer un bogue
    de boucle infinie (assert explicite sur `len(requests)` dans les tests qui comptent)."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self._responses) - 1)
        return self._responses[index]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


def _json_response(status_code: int, body: dict) -> httpx.Response:
    return httpx.Response(status_code, json=body)


# --- Anthropic -----------------------------------------------------------------------------


def _anthropic_success(
    text: str, *, input_tokens: int = 120, output_tokens: int = 40
) -> httpx.Response:
    return _json_response(
        200,
        {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        },
    )


async def test_anthropic_extract_returns_validated_object_and_usage() -> None:
    valid_json = json.dumps({"name": "Dracaufeu", "number": "006/165"})
    transport = _RecordingTransport([_anthropic_success(valid_json)])

    provider = AnthropicProvider("sk-ant-test", http_client=transport.client())
    result, usage = await provider.extract([_image()], _CardExtraction, "Extrais la carte.")

    assert result == _CardExtraction(name="Dracaufeu", number="006/165")
    assert usage.provider == AiProvider.anthropic
    assert usage.model == AnthropicProvider.DEFAULT_MODEL
    assert usage.input_tokens == 120
    assert usage.output_tokens == 40
    assert len(transport.requests) == 1


async def test_anthropic_extract_sends_the_requested_model_and_schema() -> None:
    valid_json = json.dumps({"name": "Dracaufeu", "number": "006/165"})
    transport = _RecordingTransport([_anthropic_success(valid_json)])
    provider = AnthropicProvider("sk-ant-test", http_client=transport.client())

    await provider.extract(
        [_image()], _CardExtraction, "Extrais la carte.", model="claude-haiku-4-5"
    )

    sent = json.loads(transport.requests[0].content)
    assert sent["model"] == "claude-haiku-4-5"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert sent["output_config"]["format"]["schema"]["required"] == ["name", "number"]
    assert transport.requests[0].headers["x-api-key"] == "sk-ant-test"


async def test_anthropic_extract_retries_once_then_succeeds_on_invalid_json() -> None:
    invalid_json = json.dumps({"number": "006/165"})  # "name" manquant
    valid_json = json.dumps({"name": "Dracaufeu", "number": "006/165"})
    transport = _RecordingTransport(
        [
            _anthropic_success(invalid_json, input_tokens=100, output_tokens=20),
            _anthropic_success(valid_json, input_tokens=110, output_tokens=25),
        ]
    )
    provider = AnthropicProvider("sk-ant-test", http_client=transport.client())

    result, usage = await provider.extract([_image()], _CardExtraction, "Extrais la carte.")

    assert result == _CardExtraction(name="Dracaufeu", number="006/165")
    assert len(transport.requests) == 2
    # Le message de la seconde requête explique l'échec de validation au modèle.
    second_body = json.loads(transport.requests[1].content)
    assert "schéma" in second_body["messages"][0]["content"][-1]["text"]
    # L'usage cumule les deux appels.
    assert usage.input_tokens == 210
    assert usage.output_tokens == 45


async def test_anthropic_extract_raises_after_two_invalid_json_responses() -> None:
    invalid_json = json.dumps({"number": "006/165"})
    transport = _RecordingTransport(
        [_anthropic_success(invalid_json), _anthropic_success(invalid_json)]
    )
    provider = AnthropicProvider("sk-ant-test", http_client=transport.client())

    with pytest.raises(InvalidExtractionResponseError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")
    assert len(transport.requests) == 2


async def test_anthropic_extract_maps_401_to_invalid_api_key_error() -> None:
    body = {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}}
    transport = _RecordingTransport([_json_response(401, body)])
    provider = AnthropicProvider("sk-ant-bad", http_client=transport.client())

    with pytest.raises(InvalidApiKeyError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


async def test_anthropic_extract_maps_429_to_quota_exceeded_error() -> None:
    body = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
    transport = _RecordingTransport([_json_response(429, body)])
    provider = AnthropicProvider("sk-ant-test", http_client=transport.client())

    with pytest.raises(QuotaExceededError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


async def test_anthropic_extract_maps_529_to_provider_overloaded_error() -> None:
    body = {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
    transport = _RecordingTransport([_json_response(529, body)])
    provider = AnthropicProvider("sk-ant-test", http_client=transport.client())

    with pytest.raises(ProviderOverloadedError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


async def test_anthropic_extract_maps_refusal_stop_reason_to_content_refused_error() -> None:
    transport = _RecordingTransport(
        [
            _json_response(
                200,
                {
                    "stop_reason": "refusal",
                    "stop_details": {"type": "refusal", "category": "cyber", "explanation": "non"},
                    "content": [],
                    "usage": {"input_tokens": 10, "output_tokens": 0},
                },
            )
        ]
    )
    provider = AnthropicProvider("sk-ant-test", http_client=transport.client())

    with pytest.raises(ContentRefusedError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


# --- OpenAI --------------------------------------------------------------------------------


def _openai_success(
    text: str, *, prompt_tokens: int = 100, completion_tokens: int = 30
) -> httpx.Response:
    return _json_response(
        200,
        {
            "choices": [{"finish_reason": "stop", "message": {"content": text}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        },
    )


async def test_openai_extract_returns_validated_object_and_usage() -> None:
    valid_json = json.dumps({"name": "Dracaufeu", "number": "006/165"})
    transport = _RecordingTransport([_openai_success(valid_json)])
    provider = OpenAiProvider("sk-test", http_client=transport.client())

    result, usage = await provider.extract([_image()], _CardExtraction, "Extrais la carte.")

    assert result == _CardExtraction(name="Dracaufeu", number="006/165")
    assert usage.input_tokens == 100
    assert usage.output_tokens == 30
    assert transport.requests[0].headers["authorization"] == "Bearer sk-test"


async def test_openai_extract_uses_strict_json_schema_response_format() -> None:
    valid_json = json.dumps({"name": "Dracaufeu", "number": "006/165"})
    transport = _RecordingTransport([_openai_success(valid_json)])
    provider = OpenAiProvider("sk-test", http_client=transport.client())

    await provider.extract([_image()], _CardExtraction, "Extrais la carte.")

    sent = json.loads(transport.requests[0].content)
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["response_format"]["json_schema"]["schema"]["additionalProperties"] is False


async def test_openai_extract_maps_content_filter_to_content_refused_error() -> None:
    transport = _RecordingTransport(
        [
            _json_response(
                200,
                {
                    "choices": [{"finish_reason": "content_filter", "message": {"content": None}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 0},
                },
            )
        ]
    )
    provider = OpenAiProvider("sk-test", http_client=transport.client())

    with pytest.raises(ContentRefusedError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


async def test_openai_extract_maps_401_to_invalid_api_key_error() -> None:
    body = {"error": {"message": "Incorrect API key", "code": "invalid_api_key"}}
    transport = _RecordingTransport([_json_response(401, body)])
    provider = OpenAiProvider("sk-bad", http_client=transport.client())

    with pytest.raises(InvalidApiKeyError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


async def test_openai_extract_maps_429_to_quota_exceeded_error() -> None:
    body = {"error": {"message": "Rate limit reached", "code": "rate_limit_exceeded"}}
    transport = _RecordingTransport([_json_response(429, body)])
    provider = OpenAiProvider("sk-test", http_client=transport.client())

    with pytest.raises(QuotaExceededError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


async def test_openai_extract_maps_503_to_provider_overloaded_error() -> None:
    body = {"error": {"message": "server overloaded"}}
    transport = _RecordingTransport([_json_response(503, body)])
    provider = OpenAiProvider("sk-test", http_client=transport.client())

    with pytest.raises(ProviderOverloadedError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


# --- Gemini --------------------------------------------------------------------------------


def _gemini_success(
    text: str, *, prompt_tokens: int = 80, candidates_tokens: int = 25
) -> httpx.Response:
    return _json_response(
        200,
        {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}],
            "usageMetadata": {
                "promptTokenCount": prompt_tokens,
                "candidatesTokenCount": candidates_tokens,
            },
        },
    )


async def test_gemini_extract_returns_validated_object_and_usage() -> None:
    valid_json = json.dumps({"name": "Dracaufeu", "number": "006/165"})
    transport = _RecordingTransport([_gemini_success(valid_json)])
    provider = GeminiProvider("AIza-test", http_client=transport.client())

    result, usage = await provider.extract([_image()], _CardExtraction, "Extrais la carte.")

    assert result == _CardExtraction(name="Dracaufeu", number="006/165")
    assert usage.input_tokens == 80
    assert usage.output_tokens == 25
    assert transport.requests[0].headers["x-goog-api-key"] == "AIza-test"
    expected_suffix = f"{GeminiProvider.DEFAULT_MODEL}:generateContent"
    assert str(transport.requests[0].url).endswith(expected_suffix)


async def test_gemini_extract_uses_response_schema_without_ref() -> None:
    valid_json = json.dumps({"name": "Dracaufeu", "number": "006/165"})
    transport = _RecordingTransport([_gemini_success(valid_json)])
    provider = GeminiProvider("AIza-test", http_client=transport.client())

    await provider.extract([_image()], _CardExtraction, "Extrais la carte.")

    sent = json.loads(transport.requests[0].content)
    assert sent["generationConfig"]["responseMimeType"] == "application/json"
    assert "$ref" not in json.dumps(sent["generationConfig"]["responseSchema"])


async def test_gemini_extract_maps_safety_finish_reason_to_content_refused_error() -> None:
    body = {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]}
    transport = _RecordingTransport([_json_response(200, body)])
    provider = GeminiProvider("AIza-test", http_client=transport.client())

    with pytest.raises(ContentRefusedError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


async def test_gemini_extract_maps_api_key_invalid_to_invalid_api_key_error() -> None:
    body = {
        "error": {
            "code": 400,
            "status": "INVALID_ARGUMENT",
            "message": "API key not valid. Please pass a valid API key.",
        }
    }
    transport = _RecordingTransport([_json_response(400, body)])
    provider = GeminiProvider("AIza-bad", http_client=transport.client())

    with pytest.raises(InvalidApiKeyError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


async def test_gemini_extract_does_not_confuse_a_malformed_request_with_an_invalid_key() -> None:
    """Un 400 Gemini ne signifie pas systématiquement une clé invalide (risque nommé par la
    mission, §4) : `INVALID_ARGUMENT` sans le message de clé reste une erreur générique, pas
    `InvalidApiKeyError`."""
    body = {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "bad schema"}}
    transport = _RecordingTransport([_json_response(400, body)])
    provider = GeminiProvider("AIza-test", http_client=transport.client())

    with pytest.raises(AIProviderError) as exc_info:
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")
    assert not isinstance(exc_info.value, InvalidApiKeyError)


async def test_gemini_extract_maps_resource_exhausted_to_quota_exceeded_error() -> None:
    body = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota"}}
    transport = _RecordingTransport([_json_response(429, body)])
    provider = GeminiProvider("AIza-test", http_client=transport.client())

    with pytest.raises(QuotaExceededError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


async def test_gemini_extract_maps_unavailable_to_provider_overloaded_error() -> None:
    body = {"error": {"code": 503, "status": "UNAVAILABLE", "message": "overloaded"}}
    transport = _RecordingTransport([_json_response(503, body)])
    provider = GeminiProvider("AIza-test", http_client=transport.client())

    with pytest.raises(ProviderOverloadedError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")


# --- Fabrique --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider_enum", "expected_class"),
    [
        (AiProvider.anthropic, AnthropicProvider),
        (AiProvider.openai, OpenAiProvider),
        (AiProvider.gemini, GeminiProvider),
    ],
)
def test_create_provider_returns_the_matching_implementation(provider_enum, expected_class) -> None:
    provider = create_provider(provider_enum, "some-key")
    assert isinstance(provider, expected_class)


# --- Fournisseur simulé (lot v5-e2e) ----------------------------------------------------------
# Drapeau `AI_SIMULATED_PROVIDER`, faux par défaut (voir `pbm_api.config`) : bascule la fabrique
# sur `SimulatedProvider` quel que soit le fournisseur demandé, pour que l'e2e Playwright fasse
# tourner le vrai pipeline de reconnaissance sans clé IA réelle (aucune sur chimera). Preuve
# ciblée : sans la branche ajoutée dans `create_provider`, ce test échoue (renvoie
# `AnthropicProvider` au lieu de `SimulatedProvider`).


@pytest.fixture
def simulated_provider_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pbm_api.ai.factory.settings.ai_simulated_provider", True)


def test_create_provider_returns_simulated_when_flag_enabled(simulated_provider_enabled) -> None:
    provider = create_provider(AiProvider.gemini, "some-key")

    assert isinstance(provider, SimulatedProvider)
    assert provider.PROVIDER == AiProvider.gemini


async def test_simulated_provider_cycles_through_demo_cards(simulated_provider_enabled) -> None:
    provider = create_provider(AiProvider.anthropic, "some-key")

    first, usage = await provider.extract([_image()], CardExtraction, "Extrais la carte.")
    second, _ = await provider.extract([_image()], CardExtraction, "Extrais la carte.")

    assert first.set_code == DEMO_CARDS[0]["set_code"]
    assert first.number == DEMO_CARDS[0]["number"]
    assert second.set_code == DEMO_CARDS[1]["set_code"]
    assert second.number == DEMO_CARDS[1]["number"]
    assert usage.provider == AiProvider.anthropic
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0


async def test_simulated_provider_rejects_an_unsimulated_schema(simulated_provider_enabled) -> None:
    provider = create_provider(AiProvider.anthropic, "some-key")

    with pytest.raises(UnsimulatedSchemaError):
        await provider.extract([_image()], _CardExtraction, "Extrais la carte.")
