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
        assert packet["acceptance_gate"].startswith("hard_evidence_ledger.categories.")
        assert packet["does_not_satisfy_goal_completion"] is True

    assert "record_challenge_cup_hard_evidence.py expert_feedback" in "\n".join(
        packets["expert_feedback_review"]["recording_commands"]
    )
    assert "--confirm-real-feedback" in "\n".join(packets["expert_feedback_review"]["recording_commands"])
    assert "run_challenge_cup_timed_rehearsal.py" in "\n".join(
        packets["timed_rehearsal_observer"]["recording_commands"]
    )
    assert any(
        "record_challenge_cup_hard_evidence.py timed_rehearsal" in command
        and "--confirm-real-rehearsal" in command
        for command in packets["timed_rehearsal_observer"]["recording_commands"]
    )

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
    assert "does_not_satisfy_goal_completion=True" in markdown
    assert "\u4e0d\u4f2a\u9020" in markdown
    assert "\u771f\u5b9e\u4e13\u5bb6\u53cd\u9988" in markdown
    assert "\u771f\u5b9e\u8ba1\u65f6\u5f69\u6392" in markdown
