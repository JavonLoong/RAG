from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from evaluation import run_ingest_search_evaluation_smoke as exported_smoke_runner
from evaluation.smoke import run_ingest_search_evaluation_smoke


def test_smoke_runner_is_exported_from_evaluation_package() -> None:
    assert exported_smoke_runner is run_ingest_search_evaluation_smoke


def test_ingest_search_evaluation_smoke_runs_real_pipeline_and_quality_gate(tmp_path: Path) -> None:
    result = run_ingest_search_evaluation_smoke(
        persist_dir=tmp_path / "chroma",
        report_dir=tmp_path / "reports",
        collection_name="smoke",
    )

    assert result["ingest"]["chunks_written"] >= 1
    assert result["search"]["results"]
    assert result["evaluation"]["gate_status"] == "pass"
    assert result["evaluation"]["metrics"]["retrieval"]["keyword_recall_at_k"] == 1.0
    assert result["evaluation"]["retrieval_default_policy"]["recommended_defaults"]["hybrid_rrf"] is True
    assert result["evaluation"]["retrieval_default_policy"]["recommended_defaults"]["query_rewrite"] == "keep_optional"
    assert result["graph_quality"]["gate_status"] == "pass"
    assert result["graph_quality"]["metrics"]["evidence_coverage"] == 1.0
    assert result["graphrag_query"]["status_code"] == 200
    assert result["graphrag_query"]["route"]["strategy"] == "LOCAL_SEARCH"
    assert result["graphrag_query"]["graph_quality_gate_status"] == "pass"
    assert result["graphrag_query"]["graph_citation_count"] >= 1
    assert result["graphrag_query"]["context_has_graph_evidence"] is True
    assert result["graphrag_global_answer"]["status_code"] == 200
    assert result["graphrag_global_answer"]["route"]["strategy"] == "GLOBAL_SEARCH"
    assert result["graphrag_global_answer"]["graph_quality_gate_status"] == "pass"
    assert result["graphrag_global_answer"]["answer_generated"] is True
    assert result["graphrag_global_answer"]["global_context_present"] is True
    assert result["graphrag_global_answer"]["llm_call_count"] >= 2
    assert Path(result["reports"]["json"]).exists()
    assert Path(result["reports"]["md"]).exists()


def test_run_rag_smoke_evaluation_cli(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_rag_smoke_evaluation.py",
            "--persist-dir",
            str(tmp_path / "cli-chroma"),
            "--report-dir",
            str(tmp_path / "cli-reports"),
            "--collection",
            "smoke_cli",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "gate_status=pass" in completed.stdout
    assert "graphrag_query=pass" in completed.stdout
    assert "graphrag_global=pass" in completed.stdout
