from __future__ import annotations

from pathlib import Path


def test_gitlab_ci_runs_one_command_rag_smoke_gate_before_deploy() -> None:
    ci_text = Path(".gitlab-ci.yml").read_text(encoding="utf-8")

    assert "  - test" in ci_text
    assert "rag-smoke-job:" in ci_text
    assert "stage: test" in ci_text
    assert "scripts/run_rag_smoke_evaluation.py" in ci_text
    assert "scripts/run_graphrag_triage_regression.py" in ci_text
    assert (
        "scripts/run_graphrag_triage_regression.py --dataset /tmp/rag_smoke_chroma/evaluation/graphrag_triage_regression.jsonl "
        "--report-dir /tmp/rag_smoke_reports --persist-dir /tmp/rag_smoke_chroma --collection ci_rag_smoke --backend hashing --allow-empty"
    ) in ci_text
    assert "gate_status=pass" in ci_text
    assert "graphrag_query=pass" in ci_text
    assert "graphrag_global=pass" in ci_text
    assert "triage_regression=pass" in ci_text
