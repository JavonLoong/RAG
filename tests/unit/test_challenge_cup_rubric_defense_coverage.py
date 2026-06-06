from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_rubric_defense_coverage.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_rubric_defense_coverage", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rubric_defense_coverage_binds_each_official_dimension_to_defense_assets() -> None:
    module = load_module()

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_rubric_defense_coverage"
    assert payload["status"] == "rubric_defense_coverage_ready_no_award_claim"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["award_guarantee_claimed"] is False
    assert payload["expert_approval_claimed"] is False
    assert payload["timed_rehearsal_completion_claimed"] is False
    assert payload["coverage_complete"] is True
    assert payload["dimension_count"] == 5
    assert payload["covered_dimension_count"] == 5
    assert payload["gaps"] == []

    expected_dimensions = {
        "academic_or_practical_value",
        "innovation",
        "completion",
        "defense_performance",
        "academic_norms_and_rigor",
    }
    dimensions = payload["dimensions"]
    assert expected_dimensions == {item["dimension_key"] for item in dimensions}
    for item in dimensions:
        assert item["coverage_status"] == "covered"
        assert item["official_source_ids"]
        assert len(item["evidence_files"]) >= 2
        assert item["judge_objection_ids"]
        assert item["claim_ids"]
        assert item["defense_assets"]
        assert item["boundary"]
        assert all(str(path).startswith(("docs/", "evaluation/")) for path in item["evidence_files"])

    assert payload["output_files"] == [
        "docs/challenge_cup/reproducibility/rubric_defense_coverage.md",
        "docs/challenge_cup/reproducibility/rubric_defense_coverage.json",
    ]
    assert "does not guarantee an award" in payload["boundary"]
    assert "real expert feedback" in payload["boundary"]
    assert "real timed rehearsal" in payload["boundary"]

    assert json.loads(module.OUTPUT_JSON.read_text(encoding="utf-8")) == payload
    markdown = module.OUTPUT_MD.read_text(encoding="utf-8")
    for term in [
        "Rubric Defense Coverage",
        "academic_or_practical_value",
        "defense_performance",
        "academic_norms_and_rigor",
        "no award guarantee",
    ]:
        assert term in markdown
