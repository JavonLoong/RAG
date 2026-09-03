"""Canonical JSON rendering for immutable normalized FMEA snapshots."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import NoReturn, cast

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.governance import canonical_json_value
from core_domain.structured_output import StructuredOutputError, TemplateLimits, canonical_json
from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot, revalidate_normalized_snapshot

_EXPORT_SCHEMA = "graphrag.fmea.export.v1"
_PREVIEW_MARKER = "DRAFT PREVIEW — NOT PUBLISHED"
_MAX_DEPTH = 8
_MAX_COLLECTION_ITEMS = 10_000
_MAX_OBJECT_ITEMS = 500
_MAX_STRING_LENGTH = 65_536
_UNSAFE_URI_SCHEME = re.compile(r"^(?:file|ftp|http|https|s3):", re.IGNORECASE)
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


class CanonicalJsonExportError(ValueError):
    """Stable, public-safe canonical export failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _error(code: str, message: str) -> CanonicalJsonExportError:
    return CanonicalJsonExportError(code, message)


def _safe_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return not (normalized in _FORBIDDEN_KEY_PARTS or any(part in normalized for part in _FORBIDDEN_KEY_PARTS))


def _invalid_value() -> NoReturn:
    raise ValueError


def _validate_string(value: str) -> None:
    if len(value) > _MAX_STRING_LENGTH or _UNSAFE_URI_SCHEME.match(value) or _ABSOLUTE_PATH.match(value):
        _invalid_value()


def _validate_mapping(value: Mapping[object, object], *, depth: int) -> None:
    if len(value) > _MAX_OBJECT_ITEMS:
        _invalid_value()
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip() or not _safe_key(key.strip()):
            _invalid_value()
        _validate_export_value(item, depth=depth + 1)


def _validate_array(value: list[object], *, depth: int) -> None:
    if len(value) > _MAX_COLLECTION_ITEMS:
        _invalid_value()
    for item in value:
        _validate_export_value(item, depth=depth + 1)


def _validate_export_value(value: object, *, depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        _invalid_value()
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _invalid_value()
        return
    if isinstance(value, str):
        _validate_string(value)
        return
    if isinstance(value, Mapping):
        _validate_mapping(value, depth=depth)
        return
    if isinstance(value, list):
        _validate_array(value, depth=depth)
        return
    _invalid_value()


def _snapshot_projection(
    snapshot: NormalizedFmeaSnapshot,
    *,
    draft_preview: bool,
    export_format: str,
    media_type: str,
) -> Mapping[str, object]:
    """Return the versioned, flat semantic envelope consumed by all adapters."""

    return cast(
        "Mapping[str, object]",
        canonical_json_value({
            "schema_version": _EXPORT_SCHEMA,
            "snapshot_schema_version": snapshot.schema_version,
            "snapshot_id": snapshot.snapshot_id,
            "workspace_id": snapshot.workspace_id,
            "analysis_id": snapshot.analysis_id,
            "revision_id": snapshot.revision_id,
            "revision_hash": snapshot.revision_hash,
            "publication_id": None if draft_preview else snapshot.publication_id,
            "source_publication_id": snapshot.publication_id if draft_preview else None,
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
            "snapshot_hash": snapshot.snapshot_hash,
            "created_at": snapshot.created_at,
            "draft_preview": draft_preview,
            "draft_marker": _PREVIEW_MARKER if draft_preview else None,
            "format": export_format,
            "media_type": media_type,
        }),
    )


class CanonicalJsonExporter:
    """Render one normalized snapshot as deterministic canonical JSON bytes."""

    format = "json"
    media_type = "application/json"

    def __init__(self, draft_preview: bool = False) -> None:
        if type(draft_preview) is not bool:
            raise _error("FMEA_EXPORT_JSON_INVALID", "draft_preview must be a boolean")
        self._draft_preview = draft_preview

    def render(self, snapshot: NormalizedFmeaSnapshot, *, draft_preview: bool | None = None) -> bytes:
        if type(snapshot) is not NormalizedFmeaSnapshot:
            raise _error("FMEA_EXPORT_SNAPSHOT_INVALID", "snapshot must be a NormalizedFmeaSnapshot")
        if draft_preview is not None and type(draft_preview) is not bool:
            raise _error("FMEA_EXPORT_JSON_INVALID", "draft_preview must be a boolean or None")

        try:
            resolved_preview = self._draft_preview if draft_preview is None else draft_preview
            snapshot = revalidate_normalized_snapshot(snapshot)
            projection = _snapshot_projection(
                snapshot,
                draft_preview=resolved_preview,
                export_format=self.format,
                media_type=self.media_type,
            )
            _validate_export_value(projection)
            body = canonical_json(
                projection,
                limits=TemplateLimits(max_array_items=_MAX_COLLECTION_ITEMS),
            )
            return body.encode("utf-8") + b"\n"
        except CanonicalJsonExportError:
            raise
        except (FmeaDomainError, StructuredOutputError, TypeError, ValueError, OverflowError):
            raise _error("FMEA_EXPORT_JSON_INVALID", "snapshot cannot be rendered as canonical JSON") from None


__all__ = ["CanonicalJsonExportError", "CanonicalJsonExporter"]
