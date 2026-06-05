from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_challenge_cup_goal_completion.py"
REPORT = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "goal_completion_report.md"


def load_goal_module():
    spec = importlib.util.spec_from_file_location("check_challenge_cup_goal_completion", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_goal_completion_gate_fails_until_real_hard_evidence_is_archived() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_challenge_cup_goal_completion.py"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 1
    assert "Status: fail" in result.stdout
    report = REPORT.read_text(encoding="utf-8")
    assert "Status: `fail`" in report
    assert "expert_feedback" in report
    assert "timed_rehearsal" in report
    assert "completion_claim_allowed=False" in report
    assert "不能标记目标完成" in report


def test_goal_completion_gate_passes_with_ready_package_and_complete_hard_evidence(tmp_path: Path) -> None:
    module = load_goal_module()
    repro = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    expert_source = repro / "hard_evidence" / "expert_feedback" / "advisor-a.txt"
    expert_meta = repro / "hard_evidence" / "expert_feedback" / "advisor-a.json"
    rehearsal_source = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.txt"
    rehearsal_meta = repro / "hard_evidence" / "timed_rehearsal" / "rehearsal-1.json"
    for path in (expert_source, expert_meta, rehearsal_source, rehearsal_meta):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("real evidence", encoding="utf-8")
    (repro / "readiness_gate_report.md").write_text(
        "# Challenge Cup Readiness Gate\n\n- Status: `pass`\n- Passed: 30/30\n",
        encoding="utf-8",
    )
    ledger = {
        "report_type": "challenge_cup_hard_evidence_ledger",
        "status": "hard_evidence_collected_pending_review",
        "completion_claim_allowed": True,
        "required_before_goal_completion": ["expert_feedback", "timed_rehearsal"],
        "categories": {
            "expert_feedback": {
                "required_min_count": 1,
                "collected_count": 2,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
                ],
            },
            "timed_rehearsal": {
                "required_min_count": 1,
                "collected_count": 2,
                "evidence_files": [
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
                    "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
                ],
            },
        },
        "raw_evidence_files": [
            "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.json",
            "docs/challenge_cup/reproducibility/hard_evidence/expert_feedback/advisor-a.txt",
            "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.json",
            "docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal/rehearsal-1.txt",
        ],
    }
    (repro / "hard_evidence_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    payload = module.write_report(tmp_path)

    assert payload["status"] == "pass"
    report = (repro / "goal_completion_report.md").read_text(encoding="utf-8")
    assert "Status: `pass`" in report
    assert "真实专家反馈" in report
    assert "真实计时彩排" in report
