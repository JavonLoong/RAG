from __future__ import annotations

from dataclasses import replace
from importlib.util import find_spec

import pytest

HASH = "a" * 64
TARGET_HASH = "b" * 64


def _actor(*, actor_type: str = "human", roles: tuple[str, ...] = ("template_admin",)):
    from core_domain.fmea.states import ActorType
    from fmea_application.review_contracts import ActorContext

    return ActorContext("admin-1", ActorType(actor_type), frozenset(roles), "ws-1")


def _command(*, key: str = "00000000-0000-4000-8000-000000000901", source_hash: str | None = None):
    from fmea_governance_fixtures import make_fmea_revision

    from fmea_application.migration_service import MigrationCommand

    if source_hash is None:
        source_hash = make_fmea_revision().revision_hash

    return MigrationCommand(
        migration_id="migration-1",
        source_revision_id="revision-1",
        source_revision_hash=source_hash,
        target_domain_pack_id="fuel-combustion",
        target_domain_pack_version="2.0.0",
        target_domain_pack_hash=TARGET_HASH,
        idempotency_key=key,
    )


class _PackRegistry:
    def get(self, pack_id: str, version: str):
        assert (pack_id, version) == ("fuel-combustion", "2.0.0")
        return type("Pack", (), {"pack_id": pack_id, "version": version, "content_hash": TARGET_HASH})()


class _Adapter:
    source_identity = ("fuel-combustion", "1.0.0")
    target_identity = ("fuel-combustion", "2.0.0")

    def migrate(self, source):
        from fmea_application.migration_service import MigrationCandidate

        return MigrationCandidate(
            mapped_fields=("failure_mode",),
            dropped_fields=(),
            unresolved_fields=(),
            target_domain_pack_identity=("fuel-combustion", "2.0.0", TARGET_HASH),
        )


class _CountingAdapter(_Adapter):
    def __init__(self):
        self.calls = 0

    def migrate(self, source):
        self.calls += 1
        return super().migrate(source)


class _FailingAdapter(_Adapter):
    def migrate(self, source):
        raise RuntimeError("adapter secret must not escape")  # noqa: TRY003


class _WrongTargetHashAdapter(_Adapter):
    def migrate(self, source):
        return replace(
            super().migrate(source),
            target_domain_pack_identity=("fuel-combustion", "2.0.0", "c" * 64),
        )


class _Repository:
    def __init__(self, revision):
        self.revision = revision
        self.reports = {}
        self.prepared = None

    def get_revision(self, revision_id, workspace_id):
        if (revision_id, workspace_id) == (self.revision.revision_id, self.revision.workspace_id):
            return self.revision
        return None

    def get_revision_record_version(self, revision_id, workspace_id):
        return 1 if self.get_revision(revision_id, workspace_id) is not None else None

    def save_migration_report(self, report, *, command, actor):
        self.reports[report.migration_id] = report
        return report

    def get_migration_report(self, migration_id, workspace_id):
        return self.reports.get(migration_id)

    def commit_migration(self, prepared):
        from fmea_application.migration_service import MigrationResult

        self.prepared = prepared
        return MigrationResult(
            migration_id=prepared.command.migration_id,
            child_revision_id="revision-child",
            report_hash=prepared.report.report_hash,
        )


def _service(adapter=None, repository=None):
    from fmea_governance_fixtures import make_fmea_revision

    from fmea_application.migration_service import MigrationService
    from fmea_infrastructure.migration_registry import MigrationRegistry

    repository = repository or _Repository(make_fmea_revision())
    service = MigrationService(
        repository,
        MigrationRegistry((adapter or _Adapter(),)),
        domain_pack_registry=_PackRegistry(),
        clock=lambda: "2026-09-03T00:00:00Z",
    )
    return service, repository


def test_task3_migration_service_module_is_available_after_implementation():
    assert find_spec("fmea_application.migration_service") is not None


def test_dry_run_is_repeatable_and_does_not_create_revision():
    service, repository = _service()

    first = service.dry_run(_command(), _actor())
    second = service.dry_run(_command(), _actor())

    assert first.report_hash == second.report_hash
    assert first.status.value == "dry_run"
    assert repository.revision.revision_id == "revision-1"


def test_registry_and_service_reject_model_or_non_admin_actors():
    service, _ = _service()

    with pytest.raises(Exception, match="FMEA_MIGRATION"):
        service.dry_run(_command(), _actor(actor_type="model"))
    with pytest.raises(Exception, match="FMEA_MIGRATION"):
        service.dry_run(_command(), _actor(roles=("reviewer",)))


def test_stale_source_hash_fails_closed():
    service, _ = _service()

    with pytest.raises(Exception, match="FMEA_MIGRATION_SOURCE_STALE"):
        service.dry_run(_command(source_hash="c" * 64), _actor())


def test_confirm_requires_the_exact_dry_run_report_hash():
    service, _ = _service()
    report = service.dry_run(_command(), _actor())

    from fmea_application.migration_service import ConfirmMigrationCommand

    command = ConfirmMigrationCommand(
        migration_id="migration-1",
        report_hash="c" * 64,
        source_revision_id="revision-1",
        source_revision_hash=report.source_revision_hash,
        target_domain_pack_id="fuel-combustion",
        target_domain_pack_version="2.0.0",
        target_domain_pack_hash=TARGET_HASH,
        idempotency_key="00000000-0000-4000-8000-000000000902",
        confirm_migration=True,
    )
    assert report.report_hash != command.report_hash
    with pytest.raises(Exception, match="FMEA_MIGRATION"):
        service.confirm(command, _actor())


def test_registry_resolves_one_path_and_rejects_ambiguous_or_cyclic_graphs():
    from fmea_infrastructure.migration_registry import MigrationRegistry, MigrationRegistryError

    class Edge(_Adapter):
        def __init__(self, source, target, adapter_id):
            self.source_identity = ("fuel-combustion", source)
            self.target_identity = ("fuel-combustion", target)
            self.adapter_id = adapter_id

    registry = MigrationRegistry((
        Edge("1.0.0", "1.1.0", "edge-a"),
        Edge("1.1.0", "2.0.0", "edge-b"),
    ))
    assert tuple(
        step.adapter_id for step in registry.resolve(("fuel-combustion", "1.0.0"), ("fuel-combustion", "2.0.0")).steps
    ) == (
        "edge-a",
        "edge-b",
    )

    ambiguous = MigrationRegistry((
        Edge("1.0.0", "2.0.0", "edge-a"),
        Edge("1.0.0", "1.1.0", "edge-b"),
        Edge("1.1.0", "2.0.0", "edge-c"),
    ))
    with pytest.raises(MigrationRegistryError, match="FMEA_MIGRATION_EDGE_AMBIGUOUS"):
        ambiguous.resolve(("fuel-combustion", "1.0.0"), ("fuel-combustion", "2.0.0"))

    cyclic = MigrationRegistry((Edge("1.0.0", "2.0.0", "edge-a"), Edge("2.0.0", "1.0.0", "edge-b")))
    with pytest.raises(MigrationRegistryError, match="FMEA_MIGRATION_EDGE_CYCLIC"):
        cyclic.resolve(("fuel-combustion", "1.0.0"), ("fuel-combustion", "2.0.0"))


def test_migration_contracts_reject_unbounded_hashes_and_noncanonical_idempotency():
    from fmea_application.migration_service import MigrationCandidate

    with pytest.raises(ValueError):
        _command(source_hash="not-a-hash")
    with pytest.raises(ValueError):
        _command(key="00000000-0000-4000-8000-00000000090A")
    with pytest.raises(ValueError):
        MigrationCandidate(
            mapped_fields=("x",) * 513,
            target_domain_pack_identity=("fuel-combustion", "2.0.0", TARGET_HASH),
        )


def test_dry_run_replays_stored_report_without_reinvoking_adapter():
    adapter = _CountingAdapter()
    service, repository = _service(adapter=adapter)

    first = service.dry_run(_command(), _actor())
    second = service.dry_run(_command(), _actor())

    assert first == second
    assert adapter.calls == 1
    assert repository.prepared is None


def test_adapter_and_storage_failures_are_safe_migration_errors():
    service, _ = _service(adapter=_FailingAdapter())
    with pytest.raises(Exception, match="FMEA_MIGRATION_ADAPTER_FAILED") as adapter_error:
        service.dry_run(_command(), _actor())
    assert "adapter secret" not in str(adapter_error.value)

    class BrokenRepository(_Repository):
        def get_revision(self, revision_id, workspace_id):
            raise RuntimeError("database secret")  # noqa: TRY003

    service, _ = _service(repository=BrokenRepository(None))
    with pytest.raises(Exception, match="FMEA_MIGRATION_STORAGE_UNAVAILABLE") as storage_error:
        service.dry_run(_command(), _actor())
    assert "database secret" not in str(storage_error.value)


def test_dry_run_rejects_an_adapter_candidate_with_the_wrong_target_hash():
    service, _ = _service(adapter=_WrongTargetHashAdapter())

    with pytest.raises(Exception, match="FMEA_MIGRATION_ADAPTER_INVALID"):
        service.dry_run(_command(), _actor())


def test_confirm_delegates_one_prepared_atomic_migration_unit():
    service, repository = _service()
    dry_command = _command()
    report = service.dry_run(dry_command, _actor())

    from fmea_application.migration_service import ConfirmMigrationCommand

    result = service.confirm(
        ConfirmMigrationCommand(
            migration_id=dry_command.migration_id,
            report_hash=report.report_hash,
            source_revision_id=dry_command.source_revision_id,
            source_revision_hash=dry_command.source_revision_hash,
            target_domain_pack_id=dry_command.target_domain_pack_id,
            target_domain_pack_version=dry_command.target_domain_pack_version,
            target_domain_pack_hash=dry_command.target_domain_pack_hash,
            idempotency_key="00000000-0000-4000-8000-000000000902",
            confirm_migration=True,
        ),
        _actor(),
    )

    assert result.child_revision_id == "revision-child"
    assert repository.prepared is not None
    assert repository.prepared.report.report_hash == report.report_hash
