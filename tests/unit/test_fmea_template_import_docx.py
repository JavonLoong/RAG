from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from core_domain.fmea.template_migration import SourceStructureItem, TemplateDraftStatus
from fmea_infrastructure.template_import_docx import DocxTemplateImporter, TemplateImportError


def _docx(
    *, document_xml: str | None = None, rels_xml: str | None = None, extra: tuple[tuple[str, bytes], ...] = ()
) -> bytes:
    document = (
        document_xml
        or """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Failure Mode</w:t></w:r></w:p>
        <w:p><w:r><w:t>Cause</w:t></w:r></w:p>
        <w:p><w:r><w:t>Legacy Criticality</w:t></w:r></w:p>
        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Function</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        <w:sectPr/>
      </w:body>
    </w:document>"""
    )
    rels = (
        rels_xml
        or """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    </Relationships>"""
    )
    parts = {
        "[Content_Types].xml": b"""<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
          <Default Extension="xml" ContentType="application/xml"/>
          <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
        </Types>""",
        "_rels/.rels": rels.encode(),
        "word/document.xml": document.encode(),
    }
    parts.update(dict(extra))
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)
    return output.getvalue()


def test_docx_import_preserves_paragraphs_tables_unknown_and_ambiguous_fields() -> None:
    draft = DocxTemplateImporter(clock=lambda: "2026-08-27T12:00:00Z").parse(_docx(), "fmea.docx", workspace_id="ws-1")

    assert draft.status is TemplateDraftStatus.DRAFT
    assert (
        SourceStructureItem(kind="paragraph", locator="document#paragraph-0", value="Failure Mode") in draft.structure
    )
    assert (
        SourceStructureItem(kind="table-cell", locator="document#table-0/row-0/cell-0", value="Function")
        in draft.structure
    )
    assert "Legacy Criticality" in draft.unknown_fields
    assert "Cause" in draft.ambiguous_fields
    assert "function" in draft.identified_fields


@pytest.mark.parametrize(
    "document_xml",
    (
        """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
          <w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r></w:p><w:sectPr/>
        </w:body></w:document>""",
        """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
          <w:altChunk r:id="rId2" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/><w:sectPr/>
        </w:body></w:document>""",
    ),
)
def test_docx_import_rejects_fields_and_executable_content(document_xml: str) -> None:
    with pytest.raises(TemplateImportError, match="field|executable"):
        DocxTemplateImporter().parse(_docx(document_xml=document_xml), "fmea.docx", workspace_id="ws-1")


def test_docx_import_rejects_external_relationships_and_malformed_packages() -> None:
    external = """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Target="https://example.invalid/remote" TargetMode="External"
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"/>
    </Relationships>"""
    with pytest.raises(TemplateImportError, match="external"):
        DocxTemplateImporter().parse(_docx(rels_xml=external), "fmea.docx", workspace_id="ws-1")
    with pytest.raises(TemplateImportError, match="container|ZIP|malformed"):
        DocxTemplateImporter().parse(b"not a zip", "fmea.docx", workspace_id="ws-1")


def test_docx_import_rejects_macro_enabled_extension_and_path_escape() -> None:
    with pytest.raises(TemplateImportError):
        DocxTemplateImporter().parse(
            _docx(extra=(("word/vbaProject.bin", b"macro"),)), "fmea.docm", workspace_id="ws-1"
        )
    with pytest.raises(TemplateImportError):
        DocxTemplateImporter().parse(_docx(extra=(("../escape.xml", b"escape"),)), "fmea.docx", workspace_id="ws-1")


@pytest.mark.parametrize(
    "extra",
    (
        (("word/activeX/activeX1.bin", b"plugin"),),
        (("WORD/document.xml", b"case collision"),),
    ),
)
def test_docx_import_rejects_plugins_and_case_colliding_members_before_parser(extra) -> None:
    with pytest.raises(TemplateImportError, match="executable|duplicate|collision"):
        DocxTemplateImporter().parse(_docx(extra=extra), "fmea.docx", workspace_id="ws-1")


def test_docx_import_rejects_broken_or_traversing_internal_relationships_before_parser(monkeypatch) -> None:
    monkeypatch.setattr(
        "fmea_infrastructure.template_import_docx.Document", lambda *_args: pytest.fail("Office parser was called")
    )
    for target in ("../escape.xml", "missing.xml"):
        relationships = f"""<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="{target}"/>
        </Relationships>"""
        with pytest.raises(TemplateImportError, match="relationship|path|target"):
            DocxTemplateImporter().parse(_docx(rels_xml=relationships), "fmea.docx", workspace_id="ws-1")


def test_docx_import_rejects_fields_in_header_before_parser(monkeypatch) -> None:
    monkeypatch.setattr(
        "fmea_infrastructure.template_import_docx.Document", lambda *_args: pytest.fail("Office parser was called")
    )
    header = b"""<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r></w:p>
    </w:hdr>"""
    with pytest.raises(TemplateImportError, match="field"):
        DocxTemplateImporter().parse(_docx(extra=(("word/header1.xml", header),)), "fmea.docx", workspace_id="ws-1")
