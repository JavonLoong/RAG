from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "final_acceptance_audit.json"
REPORT_MD = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "final_acceptance_audit.md"


def test_final_acceptance_audit_summarizes_package_ready_but_goal_incomplete() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_challenge_cup_final_acceptance_audit.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "final_acceptance_audit.md" in result.stdout
    payload = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert payload["report_type"] == "challenge_cup_final_acceptance_audit"
    assert payload["status"] == "package_ready_awaiting_external_hard_evidence"
    assert payload["package_readiness"]["status"] == "pass"
    assert payload["package_readiness"]["passed"] == 56
    assert payload["package_readiness"]["total"] == 56
    assert payload["package_readiness"]["current_gate_count"] == 56
    assert payload["package_readiness"]["source_report_passed"] in {55, 56}
    assert payload["package_readiness"]["source_report_total"] in {55, 56}
    assert payload["submission_package_verifier"]["available"] is True
    assert payload["submission_package_verifier"]["archived"] is True
    assert payload["goal_completion"]["status"] == "fail"
    assert payload["goal_completion"]["completion_claim_allowed"] is False
    assert payload["can_submit_for_package_review"] is True
    assert payload["can_mark_goal_complete"] is False
    assert {item["category"] for item in payload["blocking_items"]} == {"expert_feedback", "timed_rehearsal"}
    assert "--confirm-real-feedback" in "\n".join(payload["next_required_actions"])
    assert "--confirm-real-rehearsal" in "\n".join(payload["next_required_actions"])

    markdown = REPORT_MD.read_text(encoding="utf-8")
    assert "Final Acceptance Audit" in markdown
    assert "package_ready_awaiting_external_hard_evidence" in markdown
    assert "verify_submission_package.py" in markdown
    assert "completion_claim_allowed=False" in markdown
    assert "--confirm-real-feedback" in markdown
    assert "--confirm-real-rehearsal" in markdown
