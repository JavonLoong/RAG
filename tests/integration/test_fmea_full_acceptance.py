from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_slice_module():
    root = Path(__file__).resolve().parents[2]
    source = root / "examples" / "fmea" / "full-acceptance" / "candidate_review_risk_slice.py"
    spec = importlib.util.spec_from_file_location("fmea_candidate_review_risk_slice", source)
    if spec is None or spec.loader is None:
        raise AssertionError("candidate/review/risk slice helper is not loadable")  # noqa: TRY003 - test invariant
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_candidate_review_risk_slice_records_confirmed_assessment(tmp_path: Path) -> None:
    module = _load_slice_module()
    result = module.run_candidate_review_risk(tmp_path)

    evidence = result.evidence
    assert result.row.record_version == 2
    assert result.assessment.source_record_version == result.row.record_version
    assert result.analysis.analysis_id == result.row.analysis_id
    assert result.evidence_pack.pack_id == result.row.evidence_pack_id
    assert set(evidence) == {
        "schema_version",
        "case_id",
        "scoring_rules",
        "evidence_packs",
        "candidates",
        "review_decisions",
        "risk_records",
        "audits",
        "outbox",
        "replays",
        "steps",
    }
    assert evidence["schema_version"] == "graphrag.fmea.connected-lifecycle.v1"
    assert evidence["case_id"] == "fuel-combustion"
    assert evidence["scoring_rules"]
    rule = evidence["scoring_rules"][0]
    assert {"rule_pack_id", "version", "score_min", "score_max"} <= set(rule)
    assert evidence["evidence_packs"][0]["pack_id"] == "fuel-evidence-1"
    assert evidence["candidates"][0]["row_id"] == "fuel-row-1"

    decisions = evidence["review_decisions"]
    assert decisions[0]["row"]["review_status"] == "accepted"
    assert decisions[0]["row"]["record_version"] == 2
    assert evidence["steps"][3]["after"]["origin_source_record_version"] == 1

    risk = evidence["risk_records"]
    assert {item["status"] for item in risk} == {"proposed", "confirmed"}
    confirmed = next(item for item in risk if item["status"] == "confirmed")
    assert confirmed["record_version"] == 2
    assert confirmed["derived"]["rpn"] == 8 * 3 * 4
    assert evidence["outbox"]
    assert {item["event_type"] for item in evidence["outbox"]} >= {"risk.proposed", "risk.confirmed"}

    assert evidence["audits"]
    assert {item["command"] for item in evidence["steps"]} == {
        "candidate.generate",
        "review.candidates.persist",
        "review.suggestion.start",
        "review.decision",
        "fmea.risk.propose",
        "fmea.risk.confirm",
    }
    assert all(
        set(step)
        == {
            "step_id",
            "command",
            "actor_id",
            "actor_type",
            "request_identity",
            "before",
            "after",
            "result_ids",
        }
        for step in evidence["steps"]
    )
    assert all(replay["same_persisted_result"] for replay in evidence["replays"])
    assert {replay["command"] for replay in evidence["replays"]} == {
        "review.decision",
        "fmea.risk.confirm",
    }
    assert all(
        replay["event_counts_before"] == replay["event_counts_after"]
        and {"audit_events", "outbox_events"} == set(replay["event_counts_before"])
        for replay in evidence["replays"]
    )

    serialized = json.dumps(evidence, sort_keys=True)
    for marker in ("raw_response", "provider_response", "resource_path"):
        assert marker not in serialized


def test_slice_helper_writes_only_evidence_without_a_full_manifest(tmp_path: Path) -> None:
    module = _load_slice_module()
    result = module.run_candidate_review_risk(tmp_path / "run")
    output = tmp_path / "evidence.json"

    result.write_evidence(output)

    assert json.loads(output.read_text(encoding="utf-8")) == result.evidence
    assert not (output.parent / "manifest.json").exists()


def test_full_acceptance_executes_connected_lifecycle(tmp_path: Path) -> None:
    from scripts import run_fmea_full_acceptance as runner
    from scripts.verify_fmea_full_acceptance import verify_acceptance_directory

    assert callable(getattr(runner, "run_full_acceptance", None)), "full runner is not implemented"
    result = runner.run_full_acceptance(output_root=tmp_path)
    verified = verify_acceptance_directory(result.artifact_dir)
    assert verified.passed, verified.error_code
    evidence = json.loads((result.artifact_dir / "evidence.json").read_text(encoding="utf-8"))
    fuel = next(case for case in evidence["cases"] if case["case_id"] == "fuel-combustion")
    assert fuel["coverage"] == "full_lifecycle"
    migrated = next(
        revision
        for revision in fuel["revisions"]
        if revision["revision_id"] == fuel["migration_results"][0]["child_revision_id"]
    )
    assert migrated["parent_revision_id"] == fuel["revisions"][0]["revision_id"]
    assert migrated["risk_versions"] == []
    assert migrated["propagation_graph_revision_id"] is None
    assert len(fuel["exports"]) == 6
    assert len(fuel["publications"]) == 2
    assert {item["command"] for item in fuel["steps"]} >= {
        "evidence.select",
        "candidate.generate",
        "review.decision",
        "fmea.risk.confirm",
        "fmea.propagation.review",
        "fmea.approval.decide",
        "fmea.publication.publish",
        "fmea.export.start",
        "fmea.template.import",
        "fmea.migration.confirm",
        "fmea.publication.supersede",
        "fmea.publication.withdraw",
    }
    assert all(value == 0 for value in result.summary.values())


def test_governance_uses_compiled_registry_identities(tmp_path: Path) -> None:
    from scripts.run_fmea_full_acceptance import _load_helper, run_candidate_review_risk
    from structured_output_application import TemplateCompiler
    from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

    source = run_candidate_review_risk(tmp_path)
    providers = _load_helper("governance_delivery_slice").PersistedProviders(tmp_path / "fmea.sqlite3", source, None)
    analysis = providers.get_analysis(source.analysis.analysis_id, source.evidence_pack.workspace_id)
    artifacts = providers.get_artifacts(source.analysis.analysis_id, source.evidence_pack.workspace_id, analysis)
    compiler = TemplateCompiler(schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source)
    root = Path(__file__).resolve().parents[2]
    expected = compiler.compile_path(
        root / "domain_packs/fuel-combustion/templates/fmea-propagation-hypothesis-1.0.0.yaml"
    )
    identity = next(item for item in artifacts.template_identities if item.artifact_id == "fmea-propagation-hypothesis")
    assert identity.content_hash == expected.template_hash
