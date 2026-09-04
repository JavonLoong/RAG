from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import orjson
import pytest
from fmea_governance_fixtures import (
    make_governance_actor,
    make_normalized_snapshot,
    prepared_publication,
    seed_authoritative_analysis,
)

from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot


class FakeExporter:
    format = "json"
    media_type = "application/json"

    def __init__(self, payload: bytes = b'{"ok":true}\n', *, failure: Exception | None = None) -> None:
        self.payload = payload
        self.failure = failure
        self.calls = 0
        self.draft_previews: list[bool | None] = []

    def render(self, snapshot: NormalizedFmeaSnapshot, *, draft_preview: bool | None = None) -> bytes:
        self.calls += 1
        self.draft_previews.append(draft_preview)
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


class ExplosiveProviderValue:
    """Value whose ordinary coercion/comparison would leak adapter text."""

    _ERROR_DETAIL = "secret provider operation"

    def __eq__(self, other):
        raise RuntimeError(self._ERROR_DETAIL)

    def __str__(self):
        raise RuntimeError(self._ERROR_DETAIL)

    def __hash__(self):
        raise RuntimeError(self._ERROR_DETAIL)

    def __len__(self):
        raise RuntimeError(self._ERROR_DETAIL)


class ExplosiveException(RuntimeError):
    @property
    def code(self):
        raise RuntimeError("secret exception property")  # noqa: TRY003


def _published_repository(tmp_path: Path, *, fault_injector=None, upgrade_from_v10: bool = False):
    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository

    database_path = tmp_path / "fmea.sqlite3"
    if upgrade_from_v10:
        from test_fmea_governance_sqlite import _initialize_through

        _initialize_through(database_path, 10)
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


def _typed_secret_error():
    from fmea_application.export_service import ExportServiceError

    return ExportServiceError("FMEA_EXPORT_FORBIDDEN", "secret adapter detail", retryable=False)


def _reserve_queued_export(repository, snapshot):
    from fmea_application.export_service import _request_hash

    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    request_json, request_hash = _request_hash(command)
    run = repository.reserve_export_run(
        command,
        actor,
        request_json,
        request_hash,
        "2026-09-03T00:00:00Z",
    )
    return run


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
    assert exporter.draft_previews == [False]


def test_completed_legacy_export_replays_only_exact_default_version_request(tmp_path: Path, monkeypatch):
    import fmea_application.export_service as export_module
    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, _ = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    current_serializer = export_module._command_value

    def legacy_serializer(value):
        payload = current_serializer(value)
        payload.pop("expected_revision_version")
        return payload

    with monkeypatch.context() as legacy:
        legacy.setattr(export_module, "_command_value", legacy_serializer)
        completed = service.start(command, actor)

    with sqlite3.connect(repository.database_path) as connection:
        request = orjson.loads(connection.execute("SELECT request_json FROM fmea_export_runs").fetchone()[0])
        assert set(request) == {
            "export_run_id", "workspace_id", "revision_id", "snapshot_id", "snapshot_hash",
            "publication_id", "format", "draft_preview", "filename", "idempotency_key",
        }
        history = tuple(connection.iterdump())

    restarted = SqliteFmeaDeliveryRepository(repository.database_path)
    restarted.initialize()
    service, _ = _service(restarted, tmp_path, exporter)
    assert service.get_artifact(completed.artifact_id, actor).payload == exporter.payload
    assert service.start(command, actor) == completed
    for changed in (replace(command, expected_revision_version=2), replace(command, filename="other.json")):
        with pytest.raises(export_module.ExportServiceError, match="FMEA_EXPORT_IDEMPOTENCY_CONFLICT"):
            service.start(changed, actor)
    with monkeypatch.context() as extra_field:
        extra_field.setattr(export_module, "_command_value", lambda value: current_serializer(value) | {"extra": 1})
        with pytest.raises(export_module.ExportServiceError, match="FMEA_EXPORT_IDEMPOTENCY_CONFLICT"):
            service.start(command, actor)
    assert service.get_artifact(completed.artifact_id, actor).payload == exporter.payload
    assert exporter.calls == 1
    with sqlite3.connect(repository.database_path) as connection:
        assert tuple(connection.iterdump()) == history
        connection.execute(
            "UPDATE idempotency_records SET payload_hash=? WHERE resource_id=?",
            ("sha256:" + "f" * 64, completed.export_run_id),
        )
    with pytest.raises(export_module.ExportServiceError, match="FMEA_EXPORT_IDEMPOTENCY_CONFLICT"):
        service.start(command, actor)
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


def test_export_revision_version_is_checked_inside_repository_write_transaction(tmp_path: Path):
    from fmea_application.export_service import _request_hash
    from fmea_application.review_errors import ReviewError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot, expected_revision_version=2)
    request_json, request_hash = _request_hash(command)

    with pytest.raises(ReviewError) as caught:
        repository.reserve_export_run(
            command,
            actor,
            request_json,
            request_hash,
            "2026-09-03T00:00:00Z",
        )
    assert caught.value.code == "FMEA_VERSION_CONFLICT"

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_export_runs").fetchone() == (0,)


def test_export_boundary_does_not_inspect_untyped_exception_properties(tmp_path: Path):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    provider = AdversarialProvider(repository, "reserve_export_run", failure=ExplosiveException())
    service, _ = _service(repository, tmp_path, FakeExporter(), export_repository=provider)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))

    with pytest.raises(ExportServiceError) as caught:
        service.start(_command(snapshot), actor)

    assert caught.value.code == "FMEA_EXPORT_STORAGE_UNAVAILABLE"
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_export_exact_replay_stays_valid_but_changed_revision_version_fails(tmp_path: Path):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, _ = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)

    first = service.start(command, actor)
    assert service.start(command, actor) == first

    with pytest.raises(ExportServiceError, match="FMEA_EXPORT_IDEMPOTENCY_CONFLICT"):
        service.start(replace(command, expected_revision_version=2), actor)


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


def test_db_commit_failure_converges_to_replayable_failed_terminal(tmp_path: Path):
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

    result = service.start(command, actor)
    replay = service.start(command, actor)

    assert result.status.value == "failed"
    assert replay == result
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
    assert exporter.draft_previews == [True]
    with pytest.raises(Exception, match="FMEA_EXPORT_RUN_NOT_FOUND"):
        service.get_run(result.export_run_id, make_governance_actor(workspace_id="ws-2"))


def test_real_json_exporter_uses_each_command_preview_identity_and_matches_artifact_manifest(tmp_path: Path):
    from fmea_infrastructure.export_json import CanonicalJsonExporter

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = CanonicalJsonExporter(draft_preview=True)
    service, _ = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    published_command = _command(snapshot)
    preview_command = _command(
        snapshot,
        run_id="draft-run-real-json",
        key="00000000-0000-4000-8000-000000000899",
        publication_id=None,
        draft_preview=True,
        filename="fmea-preview.json",
    )

    published_run = service.start(published_command, actor)
    preview_run = service.start(preview_command, actor)
    published_artifact = service.get_artifact(published_run.artifact_id, actor)
    preview_artifact = service.get_artifact(preview_run.artifact_id, actor)
    published_body = orjson.loads(published_artifact.payload)
    preview_body = orjson.loads(preview_artifact.payload)

    assert published_artifact.manifest.draft_preview is False
    assert published_artifact.manifest.publication_id == snapshot.publication_id
    assert published_body["draft_preview"] is False
    assert published_body["draft_marker"] is None
    assert published_body["publication_id"] == published_artifact.manifest.publication_id
    assert published_body["source_publication_id"] is None
    assert preview_artifact.manifest.draft_preview is True
    assert preview_artifact.manifest.publication_id is None
    assert preview_body["draft_preview"] is True
    assert preview_body["draft_marker"] == "DRAFT PREVIEW — NOT PUBLISHED"
    assert preview_body["publication_id"] == preview_artifact.manifest.publication_id
    assert preview_body["source_publication_id"] == snapshot.publication_id


def test_corrupt_or_missing_published_artifact_is_not_exposed(tmp_path: Path):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, store = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    result = service.start(_command(snapshot), actor)
    (store.artifacts_root / result.artifact_id / result.filename).unlink()

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
        historical_010 = connection.execute(
            "SELECT version, filename FROM schema_migrations WHERE version=?",
            (10,),
        ).fetchone()
        assert historical_010 == (10, "010_fmea_migration_delivery.sql")
        applied_versions = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations")
        }
        assert {11, 12} <= applied_versions

        columns = {row[1] for row in connection.execute("PRAGMA table_info(fmea_export_runs)")}
        draft_columns = {row[1] for row in connection.execute("PRAGMA table_info(fmea_template_drafts)")}
        candidate_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(fmea_template_patch_candidates)")
        }
        decision_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(fmea_template_patch_decisions)")
        }
    assert {"actor_id", "idempotency_scope", "request_json", "request_hash"} <= columns
    assert {"record_version"} <= draft_columns
    assert {"suggestion_json", "record_version"} <= candidate_columns
    assert {"record_version"} <= decision_columns


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
    result = service.start(_command(snapshot), actor)

    assert result.status.value == "failed"

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute(
            "SELECT status FROM fmea_export_runs WHERE workspace_id='ws-1' AND export_run_id='export-run-1'"
        ).fetchone() == ("failed",)
        assert connection.execute("SELECT COUNT(*) FROM fmea_export_artifacts").fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_audit_events WHERE command='fmea.export.start'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_outbox_events WHERE event_type='export.completed'"
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    "upgrade_from_v10,from_running",
    [(False, True), (True, False)],
    ids=["fresh-v11-running", "empty-v10-to-v11-queued"],
)
def test_cancelling_and_cancelled_runs_persist_across_restart(
    tmp_path: Path, upgrade_from_v10: bool, from_running: bool
):
    from core_domain.fmea.states import RunStatus
    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository

    repository, publication = _published_repository(tmp_path, upgrade_from_v10=upgrade_from_v10)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    queued = _reserve_queued_export(repository, snapshot)
    source = (
        repository.mark_export_running(queued.export_run_id, queued.workspace_id, "2026-09-03T00:00:01Z")
        if from_running
        else queued
    )
    cancelling = repository.request_export_cancellation(
        source.export_run_id,
        source.workspace_id,
        "2026-09-03T00:00:01Z",
    )
    assert cancelling.status is RunStatus.CANCELLING

    restarted = SqliteFmeaDeliveryRepository(repository.database_path)
    restarted.initialize()
    assert restarted.get_export_run(cancelling.export_run_id, "ws-1") == cancelling

    cancelled = restarted.complete_export_cancellation(
        cancelling.export_run_id,
        cancelling.workspace_id,
        "2026-09-03T00:00:02Z",
    )
    assert cancelled.status is RunStatus.CANCELLED
    restarted_again = SqliteFmeaDeliveryRepository(repository.database_path)
    restarted_again.initialize()
    assert restarted_again.get_export_run(cancelled.export_run_id, "ws-1") == cancelled
    assert (
        restarted_again.complete_export_cancellation(
            cancelled.export_run_id,
            cancelled.workspace_id,
            "2026-09-03T00:00:03Z",
        )
        == cancelled
    )


def test_cancellation_repository_rejects_invalid_public_transitions(tmp_path: Path):
    from core_domain.fmea.states import RunStatus

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    queued = _reserve_queued_export(repository, snapshot)

    with pytest.raises(ValueError, match="not cancelling"):
        repository.complete_export_cancellation(
            queued.export_run_id,
            queued.workspace_id,
            "2026-09-03T00:00:01Z",
        )

    cancelling = repository.request_export_cancellation(
        queued.export_run_id,
        queued.workspace_id,
        "2026-09-03T00:00:01Z",
    )
    assert cancelling.status is RunStatus.CANCELLING
    with pytest.raises(ValueError, match="running"):
        repository.mark_export_running(
            cancelling.export_run_id,
            cancelling.workspace_id,
            "2026-09-03T00:00:02Z",
        )
    cancelled = repository.complete_export_cancellation(
        cancelling.export_run_id,
        cancelling.workspace_id,
        "2026-09-03T00:00:02Z",
    )
    assert (
        repository.request_export_cancellation(
            cancelled.export_run_id,
            cancelled.workspace_id,
            "2026-09-03T00:00:03Z",
        )
        == cancelled
    )
    with pytest.raises(ValueError, match="current state"):
        repository.fail_export(
            cancelled.export_run_id,
            cancelled.workspace_id,
            "late failure",
            "2026-09-03T00:00:03Z",
        )


def test_queued_cancel_closes_start_replay_and_survives_restart(tmp_path: Path):
    from core_domain.fmea.states import RunStatus
    from fmea_infrastructure.delivery_repository_sqlite import SqliteFmeaDeliveryRepository

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, _ = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    _reserve_queued_export(repository, snapshot)

    cancelled = service.cancel(command.export_run_id, actor)

    assert cancelled.status is RunStatus.CANCELLED
    assert service.cancel(command.export_run_id, actor) == cancelled
    assert service.start(command, actor) == cancelled
    restarted = SqliteFmeaDeliveryRepository(repository.database_path)
    restarted.initialize()
    restarted_service, _ = _service(restarted, tmp_path, exporter)
    assert restarted_service.start(command, actor) == cancelled
    assert exporter.calls == 0


def test_start_replay_finishes_a_persisted_cancelling_run(tmp_path: Path):
    from core_domain.fmea.states import RunStatus

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, _ = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    queued = _reserve_queued_export(repository, snapshot)
    cancelling = repository.request_export_cancellation(
        queued.export_run_id,
        queued.workspace_id,
        "2026-09-03T00:00:00Z",
    )
    assert cancelling.status is RunStatus.CANCELLING

    replay = service.start(command, actor)

    assert replay.status is RunStatus.CANCELLED
    assert service.start(command, actor) == replay
    assert exporter.calls == 0


def test_running_export_cooperatively_cancels_before_artifact_publication(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor

    from core_domain.fmea.states import RunStatus

    entered_render = threading.Event()
    release_render = threading.Event()

    class BlockingExporter(FakeExporter):
        def render(self, snapshot: NormalizedFmeaSnapshot, *, draft_preview: bool | None = None) -> bytes:
            self.calls += 1
            self.draft_previews.append(draft_preview)
            entered_render.set()
            assert release_render.wait(5)
            return self.payload

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = BlockingExporter()
    service, store = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service.start, command, actor)
        assert entered_render.wait(5)
        cancelled = service.cancel(command.export_run_id, actor)
        release_render.set()
        start_result = future.result(timeout=5)

    assert cancelled.status is RunStatus.CANCELLED
    assert start_result == cancelled
    assert service.start(command, actor) == cancelled
    assert store.latest(command.export_run_id) is None


def test_cancel_after_success_preserves_the_verified_succeeded_terminal(tmp_path: Path):
    from core_domain.fmea.states import RunStatus

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, _ = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    succeeded = service.start(command, actor)

    cancel_result = service.cancel(command.export_run_id, actor)

    assert succeeded.status is RunStatus.SUCCEEDED
    assert cancel_result == succeeded
    assert service.get_run(command.export_run_id, actor) == succeeded


def test_cancel_requires_export_authority_and_workspace_membership(tmp_path: Path):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, _ = _service(repository, tmp_path, FakeExporter())
    queued = _reserve_queued_export(repository, snapshot)

    with pytest.raises(ExportServiceError, match="FMEA_EXPORT_FORBIDDEN"):
        service.cancel(
            queued.export_run_id,
            make_governance_actor(actor_id="reviewer-1", roles=frozenset({"reviewer"})),
        )
    with pytest.raises(ExportServiceError, match="FMEA_EXPORT_RUN_NOT_FOUND"):
        service.cancel(
            queued.export_run_id,
            make_governance_actor(
                actor_id="exporter-2",
                roles=frozenset({"exporter"}),
                workspace_id="ws-2",
            ),
        )

    assert repository.get_export_run(queued.export_run_id, queued.workspace_id) == queued


def test_cancel_does_not_rewrite_failed_terminal(tmp_path: Path):
    from core_domain.fmea.states import RunStatus

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, _ = _service(repository, tmp_path, FakeExporter(failure=RuntimeError("render failed")))
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    failed = service.start(command, actor)

    cancel_result = service.cancel(command.export_run_id, actor)

    assert failed.status is RunStatus.FAILED
    assert cancel_result == failed
    assert service.get_run(command.export_run_id, actor) == failed


def test_complete_and_cancel_race_converges_to_one_succeeded_terminal(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor

    from core_domain.fmea.states import RunStatus

    completion_holds_writer = threading.Event()
    release_completion = threading.Event()

    def fault(step: str) -> None:
        if step == "export.commit":
            completion_holds_writer.set()
            assert release_completion.wait(5)

    repository, publication = _published_repository(tmp_path, fault_injector=fault)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, _ = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)

    with ThreadPoolExecutor(max_workers=2) as executor:
        start_future = executor.submit(service.start, command, actor)
        assert completion_holds_writer.wait(5)
        cancel_future = executor.submit(service.cancel, command.export_run_id, actor)
        release_completion.set()
        start_result = start_future.result(timeout=5)
        cancel_result = cancel_future.result(timeout=5)

    assert start_result.status is RunStatus.SUCCEEDED
    assert cancel_result == start_result
    assert service.get_run(command.export_run_id, actor) == start_result


def test_physical_publish_with_malformed_return_reconciles_without_rerender(tmp_path: Path):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    exporter = FakeExporter()
    service, store = _service(repository, tmp_path, exporter)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    real_publish = store.publish

    def publish_then_lie(*args, **kwargs):
        real_publish(*args, **kwargs)
        return object()

    store.publish = publish_then_lie

    result = service.start(command, actor)

    assert result.status.value == "succeeded"
    assert service.start(command, actor) == result
    assert exporter.calls == 1


def test_get_artifact_rejects_same_shaped_foreign_identity_and_path(tmp_path: Path):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, store = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    completed = service.start(_command(snapshot), actor)
    manifest = repository.get_export_artifact(completed.artifact_id, actor.workspace_id)
    store.get = lambda *args, **kwargs: SimpleNamespace(
        workspace_id="ws-2",
        export_run_id=completed.export_run_id,
        artifact_id="foreign-artifact",
        filename=manifest.filename,
        payload=b'{"ok":true}\n',
        manifest=manifest,
        path=Path("C:/outside/secret.json"),
    )
    store.latest = lambda *args, **kwargs: SimpleNamespace(
        workspace_id="ws-2",
        export_run_id=completed.export_run_id,
        artifact_id="foreign-artifact",
        filename=manifest.filename,
        payload=b'{"ok":true}\n',
        manifest=manifest,
        path=Path("C:/outside/secret.json"),
    )

    with pytest.raises(ExportServiceError) as caught:
        service.get_artifact(completed.artifact_id, actor)

    assert caught.value.code == "FMEA_EXPORT_ARTIFACT_INVALID"
    assert caught.value.__cause__ is None


def test_get_artifact_normalizes_malicious_manifest_comparison(tmp_path: Path):
    from fmea_application.export_service import ExportServiceError

    class ExplosiveManifest:
        def __ne__(self, other):
            raise _typed_secret_error()

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, store = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    completed = service.start(_command(snapshot), actor)
    store.get = lambda *args, **kwargs: SimpleNamespace(
        manifest=ExplosiveManifest(),
        payload=b'{"ok":true}\n',
    )
    store.latest = lambda *args, **kwargs: SimpleNamespace(
        manifest=ExplosiveManifest(),
        payload=b'{"ok":true}\n',
    )

    with pytest.raises(ExportServiceError) as caught:
        service.get_artifact(completed.artifact_id, actor)

    assert caught.value.code == "FMEA_EXPORT_ARTIFACT_INVALID"
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_get_artifact_returns_application_owned_path_free_value(tmp_path: Path):
    from fmea_application.delivery_contracts import VerifiedExportArtifact

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, _ = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    completed = service.start(_command(snapshot), actor)

    artifact = service.get_artifact(completed.artifact_id, actor)

    assert type(artifact) is VerifiedExportArtifact
    assert artifact.workspace_id == actor.workspace_id
    assert not hasattr(artifact, "path")


def test_fail_run_rejects_non_failed_repository_result(tmp_path: Path):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    queued = _reserve_queued_export(repository, snapshot)
    running = repository.mark_export_running(
        queued.export_run_id,
        queued.workspace_id,
        "2026-09-03T00:00:00Z",
    )
    provider = AdversarialProvider(repository, "fail_export", result=running)
    service, _ = _service(
        repository,
        tmp_path,
        FakeExporter(failure=RuntimeError("render failed")),
        export_repository=provider,
    )
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))

    with pytest.raises(ExportServiceError) as caught:
        service.start(_command(snapshot), actor)

    assert caught.value.code == "FMEA_EXPORT_PERSISTENCE_INVALID"
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "method",
    ["get_snapshot", "get_publication", "get_publication_lifecycle", "get_export_eligibility"],
)
def test_typed_governance_adapter_errors_are_normalized(tmp_path: Path, method: str):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    provider = AdversarialProvider(repository, method, failure=_typed_secret_error())
    service, _ = _service(repository, tmp_path, FakeExporter(), governance_repository=provider)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))

    with pytest.raises(ExportServiceError) as caught:
        service.start(_command(snapshot), actor)

    assert caught.value.code == "FMEA_EXPORT_PERSISTENCE_INVALID"
    assert caught.value.retryable is False
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "method,operation,expected_code,expected_retryable",
    [
        ("get_export_run", "start", "FMEA_EXPORT_PERSISTENCE_INVALID", False),
        ("reserve_export_run", "start", "FMEA_EXPORT_STORAGE_UNAVAILABLE", True),
        ("mark_export_running", "start", "FMEA_EXPORT_STORAGE_UNAVAILABLE", True),
        ("request_export_cancellation", "cancel_queued", "FMEA_EXPORT_STORAGE_UNAVAILABLE", True),
        ("complete_export_cancellation", "cancel_cancelling", "FMEA_EXPORT_STORAGE_UNAVAILABLE", True),
        ("complete_export", "start", "FMEA_EXPORT_STORAGE_UNAVAILABLE", True),
        ("fail_export", "failed_start", "FMEA_EXPORT_STORAGE_UNAVAILABLE", True),
        ("get_export_artifact", "get_artifact", "FMEA_EXPORT_PERSISTENCE_INVALID", False),
        ("verify_export_delivery", "get_run", "FMEA_EXPORT_PERSISTENCE_INVALID", False),
    ],
)
def test_typed_export_repository_errors_are_normalized(
    tmp_path: Path,
    method: str,
    operation: str,
    expected_code: str,
    expected_retryable: bool,
):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    completed = None
    if operation in {"get_artifact", "get_run"}:
        real_service, _ = _service(repository, tmp_path, FakeExporter())
        completed = real_service.start(_command(snapshot), actor)
    if operation in {"cancel_queued", "cancel_cancelling"}:
        queued = _reserve_queued_export(repository, snapshot)
        if operation == "cancel_cancelling":
            repository.request_export_cancellation(
                queued.export_run_id,
                queued.workspace_id,
                "2026-09-03T00:00:00Z",
            )
    provider = AdversarialProvider(repository, method, failure=_typed_secret_error())
    exporter = FakeExporter(failure=RuntimeError("render failed")) if operation == "failed_start" else FakeExporter()
    service, _ = _service(repository, tmp_path, exporter, export_repository=provider)

    if method == "complete_export":
        failed = service.start(_command(snapshot), actor)
        assert failed.status.value == "failed"
        assert failed.error == "export completion failed"
        assert "secret" not in failed.error
        return

    with pytest.raises(ExportServiceError) as caught:
        if operation == "get_artifact":
            service.get_artifact(completed.artifact_id, actor)
        elif operation == "get_run":
            service.get_run(completed.export_run_id, actor)
        elif operation in {"cancel_queued", "cancel_cancelling"}:
            service.cancel("export-run-1", actor)
        else:
            service.start(_command(snapshot), actor)

    assert caught.value.code == expected_code
    assert caught.value.retryable is expected_retryable
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("boundary", ["exporter", "store_latest", "store_publish"])
def test_typed_render_and_store_errors_persist_only_safe_failure(tmp_path: Path, boundary: str):
    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    exporter = FakeExporter(failure=_typed_secret_error() if boundary == "exporter" else None)
    service, store = _service(repository, tmp_path, exporter)
    if boundary == "store_latest":
        store.latest = lambda *args, **kwargs: (_ for _ in ()).throw(_typed_secret_error())
    elif boundary == "store_publish":
        store.publish = lambda *args, **kwargs: (_ for _ in ()).throw(_typed_secret_error())

    failed = service.start(_command(snapshot), actor)

    assert failed.status.value == "failed"
    assert failed.error in {"exporter failed", "artifact store lookup failed", "artifact publication failed"}
    assert "secret" not in failed.error


def test_typed_store_error_during_reconciliation_is_normalized(tmp_path: Path):
    from hashlib import sha256

    from fmea_application.delivery_contracts import ExportArtifactManifest
    from fmea_application.export_service import _artifact_id

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    service, store = _service(repository, tmp_path, FakeExporter())
    command = _command(snapshot)
    queued = _reserve_queued_export(repository, snapshot)
    repository.mark_export_running(queued.export_run_id, queued.workspace_id, "2026-09-03T00:00:00Z")
    payload = b'{"ok":true}\n'
    manifest = ExportArtifactManifest(
        artifact_id=_artifact_id(actor.workspace_id, command.export_run_id),
        export_run_id=command.export_run_id,
        publication_id=command.publication_id,
        revision_id=command.revision_id,
        snapshot_id=command.snapshot_id,
        snapshot_hash=command.snapshot_hash,
        format=command.format,
        media_type="application/json",
        byte_length=len(payload),
        sha256=sha256(payload).hexdigest(),
        draft_preview=command.draft_preview,
        created_at="2026-09-03T00:00:00Z",
        filename=command.filename,
    )
    store.publish(command.export_run_id, command.filename, payload, manifest)
    store.get = lambda *args, **kwargs: (_ for _ in ()).throw(_typed_secret_error())
    store.latest = lambda *args, **kwargs: (_ for _ in ()).throw(_typed_secret_error())

    failed = service.start(command, actor)

    assert failed.status.value == "failed"
    assert failed.error == "artifact store lookup failed"
    assert "secret" not in failed.error


def test_typed_narrative_generator_error_is_normalized_by_service_policy():
    from core_domain.fmea.states import ActorType
    from fmea_application.export_service import ExportService, ExportServiceError

    class TypedFailingGenerator:
        def generate(self, request):
            raise _typed_secret_error()

    service = ExportService(object(), object(), object(), (), narrative_generator=TypedFailingGenerator())
    actor = make_governance_actor(actor_id="model-1", actor_type=ActorType.MODEL, roles=frozenset())

    with pytest.raises(ExportServiceError) as caught:
        service.suggest_narrative(make_normalized_snapshot(), actor)

    assert caught.value.code == "FMEA_EXPORT_NARRATIVE_UNAVAILABLE"
    assert caught.value.retryable is True
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_physical_publish_with_mutated_exact_manifest_recovers_without_running_leak(tmp_path: Path):
    from core_domain.fmea.states import RunStatus

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, store = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    real_publish = store.publish

    def publish_then_mutate(*args, **kwargs):
        published = real_publish(*args, **kwargs)
        object.__setattr__(published.manifest, "sha256", ExplosiveProviderValue())
        return published

    store.publish = publish_then_mutate

    result = service.start(command, actor)

    assert result.status is RunStatus.SUCCEEDED
    assert repository.get_export_run(command.export_run_id, actor.workspace_id).status is RunStatus.SUCCEEDED


def test_mutated_exact_latest_payload_persists_failed_instead_of_running(tmp_path: Path):
    from hashlib import sha256

    from core_domain.fmea.states import RunStatus
    from fmea_application.delivery_contracts import ExportArtifactManifest, VerifiedExportArtifact
    from fmea_application.export_service import _artifact_id

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, store = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    payload = b'{"ok":true}\n'
    manifest = ExportArtifactManifest(
        artifact_id=_artifact_id(actor.workspace_id, command.export_run_id),
        export_run_id=command.export_run_id,
        publication_id=command.publication_id,
        revision_id=command.revision_id,
        snapshot_id=command.snapshot_id,
        snapshot_hash=command.snapshot_hash,
        format=command.format,
        media_type="application/json",
        byte_length=len(payload),
        sha256=sha256(payload).hexdigest(),
        draft_preview=command.draft_preview,
        created_at="2026-09-03T00:00:00Z",
        filename=command.filename,
    )
    malformed = VerifiedExportArtifact(
        workspace_id=actor.workspace_id,
        export_run_id=command.export_run_id,
        artifact_id=manifest.artifact_id,
        filename=command.filename,
        payload=payload,
        manifest=manifest,
    )
    object.__setattr__(malformed, "payload", ExplosiveProviderValue())
    store.latest = lambda *args, **kwargs: malformed
    store.get = lambda *args, **kwargs: malformed

    result = service.start(command, actor)

    assert result.status is RunStatus.FAILED
    assert repository.get_export_run(command.export_run_id, actor.workspace_id).status is RunStatus.FAILED
    assert "secret" not in result.error


@pytest.mark.parametrize("operation", ["replay", "get_artifact"])
def test_mutated_exact_artifact_is_bounded_on_completed_read_paths(tmp_path: Path, operation: str):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, store = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    completed = service.start(command, actor)
    malformed = store.get(completed.artifact_id, actor.workspace_id)
    object.__setattr__(malformed, "workspace_id", ExplosiveProviderValue())
    store.get = lambda *args, **kwargs: malformed
    store.latest = lambda *args, **kwargs: malformed

    with pytest.raises(ExportServiceError) as caught:
        if operation == "replay":
            service.start(command, actor)
        else:
            service.get_artifact(completed.artifact_id, actor)

    assert caught.value.code == "FMEA_EXPORT_ARTIFACT_INVALID"
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_mutated_exact_snapshot_is_normalized_inside_governance_boundary(tmp_path: Path):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    command = _command(snapshot)
    object.__setattr__(snapshot, "workspace_id", ExplosiveProviderValue())
    provider = AdversarialProvider(repository, "get_snapshot", result=snapshot)
    service, _ = _service(repository, tmp_path, FakeExporter(), governance_repository=provider)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))

    with pytest.raises(ExportServiceError) as caught:
        service.start(command, actor)

    assert caught.value.code == "FMEA_EXPORT_PERSISTENCE_INVALID"
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_mutated_exact_delivery_run_is_normalized_inside_repository_boundary(tmp_path: Path):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    real_service, _ = _service(repository, tmp_path, FakeExporter())
    completed = real_service.start(command, actor)
    manifest = repository.get_export_artifact(completed.artifact_id, actor.workspace_id)
    object.__setattr__(completed, "artifact_id", ExplosiveProviderValue())
    provider = AdversarialProvider(repository, "verify_export_delivery", result=(completed, manifest))
    service, _ = _service(repository, tmp_path, FakeExporter(), export_repository=provider)

    with pytest.raises(ExportServiceError) as caught:
        service.get_run(command.export_run_id, actor)

    assert caught.value.code == "FMEA_EXPORT_PERSISTENCE_INVALID"
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_plain_value_error_with_malicious_argument_is_not_coerced_for_sentinel(tmp_path: Path):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    malicious = ValueError("placeholder")
    malicious.args = (ExplosiveProviderValue(),)
    provider = AdversarialProvider(repository, "reserve_export_run", failure=malicious)
    service, _ = _service(repository, tmp_path, FakeExporter(), export_repository=provider)
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))

    with pytest.raises(ExportServiceError) as caught:
        service.start(_command(snapshot), actor)

    assert caught.value.code == "FMEA_EXPORT_STORAGE_UNAVAILABLE"
    assert caught.value.retryable is True
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


def test_same_workspace_different_actor_reuse_is_nonretryable_idempotency_conflict(tmp_path: Path):
    from fmea_application.export_service import ExportServiceError

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, _ = _service(repository, tmp_path, FakeExporter())
    command = _command(snapshot)
    first_actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    second_actor = make_governance_actor(actor_id="exporter-2", roles=frozenset({"exporter"}))
    service.start(command, first_actor)

    with pytest.raises(ExportServiceError) as caught:
        service.start(command, second_actor)

    assert caught.value.code == "FMEA_EXPORT_IDEMPOTENCY_CONFLICT"
    assert caught.value.retryable is False
    assert caught.value.__cause__ is None


def test_committed_completion_with_mutated_exact_return_reloads_verified_success(tmp_path: Path):
    from core_domain.fmea.states import RunStatus

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, store = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    real_complete = repository.complete_export

    def commit_then_mutate(*args, **kwargs):
        completed = real_complete(*args, **kwargs)
        object.__setattr__(completed, "artifact_id", ExplosiveProviderValue())
        return completed

    repository.complete_export = commit_then_mutate

    result = service.start(command, actor)

    assert result.status is RunStatus.SUCCEEDED
    assert repository.get_export_run(command.export_run_id, actor.workspace_id) == result
    assert store.latest(command.export_run_id).artifact_id == result.artifact_id


def test_uncommitted_completion_with_mutated_exact_return_persists_failed(tmp_path: Path):
    from core_domain.fmea.states import RunStatus

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, store = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)

    def return_mutated(run, manifest, actor, request_json, request_hash, finished_at):
        completed = replace(
            run,
            status=RunStatus.SUCCEEDED,
            artifact_id=manifest.artifact_id,
            finished_at=finished_at,
        )
        object.__setattr__(completed, "artifact_id", ExplosiveProviderValue())
        return completed

    repository.complete_export = return_mutated

    result = service.start(command, actor)

    assert store.latest(command.export_run_id) is not None
    assert result.status is RunStatus.FAILED
    assert repository.get_export_run(command.export_run_id, actor.workspace_id) == result
    assert "secret" not in result.error


def test_existing_latest_completion_with_non_exact_return_persists_failed(tmp_path: Path):
    from hashlib import sha256

    from core_domain.fmea.states import RunStatus
    from fmea_application.delivery_contracts import ExportArtifactManifest
    from fmea_application.export_service import _artifact_id

    repository, publication = _published_repository(tmp_path)
    snapshot = repository.get_snapshot(publication.publication_id, "ws-1")
    service, store = _service(repository, tmp_path, FakeExporter())
    actor = make_governance_actor(actor_id="exporter-1", roles=frozenset({"exporter"}))
    command = _command(snapshot)
    queued = _reserve_queued_export(repository, snapshot)
    repository.mark_export_running(queued.export_run_id, queued.workspace_id, "2026-09-03T00:00:00Z")
    payload = b'{"ok":true}\n'
    manifest = ExportArtifactManifest(
        artifact_id=_artifact_id(actor.workspace_id, command.export_run_id),
        export_run_id=command.export_run_id,
        publication_id=command.publication_id,
        revision_id=command.revision_id,
        snapshot_id=command.snapshot_id,
        snapshot_hash=command.snapshot_hash,
        format=command.format,
        media_type="application/json",
        byte_length=len(payload),
        sha256=sha256(payload).hexdigest(),
        draft_preview=command.draft_preview,
        created_at="2026-09-03T00:00:00Z",
        filename=command.filename,
    )
    store.publish(command.export_run_id, command.filename, payload, manifest)
    repository.complete_export = lambda *args, **kwargs: object()

    result = service.start(command, actor)

    assert result.status is RunStatus.FAILED
    assert repository.get_export_run(command.export_run_id, actor.workspace_id) == result
    assert "private" not in result.error
