from __future__ import annotations

import io
import json
from collections.abc import Iterable

import openpyxl
import orjson
from docx import Document

from fmea_infrastructure.export_docx import DocxFmeaExporter
from fmea_infrastructure.export_json import CanonicalJsonExporter
from fmea_infrastructure.export_xlsx import XlsxFmeaExporter
from tests.fmea_governance_fixtures import make_fmea_revision, make_normalized_snapshot, make_readiness_issue

MARKER = "DRAFT PREVIEW — NOT PUBLISHED"


def _decode_cell(value: object, value_type: str) -> object:
    if value_type == "str":
        return "" if value is None else str(value)
    if value_type == "null":
        return None
    if value_type == "bool":
        return json.loads(str(value).lower())
    if value_type in {"int", "float", "json"}:
        return json.loads(str(value))
    raise AssertionError


def _parse_typed_table(rows: Iterable[tuple[object, ...]]) -> list[dict[str, object]]:
    rows = iter(rows)
    headers = [str(value) for value in next(rows)]
    type_column = headers.index("__types__")
    result: list[dict[str, object]] = []
    for row in rows:
        if not any(value is not None and value != "" for value in row):
            continue
        types = json.loads(str(row[type_column]))
        item: dict[str, object] = {}
        for header, value in zip(headers, row, strict=True):
            if header in {"Identity", "__types__"} or header not in types:
                continue
            item[header] = _decode_cell(value, types[header])
        result.append(item)
    return result


def _parse_xlsx(payload: bytes) -> dict[str, object]:
    workbook = openpyxl.load_workbook(io.BytesIO(payload), data_only=False, read_only=False)
    manifest_rows = list(workbook["Manifest"].iter_rows(values_only=True))
    manifest = {str(row[0]): _decode_cell(row[1], str(row[2])) for row in manifest_rows[1:] if row[0] is not None}
    result: dict[str, object] = {
        key: manifest[key]
        for key in (
            "schema_version",
            "snapshot_id",
            "workspace_id",
            "analysis_id",
            "revision_id",
            "revision_hash",
            "publication_id",
            "manifest_id",
            "row_count",
            "snapshot_hash",
            "created_at",
        )
    }
    result.update({
        "rows": _parse_typed_table(workbook["FMEA"].iter_rows(values_only=True)),
        "risk_records": _parse_typed_table(workbook["Risk"].iter_rows(values_only=True)),
        "evidence_summary": _parse_typed_table(workbook["Evidence"].iter_rows(values_only=True)),
        "decision_summary": _parse_typed_table(workbook["Decisions"].iter_rows(values_only=True)),
        "unresolved_items": _parse_typed_table(workbook["Unresolved"].iter_rows(values_only=True)),
        "version_manifest": manifest["version_manifest"],
        "audit_summary": manifest["audit_summary"],
    })
    propagation_rows = _parse_typed_table(workbook["Propagation"].iter_rows(values_only=True))
    result["propagation"] = propagation_rows[0] if propagation_rows else None
    return result


def _parse_docx_typed_table(table) -> list[dict[str, object]]:
    return _parse_typed_table(tuple(tuple(cell.text for cell in row.cells) for row in table.rows))


def _parse_docx(payload: bytes) -> dict[str, object]:
    document = Document(io.BytesIO(payload))
    tables = iter(document.tables)
    manifest_table = next(tables)
    manifest = {
        row.cells[0].text: _decode_cell(row.cells[1].text, row.cells[2].text) for row in manifest_table.rows[1:]
    }
    result: dict[str, object] = {
        key: manifest[key]
        for key in (
            "schema_version",
            "snapshot_id",
            "workspace_id",
            "analysis_id",
            "revision_id",
            "revision_hash",
            "publication_id",
            "manifest_id",
            "row_count",
            "snapshot_hash",
            "created_at",
        )
    }
    result.update({
        "rows": _parse_docx_typed_table(next(tables)),
        "risk_records": _parse_docx_typed_table(next(tables)),
        "propagation": None,
    })
    propagation_rows = _parse_docx_typed_table(next(tables))
    result["propagation"] = propagation_rows[0] if propagation_rows else None
    result.update({
        "evidence_summary": _parse_docx_typed_table(next(tables)),
        "decision_summary": _parse_docx_typed_table(next(tables)),
        "unresolved_items": _parse_docx_typed_table(next(tables)),
        "version_manifest": manifest["version_manifest"],
        "audit_summary": manifest["audit_summary"],
    })
    return result


def _semantic_json(snapshot) -> dict[str, object]:
    body = orjson.loads(CanonicalJsonExporter().render(snapshot))
    return body


def test_json_xlsx_docx_share_all_snapshot_semantics() -> None:
    revision = make_fmea_revision(
        unresolved_items=(make_readiness_issue(code="missing-review", severity="blocking", evidence_ids=("ev-1",)),)
    )
    snapshot = make_normalized_snapshot(
        revision=revision,
        rows=2,
        risk_records=(
            {"assessment_id": "assessment-1", "status": "confirmed", "rpn": 12},
            {"assessment_id": "assessment-2", "status": "proposed", "rpn": 6},
        ),
        propagation={"graph_revision_id": "graph-1", "edges": [{"edge_id": "edge-1", "evidence_ids": ["ev-1"]}]},
        evidence_summary=({"pack_id": "pack-1", "evidence_count": 2, "evidence_ids": ["ev-1", "ev-2"]},),
        decision_summary=({"decision_id": "decision-1", "action": "accept", "actor": "reviewer-1"},),
        version_manifest={
            "schema_id": "graphrag.fmea.v1",
            "domain_pack": {"id": "fuel-combustion", "version": "1.0.0", "hash": "a" * 64},
            "template": {"id": "fuel-fmea", "version": "1.0.0", "hash": "b" * 64},
        },
        audit_summary={"event_count": 3, "last_hash": "c" * 64},
    )

    json_view = _semantic_json(snapshot)
    xlsx_view = _parse_xlsx(XlsxFmeaExporter().render(snapshot))
    docx_view = _parse_docx(DocxFmeaExporter().render(snapshot))

    assert json_view == xlsx_view == docx_view


def test_empty_optional_parts_round_trip_without_fabrication() -> None:
    snapshot = make_normalized_snapshot(
        revision=make_fmea_revision(unresolved_items=()),
        risk_records=(),
        propagation=None,
        evidence_summary=(),
        decision_summary=(),
    )

    expected = _semantic_json(snapshot)
    assert _parse_xlsx(XlsxFmeaExporter().render(snapshot)) == expected
    assert _parse_docx(DocxFmeaExporter().render(snapshot)) == expected


def test_draft_marker_is_visible_in_all_formats_and_absent_from_published() -> None:
    snapshot = make_normalized_snapshot()
    rendered = (
        XlsxFmeaExporter(draft_preview=True).render(snapshot),
        DocxFmeaExporter(draft_preview=True).render(snapshot),
    )
    published = (
        XlsxFmeaExporter().render(snapshot),
        DocxFmeaExporter().render(snapshot),
    )
    xlsx_text = "\n".join(
        str(cell.value)
        for row in openpyxl.load_workbook(io.BytesIO(rendered[0]))["Manifest"].iter_rows()
        for cell in row
    )
    docx_text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(rendered[1])).paragraphs)
    published_text = "\n".join([
        *(
            str(cell.value)
            for row in openpyxl.load_workbook(io.BytesIO(published[0]))["Manifest"].iter_rows()
            for cell in row
        ),
        *(paragraph.text for paragraph in Document(io.BytesIO(published[1])).paragraphs),
    ])
    assert MARKER in xlsx_text and MARKER in docx_text
    assert MARKER not in published_text


def test_repeated_render_preserves_semantic_identity_and_snapshot() -> None:
    snapshot = make_normalized_snapshot(row_payload={"row_id": "row-1", "unicode": "燃烧室 🔥"})
    before = _semantic_json(snapshot)

    first_xlsx = _parse_xlsx(XlsxFmeaExporter().render(snapshot))
    second_xlsx = _parse_xlsx(XlsxFmeaExporter().render(snapshot))
    first_docx = _parse_docx(DocxFmeaExporter().render(snapshot))
    second_docx = _parse_docx(DocxFmeaExporter().render(snapshot))

    assert first_xlsx == second_xlsx == first_docx == second_docx == before
    assert _semantic_json(snapshot) == before
