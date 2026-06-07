from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_JSON = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_context_demo.json"
REPORT_MD = REPO_ROOT / "evaluation" / "reports" / "challenge_cup_graphrag_context_demo.md"
BOUNDARY = (
    "This report is a context-only GraphRAG retrieval demo; it does not generate LLM answers "
    "or prove online answer win-rate."
)
FORBIDDEN_VISIBLE_SOURCE_TOKENS = (
    "z-library",
    "z-lib",
    "1lib",
    "libgen",
    "sci-hub",
    "anna's archive",
    "annas-archive",
    "盗版",
    "pirat",
)


def test_build_graphrag_context_demo_outputs_text_and_graph_context() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_graphrag_context_demo.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert "GraphRAG context demo" in result.stdout
    payload = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert payload["report_type"] == "challenge_cup_graphrag_context_demo"
    assert payload["context_only"] is True
    assert payload["answer_generated"] is False
    assert payload["boundary"] == BOUNDARY
    assert payload["source_graph"].endswith("triples.csv")
    assert payload["text_baseline_method"] == "keyword"
    assert payload["selection_policy"] == "supported_domain_graph_cases_first"
    assert payload["eligible_source_scopes"] == [
        "fault_reports_and_maintenance_documents",
        "public_books_operation_and_fault_reports",
        "public_books_gas_turbine_and_combined_cycle",
    ]
    assert payload["excluded_supported_case_ids"] == [
        "cc032",
        "cc033",
        "cc034",
        "cc035",
        "cc043",
        "cc048",
        "cc056",
    ]
    assert payload["demo_case_count"] == 3
    assert payload["case_ids"] == ["cc039", "cc040", "cc041"]

    for case in payload["cases"]:
        assert case["graph_evidence_status"] == "supported"
        assert case["text_evidence"], case["id"]
        assert case["graph_evidence"], case["id"]
        citation_types = {citation["source_type"] for citation in case["citations"]}
        assert {"text", "graph"} <= citation_types
        assert "## Text retrieval evidence" in case["prompt_context"]
        assert "## Graph retrieval evidence" in case["prompt_context"]
        assert "Context-only debug mode" in case["prompt_context"]
        assert case["answer"] is None

    payload_text = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in FORBIDDEN_VISIBLE_SOURCE_TOKENS:
        assert forbidden not in payload_text

    markdown = REPORT_MD.read_text(encoding="utf-8")
    assert "GraphRAG context-only QA demo" in markdown
    assert "不生成 LLM 答案" in markdown
    assert "triples.csv" in markdown
    assert BOUNDARY in markdown
    markdown_lower = markdown.lower()
    for forbidden in FORBIDDEN_VISIBLE_SOURCE_TOKENS:
        assert forbidden not in markdown_lower
