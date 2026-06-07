from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_external_evidence_closeout_checklist.py"


def load_closeout_module():
    spec = importlib.util.spec_from_file_location(
        "build_challenge_cup_external_evidence_closeout_checklist", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_builds_external_evidence_closeout_checklist_for_day_of_execution(tmp_path: Path) -> None:
    module = load_closeout_module()
    module.configure_paths(tmp_path)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_external_evidence_closeout_checklist"
    assert payload["status"] == "ready_for_real_external_evidence_closeout"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["required_before_goal_completion"] == ["expert_feedback", "timed_rehearsal"]
    assert payload["day_of_execution_owner"] == "project lead"
    assert "no award guarantee" in payload["boundary"]

    items = {item["check_id"]: item for item in payload["closeout_items"]}
    assert list(items) == [
        "package_preflight_clean",
        "expert_feedback_source_ready",
        "expert_feedback_archived",
        "timed_rehearsal_source_ready",
        "timed_rehearsal_archived",
        "hard_evidence_ledger_rebuilt",
        "package_rebuilt_after_evidence",
        "readiness_gate_rerun",
        "submission_archive_verified",
        "goal_completion_gate_rerun",
        "final_acceptance_audit_refreshed",
    ]

    hard_evidence_steps = [
        item["check_id"] for item in payload["closeout_items"] if item["counts_as_hard_evidence"]
    ]
    assert hard_evidence_steps == ["expert_feedback_archived", "timed_rehearsal_archived"]

    for item in payload["closeout_items"]:
        assert item["owner"]
        assert item["phase"]
        assert item["evidence_category"]
        assert item["proof_required"]
        assert item["command"]
        assert item["expected_after_step"]
        assert item["acceptance_signal"]
        assert item["cannot_substitute"]
        assert item["does_not_claim_award_or_completion"] is True
        assert "fake" not in item["acceptance_signal"].lower()

    assert "record_challenge_cup_hard_evidence.py expert_feedback" in items["expert_feedback_archived"]["command"]
    assert "real expert feedback source attachment" in items["expert_feedback_archived"]["proof_required"]
    assert "source_sha256" in items["expert_feedback_archived"]["acceptance_signal"]
    assert "run_challenge_cup_timed_rehearsal.py" in items["timed_rehearsal_archived"]["command"]
    assert "real timed rehearsal timer or observer attachment" in items["timed_rehearsal_archived"]["proof_required"]
    assert "timing_acceptance_pass=true" in items["timed_rehearsal_archived"]["acceptance_signal"]
    assert "hard_evidence_collected_pending_review" in items["hard_evidence_ledger_rebuilt"]["acceptance_signal"]
    assert "hard_evidence_complete" not in items["hard_evidence_ledger_rebuilt"]["acceptance_signal"]
    assert "Status: `pass`" in items["goal_completion_gate_rerun"]["acceptance_signal"]
    assert "completion_claim_allowed=True" in items["goal_completion_gate_rerun"]["acceptance_signal"]

    output_json = (
        tmp_path
        / "docs"
        / "challenge_cup"
        / "reproducibility"
        / "external_evidence_closeout_checklist.json"
    )
    output_md = (
        tmp_path
        / "docs"
        / "challenge_cup"
        / "reproducibility"
        / "external_evidence_closeout_checklist.md"
    )
    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "External Evidence Closeout Checklist" in markdown
    assert "day-of closeout" in markdown
    assert "real expert feedback" in markdown
    assert "real timed rehearsal" in markdown
    assert "source_sha256" in markdown
    assert "timing_acceptance_pass=true" in markdown
    assert "hard_evidence_collected_pending_review" in markdown
    assert "hard_evidence_complete" not in markdown
    assert "completion_claim_allowed=True" in markdown
    assert "no award guarantee" in markdown
    assert "does_not_satisfy_goal_completion=True" in markdown
