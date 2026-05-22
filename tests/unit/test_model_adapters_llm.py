from __future__ import annotations

from typing import Any

import pytest

from model_adapters import (
    BaseLLMClient,
    ChatMessage,
    DEFAULT_OPENAI_BASE_URL,
    LLMConfigurationError,
    LLMResponse,
    OpenAICompatibleLLMClient,
    build_llm_from_env,
)


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class RecordingSession:
    def __init__(self, response: FakeHTTPResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeHTTPResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def test_build_llm_from_env_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        build_llm_from_env()


def test_build_llm_from_env_uses_openai_compatible_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://llm.example.test/custom/v1/")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")

    client = build_llm_from_env()

    assert isinstance(client, OpenAICompatibleLLMClient)
    assert client.api_key == "sk-env"
    assert client.base_url == "https://llm.example.test/custom/v1"
    assert client.model == "env-model"


def test_build_llm_from_env_defaults_base_url_and_allows_configured_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    client = build_llm_from_env(default_model="fallback-model")

    assert client.base_url == DEFAULT_OPENAI_BASE_URL
    assert client.model == "fallback-model"


def test_openai_compatible_client_posts_chat_completion_payload() -> None:
    session = RecordingSession(
        FakeHTTPResponse(
            {
                "id": "chatcmpl-test",
                "model": "provider-model",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "connected"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
            }
        )
    )
    client = OpenAICompatibleLLMClient(
        api_key="sk-test",
        base_url="https://llm.example.test/v1",
        model="configured-model",
        session=session,
        timeout=7.5,
    )

    response = client.chat(
        [
            ChatMessage(role="system", content="Answer briefly."),
            ChatMessage(role="user", content="Ping"),
        ],
        temperature=0.2,
        max_tokens=16,
    )

    assert response == LLMResponse(
        content="connected",
        model="provider-model",
        finish_reason="stop",
        usage={"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
        raw=session.response._payload,
    )
    assert session.calls == [
        {
            "url": "https://llm.example.test/v1/chat/completions",
            "headers": {
                "Authorization": "Bearer sk-test",
                "Content-Type": "application/json",
            },
            "json": {
                "model": "configured-model",
                "messages": [
                    {"role": "system", "content": "Answer briefly."},
                    {"role": "user", "content": "Ping"},
                ],
                "temperature": 0.2,
                "max_tokens": 16,
            },
            "timeout": 7.5,
        }
    ]


def test_tests_can_explicitly_inject_deterministic_llm_client() -> None:
    class DeterministicLLMClient(BaseLLMClient):
        def chat(self, messages: list[ChatMessage], **_: Any) -> LLMResponse:
            return LLMResponse(
                content=f"fake reply to {messages[-1].content}",
                model="deterministic-test-client",
                raw={"source": "test"},
            )

    client: BaseLLMClient = DeterministicLLMClient()

    response = client.chat([ChatMessage(role="user", content="unit test")])

    assert response.content == "fake reply to unit test"
    assert response.model == "deterministic-test-client"
