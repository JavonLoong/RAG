from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET_JSON = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "defense_rehearsal_result_packet.json"
PACKET_MD = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "defense_rehearsal_result_packet.md"
BOUNDARY = (
    "This packet prepares actual timed rehearsal recording; it does not claim a timed rehearsal has "
    "already been completed."
)


def test_build_defense_rehearsal_result_packet_outputs_recording_schema_without_fake_result() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_defense_rehearsal_result_packet.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "defense rehearsal result packet" in result.stdout
    payload = json.loads(PACKET_JSON.read_text(encoding="utf-8"))
    assert payload["report_type"] == "challenge_cup_defense_rehearsal_result_packet"
    assert payload["status"] == "ready_to_record_actual_rehearsal"
    assert payload["actual_rehearsal_completed"] is False
    assert payload["boundary"] == BOUNDARY
    assert payload["timing_targets"] == {
        "opening_seconds": 90,
        "demo_seconds": 180,
        "offline_fallback_seconds": 20,
        "killer_question_seconds": 30,
    }
    assert payload["pass_fail_rules"] == {
        "opening_actual_seconds_max": 90,
        "demo_actual_seconds_max": 180,
        "offline_fallback_actual_seconds_max": 20,
        "each_killer_question_actual_seconds_max": 30,
        "required_killer_question_count": 5,
    }
    assert payload["required_archive_evidence_types"] == ["计时截图", "彩排录屏", "观察员签字或备注", "问题遗漏清单"]
    assert payload["result_template"]["opening_actual_seconds"] is None
    assert payload["result_template"]["demo_actual_seconds"] is None
    assert payload["result_template"]["offline_fallback_actual_seconds"] is None
    assert len(payload["result_template"]["killer_question_results"]) == 5
    assert all(item["actual_seconds"] is None for item in payload["result_template"]["killer_question_results"])
    assert payload["result_template"]["overall_result"] == "not_recorded"
    assert "docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md" in payload["evidence_files"]
    assert "docs/challenge_cup/10_答辩攻防与彩排卡.md" in payload["evidence_files"]

    markdown = PACKET_MD.read_text(encoding="utf-8")
    assert "答辩计时彩排结果归档包" in markdown
    assert "尚未记录真实计时彩排" in markdown
    assert "不伪造现场彩排记录" in markdown
    assert "opening_actual_seconds" in markdown
    assert "offline_fallback_actual_seconds" in markdown
    assert "killer_question_results" in markdown
    assert BOUNDARY in markdown
