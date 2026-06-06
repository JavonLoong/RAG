from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_challenge_cup_hard_evidence_closure_board.py"


def load_closure_module():
    spec = importlib.util.spec_from_file_location("build_challenge_cup_hard_evidence_closure_board", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_builds_hard_evidence_closure_board_without_claiming_completion(tmp_path: Path) -> None:
    module = load_closure_module()
    module.configure_paths(tmp_path)

    payload = module.write_outputs()

    assert payload["report_type"] == "challenge_cup_hard_evidence_closure_board"
    assert payload["status"] == "awaiting_real_external_evidence_closure"
    assert payload["no_completion_claimed"] is True
    assert payload["does_not_satisfy_goal_completion"] is True
    assert payload["required_before_goal_completion"] == ["expert_feedback", "timed_rehearsal"]
    assert payload["blocker_count"] == 2
    streams = {item["category"]: item for item in payload["closure_streams"]}
    assert set(streams) == {"expert_feedback", "timed_rehearsal"}
    assert streams["expert_feedback"]["required_source_examples"]
    assert streams["timed_rehearsal"]["required_source_examples"]
    assert "record_challenge_cup_hard_evidence.py expert_feedback" in "\n".join(
        streams["expert_feedback"]["ready_to_execute_commands"]
    )
    assert "preflight_challenge_cup_hard_evidence.py expert_feedback" in "\n".join(
        streams["expert_feedback"]["ready_to_execute_commands"]
    )
    assert "--confirm-real-feedback" in "\n".join(streams["expert_feedback"]["ready_to_execute_commands"])
    assert "run_challenge_cup_timed_rehearsal.py" in "\n".join(
        streams["timed_rehearsal"]["ready_to_execute_commands"]
    )
    assert "preflight_challenge_cup_hard_evidence.py timed_rehearsal" in "\n".join(
        streams["timed_rehearsal"]["ready_to_execute_commands"]
    )
    assert any(
        "record_challenge_cup_hard_evidence.py timed_rehearsal" in command
        and "--confirm-real-rehearsal" in command
        for command in streams["timed_rehearsal"]["ready_to_execute_commands"]
    )
    assert "check_challenge_cup_goal_completion.py" in "\n".join(payload["post_closure_verification_commands"])

    output_json = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_closure_board.json"
    output_md = tmp_path / "docs" / "challenge_cup" / "reproducibility" / "hard_evidence_closure_board.md"
    assert json.loads(output_json.read_text(encoding="utf-8")) == payload
    markdown = output_md.read_text(encoding="utf-8")
    assert "Hard Evidence Closure Board" in markdown
    assert "does not satisfy goal completion" in markdown
    assert "expert_feedback" in markdown
    assert "timed_rehearsal" in markdown
