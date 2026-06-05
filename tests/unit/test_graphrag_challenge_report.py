from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_same_question_report.json"
REPORT_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_same_question_report.md"
SUPPLEMENT = "docs/challenge_cup/reproducibility/graphrag_manual_evidence_supplement.csv"


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
    assert payload["graph_evidence_source"].endswith("triples.csv")
    assert payload["graph_evidence_supplement"] == SUPPLEMENT
    assert payload["base_graph_triple_count"] == 240
    assert payload["manual_evidence_supplement_count"] >= 4
    assert payload["graph_triple_count"] == payload["base_graph_triple_count"] + payload["manual_evidence_supplement_count"]
    assert payload["graph_evidence_supported_case_count"] >= 7
    assert payload["graph_evidence_missing_case_count"] == 0
    assert payload["graph_evidence_boundary"] == (
        "Graph evidence coverage audits triples.csv keyword support; it is not a completed GraphRAG answer win-rate."
    )
    cases = {case["id"]: case for case in payload["cases"]}
    assert cases["cc041"]["graph_evidence_coverage"] == 1.0
    assert cases["cc041"]["graph_evidence_status"] == "supported"
    assert cases["cc041"]["matched_graph_evidence"]
    for case_id in ["cc032", "cc035", "cc043", "cc048"]:
        assert cases[case_id]["graph_evidence_status"] == "supported"
        assert cases[case_id]["graph_evidence_coverage"] >= 0.5
        assert cases[case_id]["matched_graph_evidence"]
    assert cases["cc035"]["graph_matchable_keyword_count"] == 2
    assert cases["cc035"]["ignored_graph_keywords"] == ["27", "26", "1", "0"]
    markdown = REPORT_MD.read_text(encoding="utf-8")
    assert "GraphRAG 同题子集" in markdown
    assert "Graph evidence coverage audit" in markdown
    assert "triples.csv" in markdown
    assert "manual evidence supplement" in markdown
    assert "不代表完整 GraphRAG 在线问答已优于 baseline" in markdown
