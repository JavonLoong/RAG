from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_answer_benchmark.json"
REPORT_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_answer_benchmark.md"
BOUNDARY = (
    "This is a deterministic offline answer benchmark over the fixed GraphRAG subset; it does not claim "
    "online LLM answer win-rate or that GraphRAG beats every baseline question."
)


def test_build_graphrag_answer_benchmark_outputs_answer_level_subset_report() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_graphrag_answer_benchmark.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "GraphRAG answer benchmark" in result.stdout
    payload = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert payload["report_type"] == "challenge_cup_graphrag_answer_benchmark"
    assert payload["benchmark_mode"] == "deterministic_offline_reference_keyword_coverage"
    assert payload["llm_answer_generated"] is False
    assert payload["boundary"] == BOUNDARY
    assert payload["dataset"] == "evaluation/system_eval_questions.jsonl"
    assert payload["source_graph_report"] == "evaluation/reports/challenge_cup_graphrag_same_question_report.json"
    assert payload["answer_benchmark_case_count"] == 10
    assert payload["partial_or_missing_cases_retained"] is True
    assert payload["best_baseline_method_count"] == 3
    assert payload["graphrag_supported_answer_case_count"] >= 7
    assert payload["graphrag_partial_answer_case_count"] >= 1
    assert payload["graphrag_missing_answer_case_count"] == 0
    assert 0 <= payload["average_best_baseline_reference_keyword_coverage"] <= 1
    assert 0 <= payload["average_graphrag_reference_keyword_coverage"] <= 1
    assert "manual graph evidence now closes P0 missing cases" in payload["summary_verdict"]
    assert "does not claim online LLM answer win-rate" in payload["summary_verdict"]

    cases = {case["id"]: case for case in payload["cases"]}
    assert set(cases) == {"cc032", "cc033", "cc034", "cc035", "cc039", "cc040", "cc041", "cc043", "cc048", "cc056"}
    assert cases["cc041"]["graphrag_answer_status"] == "supported"
    for case_id in ["cc032", "cc035", "cc043", "cc048"]:
        assert cases[case_id]["graphrag_answer_status"] == "supported"
        assert cases[case_id]["answer_level_verdict"] == "graph_supported"
    for case in payload["cases"]:
        assert case["question"]
        assert case["reference_answer"]
        assert case["expected_evidence_keywords"]
        assert case["best_baseline_method"] in {"keyword", "dense_hashing", "hybrid_rrf"}
        assert 0 <= case["best_baseline_reference_keyword_coverage"] <= 1
        assert 0 <= case["graphrag_reference_keyword_coverage"] <= 1
        assert case["answer_level_verdict"] in {"graph_supported", "graph_partial", "graph_missing"}
        assert case["graphrag_answer_draft"]
        assert case["boundary"] == "保留该题原始 GraphRAG 证据状态，不把 partial/missing 改写成成功案例。"

    markdown = REPORT_MD.read_text(encoding="utf-8")
    assert "GraphRAG answer benchmark" in markdown
    assert "10 道 GraphRAG 同题" in markdown
    assert "保留 partial/missing" in markdown
    assert "P0 missing 已补证" in markdown
    assert "不宣称 GraphRAG 全面优于 baseline" in markdown
    assert BOUNDARY in markdown
