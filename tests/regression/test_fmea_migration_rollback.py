from __future__ import annotations

import sqlite3
from dataclasses import fields
from pathlib import Path

import pytest

HASH = "a" * 64
TARGET_HASH = "b" * 64


def _target_revision(source):
    from fmea_governance_fixtures import make_fmea_revision

    values = {field.name: getattr(source, field.name) for field in fields(source) if field.name != "revision_hash"}
    values["domain_pack_identity"] = ("fuel-combustion", "2.0.0", TARGET_HASH)
    return make_fmea_revision(**values)


class FaultingAdapter:
    source_identity = ("fuel-combustion", "1.0.0")
    target_identity = ("fuel-combustion", "2.0.0")

    def migrate(self, source):
        from fmea_application.migration_service import MigrationCandidate

        return MigrationCandidate(target_revision=_target_revision(source))


class PackRegistry:
    def get(self, pack_id: str, version: str):
        content_hash = HASH if version == "1.0.0" else TARGET_HASH
        return type("Pack", (), {"pack_id": pack_id, "version": version, "content_hash": content_hash})()


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

    def fail(step: str) -> None:
        if step == "migration.after_revision":
            raise RuntimeError("injected migration failure")  # noqa: TRY003

    repository = SqliteFmeaDeliveryRepository(path, fault_injector=fail)
    repository.initialize()
    seed_authoritative_analysis(path)
    repository.commit_revision(prepared_revision())
    actor = make_governance_actor(actor_id="admin-1", roles=frozenset({"template_admin"}))
    command = MigrationCommand(
        migration_id="migration-rollback",
        source_revision_id="revision-1",
        source_revision_hash=make_fmea_revision().revision_hash,
        target_domain_pack_id="fuel-combustion",
        target_domain_pack_version="2.0.0",
        target_domain_pack_hash=TARGET_HASH,
        idempotency_key="00000000-0000-4000-8000-000000000906",
    )
    service = MigrationService(
        repository,
        MigrationRegistry((FaultingAdapter(),)),
        domain_pack_registry=PackRegistry(),
        clock=lambda: "2026-09-03T00:00:00Z",
    )
    return repository, service, command, actor


def test_failed_confirmed_migration_rolls_back_child_and_events(context):
    from fmea_application.migration_service import ConfirmMigrationCommand

    repository, service, command, actor = context
    report = service.dry_run(command, actor)
    with sqlite3.connect(repository.database_path) as connection:
        before_idempotency_count = connection.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0]
    confirm = ConfirmMigrationCommand(
        migration_id=command.migration_id,
        report_hash=report.report_hash,
        source_revision_id=command.source_revision_id,
        source_revision_hash=command.source_revision_hash,
        target_domain_pack_id=command.target_domain_pack_id,
        target_domain_pack_version=command.target_domain_pack_version,
        target_domain_pack_hash=command.target_domain_pack_hash,
        idempotency_key="00000000-0000-4000-8000-000000000907",
        confirm_migration=True,
    )

    with pytest.raises(Exception, match="FMEA_MIGRATION_FAILED"):
        service.confirm(confirm, actor)
    assert repository.count_child_revisions("revision-1", "ws-1") == 0
    assert repository.count_outbox_events("migration.completed", "ws-1") == 0
    assert repository.count_migration_confirmations("ws-1") == 0
    with sqlite3.connect(repository.database_path) as connection:
        idempotency_count = connection.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0]
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM fmea_audit_events WHERE workspace_id=? AND command=?",
                ("ws-1", "fmea.migration.confirm"),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM idempotency_records WHERE scope_key IN "
                "(SELECT idempotency_scope FROM fmea_migration_confirmations WHERE workspace_id=?)",
                ("ws-1",),
            ).fetchone()[0]
            == 0
        )
        assert idempotency_count == before_idempotency_count
        assert (
            connection.execute(
                "SELECT status FROM fmea_migration_runs WHERE workspace_id=? AND migration_id=?",
                ("ws-1", command.migration_id),
            ).fetchone()[0]
            == "dry_run"
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM fmea_governance_event_bindings WHERE workspace_id=? "
                "AND resource_type='revision' AND resource_id LIKE 'migration-child-%'",
                ("ws-1",),
            ).fetchone()[0]
            == 0
        )


def test_source_revision_is_unchanged_after_failed_confirmation(context):
    repository, service, command, actor = context
    before = repository.get_revision("revision-1", "ws-1")
    service.dry_run(command, actor)
    assert repository.get_revision("revision-1", "ws-1") == before
