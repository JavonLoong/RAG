from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_gap_remediation_plan.json"
REPORT_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_gap_remediation_plan.md"
BOUNDARY = (
    "This report closes local partial/missing GraphRAG evidence gaps with auditable supplement records; "
    "it does not claim online LLM answer win-rate, external validation, or that GraphRAG beats every "
    "baseline question."
)


def test_build_graphrag_gap_remediation_plan_outputs_closed_gap_evidence_without_online_win_claims() -> None:
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
    assert payload["status"] == "graph_evidence_gaps_closed_pending_external_validation"
    assert payload["gaps_marked_fixed"] is True
    assert payload["local_graph_evidence_gaps_closed"] is True
    assert payload["boundary"] == BOUNDARY
    assert payload["source_dataset"] == "evaluation/system_eval_questions.jsonl"
    assert payload["source_graph_report"] == "evaluation/reports/challenge_cup_graphrag_same_question_report.json"
    assert payload["source_answer_benchmark"] == "evaluation/reports/challenge_cup_graphrag_answer_benchmark.json"
    assert payload["total_graph_cases"] == 10
    assert payload["supported_count"] == 10
    assert payload["partial_count"] == 0
    assert payload["missing_count"] == 0
    assert payload["partial_or_missing_count"] == 0
    assert payload["priority_counts"]["P0"] == 0
    assert payload["priority_counts"]["P1"] == 0
    assert payload["remediation_items"] == []
    assert "不宣称在线 LLM answer win-rate" in payload["no_overclaim_rules"]
    assert "不宣称 GraphRAG 全面优于 baseline" in payload["no_overclaim_rules"]
    assert payload["closure_evidence"]["closed_case_ids"] == ["cc056"]
    assert payload["closure_evidence"]["manual_supplement"] == (
        "docs/challenge_cup/reproducibility/graphrag_manual_evidence_supplement.csv"
    )
    assert payload["closure_evidence"]["source_graph_report"] == (
        "evaluation/reports/challenge_cup_graphrag_same_question_report.json"
    )
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

    markdown = REPORT_MD.read_text(encoding="utf-8")
    assert "GraphRAG 补证整改计划" in markdown
    assert "graph_evidence_gaps_closed_pending_external_validation" in markdown
    assert "All fixed GraphRAG evidence gaps closed" in markdown
    assert "P0 missing 已补证" in markdown
    assert "不宣称在线 LLM answer win-rate" in markdown
    assert "cc056" in markdown
    assert BOUNDARY in markdown
