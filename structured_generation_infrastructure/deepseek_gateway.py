"""Minimal, fixed-endpoint DeepSeek V4 structured-generation gateway."""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Protocol, cast

import requests  # type: ignore[import-untyped]

from core_domain.structured_generation import (
    GenerationStage,
    StructuredGenerationError,
    StructuredModelRequest,
    StructuredModelResponse,
)

from .retry import retry_delay_seconds

_ENDPOINT = "https://api.deepseek.com/chat/completions"
_AUTH_STATUSES = frozenset({401, 403})
_INVALID_KEY_MESSAGE = "DEEPSEEK_API_KEY is required for structured generation."


class _Response(Protocol):
    status_code: int

    def json(self) -> object: ...

    def raise_for_status(self) -> None: ...


class _Session(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> _Response: ...


def _error(
    code: str,
    message: str,
    *,
    stage: GenerationStage,
    attempts: int,
    retryable: bool = False,
) -> StructuredGenerationError:
    return StructuredGenerationError(
        code,
        message,
        stage=stage,
        attempts=attempts,
        retryable=retryable,
    )


def _validate_request(request: StructuredModelRequest) -> None:
    valid_model = (
        request.stage is GenerationStage.GENERATE
        and request.model_id == "deepseek-v4-flash"
        and not request.thinking_enabled
        and request.reasoning_effort is None
    ) or (
        request.stage in {GenerationStage.CRITIC, GenerationStage.REPAIR}
        and request.model_id == "deepseek-v4-pro"
        and request.thinking_enabled
        and request.reasoning_effort == "high"
    )
    if not valid_model:
        raise _error(
            "MODEL_CONFIGURATION_INVALID",
            "The structured-generation model configuration is not approved.",
            stage=request.stage,
            attempts=0,
        )


def _request_json(request: StructuredModelRequest) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": request.model_id,
        "messages": [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": request.max_output_tokens,
        "thinking": {"type": "enabled" if request.thinking_enabled else "disabled"},
    }
    if request.thinking_enabled:
        payload["reasoning_effort"] = request.reasoning_effort
    return payload


def _is_token_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _load_payload(response: _Response, stage: GenerationStage, attempts: int) -> object:
    try:
        return response.json()
    except Exception:
        safe_error = _error(
            "MODEL_RESPONSE_INVALID",
            "The structured-generation provider response is invalid.",
            stage=stage,
            attempts=attempts,
        )
    raise safe_error


def _extract_response_fields(payload: object) -> tuple[str, str, str, int, int]:
    if not isinstance(payload, dict):
        raise TypeError
    provider_id = payload["id"]
    provider_object = payload["object"]
    created = payload["created"]
    model_id = payload["model"]
    choices = payload["choices"]
    usage = payload["usage"]
    if (
        not isinstance(provider_id, str)
        or not provider_id
        or provider_object != "chat.completion"
        or not _is_token_count(created)
        or not isinstance(model_id, str)
        or not isinstance(choices, list)
        or len(choices) != 1
        or not isinstance(usage, dict)
    ):
        raise TypeError
    choice = choices[0]
    if not isinstance(choice, dict) or not _is_token_count(choice.get("index")):
        raise TypeError
    message = choice["message"]
    finish_reason = choice["finish_reason"]
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise TypeError
    content = message["content"]
    prompt_tokens = usage["prompt_tokens"]
    completion_tokens = usage["completion_tokens"]
    total_tokens = usage["total_tokens"]
    if (
        not isinstance(content, str)
        or not isinstance(finish_reason, str)
        or not finish_reason
        or not _is_token_count(prompt_tokens)
        or not _is_token_count(completion_tokens)
        or not _is_token_count(total_tokens)
    ):
        raise TypeError
    return content, model_id, finish_reason, prompt_tokens, completion_tokens


def _parse_response(
    response: _Response,
    request: StructuredModelRequest,
    attempts: int,
) -> StructuredModelResponse:
    payload = _load_payload(response, request.stage, attempts)
    try:
        content, model_id, finish_reason, prompt_tokens, completion_tokens = _extract_response_fields(payload)
    except (KeyError, TypeError, ValueError):
        safe_error = _error(
            "MODEL_RESPONSE_INVALID",
            "The structured-generation provider response is invalid.",
            stage=request.stage,
            attempts=attempts,
        )
    else:
        if not content.strip():
            raise _error(
                "MODEL_EMPTY_RESPONSE",
                "The structured-generation provider returned empty content.",
                stage=request.stage,
                attempts=attempts,
            )
        if model_id != request.model_id:
            raise _error(
                "MODEL_ID_MISMATCH",
                "The structured-generation provider returned an unexpected model.",
                stage=request.stage,
                attempts=attempts,
            )
        return StructuredModelResponse(
            content=content,
            model_id=model_id,
            finish_reason=finish_reason,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            response_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            http_attempts=attempts,
        )
    raise safe_error


def _status_error(status_code: int, stage: GenerationStage, attempts: int) -> StructuredGenerationError:
    if status_code == 429:
        return _error(
            "MODEL_RATE_LIMITED",
            "The structured-generation provider rate limit was reached.",
            stage=stage,
            attempts=attempts,
            retryable=True,
        )
    if status_code in {500, 502, 503, 504}:
        return _error(
            "MODEL_UPSTREAM_UNAVAILABLE",
            "The structured-generation provider is temporarily unavailable.",
            stage=stage,
            attempts=attempts,
            retryable=True,
        )
    if status_code in _AUTH_STATUSES:
        return _error(
            "MODEL_AUTHENTICATION_FAILED",
            "The structured-generation provider rejected authentication.",
            stage=stage,
            attempts=attempts,
        )
    return _error(
        "MODEL_REQUEST_REJECTED",
        "The structured-generation provider rejected the request.",
        stage=stage,
        attempts=attempts,
    )


class DeepSeekStructuredGateway:
    """OpenAI-compatible DeepSeek adapter with no raw-response retention."""

    def __init__(
        self,
        *,
        api_key: str,
        session: object | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise StructuredGenerationError("MODEL_CONFIGURATION_INVALID", _INVALID_KEY_MESSAGE)
        self._api_key = api_key
        self._session = cast("_Session", session if session is not None else requests.Session())
        self._sleeper = sleeper

    def __repr__(self) -> str:
        return f"{type(self).__name__}(endpoint={_ENDPOINT!r})"

    def _attempt(
        self,
        request: StructuredModelRequest,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
        attempt: int,
    ) -> StructuredModelResponse | StructuredGenerationError:
        try:
            response = self._session.post(
                _ENDPOINT,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
        except requests.Timeout:
            return _error(
                "MODEL_TIMEOUT",
                "The structured-generation provider request timed out.",
                stage=request.stage,
                attempts=attempt,
                retryable=True,
            )
        except requests.ConnectionError:
            return _error(
                "MODEL_UPSTREAM_UNAVAILABLE",
                "The structured-generation provider is temporarily unavailable.",
                stage=request.stage,
                attempts=attempt,
                retryable=True,
            )

        status_code = response.status_code
        if not isinstance(status_code, int) or isinstance(status_code, bool):
            return _error(
                "MODEL_RESPONSE_INVALID",
                "The structured-generation provider response is invalid.",
                stage=request.stage,
                attempts=attempt,
            )
        if 200 <= status_code < 300:
            response.raise_for_status()
            return _parse_response(response, request, attempt)
        status_error = _status_error(status_code, request.stage, attempt)
        if not status_error.retryable:
            with suppress(requests.RequestException):
                response.raise_for_status()
        return status_error

    def complete(
        self,
        request: StructuredModelRequest,
        *,
        max_attempts: int,
        timeout_seconds: float,
    ) -> StructuredModelResponse:
        _validate_request(request)
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or not 1 <= max_attempts <= 6
            or not isinstance(timeout_seconds, int | float)
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
        ):
            raise _error(
                "MODEL_CONFIGURATION_INVALID",
                "The structured-generation call budget is invalid.",
                stage=request.stage,
                attempts=0,
            )

        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        payload = _request_json(request)
        for attempt in range(1, max_attempts + 1):
            outcome = self._attempt(
                request,
                headers=headers,
                payload=payload,
                timeout_seconds=float(timeout_seconds),
                attempt=attempt,
            )
            if isinstance(outcome, StructuredModelResponse):
                return outcome
            if not outcome.retryable or attempt == max_attempts:
                raise outcome
            if attempt < max_attempts:
                self._sleeper(retry_delay_seconds(attempt))
        raise AssertionError  # pragma: no cover


def build_deepseek_gateway_from_env(
    *,
    session: object | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> DeepSeekStructuredGateway:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    return DeepSeekStructuredGateway(api_key=api_key, session=session, sleeper=sleeper)


__all__ = ["DeepSeekStructuredGateway", "build_deepseek_gateway_from_env"]
