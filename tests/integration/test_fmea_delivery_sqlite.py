from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

HASH = "a" * 64
TARGET_HASH = "b" * 64


class Adapter:
    source_identity = ("fuel-combustion", "1.0.0")
    target_identity = ("fuel-combustion", "2.0.0")

    def migrate(self, source):
        from fmea_application.migration_service import MigrationCandidate

        return MigrationCandidate(
            mapped_fields=("failure_mode", "causes"),
            dropped_fields=("legacy_criticality",),
            unresolved_fields=("operator_note",),
            warnings=("manual review required",),
            target_domain_pack_identity=("fuel-combustion", "2.0.0", TARGET_HASH),
        )


class PackRegistry:
    def get(self, pack_id: str, version: str):
        return type("Pack", (), {"pack_id": pack_id, "version": version, "content_hash": TARGET_HASH})()


@pytest.fixture
def context(tmp_path: Path):
    from fmea_governance_fixtures import (
        make_fmea_revision,
        make_governance_actor,
        prepared_revision,
        seed_authoritative_analysis,
    )

    from fmea_application.migration_service import MigrationCommand, MigrationService
    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository
    from fmea_infrastructure.migration_registry import MigrationRegistry

    path = tmp_path / "fmea.sqlite3"
    repository = SqliteFmeaDeliveryRepository(path)
    repository.initialize()
    seed_authoritative_analysis(path)
    repository.commit_revision(prepared_revision())
    actor = make_governance_actor(actor_id="admin-1", roles=frozenset({"template_admin"}))
    command = MigrationCommand(
        migration_id="migration-1",
        source_revision_id="revision-1",
        source_revision_hash=make_fmea_revision().revision_hash,
        target_domain_pack_id="fuel-combustion",
        target_domain_pack_version="2.0.0",
        target_domain_pack_hash=TARGET_HASH,
        idempotency_key="00000000-0000-4000-8000-000000000903",
    )
    service = MigrationService(
        repository,
        MigrationRegistry((Adapter(),)),
        domain_pack_registry=PackRegistry(),
        clock=lambda: "2026-09-03T00:00:00Z",
    )
    return repository, service, command, actor


def test_additive_010_creates_delivery_tables_without_rewriting_governance_tables(context):
    repository, _, _, _ = context
    with sqlite3.connect(repository.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'fmea_%'")
        }
        assert {
            "fmea_template_drafts",
            "fmea_template_patch_candidates",
            "fmea_template_patch_decisions",
            "fmea_migration_runs",
            "fmea_migration_reports",
            "fmea_migration_confirmations",
            "fmea_export_runs",
            "fmea_export_artifacts",
        } <= tables
        assert connection.execute("SELECT version FROM schema_migrations WHERE version=10").fetchone() is not None


def test_dry_run_is_repeatable_and_does_not_create_revision(context):
    repository, service, command, actor = context

    first = service.dry_run(command, actor)
    second = service.dry_run(command, actor)

    assert first.report_hash == second.report_hash
    assert repository.count_child_revisions("revision-1", "ws-1") == 0
    assert repository.count_outbox_events("migration.completed", "ws-1") == 0


def test_confirm_creates_immutable_child_and_invalidates_derived_state(context):
    from fmea_application.migration_service import ConfirmMigrationCommand

    repository, service, command, actor = context
    report = service.dry_run(command, actor)
    confirmed = service.confirm(
        ConfirmMigrationCommand(
            migration_id=command.migration_id,
            report_hash=report.report_hash,
            source_revision_id=command.source_revision_id,
            source_revision_hash=command.source_revision_hash,
            target_domain_pack_id=command.target_domain_pack_id,
            target_domain_pack_version=command.target_domain_pack_version,
            target_domain_pack_hash=command.target_domain_pack_hash,
            idempotency_key="00000000-0000-4000-8000-000000000904",
            confirm_migration=True,
        ),
        actor,
    )

    child = repository.get_revision(confirmed.child_revision_id, "ws-1")
    source = repository.get_revision("revision-1", "ws-1")
    assert child is not None
    assert source is not None
    assert child.parent_revision_id == source.revision_id
    assert child.parent_revision_hash == source.revision_hash
    assert child.revision_id != source.revision_id
    assert child.domain_pack_identity == ("fuel-combustion", "2.0.0", TARGET_HASH)
    assert child.risk_versions == ()
    assert child.propagation_graph_revision_id is None
    assert child.propagation_graph_hash is None
    assert repository.count_child_revisions("revision-1", "ws-1") == 1
    assert repository.count_outbox_events("migration.completed", "ws-1") == 1


def test_confirmation_replays_without_a_second_child_or_event(context):
    from fmea_application.migration_service import ConfirmMigrationCommand

    repository, service, command, actor = context
    report = service.dry_run(command, actor)
    confirm = ConfirmMigrationCommand(
        migration_id=command.migration_id,
        report_hash=report.report_hash,
        source_revision_id=command.source_revision_id,
        source_revision_hash=command.source_revision_hash,
        target_domain_pack_id=command.target_domain_pack_id,
        target_domain_pack_version=command.target_domain_pack_version,
        target_domain_pack_hash=command.target_domain_pack_hash,
        idempotency_key="00000000-0000-4000-8000-000000000905",
        confirm_migration=True,
    )

    first = service.confirm(confirm, actor)
    second = service.confirm(confirm, actor)

    assert first.child_revision_id == second.child_revision_id
    assert second.replayed is True
    assert repository.count_child_revisions("revision-1", "ws-1") == 1
    assert repository.count_outbox_events("migration.completed", "ws-1") == 1


def test_confirmation_replays_after_repository_restart(context):
    from fmea_application.migration_service import ConfirmMigrationCommand, MigrationService
    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository
    from fmea_infrastructure.migration_registry import MigrationRegistry

    repository, service, command, actor = context
    report = service.dry_run(command, actor)
    confirm = ConfirmMigrationCommand(
        migration_id=command.migration_id,
        report_hash=report.report_hash,
        source_revision_id=command.source_revision_id,
        source_revision_hash=command.source_revision_hash,
        target_domain_pack_id=command.target_domain_pack_id,
        target_domain_pack_version=command.target_domain_pack_version,
        target_domain_pack_hash=command.target_domain_pack_hash,
        idempotency_key="00000000-0000-4000-8000-000000000908",
        confirm_migration=True,
    )

    first = service.confirm(confirm, actor)
    restarted_repository = SqliteFmeaDeliveryRepository(repository.database_path)
    restarted_repository.initialize()
    restarted_service = MigrationService(
        restarted_repository,
        MigrationRegistry((Adapter(),)),
        domain_pack_registry=PackRegistry(),
        clock=lambda: "2026-09-03T00:00:00Z",
    )

    replay = restarted_service.confirm(confirm, actor)

    assert replay.child_revision_id == first.child_revision_id
    assert replay.replayed is True
    assert restarted_repository.count_child_revisions("revision-1", "ws-1") == 1
    assert restarted_repository.count_outbox_events("migration.completed", "ws-1") == 1
    assert restarted_repository.count_migration_confirmations("ws-1") == 1
