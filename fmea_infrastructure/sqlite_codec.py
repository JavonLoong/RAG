"""Shared strict SQLite codecs for canonical review persistence."""

# Persistence codecs intentionally expose stable ValueError failures for
# malformed stored data.
# ruff: noqa: TRY003, TRY004

from __future__ import annotations

import json
from dataclasses import fields
from typing import Any, NoReturn, cast

from core_domain.fmea.states import ActorType
from core_domain.fmea.value_objects import VersionSet
from fmea_application.review_contracts import (
    AuditEvent,
    ReviewAction,
    ReviewModelManifest,
    ReviewReasonCode,
    encode_review_json,
)

_AUDIT_LEGACY_FIELDS = frozenset({"run_id", "request_hash", "error_code", "retryable"})


def _strict_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"invalid JSON constant: {value}")


def load_strict_json(payload: object, kind: str) -> dict[str, object]:
    """Decode one persisted JSON object while rejecting ambiguous syntax."""

    if not isinstance(payload, str):
        raise ValueError(f"{kind} JSON must be text")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid persisted {kind} JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"persisted {kind} JSON must be an object")
    return value


def strict_string_tuple(value: object, kind: str) -> tuple[str, ...]:
    """Decode a strict persisted JSON string array."""

    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"persisted {kind} must be a string array")
    return tuple(value)


def decode_audit_event(payload: object) -> AuditEvent:
    """Decode current or approved legacy canonical AuditEvent JSON."""

    data = load_strict_json(payload, "audit event")
    current_fields = {field.name for field in fields(AuditEvent)}
    legacy_fields = current_fields - _AUDIT_LEGACY_FIELDS
    is_legacy = set(data) == legacy_fields
    if set(data) != current_fields and not is_legacy:
        raise ValueError("persisted audit event fields are invalid")
    raw_versions = data["versions"]
    if (
        not isinstance(raw_versions, dict)
        or set(raw_versions) != {field.name for field in fields(VersionSet)}
        or not all(isinstance(value, str) for value in raw_versions.values())
    ):
        raise ValueError("persisted audit event versions are invalid")
    raw_manifest = data["model_manifest"]
    if raw_manifest is not None and (
        not isinstance(raw_manifest, dict)
        or set(raw_manifest) != {field.name for field in fields(ReviewModelManifest)}
    ):
        raise ValueError("persisted audit event model manifest is invalid")
    try:
        versions = VersionSet(**cast(dict[str, Any], raw_versions))
        manifest = None if raw_manifest is None else ReviewModelManifest(**cast(dict[str, Any], raw_manifest))
        result = AuditEvent(
            event_id=cast(str, data["event_id"]),
            occurred_at_server=cast(str, data["occurred_at_server"]),
            workspace_id=cast(str, data["workspace_id"]),
            actor_id=cast(str, data["actor_id"]),
            actor_type=ActorType(cast(str, data["actor_type"])),
            actor_roles=strict_string_tuple(data["actor_roles"], "audit actor_roles"),
            command=cast(str, data["command"]),
            action=None if data["action"] is None else ReviewAction(cast(str, data["action"])),
            reason_code=None
            if data["reason_code"] is None
            else ReviewReasonCode(cast(str, data["reason_code"])),
            reason=cast(str, data["reason"]),
            analysis_id=cast(str, data["analysis_id"]),
            row_id=cast(str, data["row_id"]),
            suggestion_id=None if data["suggestion_id"] is None else cast(str, data["suggestion_id"]),
            decision_id=None if data["decision_id"] is None else cast(str, data["decision_id"]),
            expected_record_version=None
            if data["expected_record_version"] is None
            else cast(int, data["expected_record_version"]),
            applied_record_version=None
            if data["applied_record_version"] is None
            else cast(int, data["applied_record_version"]),
            before_hash=None if data["before_hash"] is None else cast(str, data["before_hash"]),
            after_hash=None if data["after_hash"] is None else cast(str, data["after_hash"]),
            changed_fields=strict_string_tuple(data["changed_fields"], "audit changed_fields"),
            evidence_ids=strict_string_tuple(data["evidence_ids"], "audit evidence_ids"),
            evidence_request_targets=strict_string_tuple(
                data["evidence_request_targets"], "audit evidence_request_targets"
            ),
            idempotency_key_hash=cast(str, data["idempotency_key_hash"]),
            canonical_payload_hash=cast(str, data["canonical_payload_hash"]),
            versions=versions,
            template_id=cast(str, data["template_id"]),
            template_version=cast(str, data["template_version"]),
            profile_id=cast(str, data["profile_id"]),
            profile_version=cast(str, data["profile_version"]),
            model_manifest=manifest,
            request_id=cast(str, data["request_id"]),
            trace_id=cast(str, data["trace_id"]),
            retrieval_trace_id=cast(str, data["retrieval_trace_id"]),
            run_id=None if is_legacy or data["run_id"] is None else cast(str, data["run_id"]),
            request_hash=None if is_legacy or data["request_hash"] is None else cast(str, data["request_hash"]),
            error_code=None if is_legacy or data["error_code"] is None else cast(str, data["error_code"]),
            retryable=False if is_legacy else cast(bool, data["retryable"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("persisted audit event values are invalid") from exc
    canonical_payload = load_strict_json(encode_review_json(result), "audit event")
    if is_legacy:
        for field_name in _AUDIT_LEGACY_FIELDS:
            canonical_payload.pop(field_name)
    if encode_review_json(canonical_payload) != payload:
        raise ValueError("persisted audit event is not canonical")
    return result


def audit_event_json_matches(payload: object, audit: AuditEvent) -> bool:
    """Match current or approved legacy canonical AuditEvent JSON."""

    if not isinstance(payload, str):
        return False
    if payload == encode_review_json(audit):
        return True
    try:
        canonical_payload = load_strict_json(encode_review_json(audit), "audit event")
        stored_payload = load_strict_json(payload, "audit event")
    except ValueError:
        return False
    if set(stored_payload) != set(canonical_payload) - _AUDIT_LEGACY_FIELDS:
        return False
    for field_name in _AUDIT_LEGACY_FIELDS:
        canonical_payload.pop(field_name)
    return encode_review_json(canonical_payload) == payload


__all__ = ["audit_event_json_matches", "decode_audit_event", "load_strict_json", "strict_string_tuple"]
