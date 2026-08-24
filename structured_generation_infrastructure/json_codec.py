"""Strict, public-safe JSON decoders for model-produced objects."""

from __future__ import annotations

from typing import cast

import orjson

from core_domain.structured_generation import (
    CriticFinding,
    CriticReport,
    CriticVerdict,
    SemanticSupport,
    StructuredGenerationError,
)
from core_domain.structured_output import (
    CandidateClaim,
    ClaimState,
    JsonValue,
    StructuredCandidate,
    StructuredCandidateBatch,
)

_DEFAULT_MAX_RESPONSE_CHARS = 128_000
_ROOT_BATCH_KEYS = frozenset(
    {"template_id", "template_version", "template_hash", "evidence_pack_id", "candidates"}
)
_CANDIDATE_KEYS = frozenset({"candidate_id", "payload", "claims"})
_CLAIM_KEYS = frozenset({"target", "state", "evidence_ids"})
_CRITIC_KEYS = frozenset({"verdict", "findings", "summary"})
_FINDING_KEYS = frozenset(
    {"candidate_id", "target", "support", "code", "evidence_ids", "explanation"}
)
_INVALID_LIMIT_MESSAGE = "max_response_chars must be a positive configured limit"


def _invalid_output() -> StructuredGenerationError:
    return StructuredGenerationError(
        "MODEL_OUTPUT_INVALID",
        "Model output is not a valid structured-generation object.",
    )


def _exact_object(value: object, required_keys: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != required_keys:
        raise TypeError
    return cast("dict[str, object]", value)


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError
    return cast("list[object]", value)


def _text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise TypeError
    return value


def _string_array(value: object, *, item_maximum: int = 256) -> tuple[str, ...]:
    values = _array(value)
    return tuple(_text(item, maximum=item_maximum) for item in values)


class _StrictJsonCodec:
    def __init__(self, *, max_response_chars: int = _DEFAULT_MAX_RESPONSE_CHARS) -> None:
        if (
            not isinstance(max_response_chars, int)
            or isinstance(max_response_chars, bool)
            or not 1 <= max_response_chars <= _DEFAULT_MAX_RESPONSE_CHARS
        ):
            raise ValueError(_INVALID_LIMIT_MESSAGE)
        self._max_response_chars = max_response_chars

    def _load(self, content: str) -> object:
        if not isinstance(content, str) or not content or len(content) > self._max_response_chars:
            raise TypeError
        return orjson.loads(content)


class StrictCandidateBatchCodec(_StrictJsonCodec):
    """Decode exactly one complete StructuredCandidateBatch JSON object."""

    def decode_batch(self, content: str) -> StructuredCandidateBatch:
        try:
            root = _exact_object(self._load(content), _ROOT_BATCH_KEYS)
            candidates = tuple(self._decode_candidate(value) for value in _array(root["candidates"]))
            return StructuredCandidateBatch(
                template_id=_text(root["template_id"], maximum=256),
                template_version=_text(root["template_version"], maximum=256),
                template_hash=_text(root["template_hash"], maximum=64),
                evidence_pack_id=_text(root["evidence_pack_id"], maximum=256),
                candidates=candidates,
            )
        except Exception:
            safe_error = _invalid_output()
        raise safe_error

    @staticmethod
    def _decode_candidate(value: object) -> StructuredCandidate:
        candidate = _exact_object(value, _CANDIDATE_KEYS)
        claims = tuple(
            StrictCandidateBatchCodec._decode_claim(claim) for claim in _array(candidate["claims"])
        )
        return StructuredCandidate(
            candidate_id=_text(candidate["candidate_id"], maximum=256),
            payload=cast("JsonValue", candidate["payload"]),
            claims=claims,
        )

    @staticmethod
    def _decode_claim(value: object) -> CandidateClaim:
        claim = _exact_object(value, _CLAIM_KEYS)
        return CandidateClaim(
            target=_text(claim["target"], maximum=2000),
            state=ClaimState(_text(claim["state"], maximum=64)),
            evidence_ids=_string_array(claim["evidence_ids"]),
        )


class StrictCriticReportCodec(_StrictJsonCodec):
    """Decode exactly one complete CriticReport JSON object."""

    def decode_critic(self, content: str) -> CriticReport:
        try:
            root = _exact_object(self._load(content), _CRITIC_KEYS)
            findings = tuple(self._decode_finding(value) for value in _array(root["findings"]))
            return CriticReport(
                verdict=CriticVerdict(_text(root["verdict"], maximum=64)),
                findings=findings,
                summary=_text(root["summary"], maximum=1000),
            )
        except Exception:
            safe_error = _invalid_output()
        raise safe_error

    @staticmethod
    def _decode_finding(value: object) -> CriticFinding:
        finding = _exact_object(value, _FINDING_KEYS)
        return CriticFinding(
            candidate_id=_text(finding["candidate_id"], maximum=256),
            target=_text(finding["target"], maximum=2000),
            support=SemanticSupport(_text(finding["support"], maximum=64)),
            code=_text(finding["code"], maximum=128),
            evidence_ids=_string_array(finding["evidence_ids"]),
            explanation=_text(finding["explanation"], maximum=500),
        )


__all__ = ["StrictCandidateBatchCodec", "StrictCriticReportCodec"]
