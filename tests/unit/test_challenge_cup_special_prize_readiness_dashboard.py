from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "special_prize_readiness_dashboard.json"
REPORT_MD = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "special_prize_readiness_dashboard.md"


def test_special_prize_dashboard_maps_official_rubric_to_evidence_and_gaps() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_challenge_cup_special_prize_readiness_dashboard.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "special_prize_readiness_dashboard.md" in result.stdout
    payload = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert payload["report_type"] == "challenge_cup_special_prize_readiness_dashboard"
    assert payload["status"] == "special_prize_review_ready_with_external_evidence_gaps"
    assert payload["no_award_guarantee"] is True
    assert payload["completion_claim_allowed"] is False
    assert payload["can_mark_goal_complete"] is False
    assert payload["official_basis"]["latest_public_result_source_id"] == "tsinghua_44th_2026"
    assert payload["official_basis"]["max_special_prize_count"] == 7
    assert payload["official_basis"]["may_be_vacant"] is True

    dimension_keys = {item["dimension_key"] for item in payload["rubric_readiness"]}
    assert {
        "academic_or_practical_value",
        "innovation",
        "completion",
        "defense_performance",
        "academic_norms_and_rigor",
    } <= dimension_keys
    for item in payload["rubric_readiness"]:
        assert item["evidence_files"]
        assert item["readiness_level"] in {"strong_evidence_linked", "ready_with_external_gap"}
        assert item["judge_message"]
        assert item["defense_action"]

    assert {risk["risk_id"] for risk in payload["top_risks"]} == {
        "expert_feedback",
        "timed_rehearsal",
        "award_overclaim",
    }
    assert "docs/challenge_cup/reproducibility/hard_evidence_action_pack.md" in payload["next_action_files"]
    assert "python scripts/check_challenge_cup_goal_completion.py" in payload["verification_commands"]

    markdown = REPORT_MD.read_text(encoding="utf-8")
    assert "Special Prize Readiness Dashboard" in markdown
    assert "special_prize_review_ready_with_external_evidence_gaps" in markdown
    assert "no_award_guarantee=True" in markdown
    assert "expert_feedback" in markdown
    assert "timed_rehearsal" in markdown
