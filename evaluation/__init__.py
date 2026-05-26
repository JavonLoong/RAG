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
from .runner import EvaluationRunner, EvaluationSuite

__all__ = [
    "AnswerCompletenessMetric",
    "ContextRecallMetric",
    "EvaluationResult",
    "EvaluationRunner",
    "EvaluationSuite",
    "FaithfulnessMetric",
    "RelevancyMetric",
    "evaluate_single",
]
