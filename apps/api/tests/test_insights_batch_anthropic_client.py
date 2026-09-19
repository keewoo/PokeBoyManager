"""Client de la Message Batches API (mission `v4-insights-batch`) —
`pbm_api.insights_batch.anthropic_batches`, réponses enregistrées (`httpx.MockTransport`,
même méthode que `tests/test_ai_providers.py`), aucun appel réseau réel.

Avant ce lot, ce module n'existait pas : la suite échoue entièrement à la collection
(`ModuleNotFoundError`) et passe une fois le fichier ajouté.
`test_iter_results_matches_results_by_custom_id_not_by_order` est la preuve ciblée du risque
documenté par Anthropic (« results can be returned in any order ») : sans se fier uniquement à
`custom_id`, un rapprochement par position associerait le mauvais résultat à la mauvaise carte.
"""

import json

import httpx

from pbm_api.insights_batch.anthropic_batches import (
    AnthropicBatchClient,
    BatchApiError,
    build_batch_request,
)


def _client(handler) -> AnthropicBatchClient:
    transport = httpx.MockTransport(handler)
    return AnthropicBatchClient(
        "sk-ant-platform-test", http_client=httpx.AsyncClient(transport=transport)
    )


def test_build_batch_request_shape() -> None:
    request = build_batch_request(
        custom_id="11111111-1111-1111-1111-111111111111",
        model="claude-haiku-4-5",
        max_tokens=2048,
        prompt="Extrais la carte.",
        json_schema={"type": "object"},
    )
    assert request["custom_id"] == "11111111-1111-1111-1111-111111111111"
    assert request["params"]["model"] == "claude-haiku-4-5"
    assert request["params"]["max_tokens"] == 2048
    assert request["params"]["messages"] == [{"role": "user", "content": "Extrais la carte."}]
    assert request["params"]["output_config"]["format"]["type"] == "json_schema"


async def test_create_batch_returns_status_and_sends_requests() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["headers"] = request.headers
        return httpx.Response(
            200,
            json={
                "id": "msgbatch_01",
                "type": "message_batch",
                "processing_status": "in_progress",
                "request_counts": {"processing": 2, "succeeded": 0},
                "results_url": None,
            },
        )

    client = _client(handler)
    requests = [
        build_batch_request(custom_id="c1", model="m", max_tokens=10, prompt="p", json_schema={})
    ]
    status = await client.create_batch(requests)

    assert status.batch_id == "msgbatch_01"
    assert status.processing_status == "in_progress"
    assert status.results_url is None
    assert captured["body"]["requests"] == requests
    assert captured["headers"]["x-api-key"] == "sk-ant-platform-test"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"


async def test_create_batch_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"type": "invalid_request_error"}})

    client = _client(handler)
    try:
        await client.create_batch([])
        raise AssertionError("devait lever BatchApiError")
    except BatchApiError:
        pass


async def test_get_batch_reports_ended_with_results_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/msgbatch_01")
        return httpx.Response(
            200,
            json={
                "id": "msgbatch_01",
                "type": "message_batch",
                "processing_status": "ended",
                "request_counts": {"processing": 0, "succeeded": 2},
                "results_url": "https://api.anthropic.com/v1/messages/batches/msgbatch_01/results",
            },
        )

    client = _client(handler)
    status = await client.get_batch("msgbatch_01")

    assert status.processing_status == "ended"
    assert status.results_url is not None


async def test_iter_results_matches_results_by_custom_id_not_by_order() -> None:
    """Les résultats reviennent dans un ordre non garanti (documenté par Anthropic) : seul
    `custom_id` doit servir à retrouver la bonne carte, jamais la position dans le flux."""
    jsonl = "\n".join(
        [
            json.dumps(
                {
                    "custom_id": "second",
                    "result": {
                        "type": "succeeded",
                        "message": {
                            "content": [{"type": "text", "text": "B"}],
                            "usage": {"input_tokens": 5, "output_tokens": 2},
                        },
                    },
                }
            ),
            json.dumps(
                {
                    "custom_id": "first",
                    "result": {
                        "type": "succeeded",
                        "message": {
                            "content": [{"type": "text", "text": "A"}],
                            "usage": {"input_tokens": 7, "output_tokens": 3},
                        },
                    },
                }
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=jsonl.encode())

    client = _client(handler)
    results = await client.iter_results("https://api.anthropic.com/v1/messages/batches/x/results")

    by_id = {item.custom_id: item for item in results}
    assert by_id["first"].text == "A"
    assert by_id["first"].input_tokens == 7
    assert by_id["second"].text == "B"
    assert by_id["second"].input_tokens == 5


async def test_iter_results_reports_errored_requests_without_text() -> None:
    jsonl = json.dumps(
        {
            "custom_id": "failed-one",
            "result": {"type": "errored", "error": {"type": "invalid_request_error"}},
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=jsonl.encode())

    client = _client(handler)
    results = await client.iter_results("https://api.anthropic.com/v1/messages/batches/x/results")

    assert results[0].result_type == "errored"
    assert results[0].text is None
    assert results[0].error is not None
