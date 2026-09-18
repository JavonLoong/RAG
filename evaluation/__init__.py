"""Evaluation system for GraphRAG.

Provides automated evaluation metrics for retrieval and generation quality:
- Faithfulness: Does the answer stay faithful to the retrieved context?
- Relevancy: How relevant is the retrieved content to the question?
- Context Recall: Does retrieval cover the expected answer?
- Answer Completeness: How complete is the generated answer?
"""
from __future__ import annotations

from .metrics import (
    AnswerCompletenessMetric,
    ContextRecallMetric,
    EvaluationResult,
    FaithfulnessMetric,
    RelevancyMetric,
    evaluate_single,
)
from .harness import EvaluationThresholds, RAGEvaluationCase, RAGEvaluationHarness, RAGEvaluationReport
from .benchmark_quality_gate import (
    BenchmarkQualityGateResult,
    benchmark_gate_to_json,
    evaluate_external_benchmark_gate,
    render_external_benchmark_gate_markdown,
)
from .quality_profiles import (
    OPEN_SOURCE_90_PROFILE,
    QUALITY_PROFILES,
    QualityTargetProfile,
    get_quality_profile,
    render_quality_profile_markdown,
)
from .promoted_regression_fixtures import (
    DEFAULT_TRIAGE_REGRESSION_DATASET,
    WECHAT_PRIVATE_CONTACT_CASE,
    seed_promoted_graphrag_regression_fixture,
)
from .runner import EvaluationRunner, EvaluationSuite
from .smoke import run_ingest_search_evaluation_smoke
from .triage_regression import (
    LocalChromaRegressionRag,
    load_graphrag_triage_regression_cases,
    run_graphrag_triage_regression,
)

__all__ = [
    "AnswerCompletenessMetric",
    "BenchmarkQualityGateResult",
    "ContextRecallMetric",
    "EvaluationThresholds",
    "EvaluationResult",
    "EvaluationRunner",
    "EvaluationSuite",
    "FaithfulnessMetric",
    "LocalChromaRegressionRag",
    "OPEN_SOURCE_90_PROFILE",
    "QUALITY_PROFILES",
    "QualityTargetProfile",
    "RAGEvaluationCase",
    "RAGEvaluationHarness",
    "RAGEvaluationReport",
    "RelevancyMetric",
    "DEFAULT_TRIAGE_REGRESSION_DATASET",
    "WECHAT_PRIVATE_CONTACT_CASE",
    "benchmark_gate_to_json",
    "evaluate_single",
    "evaluate_external_benchmark_gate",
    "get_quality_profile",
    "load_graphrag_triage_regression_cases",
    "render_quality_profile_markdown",
    "render_external_benchmark_gate_markdown",
    "run_graphrag_triage_regression",
    "run_ingest_search_evaluation_smoke",
    "seed_promoted_graphrag_regression_fixture",
]
