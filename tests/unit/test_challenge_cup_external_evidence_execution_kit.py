from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_external_evidence_execution_kit.py"


def load_execution_kit_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_external_evidence_execution_kit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_builds_external_evidence_execution_kit_without_claiming_completion(tmp_path: Path) -> None:
    module = load_execution_kit_module()
    module.configure_paths(tmp_path)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_external_evidence_execution_kit"
    assert payload["status"] == "ready_for_external_execution_handoff"
    assert payload["completion_claim_allowed"] is False
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["required_before_goal_completion"] == ["expert_feedback", "timed_rehearsal"]

    sequence = {item["step_id"]: item for item in payload["operator_sequence"]}
    assert list(sequence) == [
        "verify_package_ready",
        "record_expert_outreach",
        "record_rehearsal_schedule",
        "preflight_expert_feedback",
        "record_expert_feedback",
        "run_timed_rehearsal",
        "rebuild_package",
        "check_readiness_gate",
        "verify_submission_package",
        "check_goal_completion_gate",
        "refresh_final_audit",
    ]
    assert sequence["record_expert_outreach"]["counts_as_hard_evidence"] is False
    assert sequence["record_rehearsal_schedule"]["counts_as_hard_evidence"] is False
    assert sequence["record_expert_feedback"]["counts_as_hard_evidence"] is True
    assert sequence["run_timed_rehearsal"]["counts_as_hard_evidence"] is True
    for item in sequence.values():
        assert item["command"]
        assert item["human_proof_required"]
        assert item["expected_after_step"]
        assert item["guardrail"]
        assert item["does_not_claim_award_or_completion"] is True

    packets = {item["packet_id"]: item for item in payload["execution_packets"]}
    assert set(packets) == {"expert_feedback_review", "timed_rehearsal_observer"}
    assert packets["expert_feedback_review"]["hard_evidence_category"] == "expert_feedback"
    assert packets["timed_rehearsal_observer"]["hard_evidence_category"] == "timed_rehearsal"

    for packet in packets.values():
        assert packet["owner"]
        assert packet["handoff_file"]
        assert packet["attachment_files"]
        assert packet["execution_steps"]
        assert packet["done_when"]
        assert packet["recording_commands"]
        assert packet["source_integrity_guardrails"]
        assert "source_sha256" in "\n".join(packet["source_integrity_guardrails"])
        assert "source attachment" in "\n".join(packet["source_integrity_guardrails"])
        assert packet["acceptance_gate"].startswith("hard_evidence_ledger.categories.")
        assert packet["does_not_satisfy_goal_completion"] is True

    assert "record_challenge_cup_hard_evidence.py expert_feedback" in "\n".join(
        packets["expert_feedback_review"]["recording_commands"]
    )
    assert "preflight_challenge_cup_hard_evidence.py expert_feedback" in "\n".join(
        packets["expert_feedback_review"]["recording_commands"]
    )
    assert "--confirm-real-feedback" in "\n".join(packets["expert_feedback_review"]["recording_commands"])
    assert "run_challenge_cup_timed_rehearsal.py" in "\n".join(
        packets["timed_rehearsal_observer"]["recording_commands"]
    )
    assert "preflight_challenge_cup_hard_evidence.py timed_rehearsal" in "\n".join(
        packets["timed_rehearsal_observer"]["recording_commands"]
    )
    assert any(
        "record_challenge_cup_hard_evidence.py timed_rehearsal" in command
        and "--confirm-real-rehearsal" in command
        for command in packets["timed_rehearsal_observer"]["recording_commands"]
    )
    command_text = "\n".join(
        [item["command"] for item in payload["operator_sequence"]]
        + [
            command
            for packet in packets.values()
            for command in packet["recording_commands"]
        ]
    )
    assert "&&" not in command_text
    assert "2026-06-06" not in command_text
    assert "20260606" not in command_text
    for placeholder in [
        "<real-outreach-id>",
        "<real-sent-date-yyyy-mm-dd>",
        "<real-followup-due-date-yyyy-mm-dd>",
        "<real-review-date-yyyy-mm-dd>",
        "<real-rehearsal-schedule-id>",
        "<real-scheduled-date-yyyy-mm-dd>",
        "<real-rehearsal-id>",
        "<real-rehearsal-date-yyyy-mm-dd>",
    ]:
        assert placeholder in command_text

    output_dir = tmp_path / "docs" / "challenge_cup" / "reproducibility"
    output_json = output_dir / "external_evidence_execution_kit.json"
    output_md = output_dir / "external_evidence_execution_kit.md"
    expert_handoff = output_dir / "external_evidence_execution_kit" / "expert_review_handoff.md"
    observer_sheet = output_dir / "external_evidence_execution_kit" / "timed_rehearsal_observer_sheet.md"

    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    assert expert_handoff.exists()
    assert observer_sheet.exists()

    markdown = output_md.read_text(encoding="utf-8")
    assert "External Evidence Execution Kit" in markdown
    assert "Operator Sequence" in markdown
    assert "verify_package_ready" in markdown
    assert "record_expert_feedback" in markdown
    assert "run_timed_rehearsal" in markdown
    assert "does_not_satisfy_goal_completion=True" in markdown
    assert "source_sha256" in markdown
    assert "source attachment" in markdown
    assert "\u4e0d\u4f2a\u9020" in markdown
    assert "\u771f\u5b9e\u4e13\u5bb6\u53cd\u9988" in markdown
    assert "\u771f\u5b9e\u8ba1\u65f6\u5f69\u6392" in markdown

    for handoff in (expert_handoff, observer_sheet):
        handoff_text = handoff.read_text(encoding="utf-8")
        assert "source_sha256" in handoff_text
        assert "source attachment" in handoff_text
