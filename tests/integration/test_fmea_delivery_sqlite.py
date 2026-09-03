from __future__ import annotations

import sqlite3
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path

import pytest

HASH = "a" * 64
TARGET_HASH = "b" * 64
DRIFTED_TARGET_HASH = "c" * 64
MIGRATED_ROW_HASH = "d" * 64
CORRUPTED_REQUEST_KEY = "00000000-0000-4000-8000-000000000999"
CORRUPTED_TIMESTAMP = "2026-09-03T00:00:01Z"


def _target_revision(source, target_hash: str = TARGET_HASH):
    from fmea_governance_fixtures import make_fmea_revision

    values = {field.name: getattr(source, field.name) for field in fields(source) if field.name != "revision_hash"}
    values.update({
        "domain_pack_identity": ("fuel-combustion", "2.0.0", target_hash),
        "row_versions": (("row-migrated", 2, MIGRATED_ROW_HASH),),
        "template_identities": (("fuel-fmea", "2.0.0", MIGRATED_ROW_HASH),),
    })
    return make_fmea_revision(**values)


class Adapter:
    source_identity = ("fuel-combustion", "1.0.0")
    target_identity = ("fuel-combustion", "2.0.0")

    def migrate(self, source):
        from fmea_application.migration_service import MigrationCandidate

        return MigrationCandidate(
            target_revision=_target_revision(source),
            mapped_fields=("failure_mode", "causes"),
            dropped_fields=("legacy_criticality",),
            unresolved_fields=("operator_note",),
            warnings=("manual review required",),
        )


class PackRegistry:
    def __init__(self, target_hash: str = TARGET_HASH):
        self.target_hash = target_hash

    def get(self, pack_id: str, version: str):
        content_hash = HASH if version == "1.0.0" else self.target_hash
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
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_dry_run_is_repeatable_and_does_not_create_revision(context):
    repository, service, command, actor = context

    first = service.dry_run(command, actor)
    second = service.dry_run(command, actor)

    assert first.report_hash == second.report_hash
    assert repository.count_child_revisions("revision-1", "ws-1") == 0
    assert repository.count_outbox_events("migration.completed", "ws-1") == 0


def test_fresh_process_dry_run_binds_the_original_request_key(context):
    from fmea_application.migration_service import MigrationService, MigrationServiceError
    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository
    from fmea_infrastructure.migration_registry import MigrationRegistry

    repository, service, command, actor = context
    first = service.dry_run(command, actor)

    def restarted_service():
        restarted_repository = SqliteFmeaDeliveryRepository(repository.database_path)
        restarted_repository.initialize()
        return MigrationService(
            restarted_repository,
            MigrationRegistry((Adapter(),)),
            domain_pack_registry=PackRegistry(),
            clock=lambda: "2026-09-03T00:00:00Z",
        )

    replay = restarted_service().dry_run(command, actor)
    assert replay == first

    with sqlite3.connect(repository.database_path) as connection:
        before = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in (
                "fmea_migration_runs",
                "fmea_migration_reports",
                "fmea_migration_confirmations",
                "fmea_revisions",
                "fmea_audit_events",
                "fmea_outbox_events",
            )
        )

    different_key = replace(command, idempotency_key="00000000-0000-4000-8000-000000000998")
    with pytest.raises(MigrationServiceError, match="FMEA_MIGRATION_IDEMPOTENCY_CONFLICT"):
        restarted_service().dry_run(different_key, actor)

    with sqlite3.connect(repository.database_path) as connection:
        after = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in (
                "fmea_migration_runs",
                "fmea_migration_reports",
                "fmea_migration_confirmations",
                "fmea_revisions",
                "fmea_audit_events",
                "fmea_outbox_events",
            )
        )
    assert after == before


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
            dry_run_command=command,
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
    assert child.row_versions == (("row-migrated", 2, MIGRATED_ROW_HASH),)
    assert child.template_identities == (("fuel-fmea", "2.0.0", MIGRATED_ROW_HASH),)
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
        dry_run_command=command,
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
        dry_run_command=command,
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


def test_confirmation_replay_rejects_corrupted_durable_run_chain(context):
    from fmea_application.migration_service import ConfirmMigrationCommand, MigrationServiceError

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
        dry_run_command=command,
        idempotency_key="00000000-0000-4000-8000-000000000909",
        confirm_migration=True,
    )
    service.confirm(confirm, actor)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_migration_runs_immutable_fields")
        connection.execute("DROP TRIGGER fmea_migration_runs_terminal_no_update")
        request_json = connection.execute(
            "SELECT request_json FROM fmea_migration_runs WHERE workspace_id=? AND migration_id=?",
            ("ws-1", command.migration_id),
        ).fetchone()[0]
        corrupted_json = request_json.replace(command.idempotency_key, CORRUPTED_REQUEST_KEY)
        connection.execute(
            "UPDATE fmea_migration_runs SET request_json=?,request_hash=?,request_idempotency_key_hash=? "
            "WHERE workspace_id=? AND migration_id=?",
            (
                corrupted_json,
                "sha256:" + sha256(corrupted_json.encode("utf-8")).hexdigest(),
                "sha256:" + sha256(CORRUPTED_REQUEST_KEY.encode("utf-8")).hexdigest(),
                "ws-1",
                command.migration_id,
            ),
        )

    with pytest.raises(MigrationServiceError, match="FMEA_MIGRATION_STORAGE_UNAVAILABLE"):
        service.confirm(confirm, actor)
    assert repository.count_child_revisions("revision-1", "ws-1") == 1
    assert repository.count_outbox_events("migration.completed", "ws-1") == 1
    assert repository.count_migration_confirmations("ws-1") == 1


@pytest.mark.parametrize(
    ("table", "trigger", "identity_column", "confirmation_column"),
    (
        (
            "fmea_migration_confirmations",
            "fmea_migration_confirmations_no_update",
            "confirmation_id",
            "confirmation_id",
        ),
        ("fmea_revisions", "fmea_revisions_no_update", "revision_id", "child_revision_id"),
        ("fmea_audit_events", "fmea_audit_events_no_update", "event_id", "audit_event_id"),
        ("fmea_outbox_events", "fmea_outbox_events_no_update", "event_id", "outbox_event_id"),
    ),
)
def test_confirmation_replay_rejects_dedicated_timestamp_corruption(
    context, table, trigger, identity_column, confirmation_column
):
    from fmea_application.migration_service import ConfirmMigrationCommand, MigrationServiceError

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
        dry_run_command=command,
        idempotency_key="00000000-0000-4000-8000-000000000911",
        confirm_migration=True,
    )
    service.confirm(confirm, actor)
    with sqlite3.connect(repository.database_path) as connection:
        connection.row_factory = sqlite3.Row
        confirmation = connection.execute(
            "SELECT * FROM fmea_migration_confirmations WHERE workspace_id=? AND migration_id=?",
            ("ws-1", command.migration_id),
        ).fetchone()
        connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute(
            f"UPDATE {table} SET created_at=? WHERE workspace_id=? AND {identity_column}=?",  # noqa: S608
            (CORRUPTED_TIMESTAMP, "ws-1", confirmation[confirmation_column]),
        )

    with pytest.raises(MigrationServiceError, match="FMEA_MIGRATION_FAILED"):
        service.confirm(confirm, actor)
    assert repository.count_child_revisions("revision-1", "ws-1") == 1
    assert repository.count_outbox_events("migration.completed", "ws-1") == 1


def test_fresh_process_target_hash_drift_never_creates_child_or_event(context):
    from fmea_application.migration_service import ConfirmMigrationCommand, MigrationCandidate, MigrationService
    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository
    from fmea_infrastructure.migration_registry import MigrationRegistry

    repository, service, command, actor = context
    report = service.dry_run(command, actor)

    class DriftedAdapter(Adapter):
        def migrate(self, source):
            return MigrationCandidate(target_revision=_target_revision(source, DRIFTED_TARGET_HASH))

    restarted_repository = SqliteFmeaDeliveryRepository(repository.database_path)
    restarted_repository.initialize()
    restarted_service = MigrationService(
        restarted_repository,
        MigrationRegistry((DriftedAdapter(),)),
        domain_pack_registry=PackRegistry(DRIFTED_TARGET_HASH),
        clock=lambda: "2026-09-03T00:00:00Z",
    )
    confirm = ConfirmMigrationCommand(
        migration_id=command.migration_id,
        report_hash=report.report_hash,
        source_revision_id=command.source_revision_id,
        source_revision_hash=command.source_revision_hash,
        target_domain_pack_id=command.target_domain_pack_id,
        target_domain_pack_version=command.target_domain_pack_version,
        target_domain_pack_hash=command.target_domain_pack_hash,
        dry_run_command=command,
        idempotency_key="00000000-0000-4000-8000-000000000910",
        confirm_migration=True,
    )

    with pytest.raises(Exception, match="FMEA_MIGRATION_TARGET_STALE"):
        restarted_service.confirm(confirm, actor)
    assert restarted_repository.count_child_revisions("revision-1", "ws-1") == 0
    assert restarted_repository.count_outbox_events("migration.completed", "ws-1") == 0


def test_migration_run_source_revision_fk_is_workspace_scoped(context):
    repository, service, command, actor = context
    service.dry_run(command, actor)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for table in ("fmea_migration_runs", "fmea_migration_reports", "fmea_migration_confirmations"):
            foreign_keys = connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            source_fk = {(row[3], row[4]) for row in foreign_keys if row[2] == "fmea_revisions"}
            assert {("workspace_id", "workspace_id"), ("source_revision_id", "revision_id")} <= source_fk
        source = connection.execute(
            "SELECT * FROM fmea_migration_runs WHERE workspace_id=? AND migration_id=?",
            ("ws-1", command.migration_id),
        ).fetchone()
        columns = [item[1] for item in connection.execute("PRAGMA table_info(fmea_migration_runs)")]
        values = dict(zip(columns, source, strict=True))
        values.update({
            "workspace_id": "ws-foreign",
            "migration_id": "migration-foreign",
            "run_id": "migration-run-foreign",
        })
        placeholders = ",".join("?" for _ in columns)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute(
                f"INSERT INTO fmea_migration_runs ({','.join(columns)}) VALUES ({placeholders})",  # noqa: S608
                tuple(values[column] for column in columns),
            )
            connection.commit()
        connection.rollback()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
