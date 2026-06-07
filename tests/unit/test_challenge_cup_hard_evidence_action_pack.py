from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_hard_evidence_action_pack.py"


def load_action_pack_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_hard_evidence_action_pack", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_builds_human_handoff_pack_without_claiming_completion(tmp_path: Path) -> None:
    module = load_action_pack_module()
    module.configure_paths(tmp_path)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_hard_evidence_action_pack"
    assert payload["status"] == "ready_for_real_external_evidence_collection"
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["completion_claim_allowed"] is False
    assert payload["required_before_goal_completion"] == ["expert_feedback", "timed_rehearsal"]
    assert payload["operator_outcome"] == "package can be reviewed; goal cannot be closed"

    streams = {item["category"]: item for item in payload["action_streams"]}
    assert set(streams) == {"expert_feedback", "timed_rehearsal"}
    for category, stream in streams.items():
        assert stream["human_owner"]
        assert stream["human_action"]
        assert stream["proof_to_collect"]
        assert stream["ready_packet_files"]
        assert stream["recording_commands"]
        assert stream["powershell_execution_block"]
        assert stream["source_integrity_guardrails"]
        assert "source_sha256" in "\n".join(stream["source_integrity_guardrails"])
        assert "source attachment" in "\n".join(stream["source_integrity_guardrails"])
        assert "must not be a JSON metadata file" in "\n".join(stream["source_integrity_guardrails"])
        assert stream["acceptance_gate"].startswith("hard_evidence_ledger.categories.")
        assert stream["does_not_satisfy_goal_completion"] is True
        assert category in stream["acceptance_gate"]
        powershell = "\n".join(stream["powershell_execution_block"])
        assert "Set-Location" in powershell
        assert str(tmp_path) in powershell
        assert ".\\.venv\\Scripts\\python.exe" in powershell
        assert "python .\\scripts" not in powershell
        python_lines = [
            line for line in stream["powershell_execution_block"] if ".\\.venv\\Scripts\\python.exe" in line
        ]
        guard_lines = [line for line in stream["powershell_execution_block"] if "$LASTEXITCODE" in line]
        assert len(guard_lines) == len(python_lines)
        assert all("exit $LASTEXITCODE" in line for line in guard_lines)
        assert "<" not in powershell
        assert ">" not in powershell

    assert "record_challenge_cup_expert_outreach.py" in "\n".join(
        streams["expert_feedback"]["recording_commands"]
    )
    assert "record_challenge_cup_hard_evidence.py expert_feedback" in "\n".join(
        streams["expert_feedback"]["recording_commands"]
    )
    assert "preflight_challenge_cup_hard_evidence.py expert_feedback" in "\n".join(
        streams["expert_feedback"]["recording_commands"]
    )
    assert "--confirm-real-feedback" in "\n".join(streams["expert_feedback"]["recording_commands"])
    assert "record_challenge_cup_timed_rehearsal_schedule.py" in "\n".join(
        streams["timed_rehearsal"]["recording_commands"]
    )
    assert "run_challenge_cup_timed_rehearsal.py" in "\n".join(
        streams["timed_rehearsal"]["recording_commands"]
    )
    assert "preflight_challenge_cup_hard_evidence.py timed_rehearsal" in "\n".join(
        streams["timed_rehearsal"]["recording_commands"]
    )
    assert any(
        "record_challenge_cup_hard_evidence.py timed_rehearsal" in command
        and "--confirm-real-rehearsal" in command
        for command in streams["timed_rehearsal"]["recording_commands"]
    )
    command_text = "\n".join(
        command
        for stream in streams.values()
        for command in stream["recording_commands"]
    )
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
    rehearsal_rule = streams["timed_rehearsal"]["failed_rehearsal_archival_rule"]
    assert "timing_acceptance_pass=false" in rehearsal_rule
    assert "rejected_metadata_records" in rehearsal_rule
    assert "collected_count" in rehearsal_rule
    assert "check_challenge_cup_goal_completion.py" in "\n".join(payload["verification_commands"])
    timed_powershell = "\n".join(streams["timed_rehearsal"]["powershell_execution_block"])
    assert "run_challenge_cup_timed_rehearsal.py" in timed_powershell
    assert "$timerSource" not in timed_powershell
    assert "preflight_challenge_cup_hard_evidence.py timed_rehearsal" not in timed_powershell
    assert "record_challenge_cup_hard_evidence.py timed_rehearsal" not in timed_powershell

    output_json = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_action_pack.json"
    output_md = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_action_pack.md"
    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "External Hard Evidence Action Pack" in markdown
    assert "does_not_satisfy_goal_completion=True" in markdown
    assert "source_sha256" in markdown
    assert "source attachment" in markdown
    assert "must not be a JSON metadata file" in markdown
    assert "PowerShell execution block" in markdown
    assert "timing_acceptance_pass=false" in markdown
    assert "rejected_metadata_records" in markdown
    assert "expert_feedback" in markdown
    assert "timed_rehearsal" in markdown
    assert "不伪造" in markdown
