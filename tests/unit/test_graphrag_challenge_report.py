from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_same_question_report.json"
REPORT_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_same_question_report.md"


def test_build_graphrag_challenge_report_outputs_subset_metrics() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_graphrag_challenge_report.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert "GraphRAG same-question report" in result.stdout
    payload = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert payload["total_questions"] == 60
    assert payload["graphrag_question_count"] == 10
    assert payload["mode_counts"]["graphrag_context"] == 8
    assert payload["mode_counts"]["graphrag_global"] == 4
    assert payload["baseline_methods"] == ["keyword", "dense_hashing", "hybrid_rrf"]
    assert payload["priority_case_count"] >= 1
    markdown = REPORT_MD.read_text(encoding="utf-8")
    assert "GraphRAG 同题子集" in markdown
    assert "不代表完整 GraphRAG 在线问答已优于 baseline" in markdown
