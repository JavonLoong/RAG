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
from typing import cast

from core_domain.fmea.governance import FmeaRevision, revision_content_hash
from core_domain.fmea.states import FMEA_SCHEMA_ID, ActorType
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
from fmea_application.migration_service import (
    ConfirmMigrationCommand,
    MigrationCommand,
    MigrationResult,
    PreparedMigration,
)
from fmea_application.migration_service import (
    MigrationServiceError as ReviewError,
)
from fmea_application.review_contracts import (
    ActorContext,
    AuditEvent,
    IdempotencyScope,
    idempotency_key_hash,
)
from fmea_application.risk_contracts import OutboxEvent, canonical_json, outbox_payload_hash

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
        return "migration-report-" + sha256(f"{workspace_id}:{migration_id}".encode()).hexdigest()[:40]

    @staticmethod
    def _run_id(workspace_id: str, migration_id: str) -> str:
        return "migration-run-" + sha256(f"{workspace_id}:{migration_id}".encode()).hexdigest()[:40]

    @staticmethod
    def _confirmation_id(scope: IdempotencyScope) -> str:
        return "migration-confirmation-" + sha256(scope.scope_key.encode("utf-8")).hexdigest()[:40]

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
        if row is None:
            raise ValueError("persisted migration run is missing")
        request = _load_object(row["request_json"], "migration request")
        command = prepared.command
        report = prepared.report
        source_pack = report.source_domain_pack_identity
        target_pack = report.target_domain_pack_identity
        expected_keys = set(_request_value(prepared.dry_run_command)) | {"actor_id", "workspace_id"}
        if set(request) != expected_keys:
            raise ValueError("persisted migration request shape is invalid")
        try:
            durable_command = MigrationCommand(
                migration_id=cast(str, request["migration_id"]),
                source_revision_id=cast(str, request["source_revision_id"]),
                source_revision_hash=cast(str, request["source_revision_hash"]),
                target_domain_pack_id=cast(str, request["target_domain_pack_id"]),
                target_domain_pack_version=cast(str, request["target_domain_pack_version"]),
                target_domain_pack_hash=cast(str, request["target_domain_pack_hash"]),
                idempotency_key=cast(str, request["idempotency_key"]),
            )
            durable_key_hash = idempotency_key_hash(durable_command.idempotency_key)
        except Exception:
            raise ValueError("persisted migration request is invalid") from None
        expected_request = _request_value(durable_command) | {
            "actor_id": prepared.actor.actor_id,
            "workspace_id": prepared.actor.workspace_id,
        }
        if request != expected_request:
            raise ValueError("persisted migration request is not canonical")
        if durable_command != prepared.dry_run_command:
            # A fresh service rebuilds this temporary command from the confirmation
            # and therefore carries the confirmation key.  Only that known key
            # substitution is allowed; the immutable report copy anchors the
            # original dry-run key hash below.
            fresh_process_command = replace(
                prepared.dry_run_command,
                idempotency_key=durable_command.idempotency_key,
            )
            if (
                prepared.dry_run_command.idempotency_key != prepared.command.idempotency_key
                or durable_command != fresh_process_command
            ):
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
            or row["request_hash"] != _hash_json(request)
            or row["request_idempotency_key_hash"] != durable_key_hash
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

    def get_migration_report(self, migration_id: str, workspace_id: str) -> MigrationReport | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM fmea_migration_reports WHERE workspace_id=? AND migration_id=?",
                (_text(workspace_id, "workspace_id"), _text(migration_id, "migration_id")),
            ).fetchone()
            if row is None:
                return None
            report = _decode_report(row["report_json"], row["report_hash"])
            if not _report_row_is_valid(row, report):
                raise ValueError("persisted migration report hash is invalid")
            return report
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
