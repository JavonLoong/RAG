from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from core_domain.fmea.template_migration import SourceStructureItem, TemplateDraftStatus
from fmea_infrastructure.template_import_excel import ExcelTemplateImporter, OfficePackageLimits, TemplateImportError


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


@pytest.mark.parametrize(
    "extra",
    (
        (("xl/activeX/activeX1.bin", b"plugin"),),
        (("XL/workbook.xml", b"case collision"),),
    ),
)
def test_excel_import_rejects_plugins_and_case_colliding_members_before_parser(extra) -> None:
    with pytest.raises(TemplateImportError, match="executable|duplicate|collision"):
        ExcelTemplateImporter().parse(_xlsx(extra=extra), "fmea.xlsx", workspace_id="ws-1")


def test_excel_import_rejects_broken_or_traversing_internal_relationships_before_parser(monkeypatch) -> None:
    monkeypatch.setattr("openpyxl.load_workbook", lambda *_args, **_kwargs: pytest.fail("Office parser was called"))
    for target in ("../escape.xml", "worksheets/missing.xml"):
        relationships = f"""<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{target}"/>
        </Relationships>""".encode()
        with pytest.raises(TemplateImportError, match="relationship|path|target"):
            ExcelTemplateImporter().parse(
                _xlsx(extra=(("xl/_rels/workbook.xml.rels", relationships),)),
                "fmea.xlsx",
                workspace_id="ws-1",
            )


def test_excel_import_rejects_formula_defined_name_before_parser(monkeypatch) -> None:
    monkeypatch.setattr("openpyxl.load_workbook", lambda *_args, **_kwargs: pytest.fail("Office parser was called"))
    workbook = b"""<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
      <definedNames><definedName name="unsafe">SUM(Sheet1!A1:A2)</definedName></definedNames>
    </workbook>"""
    with pytest.raises(TemplateImportError, match="formula|defined"):
        ExcelTemplateImporter().parse(_xlsx(extra=(("xl/workbook.xml", workbook),)), "fmea.xlsx", workspace_id="ws-1")


def test_excel_import_marks_normalized_source_and_target_collisions_ambiguous() -> None:
    sheet = """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData><row r="1">
        <c r="A1" t="inlineStr"><is><t>Failure Mode</t></is></c>
        <c r="B1" t="inlineStr"><is><t> failure   mode </t></is></c>
      </row></sheetData>
    </worksheet>"""
    draft = ExcelTemplateImporter().parse(_xlsx(sheet_xml=sheet), "fmea.xlsx", workspace_id="ws-1")
    assert draft.proposed_fields == ()
    assert len(draft.ambiguous_fields) == 2


@pytest.mark.parametrize(
    "limits",
    (
        OfficePackageLimits(max_members=4),
        OfficePackageLimits(max_total_uncompressed_bytes=100),
        OfficePackageLimits(max_relationships=1),
        OfficePackageLimits(max_columns=2),
        OfficePackageLimits(max_cells=2),
    ),
)
def test_excel_import_enforces_package_and_worksheet_limits(limits: OfficePackageLimits) -> None:
    with pytest.raises(TemplateImportError, match="limit|many|dimensions|size"):
        ExcelTemplateImporter(limits=limits).parse(_xlsx(), "fmea.xlsx", workspace_id="ws-1")


def test_excel_import_enforces_sheet_and_compression_ratio_limits() -> None:
    second_row = """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData><row r="2"><c r="A2" t="inlineStr"><is><t>Failure Mode</t></is></c></row></sheetData>
    </worksheet>"""
    with pytest.raises(TemplateImportError, match="dimensions|limit"):
        ExcelTemplateImporter(limits=OfficePackageLimits(max_rows=1)).parse(
            _xlsx(sheet_xml=second_row), "fmea.xlsx", workspace_id="ws-1"
        )
    workbook = b"""<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheets>
        <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
        <sheet name="Sheet2" sheetId="2" r:id="rId2"/>
      </sheets>
    </workbook>"""
    relationships = b"""<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
      <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
    </Relationships>"""
    sheet = b"""<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>"""
    with pytest.raises(TemplateImportError, match="sheets|limit"):
        ExcelTemplateImporter(limits=OfficePackageLimits(max_sheets=1)).parse(
            _xlsx(
                extra=(
                    ("xl/workbook.xml", workbook),
                    ("xl/_rels/workbook.xml.rels", relationships),
                    ("xl/worksheets/sheet2.xml", sheet),
                )
            ),
            "fmea.xlsx",
            workspace_id="ws-1",
        )
    with pytest.raises(TemplateImportError, match="compression|limit"):
        ExcelTemplateImporter(limits=OfficePackageLimits(max_compression_ratio=2)).parse(
            _xlsx(extra=(("xl/large.xml", b"x" * 70_000),)),
            "fmea.xlsx",
            workspace_id="ws-1",
        )


def test_excel_import_rejects_duplicate_relationship_ids_and_bad_content_type_binding() -> None:
    duplicate_relationships = b"""<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
    </Relationships>"""
    with pytest.raises(TemplateImportError, match="relationship IDs"):
        ExcelTemplateImporter().parse(
            _xlsx(extra=(("xl/_rels/workbook.xml.rels", duplicate_relationships),)),
            "fmea.xlsx",
            workspace_id="ws-1",
        )
    bad_content_types = b"""<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/xl/workbook.xml" ContentType="application/xml"/>
    </Types>"""
    with pytest.raises(TemplateImportError, match="content types|unsupported"):
        ExcelTemplateImporter().parse(
            _xlsx(extra=(("[Content_Types].xml", bad_content_types),)),
            "fmea.xlsx",
            workspace_id="ws-1",
        )


def test_excel_import_scans_declared_xml_regardless_of_suffix_and_encoding() -> None:
    content_types = b"""<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
      <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
      <Override PartName="/xl/hidden.bin" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
    </Types>"""
    hidden_formula = b"""<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData><row r="1"><c r="A1"><f>SUM(1,2)</f></c></row></sheetData>
    </worksheet>"""
    with pytest.raises(TemplateImportError, match="formula"):
        ExcelTemplateImporter().parse(
            _xlsx(extra=(("[Content_Types].xml", content_types), ("xl/hidden.bin", hidden_formula))),
            "fmea.xlsx",
            workspace_id="ws-1",
        )

    utf16_dtd = """<?xml version="1.0" encoding="utf-16"?>
    <!DOCTYPE worksheet [<!ENTITY x "expanded">]>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>&x;</sheetData></worksheet>
    """.encode("utf-16")
    with pytest.raises(TemplateImportError, match="XML|declaration|entity|executable"):
        ExcelTemplateImporter().parse(
            _xlsx(extra=(("xl/hidden.xml", utf16_dtd),)),
            "fmea.xlsx",
            workspace_id="ws-1",
        )


@pytest.mark.parametrize("ratio", (float("nan"), float("inf"), True))
def test_office_package_limits_reject_non_finite_or_boolean_compression_ratio(ratio: object) -> None:
    with pytest.raises(ValueError, match="compression"):
        OfficePackageLimits(max_compression_ratio=ratio)  # type: ignore[arg-type]
