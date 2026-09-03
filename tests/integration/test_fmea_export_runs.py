from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from fmea_governance_fixtures import (
    make_governance_actor,
    prepared_publication,
    seed_authoritative_analysis,
)


class FakeExporter:
    format = "json"
    media_type = "application/json"

    def __init__(self, payload: bytes = b'{"ok":true}\n', *, failure: Exception | None = None) -> None:
        self.payload = payload
        self.failure = failure
        self.calls = 0

    def render(self, snapshot) -> bytes:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.payload


class IneligibleGovernance:
    def __init__(self, delegate) -> None:
        self.delegate = delegate

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def get_export_eligibility(self, publication_id: str, workspace_id: str):
        return None


class AdversarialProvider:
    def __init__(self, delegate, method: str, *, result=None, failure: Exception | None = None) -> None:
        self.delegate = delegate
        self.method = method
        self.result = result
        self.failure = failure

    def __getattr__(self, name):
        if name != self.method:
            return getattr(self.delegate, name)

        def invoke(*args, **kwargs):
            if self.failure is not None:
                raise self.failure
            return self.result

        return invoke


def _published_repository(tmp_path: Path, *, fault_injector=None):
    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository

    database_path = tmp_path / "fmea.sqlite3"
    repository = SqliteFmeaDeliveryRepository(database_path, fault_injector=fault_injector)
    repository.initialize()
    seed_authoritative_analysis(database_path)
    publication = prepared_publication()
    from test_fmea_governance_sqlite import _commit_publication_with_authority_chain

    _commit_publication_with_authority_chain(repository, publication)
    return repository, publication.publication


def _service(
    repository,
    tmp_path: Path,
    exporter: FakeExporter,
    *,
    clock=lambda: "2026-09-03T00:00:00Z",
    governance_repository=None,
    export_repository=None,
    artifact_fault_hook=None,
):
    from fmea_application.export_service import ExportService
    from fmea_infrastructure.artifact_store import WorkspaceArtifactStore

    store = WorkspaceArtifactStore(tmp_path / "artifacts", "ws-1", fault_hook=artifact_fault_hook)
    return (
        ExportService(
            governance_repository or repository,
            export_repository or repository,
            store,
            (exporter,),
            clock=clock,
        ),
        store,
    )


def _command(snapshot, *, run_id="export-run-1", key="00000000-0000-4000-8000-000000000801", **overrides):
    from fmea_application.export_service import StartExportCommand

    values = {
        "export_run_id": run_id,
        "workspace_id": snapshot.workspace_id,
        "revision_id": snapshot.revision_id,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_hash": snapshot.snapshot_hash,
        "publication_id": snapshot.publication_id,
        "format": "json",
        "draft_preview": False,
        "filename": "fmea-export.json",
        "idempotency_key": key,
    }
    values.update(overrides)
    return StartExportCommand(**values)


def test_success_is_durable_verified_and_idempotent(tmp_path: Path):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, _ = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)

    first = service.start(command, actor)
    replay = service.start(command, actor)
    artifact = service.get_artifact(first.artifact_id, actor)

    assert first.status.value == "succeeded"
    assert replay == first
    assert artifact.manifest.export_run_id == first.export_run_id
    assert artifact.payload == exporter.payload
    assert exporter.calls == 1


def test_post_latest_store_fault_is_reconciled_as_succeeded_and_replayable(tmp_path: Path):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()

    def fault(stage: str) -> None:
        if stage == "after_latest":
            raise RuntimeError

    service, store = _service(repository, tmp_path, exporter, artifact_fault_hook=fault)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)

    first = service.start(command, actor)
    replay = service.start(command, actor)

    assert first.status.value == "succeeded"
    assert replay == first
    assert store.latest(first.export_run_id).artifact_id == first.artifact_id
    assert exporter.calls == 1


def test_same_key_different_payload_fails_closed(tmp_path: Path):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, _ = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    service.start(command, actor)

    with pytest.raises(Exception, match="FMEA_EXPORT_IDEMPOTENCY_CONFLICT"):
        service.start(replace(command, filename="other.json"), actor)


@pytest.mark.parametrize("failure", [RuntimeError("renderer failed"), OSError("store failed")])
def test_exporter_or_store_failure_persists_failed_run_without_artifact(tmp_path: Path, failure: Exception):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter(failure=failure if isinstance(failure, RuntimeError) else None)
    service, store = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    if isinstance(failure, OSError):
        store.publish = lambda *args, **kwargs: (_ for _ in ()).throw(failure)

    result = service.start(command, actor)

    assert result.status.value == "failed"
    assert result.artifact_id is None
    with sqlite3.connect(repository.database_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM fmea_export_artifacts WHERE workspace_id=? AND export_run_id=?",
                ("ws-1", result.export_run_id),
            ).fetchone()[0]
            == 0
        )


def test_db_commit_failure_is_reconciled_by_same_key(tmp_path: Path):
    failed_once = False

    def fault(step: str) -> None:
        nonlocal failed_once
        if step == "export.commit" and not failed_once:
            failed_once = True
            raise sqlite3.OperationalError("simulated commit boundary failure")  # noqa: TRY003

    repository, publication = _published_repository(tmp_path, fault_injector=fault)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, _ = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)

    with pytest.raises(Exception, match="FMEA_EXPORT_STORAGE_UNAVAILABLE"):
        service.start(command, actor)
    result = service.start(command, actor)

    assert result.status.value == "succeeded"
    assert exporter.calls == 1


def test_published_eligibility_and_stale_snapshot_are_checked(tmp_path: Path):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, _ = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))

    with pytest.raises(Exception, match="FMEA_EXPORT_SNAPSHOT_STALE"):
        service.start(_command(snapshot, snapshot_hash="b" * 64), actor)

    ineligible_service, _ = _service(
        repository,
        tmp_path,
        exporter,
        governance_repository=IneligibleGovernance(repository),
    )
    with pytest.raises(Exception, match="FMEA_EXPORT_NOT_ELIGIBLE"):
        ineligible_service.start(_command(snapshot, run_id="ineligible-run"), actor)


def test_draft_preview_is_explicit_and_workspace_isolated(tmp_path: Path):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, _ = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    preview = _command(
        snapshot,
        run_id="draft-run-1",
        key="00000000-0000-4000-8000-000000000802",
        publication_id=None,
        draft_preview=True,
        filename="fmea-preview.json",
    )

    result = service.start(preview, actor)

    assert result.draft_preview is True
    assert result.publication_id is None
    with pytest.raises(Exception, match="FMEA_EXPORT_RUN_NOT_FOUND"):
        service.get_run(result.export_run_id, make_governance_actor(workspace_id="ws-2"))


def test_corrupt_or_missing_published_artifact_is_not_exposed(tmp_path: Path):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, store = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    result = service.start(_command(snapshot), actor)
    stored = store.get(result.artifact_id, "ws-1")
    stored.payload_path.unlink()

    with pytest.raises(Exception, match="FMEA_EXPORT_ARTIFACT"):
        service.get_run(result.export_run_id, actor)


def test_corrupt_persisted_run_is_not_exposed(tmp_path: Path):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, _ = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    result = service.start(_command(snapshot), actor)

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_export_runs_terminal_no_update")
        connection.execute(
            "UPDATE fmea_export_runs SET run_json=? WHERE workspace_id=? AND export_run_id=?",
            ("{}", "ws-1", result.export_run_id),
        )

    with pytest.raises(Exception, match="FMEA_EXPORT_PERSISTENCE_INVALID"):
        service.get_run(result.export_run_id, actor)


def test_old_010_empty_database_upgrades_additively_to_011(tmp_path: Path):
    from test_fmea_governance_sqlite import _initialize_through

    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository

    database_path = tmp_path / "old-v10.sqlite3"
    _initialize_through(database_path, 10)

    repository = SqliteFmeaDeliveryRepository(database_path)
    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone() == (11,)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(fmea_export_runs)")}
    assert {"actor_id", "idempotency_scope", "request_json", "request_hash"} <= columns


def test_011_rejects_legacy_export_rows_without_inventing_authority(tmp_path: Path):
    from test_fmea_governance_sqlite import _initialize_through

    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository

    database_path = tmp_path / "legacy-v10.sqlite3"
    _initialize_through(database_path, 10)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO fmea_export_runs "
            "(workspace_id,export_run_id,revision_id,snapshot_id,snapshot_hash,publication_id,format,draft_preview,"
            "status,created_at,run_json,canonical_json_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-workspace",
                "legacy-run",
                "legacy-revision",
                "legacy-snapshot",
                "a" * 64,
                None,
                "json",
                1,
                "queued",
                "2026-09-03T00:00:00Z",
                "{}",
                "sha256:" + "b" * 64,
            ),
        )

    with pytest.raises(sqlite3.IntegrityError, match="fmea_export_011_requires_empty_legacy_tables"):
        SqliteFmeaDeliveryRepository(database_path).initialize()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone() == (10,)
        assert connection.execute("SELECT COUNT(*) FROM fmea_export_runs").fetchone() == (1,)


@pytest.mark.parametrize(
    "method",
    ["get_snapshot", "get_publication", "get_publication_lifecycle", "get_export_eligibility"],
)
def test_governance_provider_failures_are_bounded_without_backend_causes(tmp_path: Path, method: str):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    provider = AdversarialProvider(repository, method, failure=RuntimeError("secret backend detail"))
    service, _ = _service(repository, tmp_path, FakeExporter(), governance_repository=provider)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))

    with pytest.raises(ExportServiceError) as caught:
        service.start(_command(snapshot), actor)

    assert caught.value.code == "FMEA_EXPORT_PERSISTENCE_INVALID"
    assert "secret backend detail" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "method",
    ["get_snapshot", "get_publication", "get_publication_lifecycle", "get_export_eligibility"],
)
def test_governance_provider_wrong_types_fail_as_invalid_persistence(tmp_path: Path, method: str):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    provider = AdversarialProvider(repository, method, result=object())
    service, _ = _service(repository, tmp_path, FakeExporter(), governance_repository=provider)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))

    with pytest.raises(ExportServiceError) as caught:
        service.start(_command(snapshot), actor)

    assert caught.value.code == "FMEA_EXPORT_PERSISTENCE_INVALID"
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("method,operation", [("get_export_run", "run"), ("get_export_artifact", "artifact")])
def test_export_query_failures_are_bounded_without_backend_causes(tmp_path: Path, method: str, operation: str):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    service, _ = _service(repository, tmp_path, FakeExporter())
    completed = service.start(_command(snapshot), actor)
    provider = AdversarialProvider(repository, method, failure=RuntimeError("secret sqlite detail"))
    faulted, _ = _service(repository, tmp_path, FakeExporter(), export_repository=provider)

    with pytest.raises(ExportServiceError) as caught:
        if operation == "run":
            faulted.get_run(completed.export_run_id, actor)
        else:
            faulted.get_artifact(completed.artifact_id, actor)

    assert caught.value.code == "FMEA_EXPORT_PERSISTENCE_INVALID"
    assert "secret sqlite detail" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "tamper_sql",
    [
        "DROP TRIGGER fmea_audit_events_no_delete; DELETE FROM fmea_audit_events WHERE command='fmea.export.start';",
        "DROP TRIGGER fmea_outbox_events_no_delete; DELETE FROM fmea_outbox_events WHERE event_type='export.completed';",
        "UPDATE idempotency_records SET response_json='{}' WHERE resource_id='export-run-1';",
        "UPDATE idempotency_records SET scope_key=scope_key || '-tampered' WHERE resource_id='export-run-1';",
        "DROP TRIGGER fmea_audit_events_no_update; UPDATE fmea_audit_events SET canonical_payload_hash='sha256:"
        + "c" * 64
        + "' WHERE command='fmea.export.start';",
        "DROP TRIGGER fmea_outbox_events_no_update; UPDATE fmea_outbox_events SET payload_hash='sha256:"
        + "d" * 64
        + "' WHERE event_type='export.completed';",
        "DROP TRIGGER fmea_audit_events_no_update; UPDATE fmea_audit_events SET created_at='2026-09-03T00:00:01Z' "
        "WHERE command='fmea.export.start';",
        "UPDATE idempotency_records SET completed_at='2026-09-03T00:00:01Z' WHERE resource_id='export-run-1';",
    ],
)
def test_completed_export_rejects_each_corrupted_delivery_chain_link(tmp_path: Path, tamper_sql: str):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    service, _ = _service(repository, tmp_path, FakeExporter())
    completed = service.start(_command(snapshot), actor)

    with sqlite3.connect(repository.database_path) as connection:
        connection.executescript(tamper_sql)

    with pytest.raises(ExportServiceError) as caught:
        service.get_run(completed.export_run_id, actor)

    assert caught.value.code == "FMEA_EXPORT_PERSISTENCE_INVALID"
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("read_path", ["replay", "get_run", "get_artifact"])
def test_every_completed_read_path_revalidates_the_delivery_chain(tmp_path: Path, read_path: str):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    service, _ = _service(repository, tmp_path, FakeExporter())
    command = _command(snapshot)
    completed = service.start(command, actor)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            "UPDATE idempotency_records SET response_json='{}' WHERE resource_id=?",
            (completed.export_run_id,),
        )

    with pytest.raises(ExportServiceError, match="FMEA_EXPORT_PERSISTENCE_INVALID"):
        if read_path == "replay":
            service.start(command, actor)
        elif read_path == "get_run":
            service.get_run(completed.export_run_id, actor)
        else:
            service.get_artifact(completed.artifact_id, actor)


def test_completion_chain_is_verified_before_transaction_commit(tmp_path: Path, monkeypatch):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    service, _ = _service(repository, tmp_path, FakeExporter())

    def reject_chain(*args, **kwargs):
        raise ValueError("simulated chain verifier rejection")  # noqa: TRY003

    monkeypatch.setattr(repository, "_verify_export_delivery_chain", reject_chain)
    with pytest.raises(Exception, match="FMEA_EXPORT_STORAGE_UNAVAILABLE"):
        service.start(_command(snapshot), actor)

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute(
            "SELECT status FROM fmea_export_runs WHERE workspace_id='ws-1' AND export_run_id='export-run-1'"
        ).fetchone() == ("running",)
        assert connection.execute("SELECT COUNT(*) FROM fmea_export_artifacts").fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_audit_events WHERE command='fmea.export.start'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_outbox_events WHERE event_type='export.completed'"
        ).fetchone() == (0,)
