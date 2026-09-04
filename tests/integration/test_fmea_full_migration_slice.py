from __future__ import annotations

# The test intentionally loads the hyphenated full-acceptance slices by path.
# ruff: noqa: I001, TRY003

import importlib.util
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from core_domain.fmea.governance import canonical_json_bytes
from fmea_application.migration_service import MigrationResult
from tests.unit.test_fmea_template_import_excel import _xlsx


ROOT = Path(__file__).resolve().parents[2]


def _load_slice(name: str):
    filename = {
        "candidate_review_risk": "candidate_review_risk_slice.py",
        "propagation": "propagation_slice.py",
    }.get(name, f"{name}.py")
    path = ROOT / "examples" / "fmea" / "full-acceptance" / filename
    module_name = f"task8_{name}"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_real_template_import_review_register_and_migration_replay(tmp_path: Path) -> None:
    """Run one real published-source chain, then check its bounded evidence guards."""

    candidate = _load_slice("candidate_review_risk").run_candidate_review_risk(tmp_path)
    propagation = _load_slice("propagation").run_propagation(
        database_path=tmp_path / "fmea.sqlite3",
        analysis=candidate.analysis,
        row=candidate.row,
        assessment=candidate.assessment,
        evidence_pack=candidate.evidence_pack,
        registry_root=tmp_path / "immutable-registries",
    )
    governance = _load_slice("governance_delivery_slice")
    connected = governance.GovernanceDeliveryRun(
        tmp_path / "fmea.sqlite3", candidate, propagation.graph, tmp_path
    )
    parent, _publication = connected.publish()
    # The main runner supplies its dedicated plain ``inputs/template.xlsx``;
    # do not feed the export-roundtrip workbook with print-area defined names.
    import_bytes = _xlsx(
        sheet_xml="""<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheetData><row r="1">
            <c r="A1" t="inlineStr"><is><t>failure_mode</t></is></c>
            <c r="B1" t="inlineStr"><is><t>legacy_criticality</t></is></c>
          </row></sheetData>
        </worksheet>"""
    )

    helper = _load_slice("migration_slice")
    migration = helper.run_migration(
        database_path=tmp_path / "fmea.sqlite3",
        source_revision=parent,
        registry_root=tmp_path / "immutable-registries",
        workspace_id=candidate.evidence_pack.workspace_id,
        import_bytes=import_bytes,
    )

    assert migration.child_revision.parent_revision_id == parent.revision_id
    assert migration.child_revision.parent_revision_hash == parent.revision_hash
    assert migration.child_revision.row_versions == parent.row_versions
    assert migration.child_revision.risk_versions == ()
    assert migration.child_revision.propagation_graph_revision_id is None
    assert migration.child_revision.propagation_graph_hash is None
    assert ("fuel-combustion-fmea", "2.0.0") in {
        (item[0], item[1]) for item in migration.child_revision.template_identities
    }

    evidence = migration.evidence
    assert evidence["template_drafts"][0]["status"] == "draft"
    assert evidence["template_drafts"][0]["structure"]
    draft = evidence["template_drafts"][0]
    assert draft["source_sha256"] == sha256(import_bytes).hexdigest()
    assert evidence["import_source"] == {
        "filename": "template.xlsx",
        "sha256": sha256(import_bytes).hexdigest(),
        "byte_length": len(import_bytes),
    }
    assert evidence["template_patch_decisions"][0]["action"] == "accepted"
    assert evidence["template_patch_decisions"][0]["actor_type"] == "human"
    assert evidence["registered_templates"][0]["version"] == "2.0.0"
    compiled = evidence["registered_templates"][0]["compiled"]
    properties = compiled["output_schema"]["properties"]
    assert {"item", "failure_mode", "effects", "legacy_criticality"} <= set(properties)
    assert compiled["source_mappings"] == {"legacy_criticality": "legacy_criticality"}
    assert evidence["migration_reports"][0]["mapped_fields"]
    assert evidence["migration_reports"][0]["dropped_fields"]
    assert evidence["migration_reports"][0]["unresolved_fields"] == []

    result = evidence["migration_results"][0]
    assert set(result) == {"migration_id", "child_revision_id", "report_hash", "replayed"}
    assert result["child_revision_id"] == migration.child_revision.revision_id
    assert len(evidence["revisions"]) == 1
    assert evidence["revisions"][0]["revision_id"] == migration.child_revision.revision_id
    assert evidence["revisions"][0]["risk_versions"] == []
    assert evidence["revisions"][0]["propagation_graph_revision_id"] is None
    assert evidence["invalidation_receipt"]["risk_invalidated"] is True
    assert evidence["invalidation_receipt"]["propagation_invalidated"] is True
    assert all(
        not (step["actor_type"] == "model" and ("confirm" in step["command"] or "approve" in step["command"]))
        for step in evidence["steps"]
    )
    assert all(replay["same_persisted_result"] for replay in evidence["replays"])
    assert all(replay["event_counts_before"] == replay["event_counts_after"] for replay in evidence["replays"])
    for replay in evidence["replays"]:
        assert "fmea_template_audit_events" in replay["event_counts_before"]
    confirmation = evidence["replays"][-1]
    assert confirmation["event_counts_after"]["fmea_template_audit_events"] == len(evidence["template_audits"])
    assert confirmation["first"]["replayed"] is False
    assert confirmation["replayed"]["replayed"] is True
    assert canonical_json_bytes(confirmation["replayed"]) == canonical_json_bytes(
        {**confirmation["first"], "replayed": True}
    )
    assert confirmation["child_revision_count"] == 1
    assert confirmation["migration_confirmation_count"] == 1

    # Exercise fail-closed evidence guards on the actual run's receipts; do not
    # rerun or replace the real repositories/services for each mutation.
    native_result = MigrationResult(**result)
    first = MigrationResult(**confirmation["first"])
    retry = MigrationResult(**confirmation["replayed"])
    counts = confirmation["event_counts_before"]
    helper._assert_confirmation_replay(first, retry, counts, counts)
    for changed in (
        {**confirmation["replayed"], "replayed": False},
        {**confirmation["replayed"], "report_hash": "0" * 64},
        {**confirmation["replayed"], "child_revision_id": "other-child"},
        {**confirmation["replayed"], "migration_id": "other-migration"},
    ):
        with pytest.raises(AssertionError, match="confirmation replay"):
            helper._assert_confirmation_replay(first, MigrationResult(**changed), counts, counts)
    with pytest.raises(AssertionError, match="confirmation replay"):
        helper._assert_confirmation_replay(retry, retry, counts, counts)
    with pytest.raises(AssertionError, match="confirmation replay"):
        helper._assert_confirmation_replay(
            first, retry, counts,
            {**counts, "fmea_template_audit_events": counts["fmea_template_audit_events"] + 1},
        )

    matching = [event for event in evidence["outbox"] if (
        event["event_type"] == "migration.completed"
        and event["workspace_id"] == parent.workspace_id
        and event["aggregate_type"] == "fmea_governance"
        and event["aggregate_id"] == native_result.child_revision_id
        and event["payload"]["migration_id"] == native_result.migration_id
        and event["payload"]["child_revision_id"] == native_result.child_revision_id
        and event["payload"]["report_hash"] == native_result.report_hash
    )]
    assert len(matching) == 1
    event = matching[0]
    assert evidence["invalidation_receipt"]["outbox_event_id"] == event["event_id"]
    assert event["payload"]["source_revision_id"] == parent.revision_id
    assert event["payload"]["source_revision_hash"] == parent.revision_hash
    assert event["payload"]["child_revision_hash"] == migration.child_revision.revision_hash
    bad_events = [
        {**event, key: "unrelated"}
        for key in ("workspace_id", "aggregate_type", "aggregate_id", "event_type")
    ] + [
        {**event, "payload": {**event["payload"], key: "unrelated"}}
        for key in (
            "migration_id", "child_revision_id", "report_hash", "source_revision_id",
            "source_revision_hash", "child_revision_hash",
        )
    ]
    assert helper._migration_completed_event(
        [*bad_events, event], parent, migration.child_revision, native_result
    ) == event
    for events in ([], [event, event], *([bad] for bad in bad_events)):
        with pytest.raises(AssertionError, match="exactly one migration.completed"):
            helper._migration_completed_event(events, parent, migration.child_revision, native_result)

    assert helper._import_source_receipt(draft, import_bytes) == evidence["import_source"]
    for changed_draft, changed_bytes in (
        ({**draft, "source_sha256": "0" * 64}, import_bytes),
        ({**draft, "source_filename": "unrelated.xlsx"}, import_bytes),
        (draft, import_bytes + b"extra"),
    ):
        with pytest.raises(AssertionError, match="import source"):
            helper._import_source_receipt(changed_draft, changed_bytes)
