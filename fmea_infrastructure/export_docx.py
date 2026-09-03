"""Presentation-only DOCX rendering for normalized FMEA snapshots."""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from typing import Final, NoReturn
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

import orjson
from defusedxml.ElementTree import fromstring as safe_xml_fromstring
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from fmea_application.snapshot_contracts import (
    DRAFT_PREVIEW_MARKER,
    NormalizedFmeaSnapshot,
    revalidate_normalized_snapshot,
)

from .export_json import _snapshot_projection, _validate_export_value

_MAX_DOCX_CELL_TEXT: Final = 1_000_000
_MAX_COLUMNS: Final = 256
_TYPES_COLUMN: Final = "__types__"
_RESERVED_HEADERS: Final = frozenset({"Identity", _TYPES_COLUMN})
_REL_NS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"


class DocxExportError(ValueError):
    """Stable, public-safe DOCX rendering failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _error(code: str, message: str) -> DocxExportError:
    return DocxExportError(code, message)


def _invalid() -> NoReturn:
    raise ValueError


def _is_xml_char(value: str) -> bool:
    return all(
        codepoint in {0x9, 0xA, 0xD}
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
        for codepoint in map(ord, value)
    )


def _validate_office_value(value: object) -> None:
    if isinstance(value, str):
        if not _is_xml_char(value):
            _invalid()
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not _is_xml_char(key):
                _invalid()
            _validate_office_value(item)
        return
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            _validate_office_value(item)


def _json_text(value: object) -> str:
    try:
        return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")
    except (TypeError, ValueError, OverflowError):
        _invalid()


def _value_encoding(value: object) -> tuple[str, str]:
    if type(value) is str:
        return value, "str"
    if value is None:
        return "null", "null"
    if type(value) is bool:
        return "true" if value else "false", "bool"
    if type(value) is int:
        return str(value), "int"
    if type(value) is float:
        return _json_text(value), "float"
    if isinstance(value, Mapping | list):
        return _json_text(value), "json"
    _invalid()


def _cell_text(value: str) -> str:
    if len(value) > _MAX_DOCX_CELL_TEXT:
        _invalid()
    return value


def _set_cell_text(cell, value: str) -> None:
    cell.text = _cell_text(value)
    for paragraph in cell.paragraphs:
        paragraph.paragraph_format.space_after = Pt(0)
        for run in paragraph.runs:
            run.font.size = Pt(9)


def _identity(record: Mapping[str, object], identity_field: str | None, index: int) -> str:
    if identity_field is not None:
        value = record.get(identity_field)
        if type(value) is not str or not value.strip():
            _invalid()
        return value
    for field_name in ("source_id", "code", "item_id"):
        value = record.get(field_name)
        if type(value) is str and value.strip():
            return value
    return f"item-{index:03d}"


def _record_columns(records: Sequence[Mapping[str, object]]) -> list[str]:
    keys = {key for record in records for key in record}
    if any(type(key) is not str or key in _RESERVED_HEADERS for key in keys):
        _invalid()
    columns = sorted(keys)
    if len(columns) + 2 > _MAX_COLUMNS:
        _invalid()
    return columns


def _append_manifest(document: Document, projection: Mapping[str, object]) -> None:
    document.add_heading("Manifest", level=1)
    table = document.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    for cell, value in zip(table.rows[0].cells, ("Key", "Value", "Type"), strict=True):
        _set_cell_text(cell, value)
    metadata: tuple[tuple[str, object], ...] = (
        ("schema_version", projection["schema_version"]),
        ("snapshot_schema_version", projection["snapshot_schema_version"]),
        ("snapshot_id", projection["snapshot_id"]),
        ("workspace_id", projection["workspace_id"]),
        ("analysis_id", projection["analysis_id"]),
        ("revision_id", projection["revision_id"]),
        ("revision_hash", projection["revision_hash"]),
        ("publication_id", projection["publication_id"]),
        ("source_publication_id", projection["source_publication_id"]),
        ("manifest_id", projection["manifest_id"]),
        ("row_count", projection["row_count"]),
        ("risk_count", len(projection["risk_records"])),
        ("propagation_present", projection["propagation"] is not None),
        ("evidence_count", len(projection["evidence_summary"])),
        ("decision_count", len(projection["decision_summary"])),
        ("unresolved_count", len(projection["unresolved_items"])),
        ("snapshot_hash", projection["snapshot_hash"]),
        ("created_at", projection["created_at"]),
        ("version_manifest", projection["version_manifest"]),
        ("audit_summary", projection["audit_summary"]),
        ("draft_preview", projection["draft_preview"]),
        ("draft_marker", projection["draft_marker"]),
        ("format", projection["format"]),
        ("media_type", projection["media_type"]),
    )
    for key, value in metadata:
        encoded, value_type = _value_encoding(value)
        row = table.add_row().cells
        _set_cell_text(row[0], key)
        _set_cell_text(row[1], encoded)
        _set_cell_text(row[2], value_type)


def _append_typed_table(
    document: Document,
    records: Sequence[Mapping[str, object]],
    *,
    identity_field: str | None,
) -> None:
    columns = _record_columns(records)
    table = document.add_table(rows=1, cols=len(columns) + 2)
    table.style = "Table Grid"
    headers = ["Identity", *columns, _TYPES_COLUMN]
    for cell, header in zip(table.rows[0].cells, headers, strict=True):
        _set_cell_text(cell, header)
    for row_index, record in enumerate(records, start=2):
        row = table.add_row().cells
        _set_cell_text(row[0], _identity(record, identity_field, row_index - 1))
        types: dict[str, str] = {}
        for column_index, key in enumerate(columns, start=1):
            if key not in record:
                _set_cell_text(row[column_index], "")
                continue
            encoded, value_type = _value_encoding(record[key])
            types[key] = value_type
            _set_cell_text(row[column_index], encoded)
        _set_cell_text(row[-1], _json_text(types))


def _append_section(
    document: Document,
    title: str,
    records: Sequence[Mapping[str, object]],
    *,
    identity_field: str | None,
) -> None:
    document.add_heading(title, level=1)
    _append_typed_table(document, records, identity_field=identity_field)


def _validate_package_xml(name: str, raw: bytes) -> None:
    folded_name = name.casefold()
    if not folded_name.endswith((".xml", ".rels")):
        return
    root = safe_xml_fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    if folded_name.endswith(".rels"):
        for relationship in root.iter("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
            target = relationship.attrib.get("Target", "")
            if relationship.attrib.get("TargetMode", "").casefold() == "external" or target.casefold().startswith((
                "http:",
                "https:",
                "file:",
                "ftp:",
            )):
                _invalid()
    if folded_name.endswith(".xml"):
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1].casefold() in {"altchunk", "fldsimple", "fldchar", "instrtext"}:
                _invalid()


def _validate_package(payload: bytes) -> None:
    try:
        with ZipFile(io.BytesIO(payload)) as archive:
            names = tuple(archive.namelist())
            folded = {name.casefold() for name in names}
            if any(".." in name.split("/") or "\\" in name or name.startswith("/") for name in names):
                _invalid()
            if any("vbaproject" in name or name.startswith("word/embeddings/") for name in folded):
                _invalid()
            for name in names:
                _validate_package_xml(name, archive.read(name))
    except (BadZipFile, OSError, ValueError, ParseError):
        _invalid()


class DocxFmeaExporter:
    """Render a normalized snapshot to an in-memory, presentation-only DOCX."""

    format = "docx"
    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def __init__(self, draft_preview: bool = False) -> None:
        if type(draft_preview) is not bool:
            raise _error("FMEA_EXPORT_DOCX_INVALID", "draft_preview must be a boolean")
        self._draft_preview = draft_preview

    def render(self, snapshot: NormalizedFmeaSnapshot, *, draft_preview: bool | None = None) -> bytes:
        if type(snapshot) is not NormalizedFmeaSnapshot:
            raise _error("FMEA_EXPORT_SNAPSHOT_INVALID", "snapshot must be a NormalizedFmeaSnapshot")
        if draft_preview is not None and type(draft_preview) is not bool:
            raise _error("FMEA_EXPORT_DOCX_INVALID", "draft_preview must be a boolean or None")
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
            _validate_office_value(projection)
            document = Document()
            document.core_properties.title = "FMEA Export"
            title = document.add_heading("FMEA Export", level=0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if resolved_preview:
                marker = document.add_paragraph(DRAFT_PREVIEW_MARKER)
                marker.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _append_manifest(document, projection)
            _append_section(document, "FMEA", projection["rows"], identity_field="row_id")
            _append_section(document, "Risk", projection["risk_records"], identity_field="assessment_id")
            propagation = () if projection["propagation"] is None else (projection["propagation"],)
            _append_section(document, "Propagation", propagation, identity_field=None)
            _append_section(document, "Evidence", projection["evidence_summary"], identity_field="pack_id")
            _append_section(document, "Decisions", projection["decision_summary"], identity_field="decision_id")
            _append_section(document, "Unresolved", projection["unresolved_items"], identity_field=None)
            footer = document.sections[0].footer.paragraphs[0]
            publication_id = projection["publication_id"] or ""
            source_publication_id = projection["source_publication_id"] or ""
            footer.text = (
                f"revision_id={projection['revision_id']} | snapshot_id={projection['snapshot_id']} | "
                f"publication_id={publication_id} | source_publication_id={source_publication_id} | "
                f"snapshot_hash={projection['snapshot_hash']}"
            )
            footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
            buffer = io.BytesIO()
            document.save(buffer)
            payload = buffer.getvalue()
            _validate_package(payload)
        except DocxExportError:
            raise
        except Exception:
            raise _error("FMEA_EXPORT_DOCX_INVALID", "snapshot cannot be rendered as DOCX") from None
        else:
            return payload


__all__ = ["DocxExportError", "DocxFmeaExporter"]
