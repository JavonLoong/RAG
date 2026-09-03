"""Focused tests for the contained, crash-safe export artifact store."""

from __future__ import annotations

import hashlib
import json
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


def test_manifest_file_is_canonical_and_contains_no_host_path(tmp_path: Path) -> None:
    store = _store(tmp_path)
    published = store.publish(RUN, FILENAME, PAYLOAD, _manifest())
    raw = published.manifest_path.read_bytes()
    decoded = json.loads(raw)

    assert raw == (json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert str(tmp_path) not in raw.decode()
