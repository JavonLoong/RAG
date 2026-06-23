from __future__ import annotations

from evaluation import evaluate_external_benchmark_gate, render_external_benchmark_gate_markdown


def test_external_benchmark_gate_passes_when_profile_targets_are_met() -> None:
    payload = {
        "run_id": "unit-pass",
        "overall_score_100": 91.0,
        "total_cases": 10,
        "benchmarks": [
            {
                "benchmark": "bench-a",
                "score_100": 92.0,
                "case_count": 10,
                "gate_status": "pass",
                "metrics": {"retrieval": {"keyword_recall_at_k": 0.91, "no_result_rate": 0.0}},
            }
        ],
    }

    gate = evaluate_external_benchmark_gate(payload)

    assert gate.status == "pass"
    assert gate.failures == []
    assert "Gate status: `pass`" in render_external_benchmark_gate_markdown(payload, gate)


def test_external_benchmark_gate_fails_on_current_low_score_shape() -> None:
    payload = {
        "run_id": "unit-fail",
        "overall_score_100": 39.05,
        "total_cases": 200,
        "benchmarks": [
            {
                "benchmark": "legal-rag-bench",
                "score_100": 23.18,
                "case_count": 50,
                "gate_status": "fail",
                "metrics": {"retrieval": {"keyword_recall_at_k": 0.188333, "no_result_rate": 0.0}},
            },
            {
                "benchmark": "ragbench-hotpotqa-validation",
                "score_100": 57.63,
                "case_count": 50,
                "gate_status": "fail",
                "metrics": {"retrieval": {"keyword_recall_at_k": 0.643333, "no_result_rate": 0.22}},
            },
        ],
    }

    gate = evaluate_external_benchmark_gate(payload)
    markdown = render_external_benchmark_gate_markdown(payload, gate)

    assert gate.status == "fail"
    assert any(failure["scope"] == "aggregate" for failure in gate.failures)
    assert any(failure["metric"] == "retrieval.no_result_rate" for failure in gate.failures)
    assert "legal-rag-bench" in markdown
    assert "A pass here is required" in markdown


def test_external_benchmark_gate_uses_gold_id_recall_when_available() -> None:
    payload = {
        "run_id": "unit-gold-id-pass",
        "overall_score_100": 91.0,
        "total_cases": 5,
        "benchmarks": [
            {
                "benchmark": "ragbench-hotpotqa-validation",
                "score_100": 91.0,
                "case_count": 5,
                "gate_status": "pass",
                "metrics": {
                    "retrieval": {
                        "keyword_recall_at_k": 0.62,
                        "gold_id_recall_at_k": 1.0,
                        "no_result_rate": 0.0,
                    }
                },
            }
        ],
    }

    gate = evaluate_external_benchmark_gate(payload)

    assert gate.status == "pass"
    assert gate.failures == []
