from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4.1-mini"


class LLMConfigurationError(RuntimeError):
    """Raised when an LLM adapter cannot be configured safely."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] | None = None


class BaseLLMClient(Protocol):
    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> LLMResponse:
        """Return a chat completion for normalized messages."""


class OpenAICompatibleLLMClient:
    """Tiny OpenAI-compatible chat completion adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        model: str = DEFAULT_MODEL,
        session: Any | None = None,
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("OPENAI_API_KEY is required for remote LLM calls.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.session = session or requests.Session()
        self.timeout = timeout

    def chat(self, messages: list[ChatMessage], **kwargs: Any) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [message.to_dict() for message in messages],
        }
        for key in ("temperature", "max_tokens", "top_p"):
            if key in kwargs and kwargs[key] is not None:
                payload[key] = kwargs[key]

        response = self.session.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        raw = response.json()
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return LLMResponse(
            content=str(message.get("content") or ""),
            model=raw.get("model") or self.model,
            finish_reason=choice.get("finish_reason"),
            usage=raw.get("usage") or {},
            raw=raw,
        )

    def generate(self, prompt: str, **kwargs: Any) -> str:
        response = self.chat([ChatMessage(role="user", content=prompt)], **kwargs)
        return response.content

    def complete(self, prompt: str, **kwargs: Any) -> str:
        return self.generate(prompt, **kwargs)


def build_llm_from_env(
    *,
    default_model: str = DEFAULT_MODEL,
    api_key_env: str = "OPENAI_API_KEY",
    timeout: float = 60.0,
) -> OpenAICompatibleLLMClient:
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise LLMConfigurationError(f"{api_key_env} is required for remote LLM calls.")
    return OpenAICompatibleLLMClient(
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip() or DEFAULT_OPENAI_BASE_URL,
        model=os.environ.get("OPENAI_MODEL", default_model).strip() or default_model,
        timeout=timeout,
    )
