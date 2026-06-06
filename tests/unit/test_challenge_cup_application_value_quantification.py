from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_application_value_quantification.py"


EXPECTED_RECORD_IDS = [
    "demo-maint-thresholds-076",
    "demo-structure-fault-130",
    "demo-gt07-fault-021",
    "demo-gt07-repair-022",
    "demo-gt07-manual-023",
]
EXPECTED_STAGE_IDS = [
    "threshold_screening",
    "mechanism_explanation",
    "case_symptom",
    "repair_result",
    "disposition_recommendation",
]


def load_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_application_value_quantification", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_application_value_quantification_builds_auditable_local_evidence(tmp_path, monkeypatch) -> None:
    module = load_module()
    output_json = tmp_path / "application_value_quantification.json"
    output_md = tmp_path / "application_value_quantification.md"
    monkeypatch.setattr(module, "OUTPUT_JSON", output_json)
    monkeypatch.setattr(module, "OUTPUT_MD", output_md)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_application_value_quantification"
    assert payload["status"] == "application_value_quantified_no_external_validation_claim"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["external_validation_claimed"] is False
    assert payload["source_browser_smoke"] == "docs/challenge_cup/reproducibility/browser_demo_smoke_report.json"
    assert payload["source_application_validation_report"] == (
        "docs/challenge_cup/reproducibility/application_validation_report.md"
    )
    assert payload["collection"] == "gas_turbine_ocr_demo_snapshot"
    assert payload["retrieval_latency_ms"] == 41.8
    assert payload["returned_record_count"] == 5
    assert payload["visible_record_count"] == 5
    assert payload["indexed_chunks"] == 2655
    assert payload["indexed_tokens"] == 1185989
    assert payload["evidence_chain_stage_count"] == 5
    assert payload["evidence_chain_complete"] is True
    assert [stage["stage_id"] for stage in payload["evidence_chain"]] == EXPECTED_STAGE_IDS
    assert [stage["record_id"] for stage in payload["evidence_chain"]] == EXPECTED_RECORD_IDS
    assert all(stage["visible"] is True for stage in payload["evidence_chain"])
    assert payload["workflow_contrast"]["manual_lookup_step_count"] == 5
    assert payload["workflow_contrast"]["system_result_step_count"] == 1
    assert payload["workflow_contrast"]["evidence_consolidation_ratio"] == 5.0
    assert payload["workflow_contrast"]["record_id_traceability"] is True
    assert {claim["claim_id"] for claim in payload["judge_value_claims"]} == {
        "practical_value",
        "review_efficiency",
        "risk_boundary",
    }
    assert "not a production validation" in payload["boundary"]
    assert "does not replace engineers" in payload["boundary"]
    assert "real expert feedback" in payload["boundary"]
    assert "real timed rehearsal" in payload["boundary"]
    assert "no external validation claim" in json.dumps(payload, ensure_ascii=False)

    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "Application Value Quantification" in markdown
    assert "GT-07" in markdown
    for record_id in EXPECTED_RECORD_IDS:
        assert record_id in markdown
    assert "41.8 ms" in markdown
    assert "5.0x evidence consolidation" in markdown
    assert "not a production validation" in markdown
