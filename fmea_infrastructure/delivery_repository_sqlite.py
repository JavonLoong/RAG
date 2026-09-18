"""SQLite delivery persistence for migration reports and confirmed revisions.

The delivery repository deliberately subclasses the existing governance
repository.  That keeps one authority implementation for revisions, audit,
outbox, and idempotency while allowing migration delivery to compose those
protected primitives inside one transaction.
"""

# The repository is an infrastructure boundary with deliberately explicit SQL
# and validation branches.  Keep the same lint policy as the governance store.
# ruff: noqa: C901, TRY003, TRY004, TRY300, TRY301

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, cast

from core_domain.fmea.governance import FmeaRevision, revision_content_hash
from core_domain.fmea.states import FMEA_SCHEMA_ID, ActorType, RunStatus
from core_domain.fmea.template_migration import (
    MigrationPlan,
    MigrationReport,
    MigrationReportStatus,
    MigrationStep,
    ProposedFieldMapping,
    SourceStructureItem,
    TemplateDraft,
    TemplatePatchCandidate,
)
from core_domain.fmea.value_objects import VersionSet
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.delivery_contracts import (
    ExportArtifactManifest,
    ExportRun,
    validate_export_binding,
)
from fmea_application.migration_service import (
    ConfirmMigrationCommand,
    MigrationCommand,
    MigrationResult,
    PreparedMigration,
    migration_report_id,
)
from fmea_application.migration_service import (
    MigrationServiceError as ReviewError,
)
from fmea_application.ports import MigrationReportRequestConflict
from fmea_application.review_contracts import (
    ActorContext,
    AuditEvent,
    IdempotencyScope,
    encode_review_json,
    idempotency_key_hash,
)
from fmea_application.review_errors import ReviewError as ApplicationReviewError
from fmea_application.risk_contracts import OutboxEvent, canonical_json, outbox_payload_hash
from fmea_application.template_patch_contracts import (
    TemplatePatchDecision,
    TemplatePatchSuggestion,
    candidate_from_payload,
)

from .governance_repository_sqlite import SqliteGovernanceRepository, _PreparedMeta
from .sqlite_codec import decode_audit_event, load_strict_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _digest(value: str) -> str:
    return value.removeprefix("sha256:")


def _prefixed(value: str) -> str:
    return value if value.startswith("sha256:") else f"sha256:{value}"


def _hash_json(value: object) -> str:
    payload = canonical_json(value)
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def _json_value(value: object) -> object:
    """Project supported contracts to strict, deterministic JSON values."""

    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, frozenset):
        return sorted(_json_value(item) for item in value)
    return value


def _contract_json(value: object) -> tuple[str, str]:
    payload = canonical_json(_json_value(value))
    return payload, _hash_json(_json_value(value))


def _load_object(payload: object, kind: str) -> dict[str, object]:
    if not isinstance(payload, str):
        raise ValueError(f"persisted {kind} JSON is not text")
    try:
        value = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"persisted {kind} JSON is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError(f"persisted {kind} JSON is not an object")
    if canonical_json(value) != payload:
        raise ValueError(f"persisted {kind} JSON is not canonical")
    return value


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


def _report_plan_value(plan: MigrationPlan) -> dict[str, object]:
    return cast(dict[str, object], _json_value(plan))


def _report_value(report: MigrationReport) -> dict[str, object]:
    return cast(dict[str, object], _json_value(report))


def _decode_plan(value: object) -> MigrationPlan:
    if not isinstance(value, dict):
        raise ValueError("persisted migration plan is invalid")
    steps_value = value.get("steps")
    if not isinstance(steps_value, list):
        raise ValueError("persisted migration plan steps are invalid")
    steps = tuple(
        MigrationStep(
            source=tuple(cast(list[object], item["source"])),
            target=tuple(cast(list[object], item["target"])),
            adapter_id=cast(str, item["adapter_id"]),
        )
        for item in steps_value
        if isinstance(item, dict)
    )
    if len(steps) != len(steps_value):
        raise ValueError("persisted migration plan steps are invalid")
    return MigrationPlan(
        source=tuple(cast(list[object], value["source"])),
        target=tuple(cast(list[object], value["target"])),
        steps=steps,
    )


def _decode_report(payload: object, stored_hash: str) -> MigrationReport:
    data = _load_object(payload, "migration report")
    report = MigrationReport(
        migration_id=cast(str, data["migration_id"]),
        plan=_decode_plan(data["plan"]),
        source_revision_id=cast(str, data["source_revision_id"]),
        source_revision_hash=cast(str, data["source_revision_hash"]),
        source_domain_pack_identity=tuple(cast(list[object], data["source_domain_pack_identity"])),
        target_domain_pack_identity=tuple(cast(list[object], data["target_domain_pack_identity"])),
        target_revision_hash=cast(str, data["target_revision_hash"]),
        status=cast(str, data["status"]),
        mapped_fields=tuple(cast(list[object], data["mapped_fields"])),
        dropped_fields=tuple(cast(list[object], data["dropped_fields"])),
        unresolved_fields=tuple(cast(list[object], data["unresolved_fields"])),
        warnings=tuple(cast(list[object], data["warnings"])),
        created_at=cast(str, data["created_at"]),
        report_hash=stored_hash,
    )
    if _report_value(report) != data:
        raise ValueError("persisted migration report does not round-trip")
    return report


def _decode_draft(payload: object) -> TemplateDraft:
    data = _load_object(payload, "template draft")
    structure = tuple(
        SourceStructureItem(
            kind=cast(str, item["kind"]),
            locator=cast(str, item["locator"]),
            value=item.get("value"),
        )
        for item in cast(list[dict[str, object]], data["structure"])
    )
    proposed = tuple(
        ProposedFieldMapping(
            source_key=cast(str, item["source_key"]),
            target_field=cast(str, item["target_field"]),
            source_locator=cast(str, item["source_locator"]),
            confidence=cast(float | None, item.get("confidence")),
            rationale=cast(str | None, item.get("rationale")),
        )
        for item in cast(list[dict[str, object]], data["proposed_fields"])
    )
    draft = TemplateDraft(
        draft_id=cast(str, data["draft_id"]),
        workspace_id=cast(str, data["workspace_id"]),
        source_filename=cast(str, data["source_filename"]),
        source_sha256=cast(str, data["source_sha256"]),
        source_type=cast(str, data["source_type"]),
        structure=structure,
        proposed_fields=proposed,
        unknown_fields=tuple(cast(list[object], data["unknown_fields"])),
        ambiguous_fields=tuple(cast(list[object], data["ambiguous_fields"])),
        parser_warnings=tuple(cast(list[object], data["parser_warnings"])),
        status=cast(str, data["status"]),
        created_at=cast(str, data["created_at"]),
        identified_fields=tuple(cast(list[object], data.get("identified_fields", []))),
    )
    if _json_value(draft) != data:
        raise ValueError("persisted template draft does not round-trip")
    return draft


def _decode_patch(payload: object) -> TemplatePatchCandidate:
    data = _load_object(payload, "template patch candidate")
    candidate = TemplatePatchCandidate(
        patch_id=cast(str, data["patch_id"]),
        draft_id=cast(str, data["draft_id"]),
        input_template_version=cast(str, data["input_template_version"]),
        target_template_id=cast(str, data["target_template_id"]),
        target_template_version=cast(str, data["target_template_version"]),
        target_template_hash=cast(str, data["target_template_hash"]),
        domain_pack_id=cast(str, data["domain_pack_id"]),
        domain_pack_version=cast(str, data["domain_pack_version"]),
        domain_pack_hash=cast(str, data["domain_pack_hash"]),
        evidence_pack_id=cast(str, data["evidence_pack_id"]),
        evidence_pack_hash=cast(str, data["evidence_pack_hash"]),
        run_id=cast(str, data["run_id"]),
        trace_id=cast(str, data["trace_id"]),
        model_version=cast(str, data["model_version"]),
        prompt_version=cast(str, data["prompt_version"]),
        diff=tuple(cast(list[Mapping[str, object]], data["diff"])),
        evidence_ids=tuple(cast(list[object], data["evidence_ids"])),
        status=cast(str, data["status"]),
        created_at=cast(str, data["created_at"]),
    )
    if _json_value(candidate) != data:
        raise ValueError("persisted template patch candidate does not round-trip")
    return candidate


def _decode_template_suggestion(payload: object) -> TemplatePatchSuggestion:
    data = _load_object(payload, "template patch suggestion")
    try:
        kind = AssistanceKind(cast(str, data["kind"]))
        candidate = candidate_from_payload(data["payload"])
        envelope = AssistanceSuggestion(
            **(
                data
                | {
                    "kind": kind,
                    "evidence_pack_ids": tuple(cast(list[object], data["evidence_pack_ids"])),
                    "evidence_ids": tuple(cast(list[object], data["evidence_ids"])),
                    "conflict_ids": tuple(cast(list[object], data["conflict_ids"])),
                }
            )
        )
        suggestion = TemplatePatchSuggestion(candidate=candidate, envelope=envelope)
    except Exception:
        raise ValueError("persisted template patch suggestion is invalid") from None
    if _json_value(suggestion.envelope) != data:
        raise ValueError("persisted template patch suggestion does not round-trip")
    return suggestion


def _decode_template_decision(payload: object) -> TemplatePatchDecision:
    data = _load_object(payload, "template patch decision")
    try:
        decision = TemplatePatchDecision(
            **(
                data
                | {
                    "actor_type": ActorType(cast(str, data["actor_type"])),
                    "candidate": candidate_from_payload(data["candidate"]),
                }
            )
        )
    except Exception:
        raise ValueError("persisted template patch decision is invalid") from None
    if _json_value(decision) != data:
        raise ValueError("persisted template patch decision does not round-trip")
    return decision


def _request_value(command: MigrationCommand | ConfirmMigrationCommand) -> dict[str, object]:
    return cast(
        dict[str, object],
        _json_value(command),
    )


def _migration_payload(
    prepared: PreparedMigration, child: FmeaRevision, dry_run_request_key_hash: str
) -> dict[str, object]:
    command = prepared.command
    report = prepared.report
    return {
        "migration_id": command.migration_id,
        "source_revision_id": command.source_revision_id,
        "source_revision_hash": command.source_revision_hash,
        "source_domain_pack_identity": list(report.source_domain_pack_identity),
        "target_domain_pack_identity": list(prepared.target_domain_pack_identity),
        "target_revision_hash": report.target_revision_hash,
        "dry_run_request_idempotency_key_hash": dry_run_request_key_hash,
        "report_hash": report.report_hash,
        "plan": _report_plan_value(report.plan),
        "mapped_fields": list(report.mapped_fields),
        "dropped_fields": list(report.dropped_fields),
        "unresolved_fields": list(report.unresolved_fields),
        "warnings": list(report.warnings),
        "child_revision_id": child.revision_id,
        "child_revision_hash": child.revision_hash,
        "actor_id": prepared.actor.actor_id,
    }


def _child_revision(source: FmeaRevision, prepared: PreparedMigration) -> FmeaRevision:
    child_id = (
        "migration-child-"
        + sha256(
            f"{source.workspace_id}:{prepared.command.migration_id}:{source.revision_id}:"
            f"{prepared.report.report_hash}:{prepared.target_domain_pack_identity}".encode()
        ).hexdigest()[:40]
    )
    target = prepared.candidate.target_revision
    values = {field.name: getattr(target, field.name) for field in fields(target)}
    values.update({
        "revision_id": child_id,
        "parent_revision_id": source.revision_id,
        "parent_revision_hash": source.revision_hash,
        "risk_versions": (),
        "propagation_graph_revision_id": None,
        "propagation_graph_hash": None,
        "created_at": prepared.report.created_at,
    })
    provisional = object.__new__(FmeaRevision)
    for field_name, value in values.items():
        object.__setattr__(provisional, field_name, value)
    values["revision_hash"] = revision_content_hash(provisional)
    return FmeaRevision(**values)


def _report_row_is_valid(
    row: sqlite3.Row, report: MigrationReport, request_idempotency_key_hash: str | None = None
) -> bool:
    source_pack = report.source_domain_pack_identity
    target_pack = report.target_domain_pack_identity
    return (
        row["migration_id"] == report.migration_id
        and row["source_revision_id"] == report.source_revision_id
        and _digest(row["source_revision_hash"]) == _digest(report.source_revision_hash)
        and row["source_domain_pack_id"] == source_pack[0]
        and row["source_domain_pack_version"] == source_pack[1]
        and _digest(row["source_domain_pack_hash"]) == _digest(source_pack[2])
        and row["target_domain_pack_id"] == target_pack[0]
        and row["target_domain_pack_version"] == target_pack[1]
        and _digest(row["target_domain_pack_hash"]) == _digest(target_pack[2])
        and _digest(row["target_revision_hash"]) == _digest(report.target_revision_hash)
        and row["status"] == report.status.value
        and _digest(row["report_hash"]) == _digest(report.report_hash)
        and row["canonical_json_hash"] == _hash_json(_report_value(report))
        and row["plan_json"] == canonical_json(_report_plan_value(report.plan))
        and row["report_json"] == canonical_json(_report_value(report))
        and row["created_at"] == report.created_at
        and (
            request_idempotency_key_hash is None or row["request_idempotency_key_hash"] == request_idempotency_key_hash
        )
    )


def _validate_prepared_binding(prepared: PreparedMigration) -> None:
    command = prepared.command
    dry_command = prepared.dry_run_command
    source = prepared.source
    report = prepared.report
    candidate = prepared.candidate
    target_revision = candidate.target_revision
    command_fields = (
        "migration_id",
        "source_revision_id",
        "source_revision_hash",
        "target_domain_pack_id",
        "target_domain_pack_version",
        "target_domain_pack_hash",
    )
    for field_name in command_fields:
        left = getattr(command, field_name)
        right = getattr(dry_command, field_name)
        if field_name.endswith("_hash"):
            if _digest(left) != _digest(right):
                raise ValueError("prepared migration command binding is invalid")
        elif left != right:
            raise ValueError("prepared migration command binding is invalid")
    if (
        command.migration_id != report.migration_id
        or source.revision_id != command.source_revision_id
        or _digest(source.revision_hash) != _digest(command.source_revision_hash)
        or report.source_revision_id != source.revision_id
        or _digest(report.source_revision_hash) != _digest(source.revision_hash)
        or report.source_domain_pack_identity != source.domain_pack_identity
        or report.target_domain_pack_identity != prepared.target_domain_pack_identity
        or target_revision.domain_pack_identity != prepared.target_domain_pack_identity
        or target_revision.workspace_id != source.workspace_id
        or target_revision.analysis_id != source.analysis_id
        or _digest(target_revision.revision_hash) != _digest(report.target_revision_hash)
        or prepared.plan != report.plan
        or candidate.mapped_fields != report.mapped_fields
        or candidate.dropped_fields != report.dropped_fields
        or candidate.unresolved_fields != report.unresolved_fields
        or candidate.warnings != report.warnings
    ):
        raise ValueError("prepared migration durable binding is invalid")
    if _digest(revision_content_hash(target_revision)) != _digest(target_revision.revision_hash):
        raise ValueError("prepared migration target revision is invalid")


class SqliteFmeaDeliveryRepository(SqliteGovernanceRepository):
    """Governance-compatible SQLite repository with durable delivery state."""

    _MIGRATION_COMMAND = "fmea.migration.confirm"

    @staticmethod
    def _template_response(kind: str, value: object, record_version: int) -> dict[str, object]:
        return {
            "kind": kind,
            "record_version": record_version,
            "value": _json_value(value),
        }

    @classmethod
    def _template_replay(
        cls,
        connection: sqlite3.Connection,
        scope: IdempotencyScope,
        payload_hash: str,
        *,
        kind: str,
        resource_id: str,
    ) -> tuple[object, int, bool] | None:
        row = cls._idempotency_row(connection, scope)
        if row is None:
            return None
        if row["payload_hash"] != payload_hash:
            raise ApplicationReviewError(
                "FMEA_IDEMPOTENCY_CONFLICT", "idempotency key was used with a different payload"
            )
        if row["state"] != "completed":
            return None
        if row["resource_id"] != resource_id:
            raise ApplicationReviewError(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                "template workflow idempotency reservation is incomplete",
                retryable=True,
            )
        response = _load_object(row["response_json"], "template workflow response")
        if set(response) != {"kind", "record_version", "value"} or response["kind"] != kind:
            raise ValueError("persisted template workflow response is invalid")
        version = response["record_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("persisted template workflow version is invalid")
        if kind == "template_draft":
            value = _decode_draft(canonical_json(response["value"]))
        elif kind == "template_patch":
            value = _decode_template_suggestion(canonical_json(response["value"]))
            stored = connection.execute(
                "SELECT * FROM fmea_template_patch_candidates "
                "WHERE workspace_id=? AND patch_id=?",
                (scope.workspace_id, resource_id),
            ).fetchone()
            if stored is None or cls._validate_template_suggestion_row(connection, stored) != value:
                raise ValueError("persisted template patch replay binding is invalid")
        elif kind == "template_patch_decision":
            value = _decode_template_decision(canonical_json(response["value"]))
            stored = connection.execute(
                "SELECT * FROM fmea_template_patch_decisions "
                "WHERE workspace_id=? AND decision_id=?",
                (scope.workspace_id, resource_id),
            ).fetchone()
            if stored is None or cls._validate_template_decision_row(connection, stored, value) != value:
                raise ValueError("persisted template decision replay binding is invalid")
        else:
            raise ValueError("persisted template workflow response kind is invalid")
        return value, version, True

    @classmethod
    def _complete_template_idempotency(
        cls,
        connection: sqlite3.Connection,
        scope: IdempotencyScope,
        payload_hash: str,
        resource_id: str,
        response: Mapping[str, object],
        created_at: str,
    ) -> None:
        cursor = connection.execute(
            "UPDATE idempotency_records SET state='completed', status_code=201, resource_id=?, "
            "response_json=?, completed_at=? WHERE scope_key=? AND payload_hash=? AND state='reserved'",
            (resource_id, encode_review_json(response), created_at, scope.scope_key, payload_hash),
        )
        if cursor.rowcount != 1:
            raise ApplicationReviewError(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE", "template workflow idempotency completion failed", retryable=True
            )

    @staticmethod
    def _template_claim_row(
        connection: sqlite3.Connection, workspace_id: str, patch_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT workspace_id, patch_id, idempotency_scope, payload_hash, created_at, completed_at "
            "FROM fmea_template_patch_generation_claims WHERE workspace_id=? AND patch_id=?",
            (workspace_id, patch_id),
        ).fetchone()

    @staticmethod
    def _template_event_ids(scope: IdempotencyScope) -> tuple[str, str]:
        digest = sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]
        return f"template-audit-{digest}", f"template-outbox-{digest}"

    @classmethod
    def _insert_template_audit(
        cls,
        connection: sqlite3.Connection,
        *,
        scope: IdempotencyScope,
        payload_hash: str,
        patch_id: str | None,
        draft_id: str,
        suggestion_id: str | None,
        decision_id: str | None,
        action: str,
        created_at: str,
        outbox_event_id: str,
        actor_type: ActorType,
    ) -> str:
        event_id, expected_outbox_id = cls._template_event_ids(scope)
        if outbox_event_id != expected_outbox_id:
            raise ApplicationReviewError(
                "FMEA_REVIEW_STORAGE_UNAVAILABLE", "template audit and outbox identities are not bound", retryable=True
            )
        command = scope.command
        if not isinstance(actor_type, ActorType):
            raise ApplicationReviewError(
                "FMEA_REVIEW_REQUEST_INVALID", "template audit actor type is invalid"
            )
        event = {
            "event_id": event_id,
            "workspace_id": scope.workspace_id,
            "patch_id": patch_id,
            "draft_id": draft_id,
            "suggestion_id": suggestion_id,
            "decision_id": decision_id,
            "actor_id": scope.actor_id,
            "actor_type": actor_type.value,
            "command": command,
            "action": action,
            "idempotency_scope": scope.scope_key,
            "canonical_payload_hash": payload_hash,
            "outbox_event_id": outbox_event_id,
            "created_at": created_at,
        }
        event_json = canonical_json(event)
        connection.execute(
            "INSERT INTO fmea_template_audit_events "
            "(workspace_id,event_id,patch_id,draft_id,suggestion_id,decision_id,actor_id,actor_type,command,action,"
            "idempotency_scope,canonical_payload_hash,outbox_event_id,event_json,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                scope.workspace_id,
                event_id,
                patch_id,
                draft_id,
                suggestion_id,
                decision_id,
                scope.actor_id,
                actor_type.value,
                command,
                action,
                scope.scope_key,
                payload_hash,
                outbox_event_id,
                event_json,
                created_at,
            ),
        )
        return event_id

    @staticmethod
    def _insert_template_outbox(
        connection: sqlite3.Connection,
        *,
        scope: IdempotencyScope,
        event_id: str,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: Mapping[str, object],
        created_at: str,
    ) -> None:
        payload_json = canonical_json(payload)
        connection.execute(
            "INSERT INTO fmea_outbox_events "
            "(event_id,workspace_id,aggregate_type,aggregate_id,event_type,status,payload_json,payload_hash,"
            "idempotency_scope,created_at) VALUES (?,?,?, ?,?,'pending',?,?,?,?)",
            (
                event_id,
                scope.workspace_id,
                aggregate_type,
                aggregate_id,
                event_type,
                payload_json,
                outbox_payload_hash(payload),
                scope.scope_key,
                created_at,
            ),
        )

    @classmethod
    def _validate_template_event_chain(
        cls,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        patch_id: str | None,
        draft_id: str,
        suggestion_id: str | None,
        decision_id: str | None,
        action: str,
        audit_event_id: object,
        outbox_event_id: object,
    ) -> None:
        links = (audit_event_id, outbox_event_id)
        if all(value is None for value in links):
            return
        if any(value is None for value in links):
            raise ValueError("persisted template workflow event links are incomplete")
        audit = connection.execute(
            "SELECT * FROM fmea_template_audit_events WHERE workspace_id=? AND event_id=?",
            (workspace_id, audit_event_id),
        ).fetchone()
        outbox = connection.execute(
            "SELECT * FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            (workspace_id, outbox_event_id),
        ).fetchone()
        if audit is None or outbox is None:
            raise ValueError("persisted template workflow event chain is missing")
        expected_command = {
            "imported": "fmea.template.import",
            "suggested": "fmea.template.patch.suggest",
            "accepted": "fmea.template.patch.accept",
            "rejected": "fmea.template.patch.reject",
        }[action]
        expected_event_type = {
            "imported": "template.imported",
            "suggested": "template.suggested",
            "accepted": "template.accepted",
            "rejected": "template.rejected",
        }[action]
        expected_aggregate_type = "template_draft" if action == "imported" else "template_patch"
        expected_aggregate_id = draft_id if action == "imported" else patch_id
        if not all(
            (
                audit["patch_id"] == patch_id,
                audit["draft_id"] == draft_id,
                audit["suggestion_id"] == suggestion_id,
                audit["decision_id"] == decision_id,
                audit["action"] == action,
                audit["command"] == expected_command,
                audit["outbox_event_id"] == outbox_event_id,
                outbox["aggregate_type"] == expected_aggregate_type,
                outbox["aggregate_id"] == expected_aggregate_id,
                outbox["event_type"] == expected_event_type,
                outbox["status"] == "pending",
                outbox["idempotency_scope"] == audit["idempotency_scope"],
            )
        ):
            raise ValueError("persisted template workflow event chain binding is invalid")
        try:
            event = _load_object(audit["event_json"], "template audit event")
            payload = _load_object(outbox["payload_json"], "template outbox payload")
        except ValueError as exc:
            raise ValueError("persisted template workflow event JSON is invalid") from exc
        if event != {
            "event_id": audit["event_id"],
            "workspace_id": audit["workspace_id"],
            "patch_id": audit["patch_id"],
            "draft_id": audit["draft_id"],
            "suggestion_id": audit["suggestion_id"],
            "decision_id": audit["decision_id"],
            "actor_id": audit["actor_id"],
            "actor_type": audit["actor_type"],
            "command": audit["command"],
            "action": audit["action"],
            "idempotency_scope": audit["idempotency_scope"],
            "canonical_payload_hash": audit["canonical_payload_hash"],
            "outbox_event_id": audit["outbox_event_id"],
            "created_at": audit["created_at"],
        } or outbox["payload_hash"] != outbox_payload_hash(payload):
            raise ValueError("persisted template workflow event payload is invalid")

    @classmethod
    def _validate_template_suggestion_row(cls, connection: sqlite3.Connection, row: sqlite3.Row) -> TemplatePatchSuggestion:
        if row["suggestion_json"] is None:
            raise ValueError("persisted template patch suggestion envelope is missing")
        suggestion = _decode_template_suggestion(row["suggestion_json"])
        if row["suggestion_id"] is not None and row["suggestion_id"] != suggestion.suggestion_id:
            raise ValueError("persisted template patch suggestion identity is invalid")
        if (
            row["candidate_json"] != canonical_json(_json_value(suggestion.candidate))
            or row["canonical_json_hash"] != _contract_json(suggestion.candidate)[1]
            or row["record_version"] != 1
        ):
            raise ValueError("persisted template patch binding is invalid")
        cls._validate_template_event_chain(
            connection,
            workspace_id=suggestion.envelope.workspace_id,
            patch_id=suggestion.candidate.patch_id,
            draft_id=suggestion.candidate.draft_id,
            suggestion_id=suggestion.suggestion_id,
            decision_id=None,
            action="suggested",
            audit_event_id=row["audit_event_id"],
            outbox_event_id=row["outbox_event_id"],
        )
        return suggestion

    @classmethod
    def _validate_template_decision_row(
        cls, connection: sqlite3.Connection, row: sqlite3.Row, decision: TemplatePatchDecision
    ) -> TemplatePatchDecision:
        candidate_row = connection.execute(
            "SELECT suggestion_json, suggestion_id, candidate_json, canonical_json_hash, record_version, "
            "audit_event_id, outbox_event_id FROM fmea_template_patch_candidates "
            "WHERE workspace_id=? AND patch_id=?",
            (decision.workspace_id, decision.patch_id),
        ).fetchone()
        if candidate_row is None:
            raise ValueError("persisted template patch candidate is missing")
        suggestion = cls._validate_template_suggestion_row(connection, candidate_row)
        if decision.suggestion_id != suggestion.suggestion_id or decision.candidate != suggestion.candidate:
            raise ValueError("persisted template decision suggestion binding is invalid")
        if row["audit_event_id"] is not None or row["outbox_event_id"] is not None:
            cls._validate_template_event_chain(
                connection,
                workspace_id=decision.workspace_id,
                patch_id=decision.patch_id,
                draft_id=decision.candidate.draft_id,
                suggestion_id=decision.suggestion_id,
                decision_id=decision.decision_id,
                action=decision.action,
                audit_event_id=row["audit_event_id"],
                outbox_event_id=row["outbox_event_id"],
            )
        return decision

    def save_template_draft(
        self, draft: TemplateDraft, scope: IdempotencyScope, payload_hash: str, *, actor_type: ActorType
    ) -> tuple[TemplateDraft, int, bool]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._template_replay(
                connection, scope, payload_hash, kind="template_draft", resource_id=draft.draft_id
            )
            if replay is not None:
                connection.execute("COMMIT")
                return cast(tuple[TemplateDraft, int, bool], replay)
            existing = connection.execute(
                "SELECT draft_json, canonical_json_hash, record_version FROM fmea_template_drafts "
                "WHERE workspace_id=? AND draft_id=?",
                (draft.workspace_id, draft.draft_id),
            ).fetchone()
            draft_json, draft_hash = _contract_json(draft)
            if existing is None:
                connection.execute(
                    "INSERT INTO fmea_template_drafts "
                    "(workspace_id,draft_id,source_filename,source_sha256,source_type,structure_json,"
                    "proposed_fields_json,unknown_fields_json,ambiguous_fields_json,parser_warnings_json,"
                    "identified_fields_json,status,draft_json,canonical_json_hash,created_at,record_version) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
                    (
                        draft.workspace_id,
                        draft.draft_id,
                        draft.source_filename,
                        draft.source_sha256,
                        draft.source_type,
                        canonical_json(_json_value(draft.structure)),
                        canonical_json(_json_value(draft.proposed_fields)),
                        canonical_json(_json_value(draft.unknown_fields)),
                        canonical_json(_json_value(draft.ambiguous_fields)),
                        canonical_json(_json_value(draft.parser_warnings)),
                        canonical_json(_json_value(draft.identified_fields)),
                        draft.status.value,
                        draft_json,
                        draft_hash,
                        draft.created_at,
                    ),
                )
                audit_event_id, outbox_event_id = self._template_event_ids(scope)
                self._insert_template_audit(
                    connection,
                    scope=scope,
                    payload_hash=payload_hash,
                    patch_id=None,
                    draft_id=draft.draft_id,
                    suggestion_id=None,
                    decision_id=None,
                    action="imported",
                    created_at=draft.created_at,
                    outbox_event_id=outbox_event_id,
                    actor_type=actor_type,
                )
                self._insert_template_outbox(
                    connection,
                    scope=scope,
                    event_id=outbox_event_id,
                    event_type="template.imported",
                    aggregate_type="template_draft",
                    aggregate_id=draft.draft_id,
                    payload={
                        "draft_id": draft.draft_id,
                        "source_sha256": draft.source_sha256,
                        "payload_hash": payload_hash,
                    },
                    created_at=draft.created_at,
                )
            elif existing["draft_json"] != draft_json or existing["canonical_json_hash"] != draft_hash:
                raise ApplicationReviewError("FMEA_VERSION_CONFLICT", "template draft identity has different content")
            self._insert_idempotency(connection, scope, payload_hash, draft.created_at)
            response = self._template_response("template_draft", draft, 1)
            self._complete_template_idempotency(
                connection, scope, payload_hash, draft.draft_id, response, draft.created_at
            )
            connection.execute("COMMIT")
            return draft, 1, False
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_template_draft(self, draft_id: str, workspace_id: str) -> tuple[TemplateDraft, int] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT draft_json, canonical_json_hash, record_version FROM fmea_template_drafts "
                "WHERE workspace_id=? AND draft_id=?",
                (workspace_id, draft_id),
            ).fetchone()
            if row is None:
                return None
            draft = _decode_draft(row["draft_json"])
            if row["canonical_json_hash"] != _contract_json(draft)[1] or row["record_version"] != 1:
                raise ValueError("persisted template draft binding is invalid")
            return draft, 1
        finally:
            connection.close()

    def reserve_template_patch_generation(
        self,
        patch_id: str,
        scope: IdempotencyScope,
        payload_hash: str,
        *,
        created_at: str,
    ) -> TemplatePatchSuggestion | None:
        """Reserve one provider call, committing before any external work."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._template_replay(
                connection, scope, payload_hash, kind="template_patch", resource_id=patch_id
            )
            if replay is not None:
                connection.execute("COMMIT")
                return cast(TemplatePatchSuggestion, replay[0])
            existing = connection.execute(
                "SELECT * FROM fmea_template_patch_candidates WHERE workspace_id=? AND patch_id=?",
                (scope.workspace_id, patch_id),
            ).fetchone()
            if existing is not None:
                self._validate_template_suggestion_row(connection, existing)
                raise ApplicationReviewError("FMEA_VERSION_CONFLICT", "template patch identity already exists")
            idempotency = self._idempotency_row(connection, scope)
            if idempotency is not None:
                if idempotency["payload_hash"] != payload_hash:
                    raise ApplicationReviewError(
                        "FMEA_IDEMPOTENCY_CONFLICT", "idempotency key was used with a different payload"
                    )
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template patch generation reservation is incomplete",
                    retryable=True,
                )
            claim = self._template_claim_row(connection, scope.workspace_id, patch_id)
            if claim is not None:
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template patch generation is already reserved",
                    retryable=True,
                )
            self._insert_idempotency(connection, scope, payload_hash, created_at)
            connection.execute(
                "UPDATE idempotency_records SET resource_id=? WHERE scope_key=? AND state='reserved'",
                (patch_id, scope.scope_key),
            )
            connection.execute(
                "INSERT INTO fmea_template_patch_generation_claims "
                "(workspace_id,patch_id,idempotency_scope,payload_hash,created_at,completed_at) "
                "VALUES (?,?,?,?,?,NULL)",
                (scope.workspace_id, patch_id, scope.scope_key, payload_hash, created_at),
            )
            connection.execute("COMMIT")
            return None
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def replay_template_patch(
        self, patch_id: str, scope: IdempotencyScope, payload_hash: str
    ) -> TemplatePatchSuggestion | None:
        connection = self._connect()
        try:
            replay = self._template_replay(
                connection, scope, payload_hash, kind="template_patch", resource_id=patch_id
            )
            return None if replay is None else cast(TemplatePatchSuggestion, replay[0])
        finally:
            connection.close()

    def save_template_patch(
        self,
        suggestion: TemplatePatchSuggestion,
        scope: IdempotencyScope,
        payload_hash: str,
        *,
        expected_draft_version: int,
        actor_type: ActorType,
    ) -> tuple[TemplatePatchSuggestion, int, bool]:
        candidate = suggestion.candidate
        workspace_id = suggestion.envelope.workspace_id
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._template_replay(
                connection, scope, payload_hash, kind="template_patch", resource_id=candidate.patch_id
            )
            if replay is not None:
                connection.execute("COMMIT")
                return cast(tuple[TemplatePatchSuggestion, int, bool], replay)
            idempotency = self._idempotency_row(connection, scope)
            if (
                idempotency is None
                or idempotency["payload_hash"] != payload_hash
                or idempotency["state"] != "reserved"
                or idempotency["resource_id"] != candidate.patch_id
            ):
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template patch generation claim is missing or invalid",
                    retryable=True,
                )
            claim = self._template_claim_row(connection, workspace_id, candidate.patch_id)
            if (
                claim is None
                or claim["idempotency_scope"] != scope.scope_key
                or claim["payload_hash"] != payload_hash
                or claim["completed_at"] is not None
            ):
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template patch generation claim is missing or already completed",
                    retryable=True,
                )
            draft = connection.execute(
                "SELECT record_version FROM fmea_template_drafts WHERE workspace_id=? AND draft_id=?",
                (workspace_id, candidate.draft_id),
            ).fetchone()
            if draft is None or draft["record_version"] != expected_draft_version:
                raise ApplicationReviewError("FMEA_VERSION_CONFLICT", "template draft version is stale")
            if (
                connection.execute(
                    "SELECT 1 FROM fmea_template_patch_candidates WHERE workspace_id=? AND patch_id=?",
                    (workspace_id, candidate.patch_id),
                ).fetchone()
                is not None
            ):
                raise ApplicationReviewError("FMEA_VERSION_CONFLICT", "template patch identity already exists")
            candidate_json, candidate_hash = _contract_json(candidate)
            suggestion_json = canonical_json(_json_value(suggestion.envelope))
            audit_event_id, outbox_event_id = self._template_event_ids(scope)
            self._insert_template_audit(
                connection,
                scope=scope,
                payload_hash=payload_hash,
                patch_id=candidate.patch_id,
                draft_id=candidate.draft_id,
                suggestion_id=suggestion.suggestion_id,
                decision_id=None,
                action="suggested",
                created_at=candidate.created_at,
                outbox_event_id=outbox_event_id,
                actor_type=actor_type,
            )
            self._insert_template_outbox(
                connection,
                scope=scope,
                event_id=outbox_event_id,
                event_type="template.suggested",
                aggregate_type="template_patch",
                aggregate_id=candidate.patch_id,
                payload={
                    "patch_id": candidate.patch_id,
                    "draft_id": candidate.draft_id,
                    "suggestion_id": suggestion.suggestion_id,
                    "payload_hash": payload_hash,
                },
                created_at=candidate.created_at,
            )
            connection.execute(
                "INSERT INTO fmea_template_patch_candidates "
                "(workspace_id,patch_id,draft_id,input_template_version,target_template_id,"
                "target_template_version,target_template_hash,domain_pack_id,domain_pack_version,domain_pack_hash,"
                "evidence_pack_id,evidence_pack_hash,run_id,trace_id,model_version,prompt_version,diff_json,"
                "evidence_ids_json,status,applied,candidate_json,canonical_json_hash,created_at,suggestion_json,"
                "record_version,suggestion_id,audit_event_id,outbox_event_id) VALUES ("
                "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    workspace_id,
                    candidate.patch_id,
                    candidate.draft_id,
                    candidate.input_template_version,
                    candidate.target_template_id,
                    candidate.target_template_version,
                    candidate.target_template_hash,
                    candidate.domain_pack_id,
                    candidate.domain_pack_version,
                    candidate.domain_pack_hash,
                    candidate.evidence_pack_id,
                    candidate.evidence_pack_hash,
                    candidate.run_id,
                    candidate.trace_id,
                    candidate.model_version,
                    candidate.prompt_version,
                    canonical_json(_json_value(candidate.diff)),
                    canonical_json(_json_value(candidate.evidence_ids)),
                    candidate.status.value,
                    0,
                    candidate_json,
                    candidate_hash,
                    candidate.created_at,
                    suggestion_json,
                    1,
                    suggestion.suggestion_id,
                    audit_event_id,
                    outbox_event_id,
                ),
            )
            response = self._template_response("template_patch", suggestion.envelope, 1)
            self._complete_template_idempotency(
                connection, scope, payload_hash, candidate.patch_id, response, candidate.created_at
            )
            claim_update = connection.execute(
                "UPDATE fmea_template_patch_generation_claims SET completed_at=? "
                "WHERE workspace_id=? AND patch_id=? AND idempotency_scope=? "
                "AND payload_hash=? AND completed_at IS NULL",
                (candidate.created_at, workspace_id, candidate.patch_id, scope.scope_key, payload_hash),
            )
            if claim_update.rowcount != 1:
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE", "template patch generation claim completion failed", retryable=True
                )
            self._fail("template_patch_before_commit")
            connection.execute("COMMIT")
            return suggestion, 1, False
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_template_patch(
        self, patch_id: str, workspace_id: str
    ) -> tuple[TemplatePatchSuggestion | TemplatePatchDecision, int] | None:
        connection = self._connect()
        try:
            decision = connection.execute(
                "SELECT * FROM fmea_template_patch_decisions "
                "WHERE workspace_id=? AND patch_id=?",
                (workspace_id, patch_id),
            ).fetchone()
            if decision is not None:
                value = _decode_template_decision(decision["decision_json"])
                if decision["canonical_json_hash"] != _contract_json(value)[1] or decision["record_version"] != 2:
                    raise ValueError("persisted template patch decision binding is invalid")
                self._validate_template_decision_row(connection, decision, value)
                return value, 2
            row = connection.execute(
                "SELECT * "
                "FROM fmea_template_patch_candidates WHERE workspace_id=? AND patch_id=?",
                (workspace_id, patch_id),
            ).fetchone()
            if row is None:
                return None
            suggestion = self._validate_template_suggestion_row(connection, row)
            return suggestion, 1
        finally:
            connection.close()

    def reserve_template_patch_decision(
        self,
        decision: TemplatePatchDecision,
        scope: IdempotencyScope,
        payload_hash: str,
        *,
        expected_patch_version: int,
    ) -> tuple[TemplatePatchDecision, bool]:
        """Persist the human decision intent before registry side effects."""

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._template_replay(
                connection,
                scope,
                payload_hash,
                kind="template_patch_decision",
                resource_id=decision.decision_id,
            )
            if replay is not None:
                connection.execute("COMMIT")
                return cast(TemplatePatchDecision, replay[0]), True
            candidate = connection.execute(
                "SELECT * FROM fmea_template_patch_candidates WHERE workspace_id=? AND patch_id=?",
                (scope.workspace_id, decision.patch_id),
            ).fetchone()
            if candidate is None or candidate["record_version"] != expected_patch_version:
                raise ApplicationReviewError("FMEA_VERSION_CONFLICT", "template patch version is stale")
            suggestion = self._validate_template_suggestion_row(connection, candidate)
            expected_command = {
                "accepted": "fmea.template.patch.accept",
                "rejected": "fmea.template.patch.reject",
            }.get(decision.action)
            if (
                decision.workspace_id != scope.workspace_id
                or decision.actor_id != scope.actor_id
                or decision.actor_type is not ActorType.HUMAN
                or scope.command != expected_command
                or decision.suggestion_id != suggestion.suggestion_id
                or decision.candidate != suggestion.candidate
            ):
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template decision is not bound to the persisted suggestion envelope",
                    retryable=True,
                )
            final_row = connection.execute(
                "SELECT * FROM fmea_template_patch_decisions WHERE workspace_id=? AND patch_id=?",
                (scope.workspace_id, decision.patch_id),
            ).fetchone()
            if final_row is not None:
                final = _decode_template_decision(final_row["decision_json"])
                if final_row["canonical_json_hash"] != _contract_json(final)[1] or final_row["record_version"] != 2:
                    raise ValueError("persisted template patch decision binding is invalid")
                self._validate_template_decision_row(connection, final_row, final)
                if (
                    final.action != decision.action
                    or final.new_template_version != decision.new_template_version
                    or final.suggestion_id != decision.suggestion_id
                ):
                    raise ApplicationReviewError("FMEA_VERSION_CONFLICT", "template patch was already decided")
                raise ApplicationReviewError("FMEA_VERSION_CONFLICT", "template patch was already decided")
            idempotency = self._idempotency_row(connection, scope)
            if idempotency is not None:
                if idempotency["payload_hash"] != payload_hash:
                    raise ApplicationReviewError(
                        "FMEA_IDEMPOTENCY_CONFLICT", "idempotency key was used with a different payload"
                    )
                if idempotency["state"] != "reserved":
                    raise ApplicationReviewError(
                        "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                        "template decision replay is incomplete",
                        retryable=True,
                    )
            intent = connection.execute(
                "SELECT * FROM fmea_template_patch_decision_intents WHERE workspace_id=? AND patch_id=?",
                (scope.workspace_id, decision.patch_id),
            ).fetchone()
            decision_json, decision_hash = _contract_json(decision)
            if intent is not None:
                if (
                    intent["idempotency_scope"] != scope.scope_key
                    or intent["payload_hash"] != payload_hash
                    or intent["decision_id"] != decision.decision_id
                    or intent["suggestion_id"] != decision.suggestion_id
                    or intent["action"] != decision.action
                ):
                    raise ApplicationReviewError(
                        "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                        "another template decision intent is already reserved",
                        retryable=True,
                    )
                if intent["state"] != "reserved":
                    raise ApplicationReviewError(
                        "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                        "template decision intent completion is incomplete",
                        retryable=True,
                    )
                if (
                    intent["decision_json"] != decision_json
                    or intent["canonical_json_hash"] != decision_hash
                ):
                    raise ApplicationReviewError(
                        "FMEA_IDEMPOTENCY_CONFLICT", "idempotency key was used with a different decision"
                    )
                stored = _decode_template_decision(intent["decision_json"])
                if stored != decision:
                    raise ValueError("persisted template decision intent binding is invalid")
                if idempotency is None:
                    raise ApplicationReviewError(
                        "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                        "template decision intent has no idempotency reservation",
                        retryable=True,
                    )
                connection.execute("COMMIT")
                return stored, False
            if idempotency is not None:
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template decision idempotency reservation has no intent",
                    retryable=True,
                )
            self._insert_idempotency(connection, scope, payload_hash, decision.created_at)
            connection.execute(
                "UPDATE idempotency_records SET resource_id=? WHERE scope_key=? AND state='reserved'",
                (decision.decision_id, scope.scope_key),
            )
            connection.execute(
                "INSERT INTO fmea_template_patch_decision_intents "
                "(workspace_id,patch_id,decision_id,suggestion_id,action,idempotency_scope,payload_hash,"
                "decision_json,canonical_json_hash,state,created_at,completed_at) VALUES (?,?,?,?,?,?,?,?,?,'reserved',?,NULL)",
                (
                    scope.workspace_id,
                    decision.patch_id,
                    decision.decision_id,
                    decision.suggestion_id,
                    decision.action,
                    scope.scope_key,
                    payload_hash,
                    decision_json,
                    decision_hash,
                    decision.created_at,
                ),
            )
            connection.execute("COMMIT")
            return decision, False
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def save_template_patch_decision(
        self,
        decision: TemplatePatchDecision,
        scope: IdempotencyScope,
        payload_hash: str,
        *,
        expected_patch_version: int,
    ) -> tuple[TemplatePatchDecision, int, bool]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._template_replay(
                connection,
                scope,
                payload_hash,
                kind="template_patch_decision",
                resource_id=decision.decision_id,
            )
            if replay is not None:
                connection.execute("COMMIT")
                return cast(tuple[TemplatePatchDecision, int, bool], replay)
            idempotency = self._idempotency_row(connection, scope)
            if (
                idempotency is None
                or idempotency["payload_hash"] != payload_hash
                or idempotency["state"] != "reserved"
                or idempotency["resource_id"] != decision.decision_id
            ):
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template decision intent reservation is missing or invalid",
                    retryable=True,
                )
            intent = connection.execute(
                "SELECT * FROM fmea_template_patch_decision_intents "
                "WHERE workspace_id=? AND patch_id=?",
                (decision.workspace_id, decision.patch_id),
            ).fetchone()
            decision_json, decision_hash = _contract_json(decision)
            if (
                intent is None
                or intent["idempotency_scope"] != scope.scope_key
                or intent["payload_hash"] != payload_hash
                or intent["decision_id"] != decision.decision_id
                or intent["state"] != "reserved"
                or intent["decision_json"] != decision_json
                or intent["canonical_json_hash"] != decision_hash
            ):
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template decision intent is missing or invalid",
                    retryable=True,
                )
            candidate = connection.execute(
                "SELECT * FROM fmea_template_patch_candidates "
                "WHERE workspace_id=? AND patch_id=?",
                (decision.workspace_id, decision.patch_id),
            ).fetchone()
            if candidate is None or candidate["record_version"] != expected_patch_version:
                raise ApplicationReviewError("FMEA_VERSION_CONFLICT", "template patch version is stale")
            suggestion = self._validate_template_suggestion_row(connection, candidate)
            if decision.suggestion_id != suggestion.suggestion_id or decision.candidate != suggestion.candidate:
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                    "template decision is not bound to the persisted suggestion envelope",
                    retryable=True,
                )
            if (
                connection.execute(
                    "SELECT 1 FROM fmea_template_patch_decisions WHERE workspace_id=? AND patch_id=?",
                    (decision.workspace_id, decision.patch_id),
                ).fetchone()
                is not None
            ):
                raise ApplicationReviewError("FMEA_VERSION_CONFLICT", "template patch was already decided")
            audit_event_id, outbox_event_id = self._template_event_ids(scope)
            self._insert_template_audit(
                connection,
                scope=scope,
                payload_hash=payload_hash,
                patch_id=decision.patch_id,
                draft_id=candidate["draft_id"],
                suggestion_id=decision.suggestion_id,
                decision_id=decision.decision_id,
                action=decision.action,
                created_at=decision.created_at,
                outbox_event_id=outbox_event_id,
                actor_type=decision.actor_type,
            )
            self._insert_template_outbox(
                connection,
                scope=scope,
                event_id=outbox_event_id,
                event_type=f"template.{decision.action}",
                aggregate_type="template_patch",
                aggregate_id=decision.patch_id,
                payload={
                    "patch_id": decision.patch_id,
                    "draft_id": candidate["draft_id"],
                    "suggestion_id": decision.suggestion_id,
                    "decision_id": decision.decision_id,
                    "action": decision.action,
                    "payload_hash": payload_hash,
                },
                created_at=decision.created_at,
            )
            connection.execute(
                "INSERT INTO fmea_template_patch_decisions "
                "(workspace_id,decision_id,suggestion_id,patch_id,draft_id,actor_id,actor_type,action,reason,"
                "base_template_id,base_template_version,base_template_hash,new_template_version,candidate_json,"
                "decision_json,canonical_json_hash,created_at,record_version,audit_event_id,outbox_event_id) "
                "VALUES (" + ",".join("?" for _ in range(20)) + ")",
                (
                    decision.workspace_id,
                    decision.decision_id,
                    decision.suggestion_id,
                    decision.patch_id,
                    candidate["draft_id"],
                    decision.actor_id,
                    decision.actor_type.value,
                    decision.action,
                    decision.reason,
                    decision.base_template_id,
                    decision.base_template_version,
                    decision.base_template_hash,
                    decision.new_template_version,
                    canonical_json(_json_value(decision.candidate)),
                    decision_json,
                    decision_hash,
                    decision.created_at,
                    2,
                    audit_event_id,
                    outbox_event_id,
                ),
            )
            response = self._template_response("template_patch_decision", decision, 2)
            self._complete_template_idempotency(
                connection, scope, payload_hash, decision.decision_id, response, decision.created_at
            )
            intent_update = connection.execute(
                "UPDATE fmea_template_patch_decision_intents SET state='completed', completed_at=? "
                "WHERE workspace_id=? AND patch_id=? AND decision_id=? AND idempotency_scope=? "
                "AND payload_hash=? AND state='reserved'",
                (
                    decision.created_at,
                    decision.workspace_id,
                    decision.patch_id,
                    decision.decision_id,
                    scope.scope_key,
                    payload_hash,
                ),
            )
            if intent_update.rowcount != 1:
                raise ApplicationReviewError(
                    "FMEA_REVIEW_STORAGE_UNAVAILABLE", "template decision intent completion failed", retryable=True
                )
            self._fail("template_decision_before_commit")
            connection.execute("COMMIT")
            return decision, 2, False
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _migration_scope(self, command: ConfirmMigrationCommand, actor: ActorContext) -> IdempotencyScope:
        return IdempotencyScope(
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            command=self._MIGRATION_COMMAND,
            resource_path=f"/fmea/migrations/{command.migration_id}/confirmations",
            key_hash=idempotency_key_hash(command.idempotency_key),
        )

    @staticmethod
    def _report_id(workspace_id: str, migration_id: str) -> str:
        return migration_report_id(workspace_id, migration_id)

    @staticmethod
    def _run_id(workspace_id: str, migration_id: str) -> str:
        return "migration-run-" + sha256(f"{workspace_id}:{migration_id}".encode()).hexdigest()[:40]

    @staticmethod
    def _confirmation_id(scope: IdempotencyScope) -> str:
        return "migration-confirmation-" + sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]

    def _durable_run_command(
        self,
        row: sqlite3.Row | None,
        *,
        workspace_id: str,
        migration_id: str,
        actor_id: str | None = None,
    ) -> tuple[MigrationCommand, str]:
        if row is None:
            raise ValueError("persisted migration run is missing")
        request = _load_object(row["request_json"], "migration request")
        command_keys = {field.name for field in fields(MigrationCommand)}
        expected_keys = command_keys | {"actor_id", "workspace_id"}
        legacy_keys = (command_keys - {"expected_source_version"}) | {"actor_id", "workspace_id"}
        if set(request) not in (expected_keys, legacy_keys):
            raise ValueError("persisted migration request shape is invalid")
        legacy_request = set(request) == legacy_keys
        try:
            durable_command = MigrationCommand(
                migration_id=cast(str, request["migration_id"]),
                source_revision_id=cast(str, request["source_revision_id"]),
                source_revision_hash=cast(str, request["source_revision_hash"]),
                target_domain_pack_id=cast(str, request["target_domain_pack_id"]),
                target_domain_pack_version=cast(str, request["target_domain_pack_version"]),
                target_domain_pack_hash=cast(str, request["target_domain_pack_hash"]),
                idempotency_key=cast(str, request["idempotency_key"]),
                expected_source_version=cast(int, request.get("expected_source_version", 1)),
            )
            durable_actor_id = _text(row["actor_id"], "persisted actor_id")
            durable_key_hash = idempotency_key_hash(durable_command.idempotency_key)
        except Exception:
            raise ValueError("persisted migration request is invalid") from None
        expected_request = _request_value(durable_command) | {
            "actor_id": durable_actor_id,
            "workspace_id": workspace_id,
        }
        if legacy_request:
            expected_request.pop("expected_source_version")
        if (
            row["workspace_id"] != workspace_id
            or row["migration_id"] != migration_id
            or row["run_id"] != self._run_id(workspace_id, migration_id)
            or row["source_revision_id"] != durable_command.source_revision_id
            or row["source_revision_hash"] != durable_command.source_revision_hash
            or row["target_domain_pack_id"] != durable_command.target_domain_pack_id
            or row["target_domain_pack_version"] != durable_command.target_domain_pack_version
            or row["target_domain_pack_hash"] != durable_command.target_domain_pack_hash
            or row["actor_id"] != durable_actor_id
            or (actor_id is not None and durable_actor_id != actor_id)
            or request != expected_request
            or row["request_hash"] != _hash_json(request)
            or row["request_idempotency_key_hash"] != durable_key_hash
        ):
            raise ValueError("persisted migration request binding is invalid")
        return durable_command, durable_key_hash

    @staticmethod
    def _assert_migration_source_version(
        connection: sqlite3.Connection, command: MigrationCommand, workspace_id: str
    ) -> None:
        row = connection.execute(
            "SELECT record_version FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            (workspace_id, command.source_revision_id),
        ).fetchone()
        if row is None:
            raise ReviewError("FMEA_MIGRATION_SOURCE_MISSING", "source revision was not found")
        record_version = row["record_version"]
        if isinstance(record_version, bool) or not isinstance(record_version, int) or record_version < 1:
            raise ReviewError(
                "FMEA_MIGRATION_STORAGE_UNAVAILABLE",
                "source revision version is unavailable",
                retryable=True,
            )
        if record_version != command.expected_source_version:
            raise ReviewError("FMEA_VERSION_CONFLICT", "source revision version is stale")

    def _validated_report_row(self, connection: sqlite3.Connection, prepared: PreparedMigration) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM fmea_migration_reports WHERE workspace_id=? AND migration_id=?",
            (prepared.actor.workspace_id, prepared.command.migration_id),
        ).fetchone()
        if row is None or row["report_id"] != self._report_id(
            prepared.actor.workspace_id, prepared.command.migration_id
        ):
            raise ReviewError("FMEA_MIGRATION_REPORT_MISSING", "a stored dry-run report is required")
        report = _decode_report(row["report_json"], row["report_hash"])
        if report != prepared.report or not _report_row_is_valid(row, report):
            raise ReviewError("FMEA_MIGRATION_REPORT_STALE", "stored migration report is stale")
        return row

    def _validate_run_row(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row | None,
        prepared: PreparedMigration,
        *,
        status: str,
        child: FmeaRevision | None = None,
        scope: IdempotencyScope | None = None,
    ) -> str:
        durable_command, durable_key_hash = self._durable_run_command(
            row,
            workspace_id=prepared.actor.workspace_id,
            migration_id=prepared.command.migration_id,
            actor_id=prepared.actor.actor_id,
        )
        row = cast(sqlite3.Row, row)
        command = prepared.command
        report = prepared.report
        source_pack = report.source_domain_pack_identity
        target_pack = report.target_domain_pack_identity
        if durable_command != prepared.dry_run_command:
            raise ValueError("persisted migration request binding is invalid")
        report_key = connection.execute(
            "SELECT request_idempotency_key_hash FROM fmea_migration_reports WHERE workspace_id=? AND migration_id=?",
            (prepared.actor.workspace_id, prepared.command.migration_id),
        ).fetchone()
        if (
            row["workspace_id"] != prepared.actor.workspace_id
            or row["migration_id"] != command.migration_id
            or row["run_id"] != self._run_id(prepared.actor.workspace_id, command.migration_id)
            or row["source_revision_id"] != command.source_revision_id
            or _digest(row["source_revision_hash"]) != _digest(command.source_revision_hash)
            or row["source_domain_pack_id"] != source_pack[0]
            or row["source_domain_pack_version"] != source_pack[1]
            or _digest(row["source_domain_pack_hash"]) != _digest(source_pack[2])
            or row["target_domain_pack_id"] != target_pack[0]
            or row["target_domain_pack_version"] != target_pack[1]
            or _digest(row["target_domain_pack_hash"]) != _digest(target_pack[2])
            or _digest(row["target_revision_hash"]) != _digest(report.target_revision_hash)
            or row["status"] != status
            or report_key is None
            or report_key["request_idempotency_key_hash"] != durable_key_hash
            or row["report_id"] != self._report_id(prepared.actor.workspace_id, command.migration_id)
            or _digest(row["report_hash"]) != _digest(report.report_hash)
            or row["actor_id"] != prepared.actor.actor_id
            or row["created_at"] != report.created_at
            or row["started_at"] != report.created_at
        ):
            raise ValueError("persisted migration run binding is invalid")
        if status == "dry_run":
            if (
                row["child_revision_id"] is not None
                or row["idempotency_scope"] is not None
                or row["finished_at"] is not None
            ):
                raise ValueError("persisted dry-run state is invalid")
        elif (
            child is None
            or scope is None
            or row["child_revision_id"] != child.revision_id
            or row["idempotency_scope"] != scope.scope_key
            or row["finished_at"] != report.created_at
        ):
            raise ValueError("persisted confirmed run state is invalid")
        return durable_key_hash

    def _ensure_migration_run(
        self,
        connection: sqlite3.Connection,
        report: MigrationReport,
        command: MigrationCommand,
        actor: ActorContext,
    ) -> tuple[str, str, str]:
        request = _request_value(command) | {"actor_id": actor.actor_id, "workspace_id": actor.workspace_id}
        request_json = canonical_json(request)
        request_hash = _hash_json(request)
        request_key_hash = idempotency_key_hash(command.idempotency_key)
        run_id = self._run_id(actor.workspace_id, command.migration_id)
        report_id = self._report_id(actor.workspace_id, command.migration_id)
        row = connection.execute(
            "SELECT run_id,request_json,request_hash,request_idempotency_key_hash,"
            "source_revision_id,source_revision_hash,"
            "source_domain_pack_id,source_domain_pack_version,source_domain_pack_hash,target_domain_pack_id,"
            "target_domain_pack_version,target_domain_pack_hash,target_revision_hash,actor_id,report_id,"
            "report_hash,status "
            "FROM fmea_migration_runs WHERE workspace_id=? AND migration_id=?",
            (actor.workspace_id, command.migration_id),
        ).fetchone()
        if row is not None:
            if (
                row["run_id"] != run_id
                or row["request_json"] != request_json
                or row["request_hash"] != request_hash
                or row["request_idempotency_key_hash"] != request_key_hash
                or row["source_revision_id"] != command.source_revision_id
                or _digest(row["source_revision_hash"]) != _digest(command.source_revision_hash)
                or row["source_domain_pack_id"] != report.source_domain_pack_identity[0]
                or row["source_domain_pack_version"] != report.source_domain_pack_identity[1]
                or _digest(row["source_domain_pack_hash"]) != _digest(report.source_domain_pack_identity[2])
                or row["target_domain_pack_id"] != command.target_domain_pack_id
                or row["target_domain_pack_version"] != command.target_domain_pack_version
                or _digest(row["target_domain_pack_hash"]) != _digest(command.target_domain_pack_hash)
                or _digest(row["target_revision_hash"]) != _digest(report.target_revision_hash)
                or row["actor_id"] != actor.actor_id
                or row["report_id"] != report_id
                or _digest(row["report_hash"] or "") != _digest(report.report_hash)
            ):
                raise ReviewError("FMEA_MIGRATION_IDEMPOTENCY_CONFLICT", "migration identity is already bound")
            if row["status"] == "confirmed":
                raise ReviewError("FMEA_MIGRATION_IDEMPOTENCY_CONFLICT", "migration is already confirmed")
            return run_id, report_id, request_hash
        connection.execute(
            "INSERT INTO fmea_migration_runs "
            "(workspace_id,migration_id,run_id,source_revision_id,source_revision_hash,"
            "source_domain_pack_id,source_domain_pack_version,source_domain_pack_hash,target_domain_pack_id,"
            "target_domain_pack_version,target_domain_pack_hash,target_revision_hash,status,request_json,"
            "request_hash,request_idempotency_key_hash,report_id,report_hash,actor_id,created_at,started_at,finished_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
            (
                actor.workspace_id,
                command.migration_id,
                run_id,
                command.source_revision_id,
                command.source_revision_hash,
                report.source_domain_pack_identity[0],
                report.source_domain_pack_identity[1],
                report.source_domain_pack_identity[2],
                command.target_domain_pack_id,
                command.target_domain_pack_version,
                command.target_domain_pack_hash,
                report.target_revision_hash,
                "dry_run",
                request_json,
                request_hash,
                request_key_hash,
                report_id,
                report.report_hash,
                actor.actor_id,
                report.created_at,
                report.created_at,
            ),
        )
        return run_id, report_id, request_hash

    def save_migration_report(
        self, report: MigrationReport, *, command: MigrationCommand, actor: ActorContext
    ) -> MigrationReport:
        if (
            not isinstance(report, MigrationReport)
            or not isinstance(command, MigrationCommand)
            or not isinstance(actor, ActorContext)
        ):
            raise ReviewError("FMEA_MIGRATION_REQUEST_INVALID", "migration report persistence request is invalid")
        if actor.actor_type is not ActorType.HUMAN or actor.workspace_id == "":
            raise ReviewError("FMEA_MIGRATION_FORBIDDEN", "migration report actor is not authorized")
        if (
            report.status is not MigrationReportStatus.DRY_RUN
            or report.migration_id != command.migration_id
            or report.source_revision_id != command.source_revision_id
            or _digest(report.source_revision_hash) != _digest(command.source_revision_hash)
            or report.plan.source != report.source_domain_pack_identity[:2]
            or report.plan.target != (command.target_domain_pack_id, command.target_domain_pack_version)
            or report.target_domain_pack_identity[:2]
            != (command.target_domain_pack_id, command.target_domain_pack_version)
            or _digest(report.target_domain_pack_identity[2]) != _digest(command.target_domain_pack_hash)
        ):
            raise ReviewError("FMEA_MIGRATION_REPORT_INVALID", "migration report identity is invalid")
        report_json = canonical_json(_report_value(report))
        canonical_hash = _hash_json(_report_value(report))
        request_key_hash = idempotency_key_hash(command.idempotency_key)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM fmea_migration_reports WHERE workspace_id=? AND migration_id=?",
                (actor.workspace_id, command.migration_id),
            ).fetchone()
            if existing is None:
                self._assert_migration_source_version(connection, command, actor.workspace_id)
            _, report_id, _ = self._ensure_migration_run(connection, report, command, actor)
            existing = connection.execute(
                "SELECT * FROM fmea_migration_reports WHERE workspace_id=? AND migration_id=?",
                (actor.workspace_id, command.migration_id),
            ).fetchone()
            if existing is not None:
                stored = _decode_report(existing["report_json"], existing["report_hash"])
                if (
                    stored != report
                    or not _report_row_is_valid(existing, stored, request_key_hash)
                    or existing["canonical_json_hash"] != canonical_hash
                ):
                    raise ReviewError("FMEA_MIGRATION_IDEMPOTENCY_CONFLICT", "migration report is already bound")
                connection.execute("COMMIT")
                return stored
            connection.execute(
                "INSERT INTO fmea_migration_reports "
                "(workspace_id,report_id,migration_id,source_revision_id,source_revision_hash,"
                "source_domain_pack_id,source_domain_pack_version,source_domain_pack_hash,target_domain_pack_id,"
                "target_domain_pack_version,target_domain_pack_hash,target_revision_hash,status,plan_json,"
                "report_json,report_hash,request_idempotency_key_hash,canonical_json_hash,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    actor.workspace_id,
                    report_id,
                    command.migration_id,
                    command.source_revision_id,
                    command.source_revision_hash,
                    report.source_domain_pack_identity[0],
                    report.source_domain_pack_identity[1],
                    report.source_domain_pack_identity[2],
                    command.target_domain_pack_id,
                    command.target_domain_pack_version,
                    command.target_domain_pack_hash,
                    report.target_revision_hash,
                    report.status.value,
                    canonical_json(_report_plan_value(report.plan)),
                    report_json,
                    report.report_hash,
                    request_key_hash,
                    canonical_hash,
                    report.created_at,
                ),
            )
            connection.execute("COMMIT")
            return report
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise ReviewError("FMEA_MIGRATION_STORAGE_UNAVAILABLE", "migration report storage is unavailable") from None
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise ReviewError("FMEA_MIGRATION_STORAGE_UNAVAILABLE", "migration report storage is unavailable") from None
        finally:
            connection.close()

    def get_migration_report(
        self,
        migration_id: str,
        workspace_id: str,
        *,
        command: MigrationCommand,
    ) -> MigrationReport | None:
        connection = self._connect()
        try:
            workspace_id = _text(workspace_id, "workspace_id")
            migration_id = _text(migration_id, "migration_id")
            if not isinstance(command, MigrationCommand):
                raise ValueError("migration report request is invalid")
            row = connection.execute(
                "SELECT * FROM fmea_migration_reports WHERE workspace_id=? AND migration_id=?",
                (workspace_id, migration_id),
            ).fetchone()
            if row is None:
                return None
            run = connection.execute(
                "SELECT * FROM fmea_migration_runs WHERE workspace_id=? AND migration_id=?",
                (workspace_id, migration_id),
            ).fetchone()
            durable_command, durable_key_hash = self._durable_run_command(
                run,
                workspace_id=workspace_id,
                migration_id=migration_id,
            )
            run = cast(sqlite3.Row, run)
            report = _decode_report(row["report_json"], row["report_hash"])
            if (
                not _report_row_is_valid(row, report, durable_key_hash)
                or run["report_id"] != row["report_id"]
                or _digest(run["report_hash"]) != _digest(report.report_hash)
                or run["source_revision_id"] != report.source_revision_id
                or _digest(run["source_revision_hash"]) != _digest(report.source_revision_hash)
                or run["source_domain_pack_id"] != report.source_domain_pack_identity[0]
                or run["source_domain_pack_version"] != report.source_domain_pack_identity[1]
                or _digest(run["source_domain_pack_hash"]) != _digest(report.source_domain_pack_identity[2])
                or run["target_domain_pack_id"] != report.target_domain_pack_identity[0]
                or run["target_domain_pack_version"] != report.target_domain_pack_identity[1]
                or _digest(run["target_domain_pack_hash"]) != _digest(report.target_domain_pack_identity[2])
                or _digest(run["target_revision_hash"]) != _digest(report.target_revision_hash)
                or run["created_at"] != report.created_at
                or run["started_at"] != report.created_at
            ):
                raise ValueError("persisted migration report binding is invalid")
            if run["status"] == "dry_run":
                if (
                    run["child_revision_id"] is not None
                    or run["idempotency_scope"] is not None
                    or run["finished_at"] is not None
                ):
                    raise ValueError("persisted dry-run state is invalid")
            elif run["status"] == "confirmed":
                if (
                    run["child_revision_id"] is None
                    or run["idempotency_scope"] is None
                    or run["finished_at"] != report.created_at
                ):
                    raise ValueError("persisted confirmed run state is invalid")
            else:
                raise ValueError("persisted migration run state is invalid")
            if durable_command != command:
                raise MigrationReportRequestConflict("stored migration report is bound to another request")
            return report
        except MigrationReportRequestConflict:
            raise
        except ReviewError:
            raise
        except Exception:
            raise ReviewError("FMEA_MIGRATION_STORAGE_UNAVAILABLE", "migration report storage is unavailable") from None
        finally:
            connection.close()

    def _verify_migration_replay(
        self,
        connection: sqlite3.Connection,
        prepared: PreparedMigration,
        child: FmeaRevision,
        scope: IdempotencyScope,
        payload_hash: str,
        result: MigrationResult,
    ) -> None:
        _validate_prepared_binding(prepared)
        self._validated_report_row(connection, prepared)
        run = connection.execute(
            "SELECT * FROM fmea_migration_runs WHERE workspace_id=? AND migration_id=?",
            (prepared.actor.workspace_id, prepared.command.migration_id),
        ).fetchone()
        dry_run_key_hash = self._validate_run_row(
            connection, run, prepared, status="confirmed", child=child, scope=scope
        )
        confirmation = connection.execute(
            "SELECT * FROM fmea_migration_confirmations WHERE workspace_id=? AND idempotency_scope=?",
            (prepared.actor.workspace_id, scope.scope_key),
        ).fetchone()
        expected_audit_id = "migration-audit-" + sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]
        expected_outbox_id = "migration-outbox-" + sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]
        expected_confirmation_id = self._confirmation_id(scope)
        expected_payload = _migration_payload(prepared, child, dry_run_key_hash)
        if confirmation is None or confirmation["confirmation_id"] != expected_confirmation_id:
            raise ValueError("persisted migration confirmation is missing")
        if (
            confirmation["migration_id"] != prepared.command.migration_id
            or confirmation["report_id"] != self._report_id(prepared.actor.workspace_id, prepared.command.migration_id)
            or confirmation["report_hash"] != prepared.report.report_hash
            or confirmation["source_revision_id"] != prepared.source.revision_id
            or _digest(confirmation["source_revision_hash"]) != _digest(prepared.source.revision_hash)
            or confirmation["source_domain_pack_id"] != prepared.report.source_domain_pack_identity[0]
            or confirmation["source_domain_pack_version"] != prepared.report.source_domain_pack_identity[1]
            or _digest(confirmation["source_domain_pack_hash"])
            != _digest(prepared.report.source_domain_pack_identity[2])
            or confirmation["target_domain_pack_id"] != child.domain_pack_identity[0]
            or confirmation["target_domain_pack_version"] != child.domain_pack_identity[1]
            or _digest(confirmation["target_domain_pack_hash"]) != _digest(child.domain_pack_identity[2])
            or _digest(confirmation["target_revision_hash"]) != _digest(prepared.report.target_revision_hash)
            or confirmation["child_revision_id"] != child.revision_id
            or confirmation["actor_id"] != prepared.actor.actor_id
            or confirmation["actor_type"] != prepared.actor.actor_type.value
            or confirmation["idempotency_scope"] != scope.scope_key
            or confirmation["payload_hash"] != payload_hash
            or confirmation["confirmation_json"] != canonical_json(expected_payload)
            or confirmation["canonical_json_hash"] != _hash_json(expected_payload)
            or confirmation["audit_event_id"] != expected_audit_id
            or confirmation["outbox_event_id"] != expected_outbox_id
            or confirmation["created_at"] != prepared.report.created_at
        ):
            raise ValueError("persisted migration confirmation binding is invalid")
        child_row = connection.execute(
            "SELECT * FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            (prepared.actor.workspace_id, child.revision_id),
        ).fetchone()
        if (
            child_row is None
            or child_row["audit_event_id"] != expected_audit_id
            or child_row["outbox_event_id"] != expected_outbox_id
            or child_row["idempotency_scope"] != scope.scope_key
            or child_row["payload_hash"] != payload_hash
            or child_row["created_at"] != child.created_at
            or child_row["created_at"] != prepared.report.created_at
        ):
            raise ValueError("persisted migration child authority binding is invalid")
        revision = self._revision_from_connection(connection, child.revision_id, prepared.actor.workspace_id)
        if revision != child or revision.created_at != child_row["created_at"]:
            raise ValueError("persisted migration child is not canonical")
        idempotency = self._idempotency_row(connection, scope)
        if (
            idempotency is None
            or idempotency["payload_hash"] != payload_hash
            or idempotency["resource_id"] != child.revision_id
        ):
            raise ValueError("persisted migration idempotency binding is invalid")
        audit_row = connection.execute(
            "SELECT * FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            (prepared.actor.workspace_id, confirmation["audit_event_id"]),
        ).fetchone()
        if audit_row is None:
            raise ValueError("persisted migration audit binding is invalid")
        audit = decode_audit_event(audit_row["event_json"])
        if (
            audit_row["workspace_id"] != prepared.actor.workspace_id
            or audit_row["resource_type"] != "revision"
            or audit_row["resource_id"] != child.revision_id
            or audit_row["actor_id"] != prepared.actor.actor_id
            or audit_row["actor_type"] != prepared.actor.actor_type.value
            or audit_row["command"] != self._MIGRATION_COMMAND
            or audit_row["idempotency_scope"] != scope.scope_key
            or audit_row["canonical_payload_hash"] != payload_hash
            or audit_row["created_at"] != audit.occurred_at_server
            or audit_row["created_at"] != prepared.report.created_at
            or audit.workspace_id != prepared.actor.workspace_id
            or audit.event_id != expected_audit_id
            or audit.row_id != child.revision_id
            or audit.command != self._MIGRATION_COMMAND
            or audit.actor_id != prepared.actor.actor_id
            or audit.idempotency_key_hash != scope.key_hash
            or audit.canonical_payload_hash != payload_hash
        ):
            raise ValueError("persisted migration audit binding is invalid")
        if canonical_json(_json_value(audit)) != audit_row["event_json"]:
            raise ValueError("persisted migration audit is not canonical")
        outbox_row = connection.execute(
            "SELECT * FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            (prepared.actor.workspace_id, confirmation["outbox_event_id"]),
        ).fetchone()
        if outbox_row is None:
            raise ValueError("persisted migration outbox binding is invalid")
        outbox_payload = load_strict_json(outbox_row["payload_json"], "migration outbox")
        if (
            canonical_json(outbox_payload) != outbox_row["payload_json"]
            or outbox_payload != expected_payload
            or outbox_row["workspace_id"] != prepared.actor.workspace_id
            or outbox_row["aggregate_type"] != "fmea_governance"
            or outbox_row["aggregate_id"] != child.revision_id
            or outbox_row["event_type"] != "migration.completed"
            or outbox_row["payload_hash"] != payload_hash
            or outbox_row["payload_hash"] != outbox_payload_hash(outbox_payload)
            or outbox_row["idempotency_scope"] != scope.scope_key
            or outbox_row["created_at"] != prepared.report.created_at
        ):
            raise ValueError("persisted migration outbox binding is invalid")
        self._verify_event_binding(
            connection,
            "revision",
            prepared.actor.workspace_id,
            child.revision_id,
            expected_audit_id,
            expected_outbox_id,
        )
        response = _load_object(idempotency["response_json"], "migration response")
        expected = {
            "migration_id": result.migration_id,
            "child_revision_id": result.child_revision_id,
            "report_hash": result.report_hash,
            "replayed": False,
        }
        if response != expected:
            raise ValueError("persisted migration response is invalid")

    def commit_migration(self, prepared: PreparedMigration) -> MigrationResult:
        if not isinstance(prepared, PreparedMigration):
            raise ReviewError("FMEA_MIGRATION_REQUEST_INVALID", "prepared migration is invalid")
        source = prepared.source
        if source.workspace_id != prepared.actor.workspace_id:
            raise ReviewError("FMEA_MIGRATION_SOURCE_MISSING", "source revision was not found")
        try:
            _validate_prepared_binding(prepared)
            child = _child_revision(source, prepared)
        except Exception:
            raise ReviewError(
                "FMEA_MIGRATION_FAILED", "confirmed migration could not be committed", retryable=True
            ) from None
        scope = self._migration_scope(prepared.command, prepared.actor)
        result = MigrationResult(prepared.command.migration_id, child.revision_id, prepared.report.report_hash)
        report_id = self._report_id(prepared.actor.workspace_id, prepared.command.migration_id)
        run_id = self._run_id(prepared.actor.workspace_id, prepared.command.migration_id)
        confirmation_id = self._confirmation_id(scope)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validated_report_row(connection, prepared)
            self._assert_migration_source_version(
                connection, prepared.dry_run_command, prepared.actor.workspace_id
            )
            if prepared.command.expected_report_version != 1:
                raise ReviewError("FMEA_VERSION_CONFLICT", "migration report version is stale")

            persisted_source = self._revision_from_connection(
                connection, source.revision_id, prepared.actor.workspace_id
            )
            record_row = connection.execute(
                "SELECT record_version FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
                (prepared.actor.workspace_id, source.revision_id),
            ).fetchone()
            if (
                persisted_source != source
                or record_row is None
                or int(record_row["record_version"]) != prepared.source_record_version
                or _digest(source.revision_hash) != _digest(prepared.command.source_revision_hash)
            ):
                raise ReviewError("FMEA_MIGRATION_SOURCE_STALE", "source revision is stale")

            run_row = connection.execute(
                "SELECT * FROM fmea_migration_runs WHERE workspace_id=? AND migration_id=?",
                (prepared.actor.workspace_id, prepared.command.migration_id),
            ).fetchone()
            existing_idempotency = self._idempotency_row(connection, scope)
            if existing_idempotency is None:
                dry_run_key_hash = self._validate_run_row(connection, run_row, prepared, status="dry_run")
            else:
                dry_run_key_hash = self._validate_run_row(
                    connection,
                    run_row,
                    prepared,
                    status="confirmed",
                    child=child,
                    scope=scope,
                )
            payload = _migration_payload(prepared, child, dry_run_key_hash)
            payload_hash = _hash_json(payload)
            if existing_idempotency is not None:
                if existing_idempotency["payload_hash"] != payload_hash:
                    raise ReviewError("FMEA_MIGRATION_IDEMPOTENCY_CONFLICT", "migration key has a different payload")
                if existing_idempotency["state"] != "completed":
                    raise ReviewError(
                        "FMEA_MIGRATION_STORAGE_UNAVAILABLE",
                        "an incomplete migration transaction is present",
                        retryable=True,
                    )
                self._verify_migration_replay(connection, prepared, child, scope, payload_hash, result)
                connection.execute("COMMIT")
                return replace(result, replayed=True)

            self._insert_idempotency(connection, scope, payload_hash, prepared.report.created_at)
            self._fail("migration.idempotency.reserve")
            audit_id = "migration-audit-" + sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]
            outbox_id = "migration-outbox-" + sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]
            source_hash = _prefixed(source.revision_hash)
            child_hash = _prefixed(child.revision_hash)
            from core_domain.fmea.value_objects import VersionSet

            audit = AuditEvent(
                event_id=audit_id,
                occurred_at_server=prepared.report.created_at,
                workspace_id=prepared.actor.workspace_id,
                actor_id=prepared.actor.actor_id,
                actor_type=prepared.actor.actor_type,
                actor_roles=tuple(sorted(prepared.actor.roles)),
                command=self._MIGRATION_COMMAND,
                action=None,
                reason_code=None,
                reason="confirmed FMEA migration",
                analysis_id=source.analysis_id,
                row_id=child.revision_id,
                suggestion_id=None,
                decision_id=None,
                expected_record_version=prepared.source_record_version,
                applied_record_version=1,
                before_hash=source_hash,
                after_hash=child_hash,
                changed_fields=(),
                evidence_ids=(),
                evidence_request_targets=(),
                idempotency_key_hash=scope.key_hash,
                canonical_payload_hash=payload_hash,
                versions=VersionSet(
                    schema_id=FMEA_SCHEMA_ID,
                    data_version="migration-v1",
                    graph_version="migration-v1",
                    evidence_pack_version="migration-v1",
                    profile_version="migration-v1",
                    template_version=child.domain_pack_identity[1],
                    scoring_version="migration-v1",
                    prompt_version="migration-v1",
                    model_version="migration-system",
                    input_snapshot_hash=source_hash,
                ),
                template_id=child.domain_pack_identity[0],
                template_version=child.domain_pack_identity[1],
                profile_id="fmea-migration",
                profile_version="1.0.0",
                model_manifest=None,
                request_id=run_id,
                trace_id=run_id,
                retrieval_trace_id=run_id,
                run_id=run_id,
                request_hash=payload_hash,
            )
            outbox = OutboxEvent(
                event_id=outbox_id,
                workspace_id=prepared.actor.workspace_id,
                aggregate_type="fmea_governance",
                aggregate_id=child.revision_id,
                event_type="migration.completed",
                payload=payload,
                payload_hash=outbox_payload_hash(payload),
                created_at=prepared.report.created_at,
                scope_key=scope.scope_key,
            )
            meta = _PreparedMeta(
                "revision",
                prepared.actor.workspace_id,
                child.revision_id,
                child.revision_id,
                "revision",
                self._MIGRATION_COMMAND,
                payload,
            )
            self._insert_audit(connection, audit, scope, payload_hash, meta)
            self._fail("migration.audit")
            inserted = self._ensure_revision(
                connection,
                child,
                audit_id,
                outbox_id,
                scope.scope_key,
                payload_hash,
            )
            if inserted:
                self._insert_revision_analysis_binding(connection, child)
            self._fail("migration.after_revision")
            connection.execute(
                "INSERT INTO fmea_migration_confirmations "
                "(workspace_id,confirmation_id,migration_id,report_id,report_hash,source_revision_id,"
                "source_revision_hash,source_domain_pack_id,source_domain_pack_version,source_domain_pack_hash,"
                "target_domain_pack_id,target_domain_pack_version,target_domain_pack_hash,target_revision_hash,"
                "child_revision_id,actor_id,actor_type,idempotency_scope,payload_hash,confirmation_json,"
                "canonical_json_hash,audit_event_id,outbox_event_id,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    prepared.actor.workspace_id,
                    confirmation_id,
                    prepared.command.migration_id,
                    report_id,
                    prepared.report.report_hash,
                    source.revision_id,
                    source.revision_hash,
                    prepared.report.source_domain_pack_identity[0],
                    prepared.report.source_domain_pack_identity[1],
                    prepared.report.source_domain_pack_identity[2],
                    child.domain_pack_identity[0],
                    child.domain_pack_identity[1],
                    child.domain_pack_identity[2],
                    prepared.report.target_revision_hash,
                    child.revision_id,
                    prepared.actor.actor_id,
                    prepared.actor.actor_type.value,
                    scope.scope_key,
                    payload_hash,
                    canonical_json(payload),
                    _hash_json(payload),
                    audit_id,
                    outbox_id,
                    prepared.report.created_at,
                ),
            )
            self._fail("migration.confirmation")
            self._insert_outbox(connection, outbox, scope, meta, "migration.completed")
            self._insert_event_binding(
                connection, meta, type("Result", (), {"audit_event_id": audit_id, "outbox_event_id": outbox_id})()
            )
            self._fail("migration.outbox")
            response_json = canonical_json(_json_value(result))
            connection.execute(
                "UPDATE idempotency_records SET state='completed',status_code=201,resource_id=?,response_json=?,completed_at=? "
                "WHERE scope_key=? AND payload_hash=? AND state='reserved'",
                (child.revision_id, response_json, prepared.report.created_at, scope.scope_key, payload_hash),
            )
            if connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise ReviewError(
                    "FMEA_MIGRATION_STORAGE_UNAVAILABLE", "migration idempotency completion failed", retryable=True
                )
            self._fail("migration.idempotency.complete")
            connection.execute(
                "UPDATE fmea_migration_runs SET status='confirmed',child_revision_id=?,"
                "idempotency_scope=?,finished_at=? WHERE workspace_id=? AND migration_id=?",
                (
                    child.revision_id,
                    scope.scope_key,
                    prepared.report.created_at,
                    prepared.actor.workspace_id,
                    prepared.command.migration_id,
                ),
            )
            if connection.execute("SELECT changes()").fetchone()[0] != 1:
                raise ReviewError(
                    "FMEA_MIGRATION_STORAGE_UNAVAILABLE", "migration run completion failed", retryable=True
                )
            self._verify_migration_replay(connection, prepared, child, scope, payload_hash, result)
            connection.execute("COMMIT")
            return result
        except ReviewError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise ReviewError(
                "FMEA_MIGRATION_FAILED", "confirmed migration could not be committed", retryable=True
            ) from None
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise ReviewError(
                "FMEA_MIGRATION_FAILED", "confirmed migration could not be committed", retryable=True
            ) from None
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Export lifecycle persistence (Task 4 C1)
    # ------------------------------------------------------------------

    @staticmethod
    def _export_scope(command: Any, actor: ActorContext) -> IdempotencyScope:
        return IdempotencyScope(
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            command="fmea.export.start",
            resource_path=f"/fmea/workspaces/{actor.workspace_id}/exports",
            key_hash=idempotency_key_hash(command.idempotency_key),
        )

    @staticmethod
    def _export_run_from_row(row: sqlite3.Row) -> ExportRun:
        body = _load_object(row["run_json"], "export run")
        expected = {field.name for field in fields(ExportRun)}
        if set(body) != expected or row["canonical_json_hash"] != _hash_json(body):
            raise ValueError("persisted export run is not canonical")
        run = ExportRun(**body)
        if _json_value(run) != body:
            raise ValueError("persisted export run does not match its contract")
        columns: dict[str, object] = {
            "workspace_id": run.workspace_id,
            "export_run_id": run.export_run_id,
            "revision_id": run.revision_id,
            "snapshot_id": run.snapshot_id,
            "snapshot_hash": run.snapshot_hash,
            "publication_id": run.publication_id,
            "format": run.format.value,
            "draft_preview": int(run.draft_preview),
            "status": run.status.value,
            "created_at": run.created_at,
            "filename": run.filename,
            "artifact_id": run.artifact_id,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "error": run.error,
        }
        for name, expected_value in columns.items():
            if row[name] != expected_value:
                raise ValueError(f"persisted export run column {name} is invalid")
        if run.status is RunStatus.SUCCEEDED and (row["audit_event_id"] is None or row["outbox_event_id"] is None):
            raise ValueError("succeeded export run is missing its audit/outbox binding")
        if run.status is not RunStatus.SUCCEEDED and (
            row["audit_event_id"] is not None or row["outbox_event_id"] is not None
        ):
            raise ValueError("non-terminal export run has a terminal event binding")
        _load_object(row["request_json"], "export request")
        if row["request_hash"] != _hash_json(json.loads(row["request_json"])):
            raise ValueError("persisted export request hash is invalid")
        if not isinstance(row["actor_id"], str) or not row["actor_id"].strip():
            raise ValueError("persisted export actor is invalid")
        if not isinstance(row["idempotency_scope"], str) or not row["idempotency_scope"].strip():
            raise ValueError("persisted export idempotency scope is invalid")
        return run

    @staticmethod
    def _export_manifest_from_row(row: sqlite3.Row) -> ExportArtifactManifest:
        body = _load_object(row["artifact_json"], "export artifact")
        expected = {field.name for field in fields(ExportArtifactManifest)}
        if set(body) != expected or row["canonical_json_hash"] != _hash_json(body):
            raise ValueError("persisted export artifact is not canonical")
        manifest = ExportArtifactManifest(**body)
        if _json_value(manifest) != body:
            raise ValueError("persisted export artifact does not match its contract")
        columns: dict[str, object] = {
            "workspace_id": row["workspace_id"],
            "artifact_id": manifest.artifact_id,
            "export_run_id": manifest.export_run_id,
            "publication_id": manifest.publication_id,
            "revision_id": manifest.revision_id,
            "snapshot_id": manifest.snapshot_id,
            "snapshot_hash": manifest.snapshot_hash,
            "format": manifest.format.value,
            "media_type": manifest.media_type,
            "byte_length": manifest.byte_length,
            "sha256": manifest.sha256,
            "draft_preview": int(manifest.draft_preview),
            "created_at": manifest.created_at,
            "filename": manifest.filename,
        }
        for name, expected_value in columns.items():
            if row[name] != expected_value:
                raise ValueError(f"persisted export artifact column {name} is invalid")
        return manifest

    @staticmethod
    def _export_run_json(run: ExportRun) -> tuple[str, str]:
        return _contract_json(run)

    @staticmethod
    def _export_manifest_json(manifest: ExportArtifactManifest) -> tuple[str, str]:
        return _contract_json(manifest)

    @classmethod
    def _verify_export_delivery_chain(
        cls,
        connection: sqlite3.Connection,
        export_run_id: str,
        workspace_id: str,
    ) -> tuple[ExportRun, ExportArtifactManifest]:
        run_row = connection.execute(
            "SELECT * FROM fmea_export_runs WHERE workspace_id=? AND export_run_id=?",
            (workspace_id, export_run_id),
        ).fetchone()
        if run_row is None:
            raise ValueError("persisted export run is missing")
        run = cls._export_run_from_row(run_row)
        if run.status is not RunStatus.SUCCEEDED or run.artifact_id is None or run.finished_at is None:
            raise ValueError("persisted export delivery is not completed")

        artifact_row = connection.execute(
            "SELECT * FROM fmea_export_artifacts WHERE workspace_id=? AND artifact_id=?",
            (workspace_id, run.artifact_id),
        ).fetchone()
        if artifact_row is None:
            raise ValueError("persisted export artifact is missing")
        manifest = cls._export_manifest_from_row(artifact_row)
        validate_export_binding(run, manifest)
        if datetime.fromisoformat(manifest.created_at.replace("Z", "+00:00")) > datetime.fromisoformat(
            run.finished_at.replace("Z", "+00:00")
        ):
            raise ValueError("persisted export artifact chronology is invalid")

        request = _load_object(run_row["request_json"], "export request")
        expected_request = {
            "export_run_id": run.export_run_id,
            "workspace_id": run.workspace_id,
            "revision_id": run.revision_id,
            "snapshot_id": run.snapshot_id,
            "snapshot_hash": run.snapshot_hash,
            "publication_id": run.publication_id,
            "format": run.format.value,
            "draft_preview": run.draft_preview,
            "filename": run.filename,
            "idempotency_key": request.get("idempotency_key"),
        }
        if "expected_revision_version" in request:
            expected_request["expected_revision_version"] = request["expected_revision_version"]
        idempotency_key = request.get("idempotency_key")
        if request != expected_request or not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("persisted export request binding is invalid")
        request_hash = _hash_json(request)
        if run_row["request_hash"] != request_hash:
            raise ValueError("persisted export request hash is invalid")
        actor_id = run_row["actor_id"]
        scope = IdempotencyScope(
            workspace_id=workspace_id,
            actor_id=actor_id,
            command="fmea.export.start",
            resource_path=f"/fmea/workspaces/{workspace_id}/exports",
            key_hash=idempotency_key_hash(idempotency_key),
        )
        if run_row["idempotency_scope"] != scope.scope_key:
            raise ValueError("persisted export idempotency scope is invalid")

        expected_audit_id = "export-audit-" + sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]
        audit_row = connection.execute(
            "SELECT * FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            (workspace_id, run_row["audit_event_id"]),
        ).fetchone()
        if audit_row is None or run_row["audit_event_id"] != expected_audit_id:
            raise ValueError("persisted export audit event is missing")
        audit = decode_audit_event(audit_row["event_json"])
        expected_versions = VersionSet(
            schema_id=FMEA_SCHEMA_ID,
            data_version="export-v1",
            graph_version="export-v1",
            evidence_pack_version="export-v1",
            profile_version="export-v1",
            template_version="export-v1",
            scoring_version="export-v1",
            prompt_version="export-v1",
            model_version="export-system",
            input_snapshot_hash=manifest.snapshot_hash,
        )
        if (
            audit_row["workspace_id"] != workspace_id
            or audit_row["event_id"] != expected_audit_id
            or audit_row["resource_type"] != "revision"
            or audit_row["resource_id"] != run.revision_id
            or audit_row["actor_id"] != actor_id
            or audit_row["actor_type"] != ActorType.HUMAN.value
            or audit_row["command"] != "fmea.export.start"
            or audit_row["idempotency_scope"] != scope.scope_key
            or audit_row["canonical_payload_hash"] != request_hash
            or audit_row["created_at"] != run.finished_at
            or canonical_json(_json_value(audit)) != audit_row["event_json"]
            or audit.event_id != expected_audit_id
            or audit.occurred_at_server != run.finished_at
            or audit.workspace_id != workspace_id
            or audit.actor_id != actor_id
            or audit.actor_type is not ActorType.HUMAN
            or not ({"exporter", "publisher", "admin"} & set(audit.actor_roles))
            or tuple(sorted(audit.actor_roles)) != audit.actor_roles
            or audit.command != "fmea.export.start"
            or audit.action is not None
            or audit.reason_code is not None
            or audit.reason != "verified FMEA export completed"
            or audit.analysis_id != "fmea-export"
            or audit.row_id != run.revision_id
            or audit.suggestion_id is not None
            or audit.decision_id is not None
            or audit.expected_record_version is not None
            or audit.applied_record_version is not None
            or audit.before_hash is not None
            or audit.after_hash != _prefixed(manifest.snapshot_hash)
            or audit.changed_fields
            or audit.evidence_ids
            or audit.evidence_request_targets
            or audit.idempotency_key_hash != scope.key_hash
            or audit.canonical_payload_hash != request_hash
            or audit.versions != expected_versions
            or audit.template_id != "fmea-export"
            or audit.template_version != "1.0.0"
            or audit.profile_id != "export"
            or audit.profile_version != "1.0.0"
            or audit.model_manifest is not None
            or audit.request_id != run.export_run_id
            or audit.trace_id != run.export_run_id
            or audit.retrieval_trace_id != run.export_run_id
            or audit.run_id != run.export_run_id
            or audit.request_hash != request_hash
            or audit.error_code is not None
            or audit.retryable
        ):
            raise ValueError("persisted export audit binding is invalid")

        expected_outbox_id = "export-outbox-" + sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]
        outbox_row = connection.execute(
            "SELECT * FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            (workspace_id, run_row["outbox_event_id"]),
        ).fetchone()
        if outbox_row is None or run_row["outbox_event_id"] != expected_outbox_id:
            raise ValueError("persisted export outbox event is missing")
        outbox_payload = load_strict_json(outbox_row["payload_json"], "export outbox")
        expected_payload = {
            "schema": "graphrag.fmea.export.lifecycle.v1",
            "event": "completed",
            "run": _json_value(run),
            "artifact": _json_value(manifest),
        }
        if (
            outbox_payload != expected_payload
            or canonical_json(outbox_payload) != outbox_row["payload_json"]
            or outbox_row["event_id"] != expected_outbox_id
            or outbox_row["workspace_id"] != workspace_id
            or outbox_row["aggregate_type"] != "fmea_governance"
            or outbox_row["aggregate_id"] != run.revision_id
            or outbox_row["event_type"] != "export.completed"
            or outbox_row["status"] != "pending"
            or outbox_row["payload_hash"] != outbox_payload_hash(outbox_payload)
            or outbox_row["idempotency_scope"] != scope.scope_key
            or outbox_row["created_at"] != run.finished_at
        ):
            raise ValueError("persisted export outbox binding is invalid")

        idempotency = connection.execute(
            "SELECT * FROM idempotency_records WHERE scope_key=?",
            (scope.scope_key,),
        ).fetchone()
        if idempotency is None:
            raise ValueError("persisted export idempotency record is missing")
        response = _load_object(idempotency["response_json"], "export response")
        if (
            idempotency["scope_key"] != scope.scope_key
            or idempotency["payload_hash"] != request_hash
            or idempotency["state"] != "completed"
            or idempotency["status_code"] != 201
            or idempotency["resource_id"] != run.export_run_id
            or response != _json_value(run)
            or canonical_json(response) != idempotency["response_json"]
            or idempotency["created_at"] != run.created_at
            or idempotency["completed_at"] != run.finished_at
        ):
            raise ValueError("persisted export idempotency binding is invalid")
        return run, manifest

    def get_export_run(self, export_run_id: str, workspace_id: str) -> ExportRun | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM fmea_export_runs WHERE workspace_id=? AND export_run_id=?",
                (workspace_id, export_run_id),
            ).fetchone()
            if row is None:
                return None
            run = self._export_run_from_row(row)
            if run.status is RunStatus.CANCELLED:
                self._verify_export_cancelled_idempotency(connection, row, run)
            return run
        finally:
            connection.close()

    def get_export_artifact(self, artifact_id: str, workspace_id: str) -> ExportArtifactManifest | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM fmea_export_artifacts WHERE workspace_id=? AND artifact_id=?",
                (workspace_id, artifact_id),
            ).fetchone()
            return None if row is None else self._export_manifest_from_row(row)
        finally:
            connection.close()

    def verify_export_delivery(self, export_run_id: str, workspace_id: str) -> tuple[ExportRun, ExportArtifactManifest]:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            result = self._verify_export_delivery_chain(connection, export_run_id, workspace_id)
            connection.execute("COMMIT")
            return result
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @staticmethod
    def _legacy_export_replay_hash(command: Any, request_json: str, request_hash: str) -> str:
        request = _load_object(request_json, "export request")
        expected_keys = {
            "export_run_id", "workspace_id", "revision_id", "snapshot_id", "snapshot_hash",
            "publication_id", "format", "draft_preview", "filename", "idempotency_key",
            "expected_revision_version",
        }
        if (
            set(request) != expected_keys
            or type(command.expected_revision_version) is not int
            or command.expected_revision_version != 1
            or type(request.get("expected_revision_version")) is not int
            or request["expected_revision_version"] != 1
            or _hash_json(request) != request_hash
        ):
            return request_hash
        # Only this added default field may differ from immutable legacy history.
        request.pop("expected_revision_version")
        return _hash_json(request)

    def reserve_export_run(
        self,
        command: Any,
        actor: ActorContext,
        request_json: str,
        request_hash: str,
        created_at: str,
    ) -> ExportRun:
        scope = self._export_scope(command, actor)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            idempotency = self._idempotency_row(connection, scope)
            existing_row = connection.execute(
                "SELECT * FROM fmea_export_runs WHERE workspace_id=? AND export_run_id=?",
                (actor.workspace_id, command.export_run_id),
            ).fetchone()
            if idempotency is not None:
                replay_hash = request_hash
                if (
                    idempotency["payload_hash"] != request_hash
                    and idempotency["state"] == "completed"
                    and existing_row is not None
                    and existing_row["status"] == "succeeded"
                ):
                    replay_hash = self._legacy_export_replay_hash(command, request_json, request_hash)
                if idempotency["payload_hash"] != replay_hash:
                    raise ValueError("FMEA_EXPORT_IDEMPOTENCY_CONFLICT")
                if existing_row is None:
                    raise ValueError("persisted export idempotency has no run")
                run = self._export_run_from_row(existing_row)
                if existing_row["request_hash"] != replay_hash or existing_row["idempotency_scope"] != scope.scope_key:
                    raise ValueError("FMEA_EXPORT_IDEMPOTENCY_CONFLICT")
                if run.status is RunStatus.CANCELLED:
                    self._verify_export_cancelled_idempotency(connection, existing_row, run)
                connection.execute("COMMIT")
                return run
            if existing_row is not None:
                self._export_run_from_row(existing_row)
                if existing_row["request_hash"] != request_hash:
                    raise ValueError("FMEA_EXPORT_IDEMPOTENCY_CONFLICT")
                if existing_row["actor_id"] != actor.actor_id:
                    raise ValueError("FMEA_EXPORT_IDEMPOTENCY_CONFLICT")
                raise ValueError("persisted export run is missing idempotency reservation")

            revision_row = connection.execute(
                "SELECT record_version FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
                (actor.workspace_id, command.revision_id),
            ).fetchone()
            expected_version = getattr(command, "expected_revision_version", 1)
            if revision_row is None:
                raise ValueError("export revision was not found")
            record_version = revision_row["record_version"]
            if (
                isinstance(record_version, bool)
                or not isinstance(record_version, int)
                or record_version < 1
                or isinstance(expected_version, bool)
                or not isinstance(expected_version, int)
                or expected_version < 1
            ):
                raise ValueError("export revision version is invalid")
            if record_version != expected_version:
                raise ApplicationReviewError("FMEA_VERSION_CONFLICT", "export source revision version is stale")

            self._insert_idempotency(connection, scope, request_hash, created_at)
            self._fail("export.reserve")
            run = ExportRun(
                export_run_id=command.export_run_id,
                workspace_id=actor.workspace_id,
                revision_id=command.revision_id,
                snapshot_id=command.snapshot_id,
                snapshot_hash=command.snapshot_hash,
                publication_id=command.publication_id,
                format=command.format,
                draft_preview=command.draft_preview,
                status=RunStatus.QUEUED,
                created_at=created_at,
                filename=command.filename,
            )
            run_json, canonical_hash = self._export_run_json(run)
            connection.execute(
                "INSERT INTO fmea_export_runs "
                "(workspace_id,export_run_id,revision_id,snapshot_id,snapshot_hash,publication_id,format,draft_preview,status,"
                "created_at,filename,artifact_id,started_at,finished_at,error,actor_id,idempotency_scope,request_json,request_hash,"
                "audit_event_id,outbox_event_id,run_json,canonical_json_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run.workspace_id,
                    run.export_run_id,
                    run.revision_id,
                    run.snapshot_id,
                    run.snapshot_hash,
                    run.publication_id,
                    run.format.value,
                    int(run.draft_preview),
                    run.status.value,
                    run.created_at,
                    run.filename,
                    run.artifact_id,
                    run.started_at,
                    run.finished_at,
                    run.error,
                    actor.actor_id,
                    scope.scope_key,
                    request_json,
                    request_hash,
                    None,
                    None,
                    run_json,
                    canonical_hash,
                ),
            )
            connection.execute("COMMIT")
            return run
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def mark_export_running(self, export_run_id: str, workspace_id: str, started_at: str) -> ExportRun:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM fmea_export_runs WHERE workspace_id=? AND export_run_id=?",
                (workspace_id, export_run_id),
            ).fetchone()
            if row is None:
                raise ValueError("export run was not found")
            run = self._export_run_from_row(row)
            if run.status is RunStatus.RUNNING:
                connection.execute("COMMIT")
                return run
            if run.status is not RunStatus.QUEUED:
                raise ValueError("export run cannot enter running state")
            updated = replace(run, status=RunStatus.RUNNING, started_at=started_at)
            run_json, canonical_hash = self._export_run_json(updated)
            connection.execute(
                "UPDATE fmea_export_runs SET status=?,started_at=?,run_json=?,canonical_json_hash=? "
                "WHERE workspace_id=? AND export_run_id=?",
                (
                    updated.status.value,
                    updated.started_at,
                    run_json,
                    canonical_hash,
                    workspace_id,
                    export_run_id,
                ),
            )
            connection.execute("COMMIT")
            return updated
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @staticmethod
    def _verify_export_cancelled_idempotency(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        run: ExportRun,
    ) -> None:
        if run.status is not RunStatus.CANCELLED or run.finished_at is None:
            raise ValueError("export cancellation is not complete")
        request = _load_object(row["request_json"], "export request")
        key = request.get("idempotency_key")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("cancelled export request is invalid")
        scope = IdempotencyScope(
            workspace_id=run.workspace_id,
            actor_id=row["actor_id"],
            command="fmea.export.start",
            resource_path=f"/fmea/workspaces/{run.workspace_id}/exports",
            key_hash=idempotency_key_hash(key),
        )
        idempotency = connection.execute(
            "SELECT * FROM idempotency_records WHERE scope_key=?",
            (scope.scope_key,),
        ).fetchone()
        if idempotency is None:
            raise ValueError("cancelled export idempotency is missing")
        response = _load_object(idempotency["response_json"], "cancelled export response")
        if (
            row["idempotency_scope"] != scope.scope_key
            or idempotency["payload_hash"] != row["request_hash"]
            or idempotency["state"] != "completed"
            or idempotency["status_code"] != 200
            or idempotency["resource_id"] != run.export_run_id
            or response != _json_value(run)
            or canonical_json(response) != idempotency["response_json"]
            or idempotency["created_at"] != run.created_at
            or idempotency["completed_at"] != run.finished_at
        ):
            raise ValueError("cancelled export idempotency is invalid")

    def request_export_cancellation(
        self,
        export_run_id: str,
        workspace_id: str,
        requested_at: str,
    ) -> ExportRun:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM fmea_export_runs WHERE workspace_id=? AND export_run_id=?",
                (workspace_id, export_run_id),
            ).fetchone()
            if row is None:
                raise ValueError("export run was not found")
            current = self._export_run_from_row(row)
            if current.status is RunStatus.CANCELLED:
                self._verify_export_cancelled_idempotency(connection, row, current)
                connection.execute("COMMIT")
                return current
            if current.status in {RunStatus.CANCELLING, RunStatus.SUCCEEDED, RunStatus.FAILED}:
                connection.execute("COMMIT")
                return current
            if current.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
                raise ValueError("export run cannot enter cancelling state")
            updated = replace(
                current,
                status=RunStatus.CANCELLING,
                started_at=current.started_at or requested_at,
            )
            run_json, canonical_hash = self._export_run_json(updated)
            connection.execute(
                "UPDATE fmea_export_runs SET status=?,started_at=?,run_json=?,canonical_json_hash=? "
                "WHERE workspace_id=? AND export_run_id=?",
                (
                    updated.status.value,
                    updated.started_at,
                    run_json,
                    canonical_hash,
                    workspace_id,
                    export_run_id,
                ),
            )
            connection.execute("COMMIT")
            return updated
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def complete_export_cancellation(
        self,
        export_run_id: str,
        workspace_id: str,
        finished_at: str,
    ) -> ExportRun:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM fmea_export_runs WHERE workspace_id=? AND export_run_id=?",
                (workspace_id, export_run_id),
            ).fetchone()
            if row is None:
                raise ValueError("export run was not found")
            current = self._export_run_from_row(row)
            if current.status is RunStatus.CANCELLED:
                self._verify_export_cancelled_idempotency(connection, row, current)
                connection.execute("COMMIT")
                return current
            if current.status is not RunStatus.CANCELLING:
                raise ValueError("export run is not cancelling")
            updated = replace(current, status=RunStatus.CANCELLED, finished_at=finished_at)
            run_json, canonical_hash = self._export_run_json(updated)
            connection.execute(
                "UPDATE fmea_export_runs SET status=?,finished_at=?,run_json=?,canonical_json_hash=? "
                "WHERE workspace_id=? AND export_run_id=?",
                (
                    updated.status.value,
                    updated.finished_at,
                    run_json,
                    canonical_hash,
                    workspace_id,
                    export_run_id,
                ),
            )
            response_json = canonical_json(_json_value(updated))
            cursor = connection.execute(
                "UPDATE idempotency_records SET state='completed',status_code=200,resource_id=?,response_json=?,"
                "completed_at=? WHERE scope_key=? AND payload_hash=? AND state='reserved'",
                (
                    updated.export_run_id,
                    response_json,
                    updated.finished_at,
                    row["idempotency_scope"],
                    row["request_hash"],
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("export cancellation idempotency completion failed")
            updated_row = connection.execute(
                "SELECT * FROM fmea_export_runs WHERE workspace_id=? AND export_run_id=?",
                (workspace_id, export_run_id),
            ).fetchone()
            persisted = self._export_run_from_row(updated_row)
            if persisted != updated:
                raise ValueError("persisted export cancellation is invalid")
            self._verify_export_cancelled_idempotency(connection, updated_row, persisted)
            connection.execute("COMMIT")
            return persisted
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _export_audit_and_outbox(
        self,
        connection: sqlite3.Connection,
        run: ExportRun,
        manifest: ExportArtifactManifest,
        actor: ActorContext,
        request_json: str,
        request_hash: str,
        finished_at: str,
    ) -> tuple[str, str]:
        request = _load_object(request_json, "export request")
        key = request.get("idempotency_key")
        if not isinstance(key, str):
            raise ValueError("export request idempotency key is invalid")
        scope = self._export_scope(type("Command", (), {"idempotency_key": key})(), actor)
        if (
            scope.scope_key
            != connection.execute(
                "SELECT idempotency_scope FROM fmea_export_runs WHERE workspace_id=? AND export_run_id=?",
                (run.workspace_id, run.export_run_id),
            ).fetchone()[0]
        ):
            raise ValueError("export idempotency scope is invalid")
        audit_id = "export-audit-" + sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]
        outbox_id = "export-outbox-" + sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]
        payload = {
            "schema": "graphrag.fmea.export.lifecycle.v1",
            "event": "completed",
            "run": _json_value(run),
            "artifact": _json_value(manifest),
        }
        audit = AuditEvent(
            event_id=audit_id,
            occurred_at_server=finished_at,
            workspace_id=run.workspace_id,
            actor_id=actor.actor_id,
            actor_type=actor.actor_type,
            actor_roles=tuple(sorted(actor.roles)),
            command="fmea.export.start",
            action=None,
            reason_code=None,
            reason="verified FMEA export completed",
            analysis_id="fmea-export",
            row_id=run.revision_id,
            suggestion_id=None,
            decision_id=None,
            expected_record_version=None,
            applied_record_version=None,
            before_hash=None,
            after_hash=_prefixed(manifest.snapshot_hash),
            changed_fields=(),
            evidence_ids=(),
            evidence_request_targets=(),
            idempotency_key_hash=scope.key_hash,
            canonical_payload_hash=request_hash,
            versions=VersionSet(
                schema_id=FMEA_SCHEMA_ID,
                data_version="export-v1",
                graph_version="export-v1",
                evidence_pack_version="export-v1",
                profile_version="export-v1",
                template_version="export-v1",
                scoring_version="export-v1",
                prompt_version="export-v1",
                model_version="export-system",
                input_snapshot_hash=manifest.snapshot_hash,
            ),
            template_id="fmea-export",
            template_version="1.0.0",
            profile_id="export",
            profile_version="1.0.0",
            model_manifest=None,
            request_id=run.export_run_id,
            trace_id=run.export_run_id,
            retrieval_trace_id=run.export_run_id,
            run_id=run.export_run_id,
            request_hash=request_hash,
        )
        meta = _PreparedMeta(
            "revision",
            run.workspace_id,
            run.revision_id,
            run.revision_id,
            "revision",
            "fmea.export.start",
            payload,
        )
        self._insert_audit(connection, audit, scope, request_hash, meta)
        outbox = OutboxEvent(
            event_id=outbox_id,
            workspace_id=run.workspace_id,
            aggregate_type="fmea_governance",
            aggregate_id=run.revision_id,
            event_type="export.completed",
            payload=payload,
            payload_hash=outbox_payload_hash(payload),
            created_at=finished_at,
            scope_key=scope.scope_key,
        )
        self._insert_outbox(connection, outbox, scope, meta, "export.completed")
        return audit_id, outbox_id

    def complete_export(
        self,
        run: ExportRun,
        manifest: ExportArtifactManifest,
        actor: ActorContext,
        request_json: str,
        request_hash: str,
        finished_at: str,
    ) -> ExportRun:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM fmea_export_runs WHERE workspace_id=? AND export_run_id=?",
                (actor.workspace_id, run.export_run_id),
            ).fetchone()
            if row is None:
                raise ValueError("export run was not found")
            current = self._export_run_from_row(row)
            if current.status is RunStatus.SUCCEEDED:
                verified, _ = self._verify_export_delivery_chain(
                    connection, current.export_run_id, current.workspace_id
                )
                connection.execute("COMMIT")
                return verified
            if current.status is not RunStatus.RUNNING:
                raise ValueError("export run is not running")
            if current != run or row["request_hash"] != request_hash:
                raise ValueError("export run binding is stale")
            completed = replace(
                current,
                status=RunStatus.SUCCEEDED,
                finished_at=finished_at,
                artifact_id=manifest.artifact_id,
            )
            if (
                manifest.export_run_id != completed.export_run_id
                or manifest.revision_id != completed.revision_id
                or manifest.snapshot_id != completed.snapshot_id
                or manifest.snapshot_hash != completed.snapshot_hash
                or manifest.publication_id != completed.publication_id
                or manifest.format != completed.format
                or manifest.draft_preview != completed.draft_preview
                or manifest.filename != completed.filename
            ):
                raise ValueError("export artifact binding is invalid")
            validate_export_binding(completed, manifest)
            artifact_json, artifact_hash = self._export_manifest_json(manifest)
            existing_artifact = connection.execute(
                "SELECT * FROM fmea_export_artifacts WHERE workspace_id=? AND artifact_id=?",
                (actor.workspace_id, manifest.artifact_id),
            ).fetchone()
            if existing_artifact is None:
                connection.execute(
                    "INSERT INTO fmea_export_artifacts "
                    "(workspace_id,artifact_id,export_run_id,publication_id,revision_id,snapshot_id,snapshot_hash,format,media_type,"
                    "byte_length,sha256,draft_preview,created_at,filename,artifact_json,canonical_json_hash) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        actor.workspace_id,
                        manifest.artifact_id,
                        manifest.export_run_id,
                        manifest.publication_id,
                        manifest.revision_id,
                        manifest.snapshot_id,
                        manifest.snapshot_hash,
                        manifest.format.value,
                        manifest.media_type,
                        manifest.byte_length,
                        manifest.sha256,
                        int(manifest.draft_preview),
                        manifest.created_at,
                        manifest.filename,
                        artifact_json,
                        artifact_hash,
                    ),
                )
            elif self._export_manifest_from_row(existing_artifact) != manifest:
                raise ValueError("export artifact identity has different content")

            audit_id, outbox_id = self._export_audit_and_outbox(
                connection, completed, manifest, actor, request_json, request_hash, finished_at
            )
            run_json, canonical_hash = self._export_run_json(completed)
            connection.execute(
                "UPDATE fmea_export_runs SET status=?,finished_at=?,artifact_id=?,audit_event_id=?,outbox_event_id=?,"
                "run_json=?,canonical_json_hash=? WHERE workspace_id=? AND export_run_id=?",
                (
                    completed.status.value,
                    completed.finished_at,
                    completed.artifact_id,
                    audit_id,
                    outbox_id,
                    run_json,
                    canonical_hash,
                    actor.workspace_id,
                    completed.export_run_id,
                ),
            )
            response_json = canonical_json(_json_value(completed))
            cursor = connection.execute(
                "UPDATE idempotency_records SET state='completed',status_code=201,resource_id=?,response_json=?,completed_at=? "
                "WHERE scope_key=? AND payload_hash=? AND state='reserved'",
                (completed.export_run_id, response_json, finished_at, row["idempotency_scope"], request_hash),
            )
            if cursor.rowcount != 1:
                raise ValueError("export idempotency completion failed")
            verified, verified_manifest = self._verify_export_delivery_chain(
                connection, completed.export_run_id, completed.workspace_id
            )
            if verified != completed or verified_manifest != manifest:
                raise ValueError("persisted export completion verification failed")
            self._fail("export.commit")
            connection.execute("COMMIT")
            return verified
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def fail_export(self, export_run_id: str, workspace_id: str, error: str, finished_at: str) -> ExportRun:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM fmea_export_runs WHERE workspace_id=? AND export_run_id=?",
                (workspace_id, export_run_id),
            ).fetchone()
            if row is None:
                raise ValueError("export run was not found")
            current = self._export_run_from_row(row)
            if current.status in {RunStatus.FAILED, RunStatus.SUCCEEDED}:
                connection.execute("COMMIT")
                return current
            if current.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
                raise ValueError("export run cannot fail from its current state")
            updated = replace(
                current,
                status=RunStatus.FAILED,
                started_at=current.started_at or finished_at,
                finished_at=finished_at,
                error=_text(error[:512], "error"),
            )
            run_json, canonical_hash = self._export_run_json(updated)
            connection.execute(
                "UPDATE fmea_export_runs SET status=?,started_at=?,finished_at=?,error=?,run_json=?,canonical_json_hash=? "
                "WHERE workspace_id=? AND export_run_id=?",
                (
                    updated.status.value,
                    updated.started_at,
                    updated.finished_at,
                    updated.error,
                    run_json,
                    canonical_hash,
                    workspace_id,
                    export_run_id,
                ),
            )
            response_json = canonical_json(_json_value(updated))
            cursor = connection.execute(
                "UPDATE idempotency_records SET state='completed',status_code=500,resource_id=?,response_json=?,completed_at=? "
                "WHERE scope_key=? AND state='reserved'",
                (export_run_id, response_json, finished_at, row["idempotency_scope"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("export failure idempotency completion failed")
            self._fail("export.fail")
            connection.execute("COMMIT")
            return updated
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    # These small query helpers are useful to integration tests and keep
    # callers from reaching through the repository to SQLite directly.
    def count_child_revisions(self, parent_revision_id: str, workspace_id: str) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM fmea_revisions WHERE workspace_id=? AND parent_revision_id=?",
                (workspace_id, parent_revision_id),
            ).fetchone()
            return int(row[0])
        finally:
            connection.close()

    def count_outbox_events(self, event_type: str, workspace_id: str) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM fmea_outbox_events WHERE workspace_id=? AND event_type=?",
                (workspace_id, event_type),
            ).fetchone()
            return int(row[0])
        finally:
            connection.close()

    def count_migration_confirmations(self, workspace_id: str) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM fmea_migration_confirmations WHERE workspace_id=?",
                (workspace_id,),
            ).fetchone()
            return int(row[0])
        finally:
            connection.close()


__all__ = ["SqliteFmeaDeliveryRepository"]
