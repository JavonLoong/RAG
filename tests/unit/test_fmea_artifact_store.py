"""Focused tests for the contained, crash-safe export artifact store."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
from pathlib import Path

import pytest

from fmea_application.delivery_contracts import ExportArtifactManifest
from fmea_infrastructure.artifact_store import ArtifactStoreError, StoredArtifact, WorkspaceArtifactStore

WORKSPACE = "workspace-1"
RUN = "export-run-1"
ARTIFACT = "artifact-1"
FILENAME = "snapshot.json"
PAYLOAD = b'{"schema_version":"graphrag.fmea.export.v1"}\n'


def _manifest(
    payload: bytes = PAYLOAD,
    *,
    artifact_id: str = ARTIFACT,
    run_id: str = RUN,
    filename: str = FILENAME,
) -> ExportArtifactManifest:
    return ExportArtifactManifest(
        artifact_id=artifact_id,
        export_run_id=run_id,
        publication_id=None,
        revision_id="revision-1",
        snapshot_hash="a" * 64,
        format="json",
        media_type="application/json",
        byte_length=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        draft_preview=True,
        created_at="2026-08-27T00:00:00+00:00",
        snapshot_id="snapshot-1",
        filename=filename,
    )


def _store(tmp_path: Path, **kwargs: object) -> WorkspaceArtifactStore:
    return WorkspaceArtifactStore(tmp_path / "artifacts", WORKSPACE, **kwargs)


class _ReparseStat:
    def __init__(self, delegate: os.stat_result) -> None:
        self._delegate = delegate
        self.st_file_attributes = getattr(delegate, "st_file_attributes", 0) | 0x400

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)


def _multiprocess_publish(
    root: str,
    ready,
    release,
    attempted,
    results,
    *,
    hold_reservation: bool,
) -> None:
    def fault(stage: str) -> None:
        if hold_reservation and stage == "after_temp_verify":
            ready.set()
            if not release.wait(10):
                raise RuntimeError

    store = WorkspaceArtifactStore(
        root,
        WORKSPACE,
        fault_hook=fault,
        reservation_timeout_seconds=5.0,
        reservation_poll_seconds=0.01,
    )
    attempted.set()
    try:
        published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
        results.put(("ok", published.manifest.sha256))
    except Exception as exc:  # pragma: no cover - reported to the parent process
        results.put(("error", type(exc).__name__, str(exc)))


def test_publish_get_and_latest_return_the_same_verified_artifact(tmp_path: Path) -> None:
    store = _store(tmp_path)

    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    loaded = store.get(ARTIFACT, WORKSPACE)
    latest = store.latest(RUN)

    assert isinstance(published, StoredArtifact)
    assert loaded == published
    assert latest == published
    assert published.path.read_bytes() == PAYLOAD
    assert published.manifest == _manifest()
    assert published.path.name == FILENAME
    assert not tuple(published.directory.glob(".*.tmp-*"))


@pytest.mark.parametrize("filename", ["../escape.json", "nested/file.json", "/absolute.json", "CON.json"])
def test_publish_rejects_user_controlled_path_names(tmp_path: Path, filename: str) -> None:
    store = _store(tmp_path)
    manifest = _manifest()

    with pytest.raises(ArtifactStoreError) as error:
        store.publish(RUN, filename, PAYLOAD, manifest)

    assert error.value.code == "FMEA_ARTIFACT_PATH_INVALID"
    assert str(tmp_path) not in str(error.value)
    assert not tuple(store.artifacts_root.iterdir())


def test_publish_rejects_binding_and_hash_mismatches_before_writing(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(ArtifactStoreError) as run_error:
        store.publish("other-run", FILENAME, PAYLOAD, _manifest())
    assert run_error.value.code == "FMEA_ARTIFACT_BINDING_INVALID"

    with pytest.raises(ArtifactStoreError) as hash_error:
        store.publish(RUN, FILENAME, b"different", _manifest())
    assert hash_error.value.code == "FMEA_ARTIFACT_PAYLOAD_INVALID"
    assert not tuple(store.artifacts_root.iterdir())


def test_identical_replay_is_immutable_but_different_content_conflicts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    replay = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    assert replay == first

    changed = b"changed\n"
    with pytest.raises(ArtifactStoreError) as error:
        store.publish(RUN, FILENAME, changed, _manifest(changed))
    assert error.value.code == "FMEA_ARTIFACT_CONFLICT"
    assert first.path.read_bytes() == PAYLOAD


def test_identical_replay_repairs_a_missing_latest_pointer(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    (store.runs_root / RUN / ".latest.json").unlink()

    replay = store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert replay == first
    assert store.latest(RUN) == first


def test_fault_after_final_rename_before_latest_preserves_previous_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    previous = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    next_payload = b'{"next":true}\n'
    next_manifest = _manifest(next_payload, artifact_id="artifact-2")

    def fail(stage: str) -> None:
        if stage == "after_final_rename":
            raise RuntimeError

    monkeypatch.setattr(store, "_fault", fail)
    with pytest.raises(ArtifactStoreError) as error:
        store.publish(RUN, FILENAME, next_payload, next_manifest)

    assert error.value.code == "FMEA_ARTIFACT_STORAGE_FAILED"
    assert store.latest(RUN) == previous
    assert not (store.artifacts_root / "artifact-2").exists()


def test_fault_after_latest_reconciles_the_committed_artifact(tmp_path: Path) -> None:
    def fail(stage: str) -> None:
        if stage == "after_latest":
            raise RuntimeError

    store = _store(tmp_path, fault_hook=fail)

    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert published == store.get(ARTIFACT, WORKSPACE)
    assert published == store.latest(RUN)


def test_latest_directory_sync_fault_reconciles_the_committed_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    original_sync = store._sync_directory

    def sync_then_fail(path: Path) -> None:
        original_sync(path)
        if path == store.runs_root / RUN:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "injected directory sync failure")

    monkeypatch.setattr(store, "_sync_directory", sync_then_fail)

    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert published == store.latest(RUN)


def test_final_directory_sync_failure_before_latest_preserves_previous_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    previous = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    next_payload = b'{"next":true}\n'
    next_manifest = _manifest(next_payload, artifact_id="artifact-2")
    original_sync = store._sync_directory

    def fail_final_parent_sync(path: Path) -> None:
        if path == store.artifacts_root:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "injected directory sync failure")
        original_sync(path)

    monkeypatch.setattr(store, "_sync_directory", fail_final_parent_sync)

    with pytest.raises(ArtifactStoreError) as error:
        store.publish(RUN, FILENAME, next_payload, next_manifest)

    assert error.value.code == "FMEA_ARTIFACT_STORAGE_FAILED"
    assert store.latest(RUN) == previous
    assert not (store.artifacts_root / "artifact-2").exists()


def test_fault_during_temp_write_does_not_create_latest_or_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)

    def fail(stage: str) -> None:
        if stage == "after_payload_write":
            raise RuntimeError

    monkeypatch.setattr(store, "_fault", fail)
    with pytest.raises(ArtifactStoreError):
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert store.latest(RUN) is None
    assert not tuple(store.artifacts_root.iterdir())


def test_fsync_seam_failure_cleans_the_staged_directory(tmp_path: Path) -> None:
    calls = 0

    def fail(_descriptor: int) -> None:
        nonlocal calls
        calls += 1
        raise OSError

    store = _store(tmp_path, fsync_seam=fail)
    with pytest.raises(ArtifactStoreError) as error:
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert calls == 1
    assert error.value.code == "FMEA_ARTIFACT_STORAGE_FAILED"
    assert store.latest(RUN) is None
    assert not tuple(store.artifacts_root.iterdir())


def test_owned_tree_cleanup_preserves_a_replacement_after_identity_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    owned = store.artifacts_root / ".owned-cleanup"
    displaced = store.artifacts_root / ".displaced-owned-cleanup"
    owned.mkdir()
    (owned / "owned.txt").write_bytes(b"owned")
    expected = owned.lstat()
    foreign_sentinel = owned / "foreign-sentinel.txt"
    original_remove_tree = store._remove_tree

    def replace_after_check(path: Path, *, expected=None) -> None:
        path.rename(displaced)
        path.mkdir()
        foreign_sentinel.write_bytes(b"foreign")
        if expected is None:
            original_remove_tree(path)
        else:
            original_remove_tree(path, expected=expected)

    monkeypatch.setattr(store, "_remove_tree", replace_after_check)

    store._remove_owned_tree(owned, expected)

    assert owned.is_dir()
    assert foreign_sentinel.read_bytes() == b"foreign"


def test_owned_tree_cleanup_fails_closed_when_parent_cannot_be_revalidated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    owned = store.artifacts_root / ".owned-cleanup"
    owned.mkdir()
    owned_file = owned / "owned.txt"
    owned_file.write_bytes(b"owned")
    expected = owned.lstat()
    original_inspect = store._inspect

    def reject_owned_parent(path: Path, *, directory: bool, allow_missing: bool):
        if path == owned:
            raise ArtifactStoreError("FMEA_ARTIFACT_PATH_INVALID")
        return original_inspect(path, directory=directory, allow_missing=allow_missing)

    monkeypatch.setattr(store, "_inspect", reject_owned_parent)

    store._remove_owned_tree(owned, expected)

    assert owned_file.read_bytes() == b"owned"


@pytest.mark.skipif(os.name != "nt", reason="Windows handle deletion regression")
def test_windows_cleanup_handle_does_not_delete_a_post_check_replacement(tmp_path: Path) -> None:
    owned = tmp_path / "artifacts" / WORKSPACE / "artifacts" / ".owned.txt"
    displaced = owned.with_name(".displaced-owned.txt")

    def replace_after_handle_check(stage: str) -> None:
        if stage == "before_cleanup_remove":
            owned.rename(displaced)
            owned.write_bytes(b"foreign")

    store = _store(tmp_path, fault_hook=replace_after_handle_check)
    owned.write_bytes(b"owned")
    expected = owned.lstat()

    store._remove_file(owned, expected=expected)

    assert owned.read_bytes() == b"foreign"
    assert not displaced.exists()


def test_get_rejects_corrupt_payload_and_latest_pointer(tmp_path: Path) -> None:
    store = _store(tmp_path)
    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    published.path.write_bytes(b"tampered")

    with pytest.raises(ArtifactStoreError) as artifact_error:
        store.get(ARTIFACT, WORKSPACE)
    assert artifact_error.value.code == "FMEA_ARTIFACT_INTEGRITY_FAILED"

    published.path.write_bytes(PAYLOAD)
    pointer = store.runs_root / RUN / ".latest.json"
    pointer.write_bytes(b"not-json")
    with pytest.raises(ArtifactStoreError) as latest_error:
        store.latest(RUN)
    assert latest_error.value.code == "FMEA_ARTIFACT_INTEGRITY_FAILED"


def test_get_rejects_wrong_workspace_and_publish_rejects_malformed_inputs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    with pytest.raises(ArtifactStoreError) as workspace_error:
        store.get(ARTIFACT, "other-workspace")
    assert workspace_error.value.code == "FMEA_ARTIFACT_WORKSPACE_MISMATCH"

    with pytest.raises(ArtifactStoreError) as manifest_error:
        store.publish("new-run", FILENAME, PAYLOAD, object())  # type: ignore[arg-type]
    assert manifest_error.value.code == "FMEA_ARTIFACT_MANIFEST_INVALID"

    oversized = _store(tmp_path / "small", max_artifact_bytes=1)
    with pytest.raises(ArtifactStoreError) as size_error:
        oversized.publish(RUN, FILENAME, PAYLOAD, _manifest())
    assert size_error.value.code == "FMEA_ARTIFACT_LIMIT_EXCEEDED"


def test_symlinked_artifact_path_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = store.artifacts_root / ARTIFACT
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(ArtifactStoreError) as error:
        store.get(ARTIFACT, WORKSPACE)
    assert error.value.code == "FMEA_ARTIFACT_PATH_INVALID"


def test_windows_reparse_attribute_is_rejected_without_symlink_privilege(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(tmp_path)
    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    original_lstat = Path.lstat

    def marked_lstat(path: Path):
        result = original_lstat(path)
        if path == published.directory:
            return _ReparseStat(result)
        return result

    monkeypatch.setattr(Path, "lstat", marked_lstat)

    with pytest.raises(ArtifactStoreError) as error:
        store.get(ARTIFACT, WORKSPACE)
    assert error.value.code == "FMEA_ARTIFACT_PATH_INVALID"


def test_foreign_reservation_times_out_retryably_without_unlinking_owner(tmp_path: Path) -> None:
    elapsed = 0.0

    def monotonic() -> float:
        return elapsed

    def wait(duration: float) -> None:
        nonlocal elapsed
        elapsed += duration

    store = _store(
        tmp_path,
        reservation_timeout_seconds=0.03,
        reservation_poll_seconds=0.01,
        monotonic_seam=monotonic,
        reservation_wait_seam=wait,
    )
    reservation = store.workspace_root / ".locks" / ARTIFACT
    reservation.mkdir()
    owner = reservation / ".owner"
    owner.write_bytes(b'{"token":"foreign-owner"}\n')

    with pytest.raises(ArtifactStoreError) as error:
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert error.value.code == "FMEA_ARTIFACT_BUSY"
    assert error.value.retryable is True
    assert owner.read_bytes() == b'{"token":"foreign-owner"}\n'


def test_publisher_never_releases_a_reservation_after_owner_token_changes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    owner = store.workspace_root / ".locks" / ARTIFACT / ".owner"
    foreign_owner = b'{"token":"replacement-owner"}\n'

    def replace_owner(stage: str) -> None:
        if stage == "after_payload_write":
            owner.write_bytes(foreign_owner)
            raise RuntimeError

    store._fault_hook = replace_owner

    with pytest.raises(ArtifactStoreError):
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert owner.read_bytes() == foreign_owner


def test_identical_cross_process_publish_converges(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    first_attempted = context.Event()
    second_attempted = context.Event()
    results = context.Queue()
    root = str((tmp_path / "artifacts").resolve())
    first = context.Process(
        target=_multiprocess_publish,
        args=(root, ready, release, first_attempted, results),
        kwargs={"hold_reservation": True},
    )
    second = context.Process(
        target=_multiprocess_publish,
        args=(root, ready, release, second_attempted, results),
        kwargs={"hold_reservation": False},
    )
    first.start()
    try:
        assert first_attempted.wait(10)
        assert ready.wait(10)
        second.start()
        assert second_attempted.wait(10)
        release.set()
        first.join(15)
        second.join(15)
        assert first.exitcode == 0
        assert second.exitcode == 0
        outcomes = [results.get(timeout=5), results.get(timeout=5)]
        assert len(outcomes) == 2
        assert all(outcome == ("ok", _manifest().sha256) for outcome in outcomes)
        assert WorkspaceArtifactStore(root, WORKSPACE).latest(RUN) is not None
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None and process.is_alive():
                process.terminate()
            if process.pid is not None:
                process.join(5)


def test_manifest_file_is_canonical_and_contains_no_host_path(tmp_path: Path) -> None:
    store = _store(tmp_path)
    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    raw = published.manifest_path.read_bytes()
    decoded = json.loads(raw)

    assert raw == (json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert str(tmp_path) not in raw.decode()
