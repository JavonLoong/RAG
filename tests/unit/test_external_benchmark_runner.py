from __future__ import annotations

from pathlib import Path

from scripts.run_open_source_90_external_benchmark_gate import select_open_source_90_reranker
from scripts.run_external_benchmark_evaluation import repo_relative_path, score_suite_payload


def test_score_suite_payload_weights_retrieval_first_metrics() -> None:
    payload = {
        "metrics": {
            "retrieval": {
                "keyword_recall_at_k": 0.50,
                "passage_id_recall_at_k": 0.80,
                "full_evidence_coverage_rate": 0.25,
                "no_result_rate": 0.10,
            }
        }
    }

    score = score_suite_payload(payload)

    assert score == 75.25


def test_repo_relative_path_keeps_workspace_outputs_ascii() -> None:
    path = Path("D:/example/RAG/outputs/external_benchmark_eval/run1")
    repo_root = Path("D:/example/RAG")

    normalized = repo_relative_path(path, repo_root=repo_root)

    assert normalized == Path("outputs/external_benchmark_eval/run1")


def test_open_source_90_external_gate_uses_reranker_only_for_multihop_auto_mode() -> None:
    assert select_open_source_90_reranker("legal", "auto") == "none"
    assert select_open_source_90_reranker("ragbench-hotpotqa-validation", "auto") == "cross_encoder"
    assert select_open_source_90_reranker("legal", "noop") == "noop"
