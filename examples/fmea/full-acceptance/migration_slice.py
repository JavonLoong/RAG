"""Bounded real template-admin import and fuel domain-pack migration.

The full acceptance runner owns the published source revision and the plain
template XLSX. This slice deliberately only consumes those values: it never seeds a
revision, chooses an adapter, or performs an approval.  The only model-like
component is the deterministic provider at the template-mapping gateway; the
template compiler/registry, workflow repository, migration repository, and
domain-pack registry are the real implementations.
"""

# This example intentionally keeps the complete bounded orchestration in one
# file; the rule suppressions below do not change application-layer safety.
# ruff: noqa: C901, S608, TRY003, TRY004

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass, fields
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from core_domain.fmea.governance import (
    FmeaRevision,
    canonical_hash,
    canonical_json_bytes,
    revision_content_hash,
)
from core_domain.fmea.states import ActorType
from fmea_application.domain_pack_service import (
    AcceptTemplatePatchCommand,
    DomainPackService,
    ImportTemplateCommand,
    SuggestTemplatePatchCommand,
)
from fmea_application.migration_service import (
    ConfirmMigrationCommand,
    MigrationCandidate,
    MigrationCommand,
    MigrationResult,
    MigrationService,
)
from fmea_application.review_contracts import ActorContext, idempotency_key_hash
from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository
from fmea_infrastructure.domain_pack_registry import (
    FileDomainPackRegistry,
    load_domain_pack_manifest,
)
from fmea_infrastructure.migration_registry import MigrationRegistry
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository
from fmea_infrastructure.template_import_excel import ExcelTemplateImporter
from fmea_infrastructure.template_patch_generator import TemplatePatchGenerator
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import (
    Draft202012SchemaAdapter,
    FileTemplateRegistry,
    load_template_source,
)

_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_PACK_IDENTITY = ("fuel-combustion", "1.0.0")
_TARGET_PACK_IDENTITY = ("fuel-combustion", "2.0.0")
_SOURCE_TEMPLATE_IDENTITY = ("fuel-combustion-fmea", "1.0.0")
_TARGET_TEMPLATE_IDENTITY = ("fuel-combustion-fmea", "2.0.0")
_TARGET_PACK = Path(__file__).with_name("fuel-pack-v2.yaml")
_SOURCE_TEMPLATE = _ROOT / "templates" / "examples" / "fuel-combustion-fmea.yaml"
_UTC_FALLBACK = "2026-09-04T00:00:00Z"
_IMPORT_FILENAME = "template.xlsx"


@dataclass(frozen=True, slots=True)
class MigrationSliceResult:
    """Native helper result consumed by the main acceptance runner."""

    evidence: dict[str, object]
    child_revision: FmeaRevision


def _public(value: object) -> object:
    if isinstance(value, ImportTemplateCommand):
        return {
            "filename": value.filename,
            "workspace_id": value.workspace_id,
            "raw_bytes_sha256": sha256(value.raw_bytes).hexdigest(),
            "raw_bytes_length": len(value.raw_bytes),
            "idempotency_key": value.idempotency_key,
        }
    return json.loads(canonical_json_bytes(value))


def _request_identity_value(request: object) -> object:
    if isinstance(request, ImportTemplateCommand):
        return _public(request)
    return request


def _key(workspace_id: str, source_revision: FmeaRevision, name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"fmea-task8-migration:{workspace_id}:{source_revision.revision_id}:{name}"))


def _migration_id(workspace_id: str, source_revision: FmeaRevision) -> str:
    digest = sha256(f"{workspace_id}:{source_revision.revision_id}".encode()).hexdigest()[:24]
    return f"fuel-migration-{digest}"


def _records(database_path: Path, table: str, json_column: str, workspace_id: str) -> list[dict[str, object]]:
    # Do not use ``with sqlite3.connect`` here: on Windows it commits but does
    # not close the connection, which prevents the runner's temp directory
    # cleanup.
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute(
            f"SELECT {json_column} FROM {table} WHERE workspace_id=? ORDER BY rowid",
            (workspace_id,),
        ).fetchall()
    return [json.loads(str(row[0])) for row in rows]


def _counts(database_path: Path, workspace_id: str) -> dict[str, int]:
    tables = (
        "audit_events",
        "fmea_audit_events",
        "fmea_template_audit_events",
        "fmea_outbox_events",
        "fmea_template_drafts",
        "fmea_template_patch_candidates",
        "fmea_template_patch_decisions",
        "fmea_migration_reports",
        "fmea_migration_runs",
        "fmea_migration_confirmations",
        "fmea_revisions",
    )
    with closing(sqlite3.connect(database_path)) as connection:
        result = {
            table: int(
                connection.execute(f"SELECT COUNT(*) FROM {table} WHERE workspace_id=?", (workspace_id,)).fetchone()[0]
            )
            for table in tables
        }
    result["audit_events"] += result.pop("fmea_audit_events")
    result["outbox_events"] = result.pop("fmea_outbox_events")
    return result


def _import_source_receipt(draft: Mapping[str, object], import_bytes: bytes) -> dict[str, object]:
    source_hash = sha256(import_bytes).hexdigest()
    if draft.get("source_sha256") != source_hash or draft.get("source_filename") != _IMPORT_FILENAME:
        raise AssertionError("import source does not match the persisted draft")
    # TemplateDraft has no byte-length field: measure the actual supplied bytes,
    # and keep this metadata in the receipt, not in the native public DTO.
    return {"filename": _IMPORT_FILENAME, "sha256": source_hash, "byte_length": len(import_bytes)}


def _assert_confirmation_replay(
    first: MigrationResult,
    retry: MigrationResult,
    before: Mapping[str, int],
    after: Mapping[str, int],
) -> None:
    if (
        first.replayed is not False
        or retry.replayed is not True
        or canonical_json_bytes(retry) != canonical_json_bytes({**_public(first), "replayed": True})
        or before != after
    ):
        raise AssertionError("confirmation replay changed native result or persisted counts")


def _migration_completed_event(
    events: list[dict[str, object]],
    source: FmeaRevision,
    child: FmeaRevision,
    result: MigrationResult,
) -> dict[str, object]:
    expected_payload = {
        "migration_id": result.migration_id,
        "report_hash": result.report_hash,
        "source_revision_id": source.revision_id,
        "source_revision_hash": source.revision_hash,
        "child_revision_id": child.revision_id,
        "child_revision_hash": child.revision_hash,
    }
    matching = [event for event in events if (
        event.get("event_type") == "migration.completed"
        and event.get("workspace_id") == source.workspace_id == child.workspace_id
        and event.get("aggregate_type") == "fmea_governance"
        and event.get("aggregate_id") == child.revision_id == result.child_revision_id
        and isinstance(event.get("payload"), Mapping)
        and all(event["payload"].get(key) == value for key, value in expected_payload.items())
    )]
    if len(matching) != 1:
        raise AssertionError("expected exactly one migration.completed event bound to this migration")
    return matching[0]


def _step(
    *,
    command: str,
    actor: ActorContext,
    request: object,
    idempotency_key: str,
    before: Mapping[str, int],
    after: Mapping[str, int],
    result_ids: Mapping[str, object],
    result: object,
) -> dict[str, object]:
    return {
        "step_id": f"migration-step-{command.replace('.', '-')}",
        "command": command,
        "actor_id": actor.actor_id,
        "actor_type": actor.actor_type.value,
        "request_identity": {
            "request_hash": canonical_hash(_request_identity_value(request)),
            "idempotency_key_hash": idempotency_key_hash(idempotency_key),
        },
        "request": _public(request),
        "before": dict(before),
        "after": dict(after),
        "result_ids": dict(result_ids),
        "result": _public(result),
    }


class _PersistedEvidenceProvider:
    """Template mapping evidence provider backed by the same SQLite database."""

    def __init__(self, database_path: Path) -> None:
        self._repository = SqliteFmeaRepository(database_path)

    def load_pack(self, workspace_id: str, pack_id: str) -> object:
        pack = self._repository.get_evidence_pack(pack_id, workspace_id)
        if pack is None:
            raise ValueError("the source EvidencePack is not persisted")
        return pack


class _DeterministicFuelTemplateGateway:
    """A fake strictly at the model-generation gateway."""

    def generate(self, _request: object) -> object:
        return {
            "diff": (
                {
                    "op": "add",
                    "path": "/fields/legacy_criticality",
                    "value": {"type": "string", "minLength": 1},
                },
                {
                    "op": "add",
                    "path": "/mappings/legacy_criticality",
                    "value": "legacy_criticality",
                },
            ),
            "evidence_ids": ("ref-001",),
        }


class _FuelCombustionMigrationAdapter:
    """Explicit, deterministic example edge for fuel-combustion 1.0 -> 2.0."""

    adapter_id = "fuel-combustion-1-0-0-to-2-0-0"
    source_identity = _SOURCE_PACK_IDENTITY
    target_identity = _TARGET_PACK_IDENTITY

    def __init__(self, target_pack_hash: str, target_template_hash: str) -> None:
        self._target_pack_hash = target_pack_hash
        self._target_template_hash = target_template_hash

    def migrate(self, source: FmeaRevision) -> MigrationCandidate:
        if source.domain_pack_identity[:2] != self.source_identity:
            raise ValueError("fuel adapter source domain identity is not allowlisted")
        template_identities: list[tuple[str, str, str]] = []
        mapped_template = False
        for template_id, version, content_hash in source.template_identities:
            if (template_id, version) == _SOURCE_TEMPLATE_IDENTITY:
                template_identities.append((*_TARGET_TEMPLATE_IDENTITY, self._target_template_hash))
                mapped_template = True
            else:
                template_identities.append((template_id, version, content_hash))
        if not mapped_template:
            raise ValueError("source revision does not contain the fuel FMEA template identity")
        values = {
            field.name: getattr(source, field.name)
            for field in fields(source)
            if field.name not in {"revision_hash", "created_at"}
        }
        values["domain_pack_identity"] = (*self.target_identity, self._target_pack_hash)
        values["template_identities"] = tuple(template_identities)
        values["created_at"] = source.created_at
        provisional = object.__new__(FmeaRevision)
        for field_name, field_value in values.items():
            object.__setattr__(provisional, field_name, field_value)
        values["revision_hash"] = revision_content_hash(provisional)
        target = FmeaRevision(**values)
        return MigrationCandidate(
            target_revision=target,
            mapped_fields=("row_references", "fuel-combustion-fmea:1.0.0->2.0.0"),
            dropped_fields=("legacy-template-version",),
            unresolved_fields=(),
            warnings=("risk and propagation state are invalidated and require re-review",),
        )


def _ensure_source_template(registry: FileTemplateRegistry, compiler: TemplateCompiler) -> object:
    source_bytes = _SOURCE_TEMPLATE.read_bytes()
    compiled = compiler.compile_path(_SOURCE_TEMPLATE)
    try:
        return registry.get(compiled.metadata.template_id, compiled.metadata.version)
    except Exception as error:
        if getattr(error, "code", None) != "TEMPLATE_NOT_FOUND":
            raise
        return registry.register(compiled, source_bytes, _SOURCE_TEMPLATE.suffix.lower())


def _template_service(
    database_path: Path,
    registry_root: Path,
    workspace_id: str,
    clock: Any,
) -> tuple[DomainPackService, FileTemplateRegistry, object]:
    compiler = TemplateCompiler(schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source)
    registry = FileTemplateRegistry(registry_root / "templates")
    base = _ensure_source_template(registry, compiler)
    service = DomainPackService(
        importers={"xlsx": ExcelTemplateImporter(clock=clock)},
        patch_generator=TemplatePatchGenerator(_DeterministicFuelTemplateGateway(), clock=clock),
        evidence_provider=_PersistedEvidenceProvider(database_path),
        compiler=compiler,
        registry=registry,
        workflow_repository=SqliteFmeaDeliveryRepository(database_path),
        clock=clock,
    )
    del workspace_id
    return service, registry, base


def run_migration(
    *,
    database_path: Path,
    source_revision: FmeaRevision,
    registry_root: Path,
    workspace_id: str,
    import_bytes: bytes,
) -> MigrationSliceResult:
    """Import, human-review/register, and migrate one published source snapshot."""

    database_path = Path(database_path)
    registry_root = Path(registry_root)
    if not isinstance(source_revision, FmeaRevision):
        raise TypeError("source_revision must be an FmeaRevision")
    if source_revision.workspace_id != workspace_id:
        raise ValueError("source revision and workspace scope differ")
    if source_revision.domain_pack_identity[:2] != _SOURCE_PACK_IDENTITY:
        raise ValueError("only fuel-combustion 1.0.0 is allowlisted by this helper")
    if type(import_bytes) is not bytes or not import_bytes:
        raise ValueError("import_bytes must contain the real XLSX export bytes")

    repository = SqliteFmeaDeliveryRepository(database_path)
    repository.initialize()
    stored_source = repository.get_revision(source_revision.revision_id, workspace_id)
    if stored_source != source_revision:
        raise ValueError("the supplied source revision is not the committed SQLite revision")
    if repository.get_revision_record_version(source_revision.revision_id, workspace_id) != 1:
        raise ValueError("the committed source revision record version is not 1")

    domain_registry = FileDomainPackRegistry(registry_root / "domain")
    source_pack = domain_registry.get(*_SOURCE_PACK_IDENTITY)
    if source_pack.content_hash != source_revision.domain_pack_identity[2]:
        raise ValueError("the committed source revision is bound to a different source pack")
    target_pack_source = _TARGET_PACK.read_bytes()
    target_pack = load_domain_pack_manifest(target_pack_source)
    if (target_pack.pack_id, target_pack.version) != _TARGET_PACK_IDENTITY:
        raise ValueError("the bundled example target pack identity is invalid")
    domain_registry.register(target_pack, target_pack_source)

    clock = lambda: source_revision.created_at or _UTC_FALLBACK
    template_service, template_registry, base_template = _template_service(
        database_path, registry_root, workspace_id, clock
    )
    template_admin = ActorContext(
        "task8-template-admin", ActorType.HUMAN, frozenset({"template_admin"}), workspace_id
    )
    template_model = ActorContext("task8-template-model", ActorType.MODEL, frozenset(), workspace_id)
    draft_command = ImportTemplateCommand(
        raw_bytes=import_bytes,
        filename=_IMPORT_FILENAME,
        workspace_id=workspace_id,
        idempotency_key=_key(workspace_id, source_revision, "template-import"),
    )
    before = _counts(database_path, workspace_id)
    draft = template_service.import_template(draft_command, template_admin)
    after = _counts(database_path, workspace_id)
    draft, draft_version = template_service.get_draft_record(draft.draft_id, template_admin)
    import_source = _import_source_receipt(_public(draft), import_bytes)
    steps = [
        _step(
            command="fmea.template.import",
            actor=template_admin,
            request=draft_command,
            idempotency_key=draft_command.idempotency_key or "",
            before=before,
            after=after,
            result_ids={"draft_id": draft.draft_id},
            result=draft,
        )
    ]
    import_replay_before = _counts(database_path, workspace_id)
    draft_replay = template_service.import_template(draft_command, template_admin)
    import_replay_after = _counts(database_path, workspace_id)

    evidence_pack_id, evidence_pack_hash = source_revision.evidence_pack_hashes[0]
    suggest_command = SuggestTemplatePatchCommand(
        draft_id=draft.draft_id,
        patch_id=f"fuel-template-patch-{sha256(draft.source_sha256.encode()).hexdigest()[:24]}",
        input_template_version=_SOURCE_TEMPLATE_IDENTITY[1],
        target_template_id=_SOURCE_TEMPLATE_IDENTITY[0],
        target_template_version=_SOURCE_TEMPLATE_IDENTITY[1],
        target_template_hash=base_template.template_hash,
        domain_pack_id=target_pack.pack_id,
        domain_pack_version=target_pack.version,
        domain_pack_hash=target_pack.content_hash,
        evidence_pack_id=evidence_pack_id,
        evidence_pack_hash=evidence_pack_hash,
        run_id=f"fuel-template-map-{sha256(draft.draft_id.encode()).hexdigest()[:24]}",
        trace_id=f"fuel-template-trace-{sha256(import_bytes).hexdigest()[:24]}",
        model_version="task8-deterministic-template-model",
        prompt_version="task8-fuel-template-mapping-v1",
        target_record_version=draft_version,
        idempotency_key=_key(workspace_id, source_revision, "template-suggest"),
    )
    before = _counts(database_path, workspace_id)
    suggestion = template_service.suggest_patch(suggest_command, template_model)
    after = _counts(database_path, workspace_id)
    steps.append(
        _step(
            command="fmea.template.patch.suggest",
            actor=template_model,
            request=suggest_command,
            idempotency_key=suggest_command.idempotency_key or "",
            before=before,
            after=after,
            result_ids={"suggestion_id": suggestion.suggestion_id, "patch_id": suggestion.candidate.patch_id},
            result=suggestion,
        )
    )
    suggestion_replay_before = _counts(database_path, workspace_id)
    suggestion_replay = template_service.suggest_patch(suggest_command, template_model)
    suggestion_replay_after = _counts(database_path, workspace_id)

    accept_command = AcceptTemplatePatchCommand(
        suggestion_id=suggestion.suggestion_id,
        patch_id=suggestion.candidate.patch_id,
        draft_id=draft.draft_id,
        draft_sha256=draft.source_sha256,
        target_template_version=suggestion.candidate.target_template_version,
        target_template_hash=suggestion.candidate.target_template_hash,
        new_template_version=_TARGET_TEMPLATE_IDENTITY[1],
        domain_pack_hash=target_pack.content_hash,
        evidence_pack_hash=evidence_pack_hash,
        confirm_template_change=True,
        expected_patch_version=1,
        idempotency_key=_key(workspace_id, source_revision, "template-accept"),
    )
    before = _counts(database_path, workspace_id)
    registered_template = template_service.accept_patch(accept_command, template_admin)
    after = _counts(database_path, workspace_id)
    registered_template = template_registry.get(*_TARGET_TEMPLATE_IDENTITY)
    steps.append(
        _step(
            command="fmea.template.patch.accept",
            actor=template_admin,
            request=accept_command,
            idempotency_key=accept_command.idempotency_key or "",
            before=before,
            after=after,
            result_ids={
                "decision_id": f"template-patch-decision-{suggestion.candidate.patch_id}",
                "template_id": registered_template.metadata.template_id,
                "template_version": registered_template.metadata.version,
            },
            result=registered_template,
        )
    )
    accept_replay_before = _counts(database_path, workspace_id)
    accepted_replay = template_service.accept_patch(accept_command, template_admin)
    accept_replay_after = _counts(database_path, workspace_id)

    migration_id = _migration_id(workspace_id, source_revision)
    adapter = _FuelCombustionMigrationAdapter(target_pack.content_hash, registered_template.template_hash)
    migration_registry = MigrationRegistry((adapter,))
    migration_service = MigrationService(
        repository,
        migration_registry,
        domain_pack_registry=domain_registry,
        clock=clock,
    )
    dry_run_command = MigrationCommand(
        migration_id=migration_id,
        source_revision_id=source_revision.revision_id,
        source_revision_hash=source_revision.revision_hash,
        target_domain_pack_id=target_pack.pack_id,
        target_domain_pack_version=target_pack.version,
        target_domain_pack_hash=target_pack.content_hash,
        idempotency_key=_key(workspace_id, source_revision, "migration-dry-run"),
        expected_source_version=1,
    )
    migration_actor = template_admin
    before = _counts(database_path, workspace_id)
    report = migration_service.dry_run(dry_run_command, migration_actor)
    after = _counts(database_path, workspace_id)
    steps.append(
        _step(
            command="fmea.migration.dry_run",
            actor=migration_actor,
            request=dry_run_command,
            idempotency_key=dry_run_command.idempotency_key,
            before=before,
            after=after,
            result_ids={"migration_id": migration_id, "report_hash": report.report_hash},
            result=report,
        )
    )
    dry_run_replay_before = _counts(database_path, workspace_id)
    report_replay = migration_service.dry_run(dry_run_command, migration_actor)
    dry_run_replay_after = _counts(database_path, workspace_id)

    confirm_command = ConfirmMigrationCommand(
        migration_id=migration_id,
        report_hash=report.report_hash,
        source_revision_id=source_revision.revision_id,
        source_revision_hash=source_revision.revision_hash,
        target_domain_pack_id=target_pack.pack_id,
        target_domain_pack_version=target_pack.version,
        target_domain_pack_hash=target_pack.content_hash,
        dry_run_command=dry_run_command,
        idempotency_key=_key(workspace_id, source_revision, "migration-confirm"),
        confirm_migration=True,
        expected_report_version=1,
    )
    before = _counts(database_path, workspace_id)
    result = migration_service.confirm(confirm_command, migration_actor)
    after = _counts(database_path, workspace_id)
    if not isinstance(result, MigrationResult):
        raise AssertionError("migration service returned a non-native result")
    child_revision = repository.get_revision(result.child_revision_id, workspace_id)
    if child_revision is None:
        raise AssertionError("confirmed migration child revision was not persisted")
    steps.append(
        _step(
            command="fmea.migration.confirm",
            actor=migration_actor,
            request=confirm_command,
            idempotency_key=confirm_command.idempotency_key,
            before=before,
            after=after,
            result_ids={"migration_id": result.migration_id, "child_revision_id": result.child_revision_id},
            result=result,
        )
    )
    confirm_replay_before = _counts(database_path, workspace_id)
    result_replay = migration_service.confirm(confirm_command, migration_actor)
    confirm_replay_after = _counts(database_path, workspace_id)
    _assert_confirmation_replay(result, result_replay, confirm_replay_before, confirm_replay_after)

    if child_revision.parent_revision_id != source_revision.revision_id:
        raise AssertionError("migration child is not linked to the supplied source revision")
    if child_revision.risk_versions or child_revision.propagation_graph_revision_id is not None:
        raise AssertionError("migration child did not clear invalidated risk/propagation state")
    audits = _records(database_path, "audit_events", "event_json", workspace_id)
    audits.extend(_records(database_path, "fmea_audit_events", "event_json", workspace_id))
    template_audits = _records(database_path, "fmea_template_audit_events", "event_json", workspace_id)
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        outbox_rows = [dict(row) for row in connection.execute(
            "SELECT * FROM fmea_outbox_events WHERE workspace_id=? ORDER BY rowid", (workspace_id,)
        ).fetchall()]
    for row in outbox_rows:
        row["payload"] = json.loads(str(row.pop("payload_json")))

    invalidation_outbox = _migration_completed_event(outbox_rows, source_revision, child_revision, result)
    invalidation_receipt = {
        "source_revision_id": source_revision.revision_id,
        "child_revision_id": child_revision.revision_id,
        "risk_versions_before": _public(source_revision.risk_versions),
        "propagation_graph_revision_id_before": source_revision.propagation_graph_revision_id,
        "risk_invalidated": child_revision.risk_versions == (),
        "propagation_invalidated": child_revision.propagation_graph_revision_id is None
        and child_revision.propagation_graph_hash is None,
        "outbox_event_id": invalidation_outbox["event_id"],
    }
    evidence = {
        "schema_version": "graphrag.fmea.template-migration-lifecycle.v1",
        "case_id": "fuel-combustion",
        "import_source": import_source,
        "template_drafts": [_public(draft)],
        "template_patch_suggestions": [_public(suggestion)],
        "template_patch_decisions": [_public(template_service.decision_for_patch(suggestion.candidate.patch_id, template_admin))],
        "registered_templates": [
            {
                "template_id": registered_template.metadata.template_id,
                "version": registered_template.metadata.version,
                "template_hash": registered_template.template_hash,
                "compiled": _public(registered_template),
            }
        ],
        "migration_reports": [_public(report)],
        "migration_results": [_public(result)],
        "revisions": [_public(child_revision)],
        "invalidation_receipt": invalidation_receipt,
        "audits": audits,
        "template_audits": template_audits,
        "outbox": outbox_rows,
        "steps": steps,
        "replays": [
            {
                "command": "fmea.template.import",
                "first": _public(draft),
                "replayed": _public(draft_replay),
                "same_persisted_result": draft_replay == draft,
                "event_counts_before": import_replay_before,
                "event_counts_after": import_replay_after,
            },
            {
                "command": "fmea.template.patch.suggest",
                "first": _public(suggestion),
                "replayed": _public(suggestion_replay),
                "same_persisted_result": suggestion_replay == suggestion,
                "event_counts_before": suggestion_replay_before,
                "event_counts_after": suggestion_replay_after,
            },
            {
                "command": "fmea.template.patch.accept",
                "first": _public(registered_template),
                "replayed": _public(accepted_replay),
                "same_persisted_result": accepted_replay == registered_template,
                "event_counts_before": accept_replay_before,
                "event_counts_after": accept_replay_after,
            },
            {
                "command": "fmea.migration.dry_run",
                "first": _public(report),
                "replayed": _public(report_replay),
                "same_persisted_result": report_replay == report,
                "event_counts_before": dry_run_replay_before,
                "event_counts_after": dry_run_replay_after,
            },
            {
                "command": "fmea.migration.confirm",
                "first": _public(result),
                "replayed": _public(result_replay),
                # Full canonical native equality (except False -> True replayed)
                # and unchanged persisted counts were enforced above.
                "same_persisted_result": True,
                "event_counts_before": confirm_replay_before,
                "event_counts_after": confirm_replay_after,
                "child_revision_count": repository.count_child_revisions(source_revision.revision_id, workspace_id),
                "migration_confirmation_count": repository.count_migration_confirmations(workspace_id),
            },
        ],
        "authority": {
            "model_can_confirm": False,
            "model_can_approve": False,
            "template_registration_actor_type": template_admin.actor_type.value,
        },
    }
    return MigrationSliceResult(evidence=evidence, child_revision=child_revision)


__all__ = ["MigrationSliceResult", "run_migration"]
