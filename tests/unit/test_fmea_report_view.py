from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from fmea_governance_fixtures import make_fmea_revision, make_normalized_snapshot
from test_fmea_snapshot_contracts import _marked_publication_body_source

from core_domain.fmea.errors import FmeaDomainError
from fmea_application.snapshot_contracts import build_normalized_snapshot

TEMPLATE_HASH = "a" * 64


def _implementation():
    try:
        from fmea_application.report_view import FmeaReportView, build_report_view
    except ModuleNotFoundError as exc:
        pytest.fail(f"Task 3 report view is missing: {exc}")
    return FmeaReportView, build_report_view


def _layout(*columns: dict[str, object]) -> dict[str, object]:
    return {
        "template_identity": {
            "template_id": "fuel-fmea",
            "version": "1.0.0",
            "template_hash": TEMPLATE_HASH,
        },
        "columns": columns,
    }


def _snapshot(*, layout: dict[str, object] | None, row: dict[str, object], risk_records=(), refs=()) -> object:
    source = _marked_publication_body_source()
    if layout is not None:
        identity = layout["template_identity"]
        revision = make_fmea_revision(
            template_identities=(
                (
                    identity["template_id"],
                    identity["version"],
                    identity["template_hash"],
                ),
            )
        )
        source = replace(source, revision=revision, publication_revision_hash=revision.revision_hash)
    manifest: dict[str, object] = {
        "body_schema_version": "graphrag.fmea.body.v1",
        "template_identities": source.revision.template_identities,
    }
    if layout is not None:
        manifest["report_layout"] = layout
    return build_normalized_snapshot(
        replace(
            source,
            rows=({**source.rows[0], **row},),
            risk_records=risk_records,
            evidence_summary=({**source.evidence_summary[0], "refs": refs},),
            version_manifest=manifest,
        )
    )


def test_build_report_view_uses_pinned_labels_and_order_without_mutating_snapshot() -> None:
    FmeaReportView, build_report_view = _implementation()
    row = {
        "row_id": "row-1",
        "failure_mode": "low pressure",
        "causes": ("blocked filter", "cold start"),
        "effects": ("unstable flame",),
    }
    layout = _layout(
        {
            "field_key": "effects",
            "label": "影响",
            "value_type": "string[]",
            "value_path": ("row", "effects"),
        },
        {
            "field_key": "failure_mode",
            "label": "故障模式",
            "value_type": "string",
            "value_path": ("row", "failure_mode"),
        },
        {
            "field_key": "causes",
            "label": "原因",
            "value_type": "string[]",
            "value_path": ("row", "causes"),
        },
    )
    snapshot = _snapshot(layout=layout, row=row)
    original_snapshot_hash = snapshot.snapshot_hash

    view = build_report_view(snapshot)

    assert isinstance(view, FmeaReportView)
    assert [(column.field_key, column.label) for column in view.columns] == [
        ("effects", "影响"),
        ("failure_mode", "故障模式"),
        ("causes", "原因"),
    ]
    assert view.rows[0]["failure_mode"] == snapshot.rows[0]["failure_mode"]
    assert view.rows[0]["effects"] == ("unstable flame",)
    assert snapshot.snapshot_hash == original_snapshot_hash


def test_build_report_view_keeps_long_evidence_and_decimal_extensions_in_details() -> None:
    _, build_report_view = _implementation()
    long_quote = "完整证据文本。" * 4000
    refs = tuple(
        {
            "evidence_id": f"evidence-{index}",
            "document_id": f"document-{index}",
            "document_version": "1",
            "content_hash": "c" * 64,
            "evidence_hash": "d" * 64,
            "locator": {"page": index + 1, "span": 1},
            "quote": long_quote if index == 0 else "完整引用",
            "source_type": "primary_document",
            "source_trust": "trusted",
        }
        for index in range(80)
    )
    long_evidence = tuple(ref["evidence_id"] for ref in refs)
    row = {
        "row_id": "row-1",
        "failure_mode": "low pressure",
        "causes": ("blocked filter", "cold start"),
        "effects": ("unstable flame",),
        "field_evidence": ({"field_key": "causes", "evidence_ids": long_evidence},),
        "field_support": ({"field_key": "causes", "support_status": "supported"},),
        "extension_values": (
            {"field_key": "fuel.pressure_drop", "value_type": "decimal", "value": "48.2000"},
            {"field_key": "vendor.unrecognized", "value_type": "string", "value": "keep me"},
        ),
    }
    layout = _layout(
        {
            "field_key": "failure_mode",
            "label": "故障模式",
            "value_type": "string",
            "value_path": ("row", "failure_mode"),
        },
        {
            "field_key": "fuel.pressure_drop",
            "label": "压降",
            "value_type": "decimal",
            "value_path": ("extension_values", "fuel.pressure_drop"),
        },
    )

    snapshot = _snapshot(layout=layout, row=row, refs=refs)
    view = build_report_view(snapshot)

    assert view.rows[0]["fuel.pressure_drop"] == "48.2000"
    assert view.details[0]["causes"] == ("blocked filter", "cold start")
    assert view.details[0]["field_evidence"][0]["evidence_ids"] == long_evidence
    assert view.details[0]["evidence_summary"] == snapshot.evidence_summary
    assert view.details[0]["evidence_summary"][0]["refs"][0]["quote"] == long_quote
    assert len(view.details[0]["evidence_summary"][0]["refs"]) == 80
    assert view.details[0]["extension_values"][1]["field_key"] == "vendor.unrecognized"
    assert view.details[0]["extension_values"] == snapshot.rows[0]["extension_values"]


def test_report_view_does_not_turn_non_rpn_scores_into_rpn() -> None:
    _, build_report_view = _implementation()
    row = {
        "row_id": "row-1",
        "failure_mode": "unsafe state",
    }
    layout = _layout({
        "field_key": "failure_mode",
        "label": "故障模式",
        "value_type": "string",
        "value_path": ("row", "failure_mode"),
    })

    risk = {
        "assessment_id": "risk-1",
        "assessment_hash": "c" * 64,
        "workspace_id": "ws-1",
        "row_id": "row-1",
        "source_record_version": 1,
        "evidence_pack_id": "pack-1",
        "domain_pack_id": "generic-domain",
        "domain_pack_version": "1.0.0",
        "rule_pack_id": "qualitative-matrix",
        "rule_pack_version": "1.0.0",
        "status": "confirmed",
        "dimensions": (),
        "derived": {"priority": "high", "evidence_ids": ()},
        "proposal_id": None,
        "invalidated_reason": None,
        "record_version": 1,
        "confirmation_basis": None,
    }
    snapshot = _snapshot(layout=layout, row=row, risk_records=(risk,))
    view = build_report_view(snapshot)

    assert view.details[0]["risk_records"] == snapshot.risk_records
    assert "rpn" not in view.rows[0]
    assert "rpn" not in view.details[0]["risk_records"][0]["derived"]


def test_build_report_view_rejects_non_whitelisted_value_path() -> None:
    _, build_report_view = _implementation()
    row = {"row_id": "row-1", "failure_mode": "low pressure"}
    layout = _layout({
        "field_key": "failure_mode",
        "label": "故障模式",
        "value_type": "string",
        "value_path": "../failure_mode",
    })

    with pytest.raises(FmeaDomainError, match="report layout"):
        build_report_view(_snapshot(layout=layout, row=row))


def test_markerless_snapshot_uses_summary_only_compatibility_view() -> None:
    _, build_report_view = _implementation()
    snapshot = make_normalized_snapshot(
        rows=({"row_id": "row-1", "failure_mode": "legacy summary"},),
        version_manifest={"schema_id": "graphrag.fmea.v1"},
    )

    view = build_report_view(snapshot)

    assert [(column.field_key, column.value_type) for column in view.columns] == [
        ("publication_id", "string"),
        ("revision_id", "string"),
        ("row_count", "integer"),
        ("snapshot_hash", "string"),
    ]
    assert set(view.rows[0]) == {"publication_id", "revision_id", "row_count", "snapshot_hash"}
    assert view.details == ()


def test_saved_task2_body_without_layout_uses_stable_keys():
    _, build_report_view = _implementation()
    snapshot = _snapshot(layout=None, row={"failure_mode": "saved body"})
    view = build_report_view(snapshot)
    assert {column.field_key for column in view.columns} >= {"failure_mode", "causes", "effects"}
    assert all(column.label == column.field_key for column in view.columns)
    assert view.rows[0]["failure_mode"] == "saved body"


def _compiled_template(**schema_overrides):
    from structured_output_application.compiler import TemplateCompiler
    from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

    return TemplateCompiler(schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source).compile({
        "template": {
            "id": "report-test",
            "version": "1.0.0",
            "title": "报告",
            "description": "Pinned report",
            "domain_tags": ["fmea"],
            "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "failure_mode": {"type": "string", "title": "故障模式"},
                "causes": {"type": "array", "items": {"type": "string"}},
                "fuel.pressure_drop": {"type": "number", "title": "压降"},
            },
            **schema_overrides,
        },
        "evidence_bindings": [],
        "source_mappings": {"failure_mode": "causes"},
    })


def test_layout_compiler_uses_titles_and_canonical_order_not_import_mappings():
    _implementation()
    from fmea_application.report_view import compile_report_layout

    template = _compiled_template()
    layout = compile_report_layout(template.canonical_json, (("report-test", "1.0.0", template.template_hash),))
    assert [(c["field_key"], c["label"]) for c in layout["columns"]] == [
        ("causes", "causes"),
        ("failure_mode", "故障模式"),
        ("fuel.pressure_drop", "压降"),
    ]
    assert layout["columns"][2]["value_path"] == ("extension_values", "fuel.pressure_drop")


@pytest.mark.parametrize("identities", [(), (("one", "1", "a" * 64), ("two", "1", "b" * 64))])
def test_layout_compiler_blocks_missing_or_ambiguous_template(identities):
    _implementation()
    from fmea_application.report_view import compile_report_layout

    with pytest.raises(FmeaDomainError, match="INCOMPLETE"):
        compile_report_layout(_compiled_template().canonical_json, identities)


def test_layout_compiler_recomputes_hash_instead_of_trusting_identity():
    _implementation()
    from fmea_application.report_view import compile_report_layout

    template = _compiled_template()
    with pytest.raises(FmeaDomainError, match="report layout"):
        compile_report_layout(
            template.canonical_json.replace("故障模式", "伪造标签"), (("report-test", "1.0.0", template.template_hash),)
        )


def test_boolean_property_and_array_item_schemas_use_lossless_generic_types():
    from fmea_application.report_view import compile_report_layout

    template = _compiled_template(properties={"failure_mode": True, "causes": {"type": "array", "items": True}})
    layout = compile_report_layout(template.canonical_json, (("report-test", "1.0.0", template.template_hash),))
    assert [(column["field_key"], column["value_type"]) for column in layout["columns"]] == [
        ("causes", "array"),
        ("failure_mode", "json"),
    ]


def test_report_details_keep_original_row_even_when_unknown_fields_collide():
    _, build_report_view = _implementation()
    snapshot = _snapshot(
        layout=None,
        row={
            "risk_records": {"vendor_annotation": "keep this"},
            "propagation": {"vendor_annotation": "keep that"},
        },
    )
    view = build_report_view(snapshot)
    assert view.details[0]["row"] == snapshot.rows[0]
    assert view.details[0]["row"]["risk_records"] == {"vendor_annotation": "keep this"}


def test_report_view_and_compiled_layout_are_deeply_immutable():
    from fmea_application.report_view import build_report_view, compile_report_layout

    template = _compiled_template()
    layout = compile_report_layout(template.canonical_json, (("report-test", "1.0.0", template.template_hash),))
    with pytest.raises(TypeError):
        layout["columns"][0]["label"] = "changed"
    view = build_report_view(_snapshot(layout=None, row={}))
    with pytest.raises(FrozenInstanceError):
        view.columns = ()
    with pytest.raises(FrozenInstanceError):
        view.columns[0].label = "changed"
    with pytest.raises(TypeError):
        view.rows[0]["failure_mode"] = "changed"
    with pytest.raises(TypeError):
        view.details[0]["evidence_summary"][0]["refs"] = ()


@pytest.mark.parametrize(
    "path",
    [
        ("row", "effects"),
        ("extension_values", "fuel", "pressure_drop"),
        ("row", "__class__"),
        ("row", "failure_mode", "upper"),
        "failure_mode.upper()",
    ],
)
def test_layout_validator_rejects_remapping_or_executable_paths(path):
    from fmea_application.report_view import validate_report_layout

    layout = _layout({"field_key": "failure_mode", "label": "故障模式", "value_type": "string", "value_path": path})
    with pytest.raises(FmeaDomainError, match="report layout"):
        validate_report_layout(layout, (("fuel-fmea", "1.0.0", TEMPLATE_HASH),))


def test_template_labels_do_not_remap_unavailable_fields_or_change_existing_layout():
    from fmea_application.report_view import compile_report_layout

    original = _compiled_template(
        properties={
            "causes": {"type": "array"},
            "component": {"type": "string", "title": "部件"},
        }
    )
    identities = (("report-test", "1.0.0", original.template_hash),)
    layout = compile_report_layout(original.canonical_json, identities)
    upgraded = _compiled_template(properties={"causes": {"type": "array", "title": "新标题"}})
    compile_report_layout(upgraded.canonical_json, (("report-test", "1.0.0", upgraded.template_hash),))
    assert layout["columns"][0]["label"] == "causes"
    assert layout["columns"][1]["value_path"] == ("unavailable", "component")


def test_compiling_changed_template_cannot_change_saved_body_view():
    from fmea_application.report_view import build_report_view, compile_report_layout

    template = _compiled_template()
    layout = compile_report_layout(template.canonical_json, (("report-test", "1.0.0", template.template_hash),))
    snapshot = _snapshot(layout=layout, row={"failure_mode": "original failure", "causes": ("cause A", "cause B")})
    original_hash = snapshot.snapshot_hash
    view = build_report_view(snapshot)
    changed = _compiled_template(properties={"causes": {"type": "array", "title": "Changed label"}})
    compile_report_layout(changed.canonical_json, (("report-test", "1.0.0", changed.template_hash),))

    assert build_report_view(snapshot) == view
    assert snapshot.snapshot_hash == original_hash
    assert view.rows[0]["failure_mode"] == "original failure"
    assert view.rows[0]["causes"] == ("cause A", "cause B")
    assert next(c.label for c in view.columns if c.field_key == "failure_mode") == "故障模式"


@pytest.mark.parametrize("identity", [("wrong-id", "1.0.0"), ("report-test", "2.0.0")])
def test_layout_compiler_binds_id_and_version_in_addition_to_hash(identity):
    from fmea_application.report_view import compile_report_layout

    template = _compiled_template()
    with pytest.raises(FmeaDomainError, match="report layout"):
        compile_report_layout(template.canonical_json, ((*identity, template.template_hash),))
