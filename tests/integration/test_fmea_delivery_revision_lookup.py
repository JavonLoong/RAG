"""Focused SQLite tests for exact revision-bound delivery snapshots."""

from __future__ import annotations

import io
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from openpyxl import Workbook

from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.governance import FmeaRevision
from core_domain.fmea.states import ActorType
from fmea_application.domain_pack_service import ImportTemplateCommand
from fmea_application.export_service import ExportServiceError
from fmea_application.governance_contracts import (
    AssembleRevisionCommand,
    PreparedRevision,
    canonical_governance_payload,
    governance_payload_hash,
)
from fmea_application.migration_service import (
    CompatibilityCommand,
    ConfirmMigrationCommand,
    MigrationCandidate,
    MigrationCommand,
)
from fmea_application.review_contracts import ActorContext
from fmea_infrastructure.composition import build_default_workspace_delivery_runtime
from fmea_infrastructure.domain_pack_registry import (
    domain_pack_content_hash,
    load_domain_pack_manifest,
)
from fmea_infrastructure.governance_repository_sqlite import SqliteGovernanceRepository
from tests.fmea_governance_fixtures import (
    _prepared_events,
    _scope,
    make_assemble_request,
    make_fmea_revision,
    make_governance_actor,
    seed_authoritative_analysis,
)
from tests.integration.test_fmea_governance_sqlite import (
    _commit_publication_with_authority_chain,
    _prepared_publication_bundle,
)


def _workspace(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        workspace_id="ws-1",
        chroma_persist_dir=tmp_path / "chroma",
        fmea_db_path=tmp_path / "fmea" / "fmea.sqlite3",
        fmea_template_registry_path=tmp_path / "fmea" / "templates",
        graph_db_path=tmp_path / "graph.sqlite3",
    )


def _target_domain_pack() -> tuple[DomainPackManifest, bytes]:
    bundled_path = Path(__file__).resolve().parents[2] / "domain_packs" / "fuel-combustion" / "manifest.yaml"
    source_manifest = load_domain_pack_manifest(bundled_path.read_bytes())
    target_without_hash = replace(source_manifest, version="1.1.0", content_hash="0" * 64)
    target_manifest = replace(target_without_hash, content_hash=domain_pack_content_hash(target_without_hash))
    source = yaml.safe_dump(
        {
            "domain_pack": {
                "id": target_manifest.pack_id,
                "version": target_manifest.version,
                "content_hash": target_manifest.content_hash,
                "kernel_compatibility_range": target_manifest.kernel_compatibility_range,
                "compatible_schema_ids": list(target_manifest.compatible_schema_ids),
                "analysis_types": list(target_manifest.analysis_types),
                "templates": [
                    {"id": item_id, "version": version}
                    for item_id, version in target_manifest.template_identities
                ],
                "scoring_rules": [
                    {"id": item_id, "version": version}
                    for item_id, version in target_manifest.scoring_rule_identities
                ],
                "propagation_rules": [
                    {"id": item_id, "version": version}
                    for item_id, version in target_manifest.propagation_rule_identities
                ],
                "extension_fields": [
                    {"key": key, "type": value_type}
                    for key, value_type in target_manifest.extension_fields
                ],
            }
        },
        sort_keys=False,
    ).encode("utf-8")
    assert load_domain_pack_manifest(source) == target_manifest
    return target_manifest, source


def _prepared_revision_for(revision: FmeaRevision) -> PreparedRevision:
    key = "00000000-0000-4000-8000-000000000961"
    actor = make_governance_actor(actor_id="assembler-1", roles=frozenset({"assembler"}))
    command = AssembleRevisionCommand(request=make_assemble_request(), idempotency_key=key)
    scope = _scope(actor, "fmea.revision.assemble", f"/fmea/analyses/{revision.analysis_id}/revisions", key)
    payload = canonical_governance_payload("revision.assemble", command, revision=revision)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, revision.revision_id)
    return PreparedRevision(
        scope=scope,
        payload_hash=payload_hash,
        command=command,
        expected_analysis_version=revision.analysis_record_version,
        revision=revision,
        audit=audit,
        outbox=outbox,
    )


class _PersistedRegistryMigrationAdapter:
    source_identity = ("fuel-combustion", "1.0.0")

    def __init__(self, target_manifest: DomainPackManifest) -> None:
        self.target_identity = (target_manifest.pack_id, target_manifest.version)
        self._target_hash = target_manifest.content_hash

    def migrate(self, source: FmeaRevision) -> MigrationCandidate:
        values = {
            field.name: getattr(source, field.name)
            for field in fields(source)
            if field.name != "revision_hash"
        }
        values["domain_pack_identity"] = (*self.target_identity, self._target_hash)
        return MigrationCandidate(
            target_revision=make_fmea_revision(**values),
            mapped_fields=("failure_mode",),
        )


class _FailIfNarrativeGenerated:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request: object) -> object:
        del request
        self.calls += 1
        raise AssertionError("narrative generator must not run for a stale snapshot binding")  # noqa: TRY003


def test_revision_lookup_is_workspace_and_revision_exact(tmp_path: Path) -> None:
    database_path = tmp_path / "fmea.sqlite3"
    repository = SqliteGovernanceRepository(database_path)
    repository.initialize()
    seed_authoritative_analysis(database_path)

    revision_a = make_fmea_revision(revision_id="revision-1")
    revision_b = make_fmea_revision(
        revision_id="revision-2",
        parent_revision_id=revision_a.revision_id,
        parent_revision_hash=revision_a.revision_hash,
    )
    publication_a = _prepared_publication_bundle(revision_a, "publication-a", "a", "00000000-0000-4000-8000-000000000951")
    publication_b = _prepared_publication_bundle(
        revision_b,
        "publication-b",
        "b",
        "00000000-0000-4000-8000-000000000952",
        previous_audit_chain_head=publication_a.publication.audit_chain_head,
    )
    _commit_publication_with_authority_chain(repository, publication_a)
    _commit_publication_with_authority_chain(repository, publication_b)

    assert repository.get_snapshot_for_revision(revision_a.revision_id, "ws-1") == publication_a.snapshot
    assert repository.get_snapshot_for_revision(revision_b.revision_id, "ws-1") == publication_b.snapshot
    assert repository.get_snapshot_for_revision(revision_a.revision_id, "other-workspace") is None
    assert repository.get_snapshot_for_revision("revision-missing", "ws-1") is None


def test_revision_lookup_fails_when_persisted_revision_binding_is_ambiguous(tmp_path: Path) -> None:
    database_path = tmp_path / "fmea.sqlite3"
    repository = SqliteGovernanceRepository(database_path)
    repository.initialize()
    seed_authoritative_analysis(database_path)

    revision = make_fmea_revision(revision_id="revision-1")
    first = _prepared_publication_bundle(revision, "publication-a", "a", "00000000-0000-4000-8000-000000000953")
    second = _prepared_publication_bundle(
        revision,
        "publication-b",
        "b",
        "00000000-0000-4000-8000-000000000954",
        previous_audit_chain_head=first.publication.audit_chain_head,
    )
    _commit_publication_with_authority_chain(repository, first)
    _commit_publication_with_authority_chain(repository, second)

    with pytest.raises(ValueError, match="revision snapshot lookup is ambiguous"):
        repository.get_snapshot_for_revision(revision.revision_id, "ws-1")


def test_composite_delivery_runtime_reloads_template_draft_after_restart(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workbook = Workbook()
    workbook.active.append(["Failure Mode", "Cause"])
    payload = io.BytesIO()
    workbook.save(payload)
    workbook.close()
    actor = ActorContext("template-admin-1", ActorType.HUMAN, frozenset({"template_admin"}), "ws-1")

    first_runtime = build_default_workspace_delivery_runtime(workspace, migration_adapters=())
    try:
        first = first_runtime.domain_pack_service.import_template(
            ImportTemplateCommand(
                raw_bytes=payload.getvalue(),
                filename="imported-template.xlsx",
                workspace_id="ws-1",
                idempotency_key="00000000-0000-4000-8000-000000000955",
            ),
            actor,
        )
    finally:
        first_runtime.close()

    second_runtime = build_default_workspace_delivery_runtime(workspace, migration_adapters=())
    try:
        reloaded, record_version = second_runtime.domain_pack_service.get_draft_record(first.draft_id, actor)
    finally:
        second_runtime.close()

    assert reloaded == first
    assert record_version == 1


def test_default_composite_migration_uses_persisted_packs_across_restart(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    target_manifest, target_source = _target_domain_pack()
    adapter = _PersistedRegistryMigrationAdapter(target_manifest)
    actor = make_governance_actor(actor_id="admin-1", roles=frozenset({"template_admin"}))
    source_manifest = load_domain_pack_manifest(
        (Path(__file__).resolve().parents[2] / "domain_packs" / "fuel-combustion" / "manifest.yaml").read_bytes()
    )
    source_revision = make_fmea_revision(
        domain_pack_identity=(source_manifest.pack_id, source_manifest.version, source_manifest.content_hash),
    )

    first_runtime = build_default_workspace_delivery_runtime(
        workspace,
        migration_adapters=(adapter,),
        clock=lambda: "2026-09-04T00:00:00Z",
    )
    try:
        registry = first_runtime.migration_runtime.domain_pack_registry
        registry.register(target_manifest, target_source)
        assert registry.get(target_manifest.pack_id, target_manifest.version) == target_manifest
        assert registry.get_source_bytes(target_manifest.pack_id, target_manifest.version) == target_source

        database_path = first_runtime.migration_runtime.repository.database_path
        seed_authoritative_analysis(database_path)
        first_runtime.migration_runtime.repository.commit_revision(_prepared_revision_for(source_revision))
        compatibility = first_runtime.migration_service.compatibility(
            CompatibilityCommand(
                source_domain_pack_id=source_manifest.pack_id,
                source_domain_pack_version=source_manifest.version,
                target_domain_pack_id=target_manifest.pack_id,
                target_domain_pack_version=target_manifest.version,
                target_domain_pack_hash=target_manifest.content_hash,
                idempotency_key="00000000-0000-4000-8000-000000000956",
            ),
            actor,
        )
        assert compatibility.compatible is True

        dry_run_command = MigrationCommand(
            migration_id="migration-persisted-pack-1",
            source_revision_id=source_revision.revision_id,
            source_revision_hash=source_revision.revision_hash,
            target_domain_pack_id=target_manifest.pack_id,
            target_domain_pack_version=target_manifest.version,
            target_domain_pack_hash=target_manifest.content_hash,
            idempotency_key="00000000-0000-4000-8000-000000000957",
        )
        report = first_runtime.migration_service.dry_run(dry_run_command, actor)
    finally:
        first_runtime.close()

    second_runtime = build_default_workspace_delivery_runtime(
        workspace,
        migration_adapters=(_PersistedRegistryMigrationAdapter(target_manifest),),
        clock=lambda: "2026-09-04T00:00:01Z",
    )
    try:
        registry = second_runtime.migration_runtime.domain_pack_registry
        assert registry.get(target_manifest.pack_id, target_manifest.version) == target_manifest
        assert registry.get_source_bytes(target_manifest.pack_id, target_manifest.version) == target_source
        result = second_runtime.migration_service.confirm(
            ConfirmMigrationCommand(
                migration_id=dry_run_command.migration_id,
                report_hash=report.report_hash,
                source_revision_id=dry_run_command.source_revision_id,
                source_revision_hash=dry_run_command.source_revision_hash,
                target_domain_pack_id=dry_run_command.target_domain_pack_id,
                target_domain_pack_version=dry_run_command.target_domain_pack_version,
                target_domain_pack_hash=dry_run_command.target_domain_pack_hash,
                dry_run_command=dry_run_command,
                idempotency_key="00000000-0000-4000-8000-000000000958",
                confirm_migration=True,
            ),
            actor,
        )
    finally:
        second_runtime.close()

    assert result.migration_id == dry_run_command.migration_id
    assert result.replayed is False


def test_narrative_revision_lookup_rejects_wrong_optional_snapshot_before_generation(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    generator = _FailIfNarrativeGenerated()
    runtime = build_default_workspace_delivery_runtime(
        workspace,
        migration_adapters=(),
        narrative_generator=generator,
    )
    try:
        database_path = runtime.export_runtime.repository.database_path
        seed_authoritative_analysis(database_path)
        revision_a = make_fmea_revision(revision_id="revision-1")
        revision_b = make_fmea_revision(
            revision_id="revision-2",
            parent_revision_id=revision_a.revision_id,
            parent_revision_hash=revision_a.revision_hash,
        )
        publication_a = _prepared_publication_bundle(
            revision_a,
            "publication-a",
            "a",
            "00000000-0000-4000-8000-000000000959",
        )
        publication_b = _prepared_publication_bundle(
            revision_b,
            "publication-b",
            "b",
            "00000000-0000-4000-8000-000000000960",
            previous_audit_chain_head=publication_a.publication.audit_chain_head,
        )
        _commit_publication_with_authority_chain(runtime.export_runtime.repository, publication_a)
        _commit_publication_with_authority_chain(runtime.export_runtime.repository, publication_b)
        actor = ActorContext("model-1", ActorType.MODEL, frozenset(), "ws-1")

        with pytest.raises(ExportServiceError, match="FMEA_EXPORT_SNAPSHOT_STALE"):
            runtime.export_service.suggest_narrative_for_revision(
                revision_a.revision_id,
                actor,
                snapshot_id=publication_b.snapshot.snapshot_id,
            )
    finally:
        runtime.close()

    assert generator.calls == 0
