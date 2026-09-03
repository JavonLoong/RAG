from __future__ import annotations

import io
from dataclasses import fields
from zipfile import ZipFile

import openpyxl
import pytest
from defusedxml.ElementTree import fromstring as safe_xml_fromstring

from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot, snapshot_content_hash
from fmea_infrastructure.export_xlsx import XlsxFmeaExporter
from tests.fmea_governance_fixtures import make_normalized_snapshot

MARKER = "DRAFT PREVIEW — NOT PUBLISHED"
SHEETS = ["Manifest", "FMEA", "Risk", "Propagation", "Evidence", "Decisions", "Unresolved"]


def _forge_snapshot(snapshot: NormalizedFmeaSnapshot, **overrides: object) -> NormalizedFmeaSnapshot:
    forged = object.__new__(NormalizedFmeaSnapshot)
    for field in fields(snapshot):
        object.__setattr__(forged, field.name, getattr(snapshot, field.name))
    for name, value in overrides.items():
        object.__setattr__(forged, name, value)
    return forged


def test_xlsx_render_has_the_exact_readable_sheet_contract() -> None:
    snapshot = make_normalized_snapshot(rows=2)
    exporter = XlsxFmeaExporter()

    payload = exporter.render(snapshot)

    assert type(payload) is bytes
    assert exporter.format == "xlsx"
    assert exporter.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    workbook = openpyxl.load_workbook(io.BytesIO(payload), data_only=False, read_only=False)
    assert workbook.sheetnames == SHEETS
    assert workbook["Manifest"].freeze_panes == "A2"
    assert workbook["FMEA"].freeze_panes == "A2"
    manifest = {
        str(row[0].value): row[1].value for row in workbook["Manifest"].iter_rows(min_row=2) if row[0].value is not None
    }
    assert manifest["schema_version"] == "graphrag.fmea.export.v1"
    assert manifest["snapshot_id"] == snapshot.snapshot_id
    assert manifest["revision_id"] == snapshot.revision_id
    assert manifest["publication_id"] == snapshot.publication_id
    assert manifest["manifest_id"] == snapshot.manifest_id
    assert manifest["snapshot_hash"] == snapshot.snapshot_hash
    assert manifest["row_count"] == "2"
    assert manifest["version_manifest"]
    assert manifest["draft_marker"] == "null"
    for worksheet in workbook.worksheets:
        assert worksheet.auto_filter.ref is not None
        assert all(0 < dimension.width <= 48 for dimension in worksheet.column_dimensions.values())


def test_xlsx_formula_prefixes_are_real_strings_and_never_formula_xml() -> None:
    snapshot = make_normalized_snapshot(
        row_payload={
            "row_id": "row-injection",
            "formula": "=SUM(A1:A2)",
            "plus": "+cmd|' /C calc'!A0",
            "minus": "-1+1",
            "at": "@SUM(1,1)",
        }
    )

    payload = XlsxFmeaExporter().render(snapshot)

    workbook = openpyxl.load_workbook(io.BytesIO(payload), data_only=False, read_only=False)
    worksheet = workbook["FMEA"]
    headers = {cell.value: cell.column for cell in worksheet[1]}
    for field_name, expected in {
        "formula": "=SUM(A1:A2)",
        "plus": "+cmd|' /C calc'!A0",
        "minus": "-1+1",
        "at": "@SUM(1,1)",
    }.items():
        cell = worksheet.cell(2, headers[field_name])
        assert cell.value == expected
        assert cell.data_type == "s"

    with ZipFile(io.BytesIO(payload)) as archive:
        original_names = archive.namelist()
        names = {name.casefold() for name in original_names}
        assert not any(name.startswith("xl/externallinks/") for name in names)
        assert not any(name.endswith((".xlsm", ".bin")) for name in names)
        for name in original_names:
            if name.endswith(".xml"):
                root = safe_xml_fromstring(archive.read(name))
                assert not list(root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}f"))
        assert b"<f>" not in archive.read("xl/worksheets/sheet2.xml")


def test_xlsx_draft_marker_is_explicit_and_published_output_has_none() -> None:
    snapshot = make_normalized_snapshot()
    exporter = XlsxFmeaExporter(draft_preview=True)

    draft = exporter.render(snapshot)
    published = exporter.render(snapshot, draft_preview=False)

    draft_workbook = openpyxl.load_workbook(io.BytesIO(draft), read_only=False)
    published_workbook = openpyxl.load_workbook(io.BytesIO(published), read_only=False)
    draft_text = [cell.value for row in draft_workbook["Manifest"].iter_rows() for cell in row]
    published_text = [cell.value for row in published_workbook["Manifest"].iter_rows() for cell in row]
    assert MARKER in draft_text
    assert MARKER not in published_text
    draft_manifest = {
        str(row[0].value): (row[1].value, row[2].value)
        for row in draft_workbook["Manifest"].iter_rows(min_row=2)
        if row[0].value is not None
    }
    published_manifest = {
        str(row[0].value): (row[1].value, row[2].value)
        for row in published_workbook["Manifest"].iter_rows(min_row=2)
        if row[0].value is not None
    }
    assert draft_manifest["publication_id"] == ("null", "null")
    assert draft_manifest["source_publication_id"] == (snapshot.publication_id, "str")
    assert published_manifest["publication_id"] == (snapshot.publication_id, "str")
    assert published_manifest["source_publication_id"] == ("null", "null")


@pytest.mark.parametrize("bad_value", ["bad\x01value", float("nan"), float("inf"), object()])
def test_xlsx_rejects_office_unsafe_or_malformed_snapshot_without_leaking_input(bad_value: object) -> None:
    snapshot = make_normalized_snapshot()
    forged = _forge_snapshot(snapshot, rows=({"row_id": "row-1", "value": bad_value},), row_count=1)

    with pytest.raises(ValueError) as captured:
        XlsxFmeaExporter().render(forged)

    assert getattr(captured.value, "code", None) == "FMEA_EXPORT_XLSX_INVALID"
    assert str(captured.value) == "snapshot cannot be rendered as XLSX"
    assert "bad" not in str(captured.value)


@pytest.mark.parametrize(
    "overrides",
    (
        {"row_count": 0},
        {"schema_version": "not-normalized-v99"},
    ),
)
def test_xlsx_rejects_hash_consistent_snapshot_invariant_bypass(overrides: dict[str, object]) -> None:
    snapshot = make_normalized_snapshot()
    forged = _forge_snapshot(snapshot, **overrides)
    object.__setattr__(forged, "snapshot_hash", snapshot_content_hash(forged))

    with pytest.raises(ValueError) as captured:
        XlsxFmeaExporter().render(forged)

    assert getattr(captured.value, "code", None) == "FMEA_EXPORT_XLSX_INVALID"
    assert str(captured.value) == "snapshot cannot be rendered as XLSX"
    assert captured.value.__cause__ is None


def test_xlsx_rejects_wrong_type_and_does_not_mutate_snapshot() -> None:
    snapshot = make_normalized_snapshot()
    before = repr(snapshot)

    with pytest.raises(ValueError) as captured:
        XlsxFmeaExporter().render(object())  # type: ignore[arg-type]

    assert getattr(captured.value, "code", None) == "FMEA_EXPORT_SNAPSHOT_INVALID"
    assert str(captured.value) == "snapshot must be a NormalizedFmeaSnapshot"
    XlsxFmeaExporter().render(snapshot)
    assert repr(snapshot) == before
