from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_gap_remediation_plan.json"
REPORT_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_gap_remediation_plan.md"
BOUNDARY = (
    "This plan turns partial/missing GraphRAG evidence into prioritized remediation work; it does not "
    "claim the gaps are already fixed."
)


def test_build_graphrag_gap_remediation_plan_outputs_all_partial_missing_cases_without_fix_claims() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_graphrag_gap_remediation_plan.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "GraphRAG gap remediation plan" in result.stdout
    payload = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert payload["report_type"] == "challenge_cup_graphrag_gap_remediation_plan"
    assert payload["status"] == "ready_for_graph_iteration"
    assert payload["gaps_marked_fixed"] is False
    assert payload["boundary"] == BOUNDARY
    assert payload["source_dataset"] == "evaluation/system_eval_questions.jsonl"
    assert payload["source_graph_report"] == "evaluation/reports/challenge_cup_graphrag_same_question_report.json"
    assert payload["source_answer_benchmark"] == "evaluation/reports/challenge_cup_graphrag_answer_benchmark.json"
    assert payload["total_graph_cases"] == 10
    assert payload["supported_count"] >= 3
    assert payload["supported_count"] >= 7
    assert payload["partial_count"] >= 1
    assert payload["missing_count"] == 0
    assert payload["partial_or_missing_count"] == payload["partial_count"] + payload["missing_count"]
    assert payload["priority_counts"]["P0"] == 0
    assert payload["priority_counts"]["P1"] == payload["partial_count"]
    assert len(payload["remediation_items"]) == payload["partial_or_missing_count"]
    assert "不把 partial/missing 改写成成功案例" in payload["no_overclaim_rules"]
    assert payload["required_evidence_to_archive"] == [
        "new_triples_or_summary_diff",
        "source_page_or_doc_anchor",
        "manual_review_note",
        "rerun_report_json",
    ]
    assert payload["rerun_commands"] == [
        "python scripts/build_graphrag_challenge_report.py",
        "python scripts/build_graphrag_answer_benchmark.py",
        "python scripts/build_graphrag_gap_remediation_plan.py",
        "python scripts/check_challenge_cup_readiness.py",
    ]

    items = {item["id"]: item for item in payload["remediation_items"]}
    assert "cc032" not in items
    assert "cc043" not in items
    assert "cc056" in items
    for item in payload["remediation_items"]:
        assert item["current_status"] == "partial"
        assert item["priority"] == "P1"
        assert item["claim_fixed"] is False
        assert item["missing_expected_keywords"]
        assert len(item["action_items"]) >= 3
        assert "rerun_report_json" in item["acceptance_evidence"]

    markdown = REPORT_MD.read_text(encoding="utf-8")
    assert "GraphRAG 补证整改计划" in markdown
    assert "ready_for_graph_iteration" in markdown
    assert "P0 missing 已补证" in markdown
    assert "不把 partial/missing 改写成成功案例" in markdown
    assert "cc056" in markdown
    assert BOUNDARY in markdown
