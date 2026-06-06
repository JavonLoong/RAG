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
        assert stream["source_integrity_guardrails"]
        assert "source_sha256" in "\n".join(stream["source_integrity_guardrails"])
        assert "source attachment" in "\n".join(stream["source_integrity_guardrails"])
        assert stream["acceptance_gate"].startswith("hard_evidence_ledger.categories.")
        assert stream["does_not_satisfy_goal_completion"] is True
        assert category in stream["acceptance_gate"]

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
    assert "check_challenge_cup_goal_completion.py" in "\n".join(payload["verification_commands"])

    output_json = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_action_pack.json"
    output_md = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_action_pack.md"
    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "External Hard Evidence Action Pack" in markdown
    assert "does_not_satisfy_goal_completion=True" in markdown
    assert "source_sha256" in markdown
    assert "source attachment" in markdown
    assert "expert_feedback" in markdown
    assert "timed_rehearsal" in markdown
    assert "不伪造" in markdown
