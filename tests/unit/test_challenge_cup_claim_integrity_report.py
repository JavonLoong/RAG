from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_claim_integrity_report.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_claim_integrity_report", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_claim_integrity_report_binds_defense_claims_to_evidence_without_overclaim(
    tmp_path, monkeypatch
) -> None:
    module = load_module()
    output_json = tmp_path / "claim_integrity_report.json"
    output_md = tmp_path / "claim_integrity_report.md"
    monkeypatch.setattr(module, "OUTPUT_JSON", output_json)
    monkeypatch.setattr(module, "OUTPUT_MD", output_md)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_claim_integrity_report"
    assert payload["status"] == "claim_integrity_verified_no_award_or_external_claim"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["award_guarantee_claimed"] is False
    assert payload["expert_approval_claimed"] is False
    assert payload["timed_rehearsal_completion_claimed"] is False
    assert payload["production_deployment_claimed"] is False
    assert payload["all_claims_evidence_bound"] is True
    assert payload["forbidden_hit_count"] == 0
    assert payload["claim_count"] >= 8
    assert payload["failures"] == []

    claim_ids = {claim["claim_id"] for claim in payload["claims"]}
    assert {
        "package_review_ready",
        "graphrag_innovation_bounded",
        "evaluation_transparency",
        "application_value_bounded",
        "defense_demo_fallback_ready",
        "external_hard_evidence_not_closed",
        "special_prize_competition_argument",
        "human_decision_boundary",
    } <= claim_ids

    for claim in payload["claims"]:
        assert claim["evidence_files"], claim["claim_id"]
        assert claim["boundary"], claim["claim_id"]
        assert claim["forbidden_overclaim"], claim["claim_id"]

    assert "does not guarantee an award" in payload["boundary"]
    assert "does not claim expert approval" in payload["boundary"]
    assert payload["output_files"] == [
        "docs/challenge_cup/reproducibility/claim_integrity_report.md",
        "docs/challenge_cup/reproducibility/claim_integrity_report.json",
    ]

    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "Claim Integrity Report" in markdown
    assert "claim_integrity_verified_no_award_or_external_claim" in markdown
    assert "package_review_ready" in markdown
    assert "special_prize_competition_argument" in markdown
