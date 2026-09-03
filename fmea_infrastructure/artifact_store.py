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
import math
import ntpath
import os
import secrets
import stat
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, NoReturn

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.filename_policy import validate_filename
from fmea_application.delivery_contracts import ExportArtifactManifest, ExportFormat, VerifiedExportArtifact

MAX_ARTIFACT_BYTES = 1_073_741_824
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_POINTER_BYTES = 4096
_MANIFEST_FILENAME = ".manifest.json"
_LATEST_FILENAME = ".latest.json"
_OWNER_FILENAME = ".owner"
_TEMP_PREFIX = ".artifact-tmp-"
_DEFAULT_RESERVATION_TIMEOUT_SECONDS = 2.0
_DEFAULT_RESERVATION_POLL_SECONDS = 0.02
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

if os.name == "nt":
    _DELETE = 0x00010000
    _FILE_READ_ATTRIBUTES = 0x00000080
    _FILE_SHARE_ALL = 0x00000001 | 0x00000002 | 0x00000004
    _OPEN_EXISTING = 3
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    _FILE_DISPOSITION_INFO_CLASS = 4
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class _WindowsHandleInfo(ctypes.Structure):
        _fields_: ClassVar[list[tuple[str, object]]] = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    class _WindowsDispositionInfo(ctypes.Structure):
        _fields_: ClassVar[list[tuple[str, object]]] = [("delete_file", ctypes.c_ubyte)]

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _KERNEL32.CreateFileW.restype = wintypes.HANDLE
    _KERNEL32.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(_WindowsHandleInfo)]
    _KERNEL32.GetFileInformationByHandle.restype = wintypes.BOOL
    _KERNEL32.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _KERNEL32.SetFileInformationByHandle.restype = wintypes.BOOL
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL


def _raise_short_write() -> NoReturn:
    raise OSError(errno.EIO, "short artifact write")


class ArtifactStoreError(FmeaDomainError):
    """Stable, bounded error raised at the artifact storage boundary."""

    def __init__(
        self,
        code: str,
        message: str = "artifact store operation failed",
        *,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class _StoredArtifact:
    """Infrastructure-only verified artifact carrying its contained server path."""

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


@dataclass(frozen=True, slots=True)
class _Reservation:
    path: Path
    owner_path: Path
    token: str
    directory_info: os.stat_result
    owner_info: os.stat_result


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
        reservation_timeout_seconds: float = _DEFAULT_RESERVATION_TIMEOUT_SECONDS,
        reservation_poll_seconds: float = _DEFAULT_RESERVATION_POLL_SECONDS,
        monotonic_seam: Callable[[], float] = time.monotonic,
        reservation_wait_seam: Callable[[float], None] = time.sleep,
    ) -> None:
        self._root = _absolute_root(artifact_root)
        self._workspace_id = _safe_segment(workspace_id, "workspace_id")
        if isinstance(max_artifact_bytes, bool) or not isinstance(max_artifact_bytes, int) or max_artifact_bytes <= 0:
            _raise("FMEA_ARTIFACT_LIMIT_INVALID", "artifact size limit is invalid")
        self._max_artifact_bytes = min(max_artifact_bytes, MAX_ARTIFACT_BYTES)
        self._fault_hook = fault_hook
        self._fsync_seam = fsync_seam
        if (
            isinstance(reservation_timeout_seconds, bool)
            or not isinstance(reservation_timeout_seconds, int | float)
            or not math.isfinite(reservation_timeout_seconds)
            or reservation_timeout_seconds <= 0
            or isinstance(reservation_poll_seconds, bool)
            or not isinstance(reservation_poll_seconds, int | float)
            or not math.isfinite(reservation_poll_seconds)
            or reservation_poll_seconds <= 0
            or reservation_poll_seconds > reservation_timeout_seconds
            or not callable(monotonic_seam)
            or not callable(reservation_wait_seam)
        ):
            _raise("FMEA_ARTIFACT_LIMIT_INVALID", "artifact reservation policy is invalid")
        self._reservation_timeout_seconds = float(reservation_timeout_seconds)
        self._reservation_poll_seconds = float(reservation_poll_seconds)
        self._monotonic = monotonic_seam
        self._reservation_wait = reservation_wait_seam
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

    @staticmethod
    def _public_artifact(stored: _StoredArtifact) -> VerifiedExportArtifact:
        """Remove infrastructure paths before crossing the application port."""

        return VerifiedExportArtifact(
            workspace_id=stored.workspace_id,
            export_run_id=stored.export_run_id,
            artifact_id=stored.artifact_id,
            filename=stored.filename,
            payload=stored.payload,
            manifest=stored.manifest,
        )

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

    @staticmethod
    def _cleanup_entry_matches(
        expected: os.stat_result,
        current: os.stat_result,
        *,
        directory: bool,
    ) -> bool:
        expected_type_matches = stat.S_ISDIR(expected.st_mode) if directory else stat.S_ISREG(expected.st_mode)
        current_type_matches = stat.S_ISDIR(current.st_mode) if directory else stat.S_ISREG(current.st_mode)
        return (
            expected_type_matches
            and current_type_matches
            and not _is_reparse_point(expected)
            and not _is_reparse_point(current)
            and _same_file(expected, current)
        )

    @staticmethod
    def _supports_relative_cleanup(operation: Callable[..., object]) -> bool:
        return (
            operation in os.supports_dir_fd and os.stat in os.supports_dir_fd and os.stat in os.supports_follow_symlinks
        )

    def _remove_relative_entry(
        self,
        path: Path,
        expected: os.stat_result,
        parent_expected: os.stat_result,
        operation: Callable[..., object],
        *,
        directory: bool,
    ) -> bool:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            parent_descriptor = os.open(os.fspath(path.parent), flags)
        except OSError:
            return False
        try:
            opened_parent = os.fstat(parent_descriptor)
            current_parent = path.parent.lstat()
            if (
                _is_reparse_point(current_parent)
                or not stat.S_ISDIR(opened_parent.st_mode)
                or not _same_file(parent_expected, opened_parent)
                or not _same_file(parent_expected, current_parent)
            ):
                return False
            current = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
            if not self._cleanup_entry_matches(expected, current, directory=directory):
                return False
            final = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
            if not self._cleanup_entry_matches(expected, final, directory=directory):
                return False
            operation(path.name, dir_fd=parent_descriptor)
        except (FileNotFoundError, OSError, TypeError, ValueError):
            return False
        else:
            return True
        finally:
            os.close(parent_descriptor)

    def _remove_windows_entry(
        self,
        path: Path,
        expected: os.stat_result,
        *,
        directory: bool,
    ) -> bool:
        flags = _FILE_FLAG_OPEN_REPARSE_POINT
        if directory:
            flags |= _FILE_FLAG_BACKUP_SEMANTICS
        handle = _KERNEL32.CreateFileW(
            os.fspath(path),
            _DELETE | _FILE_READ_ATTRIBUTES,
            _FILE_SHARE_ALL,
            None,
            _OPEN_EXISTING,
            flags,
            None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            return False
        try:
            handle_info = _WindowsHandleInfo()
            if not _KERNEL32.GetFileInformationByHandle(handle, ctypes.byref(handle_info)):
                return False
            file_index = (int(handle_info.nFileIndexHigh) << 32) | int(handle_info.nFileIndexLow)
            expected_index = int(getattr(expected, "st_ino", 0))
            attributes = int(handle_info.dwFileAttributes)
            handle_is_directory = bool(attributes & _FILE_ATTRIBUTE_DIRECTORY)
            if (
                expected_index == 0
                or file_index != expected_index
                or handle_is_directory is not directory
                or bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)
                or _is_reparse_point(expected)
            ):
                return False
            self._fault("before_cleanup_remove")
            disposition = _WindowsDispositionInfo(1)
            if not _KERNEL32.SetFileInformationByHandle(
                handle,
                _FILE_DISPOSITION_INFO_CLASS,
                ctypes.byref(disposition),
                ctypes.sizeof(disposition),
            ):
                return False
        except (OSError, RuntimeError, TypeError, ValueError):
            return False
        else:
            return True
        finally:
            _KERNEL32.CloseHandle(handle)

    def _remove_entry(self, path: Path, expected: os.stat_result, *, directory: bool) -> bool:
        try:
            path.relative_to(self._root)
        except ValueError:
            return False
        try:
            parent_expected = self._inspect(path.parent, directory=True, allow_missing=False)
        except ArtifactStoreError:
            return False
        if parent_expected is None:
            return False
        operation = os.rmdir if directory else os.unlink
        if os.name == "nt":
            return self._remove_windows_entry(path, expected, directory=directory)
        if self._supports_relative_cleanup(operation):
            return self._remove_relative_entry(
                path,
                expected,
                parent_expected,
                operation,
                directory=directory,
            )
        # Platforms without a handle-relative primitive cannot safely close
        # the final check-to-delete race, so cleanup is deliberately skipped.
        return False

    def _remove_file(self, path: Path, *, expected: os.stat_result | None = None) -> bool:
        if expected is None:
            return False
        return self._remove_entry(path, expected, directory=False)

    def _remove_empty_directory(self, path: Path, expected: os.stat_result) -> bool:
        try:
            current = path.lstat()
            if not self._cleanup_entry_matches(expected, current, directory=True):
                return False
            if next(path.iterdir(), None) is not None:
                return False
        except (FileNotFoundError, OSError):
            return False
        return self._remove_entry(path, expected, directory=True)

    def _remove_tree_children(
        self,
        path: Path,
        expected: os.stat_result,
        children: tuple[tuple[Path, os.stat_result], ...],
    ) -> bool:
        for child, child_info in children:
            try:
                current = path.lstat()
            except OSError:
                return False
            if not self._cleanup_entry_matches(expected, current, directory=True):
                return False
            if _is_reparse_point(child_info):
                return False
            if stat.S_ISDIR(child_info.st_mode):
                if not self._remove_tree(child, expected=child_info):
                    return False
            elif stat.S_ISREG(child_info.st_mode):
                if not self._remove_file(child, expected=child_info):
                    return False
            else:
                return False
        return True

    def _remove_tree(self, path: Path, *, expected: os.stat_result | None = None) -> bool:
        if expected is None:
            return False
        try:
            path.relative_to(self._root)
            info = path.lstat()
            if not self._cleanup_entry_matches(expected, info, directory=True):
                return False
            children = tuple((child, child.lstat()) for child in path.iterdir())
        except (FileNotFoundError, OSError, ValueError):
            return False
        if not self._remove_tree_children(path, expected, children):
            return False
        return self._remove_empty_directory(path, expected)

    def _remove_owned_tree(self, path: Path, expected: os.stat_result | None) -> None:
        if expected is None:
            return
        try:
            current = path.lstat()
        except (FileNotFoundError, OSError):
            return
        if not _same_file(expected, current):
            return
        self._remove_tree(path, expected=expected)

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

    def _verify_directory(self, directory: Path, artifact_id: str) -> _StoredArtifact:
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
        return _StoredArtifact(
            workspace_id=self._workspace_id,
            export_run_id=manifest.export_run_id,
            artifact_id=manifest.artifact_id,
            filename=filename,
            payload=payload,
            manifest=manifest,
            path=payload_path,
        )

    def _read_existing(self, artifact_id: str) -> _StoredArtifact | None:
        directory = self._safe_artifact_path(artifact_id)
        if self._inspect(directory, directory=True, allow_missing=True) is None:
            return None
        return self._verify_directory(directory, artifact_id)

    def _lock_for(self, artifact_id: str) -> threading.RLock:
        key = f"{self._root}\x00{self._workspace_id}\x00{artifact_id}"
        with _LOCAL_LOCKS_GUARD:
            return _LOCAL_LOCKS.setdefault(key, threading.RLock())

    def _reservation_deadline(self) -> float:
        try:
            return self._monotonic() + self._reservation_timeout_seconds
        except (ArithmeticError, RuntimeError, TypeError, ValueError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact reservation failed") from exc

    def _wait_for_reservation(
        self,
        lock_path: Path,
        artifact_id: str,
        run_id: str,
        filename: str,
        payload: bytes,
        manifest: ExportArtifactManifest,
        deadline: float,
    ) -> _StoredArtifact | None:
        self._inspect(lock_path, directory=True, allow_missing=True)
        existing = self._read_existing(artifact_id)
        if existing is not None:
            if not self._matches_request(existing, run_id, filename, payload, manifest):
                _raise("FMEA_ARTIFACT_CONFLICT", "artifact identity already has different content")
            committed = self._reconcile_committed(run_id, filename, payload, manifest)
            if committed is not None:
                return committed
            self._read_latest_pointer(run_id)
        try:
            remaining = deadline - self._monotonic()
        except (ArithmeticError, RuntimeError, TypeError, ValueError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact reservation failed") from exc
        if remaining <= 0:
            raise ArtifactStoreError(
                "FMEA_ARTIFACT_BUSY",
                "artifact publication is busy",
                retryable=True,
            ) from None
        try:
            self._reservation_wait(min(self._reservation_poll_seconds, remaining))
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact reservation wait failed") from exc
        return None

    def _reserve(
        self,
        artifact_id: str,
        run_id: str,
        filename: str,
        payload: bytes,
        manifest: ExportArtifactManifest,
    ) -> _Reservation | _StoredArtifact:
        lock_path = self._locks_root / artifact_id
        deadline = self._reservation_deadline()
        while True:
            try:
                lock_path.mkdir()
                break
            except FileExistsError:
                # Validate every extant component but never remove a lock whose
                # owner token is not ours.  A crashed owner therefore fails
                # closed as a bounded, retryable busy result.
                existing = self._wait_for_reservation(
                    lock_path,
                    artifact_id,
                    run_id,
                    filename,
                    payload,
                    manifest,
                    deadline,
                )
                if existing is not None:
                    return existing
            except OSError as exc:
                raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact reservation failed") from exc
        directory_info: os.stat_result | None = None
        owner_info: os.stat_result | None = None
        token = secrets.token_hex(32)
        owner_path = lock_path / _OWNER_FILENAME
        try:
            self._inspect(lock_path, directory=True, allow_missing=False)
            directory_info = lock_path.lstat()
            self._write_file(owner_path, _canonical_json({"token": token}))
            owner_info = owner_path.lstat()
            self._sync_directory(lock_path)
        except ArtifactStoreError:
            self._remove_owned_tree(lock_path, directory_info)
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._remove_owned_tree(lock_path, directory_info)
            raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact reservation failed") from exc
        return _Reservation(lock_path, owner_path, token, directory_info, owner_info)

    def _release_reservation(self, reservation: _Reservation) -> None:
        try:
            directory_info = reservation.path.lstat()
            owner_info = reservation.owner_path.lstat()
            if not _same_file(reservation.directory_info, directory_info) or not _same_file(
                reservation.owner_info, owner_info
            ):
                return
            raw_owner = self._read_file(reservation.owner_path, max_bytes=_MAX_POINTER_BYTES)
            if raw_owner != _canonical_json({"token": reservation.token}):
                return
            self._remove_file(reservation.owner_path, expected=reservation.owner_info)
            try:
                reservation.owner_path.lstat()
            except FileNotFoundError:
                pass
            else:
                return
            self._remove_empty_directory(reservation.path, reservation.directory_info)
        except (ArtifactStoreError, FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
            return

    @staticmethod
    def _matches_request(
        stored: _StoredArtifact,
        run_id: str,
        filename: str,
        payload: bytes,
        manifest: ExportArtifactManifest,
    ) -> bool:
        return (
            stored.export_run_id == run_id
            and stored.filename == filename
            and stored.payload == payload
            and stored.manifest == manifest
        )

    def _reconcile_committed(
        self,
        run_id: str,
        filename: str,
        payload: bytes,
        manifest: ExportArtifactManifest,
    ) -> _StoredArtifact | None:
        """Return success only when both immutable bytes and latest are exact."""

        try:
            final = self._read_existing(manifest.artifact_id)
            latest = self._read_latest_pointer(run_id)
        except ArtifactStoreError:
            return None
        if final is None or latest is None:
            return None
        if not self._matches_request(final, run_id, filename, payload, manifest):
            return None
        if not self._matches_request(latest, run_id, filename, payload, manifest):
            return None
        if final.path != latest.path:
            return None
        return final

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

    def _read_latest_pointer(self, run_id: str) -> _StoredArtifact | None:
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

    def _publish_stored(  # noqa: C901
        self,
        run_id: str,
        filename: str,
        payload: bytes,
        manifest: ExportArtifactManifest,
    ) -> _StoredArtifact:
        """Validate and atomically publish one immutable artifact."""

        normalized = self._validate_manifest_and_payload(run_id, filename, payload, manifest)
        artifact_id = normalized.artifact_id
        final_directory = self._safe_artifact_path(artifact_id)
        existing = self._read_existing(artifact_id)
        if existing is not None:
            if not self._matches_request(existing, run_id, filename, payload, normalized):
                _raise("FMEA_ARTIFACT_CONFLICT", "artifact identity already has different content")
            committed = self._reconcile_committed(run_id, filename, payload, normalized)
            if committed is not None:
                return committed
            self._read_latest_pointer(run_id)

        # The process lock keeps same-instance/thread callers out of the
        # reservation race; the mkdir reservation covers separate processes.
        local_lock = self._lock_for(artifact_id)
        with local_lock:
            existing = self._read_existing(artifact_id)
            if existing is not None:
                if not self._matches_request(existing, run_id, filename, payload, normalized):
                    _raise("FMEA_ARTIFACT_CONFLICT", "artifact identity already has different content")
                committed = self._reconcile_committed(run_id, filename, payload, normalized)
                if committed is not None:
                    return committed
                self._read_latest_pointer(run_id)
            reservation_or_existing = self._reserve(artifact_id, run_id, filename, payload, normalized)
            if isinstance(reservation_or_existing, _StoredArtifact):
                return reservation_or_existing
            reservation = reservation_or_existing
            temporary: Path | None = None
            temporary_info: os.stat_result | None = None
            moved = False
            moved_info: os.stat_result | None = None
            pointer_replaced = False
            try:
                existing = self._read_existing(artifact_id)
                if existing is not None:
                    if not self._matches_request(existing, run_id, filename, payload, normalized):
                        _raise("FMEA_ARTIFACT_CONFLICT", "artifact identity already has different content")
                    self._read_latest_pointer(run_id)
                    self._fault("before_latest")
                    pointer_replaced = self._write_latest(run_id, artifact_id)
                    self._fault("after_latest")
                    return existing
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
                if pointer_replaced:
                    reconciled = self._reconcile_committed(run_id, filename, payload, normalized)
                    if reconciled is not None:
                        return reconciled
                raise
            except ArtifactStoreError:
                if pointer_replaced:
                    reconciled = self._reconcile_committed(run_id, filename, payload, normalized)
                    if reconciled is not None:
                        return reconciled
                raise
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                if pointer_replaced:
                    reconciled = self._reconcile_committed(run_id, filename, payload, normalized)
                    if reconciled is not None:
                        return reconciled
                raise ArtifactStoreError("FMEA_ARTIFACT_STORAGE_FAILED", "artifact publication failed") from exc
            finally:
                if temporary is not None:
                    self._remove_owned_tree(temporary, temporary_info)
                if moved and not pointer_replaced:
                    self._remove_owned_tree(final_directory, moved_info)
                self._release_reservation(reservation)

    def publish(
        self,
        run_id: str,
        filename: str,
        payload: bytes,
        manifest: ExportArtifactManifest,
    ) -> VerifiedExportArtifact:
        """Publish and expose only the path-free application artifact value."""

        return self._public_artifact(self._publish_stored(run_id, filename, payload, manifest))

    def get(self, artifact_id: str, workspace_id: str) -> VerifiedExportArtifact:
        """Return an independently reverified artifact for this workspace."""

        if workspace_id != self._workspace_id:
            _raise("FMEA_ARTIFACT_WORKSPACE_MISMATCH", "artifact belongs to another workspace")
        _safe_segment(artifact_id, "artifact_id")
        stored = self._read_existing(artifact_id)
        if stored is None:
            _raise("FMEA_ARTIFACT_NOT_FOUND", "artifact was not found")
        return self._public_artifact(stored)

    def latest(self, run_id: str) -> VerifiedExportArtifact | None:
        """Return the verified artifact selected by the run's atomic pointer."""

        _safe_segment(run_id, "run_id")
        stored = self._read_latest_pointer(run_id)
        return None if stored is None else self._public_artifact(stored)


__all__ = [
    "MAX_ARTIFACT_BYTES",
    "ArtifactStoreError",
    "WorkspaceArtifactStore",
]
