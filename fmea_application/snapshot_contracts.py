"""Immutable, bounded normalized snapshot contracts for FMEA exports."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Literal, NoReturn

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.governance import (
    FmeaRevision,
    canonical_hash,
    canonical_json_bytes,
)

_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")
_FORBIDDEN_KEY_PARTS = frozenset({
    "access_token",
    "api_key",
    "authorization",
    "credential",
    "password",
    "private_key",
    "private_path",
    "prompt",
    "provider_output",
    "raw_output",
    "secret",
    "source_url",
    "url",
})
_MAX_DEPTH = 8
_MAX_ITEMS = 500
_MAX_STRING_LENGTH = 65_536
_MAX_CANONICAL_ARRAY_ITEMS = 10_000


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    return value.strip()


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    if _HASH.fullmatch(normalized) is None:
        raise FmeaDomainError(f"{field_name} must be a lowercase SHA-256 hash")  # noqa: TRY003
    return normalized


def _timestamp(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FmeaDomainError(f"{field_name} must be an ISO-8601 UTC timestamp") from exc  # noqa: TRY003
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise FmeaDomainError(f"{field_name} must be an ISO-8601 UTC timestamp")  # noqa: TRY003
    return normalized


def _reject_unsafe_key(key: str) -> None:
    normalized = key.casefold().replace("-", "_")
    if normalized in _FORBIDDEN_KEY_PARTS or any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
        raise FmeaDomainError("snapshot contains non-export-safe field")  # noqa: TRY003


def _freeze_export_value(value: object, *, depth: int = 0) -> object:  # noqa: C901
    if depth > _MAX_DEPTH:
        raise FmeaDomainError("snapshot exceeds maximum JSON depth")  # noqa: TRY003
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise FmeaDomainError("snapshot numbers must be finite")  # noqa: TRY003
        return value
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            raise FmeaDomainError("snapshot string exceeds maximum length")  # noqa: TRY003
        if _URI_SCHEME.match(value) or _ABSOLUTE_PATH.match(value):
            raise FmeaDomainError("snapshot contains non-export-safe value")  # noqa: TRY003
        return value
    if isinstance(value, Mapping):
        if len(value) > _MAX_ITEMS:
            raise FmeaDomainError("snapshot mapping exceeds maximum size")  # noqa: TRY003
        items: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise FmeaDomainError("snapshot object keys must be non-empty strings")  # noqa: TRY003
            normalized_key = key.strip()
            _reject_unsafe_key(normalized_key)
            if normalized_key in items:
                raise FmeaDomainError("snapshot contains duplicate object keys")  # noqa: TRY003
            items[normalized_key] = _freeze_export_value(item, depth=depth + 1)
        return MappingProxyType(dict(sorted(items.items())))
    if isinstance(value, tuple | list):
        if len(value) > _MAX_ITEMS:
            raise FmeaDomainError("snapshot array exceeds maximum size")  # noqa: TRY003
        return tuple(_freeze_export_value(item, depth=depth + 1) for item in value)
    raise FmeaDomainError("snapshot contains a non-JSON value")  # noqa: TRY003


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FmeaDomainError(f"{field_name} must be a mapping")  # noqa: TRY003
    frozen = _freeze_export_value(value)
    if not isinstance(frozen, Mapping):  # pragma: no cover - _freeze_export_value preserves mappings.
        raise FmeaDomainError(f"{field_name} must be a mapping")  # noqa: TRY003
    return frozen


def _mapping_tuple(
    value: object,
    field_name: str,
    *,
    identity_field: str | None = None,
) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc  # noqa: TRY003
    normalized = tuple(_mapping(item, field_name) for item in items)
    if identity_field is None:
        return normalized
    identities: list[str] = []
    for item in normalized:
        identity = item.get(identity_field)
        if not isinstance(identity, str) or not identity.strip():
            raise FmeaDomainError(f"{field_name} items must contain {identity_field}")  # noqa: TRY003
        identities.append(identity.strip())
    if len(identities) != len(set(identities)):
        raise FmeaDomainError(f"{field_name} must not contain duplicate identities")  # noqa: TRY003
    return tuple(item for _, item in sorted(zip(identities, normalized, strict=True), key=lambda pair: pair[0]))


@dataclass(frozen=True, slots=True)
class NormalizedFmeaSnapshot:
    schema_version: Literal["graphrag.fmea.normalized-snapshot.v1"]
    snapshot_id: str
    workspace_id: str
    analysis_id: str
    revision_id: str
    revision_hash: str
    publication_id: str
    manifest_id: str
    rows: tuple[Mapping[str, object], ...]
    risk_records: tuple[Mapping[str, object], ...]
    propagation: Mapping[str, object] | None
    evidence_summary: tuple[Mapping[str, object], ...]
    decision_summary: tuple[Mapping[str, object], ...]
    version_manifest: Mapping[str, object]
    unresolved_items: tuple[Mapping[str, object], ...]
    audit_summary: Mapping[str, object]
    row_count: int
    snapshot_hash: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != "graphrag.fmea.normalized-snapshot.v1":
            raise FmeaDomainError("snapshot schema_version is invalid")  # noqa: TRY003
        for field_name in (
            "snapshot_id",
            "workspace_id",
            "analysis_id",
            "revision_id",
            "publication_id",
            "manifest_id",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        object.__setattr__(self, "rows", _mapping_tuple(self.rows, "rows", identity_field="row_id"))
        object.__setattr__(
            self, "risk_records", _mapping_tuple(self.risk_records, "risk_records", identity_field="assessment_id")
        )
        object.__setattr__(
            self, "propagation", None if self.propagation is None else _mapping(self.propagation, "propagation")
        )
        object.__setattr__(
            self,
            "evidence_summary",
            _mapping_tuple(self.evidence_summary, "evidence_summary", identity_field="pack_id"),
        )
        object.__setattr__(
            self,
            "decision_summary",
            _mapping_tuple(self.decision_summary, "decision_summary", identity_field="decision_id"),
        )
        object.__setattr__(self, "version_manifest", _mapping(self.version_manifest, "version_manifest"))
        object.__setattr__(self, "unresolved_items", _mapping_tuple(self.unresolved_items, "unresolved_items"))
        object.__setattr__(self, "audit_summary", _mapping(self.audit_summary, "audit_summary"))
        if isinstance(self.row_count, bool) or not isinstance(self.row_count, int) or self.row_count < 0:
            raise FmeaDomainError("row_count must be a non-negative integer")  # noqa: TRY003
        if self.row_count != len(self.rows):
            raise FmeaDomainError("row_count does not match rows")  # noqa: TRY003
        object.__setattr__(self, "snapshot_hash", _hash(self.snapshot_hash, "snapshot_hash"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        if self.snapshot_hash.removeprefix("sha256:") != snapshot_content_hash(self):
            raise FmeaDomainError("snapshot hash does not match snapshot content")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class NormalizedSnapshotPage:
    rows: tuple[Mapping[str, object], ...]
    next_offset: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", _mapping_tuple(self.rows, "rows"))
        if self.next_offset is not None and (
            isinstance(self.next_offset, bool) or not isinstance(self.next_offset, int) or self.next_offset < 0
        ):
            raise FmeaDomainError("next_offset must be a non-negative integer or None")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class NormalizedSnapshotInput:
    revision: FmeaRevision
    publication_id: str
    manifest_id: str
    publication_revision_id: str
    publication_revision_hash: str
    publication_workspace_id: str
    publication_analysis_id: str
    rows: tuple[Mapping[str, object], ...]
    risk_records: tuple[Mapping[str, object], ...]
    propagation: Mapping[str, object] | None
    evidence_summary: tuple[Mapping[str, object], ...]
    decision_summary: tuple[Mapping[str, object], ...]
    version_manifest: Mapping[str, object]
    audit_summary: Mapping[str, object]
    created_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.revision, FmeaRevision):
            raise FmeaDomainError("revision must be an FmeaRevision")  # noqa: TRY003
        object.__setattr__(self, "publication_id", _text(self.publication_id, "publication_id"))
        object.__setattr__(self, "manifest_id", _text(self.manifest_id, "manifest_id"))
        object.__setattr__(
            self, "publication_revision_id", _text(self.publication_revision_id, "publication_revision_id")
        )
        object.__setattr__(
            self, "publication_revision_hash", _hash(self.publication_revision_hash, "publication_revision_hash")
        )
        object.__setattr__(
            self, "publication_workspace_id", _text(self.publication_workspace_id, "publication_workspace_id")
        )
        object.__setattr__(
            self, "publication_analysis_id", _text(self.publication_analysis_id, "publication_analysis_id")
        )
        object.__setattr__(self, "rows", _mapping_tuple(self.rows, "rows", identity_field="row_id"))
        object.__setattr__(
            self, "risk_records", _mapping_tuple(self.risk_records, "risk_records", identity_field="assessment_id")
        )
        object.__setattr__(
            self, "propagation", None if self.propagation is None else _mapping(self.propagation, "propagation")
        )
        object.__setattr__(
            self,
            "evidence_summary",
            _mapping_tuple(self.evidence_summary, "evidence_summary", identity_field="pack_id"),
        )
        object.__setattr__(
            self,
            "decision_summary",
            _mapping_tuple(self.decision_summary, "decision_summary", identity_field="decision_id"),
        )
        object.__setattr__(self, "version_manifest", _mapping(self.version_manifest, "version_manifest"))
        object.__setattr__(self, "audit_summary", _mapping(self.audit_summary, "audit_summary"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


def validate_snapshot_publication_binding(source: NormalizedSnapshotInput) -> None:
    if (
        source.publication_revision_id != source.revision.revision_id
        or source.publication_revision_hash != source.revision.revision_hash
    ):
        raise FmeaDomainError("snapshot publication binding does not match revision")  # noqa: TRY003
    if (
        source.publication_workspace_id != source.revision.workspace_id
        or source.publication_analysis_id != source.revision.analysis_id
    ):
        raise FmeaDomainError("snapshot publication workspace/analysis binding is invalid")  # noqa: TRY003


def canonical_normalized_snapshot_body(source: NormalizedSnapshotInput) -> Mapping[str, object]:
    if not isinstance(source, NormalizedSnapshotInput):
        raise FmeaDomainError("source must be a NormalizedSnapshotInput")  # noqa: TRY003
    validate_snapshot_publication_binding(source)
    snapshot_id = f"snapshot:{source.revision.revision_id}:{source.publication_id}"
    unresolved_items = tuple(
        {
            "acknowledgement_decision_id": item.acknowledgement_decision_id,
            "code": item.code,
            "evidence_ids": item.evidence_ids,
            "severity": item.severity,
            "source_id": item.source_id,
            "source_type": item.source_type,
        }
        for item in source.revision.unresolved_items
    )
    return {
        "schema_version": "graphrag.fmea.normalized-snapshot.v1",
        "snapshot_id": snapshot_id,
        "workspace_id": source.revision.workspace_id,
        "analysis_id": source.revision.analysis_id,
        "revision_id": source.revision.revision_id,
        "revision_hash": source.revision.revision_hash,
        "publication_id": source.publication_id,
        "manifest_id": source.manifest_id,
        "rows": source.rows,
        "risk_records": source.risk_records,
        "propagation": source.propagation,
        "evidence_summary": source.evidence_summary,
        "decision_summary": source.decision_summary,
        "version_manifest": source.version_manifest,
        "unresolved_items": unresolved_items,
        "audit_summary": source.audit_summary,
        "row_count": len(source.rows),
        "created_at": source.created_at,
    }


def _canonical_snapshot_body(snapshot: NormalizedFmeaSnapshot) -> Mapping[str, object]:
    return {
        "schema_version": snapshot.schema_version,
        "snapshot_id": snapshot.snapshot_id,
        "workspace_id": snapshot.workspace_id,
        "analysis_id": snapshot.analysis_id,
        "revision_id": snapshot.revision_id,
        "revision_hash": snapshot.revision_hash,
        "publication_id": snapshot.publication_id,
        "manifest_id": snapshot.manifest_id,
        "rows": snapshot.rows,
        "risk_records": snapshot.risk_records,
        "propagation": snapshot.propagation,
        "evidence_summary": snapshot.evidence_summary,
        "decision_summary": snapshot.decision_summary,
        "version_manifest": snapshot.version_manifest,
        "unresolved_items": snapshot.unresolved_items,
        "audit_summary": snapshot.audit_summary,
        "row_count": snapshot.row_count,
        "created_at": snapshot.created_at,
    }


def _plain_snapshot_value(value: object, *, depth: int = 0) -> object:
    """Copy only exact plain JSON values without invoking custom protocols."""

    if depth > _MAX_DEPTH + 1:
        raise ValueError("snapshot value depth is invalid")  # noqa: TRY003
    value_type = type(value)
    if value is None or value_type in {bool, int, float, str}:
        return value
    if value_type in {tuple, list}:
        if len(value) > _MAX_CANONICAL_ARRAY_ITEMS:  # type: ignore[arg-type]
            raise ValueError("snapshot sequence is too large")  # noqa: TRY003
        copied = tuple(_plain_snapshot_value(item, depth=depth + 1) for item in value)  # type: ignore[union-attr]
        return copied
    if value_type in {dict, MappingProxyType}:
        if len(value) > _MAX_ITEMS:  # type: ignore[arg-type]
            raise ValueError("snapshot mapping is too large")  # noqa: TRY003
        copied_mapping: dict[str, object] = {}
        for key, item in value.items():  # type: ignore[union-attr]
            if type(key) is not str:
                raise ValueError("snapshot mapping key is invalid")  # noqa: TRY003
            copied_mapping[key] = _plain_snapshot_value(item, depth=depth + 1)
        return copied_mapping
    raise ValueError("snapshot value is not plain JSON")  # noqa: TRY003


def _plain_snapshot_string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("snapshot string is invalid")  # noqa: TRY003
    return value


def _snapshot_revalidation_invalid() -> NoReturn:
    raise ValueError


def revalidate_normalized_snapshot(value: object) -> NormalizedFmeaSnapshot:
    """Rebuild an exact immutable snapshot and replay every constructor invariant."""

    try:
        if type(value) is not NormalizedFmeaSnapshot:
            _snapshot_revalidation_invalid()
        values = {
            "schema_version": _plain_snapshot_string(value.schema_version),
            "snapshot_id": _plain_snapshot_string(value.snapshot_id),
            "workspace_id": _plain_snapshot_string(value.workspace_id),
            "analysis_id": _plain_snapshot_string(value.analysis_id),
            "revision_id": _plain_snapshot_string(value.revision_id),
            "revision_hash": _plain_snapshot_string(value.revision_hash),
            "publication_id": _plain_snapshot_string(value.publication_id),
            "manifest_id": _plain_snapshot_string(value.manifest_id),
            "rows": _plain_snapshot_value(value.rows),
            "risk_records": _plain_snapshot_value(value.risk_records),
            "propagation": None if value.propagation is None else _plain_snapshot_value(value.propagation),
            "evidence_summary": _plain_snapshot_value(value.evidence_summary),
            "decision_summary": _plain_snapshot_value(value.decision_summary),
            "version_manifest": _plain_snapshot_value(value.version_manifest),
            "unresolved_items": _plain_snapshot_value(value.unresolved_items),
            "audit_summary": _plain_snapshot_value(value.audit_summary),
            "row_count": value.row_count,
            "snapshot_hash": _plain_snapshot_string(value.snapshot_hash),
            "created_at": _plain_snapshot_string(value.created_at),
        }
        if type(values["row_count"]) is not int:
            _snapshot_revalidation_invalid()
        return NormalizedFmeaSnapshot(**values)  # type: ignore[arg-type]
    except Exception:
        raise FmeaDomainError("snapshot revalidation failed") from None  # noqa: TRY003


def snapshot_content_hash(snapshot: NormalizedFmeaSnapshot) -> str:
    if not isinstance(snapshot, NormalizedFmeaSnapshot):
        raise FmeaDomainError("snapshot must be a NormalizedFmeaSnapshot")  # noqa: TRY003
    return canonical_hash(_canonical_snapshot_body(snapshot), max_array_items=_MAX_CANONICAL_ARRAY_ITEMS)


def build_normalized_snapshot(source: NormalizedSnapshotInput) -> NormalizedFmeaSnapshot:
    validate_snapshot_publication_binding(source)
    body = canonical_normalized_snapshot_body(source)
    snapshot_hash = canonical_hash(body, max_array_items=_MAX_CANONICAL_ARRAY_ITEMS)
    return NormalizedFmeaSnapshot(**body, snapshot_hash=snapshot_hash)  # type: ignore[arg-type]


def iter_normalized_snapshot_pages(
    snapshot: NormalizedFmeaSnapshot, *, page_size: int
) -> Iterator[NormalizedSnapshotPage]:
    if not isinstance(snapshot, NormalizedFmeaSnapshot):
        raise FmeaDomainError("snapshot must be a NormalizedFmeaSnapshot")  # noqa: TRY003
    if isinstance(page_size, bool) or not 1 <= page_size <= 500:
        raise ValueError("page_size must be between 1 and 500")  # noqa: TRY003

    for offset in range(0, snapshot.row_count, page_size):
        end = offset + page_size
        yield NormalizedSnapshotPage(
            rows=snapshot.rows[offset:end],
            next_offset=end if end < snapshot.row_count else None,
        )


__all__ = [
    "NormalizedFmeaSnapshot",
    "NormalizedSnapshotInput",
    "NormalizedSnapshotPage",
    "build_normalized_snapshot",
    "canonical_json_bytes",
    "canonical_normalized_snapshot_body",
    "iter_normalized_snapshot_pages",
    "revalidate_normalized_snapshot",
    "snapshot_content_hash",
    "validate_snapshot_publication_binding",
]
