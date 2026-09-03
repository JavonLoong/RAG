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
):
    from fmea_application.export_service import ExportService
    from fmea_infrastructure.artifact_store import WorkspaceArtifactStore

    store = WorkspaceArtifactStore(tmp_path / "artifacts", "ws-1")
    return ExportService(governance_repository or repository, repository, store, (exporter,), clock=clock), store


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
