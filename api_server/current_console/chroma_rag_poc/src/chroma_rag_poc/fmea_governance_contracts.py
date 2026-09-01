"""Shared, projection-safe contracts for the FMEA governance adapters."""

# ruff: noqa: C901, TRY003, TRY004

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import re
import secrets
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

SCHEMA_VERSION = "graphrag.fmea.v1"
RESOURCE_VERSION = "1.0.0"
EMPTY_FILTER_HASH = hashlib.sha256(b"{}").hexdigest()
_CURSOR_MAX_BYTES = 4096
_CURSOR_FORMAT_VERSION = 1
_CURSOR_NONCE_BYTES = 16
_ID_MAX_CHARS = 256
_REASON_MAX_CHARS = 500
_PROJECTION_MAX_DEPTH = 8
_PROJECTION_MAX_CONTAINER_ITEMS = 500
_PROJECTION_MAX_NODES = 10_000
_PROJECTION_MAX_STRING_CHARS = 4096
_PROJECTION_MAX_BYTES = 256 * 1024
_PRIVATE_KEY_MARKERS = frozenset({
    "accesstoken",
    "apikey",
    "authorization",
    "credential",
    "databasepath",
    "password",
    "passwd",
    "private",
    "privatekey",
    "privatepath",
    "prompt",
    "providererror",
    "provideroutput",
    "rawoutput",
    "secret",
    "sql",
})
_IMMUTABLE_HASH = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
_URI_OR_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:|[A-Za-z]:[\\/]|[\\/])")
_PATH_TRAVERSAL = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")


def derive_governance_cursor_secret(configured: str | None) -> bytes:
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError("FMEA_GOVERNANCE_CURSOR_SECRET is required")
    return hashlib.sha256(b"fmea-governance-cursor-secret\x00" + configured.encode("utf-8")).digest()


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RevisionAssemblyBody(_StrictRequest):
    parent_revision_id: StrictStr | None = Field(default=None, min_length=1, max_length=_ID_MAX_CHARS)
    parent_revision_hash: StrictStr | None = Field(default=None, min_length=1, max_length=_ID_MAX_CHARS)
    confirm_human_approval: StrictBool = False


class ApprovalSubmissionBody(_StrictRequest):
    revision_hash: StrictStr = Field(min_length=1, max_length=_ID_MAX_CHARS)
    confirm_human_approval: StrictBool = False


class ApprovalDecisionBody(_StrictRequest):
    revision_id: StrictStr = Field(min_length=1, max_length=_ID_MAX_CHARS)
    revision_hash: StrictStr = Field(min_length=1, max_length=_ID_MAX_CHARS)
    reason: StrictStr = Field(min_length=1, max_length=_REASON_MAX_CHARS)
    confirm_human_approval: StrictBool = False


class ApprovalWithdrawalBody(_StrictRequest):
    revision_hash: StrictStr = Field(min_length=1, max_length=_ID_MAX_CHARS)
    reason: StrictStr = Field(min_length=1, max_length=_REASON_MAX_CHARS)
    confirm_approval_withdrawal: StrictBool = False


class PublicationBody(_StrictRequest):
    approval_id: StrictStr = Field(min_length=1, max_length=_ID_MAX_CHARS)
    revision_hash: StrictStr = Field(min_length=1, max_length=_ID_MAX_CHARS)
    confirm_publication: StrictBool = False


class PublicationWithdrawalBody(_StrictRequest):
    reason: StrictStr = Field(min_length=1, max_length=_REASON_MAX_CHARS)
    replacement_publication_id: StrictStr | None = Field(default=None, min_length=1, max_length=_ID_MAX_CHARS)
    confirm_publication_withdrawal: StrictBool = False


class SupersessionBody(_StrictRequest):
    replacement_publication_id: StrictStr = Field(min_length=1, max_length=_ID_MAX_CHARS)
    replacement_record_version: StrictInt = Field(ge=1)
    reason: StrictStr = Field(min_length=1, max_length=_REASON_MAX_CHARS)
    confirm_supersession: StrictBool = False


class RevisionVersionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: str
    record_version: StrictInt
    content_hash: str


class RetrievalProvenanceData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_profile: str
    resolved_profile: str
    evidence_types: list[str]
    source_counts: list[list[str | int]]
    warnings: list[str]


class ReadinessIssueData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: str
    source_type: str
    source_id: str
    evidence_ids: list[str]
    acknowledgement_decision_id: str | None


class RevisionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: str
    workspace_id: str
    analysis_id: str
    record_version: StrictInt
    analysis_record_version: StrictInt
    revision_hash: str
    analysis_hash: str
    parent_revision_id: str | None
    parent_revision_hash: str | None
    row_versions: list[RevisionVersionData]
    risk_versions: list[RevisionVersionData]
    propagation_graph_revision_id: str | None
    propagation_graph_hash: str | None
    evidence_pack_hashes: list[list[str]]
    retrieval_provenance: RetrievalProvenanceData
    domain_pack_identity: list[str]
    template_identities: list[list[str]]
    scoring_rule_identities: list[list[str]]
    propagation_rule_identity: list[str] | None
    unresolved_items: list[ReadinessIssueData]
    created_at: str


class ReadinessData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: str
    workspace_id: str
    analysis_id: str
    record_version: StrictInt
    target_record_version: StrictInt
    revision_hash: str
    evidence_pack_ids: list[str]
    ready: StrictBool
    issues: list[ReadinessIssueData]
    blocking_codes: list[str]
    deterministic: StrictBool


class ReadinessSuggestionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: str
    run_id: str
    target_type: str
    target_id: str
    target_record_version: StrictInt
    ready: StrictBool
    blocking_codes: list[str]
    checklist: list[dict[str, Any]]
    applied: StrictBool
    trace_id: str
    created_at: str


class GovernanceMutationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replayed: StrictBool
    audit_event_id: str
    outbox_event_id: str
    record_version: StrictInt | None = None
    revision_id: str | None = None
    readiness_id: str | None = None
    submission_id: str | None = None
    approval_id: str | None = None
    withdrawal_id: str | None = None
    publication_id: str | None = None
    manifest_id: str | None = None
    snapshot_id: str | None = None
    supersession_id: str | None = None
    old_publication_id: str | None = None
    new_publication_id: str | None = None


class PublicationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publication_id: str
    workspace_id: str
    analysis_id: str
    revision_id: str
    revision_hash: str
    approval_id: str
    manifest_id: str
    manifest_hash: str
    snapshot_id: str
    snapshot_hash: str
    audit_chain_head: str
    publisher_actor_id: str
    record_version: StrictInt
    created_at: str
    effective_status: str
    withdrawal: dict[str, Any] | None
    supersession: dict[str, Any] | None


class SnapshotData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    snapshot_id: str
    workspace_id: str
    analysis_id: str
    revision_id: str
    revision_hash: str
    publication_id: str
    manifest_id: str
    rows: list[dict[str, Any]]
    risk_records: list[dict[str, Any]]
    propagation: dict[str, Any] | None
    evidence_summary: list[dict[str, Any]]
    decision_summary: list[dict[str, Any]]
    version_manifest: dict[str, Any]
    unresolved_items: list[dict[str, Any]]
    audit_summary: dict[str, Any]
    row_count: StrictInt
    snapshot_hash: str
    created_at: str


class GovernanceEventData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    occurred_at_server: str
    workspace_id: str
    actor_id: str
    actor_type: str
    actor_roles: list[str]
    command: str
    reason: str
    analysis_id: str
    row_id: str
    decision_id: str | None
    expected_record_version: StrictInt | None
    applied_record_version: StrictInt | None
    after_hash: str | None


class GovernanceHistoryPageData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[GovernanceEventData]
    next_cursor: str | None
    limit: StrictInt


class GovernanceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    resource_type: str
    resource_version: str = RESOURCE_VERSION
    request_id: str
    trace_id: str
    data: Any


def projection_safe_json(value: object) -> object:
    """Normalize generic governance projection values through one bounded JSON boundary."""

    nodes = 0
    active: set[int] = set()

    def visit(item: object, depth: int) -> object:
        nonlocal nodes
        nodes += 1
        if nodes > _PROJECTION_MAX_NODES:
            raise ValueError("governance projection has too many values")
        if depth > _PROJECTION_MAX_DEPTH:
            raise ValueError("governance projection is too deeply nested")
        if item is None or isinstance(item, bool | int):
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("governance projection contains a non-finite number")
            return item
        if isinstance(item, str):
            if len(item) > _PROJECTION_MAX_STRING_CHARS:
                raise ValueError("governance projection string is too long")
            if not _IMMUTABLE_HASH.fullmatch(item) and (
                _URI_OR_ABSOLUTE_PATH.match(item) or _PATH_TRAVERSAL.search(item)
            ):
                raise ValueError("governance projection contains a private location")
            return item
        if not isinstance(item, dict | list | tuple):
            raise ValueError("governance projection contains a non-JSON value")
        identity = id(item)
        if identity in active:
            raise ValueError("governance projection contains a cycle")
        if len(item) > _PROJECTION_MAX_CONTAINER_ITEMS:
            raise ValueError("governance projection container is too large")
        active.add(identity)
        try:
            if isinstance(item, dict):
                result: dict[str, object] = {}
                for key, nested in item.items():
                    if not isinstance(key, str) or not key or len(key) > _ID_MAX_CHARS:
                        raise ValueError("governance projection key is invalid")
                    normalized = "".join(character for character in key.lower() if character.isalnum())
                    if key.startswith("_") or any(marker in normalized for marker in _PRIVATE_KEY_MARKERS):
                        raise ValueError("governance projection contains a private key")
                    result[key] = visit(nested, depth + 1)
                return result
            return [visit(nested, depth + 1) for nested in item]
        finally:
            active.remove(identity)

    normalized = visit(value, 0)
    encoded = json.dumps(normalized, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > _PROJECTION_MAX_BYTES:
        raise ValueError("governance projection exceeds the response byte budget")
    return normalized


def _safe_model(model_type: type[BaseModel], payload: dict[str, object]) -> BaseModel:
    normalized = projection_safe_json(payload)
    if not isinstance(normalized, dict):
        raise ValueError("governance projection must be a JSON object")
    return model_type.model_validate(normalized)


def _revision_versions(value: object) -> list[RevisionVersionData]:
    return [
        RevisionVersionData(identity=str(item[0]), record_version=item[1], content_hash=item[2])
        for item in getattr(value, "__iter__", lambda: ())()
    ]


def _issue_data(value: object) -> ReadinessIssueData:
    return ReadinessIssueData(
        code=value.code,
        severity=value.severity,
        source_type=value.source_type,
        source_id=value.source_id,
        evidence_ids=list(value.evidence_ids),
        acknowledgement_decision_id=value.acknowledgement_decision_id,
    )


def revision_data(value: object, *, record_version: int | None = None) -> RevisionData:
    version = record_version if record_version is not None else getattr(value, "record_version", None)
    if version is None:
        raise ValueError("repository-backed revision record_version is required")
    provenance = value.retrieval_provenance
    return RevisionData(
        revision_id=value.revision_id,
        workspace_id=value.workspace_id,
        analysis_id=value.analysis_id,
        record_version=version,
        analysis_record_version=value.analysis_record_version,
        revision_hash=value.revision_hash,
        analysis_hash=value.analysis_hash,
        parent_revision_id=value.parent_revision_id,
        parent_revision_hash=value.parent_revision_hash,
        row_versions=_revision_versions(value.row_versions),
        risk_versions=_revision_versions(value.risk_versions),
        propagation_graph_revision_id=value.propagation_graph_revision_id,
        propagation_graph_hash=value.propagation_graph_hash,
        evidence_pack_hashes=[list(item) for item in value.evidence_pack_hashes],
        retrieval_provenance=RetrievalProvenanceData(
            requested_profile=str(provenance.requested_profile),
            resolved_profile=str(provenance.resolved_profile),
            evidence_types=[str(item) for item in provenance.evidence_types],
            source_counts=[list(item) for item in provenance.source_counts],
            warnings=list(provenance.warnings),
        ),
        domain_pack_identity=list(value.domain_pack_identity),
        template_identities=[list(item) for item in value.template_identities],
        scoring_rule_identities=[list(item) for item in value.scoring_rule_identities],
        propagation_rule_identity=(
            None if value.propagation_rule_identity is None else list(value.propagation_rule_identity)
        ),
        unresolved_items=[_issue_data(item) for item in value.unresolved_items],
        created_at=value.created_at,
    )


def readiness_data(value: object, *, record_version: int) -> ReadinessData:
    return ReadinessData(
        revision_id=value.revision_id,
        workspace_id=value.workspace_id,
        analysis_id=value.analysis_id,
        record_version=record_version,
        target_record_version=value.target_record_version,
        revision_hash=value.revision_hash,
        evidence_pack_ids=list(value.evidence_pack_ids),
        ready=value.ready,
        issues=[_issue_data(item) for item in value.issues],
        blocking_codes=list(value.blocking_codes),
        deterministic=value.deterministic,
    )


def readiness_suggestion_data(value: object) -> ReadinessSuggestionData:
    payload = projection_safe_json(getattr(value, "payload", {}))
    if not isinstance(payload, dict):
        payload = {}
    checklist = payload.get("checklist", getattr(value, "checklist", ()))
    return cast(
        ReadinessSuggestionData,
        _safe_model(
            ReadinessSuggestionData,
            {
                "suggestion_id": value.suggestion_id,
                "run_id": value.run_id,
                "target_type": getattr(value, "target_type", "fmea_revision_readiness"),
                "target_id": getattr(value, "target_id", getattr(value, "target", "")),
                "target_record_version": value.target_record_version,
                "ready": payload.get("ready", getattr(value, "ready", False)),
                "blocking_codes": list(payload.get("blocking_codes", getattr(value, "blocking_codes", ()))),
                "checklist": [dict(item) for item in checklist],
                "applied": value.applied,
                "trace_id": value.trace_id,
                "created_at": getattr(value, "created_at", ""),
            },
        ),
    )


def _mutation(value: object, **identities: object) -> GovernanceMutationData:
    return GovernanceMutationData(
        replayed=bool(getattr(value, "replayed", False)),
        audit_event_id=value.audit_event_id,
        outbox_event_id=value.outbox_event_id,
        record_version=getattr(value, "record_version", None),
        **identities,
    )


def revision_result_data(value: object) -> GovernanceMutationData:
    return _mutation(value, revision_id=value.revision_id)


def readiness_result_data(value: object) -> GovernanceMutationData:
    return _mutation(value, readiness_id=value.readiness_id)  # type: ignore[call-arg]


def approval_submission_result_data(value: object) -> GovernanceMutationData:
    return _mutation(value, submission_id=value.submission_id)


def approval_result_data(value: object) -> GovernanceMutationData:
    return _mutation(value, approval_id=value.approval_id)


def approval_withdrawal_result_data(value: object) -> GovernanceMutationData:
    return _mutation(value, withdrawal_id=value.withdrawal_id, approval_id=value.approval_id)


def publication_result_data(value: object) -> GovernanceMutationData:
    return _mutation(
        value,
        publication_id=value.publication_id,
        manifest_id=value.manifest_id,
        snapshot_id=value.snapshot_id,
    )


def publication_withdrawal_result_data(value: object) -> GovernanceMutationData:
    return _mutation(value, withdrawal_id=value.withdrawal_id, publication_id=value.publication_id)


def supersession_result_data(value: object) -> GovernanceMutationData:
    return _mutation(
        value,
        supersession_id=value.supersession_id,
        old_publication_id=value.old_publication_id,
        new_publication_id=value.new_publication_id,
    )


def publication_data(value: object) -> PublicationData:
    publication = value.publication
    withdrawal_fields = (
        "withdrawal_id",
        "publication_id",
        "replacement_publication_id",
        "actor_id",
        "reason",
        "created_at",
    )
    supersession_fields = (
        "supersession_id",
        "old_publication_id",
        "new_publication_id",
        "actor_id",
        "reason",
        "created_at",
    )

    def lifecycle_record(record: object | None, names: tuple[str, ...]) -> dict[str, object] | None:
        if record is None:
            return None
        if isinstance(record, dict):
            return record
        return {name: getattr(record, name) for name in names}

    return cast(
        PublicationData,
        _safe_model(
            PublicationData,
            {
                "publication_id": publication.publication_id,
                "workspace_id": publication.workspace_id,
                "analysis_id": publication.analysis_id,
                "revision_id": publication.revision_id,
                "revision_hash": publication.revision_hash,
                "approval_id": publication.approval_id,
                "manifest_id": publication.manifest_id,
                "manifest_hash": publication.manifest_hash,
                "snapshot_id": publication.snapshot_id,
                "snapshot_hash": publication.snapshot_hash,
                "audit_chain_head": publication.audit_chain_head,
                "publisher_actor_id": publication.publisher_actor_id,
                "record_version": publication.record_version,
                "created_at": publication.created_at,
                "effective_status": getattr(value.effective_status, "value", value.effective_status),
                "withdrawal": lifecycle_record(value.withdrawal, withdrawal_fields),
                "supersession": lifecycle_record(value.supersession, supersession_fields),
            },
        ),
    )


def snapshot_data(value: object) -> SnapshotData:
    names = (
        "schema_version",
        "snapshot_id",
        "workspace_id",
        "analysis_id",
        "revision_id",
        "revision_hash",
        "publication_id",
        "manifest_id",
        "rows",
        "risk_records",
        "propagation",
        "evidence_summary",
        "decision_summary",
        "version_manifest",
        "unresolved_items",
        "audit_summary",
        "row_count",
        "snapshot_hash",
        "created_at",
    )
    data = {name: getattr(value, name) for name in names}
    return cast(SnapshotData, _safe_model(SnapshotData, data))


def event_data(value: object) -> GovernanceEventData:
    return cast(
        GovernanceEventData,
        _safe_model(
            GovernanceEventData,
            {
                "event_id": value.event_id,
                "occurred_at_server": value.occurred_at_server,
                "workspace_id": value.workspace_id,
                "actor_id": value.actor_id,
                "actor_type": getattr(value.actor_type, "value", value.actor_type),
                "actor_roles": list(value.actor_roles),
                "command": value.command,
                "reason": value.reason,
                "analysis_id": value.analysis_id,
                "row_id": value.row_id,
                "decision_id": value.decision_id,
                "expected_record_version": value.expected_record_version,
                "applied_record_version": value.applied_record_version,
                "after_hash": value.after_hash,
            },
        ),
    )


def history_data(events: object, *, next_cursor: str | None, limit: int) -> GovernanceHistoryPageData:
    return cast(
        GovernanceHistoryPageData,
        _safe_model(
            GovernanceHistoryPageData,
            {
                "items": [event_data(item).model_dump(mode="json") for item in events],
                "next_cursor": next_cursor,
                "limit": limit,
            },
        ),
    )


def governance_envelope(resource_type: str, data: object, *, request_id: str, trace_id: str) -> dict[str, object]:
    envelope = GovernanceEnvelope(
        resource_type=resource_type,
        request_id=request_id,
        trace_id=trace_id,
        data=data,
    ).model_dump(mode="json")
    normalized = projection_safe_json(envelope)
    if not isinstance(normalized, dict):
        raise ValueError("governance envelope must be a JSON object")
    return normalized


def _b64decode(value: str) -> bytes:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        canonical = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("history cursor is invalid") from exc
    if not hmac.compare_digest(canonical, value):
        raise ValueError("history cursor is invalid")
    return raw


def _cursor_keystream(secret: bytes, nonce: bytes, length: int) -> bytes:
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        stream.extend(
            hmac.new(
                secret,
                b"fmea-governance-cursor\x00" + nonce + counter.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
        )
        counter += 1
    return bytes(stream[:length])


def _cursor_crypt(secret: bytes, nonce: bytes, payload: bytes) -> bytes:
    return bytes(
        left ^ right for left, right in zip(payload, _cursor_keystream(secret, nonce, len(payload)), strict=False)
    )


def _cursor_context(
    *, workspace_id: str, resource_type: str, resource_id: str, descending: bool, page_size: int, filter_hash: str
) -> dict[str, object]:
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError("workspace_id is invalid")
    if resource_type not in {"revision", "publication"}:
        raise ValueError("resource_type is invalid")
    if not isinstance(resource_id, str) or not resource_id.strip():
        raise ValueError("resource_id is invalid")
    if (
        type(descending) is not bool
        or not isinstance(page_size, int)
        or isinstance(page_size, bool)
        or not 1 <= page_size <= 500
    ):
        raise ValueError("cursor page contract is invalid")
    if (
        not isinstance(filter_hash, str)
        or len(filter_hash) != 64
        or any(char not in "0123456789abcdef" for char in filter_hash)
    ):
        raise ValueError("cursor filter hash is invalid")
    return {
        "workspace_id": workspace_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "descending": descending,
        "page_size": page_size,
        "filter_hash": filter_hash,
    }


def encode_history_cursor(
    secret: bytes,
    *,
    workspace_id: str,
    resource_type: str,
    resource_id: str,
    descending: bool,
    page_size: int,
    filter_hash: str = EMPTY_FILTER_HASH,
    repository_cursor: str,
) -> str:
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("history cursor signing is unavailable")
    if not isinstance(repository_cursor, str) or not repository_cursor:
        raise ValueError("repository cursor is invalid")
    payload_object = _cursor_context(
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        descending=descending,
        page_size=page_size,
        filter_hash=filter_hash,
    )
    payload_object["repository_cursor"] = repository_cursor
    plaintext = json.dumps(payload_object, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    nonce = secrets.token_bytes(_CURSOR_NONCE_BYTES)
    payload = bytes([_CURSOR_FORMAT_VERSION]) + nonce + _cursor_crypt(secret, nonce, plaintext)
    payload_text = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    signature = hmac.new(secret, payload_text.encode("ascii"), hashlib.sha256).digest()
    signature_text = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    result = f"{payload_text}.{signature_text}"
    if len(result) > _CURSOR_MAX_BYTES:
        raise ValueError("history cursor is too large")
    return result


def decode_history_cursor(
    secret: bytes,
    value: str,
    *,
    workspace_id: str,
    resource_type: str,
    resource_id: str,
    descending: bool,
    page_size: int,
    filter_hash: str = EMPTY_FILTER_HASH,
) -> str:
    if (
        not isinstance(secret, bytes)
        or len(secret) < 32
        or not isinstance(value, str)
        or len(value) > _CURSOR_MAX_BYTES
    ):
        raise ValueError("history cursor is invalid")
    if value.count(".") != 1:
        raise ValueError("history cursor is invalid")
    payload_text, signature_text = value.split(".", 1)
    if not payload_text or not signature_text:
        raise ValueError("history cursor is invalid")
    payload = _b64decode(payload_text)
    actual = _b64decode(signature_text)
    expected = hmac.new(secret, payload_text.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(actual, expected):
        raise ValueError("history cursor is invalid")
    if len(payload) <= 1 + _CURSOR_NONCE_BYTES or payload[0] != _CURSOR_FORMAT_VERSION:
        raise ValueError("history cursor is invalid")
    nonce = payload[1 : 1 + _CURSOR_NONCE_BYTES]
    encrypted = payload[1 + _CURSOR_NONCE_BYTES :]
    try:
        decoded = json.loads(_cursor_crypt(secret, nonce, encrypted).decode("ascii"))
    except (ValueError, UnicodeDecodeError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("history cursor is invalid") from exc
    expected_context = _cursor_context(
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        descending=descending,
        page_size=page_size,
        filter_hash=filter_hash,
    )
    if (
        not isinstance(decoded, dict)
        or set(decoded) != set(expected_context) | {"repository_cursor"}
        or any(decoded.get(key) != expected for key, expected in expected_context.items())
        or not isinstance(decoded.get("repository_cursor"), str)
        or not decoded["repository_cursor"]
    ):
        raise ValueError("history cursor is invalid")
    return decoded["repository_cursor"]


__all__ = [
    "EMPTY_FILTER_HASH",
    "ApprovalDecisionBody",
    "ApprovalSubmissionBody",
    "ApprovalWithdrawalBody",
    "GovernanceEnvelope",
    "GovernanceEventData",
    "GovernanceHistoryPageData",
    "GovernanceMutationData",
    "PublicationBody",
    "PublicationData",
    "PublicationWithdrawalBody",
    "ReadinessData",
    "ReadinessIssueData",
    "ReadinessSuggestionData",
    "RevisionAssemblyBody",
    "RevisionData",
    "SnapshotData",
    "SupersessionBody",
    "approval_result_data",
    "approval_submission_result_data",
    "approval_withdrawal_result_data",
    "decode_history_cursor",
    "encode_history_cursor",
    "event_data",
    "governance_envelope",
    "history_data",
    "publication_data",
    "publication_result_data",
    "publication_withdrawal_result_data",
    "readiness_data",
    "readiness_result_data",
    "readiness_suggestion_data",
    "revision_data",
    "revision_result_data",
    "snapshot_data",
    "supersession_result_data",
]
