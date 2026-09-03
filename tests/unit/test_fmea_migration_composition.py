"""Focused tests for workspace migration runtime composition."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fmea_application.migration_service import (
    CompatibilityCommand,
    MigrationCandidate,
    MigrationCommand,
)
from fmea_infrastructure.composition import MigrationRuntime, build_workspace_migration_runtime
from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository
from tests.fmea_governance_fixtures import (
    make_fmea_revision,
    make_governance_actor,
    prepared_revision,
    seed_authoritative_analysis,
)

TARGET_HASH = "b" * 64


class _MigrationAdapter:
    source_identity = ("fuel-combustion", "1.0.0")
    target_identity = ("fuel-combustion", "2.0.0")

    def migrate(self, source: object) -> MigrationCandidate:
        return MigrationCandidate(
            target_domain_pack_identity=("fuel-combustion", "2.0.0", TARGET_HASH),
            mapped_fields=("failure_mode",),
        )


class _DomainPackRegistry:
    def get(self, pack_id: str, version: str) -> object:
        return SimpleNamespace(pack_id=pack_id, version=version, content_hash=TARGET_HASH)


def test_workspace_migration_runtime_wires_explicit_adapter_and_callable_paths(tmp_path: Path) -> None:
    workspace = SimpleNamespace(
        chroma_persist_dir=tmp_path / "chroma",
        fmea_db_path=tmp_path / "fmea" / "fmea.sqlite3",
        fmea_template_registry_path=tmp_path / "fmea" / "templates",
        graph_db_path=tmp_path / "graph.sqlite3",
    )
    adapter = _MigrationAdapter()
    domain_pack_registry = _DomainPackRegistry()

    runtime = build_workspace_migration_runtime(
        workspace,
        domain_pack_registry=domain_pack_registry,
        migration_adapters=(adapter,),
        clock=lambda: "2026-09-03T00:00:00Z",
    )

    assert isinstance(runtime, MigrationRuntime)
    assert isinstance(runtime.repository, SqliteFmeaDeliveryRepository)
    assert runtime.repository.database_path == (tmp_path / "fmea" / "fmea.sqlite3").resolve()
    assert runtime.template_registry_root == (tmp_path / "fmea" / "templates").resolve()
    assert runtime.domain_pack_registry is domain_pack_registry
    assert runtime.migration_registry.adapters == (adapter,)

    seed_authoritative_analysis(runtime.repository.database_path)
    runtime.repository.commit_revision(prepared_revision())
    actor = make_governance_actor(actor_id="admin-1", roles=frozenset({"template_admin"}))

    compatibility = runtime.service.compatibility(
        CompatibilityCommand(
            source_domain_pack_id="fuel-combustion",
            source_domain_pack_version="1.0.0",
            target_domain_pack_id="fuel-combustion",
            target_domain_pack_version="2.0.0",
            target_domain_pack_hash=TARGET_HASH,
            idempotency_key="00000000-0000-4000-8000-000000000921",
        ),
        actor,
    )
    assert compatibility.compatible is True

    report = runtime.service.dry_run(
        MigrationCommand(
            migration_id="migration-composition-1",
            source_revision_id="revision-1",
            source_revision_hash=make_fmea_revision().revision_hash,
            target_domain_pack_id="fuel-combustion",
            target_domain_pack_version="2.0.0",
            target_domain_pack_hash=TARGET_HASH,
            idempotency_key="00000000-0000-4000-8000-000000000922",
        ),
        actor,
    )
    assert report.mapped_fields == ("failure_mode",)
