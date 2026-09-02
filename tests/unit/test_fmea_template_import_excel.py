from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from core_domain.fmea.template_migration import SourceStructureItem, TemplateDraftStatus
from fmea_infrastructure.template_import_excel import ExcelTemplateImporter, TemplateImportError


def _xlsx(*, sheet_xml: str | None = None, extra: tuple[tuple[str, bytes], ...] = ()) -> bytes:
    worksheet = (
        sheet_xml
        or """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData>
        <row r="1">
          <c r="A1" t="inlineStr"><is><t>Failure Mode</t></is></c>
          <c r="B1" t="inlineStr"><is><t>Cause</t></is></c>
          <c r="C1" t="inlineStr"><is><t>Legacy Criticality</t></is></c>
        </row>
      </sheetData>
      <mergeCells count="1"><mergeCell ref="A3:B3"/></mergeCells>
    </worksheet>"""
    )
    parts = {
        "[Content_Types].xml": b"""<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
          <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
        </Types>""",
        "_rels/.rels": b"""<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
        </Relationships>""",
        "xl/workbook.xml": b"""<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
        </workbook>""",
        "xl/_rels/workbook.xml.rels": b"""<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
        </Relationships>""",
        "xl/worksheets/sheet1.xml": worksheet.encode(),
    }
    parts.update(dict(extra))
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)
    return output.getvalue()


def test_excel_import_preserves_cells_merges_unknown_and_ambiguous_headers() -> None:
    draft = ExcelTemplateImporter(clock=lambda: "2026-08-27T12:00:00Z").parse(_xlsx(), "fmea.xlsx", workspace_id="ws-1")

    assert draft.status is TemplateDraftStatus.DRAFT
    assert draft.source_type == "xlsx"
    assert SourceStructureItem(kind="merge", locator="Sheet1!A3:B3") in draft.structure
    assert SourceStructureItem(kind="cell", locator="Sheet1!A1", value="Failure Mode") in draft.structure
    assert "Legacy Criticality" in draft.unknown_fields
    assert "Cause" in draft.ambiguous_fields
    assert "failure_mode" in draft.identified_fields


def test_excel_import_rejects_formula_before_openpyxl_can_evaluate_it() -> None:
    formula = b"""<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData><row r="1"><c r="A1"><f>SUM(1,2)</f><v>3</v></c></row></sheetData>
    </worksheet>"""

    with pytest.raises(TemplateImportError, match="formula"):
        ExcelTemplateImporter().parse(_xlsx(sheet_xml=formula.decode()), "fmea.xlsx", workspace_id="ws-1")


@pytest.mark.parametrize(
    ("filename", "extra"),
    (
        ("fmea.xlsm", (("xl/vbaProject.bin", b"macro"),)),
        ("fmea.xlsx", (("../escape.xml", b"escape"),)),
    ),
)
def test_excel_import_rejects_macro_enabled_and_path_escape_packages(
    filename: str, extra: tuple[tuple[str, bytes], ...]
) -> None:
    with pytest.raises(TemplateImportError):
        ExcelTemplateImporter().parse(_xlsx(extra=extra), filename, workspace_id="ws-1")


def test_excel_import_rejects_duplicate_zip_members_and_oversized_members() -> None:
    duplicate = BytesIO()
    with ZipFile(duplicate, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", b"one")
        archive.writestr("xl/workbook.xml", b"two")
    with pytest.raises(TemplateImportError, match="duplicate"):
        ExcelTemplateImporter().parse(duplicate.getvalue(), "fmea.xlsx", workspace_id="ws-1")

    with pytest.raises(TemplateImportError, match="limit|size"):
        ExcelTemplateImporter(max_uncompressed_member_bytes=8).parse(
            _xlsx(extra=(("xl/large.xml", b"x" * 9),)), "fmea.xlsx", workspace_id="ws-1"
        )


def test_excel_import_rejects_external_relationships_before_office_parsing() -> None:
    relationships = b"""<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Target="https://example.invalid/model" TargetMode="External"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink"/>
    </Relationships>"""

    with pytest.raises(TemplateImportError, match="external"):
        ExcelTemplateImporter().parse(
            _xlsx(
                extra=(
                    ("xl/externalLinks/externalLink1.xml", b"<externalLink/>"),
                    ("xl/_rels/workbook.xml.rels", relationships),
                )
            ),
            "fmea.xlsx",
            workspace_id="ws-1",
        )
