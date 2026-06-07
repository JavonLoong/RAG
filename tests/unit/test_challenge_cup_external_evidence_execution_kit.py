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
    assert "timing_acceptance_pass" in sequence["run_timed_rehearsal"]["expected_after_step"]
    assert "rejected_metadata_records" in sequence["run_timed_rehearsal"]["expected_after_step"]
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
        assert packet["pre_hard_evidence_powershell_block"]
        assert packet["powershell_execution_block"]
        assert packet["source_integrity_guardrails"]
        assert "source_sha256" in "\n".join(packet["source_integrity_guardrails"])
        assert "source attachment" in "\n".join(packet["source_integrity_guardrails"])
        assert "must not be a JSON metadata file" in "\n".join(packet["source_integrity_guardrails"])
        assert packet["acceptance_gate"].startswith("hard_evidence_ledger.categories.")
        assert packet["does_not_satisfy_goal_completion"] is True
        powershell = "\n".join(packet["powershell_execution_block"])
        assert "Set-Location" in powershell
        assert str(tmp_path) in powershell
        assert ".\\.venv\\Scripts\\python.exe" in powershell
        assert "python .\\scripts" not in powershell
        python_lines = [
            line for line in packet["powershell_execution_block"] if ".\\.venv\\Scripts\\python.exe" in line
        ]
        guard_lines = [line for line in packet["powershell_execution_block"] if "$LASTEXITCODE" in line]
        assert len(guard_lines) == len(python_lines)
        assert all("exit $LASTEXITCODE" in line for line in guard_lines)
        assert "<" not in powershell
        assert ">" not in powershell
        pre_block = "\n".join(packet["pre_hard_evidence_powershell_block"])
        assert "Set-Location" in pre_block
        assert str(tmp_path) in pre_block
        assert ".\\.venv\\Scripts\\python.exe" in pre_block
        assert "python .\\scripts" not in pre_block
        pre_python_lines = [
            line for line in packet["pre_hard_evidence_powershell_block"] if ".\\.venv\\Scripts\\python.exe" in line
        ]
        pre_guard_lines = [line for line in packet["pre_hard_evidence_powershell_block"] if "$LASTEXITCODE" in line]
        assert len(pre_guard_lines) == len(pre_python_lines)
        assert all("exit $LASTEXITCODE" in line for line in pre_guard_lines)
        assert "<" not in pre_block
        assert ">" not in pre_block

    assert "record_challenge_cup_hard_evidence.py expert_feedback" in "\n".join(
        packets["expert_feedback_review"]["recording_commands"]
    )
    assert "preflight_challenge_cup_hard_evidence.py expert_feedback" in "\n".join(
        packets["expert_feedback_review"]["recording_commands"]
    )
    assert "--confirm-real-feedback" in "\n".join(packets["expert_feedback_review"]["recording_commands"])
    expert_pre_block = "\n".join(packets["expert_feedback_review"]["pre_hard_evidence_powershell_block"])
    assert "record_challenge_cup_expert_outreach.py" in expert_pre_block
    assert "--confirm-real-outreach" in expert_pre_block
    assert "preflight_challenge_cup_hard_evidence.py expert_feedback" not in expert_pre_block
    assert "record_challenge_cup_hard_evidence.py expert_feedback" not in expert_pre_block
    assert "run_challenge_cup_timed_rehearsal.py" in "\n".join(
        packets["timed_rehearsal_observer"]["recording_commands"]
    )
    timed_pre_block = "\n".join(packets["timed_rehearsal_observer"]["pre_hard_evidence_powershell_block"])
    assert "record_challenge_cup_timed_rehearsal_schedule.py" in timed_pre_block
    assert "--confirm-real-schedule" in timed_pre_block
    assert "run_challenge_cup_timed_rehearsal.py" not in timed_pre_block
    assert "preflight_challenge_cup_hard_evidence.py timed_rehearsal" in "\n".join(
        packets["timed_rehearsal_observer"]["recording_commands"]
    )
    assert any(
        "record_challenge_cup_hard_evidence.py timed_rehearsal" in command
        and "--confirm-real-rehearsal" in command
        for command in packets["timed_rehearsal_observer"]["recording_commands"]
    )
    timed_powershell = "\n".join(packets["timed_rehearsal_observer"]["powershell_execution_block"])
    assert "run_challenge_cup_timed_rehearsal.py" in timed_powershell
    assert "$timerSource" not in timed_powershell
    assert "preflight_challenge_cup_hard_evidence.py timed_rehearsal" not in timed_powershell
    assert "record_challenge_cup_hard_evidence.py timed_rehearsal" not in timed_powershell
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
    assert "<" not in command_text
    assert ">" not in command_text
    assert "actual-opening-seconds" not in command_text
    assert "actual-demo-seconds" not in command_text
    assert "actual-offline-fallback-seconds" not in command_text
    assert "q1-seconds" not in command_text
    assert "--opening-actual-seconds 88" in command_text
    assert "--demo-actual-seconds 170" in command_text
    assert "--offline-fallback-actual-seconds 18" in command_text
    assert "--killer-question-seconds 25 25 25 25 25" in command_text
    rehearsal_packet = packets["timed_rehearsal_observer"]
    assert "timing_acceptance_pass=false" in rehearsal_packet["failed_rehearsal_archival_rule"]
    assert "rejected_metadata_records" in rehearsal_packet["failed_rehearsal_archival_rule"]
    assert "collected_count" in rehearsal_packet["failed_rehearsal_archival_rule"]

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
    assert "must not be a JSON metadata file" in markdown
    assert "PowerShell execution block" in markdown
    assert "Pre-hard-evidence PowerShell block" in markdown
    assert "timing_acceptance_pass=false" in markdown
    assert "rejected_metadata_records" in markdown
    assert "\u4e0d\u4f2a\u9020" in markdown
    assert "\u771f\u5b9e\u4e13\u5bb6\u53cd\u9988" in markdown
    assert "\u771f\u5b9e\u8ba1\u65f6\u5f69\u6392" in markdown

    for handoff in (expert_handoff, observer_sheet):
        handoff_text = handoff.read_text(encoding="utf-8")
        assert "source_sha256" in handoff_text
        assert "source attachment" in handoff_text
        assert "must not be a JSON metadata file" in handoff_text
        assert "PowerShell execution block" in handoff_text
