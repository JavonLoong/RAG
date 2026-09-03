from __future__ import annotations

import io
from dataclasses import fields
from zipfile import ZipFile

import pytest
from docx import Document

from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot
from fmea_infrastructure.export_docx import DocxFmeaExporter
from tests.fmea_governance_fixtures import make_normalized_snapshot

MARKER = "DRAFT PREVIEW — NOT PUBLISHED"
SECTIONS = ["FMEA", "Risk", "Propagation", "Evidence", "Decisions", "Unresolved"]


def _forge_snapshot(snapshot: NormalizedFmeaSnapshot, **overrides: object) -> NormalizedFmeaSnapshot:
    forged = object.__new__(NormalizedFmeaSnapshot)
    for field in fields(snapshot):
        object.__setattr__(forged, field.name, getattr(snapshot, field.name))
    for name, value in overrides.items():
        object.__setattr__(forged, name, value)
    return forged


def _paragraph_text(document: Document) -> str:
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def test_docx_render_has_title_manifest_tables_sections_and_footer_identity() -> None:
    snapshot = make_normalized_snapshot(rows=2)

    payload = DocxFmeaExporter().render(snapshot)

    document = Document(io.BytesIO(payload))
    text = _paragraph_text(document)
    table_text = "\n".join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
    assert "FMEA Export" in text
    assert all(section in text for section in SECTIONS)
    assert snapshot.revision_id in table_text
    assert snapshot.snapshot_id in table_text
    assert snapshot.publication_id in table_text
    assert snapshot.manifest_id in table_text
    assert snapshot.snapshot_hash in table_text
    assert len(document.tables) >= 7
    footer_text = "\n".join(paragraph.text for paragraph in document.sections[0].footer.paragraphs)
    assert snapshot.revision_id in footer_text
    assert snapshot.snapshot_hash in footer_text


def test_docx_formula_prefix_text_is_literal_and_package_has_no_executable_or_external_parts() -> None:
    snapshot = make_normalized_snapshot(
        row_payload={
            "row_id": "row-docx",
            "formula": "=SUM(A1:A2)",
            "plus": "+cmd|' /C calc'!A0",
            "minus": "-1+1",
            "at": "@SUM(1,1)",
        }
    )

    payload = DocxFmeaExporter().render(snapshot)

    document = Document(io.BytesIO(payload))
    text = "\n".join(cell.text for table in document.tables for row in table.rows for cell in row.cells)
    assert "=SUM(A1:A2)" in text
    assert "+cmd|' /C calc'!A0" in text
    with ZipFile(io.BytesIO(payload)) as archive:
        original_names = archive.namelist()
        names = {name.casefold() for name in original_names}
        assert not any("vbaproject" in name or "altchunk" in name for name in names)
        assert not any(name.startswith("word/embeddings/") for name in names)
        assert not any(
            b'targetmode="external"' in archive.read(name).lower() for name in original_names if name.endswith(".rels")
        )
        assert b"altChunk" not in archive.read("word/document.xml")


def test_docx_draft_marker_is_explicit_and_published_output_has_none() -> None:
    snapshot = make_normalized_snapshot()

    draft = DocxFmeaExporter(draft_preview=True).render(snapshot)
    published = DocxFmeaExporter(draft_preview=False).render(snapshot)

    draft_text = _paragraph_text(Document(io.BytesIO(draft)))
    published_text = _paragraph_text(Document(io.BytesIO(published)))
    assert MARKER in draft_text
    assert MARKER not in published_text


@pytest.mark.parametrize("bad_value", ["bad\x01value", float("nan"), float("inf"), object()])
def test_docx_rejects_office_unsafe_or_malformed_snapshot_without_leaking_input(bad_value: object) -> None:
    snapshot = make_normalized_snapshot()
    forged = _forge_snapshot(snapshot, rows=({"row_id": "row-1", "value": bad_value},), row_count=1)

    with pytest.raises(ValueError) as captured:
        DocxFmeaExporter().render(forged)

    assert getattr(captured.value, "code", None) == "FMEA_EXPORT_DOCX_INVALID"
    assert str(captured.value) == "snapshot cannot be rendered as DOCX"
    assert "bad" not in str(captured.value)


def test_docx_rejects_wrong_type_and_does_not_mutate_snapshot() -> None:
    snapshot = make_normalized_snapshot()
    before = repr(snapshot)

    with pytest.raises(ValueError) as captured:
        DocxFmeaExporter().render(object())  # type: ignore[arg-type]

    assert getattr(captured.value, "code", None) == "FMEA_EXPORT_SNAPSHOT_INVALID"
    assert str(captured.value) == "snapshot must be a NormalizedFmeaSnapshot"
    DocxFmeaExporter().render(snapshot)
    assert repr(snapshot) == before
