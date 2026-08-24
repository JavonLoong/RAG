from __future__ import annotations

from dataclasses import fields, replace
from typing import Any

import pytest
import requests

from core_domain.structured_generation import (
    GenerationStage,
    StructuredGenerationError,
    StructuredModelRequest,
    StructuredModelResponse,
)
from structured_generation_infrastructure.deepseek_gateway import (
    DeepSeekStructuredGateway,
    build_deepseek_gateway_from_env,
)
from structured_generation_infrastructure.retry import retry_delay_seconds

COMPLETE_FLASH_RESPONSE = {
    "id": "chatcmpl-flash",
    "object": "chat.completion",
    "created": 1_787_500_000,
    "model": "deepseek-v4-flash",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": '{"ok":true}',
                "reasoning_content": "private chain of thought",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
}
_HTTP_ERROR_MESSAGE = "provider returned an HTTP error"


class FakeResponse:
    def __init__(self, status_code: int, payload: object = None, *, json_error: Exception | None = None) -> None:
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error
        self.raise_calls = 0

    def json(self) -> object:
        if self.json_error is not None:
            raise self.json_error
        return self.payload

    def raise_for_status(self) -> None:
        self.raise_calls += 1
        if self.status_code >= 400:
            raise requests.HTTPError(_HTTP_ERROR_MESSAGE)


class FakeSession:
    def __init__(self, values: list[FakeResponse | BaseException]) -> None:
        self.values = values
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        value = self.values.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def _flash_request() -> StructuredModelRequest:
    return StructuredModelRequest(
        stage=GenerationStage.GENERATE,
        model_id="deepseek-v4-flash",
        system_prompt="Return JSON only.",
        user_prompt="Generate a json object.",
        max_output_tokens=8000,
        thinking_enabled=False,
        reasoning_effort=None,
    )


def _critic_request() -> StructuredModelRequest:
    return StructuredModelRequest(
        stage=GenerationStage.CRITIC,
        model_id="deepseek-v4-pro",
        system_prompt="Return JSON only.",
        user_prompt="Criticize this json object.",
        max_output_tokens=8000,
        thinking_enabled=True,
        reasoning_effort="high",
    )


def _pro_response() -> dict[str, object]:
    return {**COMPLETE_FLASH_RESPONSE, "id": "chatcmpl-pro", "model": "deepseek-v4-pro"}


def _gateway(
    session: FakeSession,
    *,
    api_key: str = "test-key",
    sleeps: list[float] | None = None,
) -> DeepSeekStructuredGateway:
    recorded = sleeps if sleeps is not None else []
    return DeepSeekStructuredGateway(api_key=api_key, session=session, sleeper=recorded.append)


def test_flash_request_uses_json_output_and_disables_thinking() -> None:
    session = FakeSession([FakeResponse(200, COMPLETE_FLASH_RESPONSE)])

    response = _gateway(session).complete(_flash_request(), max_attempts=2, timeout_seconds=30.0)

    sent = session.requests[0]
    assert sent["url"] == "https://api.deepseek.com/chat/completions"
    assert sent["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert sent["json"] == {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "Generate a json object."},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 8000,
        "thinking": {"type": "disabled"},
    }
    assert sent["timeout"] == 30.0
    assert response.model_id == "deepseek-v4-flash"
    assert response.http_attempts == 1


def test_pro_request_enables_high_thinking_without_sampling_parameters() -> None:
    session = FakeSession([FakeResponse(200, _pro_response())])

    _gateway(session).complete(_critic_request(), max_attempts=1, timeout_seconds=30.0)

    sent = session.requests[0]["json"]
    assert sent["thinking"] == {"type": "enabled"}
    assert sent["reasoning_effort"] == "high"
    assert not ({"temperature", "top_p", "presence_penalty", "frequency_penalty"} & set(sent))


def test_response_excludes_reasoning_and_raw_provider_data() -> None:
    response = _gateway(FakeSession([FakeResponse(200, COMPLETE_FLASH_RESPONSE)])).complete(
        _flash_request(), max_attempts=1, timeout_seconds=30.0
    )

    assert {item.name for item in fields(response)} == {
        "content",
        "model_id",
        "finish_reason",
        "input_tokens",
        "output_tokens",
        "response_hash",
        "http_attempts",
    }
    assert "reasoning" not in repr(response)
    assert "chatcmpl-flash" not in repr(response)


@pytest.mark.parametrize(
    "first",
    [
        requests.ConnectionError("private connection detail"),
        requests.Timeout("private timeout detail"),
        FakeResponse(429, {"error": {"message": "private rate detail"}}),
        FakeResponse(500, {}),
        FakeResponse(502, {}),
        FakeResponse(503, {}),
        FakeResponse(504, {}),
    ],
)
def test_transient_failures_retry_with_deterministic_backoff(first: object) -> None:
    sleeps: list[float] = []
    session = FakeSession([first, FakeResponse(200, COMPLETE_FLASH_RESPONSE)])  # type: ignore[list-item]

    response = _gateway(session, sleeps=sleeps).complete(
        _flash_request(), max_attempts=2, timeout_seconds=30.0
    )

    assert response.http_attempts == 2
    assert len(session.requests) == 2
    assert sleeps == [1.0]


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "MODEL_REQUEST_REJECTED"),
        (401, "MODEL_AUTHENTICATION_FAILED"),
        (403, "MODEL_AUTHENTICATION_FAILED"),
        (404, "MODEL_REQUEST_REJECTED"),
    ],
)
def test_non_retryable_http_failures_stop_after_one_attempt(status: int, code: str) -> None:
    response = FakeResponse(status, {"error": {"message": "sk-provider-body"}})
    session = FakeSession([response])

    with pytest.raises(StructuredGenerationError) as caught:
        _gateway(session, api_key="sk-private").complete(
            _flash_request(), max_attempts=3, timeout_seconds=30.0
        )

    assert (caught.value.code, caught.value.attempts, caught.value.retryable) == (code, 1, False)
    assert len(session.requests) == 1
    assert response.raise_calls == 1
    assert "sk-private" not in str(caught.value)
    assert "sk-provider-body" not in str(caught.value)


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (FakeResponse(200, json_error=ValueError("private json body")), "MODEL_RESPONSE_INVALID"),
        (FakeResponse(200, {**COMPLETE_FLASH_RESPONSE, "choices": []}), "MODEL_RESPONSE_INVALID"),
        (
            FakeResponse(
                200,
                {
                    **COMPLETE_FLASH_RESPONSE,
                    "choices": [{"index": 0, "message": {}, "finish_reason": "stop"}],
                },
            ),
            "MODEL_RESPONSE_INVALID",
        ),
        (FakeResponse(200, {**COMPLETE_FLASH_RESPONSE, "usage": {}}), "MODEL_RESPONSE_INVALID"),
        (
            FakeResponse(
                200,
                {
                    **COMPLETE_FLASH_RESPONSE,
                    "usage": {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
                },
            ),
            "MODEL_RESPONSE_INVALID",
        ),
        (
            FakeResponse(
                200,
                {
                    **COMPLETE_FLASH_RESPONSE,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "   "},
                            "finish_reason": "stop",
                        }
                    ],
                },
            ),
            "MODEL_EMPTY_RESPONSE",
        ),
        (FakeResponse(200, {**COMPLETE_FLASH_RESPONSE, "model": "deepseek-v4-pro"}), "MODEL_ID_MISMATCH"),
    ],
)
def test_invalid_provider_responses_never_retry(response: FakeResponse, code: str) -> None:
    session = FakeSession([response])

    with pytest.raises(StructuredGenerationError) as caught:
        _gateway(session).complete(_flash_request(), max_attempts=3, timeout_seconds=30.0)

    assert (caught.value.code, caught.value.attempts, len(session.requests)) == (code, 1, 1)


def test_retry_budget_is_exact_and_never_sleeps_after_final_attempt() -> None:
    sleeps: list[float] = []
    session = FakeSession([FakeResponse(503, {}), FakeResponse(503, {}), FakeResponse(503, {})])

    with pytest.raises(StructuredGenerationError) as caught:
        _gateway(session, sleeps=sleeps).complete(_flash_request(), max_attempts=3, timeout_seconds=30.0)

    assert (caught.value.code, caught.value.attempts, caught.value.retryable) == (
        "MODEL_UPSTREAM_UNAVAILABLE",
        3,
        True,
    )
    assert sleeps == [1.0, 2.0]
    assert [retry_delay_seconds(attempt) for attempt in (1, 2, 3, 4)] == [1.0, 2.0, 4.0, 4.0]


def test_wrong_stage_model_alias_is_rejected_before_http() -> None:
    session = FakeSession([])

    with pytest.raises(StructuredGenerationError) as caught:
        _gateway(session).complete(
            replace(_flash_request(), model_id="deepseek-v4-pro"),
            max_attempts=1,
            timeout_seconds=30.0,
        )

    assert caught.value.code == "MODEL_CONFIGURATION_INVALID"
    assert caught.value.attempts == 0
    assert session.requests == []


def test_environment_builder_requires_only_key_and_ignores_base_url_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(StructuredGenerationError) as caught:
        build_deepseek_gateway_from_env(session=FakeSession([]))
    assert caught.value.code == "MODEL_CONFIGURATION_INVALID"

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-environment-private")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://attacker.invalid")
    session = FakeSession([FakeResponse(200, COMPLETE_FLASH_RESPONSE)])
    gateway = build_deepseek_gateway_from_env(session=session, sleeper=lambda _: None)
    gateway.complete(_flash_request(), max_attempts=1, timeout_seconds=30.0)

    assert session.requests[0]["url"] == "https://api.deepseek.com/chat/completions"
    assert "sk-environment-private" not in repr(gateway)
    assert "attacker.invalid" not in repr(gateway)


def test_success_response_hashes_content_and_records_usage() -> None:
    response = _gateway(FakeSession([FakeResponse(200, COMPLETE_FLASH_RESPONSE)])).complete(
        _flash_request(), max_attempts=1, timeout_seconds=30.0
    )

    assert isinstance(response, StructuredModelResponse)
    assert response.input_tokens == 20
    assert response.output_tokens == 5
    assert response.response_hash == "4062edaf750fb8074e7e83e0c9028c94e32468a8b6f1614774328ef045150f93"
