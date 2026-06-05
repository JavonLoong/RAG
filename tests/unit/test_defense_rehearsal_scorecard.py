from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCORECARD_JSON = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "defense_rehearsal_scorecard.json"
SCORECARD_MD = REPO_ROOT / "docs" / "challenge_cup" / "reproducibility" / "defense_rehearsal_scorecard.md"
BOUNDARY = "This scorecard proves rehearsal readiness and evidence anchors; it does not prove a live defense has already happened or guarantee an award."


def test_build_defense_rehearsal_scorecard_outputs_timed_evidence_plan() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_defense_rehearsal_scorecard.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "defense rehearsal scorecard" in result.stdout
    payload = json.loads(SCORECARD_JSON.read_text(encoding="utf-8"))
    assert payload["report_type"] == "challenge_cup_defense_rehearsal_scorecard"
    assert payload["status"] == "ready_for_timed_rehearsal"
    assert payload["boundary"] == BOUNDARY
    assert payload["timing_targets"] == {
        "opening_seconds": 90,
        "demo_seconds": 180,
        "offline_fallback_seconds": 20,
        "killer_question_seconds": 30,
    }
    assert payload["opening_required_points"] == ["问题", "方法", "完成度", "边界"]
    assert len(payload["demo_timeline"]) == 5
    assert len(payload["killer_questions"]) >= 5
    assert len(payload["no_overclaim_boundaries"]) >= 4
    assert payload["minimum_evidence_anchor_count"] >= 12
    assert "docs/challenge_cup/reproducibility/readiness_gate_report.md" in payload["evidence_files"]
    assert "evaluation/reports/challenge_cup_graphrag_context_demo.md" in payload["evidence_files"]
    assert all(item["evidence_anchors"] for item in payload["killer_questions"])

    markdown = SCORECARD_MD.read_text(encoding="utf-8")
    assert "答辩彩排计分卡" in markdown
    assert "90秒开场" in markdown
    assert "三分钟演示节奏" in markdown
    assert "20 秒内切换" in markdown
    assert "30 秒内回答" in markdown
    assert "不把 readiness gate 说成获奖保证" in markdown
    assert BOUNDARY in markdown
