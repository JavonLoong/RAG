"""Snapshot-only report projection and deterministic, non-executable layouts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import TYPE_CHECKING, NoReturn

from core_domain.fmea.errors import FmeaDomainError

if TYPE_CHECKING:
    from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot


_ROW_FIELDS = frozenset({
    "row_id",
    "analysis_id",
    "evidence_pack_id",
    "item_id",
    "function_id",
    "failure_mode",
    "causes",
    "mechanisms",
    "effects",
    "symptoms",
    "controls",
    "barriers",
    "actions",
    "claim_status",
    "review_status",
    "publication_status",
    "record_version",
    "row_hash",
})
_ARRAY_FIELDS = frozenset({"causes", "mechanisms", "effects", "symptoms", "controls", "barriers", "actions"})
_FIELD_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")
_VALUE_TYPES = frozenset({
    "string",
    "integer",
    "number",
    "decimal",
    "boolean",
    "object",
    "array",
    "null",
    "json",
    "string[]",
})


def _invalid() -> NoReturn:
    raise FmeaDomainError("FMEA_PUBLICATION_BODY_UNSAFE: report layout is invalid or not template-bound")  # noqa: TRY003


def _path(key: str) -> tuple[str, str]:
    if not _FIELD_KEY.fullmatch(key) or ".." in key:
        _invalid()
    if key in _ROW_FIELDS:
        return "row", key
    if "." in key:
        return "extension_values", key
    # A declared but unavailable field is explicitly empty, never semantically remapped.
    return "unavailable", key


def validate_report_layout(layout: object, identities: object) -> None:
    """Validate saved layout structure; exact template-content binding happens at commit."""
    if not isinstance(layout, Mapping) or set(layout) != {"template_identity", "columns"}:
        _invalid()
    identity = layout["template_identity"]
    if not isinstance(identity, Mapping) or set(identity) != {"template_id", "version", "template_hash"}:
        _invalid()
    if not isinstance(identities, tuple | list) or len(identities) != 1:
        _invalid()
    expected = identities[0]
    if not isinstance(expected, tuple | list) or len(expected) != 3 or not all(isinstance(v, str) for v in expected):
        _invalid()
    if tuple(identity[k] for k in ("template_id", "version", "template_hash")) != (
        expected[0],
        expected[1],
        expected[2].removeprefix("sha256:"),
    ):
        _invalid()
    if not re.fullmatch(r"[0-9a-f]{64}", str(identity["template_hash"])):
        _invalid()
    _validate_columns(layout["columns"])


def _validate_columns(columns: object) -> None:
    if not isinstance(columns, tuple | list) or not 1 <= len(columns) <= 500:
        _invalid()
    keys: set[str] = set()
    for column in columns:
        if not isinstance(column, Mapping) or set(column) != {"field_key", "label", "value_type", "value_path"}:
            _invalid()
        key, label, value_type, path = (column[k] for k in ("field_key", "label", "value_type", "value_path"))
        if not isinstance(key, str) or key in keys or not isinstance(label, str) or not label.strip():
            _invalid()
        if not isinstance(value_type, str) or value_type not in _VALUE_TYPES:
            _invalid()
        if not isinstance(path, tuple | list) or tuple(path) != _path(key):
            _invalid()
        keys.add(key)


def compile_report_layout(canonical_json: str, identities: Sequence[tuple[str, str, str]]) -> Mapping[str, object]:
    """Derive display-only fields from exact compiled content, not source_mappings.

    Callers resolving/committing templates also run the existing bounded TemplateCompiler.
    Read paths never need this content or a registry.
    """
    if len(identities) != 1:
        raise FmeaDomainError("FMEA_PUBLICATION_BODY_INCOMPLETE: report layout requires exactly one template")  # noqa: TRY003
    if not isinstance(canonical_json, str) or len(canonical_json.encode("utf-8")) > 1_048_576:
        _invalid()
    template_id, version, expected_hash = identities[0]
    digest = sha256(canonical_json.encode("utf-8")).hexdigest()
    if digest != expected_hash.removeprefix("sha256:"):
        _invalid()
    try:
        source = json.loads(canonical_json)
        metadata = source["template"]
        if (metadata["id"], metadata["version"]) != (template_id, version):
            _invalid()
        properties = source["output_schema"]["properties"]
        columns = []
        for key, definition in sorted(properties.items()):
            # JSON Schema permits boolean property schemas and boolean array items.
            if isinstance(definition, bool):
                definition = {}
            value_type = definition.get("type", "json")
            items = definition.get("items", {})
            if value_type == "array" and isinstance(items, Mapping) and items.get("type") == "string":
                value_type = "string[]"
            if not isinstance(value_type, str) or value_type not in _VALUE_TYPES:
                value_type = "json"
            columns.append(
                MappingProxyType({
                    "field_key": key,
                    "label": definition.get("title", key),
                    "value_type": value_type,
                    "value_path": _path(key),
                })
            )
        layout = MappingProxyType({
            "template_identity": MappingProxyType({
                "template_id": template_id,
                "version": version,
                "template_hash": digest,
            }),
            "columns": tuple(columns),
        })
        validate_report_layout(layout, identities)
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError) as exc:
        raise FmeaDomainError("FMEA_PUBLICATION_BODY_UNSAFE: report layout template content is invalid") from exc  # noqa: TRY003
    return layout


@dataclass(frozen=True, slots=True)
class ReportColumn:
    field_key: str
    label: str
    value_type: str


@dataclass(frozen=True, slots=True)
class FmeaReportView:
    columns: tuple[ReportColumn, ...]
    rows: tuple[Mapping[str, object], ...]
    details: tuple[Mapping[str, object], ...]


def build_report_view(snapshot: NormalizedFmeaSnapshot) -> FmeaReportView:
    from fmea_application.snapshot_contracts import revalidate_normalized_snapshot

    snapshot = revalidate_normalized_snapshot(snapshot)
    if "body_schema_version" not in snapshot.version_manifest:
        keys = ("publication_id", "revision_id", "row_count", "snapshot_hash")
        return FmeaReportView(
            tuple(ReportColumn(key, key, "integer" if key == "row_count" else "string") for key in keys),
            (MappingProxyType({key: getattr(snapshot, key) for key in keys}),),
            (),
        )
    layout = snapshot.version_manifest.get("report_layout")
    if layout is None:
        # Task2 saved bodies remain readable; this branch never authorizes a new commit.
        keys = sorted(set(_ROW_FIELDS).intersection(key for row in snapshot.rows for key in row))
        extension_types = {
            str(value["field_key"]): str(value["value_type"])
            for row in snapshot.rows
            for value in row["extension_values"]
        }
        definitions = tuple(
            {
                "field_key": key,
                "label": key,
                "value_type": extension_types.get(
                    key, "string[]" if key in _ARRAY_FIELDS else "integer" if key == "record_version" else "string"
                ),
                "value_path": _path(key),
            }
            for key in sorted(set(keys) | set(extension_types))
        )
    else:
        validate_report_layout(layout, snapshot.version_manifest.get("template_identities"))
        definitions = layout["columns"]
    columns = tuple(ReportColumn(c["field_key"], c["label"], c["value_type"]) for c in definitions)
    rows = []
    details = []
    for row in snapshot.rows:
        extensions = {entry["field_key"]: entry["value"] for entry in row["extension_values"]}
        values = {}
        for definition in definitions:
            kind, key = definition["value_path"]
            values[definition["field_key"]] = (
                row.get(key) if kind == "row" else extensions.get(key) if kind == "extension_values" else None
            )
        rows.append(MappingProxyType(values))
        # Preserve all body/evidence/risk data without truncation or derived calculations.
        details.append(
            MappingProxyType({
                **row,
                "row": row,
                "risk_records": tuple(risk for risk in snapshot.risk_records if risk["row_id"] == row["row_id"]),
                "evidence_summary": snapshot.evidence_summary,
                "decision_summary": tuple(d for d in snapshot.decision_summary if d.get("row_id") == row["row_id"]),
                "propagation": snapshot.propagation,
            })
        )
    return FmeaReportView(columns, tuple(rows), tuple(details))
