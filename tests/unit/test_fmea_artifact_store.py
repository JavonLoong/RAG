"""Focused tests for the contained, crash-safe export artifact store."""

from __future__ import annotations

import errno
import hashlib
import json
import multiprocessing
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import fmea_infrastructure.artifact_store as artifact_store_module
from fmea_application.delivery_contracts import ExportArtifactManifest, VerifiedExportArtifact
from fmea_infrastructure.artifact_store import ArtifactStoreError, WorkspaceArtifactStore

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


def _payload_path(store: WorkspaceArtifactStore) -> Path:
    return store.artifacts_root / ARTIFACT / FILENAME


def _manifest_path(store: WorkspaceArtifactStore) -> Path:
    return store.artifacts_root / ARTIFACT / ".manifest.json"


class _ReparseStat:
    def __init__(self, delegate: os.stat_result) -> None:
        self._delegate = delegate
        self.st_file_attributes = getattr(delegate, "st_file_attributes", 0) | 0x400

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)


class _PosixStat:
    def __init__(
        self,
        delegate: os.stat_result,
        *,
        owner_uid: int,
        writable: bool,
        reparse: bool,
    ) -> None:
        self._delegate = delegate
        self.st_mode = delegate.st_mode | 0o022 if writable else delegate.st_mode & ~0o022
        self.st_uid = owner_uid
        self.st_file_attributes = getattr(delegate, "st_file_attributes", 0) | (0x400 if reparse else 0)

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)


class _PosixOsProxy:
    name = "posix"
    O_CLOEXEC = 0
    O_DIRECTORY = 0
    O_NOFOLLOW = 0

    def __init__(
        self,
        *,
        writable_paths: tuple[Path, ...] = (),
        foreign_owner_paths: tuple[Path, ...] = (),
        reparse_paths: tuple[Path, ...] = (),
        symlink_paths: tuple[Path, ...] = (),
    ) -> None:
        self._current_uid = 1000
        self._descriptor_paths: dict[int, Path] = {}
        self._directory_descriptors: set[int] = set()
        self._next_directory_descriptor = 100_000
        self._writable_paths = {self._key(path) for path in writable_paths}
        self._foreign_owner_paths = {self._key(path) for path in foreign_owner_paths}
        self._reparse_paths = {self._key(path) for path in reparse_paths}
        self._symlink_paths = {self._key(path) for path in symlink_paths}
        self._pathname_redirects: dict[str, Path] = {}
        self.open_calls: list[tuple[str, int | None]] = []
        self.lease_mutations: list[str] = []

    @staticmethod
    def _key(path: str | Path) -> str:
        return os.path.normcase(os.path.abspath(os.fspath(path)))

    def _path(self, path: str | Path, dir_fd: int | None) -> Path:
        candidate = Path(path)
        if dir_fd is not None:
            candidate = self._descriptor_paths[dir_fd] / candidate
        target = Path(os.path.abspath(os.fspath(candidate)))
        if dir_fd is None:
            target_key = self._key(target)
            for original_key, replacement in self._pathname_redirects.items():
                if target_key == original_key or target_key.startswith(f"{original_key}{os.sep}"):
                    relative = os.path.relpath(target, original_key)
                    return replacement if relative == "." else replacement / relative
        return target

    def open(
        self,
        path: str | Path,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        target = self._path(path, dir_fd)
        self.open_calls.append((os.fspath(path), dir_fd))
        if self._key(target) in self._symlink_paths or target.is_symlink():
            raise OSError(errno.ELOOP, "link refused")
        if target.is_dir():
            descriptor = self._next_directory_descriptor
            self._next_directory_descriptor += 1
            self._directory_descriptors.add(descriptor)
        else:
            descriptor = os.open(target, flags, mode)
        self._descriptor_paths[descriptor] = target
        return descriptor

    def close(self, descriptor: int) -> None:
        if descriptor not in self._descriptor_paths:
            os.close(descriptor)
            return
        self._descriptor_paths.pop(descriptor)
        if descriptor in self._directory_descriptors:
            self._directory_descriptors.remove(descriptor)
            return
        os.close(descriptor)

    def fstat(self, descriptor: int) -> _PosixStat:
        path = self._descriptor_paths.get(descriptor)
        if path is None:
            return os.fstat(descriptor)
        delegate = path.lstat() if descriptor in self._directory_descriptors else os.fstat(descriptor)
        key = self._key(path)
        return _PosixStat(
            delegate,
            owner_uid=self._current_uid + 1 if key in self._foreign_owner_paths else self._current_uid,
            writable=key in self._writable_paths,
            reparse=key in self._reparse_paths,
        )

    def stat(
        self,
        path: str | Path,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> _PosixStat:
        target = self._path(path, dir_fd)
        delegate = os.stat(target, follow_symlinks=follow_symlinks)
        key = self._key(target)
        return _PosixStat(
            delegate,
            owner_uid=self._current_uid + 1 if key in self._foreign_owner_paths else self._current_uid,
            writable=key in self._writable_paths,
            reparse=key in self._reparse_paths,
        )

    def fsync(self, descriptor: int) -> None:
        if descriptor not in self._directory_descriptors:
            os.fsync(descriptor)

    def unlink(self, path: str | Path, *, dir_fd: int | None = None) -> None:
        target = self._path(path, dir_fd)
        if target.name.endswith(".artifact-lease"):
            self.lease_mutations.append("unlink")
        os.unlink(target)

    def rename(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        source_path = self._path(source, src_dir_fd)
        destination_path = self._path(destination, dst_dir_fd)
        if source_path.name.endswith(".artifact-lease") or destination_path.name.endswith(".artifact-lease"):
            self.lease_mutations.append("rename")
        os.rename(source_path, destination_path)

    def replace(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        source_path = self._path(source, src_dir_fd)
        destination_path = self._path(destination, dst_dir_fd)
        if source_path.name.endswith(".artifact-lease") or destination_path.name.endswith(".artifact-lease"):
            self.lease_mutations.append("replace")
        os.replace(source_path, destination_path)

    def geteuid(self) -> int:
        return self._current_uid

    def rebind_directory(self, original: Path, replacement: Path) -> None:
        original_key = self._key(original)
        for descriptor, path in tuple(self._descriptor_paths.items()):
            if descriptor in self._directory_descriptors and self._key(path) == original_key:
                self._descriptor_paths[descriptor] = replacement

    def redirect_pathname(self, original: Path, replacement: Path) -> None:
        self._pathname_redirects[self._key(original)] = replacement

    @property
    def open_descriptors(self) -> frozenset[int]:
        return frozenset(self._descriptor_paths)

    def __getattr__(self, name: str):
        return getattr(os, name)


class _FakeFcntl:
    LOCK_EX = 1
    LOCK_NB = 2
    LOCK_UN = 4

    def __init__(self, *, busy_attempts: int = 0) -> None:
        self.calls: list[tuple[int, int]] = []
        self._busy_attempts = busy_attempts
        self._attempts = 0

    def flock(self, descriptor: int, operation: int) -> None:
        self.calls.append((descriptor, operation))
        if operation == self.LOCK_EX | self.LOCK_NB:
            self._attempts += 1
            if self._attempts <= self._busy_attempts:
                raise BlockingIOError(errno.EAGAIN, "lease busy")
        return


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


def _hold_posix_lease(
    root: str,
    ready,
    release,
    *,
    abrupt_exit: bool,
) -> None:
    store = WorkspaceArtifactStore(root, WORKSPACE)
    reservation = store._reserve(ARTIFACT, RUN, FILENAME, PAYLOAD, _manifest())
    ready.set()
    if not release.wait(10):
        os._exit(98)
    if abrupt_exit:
        os._exit(17)
    store._release_reservation(reservation)


def _multiprocess_publish_after_wait(root: str, waiting, results) -> None:
    def wait(duration: float) -> None:
        waiting.set()
        time.sleep(duration)

    store = WorkspaceArtifactStore(
        root,
        WORKSPACE,
        reservation_timeout_seconds=5.0,
        reservation_poll_seconds=0.01,
        reservation_wait_seam=wait,
    )
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

    assert type(published) is VerifiedExportArtifact
    assert loaded == published
    assert latest == published
    assert _payload_path(store).read_bytes() == PAYLOAD
    assert published.manifest == _manifest()
    assert published.filename == FILENAME
    assert not tuple((store.artifacts_root / ARTIFACT).glob(".*.tmp-*"))


def test_public_store_contract_returns_application_owned_path_free_value(tmp_path: Path) -> None:
    store = _store(tmp_path)

    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    loaded = store.get(ARTIFACT, WORKSPACE)
    latest = store.latest(RUN)

    assert type(published) is VerifiedExportArtifact
    assert loaded == published
    assert latest == published
    assert not hasattr(published, "path")


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
    assert _payload_path(store).read_bytes() == PAYLOAD


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
    if os.name == "nt":
        assert not (store.artifacts_root / "artifact-2").exists()
    else:
        assert store.get("artifact-2", WORKSPACE).payload == next_payload


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
    if os.name == "nt":
        assert not (store.artifacts_root / "artifact-2").exists()
    else:
        assert store.get("artifact-2", WORKSPACE).payload == next_payload


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
    staged = tuple(store.artifacts_root.iterdir())
    if os.name == "nt":
        assert not staged
    else:
        assert len(staged) == 1
        assert staged[0].name.startswith(".artifact-tmp-")


def test_fsync_seam_failure_does_not_expose_the_staged_directory(tmp_path: Path) -> None:
    calls = 0
    fail_on_call = 1 if os.name == "nt" else 2

    def fail(_descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == fail_on_call:
            raise OSError

    store = _store(tmp_path, fsync_seam=fail)
    with pytest.raises(ArtifactStoreError) as error:
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert calls == fail_on_call
    assert error.value.code == "FMEA_ARTIFACT_STORAGE_FAILED"
    assert store.latest(RUN) is None
    staged = tuple(store.artifacts_root.iterdir())
    if os.name == "nt":
        assert not staged
    else:
        assert len(staged) == 1
        assert staged[0].name.startswith(".artifact-tmp-")


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


@pytest.mark.parametrize(
    ("entry_role", "directory"),
    [
        pytest.param("file", False, id="file"),
        pytest.param("directory", True, id="directory"),
        pytest.param("owner", False, id="owner"),
        pytest.param("reservation", True, id="reservation"),
    ],
)
def test_posix_cleanup_never_removes_a_second_stat_replacement(  # noqa: C901
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry_role: str,
    directory: bool,
) -> None:
    store = _store(tmp_path)
    parent = store.workspace_root / ".locks" if entry_role in {"owner", "reservation"} else store.artifacts_root
    if entry_role == "owner":
        parent = parent / "owned-reservation"
        parent.mkdir()
        target = parent / ".owner"
    else:
        target = parent / f".{entry_role}-cleanup"
    displaced = target.with_name(f".displaced-{target.name}")
    if directory:
        target.mkdir()
    else:
        target.write_bytes(b"owned")
    expected = target.lstat()
    parent_expected = target.parent.lstat()
    descriptor = 91
    stat_calls = 0
    operation_calls = 0
    original_unlink = os.unlink
    original_rmdir = os.rmdir

    def open_parent(path: str, _flags: int) -> int:
        assert os.fspath(path) == os.fspath(target.parent)
        return descriptor

    def inspect_parent(opened_descriptor: int) -> os.stat_result:
        assert opened_descriptor == descriptor
        return parent_expected

    def replace_after_second_stat(
        name: str,
        *,
        dir_fd: int,
        follow_symlinks: bool,
    ) -> os.stat_result:
        nonlocal stat_calls
        assert name == target.name
        assert dir_fd == descriptor
        assert follow_symlinks is False
        stat_calls += 1
        if stat_calls == 2:
            target.rename(displaced)
            if directory:
                target.mkdir()
            else:
                target.write_bytes(b"foreign")
        return expected

    def remove_replacement(name: str, *, dir_fd: int) -> None:
        nonlocal operation_calls
        assert name == target.name
        assert dir_fd == descriptor
        operation_calls += 1
        if directory:
            original_rmdir(target)
        else:
            original_unlink(target)

    monkeypatch.setattr(store, "_supports_relative_cleanup", lambda _operation: True)
    monkeypatch.setattr(
        artifact_store_module,
        "os",
        SimpleNamespace(
            name="posix",
            O_RDONLY=os.O_RDONLY,
            close=lambda opened_descriptor: None,
            fspath=os.fspath,
            fstat=inspect_parent,
            open=open_parent,
            rmdir=remove_replacement,
            stat=replace_after_second_stat,
            unlink=remove_replacement,
        ),
    )

    if directory:
        removed = store._remove_empty_directory(target, expected)
    else:
        removed = store._remove_file(target, expected=expected)

    assert stat_calls == 2
    assert operation_calls == 0
    assert removed is False
    assert target.exists()
    if directory:
        assert target.is_dir()
    else:
        assert target.read_bytes() == b"foreign"
    assert displaced.exists()


def test_posix_persistent_lease_file_allows_committed_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = _PosixOsProxy()
    monkeypatch.setattr(artifact_store_module, "os", proxy)
    monkeypatch.setattr(artifact_store_module, "_fcntl", _FakeFcntl())
    store = _store(tmp_path)
    monkeypatch.setattr(store, "_sync_directory", lambda _path: None)

    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    lease = store.workspace_root / ".locks" / f"{ARTIFACT}.artifact-lease"
    diagnostic = json.loads(lease.read_bytes())

    assert lease.is_file()
    assert not (store.workspace_root / ".locks" / ARTIFACT).exists()
    assert diagnostic == {
        "artifact_id": ARTIFACT,
        "export_run_id": RUN,
        "owner_token": diagnostic["owner_token"],
        "request_sha256": _manifest().sha256,
    }
    assert type(diagnostic["owner_token"]) is str
    assert len(diagnostic["owner_token"]) == 64
    assert PAYLOAD not in lease.read_bytes()
    assert str(tmp_path).encode() not in lease.read_bytes()
    assert store.publish(RUN, FILENAME, PAYLOAD, _manifest()) == published
    assert store.latest(RUN) == published
    assert proxy.lease_mutations == []


@pytest.mark.parametrize("violation", ["writable", "foreign-owner", "reparse"])
def test_posix_rejects_untrusted_server_owned_lock_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    violation: str,
) -> None:
    locks = tmp_path / "artifacts" / WORKSPACE / ".locks"
    proxy = _PosixOsProxy(
        writable_paths=(locks,) if violation == "writable" else (),
        foreign_owner_paths=(locks,) if violation == "foreign-owner" else (),
        reparse_paths=(locks,) if violation == "reparse" else (),
    )
    monkeypatch.setattr(artifact_store_module, "os", proxy)
    monkeypatch.setattr(artifact_store_module, "_fcntl", _FakeFcntl())

    with pytest.raises(ArtifactStoreError) as error:
        _store(tmp_path)

    assert error.value.code == "FMEA_ARTIFACT_PATH_INVALID"
    assert not proxy.open_descriptors


def test_posix_rejects_reparse_lease_entry_without_descriptor_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lease = tmp_path / "artifacts" / WORKSPACE / ".locks" / f"{ARTIFACT}.artifact-lease"
    proxy = _PosixOsProxy(reparse_paths=(lease,))
    monkeypatch.setattr(artifact_store_module, "os", proxy)
    monkeypatch.setattr(artifact_store_module, "_fcntl", _FakeFcntl())
    store = _store(tmp_path)

    with pytest.raises(ArtifactStoreError) as error:
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert error.value.code == "FMEA_ARTIFACT_PATH_INVALID"
    assert not proxy.open_descriptors


@pytest.mark.parametrize("target_kind", ["ancestor", "lease"])
def test_posix_rejects_symlinked_lease_path_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_kind: str,
) -> None:
    workspace = tmp_path / "artifacts" / WORKSPACE
    lease = workspace / ".locks" / f"{ARTIFACT}.artifact-lease"
    target = workspace if target_kind == "ancestor" else lease
    proxy = _PosixOsProxy(symlink_paths=(target,))
    monkeypatch.setattr(artifact_store_module, "os", proxy)
    monkeypatch.setattr(artifact_store_module, "_fcntl", _FakeFcntl())

    with pytest.raises(ArtifactStoreError) as error:
        store = _store(tmp_path)
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert error.value.code == "FMEA_ARTIFACT_PATH_INVALID"
    assert not proxy.open_descriptors


def test_posix_lease_open_is_anchored_to_verified_locks_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = _PosixOsProxy()
    monkeypatch.setattr(artifact_store_module, "os", proxy)
    monkeypatch.setattr(artifact_store_module, "_fcntl", _FakeFcntl())
    store = _store(tmp_path)
    monkeypatch.setattr(store, "_sync_directory", lambda _path: None)

    store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    lease_name = f"{ARTIFACT}.artifact-lease"
    lease_opens = [(path, dir_fd) for path, dir_fd in proxy.open_calls if str(path).endswith(lease_name)]
    assert lease_opens == [(lease_name, lease_opens[0][1])]
    assert lease_opens[0][1] is not None
    assert not proxy.open_descriptors


def test_posix_parent_replacement_after_validation_cannot_redirect_lease_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy = _PosixOsProxy()
    locks = tmp_path / "artifacts" / WORKSPACE / ".locks"
    displaced = locks.with_name(".locks-displaced")
    outside = tmp_path / "outside"
    outside.mkdir()
    triggered = False

    def replace_locks_path(stage: str) -> None:
        nonlocal triggered
        if stage != "after_posix_locks_open" or triggered:
            return
        triggered = True
        locks.rename(displaced)
        proxy.rebind_directory(locks, displaced)
        locks.mkdir()
        locks.joinpath("foreign-sentinel.txt").write_text("foreign", encoding="utf-8")
        proxy.redirect_pathname(locks, outside)

    monkeypatch.setattr(artifact_store_module, "os", proxy)
    monkeypatch.setattr(artifact_store_module, "_fcntl", _FakeFcntl())
    store = _store(tmp_path, fault_hook=replace_locks_path)
    monkeypatch.setattr(store, "_sync_directory", lambda _path: None)

    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    lease_name = f"{ARTIFACT}.artifact-lease"
    assert triggered is True
    assert store.latest(RUN) == published
    assert locks.joinpath("foreign-sentinel.txt").read_text(encoding="utf-8") == "foreign"
    assert not locks.joinpath(lease_name).exists()
    assert not outside.joinpath(lease_name).exists()
    assert displaced.joinpath(lease_name).is_file()
    assert not proxy.open_descriptors


def test_posix_lease_releases_after_fault_and_retry_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_after_write(stage: str) -> None:
        if stage == "after_payload_write":
            raise RuntimeError

    if os.name == "nt":
        monkeypatch.setattr(artifact_store_module, "os", _PosixOsProxy())
        monkeypatch.setattr(artifact_store_module, "_fcntl", _FakeFcntl())
    store = _store(
        tmp_path,
        fault_hook=fail_after_write,
    )
    if os.name == "nt":
        monkeypatch.setattr(store, "_sync_directory", lambda _path: None)

    with pytest.raises(ArtifactStoreError):
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    store._fault_hook = None
    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert store.latest(RUN) == published
    assert not (store.workspace_root / ".locks" / ARTIFACT).exists()
    assert (store.workspace_root / ".locks" / f"{ARTIFACT}.artifact-lease").is_file()
    orphaned = tuple(path for path in store.artifacts_root.iterdir() if path.name.startswith(".artifact-tmp-"))
    assert len(orphaned) == 1
    assert (orphaned[0] / FILENAME).read_bytes() == PAYLOAD


def test_posix_lease_ignores_legacy_directory_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(artifact_store_module, "os", _PosixOsProxy())
    monkeypatch.setattr(artifact_store_module, "_fcntl", _FakeFcntl())
    store = _store(tmp_path)
    monkeypatch.setattr(store, "_sync_directory", lambda _path: None)
    legacy = store.workspace_root / ".locks" / ARTIFACT
    legacy.mkdir()
    owner = legacy / ".owner"
    owner.write_bytes(b'{"token":"legacy"}\n')

    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert store.latest(RUN) == published
    assert owner.read_bytes() == b'{"token":"legacy"}\n'
    assert (store.workspace_root / ".locks" / f"{ARTIFACT}.artifact-lease").is_file()


@pytest.mark.parametrize("lease_module", [None, SimpleNamespace()], ids=["missing-module", "missing-flock"])
def test_posix_without_flock_fails_retryably_without_path_lock_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    lease_module: object,
) -> None:
    monkeypatch.setattr(artifact_store_module, "os", _PosixOsProxy())
    monkeypatch.setattr(artifact_store_module, "_fcntl", lease_module)
    store = _store(tmp_path)

    with pytest.raises(ArtifactStoreError) as error:
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert error.value.code == "FMEA_ARTIFACT_BUSY"
    assert error.value.retryable is True
    assert not tuple(store.workspace_root.joinpath(".locks").iterdir())


def test_posix_lease_retries_contention_with_existing_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elapsed = 0.0

    def monotonic() -> float:
        return elapsed

    def wait(duration: float) -> None:
        nonlocal elapsed
        elapsed += duration

    fake_fcntl = _FakeFcntl(busy_attempts=2)
    monkeypatch.setattr(artifact_store_module, "os", _PosixOsProxy())
    monkeypatch.setattr(artifact_store_module, "_fcntl", fake_fcntl)
    store = _store(
        tmp_path,
        monotonic_seam=monotonic,
        reservation_wait_seam=wait,
    )
    monkeypatch.setattr(store, "_sync_directory", lambda _path: None)

    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert store.latest(RUN) == published
    assert elapsed == pytest.approx(0.04)
    attempts = [operation for _descriptor, operation in fake_fcntl.calls if operation != _FakeFcntl.LOCK_UN]
    assert attempts == [_FakeFcntl.LOCK_EX | _FakeFcntl.LOCK_NB] * 3


def test_posix_lease_contention_times_out_without_unbounded_wait(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elapsed = 0.0

    def monotonic() -> float:
        return elapsed

    def wait(duration: float) -> None:
        nonlocal elapsed
        elapsed += duration

    monkeypatch.setattr(artifact_store_module, "os", _PosixOsProxy())
    monkeypatch.setattr(artifact_store_module, "_fcntl", _FakeFcntl(busy_attempts=100))
    store = _store(
        tmp_path,
        reservation_timeout_seconds=0.03,
        reservation_poll_seconds=0.01,
        monotonic_seam=monotonic,
        reservation_wait_seam=wait,
    )

    with pytest.raises(ArtifactStoreError) as error:
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert error.value.code == "FMEA_ARTIFACT_BUSY"
    assert error.value.retryable is True
    assert elapsed == pytest.approx(0.03)
    assert not tuple(store.artifacts_root.iterdir())


def test_posix_lease_double_release_unlocks_and_closes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_fcntl = _FakeFcntl()
    monkeypatch.setattr(artifact_store_module, "os", _PosixOsProxy())
    monkeypatch.setattr(artifact_store_module, "_fcntl", fake_fcntl)
    store = _store(tmp_path)
    reservation = store._reserve(ARTIFACT, RUN, FILENAME, PAYLOAD, _manifest())
    descriptor = reservation.lease_descriptor

    store._release_reservation(reservation)
    store._release_reservation(reservation)

    assert descriptor is not None
    assert [operation for _descriptor, operation in fake_fcntl.calls] == [
        _FakeFcntl.LOCK_EX | _FakeFcntl.LOCK_NB,
        _FakeFcntl.LOCK_UN,
    ]
    with pytest.raises(OSError):
        os.fstat(descriptor)


def test_posix_lease_does_not_leak_descriptor_when_deadline_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_monotonic() -> float:
        raise RuntimeError

    proxy = _PosixOsProxy()
    monkeypatch.setattr(artifact_store_module, "os", proxy)
    monkeypatch.setattr(artifact_store_module, "_fcntl", _FakeFcntl())
    store = _store(tmp_path, monotonic_seam=fail_monotonic)
    proxy.open_calls.clear()

    with pytest.raises(ArtifactStoreError):
        store.publish(RUN, FILENAME, PAYLOAD, _manifest())

    assert proxy.open_calls == []
    assert not proxy.open_descriptors


@pytest.mark.skipif(
    os.name == "nt" or getattr(artifact_store_module, "_fcntl", None) is None,
    reason="real POSIX flock regression",
)
def test_posix_process_lease_is_bounded_busy_then_recovers_after_close(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    root = str((tmp_path / "artifacts").resolve())
    holder = context.Process(
        target=_hold_posix_lease,
        args=(root, ready, release),
        kwargs={"abrupt_exit": False},
    )
    holder.start()
    try:
        assert ready.wait(10)
        elapsed = 0.0

        def monotonic() -> float:
            return elapsed

        def wait(duration: float) -> None:
            nonlocal elapsed
            elapsed += duration

        competitor = WorkspaceArtifactStore(
            root,
            WORKSPACE,
            reservation_timeout_seconds=0.03,
            reservation_poll_seconds=0.01,
            monotonic_seam=monotonic,
            reservation_wait_seam=wait,
        )
        with pytest.raises(ArtifactStoreError) as error:
            competitor.publish(RUN, FILENAME, PAYLOAD, _manifest())
        assert error.value.code == "FMEA_ARTIFACT_BUSY"
        assert error.value.retryable is True
        assert elapsed == pytest.approx(0.03)
        assert not tuple(competitor.artifacts_root.iterdir())

        release.set()
        holder.join(10)
        assert holder.exitcode == 0
        assert competitor.publish(RUN, FILENAME, PAYLOAD, _manifest()) == competitor.latest(RUN)
    finally:
        release.set()
        if holder.is_alive():
            holder.terminate()
        holder.join(5)


@pytest.mark.skipif(
    os.name == "nt" or getattr(artifact_store_module, "_fcntl", None) is None,
    reason="real POSIX flock regression",
)
def test_posix_process_exit_releases_lease_to_waiting_competitor(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    crash = context.Event()
    waiting = context.Event()
    results = context.Queue()
    root = str((tmp_path / "artifacts").resolve())
    holder = context.Process(
        target=_hold_posix_lease,
        args=(root, ready, crash),
        kwargs={"abrupt_exit": True},
    )
    competitor = context.Process(target=_multiprocess_publish_after_wait, args=(root, waiting, results))
    holder.start()
    try:
        assert ready.wait(10)
        competitor.start()
        assert waiting.wait(10)
        crash.set()
        holder.join(10)
        competitor.join(15)
        assert holder.exitcode == 17
        assert competitor.exitcode == 0
        assert results.get(timeout=5) == ("ok", _manifest().sha256)
        assert WorkspaceArtifactStore(root, WORKSPACE).latest(RUN) is not None
    finally:
        crash.set()
        for process in (holder, competitor):
            if process.pid is not None and process.is_alive():
                process.terminate()
            if process.pid is not None:
                process.join(5)


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
    store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    _payload_path(store).write_bytes(b"tampered")

    with pytest.raises(ArtifactStoreError) as artifact_error:
        store.get(ARTIFACT, WORKSPACE)
    assert artifact_error.value.code == "FMEA_ARTIFACT_INTEGRITY_FAILED"

    _payload_path(store).write_bytes(PAYLOAD)
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
    store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    artifact_directory = store.artifacts_root / ARTIFACT
    original_lstat = Path.lstat

    def marked_lstat(path: Path):
        result = original_lstat(path)
        if path == artifact_directory:
            return _ReparseStat(result)
        return result

    monkeypatch.setattr(Path, "lstat", marked_lstat)

    with pytest.raises(ArtifactStoreError) as error:
        store.get(ARTIFACT, WORKSPACE)
    assert error.value.code == "FMEA_ARTIFACT_PATH_INVALID"


@pytest.mark.skipif(os.name != "nt", reason="Windows directory reservation regression")
def test_windows_foreign_reservation_times_out_without_unlinking_owner(tmp_path: Path) -> None:
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


@pytest.mark.skipif(os.name != "nt", reason="Windows directory reservation regression")
def test_windows_publisher_preserves_reservation_after_owner_token_changes(tmp_path: Path) -> None:
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
    store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    raw = _manifest_path(store).read_bytes()
    decoded = json.loads(raw)

    assert raw == (json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert str(tmp_path) not in raw.decode()
