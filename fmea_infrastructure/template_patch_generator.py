"""Provider-neutral, bounded model suggestions for imported template mappings."""

# TRY003 is consistent with the stable ReviewError boundary used by FMEA.
# ruff: noqa: TRY003

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from typing import Protocol

from core_domain.fmea.template_migration import TemplateDraft, TemplatePatchCandidate, TemplatePatchStatus
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.ports import TemplatePatchRequest
from fmea_application.review_errors import ReviewError


class TemplatePatchModelGateway(Protocol):
    """A provider-neutral model boundary; implementations may be local or remote."""

    def generate(self, request: Mapping[str, object]) -> object: ...


_PATH = re.compile(r"^/(?:fields|mappings)/[a-z][a-z0-9_.-]{0,127}$")
_FORBIDDEN_TEXT = re.compile(
    r"(?i)(?:https?://|file://|\\\\|(?:[a-z]:[\\/])|\.\.|\b(?:exec|eval|import|lambda|select|insert|update|delete|drop|curl|wget|powershell|bash)\b|(?:api[_ -]?key|password|secret|authorization|token))"
)
_SHA = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_MAX_DIFF = 64
_MAX_VALUE_DEPTH = 4
_MAX_VALUE_NODES = 512


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("created_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("created_at must be an ISO-8601 UTC timestamp")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _invalid(message: str) -> ReviewError:
    return ReviewError("FMEA_MODEL_SUGGESTION_INVALID", message)


def _safe_hash(value: str, field_name: str) -> str:
    if _SHA.fullmatch(value) is None:
        raise _invalid(f"{field_name} provenance is invalid")
    return value


def _validate_value(  # noqa: C901
    value: object, *, depth: int = 0, nodes: list[int] | None = None
) -> object:
    budget = [0] if nodes is None else nodes
    budget[0] += 1
    if budget[0] > _MAX_VALUE_NODES or depth > _MAX_VALUE_DEPTH:
        raise _invalid("patch value exceeds the bounded declarative limit")
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise _invalid("patch values must be finite")
        return value
    if isinstance(value, str):
        if len(value) > 4096 or _FORBIDDEN_TEXT.search(value):
            raise _invalid("patch value contains unsupported executable or private content")
        return value
    if isinstance(value, Mapping):
        if len(value) > 32:
            raise _invalid("patch value mapping is too large")
        result: dict[str, object] = {}
        for key, child in sorted(value.items(), key=lambda pair: str(pair[0])):
            if not isinstance(key, str) or not key.strip() or _FORBIDDEN_TEXT.search(key):
                raise _invalid("patch value contains an unsupported key")
            result[key] = _validate_value(child, depth=depth + 1, nodes=budget)
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if len(value) > 64:
            raise _invalid("patch value sequence is too large")
        return [_validate_value(child, depth=depth + 1, nodes=budget) for child in value]
    raise _invalid("patch values must be declarative JSON values")


def _validate_diff(value: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise _invalid("patch diff must be a bounded array")
    if len(value) > _MAX_DIFF:
        raise _invalid("patch diff exceeds the bounded limit")
    paths: set[str] = set()
    normalized: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) - {"op", "path", "value"}:
            raise _invalid("patch diff contains unknown or missing fields")
        operation = item.get("op")
        path = item.get("path")
        if operation not in {"add", "replace", "remove"} or not isinstance(path, str) or _PATH.fullmatch(path) is None:
            raise _invalid("patch diff is not an allowlisted declarative mapping")
        if path in paths:
            raise _invalid("patch diff paths must be unique")
        if operation != "remove" and "value" not in item:
            raise _invalid("patch add and replace operations require a value")
        paths.add(path)
        entry: dict[str, object] = {"op": operation, "path": path}
        if operation != "remove":
            entry["value"] = _validate_value(item["value"])
        normalized.append(entry)
    return tuple(normalized)


def _normalize_evidence_ids(value: object) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise _invalid("patch evidence IDs must be an array")
    if len(value) > 128 or any(not isinstance(item, str) or not item.strip() for item in value):
        raise _invalid("patch evidence IDs are invalid")
    result = tuple(item.strip() for item in value)
    if len(result) != len(set(result)):
        raise _invalid("patch evidence IDs must be unique")
    return result


def _request_projection(request: TemplatePatchRequest) -> Mapping[str, object]:
    draft = request.draft
    return {
        "draft": {
            "draft_id": draft.draft_id,
            "workspace_id": draft.workspace_id,
            "source_type": draft.source_type,
            "source_sha256": draft.source_sha256,
            "identified_fields": list(draft.identified_fields),
            "unknown_fields": list(draft.unknown_fields),
            "ambiguous_fields": list(draft.ambiguous_fields),
            "proposed_fields": [
                {
                    "source_key": item.source_key,
                    "target_field": item.target_field,
                    "source_locator": item.source_locator,
                }
                for item in draft.proposed_fields
            ],
            "structure": [
                {"kind": item.kind, "locator": item.locator, "value": item.value} for item in draft.structure
            ],
        },
        "target": {
            "template_id": request.target_template_id,
            "template_version": request.target_template_version,
            "domain_pack_id": request.domain_pack_id,
            "domain_pack_version": request.domain_pack_version,
            "evidence_pack_id": request.evidence_pack_id,
        },
        "rule": "Return only declarative field mapping diff and evidence IDs; never return executable content or authority decisions.",
    }


def _candidate_payload(candidate: TemplatePatchCandidate) -> Mapping[str, object]:
    return {
        "patch_id": candidate.patch_id,
        "draft_id": candidate.draft_id,
        "input_template_version": candidate.input_template_version,
        "target_template_id": candidate.target_template_id,
        "target_template_version": candidate.target_template_version,
        "target_template_hash": candidate.target_template_hash,
        "domain_pack_id": candidate.domain_pack_id,
        "domain_pack_version": candidate.domain_pack_version,
        "domain_pack_hash": candidate.domain_pack_hash,
        "evidence_pack_id": candidate.evidence_pack_id,
        "evidence_pack_hash": candidate.evidence_pack_hash,
        "run_id": candidate.run_id,
        "trace_id": candidate.trace_id,
        "model_version": candidate.model_version,
        "prompt_version": candidate.prompt_version,
        "diff": [dict(item) for item in candidate.diff],
        "evidence_ids": list(candidate.evidence_ids),
        "status": candidate.status.value,
        "created_at": candidate.created_at,
        "applied": candidate.applied,
    }


class TemplatePatchGenerator:
    """Decode one provider-neutral model response into an unapplied suggestion."""

    def __init__(self, gateway: TemplatePatchModelGateway, *, clock: Callable[[], str] = _now) -> None:
        self._gateway = gateway
        self._clock = clock

    def suggest(self, request: TemplatePatchRequest) -> AssistanceSuggestion[object]:
        if not isinstance(request, TemplatePatchRequest):
            raise _invalid("template patch request is invalid")
        if not isinstance(request.draft, TemplateDraft):
            raise _invalid("template patch draft is invalid")
        if request.draft.workspace_id.strip() == "":
            raise _invalid("template patch draft workspace is invalid")
        try:
            projection = _request_projection(request)
            response = self._gateway.generate(projection)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError(
                "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
                "the template mapping model is temporarily unavailable",
                retryable=True,
            ) from exc
        if not isinstance(response, Mapping) or set(response) != {"diff", "evidence_ids"}:
            raise _invalid("template mapping model returned invalid, unknown, or missing fields")
        diff = _validate_diff(response["diff"])
        evidence_ids = _normalize_evidence_ids(response["evidence_ids"])
        created_at = request.created_at or self._clock()
        try:
            candidate = TemplatePatchCandidate(
                patch_id=request.patch_id,
                draft_id=request.draft.draft_id,
                input_template_version=request.input_template_version,
                target_template_id=request.target_template_id,
                target_template_version=request.target_template_version,
                target_template_hash=_safe_hash(request.target_template_hash, "target template"),
                domain_pack_id=request.domain_pack_id,
                domain_pack_version=request.domain_pack_version,
                domain_pack_hash=_safe_hash(request.domain_pack_hash, "DomainPack"),
                evidence_pack_id=request.evidence_pack_id,
                evidence_pack_hash=_safe_hash(request.evidence_pack_hash, "EvidencePack"),
                run_id=request.run_id,
                trace_id=request.trace_id,
                model_version=request.model_version,
                prompt_version=request.prompt_version,
                diff=diff,
                evidence_ids=evidence_ids,
                status=TemplatePatchStatus.SUGGESTED,
                created_at=created_at,
            )
        except ReviewError:
            raise
        except (TypeError, ValueError) as exc:
            raise _invalid("template mapping provenance or candidate is invalid") from exc
        model_hash = sha256(request.model_version.encode("utf-8")).hexdigest()
        prompt_hash = sha256(request.prompt_version.encode("utf-8")).hexdigest()
        return AssistanceSuggestion(
            suggestion_id=f"template-patch-suggestion-{candidate.patch_id}",
            kind=AssistanceKind.TEMPLATE_FIELD_MAPPING,
            workspace_id=request.draft.workspace_id,
            target_type="template_draft",
            target_id=request.draft.draft_id,
            target_record_version=request.target_record_version,
            evidence_pack_ids=(candidate.evidence_pack_id,),
            payload=_candidate_payload(candidate),
            evidence_ids=candidate.evidence_ids,
            model_hash=model_hash,
            prompt_hash=prompt_hash,
            run_id=candidate.run_id,
            trace_id=candidate.trace_id,
            domain_pack_id=candidate.domain_pack_id,
            domain_pack_version=candidate.domain_pack_version,
            template_id=candidate.target_template_id,
            template_version=candidate.target_template_version,
            created_at=created_at,
        )


__all__ = ["TemplatePatchGenerator", "TemplatePatchModelGateway", "TemplatePatchRequest"]
