from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_defense_slide_traceability.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_defense_slide_traceability", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_defense_slide_traceability_binds_each_slide_to_evidence_and_boundaries() -> None:
    module = load_module()

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_defense_slide_traceability"
    assert payload["status"] == "defense_slide_traceability_ready_no_rehearsal_or_award_claim"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["award_guarantee_claimed"] is False
    assert payload["expert_approval_claimed"] is False
    assert payload["timed_rehearsal_completion_claimed"] is False
    assert payload["coverage_complete"] is True
    assert payload["slide_count"] == 10
    assert payload["covered_slide_count"] == 10
    assert payload["gaps"] == []

    slides = payload["slides"]
    assert [slide["slide_index"] for slide in slides] == list(range(1, 11))
    for slide in slides:
        assert slide["coverage_status"] == "covered"
        assert slide["title"]
        assert slide["rubric_dimensions"]
        assert len(slide["evidence_files"]) >= 2
        assert slide["judge_objection_ids"]
        assert slide["claim_ids"]
        assert slide["notes_anchor_terms"]
        assert slide["boundary"]
        assert all(str(path).startswith(("docs/", "evaluation/")) for path in slide["evidence_files"])

    assert payload["output_files"] == [
        "docs/challenge_cup/reproducibility/defense_slide_traceability.md",
        "docs/challenge_cup/reproducibility/defense_slide_traceability.json",
    ]
    assert "does not guarantee an award" in payload["boundary"]
    assert "does not claim expert approval" in payload["boundary"]
    assert "does not claim timed rehearsal completion" in payload["boundary"]
    assert "does not satisfy goal completion" in payload["boundary"]

    assert json.loads(module.OUTPUT_JSON.read_text(encoding="utf-8")) == payload
    markdown = module.OUTPUT_MD.read_text(encoding="utf-8")
    for term in [
        "Defense Slide Traceability",
        "slide 1",
        "slide 10",
        "no award guarantee",
        "timed rehearsal",
    ]:
        assert term in markdown
