"""Contained, verified, and crash-safe storage for export artifacts.

The store deliberately owns the complete filesystem layout.  Callers provide an
export identity and bytes, never an output path.  A final artifact directory is
immutable after its atomic rename; the per-run latest pointer is updated only
after that directory has been independently read back and verified.
"""

from __future__ import annotations

import errno
import hashlib
import json
import ntpath
import os
import stat
import tempfile
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.filename_policy import validate_filename
from fmea_application.delivery_contracts import ExportArtifactManifest, ExportFormat

MAX_ARTIFACT_BYTES = 1_073_741_824
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_POINTER_BYTES = 4096
_MANIFEST_FILENAME = ".manifest.json"
_LATEST_FILENAME = ".latest.json"
_TEMP_PREFIX = ".artifact-tmp-"
_WINDOWS_RESERVED_BASENAMES = frozenset({
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
})
_INVALID_ID_CHARACTERS = frozenset('\\/:*?"<>|')
_MANIFEST_FIELDS = frozenset({
    "artifact_id",
    "export_run_id",
    "publication_id",
    "revision_id",
    "snapshot_hash",
    "format",
    "media_type",
    "byte_length",
    "sha256",
    "draft_preview",
    "created_at",
    "snapshot_id",
    "filename",
})
_POINTER_FIELDS = frozenset({"artifact_id", "export_run_id", "workspace_id"})

_LOCAL_LOCKS: dict[str, threading.RLock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


def _raise_short_write() -> NoReturn:
    raise OSError(errno.EIO, "short artifact write")


class ArtifactStoreError(FmeaDomainError):
    """Stable, bounded error raised at the artifact storage boundary."""

    def __init__(self, code: str, message: str = "artifact store operation failed") -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """One independently verified immutable artifact returned by the store."""

    workspace_id: str
    export_run_id: str
    artifact_id: str
    filename: str
    payload: bytes
    manifest: ExportArtifactManifest
    path: Path

    @property
    def run_id(self) -> str:
        return self.export_run_id

    @property
    def directory(self) -> Path:
        return self.path.parent

    @property
    def payload_path(self) -> Path:
        return self.path

    @property
    def artifact_path(self) -> Path:
        return self.path

    @property
    def manifest_path(self) -> Path:
        return self.directory / _MANIFEST_FILENAME

    def __fspath__(self) -> str:
        return os.fspath(self.path)


class _LatestUpdateError(ArtifactStoreError):
    def __init__(self, code: str, message: str, *, pointer_replaced: bool) -> None:
        super().__init__(code, message)
        self.pointer_replaced = pointer_replaced


def _raise(code: str, message: str = "artifact store operation failed") -> NoReturn:
    raise ArtifactStoreError(code, message)


def _is_reparse_point(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _same_file(first: os.stat_result, second: os.stat_result) -> bool:
    first_identity = (int(getattr(first, "st_dev", 0)), int(getattr(first, "st_ino", 0)))
    second_identity = (int(getattr(second, "st_dev", 0)), int(getattr(second, "st_ino", 0)))
    if first_identity != (0, 0) and second_identity != (0, 0):
        return first_identity == second_identity
    return (
        first.st_mode,
        first.st_size,
        getattr(first, "st_mtime_ns", 0),
        getattr(first, "st_ctime_ns", 0),
    ) == (
        second.st_mode,
        second.st_size,
        getattr(second, "st_mtime_ns", 0),
        getattr(second, "st_ctime_ns", 0),
    )


def _strict_json(data: bytes) -> object:
    def reject_constant(value: str) -> NoReturn:
        raise ValueError(value)

    return json.loads(data.decode("utf-8", errors="strict"), parse_constant=reject_constant)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _safe_segment(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value or len(value) > 256:
        _raise("FMEA_ARTIFACT_PATH_INVALID", f"{field_name} is not a contained identity")
    if ntpath.isabs(value) or value in {".", ".."} or ".." in value:
        _raise("FMEA_ARTIFACT_PATH_INVALID", f"{field_name} is not a contained identity")
    if any(character in _INVALID_ID_CHARACTERS for character in value) or value.endswith((".", " ")):
        _raise("FMEA_ARTIFACT_PATH_INVALID", f"{field_name} is not a contained identity")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        _raise("FMEA_ARTIFACT_PATH_INVALID", f"{field_name} is not a contained identity")
    if value.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_BASENAMES:
        _raise("FMEA_ARTIFACT_PATH_INVALID", f"{field_name} is not a contained identity")
    return value


def _absolute_root(root: str | Path) -> Path:
    if not isinstance(root, str | Path):
        _raise("FMEA_ARTIFACT_PATH_INVALID", "artifact root is invalid")
    candidate = Path(root)
    if not candidate.is_absolute():
        _raise("FMEA_ARTIFACT_PATH_INVALID", "artifact root must be absolute")
    return Path(os.path.abspath(os.fspath(candidate)))


class WorkspaceArtifactStore:
    """Store export artifacts under one server-owned workspace directory."""

    def __init__(
        self,
        artifact_root: str | Path,
        workspace_id: str,
        *,
        max_artifact_bytes: int = MAX_ARTIFACT_BYTES,
        fault_hook: Callable[[str], None] | None = None,
        fsync_seam: Callable[[int], None] | None = None,
    ) -> None:
        self._root = _absolute_root(artifact_root)
        self._workspace_id = _safe_segment(workspace_id, "workspace_id")
        if isinstance(max_artifact_bytes, bool) or not isinstance(max_artifact_bytes, int) or max_artifact_bytes <= 0:
            _raise("FMEA_ARTIFACT_LIMIT_INVALID", "artifact size limit is invalid")
        self._max_artifact_bytes = min(max_artifact_bytes, MAX_ARTIFACT_BYTES)
        self._fault_hook = fault_hook
        self._fsync_seam = fsync_seam
        self._workspace_root = self._root / self._workspace_id
        self._artifacts_root = self._workspace_root / "artifacts"
        self._runs_root = self._workspace_root / "runs"
        self._locks_root = self._workspace_root / ".locks"
        self._ensure_directory(self._root)
        self._ensure_directory(self._workspace_root)
        self._ensure_directory(self._artifacts_root)
        self._ensure_directory(self._runs_root)
        self._ensure_directory(self._locks_root)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def workspace_id(self) -> str:
        return self._workspace_id

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    @property
    def artifacts_root(self) -> Path:
        return self._artifacts_root

    @property
    def runs_root(self) -> Path:
        return self._runs_root

    def _fault(self, stage: str) -> None:
        if self._fault_hook is not None:
            self._fault_hook(stage)

    def _fsync(self, descriptor: int) -> None:
        if self._fsync_seam is not None:
            self._fsync_seam(descriptor)
        else:
            os.fsync(descriptor)

    @staticmethod
    def _path_parts(path: Path) -> tuple[str, ...]:
        anchor_parts = Path(path.anchor).parts if path.anchor else ()
        return tuple(path.parts[len(anchor_parts) :])

    def _ensure_directory(self, path: Path) -> None:
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            _raise("FMEA_ARTIFACT_PATH_INVALID", "artifact path is outside the server root")
            raise AssertionError from exc
        current = Path(path.anchor) if path.anchor else Path()
        for part in self._path_parts(path):
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise ArtifactStoreError(
                        "FMEA_ARTIFACT_STORAGE_FAILED", "artifact directory creation failed"
                    ) from exc
                try:
                    info = current.lstat()
                except OSError as exc:
                    raise ArtifactStoreError(
                        "FMEA_ARTIFACT_STORAGE_FAILED", "artifact directory validation failed"
                    ) from exc
            except OSError as exc:
                raise ArtifactStoreError(
                    "FMEA_ARTIFACT_STORAGE_FAILED", "artifact directory validation failed"
                ) from exc
            if _is_reparse_point(info) or not stat.S_ISDIR(info.st_mode):
                _raise("FMEA_ARTIFACT_PATH_INVALID", "artifact path is not a normal directory")

    def _inspect(self, path: Path, *, directory: bool, allow_missing: bool) -> os.stat_result | None:  # noqa: C901
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            _raise("FMEA_ARTIFACT_PATH_INVALID", "artifact path is outside the server root")
            raise AssertionError from exc
        current = self._root
        try:
            root_info = current.lstat()
        except FileNotFoundError:
            if allow_missing:
                return None
            _raise("FMEA_ARTIFACT_NOT_FOUND", "artifact was not found")
        except OSError as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact path validation failed") from exc
        if _is_reparse_point(root_info) or not stat.S_ISDIR(root_info.st_mode):
            _raise("FMEA_ARTIFACT_PATH_INVALID", "artifact path is not a normal directory")
        relative = path.relative_to(self._root)
        for index, part in enumerate(relative.parts):
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                if allow_missing:
                    return None
                _raise("FMEA_ARTIFACT_NOT_FOUND", "artifact was not found")
            except OSError as exc:
                raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact path validation failed") from exc
            if _is_reparse_point(info):
                _raise("FMEA_ARTIFACT_PATH_INVALID", "artifact path contains a link or reparse point")
            is_final = index == len(relative.parts) - 1
            if not is_final and not stat.S_ISDIR(info.st_mode):
                _raise("FMEA_ARTIFACT_PATH_INVALID", "artifact path contains a non-directory component")
            if is_final and stat.S_ISDIR(info.st_mode) is not directory:
                _raise("FMEA_ARTIFACT_PATH_INVALID", "artifact path has an unexpected type")
        return root_info if not relative.parts else info

    def _safe_artifact_path(self, artifact_id: str) -> Path:
        return self._artifacts_root / _safe_segment(artifact_id, "artifact_id")

    def _safe_run_path(self, run_id: str) -> Path:
        return self._runs_root / _safe_segment(run_id, "run_id")

    def _validate_filename(self, filename: object, expected_extension: str) -> str:
        try:
            normalized = validate_filename(filename, "filename", expected_extension=expected_extension)
        except (FmeaDomainError, TypeError, ValueError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_PATH_INVALID", "filename is not a contained filename") from exc
        if normalized != filename or normalized.casefold() == _MANIFEST_FILENAME.casefold():
            _raise("FMEA_ARTIFACT_PATH_INVALID", "filename is not a contained filename")
        return normalized

    @staticmethod
    def _manifest_fields(manifest: ExportArtifactManifest) -> dict[str, object]:
        return {
            "artifact_id": manifest.artifact_id,
            "export_run_id": manifest.export_run_id,
            "publication_id": manifest.publication_id,
            "revision_id": manifest.revision_id,
            "snapshot_hash": manifest.snapshot_hash,
            "format": manifest.format.value if isinstance(manifest.format, ExportFormat) else manifest.format,
            "media_type": manifest.media_type,
            "byte_length": manifest.byte_length,
            "sha256": manifest.sha256,
            "draft_preview": manifest.draft_preview,
            "created_at": manifest.created_at,
            "snapshot_id": manifest.snapshot_id,
            "filename": manifest.filename,
        }

    def _normalise_manifest(self, manifest: object) -> ExportArtifactManifest:
        if not isinstance(manifest, ExportArtifactManifest):
            _raise("FMEA_ARTIFACT_MANIFEST_INVALID", "artifact manifest is invalid")
        try:
            return ExportArtifactManifest(**self._manifest_fields(manifest))
        except (AttributeError, FmeaDomainError, TypeError, ValueError, OverflowError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_MANIFEST_INVALID", "artifact manifest is invalid") from exc

    def _validate_manifest_and_payload(  # noqa: C901
        self,
        run_id: object,
        filename: object,
        payload: object,
        manifest: object,
    ) -> ExportArtifactManifest:
        if not isinstance(run_id, str):
            _raise("FMEA_ARTIFACT_BINDING_INVALID", "export run binding is invalid")
        safe_run_id = _safe_segment(run_id, "run_id")
        if type(payload) is not bytes:
            _raise("FMEA_ARTIFACT_PAYLOAD_INVALID", "artifact payload must be bytes")
        normalized = self._normalise_manifest(manifest)
        _safe_segment(normalized.export_run_id, "export_run_id")
        _safe_segment(normalized.artifact_id, "artifact_id")
        if normalized.export_run_id != safe_run_id:
            _raise("FMEA_ARTIFACT_BINDING_INVALID", "export run does not match artifact manifest")
        if normalized.filename is None:
            _raise("FMEA_ARTIFACT_MANIFEST_INVALID", "artifact manifest must contain a filename")
        safe_filename = self._validate_filename(filename, normalized.format.value)
        stored_filename = self._validate_filename(normalized.filename, normalized.format.value)
        if safe_filename != stored_filename:
            _raise("FMEA_ARTIFACT_BINDING_INVALID", "filename does not match artifact manifest")
        expected_media_type = {
            ExportFormat.JSON: "application/json",
            ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ExportFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get(normalized.format)
        if expected_media_type is None or normalized.media_type != expected_media_type:
            _raise("FMEA_ARTIFACT_MANIFEST_INVALID", "artifact media type does not match format")
        if len(payload) > self._max_artifact_bytes:
            _raise("FMEA_ARTIFACT_LIMIT_EXCEEDED", "artifact payload exceeds the configured limit")
        if len(payload) != normalized.byte_length:
            _raise("FMEA_ARTIFACT_PAYLOAD_INVALID", "artifact payload length does not match manifest")
        digest = hashlib.sha256(payload).hexdigest()
        if normalized.sha256.removeprefix("sha256:") != digest:
            _raise("FMEA_ARTIFACT_PAYLOAD_INVALID", "artifact payload hash does not match manifest")
        if normalized.byte_length > MAX_ARTIFACT_BYTES:
            _raise("FMEA_ARTIFACT_LIMIT_EXCEEDED", "artifact payload exceeds the configured limit")
        return normalized

    def _write_open_descriptor(self, descriptor: int, path: Path, payload: bytes) -> None:
        try:
            view = memoryview(payload)
            offset = 0
            while offset < len(view):
                written = os.write(descriptor, view[offset:])
                if written <= 0:
                    _raise_short_write()
                offset += written
            self._fsync(descriptor)
            before = os.fstat(descriptor)
            current = path.lstat()
            if _is_reparse_point(current) or not stat.S_ISREG(current.st_mode) or not _same_file(before, current):
                _raise("FMEA_ARTIFACT_PATH_INVALID", "artifact file changed during publication")
            if before.st_size != len(payload):
                _raise_short_write()
        except ArtifactStoreError:
            raise
        except (OSError, ValueError, TypeError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact file write failed") from exc

    def _write_file(self, path: Path, payload: bytes) -> None:
        self._inspect(path.parent, directory=True, allow_missing=False)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
        if os.name != "nt":
            flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(os.fspath(path), flags, 0o600)
        except OSError as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact file creation failed") from exc
        try:
            self._write_open_descriptor(descriptor, path, payload)
        finally:
            os.close(descriptor)

    def _read_file(self, path: Path, *, max_bytes: int) -> bytes:  # noqa: C901
        expected = self._inspect(path, directory=False, allow_missing=False)
        if expected is None:
            _raise("FMEA_ARTIFACT_NOT_FOUND", "artifact was not found")
        if _is_reparse_point(expected) or not stat.S_ISREG(expected.st_mode):
            _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact is not a regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
        if os.name != "nt":
            flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(os.fspath(path), flags)
        except OSError as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact cannot be read") from exc
        chunks: list[bytes] = []
        total = 0
        try:
            opened = os.fstat(descriptor)
            if not _same_file(expected, opened):
                _raise("FMEA_ARTIFACT_PATH_INVALID", "stored artifact changed during read")
            while True:
                remaining = max_bytes + 1 - total
                if remaining <= 0:
                    _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact exceeds the configured limit")
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact exceeds the configured limit")
            closed = os.fstat(descriptor)
            current = path.lstat()
            if not _same_file(expected, closed) or not _same_file(expected, current) or closed.st_size != total:
                _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact changed during read")
            return b"".join(chunks)
        except ArtifactStoreError:
            raise
        except (OSError, ValueError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact cannot be read") from exc
        finally:
            os.close(descriptor)

    def _sync_directory(self, path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_BINARY", 0)
        try:
            descriptor = os.open(os.fspath(path), flags)
        except OSError as exc:
            unsupported = {
                errno.EINVAL,
                errno.ENOSYS,
                getattr(errno, "ENOTSUP", errno.EINVAL),
                getattr(errno, "EOPNOTSUPP", errno.EINVAL),
            }
            if os.name == "nt":
                unsupported.add(errno.EACCES)
            if exc.errno in unsupported:
                return
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact directory sync failed") from exc
        try:
            self._fsync(descriptor)
        except (OSError, ValueError, TypeError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact directory sync failed") from exc
        finally:
            os.close(descriptor)

    def _remove_file(self, path: Path, *, expected: os.stat_result | None = None) -> None:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return
        except OSError:
            return
        if expected is not None and not _same_file(expected, info):
            return
        if _is_reparse_point(info) or not stat.S_ISREG(info.st_mode):
            return
        with suppress(OSError):
            path.unlink()

    def _remove_tree(self, path: Path) -> None:
        try:
            path.relative_to(self._root)
        except ValueError:
            return
        try:
            info = path.lstat()
        except (FileNotFoundError, OSError):
            return
        if _is_reparse_point(info) or not stat.S_ISDIR(info.st_mode):
            return
        try:
            children = tuple(path.iterdir())
        except OSError:
            return
        for child in children:
            try:
                child_info = child.lstat()
            except OSError:
                return
            if _is_reparse_point(child_info):
                return
            if stat.S_ISDIR(child_info.st_mode):
                self._remove_tree(child)
            elif stat.S_ISREG(child_info.st_mode):
                self._remove_file(child)
            else:
                return
        with suppress(OSError):
            path.rmdir()

    def _remove_owned_tree(self, path: Path, expected: os.stat_result | None) -> None:
        if expected is None:
            return
        try:
            current = path.lstat()
        except (FileNotFoundError, OSError):
            return
        if not _same_file(expected, current):
            return
        self._remove_tree(path)

    def _manifest_bytes(self, manifest: ExportArtifactManifest) -> bytes:
        try:
            return _canonical_json(self._manifest_fields(manifest))
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_MANIFEST_INVALID", "artifact manifest is invalid") from exc

    def _decode_manifest(self, raw: bytes) -> ExportArtifactManifest:
        if len(raw) > _MAX_MANIFEST_BYTES:
            _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact manifest exceeds the configured limit")
        try:
            decoded = _strict_json(raw)
            if not isinstance(decoded, dict) or set(decoded) != _MANIFEST_FIELDS:
                _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact manifest is invalid")
            manifest = self._normalise_manifest(ExportArtifactManifest(**decoded))
            if self._manifest_bytes(manifest) != raw:
                _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact manifest is not canonical")
            return manifest  # noqa: TRY300
        except ArtifactStoreError:
            raise
        except (FmeaDomainError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact manifest is invalid") from exc

    def _verify_directory(self, directory: Path, artifact_id: str) -> StoredArtifact:
        info = self._inspect(directory, directory=True, allow_missing=False)
        if info is None:
            _raise("FMEA_ARTIFACT_NOT_FOUND", "artifact was not found")
        try:
            children = tuple(directory.iterdir())
        except OSError as exc:
            raise ArtifactStoreError(
                "FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact directory cannot be read"
            ) from exc
        for child in children:
            try:
                child_info = child.lstat()
            except OSError as exc:
                raise ArtifactStoreError(
                    "FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact directory cannot be read"
                ) from exc
            if _is_reparse_point(child_info):
                _raise("FMEA_ARTIFACT_PATH_INVALID", "stored artifact contains a link or reparse point")
            if not stat.S_ISREG(child_info.st_mode):
                _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact contains an unexpected entry")
        manifest_path = directory / _MANIFEST_FILENAME
        raw_manifest = self._read_file(manifest_path, max_bytes=_MAX_MANIFEST_BYTES)
        manifest = self._decode_manifest(raw_manifest)
        _safe_segment(manifest.artifact_id, "artifact_id")
        _safe_segment(manifest.export_run_id, "export_run_id")
        if manifest.artifact_id != artifact_id or manifest.filename is None:
            _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact identity does not match its directory")
        filename = self._validate_filename(manifest.filename, manifest.format.value)
        payload_path = directory / filename
        names = {child.name for child in children}
        if names != {filename, _MANIFEST_FILENAME}:
            _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact directory has unexpected entries")
        payload = self._read_file(payload_path, max_bytes=self._max_artifact_bytes)
        if len(payload) != manifest.byte_length or hashlib.sha256(payload).hexdigest() != manifest.sha256.removeprefix(
            "sha256:"
        ):
            _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "stored artifact bytes do not match its manifest")
        return StoredArtifact(
            workspace_id=self._workspace_id,
            export_run_id=manifest.export_run_id,
            artifact_id=manifest.artifact_id,
            filename=filename,
            payload=payload,
            manifest=manifest,
            path=payload_path,
        )

    def _read_existing(self, artifact_id: str) -> StoredArtifact | None:
        directory = self._safe_artifact_path(artifact_id)
        if self._inspect(directory, directory=True, allow_missing=True) is None:
            return None
        return self._verify_directory(directory, artifact_id)

    def _lock_for(self, artifact_id: str) -> threading.RLock:
        key = f"{self._root}\x00{self._workspace_id}\x00{artifact_id}"
        with _LOCAL_LOCKS_GUARD:
            return _LOCAL_LOCKS.setdefault(key, threading.RLock())

    def _reserve(self, artifact_id: str) -> Path:
        lock_path = self._locks_root / artifact_id
        try:
            lock_path.mkdir()
        except FileExistsError as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact publication is busy") from exc
        except OSError as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact reservation failed") from exc
        try:
            self._inspect(lock_path, directory=True, allow_missing=False)
        except ArtifactStoreError:
            self._remove_tree(lock_path)
            raise
        return lock_path

    def _pointer_bytes(self, run_id: str, artifact_id: str) -> bytes:
        return _canonical_json({
            "artifact_id": artifact_id,
            "export_run_id": run_id,
            "workspace_id": self._workspace_id,
        })

    def _decode_pointer(self, raw: bytes, run_id: str) -> str:
        if len(raw) > _MAX_POINTER_BYTES:
            _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "latest pointer is invalid")
        try:
            decoded = _strict_json(raw)
            if not isinstance(decoded, dict) or set(decoded) != _POINTER_FIELDS:
                _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "latest pointer is invalid")
            if decoded["workspace_id"] != self._workspace_id or decoded["export_run_id"] != run_id:
                _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "latest pointer identity is invalid")
            artifact_id = _safe_segment(decoded["artifact_id"], "artifact_id")
            if _canonical_json(decoded) != raw:
                _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "latest pointer is not canonical")
            return artifact_id  # noqa: TRY300
        except ArtifactStoreError:
            raise
        except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_INTEGRITY_FAILED", "latest pointer is invalid") from exc

    def _read_latest_pointer(self, run_id: str) -> StoredArtifact | None:
        run_directory = self._safe_run_path(run_id)
        if self._inspect(run_directory, directory=True, allow_missing=True) is None:
            return None
        pointer = run_directory / _LATEST_FILENAME
        if self._inspect(pointer, directory=False, allow_missing=True) is None:
            return None
        artifact_id = self._decode_pointer(self._read_file(pointer, max_bytes=_MAX_POINTER_BYTES), run_id)
        stored = self._read_existing(artifact_id)
        if stored is None or stored.export_run_id != run_id:
            _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "latest pointer targets a missing artifact")
        return stored

    def _write_latest(self, run_id: str, artifact_id: str) -> bool:
        run_directory = self._safe_run_path(run_id)
        self._ensure_directory(run_directory)
        pointer = run_directory / _LATEST_FILENAME
        existing = self._inspect(pointer, directory=False, allow_missing=True)
        if existing is not None and _is_reparse_point(existing):
            _raise("FMEA_ARTIFACT_PATH_INVALID", "latest pointer is not a normal file")
        raw = self._pointer_bytes(run_id, artifact_id)
        fd: int | None = None
        temporary: Path | None = None
        temporary_info: os.stat_result | None = None
        replaced = False
        try:
            fd, raw_name = tempfile.mkstemp(prefix=f"{_LATEST_FILENAME}.tmp-", dir=os.fspath(run_directory))
            temporary = Path(raw_name)
            temporary_info = temporary.lstat()
            self._write_open_descriptor(fd, temporary, raw)
            os.close(fd)
            fd = None
            self._fault("after_latest_temp_write")
            self._fault("before_latest_replace")
            os.replace(os.fspath(temporary), os.fspath(pointer))
            replaced = True
            temporary = None
            self._sync_directory(run_directory)
            return replaced  # noqa: TRY300
        except _LatestUpdateError:
            raise
        except ArtifactStoreError as exc:
            raise _LatestUpdateError(exc.code, "latest pointer update failed", pointer_replaced=replaced) from exc
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise _LatestUpdateError(
                "FMEA_ARTIFACT_STORAGE_FAILED", "latest pointer update failed", pointer_replaced=replaced
            ) from exc
        finally:
            if fd is not None:
                os.close(fd)
            if temporary is not None:
                self._remove_file(temporary, expected=temporary_info)

    def publish(  # noqa: C901
        self,
        run_id: str,
        filename: str,
        payload: bytes,
        manifest: ExportArtifactManifest,
    ) -> StoredArtifact:
        """Validate and atomically publish one immutable artifact."""

        normalized = self._validate_manifest_and_payload(run_id, filename, payload, manifest)
        artifact_id = normalized.artifact_id
        final_directory = self._safe_artifact_path(artifact_id)
        existing = self._read_existing(artifact_id)
        if existing is not None:
            if (
                existing.export_run_id == run_id
                and existing.filename == filename
                and existing.payload == payload
                and existing.manifest == normalized
            ):
                return existing
            _raise("FMEA_ARTIFACT_CONFLICT", "artifact identity already has different content")

        # The process lock keeps same-instance/thread callers out of the
        # reservation race; the mkdir reservation covers separate processes.
        local_lock = self._lock_for(artifact_id)
        with local_lock:
            existing = self._read_existing(artifact_id)
            if existing is not None:
                if (
                    existing.export_run_id == run_id
                    and existing.filename == filename
                    and existing.payload == payload
                    and existing.manifest == normalized
                ):
                    return existing
                _raise("FMEA_ARTIFACT_CONFLICT", "artifact identity already has different content")
            reservation = self._reserve(artifact_id)
            reservation_info = reservation.lstat()
            temporary: Path | None = None
            temporary_info: os.stat_result | None = None
            moved = False
            moved_info: os.stat_result | None = None
            pointer_replaced = False
            try:
                existing = self._read_existing(artifact_id)
                if existing is not None:
                    if (
                        existing.export_run_id == run_id
                        and existing.filename == filename
                        and existing.payload == payload
                        and existing.manifest == normalized
                    ):
                        return existing
                    _raise("FMEA_ARTIFACT_CONFLICT", "artifact identity already has different content")
                # Fail closed on a corrupt prior pointer before allocating a
                # new artifact; a failed publication must not hide it.
                self._read_latest_pointer(run_id)
                temporary = Path(tempfile.mkdtemp(prefix=_TEMP_PREFIX, dir=os.fspath(self._artifacts_root)))
                temporary_info = temporary.lstat()
                self._inspect(temporary, directory=True, allow_missing=False)
                payload_path = temporary / filename
                manifest_path = temporary / _MANIFEST_FILENAME
                self._write_file(payload_path, payload)
                self._fault("after_payload_write")
                self._write_file(manifest_path, self._manifest_bytes(normalized))
                self._fault("after_manifest_write")
                self._sync_directory(temporary)
                self._fault("after_temp_fsync")
                staged = self._verify_directory(temporary, artifact_id)
                if staged.payload != payload or staged.manifest != normalized:
                    _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "staged artifact verification failed")
                self._fault("after_temp_verify")
                self._fault("before_final_rename")
                os.rename(os.fspath(temporary), os.fspath(final_directory))
                moved = True
                moved_info = final_directory.lstat()
                temporary = None
                temporary_info = None
                self._sync_directory(self._artifacts_root)
                self._fault("after_final_rename")
                verified = self._verify_directory(final_directory, artifact_id)
                if verified.payload != payload or verified.manifest != normalized:
                    _raise("FMEA_ARTIFACT_INTEGRITY_FAILED", "published artifact verification failed")
                self._fault("after_final_verify")
                self._fault("before_latest")
                pointer_replaced = self._write_latest(run_id, artifact_id)
                self._fault("after_latest")
                return verified  # noqa: TRY300
            except _LatestUpdateError as exc:
                pointer_replaced = exc.pointer_replaced
                raise
            except ArtifactStoreError:
                raise
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact publication failed") from exc
            finally:
                if temporary is not None:
                    self._remove_owned_tree(temporary, temporary_info)
                if moved and not pointer_replaced:
                    self._remove_owned_tree(final_directory, moved_info)
                self._remove_owned_tree(reservation, reservation_info)

    def get(self, artifact_id: str, workspace_id: str) -> StoredArtifact:
        """Return an independently reverified artifact for this workspace."""

        if workspace_id != self._workspace_id:
            _raise("FMEA_ARTIFACT_WORKSPACE_MISMATCH", "artifact belongs to another workspace")
        _safe_segment(artifact_id, "artifact_id")
        stored = self._read_existing(artifact_id)
        if stored is None:
            _raise("FMEA_ARTIFACT_NOT_FOUND", "artifact was not found")
        return stored

    def latest(self, run_id: str) -> StoredArtifact | None:
        """Return the verified artifact selected by the run's atomic pointer."""

        _safe_segment(run_id, "run_id")
        return self._read_latest_pointer(run_id)


__all__ = [
    "MAX_ARTIFACT_BYTES",
    "ArtifactStoreError",
    "StoredArtifact",
    "WorkspaceArtifactStore",
]
