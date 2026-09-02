"""Immutable, bounded application contracts for export runs and artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TypeVar

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.filename_policy import validate_filename
from core_domain.fmea.states import RunStatus

_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_MAX_TEXT_LENGTH = 4096
_MAX_ID_LENGTH = 256
_MAX_FILENAME_LENGTH = 255
_MAX_ARTIFACT_BYTES = 1_073_741_824
_E = TypeVar("_E", bound=Enum)


class ExportFormat(str, Enum):
    JSON = "json"
    XLSX = "xlsx"
    DOCX = "docx"


_MEDIA_TYPES = {
    ExportFormat.JSON: "application/json",
    ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_LIFECYCLE_REQUIREMENTS: dict[RunStatus, tuple[str | None, ...]] = {
    RunStatus.QUEUED: (None, None, None, None),
    RunStatus.RUNNING: ("required", None, None, None),
    RunStatus.SUCCEEDED: ("required", "required", "required", None),
    RunStatus.CANCELLING: ("required", None, None, None),
    RunStatus.CANCELLED: ("required", "required", None, None),
    RunStatus.FAILED: ("required", "required", None, "required"),
}


def _text(value: object, field_name: str, *, limit: int = _MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    normalized = value.strip()
    if len(normalized) > limit:
        raise FmeaDomainError(f"{field_name} exceeds maximum length {limit}")  # noqa: TRY003
    return normalized


def _id(value: object, field_name: str) -> str:
    return _text(value, field_name, limit=_MAX_ID_LENGTH)


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=71)
    if _SHA256.fullmatch(normalized) is None:
        raise FmeaDomainError(f"{field_name} must be lowercase SHA-256")  # noqa: TRY003
    return normalized


def _timestamp(value: object, field_name: str) -> str:
    normalized = _text(value, field_name, limit=64)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FmeaDomainError(f"{field_name} must be an ISO-8601 UTC timestamp") from exc  # noqa: TRY003
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise FmeaDomainError(f"{field_name} must be an ISO-8601 UTC timestamp")  # noqa: TRY003
    return normalized


def _enum(value: object, expected: type[_E], field_name: str) -> _E:
    if isinstance(value, expected):
        return value
    try:
        return expected(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(str(member.value) for member in expected)
        raise FmeaDomainError(f"{field_name} must be one of: {allowed}") from exc  # noqa: TRY003


def _filename(value: object, field_name: str, *, expected_extension: str | None = None) -> str:
    return validate_filename(value, field_name, expected_extension=expected_extension)


def _format(value: object, field_name: str) -> ExportFormat:
    result = _enum(value, ExportFormat, field_name)
    return result


def _publication_binding(
    publication_id: object,
    draft_preview: object,
    *,
    field_name: str = "publication_id",
) -> str | None:
    if not isinstance(draft_preview, bool):
        raise FmeaDomainError("draft_preview must be a boolean")  # noqa: TRY003
    normalized = None if publication_id is None else _id(publication_id, field_name)
    if draft_preview and normalized is not None:
        raise FmeaDomainError("draft preview must not contain a publication identity")  # noqa: TRY003
    if not draft_preview and normalized is None:
        raise FmeaDomainError("published export requires a publication identity")  # noqa: TRY003
    return normalized


def _validate_lifecycle(
    status: RunStatus,
    *,
    created_at: str,
    started_at: str | None,
    finished_at: str | None,
    artifact_id: str | None,
    error: str | None,
) -> None:
    try:
        expected = _LIFECYCLE_REQUIREMENTS[status]
    except KeyError as exc:
        raise FmeaDomainError("export status is not a supported lifecycle status") from exc  # noqa: TRY003

    fields = (started_at, finished_at, artifact_id, error)
    labels = ("started_at", "finished_at", "artifact_id", "error")
    for label, value, requirement in zip(labels, fields, expected, strict=True):
        if requirement == "required" and value is None:
            raise FmeaDomainError(f"export lifecycle requires {label} for {status.value}")  # noqa: TRY003
        if requirement is None and value is not None:
            raise FmeaDomainError(f"export lifecycle forbids {label} for {status.value}")  # noqa: TRY003

    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if started_at is not None:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if created > started:
            raise FmeaDomainError("export lifecycle created_at must not follow started_at")  # noqa: TRY003
        if finished_at is not None:
            finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            if finished < started:
                raise FmeaDomainError("export lifecycle finished_at must not precede started_at")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class ExportRun:
    export_run_id: str
    workspace_id: str
    revision_id: str
    snapshot_hash: str
    publication_id: str | None
    format: ExportFormat | str
    draft_preview: bool
    status: RunStatus | str
    created_at: str
    snapshot_id: str | None = None
    filename: str | None = None
    artifact_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("export_run_id", "workspace_id", "revision_id"):
            object.__setattr__(self, field_name, _id(getattr(self, field_name), field_name))
        object.__setattr__(self, "snapshot_hash", _hash(self.snapshot_hash, "snapshot_hash"))
        object.__setattr__(self, "publication_id", _publication_binding(self.publication_id, self.draft_preview))
        object.__setattr__(self, "format", _format(self.format, "format"))
        object.__setattr__(self, "status", _enum(self.status, RunStatus, "status"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        for field_name in ("snapshot_id", "artifact_id"):
            value = getattr(self, field_name)
            object.__setattr__(self, field_name, None if value is None else _id(value, field_name))
        if self.filename is not None:
            object.__setattr__(
                self, "filename", _filename(self.filename, "filename", expected_extension=self.format.value)
            )
        for field_name in ("started_at", "finished_at"):
            value = getattr(self, field_name)
            object.__setattr__(self, field_name, None if value is None else _timestamp(value, field_name))
        if self.error is not None:
            object.__setattr__(self, "error", _text(self.error, "error"))
        _validate_lifecycle(
            self.status,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            artifact_id=self.artifact_id,
            error=self.error,
        )

    @property
    def run_id(self) -> str:
        """Compatibility spelling for ports that call an export run a run."""

        return self.export_run_id


@dataclass(frozen=True, slots=True)
class ExportArtifactManifest:
    artifact_id: str
    export_run_id: str
    publication_id: str | None
    revision_id: str
    snapshot_hash: str
    format: ExportFormat | str
    media_type: str
    byte_length: int
    sha256: str
    draft_preview: bool
    created_at: str
    snapshot_id: str | None = None
    filename: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("artifact_id", "export_run_id", "revision_id"):
            object.__setattr__(self, field_name, _id(getattr(self, field_name), field_name))
        object.__setattr__(self, "snapshot_hash", _hash(self.snapshot_hash, "snapshot_hash"))
        object.__setattr__(self, "publication_id", _publication_binding(self.publication_id, self.draft_preview))
        export_format = _format(self.format, "format")
        object.__setattr__(self, "format", export_format)
        media_type = _text(self.media_type, "media_type", limit=256)
        if media_type != _MEDIA_TYPES[export_format]:
            raise FmeaDomainError("media_type does not match format")  # noqa: TRY003
        object.__setattr__(self, "media_type", media_type)
        if (
            isinstance(self.byte_length, bool)
            or not isinstance(self.byte_length, int)
            or not 0 <= self.byte_length <= _MAX_ARTIFACT_BYTES
        ):
            raise FmeaDomainError(f"byte_length must be between 0 and {_MAX_ARTIFACT_BYTES}")  # noqa: TRY003
        object.__setattr__(self, "sha256", _hash(self.sha256, "sha256"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        if self.snapshot_id is not None:
            object.__setattr__(self, "snapshot_id", _id(self.snapshot_id, "snapshot_id"))
        if self.filename is not None:
            object.__setattr__(
                self, "filename", _filename(self.filename, "filename", expected_extension=self.format.value)
            )


def validate_export_binding(run: ExportRun, manifest: ExportArtifactManifest) -> None:
    """Validate that a completed run and artifact manifest describe one export."""

    if not isinstance(run, ExportRun) or not isinstance(manifest, ExportArtifactManifest):
        raise FmeaDomainError("export binding requires ExportRun and ExportArtifactManifest")  # noqa: TRY003
    if run.status is not RunStatus.SUCCEEDED:
        raise FmeaDomainError("export binding requires a completed export run")  # noqa: TRY003
    shared_fields = (
        ("export_run_id", run.export_run_id, manifest.export_run_id),
        ("revision_id", run.revision_id, manifest.revision_id),
        ("snapshot_id", run.snapshot_id, manifest.snapshot_id),
        ("snapshot_hash", run.snapshot_hash, manifest.snapshot_hash),
        ("publication_id", run.publication_id, manifest.publication_id),
        ("draft_preview", run.draft_preview, manifest.draft_preview),
        ("format", run.format, manifest.format),
        ("filename", run.filename, manifest.filename),
        ("artifact_id", run.artifact_id, manifest.artifact_id),
    )
    for field_name, run_value, manifest_value in shared_fields:
        if run_value != manifest_value:
            raise FmeaDomainError(f"export binding mismatch for {field_name}")  # noqa: TRY003


def bind_export_artifact(run: ExportRun, manifest: ExportArtifactManifest) -> ExportArtifactManifest:
    """Return an immutable manifest after validating its completed-run binding."""

    validate_export_binding(run, manifest)
    return manifest


__all__ = [
    "ExportArtifactManifest",
    "ExportFormat",
    "ExportRun",
    "bind_export_artifact",
    "validate_export_binding",
]
