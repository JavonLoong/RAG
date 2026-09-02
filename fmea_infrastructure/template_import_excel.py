"""Bounded, non-executing XLSX template ingestion."""

# XML is parsed only after ZIP limits, path checks, and declaration checks.
# TRY003 is consistent with the stable ValueError-style importer boundary.

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from core_domain.fmea.filename_policy import validate_filename
from core_domain.fmea.template_migration import (
    SourceStructureItem,
    TemplateDraft,
    TemplateDraftStatus,
)

from .office_package import (
    InspectedOfficePackage,
    OfficePackageLimits,
    TemplateImportError,
    _error,
    _parse_xml,
    _resolve_part_target,
    _text,
    classify_source_fields,
    inspect_office_zip,
)

_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _clock_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _worksheet_payloads(package: InspectedOfficePackage) -> tuple[tuple[str, bytes], ...]:
    workbook = _parse_xml(package.members["xl/workbook.xml"], label="workbook")
    relationships = package.members.get("xl/_rels/workbook.xml.rels")
    if relationships is None:
        raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "workbook relationships are missing")
    rel_root = _parse_xml(relationships, label="workbook relationships")
    targets = {
        relationship.attrib.get("Id", ""): relationship.attrib.get("Target", "")
        for relationship in rel_root
        if relationship.tag.rsplit("}", 1)[-1] == "Relationship"
    }
    payloads: list[tuple[str, bytes]] = []
    for sheet in workbook.findall(f"{{{_NAMESPACE}}}sheets/{{{_NAMESPACE}}}sheet"):
        name = sheet.attrib.get("name", "")
        relationship_id = sheet.attrib.get(f"{{{_R_NAMESPACE}}}id", "")
        target = targets.get(relationship_id)
        if not name or not target:
            raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "workbook sheet relationship is invalid")
        part_name = _resolve_part_target("xl/workbook.xml", target)
        if not part_name.casefold().startswith("xl/worksheets/") or part_name not in package.members:
            raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "workbook worksheet relationship is invalid")
        payloads.append((name, package.members[part_name]))
    return tuple(payloads)


def _stable_draft_id(workspace_id: str, source_hash: str) -> str:
    return f"draft-{uuid5(NAMESPACE_URL, f'fmea-template:{workspace_id}:{source_hash}')}"


class ExcelTemplateImporter:
    """Read worksheet structure without evaluating formulas, links, or macros."""

    def __init__(
        self,
        *,
        limits: OfficePackageLimits | None = None,
        clock: Callable[[], str] = _clock_now,
        max_uncompressed_member_bytes: int | None = None,
    ) -> None:
        self._limits = limits or OfficePackageLimits(
            max_uncompressed_member_bytes=max_uncompressed_member_bytes
            if max_uncompressed_member_bytes is not None
            else OfficePackageLimits().max_uncompressed_member_bytes
        )
        self._clock = clock

    def parse(self, raw_bytes: bytes, filename: str, *, workspace_id: str) -> TemplateDraft:  # noqa: C901
        workspace = _text(workspace_id, "workspace_id")
        package = inspect_office_zip(raw_bytes, filename, kind="xlsx", limits=self._limits)
        worksheet_payloads = _worksheet_payloads(package)
        if len(worksheet_payloads) > self._limits.max_sheets:
            raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "workbook has too many sheets")
        if not worksheet_payloads:
            raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "workbook has no worksheets")
        try:
            from openpyxl import load_workbook

            workbook = load_workbook(
                io.BytesIO(raw_bytes),
                read_only=True,
                data_only=False,
                keep_links=False,
            )
        except TemplateImportError:
            raise
        except Exception as exc:
            raise _error("FMEA_TEMPLATE_CONTAINER_INVALID", "workbook cannot be parsed") from exc

        structure: list[SourceStructureItem] = []
        headers: list[tuple[str, str]] = []
        total_cell_count = 0
        try:
            if len(workbook.sheetnames) > self._limits.max_sheets:
                raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "workbook has too many sheets")
            for sheet_index, sheet_name in enumerate(workbook.sheetnames):
                worksheet = workbook[sheet_name]
                structure.append(SourceStructureItem(kind="sheet", locator=sheet_name))
                max_row = worksheet.max_row or 0
                max_column = worksheet.max_column or 0
                if max_row > self._limits.max_rows or max_column > self._limits.max_columns:
                    raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "worksheet dimensions exceed the configured limit")
                cell_count = 0
                for row in worksheet.iter_rows():
                    for cell in row:
                        if cell.value is None:
                            continue
                        cell_count += 1
                        total_cell_count += 1
                        if total_cell_count > self._limits.max_cells:
                            raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "worksheet has too many cells")
                        value = cell.value if isinstance(cell.value, str) else str(cell.value)
                        if len(value) > self._limits.max_text_length:
                            raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "cell text exceeds the configured limit")
                        structure.append(
                            SourceStructureItem(kind="cell", locator=f"{sheet_name}!{cell.coordinate}", value=value)
                        )
                        if cell.row == 1 and isinstance(cell.value, str) and cell.value.strip():
                            headers.append((cell.value.strip(), f"{sheet_name}!{cell.coordinate}"))
                worksheet_xml = _parse_xml(worksheet_payloads[sheet_index][1], label="worksheet")
                for merged in worksheet_xml.findall(f"{{{_NAMESPACE}}}mergeCells/{{{_NAMESPACE}}}mergeCell"):
                    reference = merged.attrib.get("ref")
                    if reference:
                        structure.append(SourceStructureItem(kind="merge", locator=f"{sheet_name}!{reference}"))
        finally:
            workbook.close()
        if len(structure) > self._limits.max_structure_items:
            raise _error("FMEA_TEMPLATE_LIMIT_EXCEEDED", "worksheet structure exceeds the configured limit")
        proposed, unknown, ambiguous, identified = classify_source_fields(tuple(headers))
        source_hash = sha256(raw_bytes).hexdigest()
        return TemplateDraft(
            draft_id=_stable_draft_id(workspace, source_hash),
            workspace_id=workspace,
            source_filename=validate_filename(filename, "source_filename", expected_extension="xlsx"),
            source_sha256=source_hash,
            source_type="xlsx",
            structure=tuple(structure),
            proposed_fields=proposed,
            unknown_fields=unknown,
            ambiguous_fields=ambiguous,
            parser_warnings=(),
            status=TemplateDraftStatus.DRAFT,
            created_at=self._clock(),
            identified_fields=identified,
        )


__all__ = [
    "ExcelTemplateImporter",
    "InspectedOfficePackage",
    "OfficePackageLimits",
    "TemplateImportError",
    "classify_source_fields",
    "inspect_office_zip",
]
