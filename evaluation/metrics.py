"""Evaluation metrics for RAG quality assessment.

Implements four key metrics identified in the evaluation report:
1. Faithfulness — Does the answer only use information from retrieved context?
2. Relevancy — How relevant are the retrieved chunks to the query?
3. Context Recall — Does the retrieved context cover expected knowledge?
4. Answer Completeness — How complete and thorough is the generated answer?

Each metric supports both LLM-based evaluation and simple heuristic fallback.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EvaluationResult:
    """Result of evaluating a single question-answer pair."""

    question: str
    answer: str
    faithfulness: float | None = None
    relevancy: float | None = None
    context_recall: float | None = None
    answer_completeness: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def overall_score(self) -> float:
        """Weighted average of available metrics (0-1 scale)."""
        scores = [
            s
            for s in [
                self.faithfulness,
                self.relevancy,
                self.context_recall,
                self.answer_completeness,
            ]
            if s is not None
        ]
        return sum(scores) / len(scores) if scores else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer[:200] + "..." if len(self.answer) > 200 else self.answer,
            "faithfulness": self.faithfulness,
            "relevancy": self.relevancy,
            "context_recall": self.context_recall,
            "answer_completeness": self.answer_completeness,
            "overall_score": round(self.overall_score, 4),
            "details": self.details,
        }


def _call_llm(llm_client: Any, prompt: str) -> str:
    """Call LLM in a compatible way."""
    for method_name in ("generate", "complete", "invoke"):
        method = getattr(llm_client, method_name, None)
        if callable(method):
            return str(method(prompt))
    if callable(llm_client):
        return str(llm_client(prompt))
    raise TypeError("LLM client must be callable or expose generate/complete/invoke.")


def _extract_score(text: str) -> float:
    """Extract a numeric score (0-1) from LLM response text."""
    text = text.strip()
    # Try to parse JSON first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            score = parsed.get("score", parsed.get("rating"))
            if score is not None:
                return max(0.0, min(1.0, float(score)))
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Look for explicit score patterns
    patterns = [
        r"score[:\s]*([0-9]*\.?[0-9]+)",
        r"rating[:\s]*([0-9]*\.?[0-9]+)",
        r"([0-9]*\.?[0-9]+)\s*/\s*(?:1\.0|1|10)",
        r"^([0-9]*\.?[0-9]+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            try:
                value = float(match.group(1))
                # Normalize to 0-1 if appears to be on 0-10 scale
                if value > 1.0:
                    value = value / 10.0
                return max(0.0, min(1.0, value))
            except ValueError:
                continue

    logger.warning("Could not extract score from LLM response: %s", text[:100])
    return 0.5


class FaithfulnessMetric:
    """Measures whether the answer is faithful to the retrieved context.

    A faithful answer only makes claims that are supported by the context,
    without hallucinating additional information.
    """

    PROMPT = """Evaluate the faithfulness of the following answer to the given context.

## Context:
{context}

## Question:
{question}

## Answer:
{answer}

## Instructions:
Rate the faithfulness on a scale of 0.0 to 1.0:
- 1.0 = Every claim in the answer is directly supported by the context
- 0.5 = Some claims are supported, some are not found in context (but not wrong)
- 0.0 = The answer contains information that contradicts the context

Respond with ONLY a JSON object: {{"score": <float>, "reason": "<brief explanation>"}}"""

    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client

    def evaluate(
        self, question: str, answer: str, context: str
    ) -> float:
        """Evaluate faithfulness of answer to context."""
        if self.llm_client is None:
            return self._heuristic(answer, context)

        prompt = self.PROMPT.format(
            context=context[:3000],
            question=question,
            answer=answer[:2000],
        )
        try:
            response = _call_llm(self.llm_client, prompt)
            return _extract_score(response)
        except Exception as exc:
            logger.error("LLM faithfulness evaluation failed: %s", exc)
            return self._heuristic(answer, context)

    @staticmethod
    def _heuristic(answer: str, context: str) -> float:
        """Simple heuristic: check word overlap between answer and context."""
        answer_words = set(answer.lower().split())
        context_words = set(context.lower().split())
        if not answer_words:
            return 0.0
        overlap = answer_words & context_words
        return min(1.0, len(overlap) / max(len(answer_words) * 0.3, 1))


class RelevancyMetric:
    """Measures the relevancy of retrieved chunks to the question."""

    PROMPT = """Evaluate how relevant the following retrieved context is to the question.

## Question:
{question}

## Retrieved Context:
{context}

## Instructions:
Rate the relevancy on a scale of 0.0 to 1.0:
- 1.0 = The context directly and comprehensively addresses the question
- 0.5 = The context is partially relevant but missing key information
- 0.0 = The context is completely irrelevant to the question

Respond with ONLY a JSON object: {{"score": <float>, "reason": "<brief explanation>"}}"""

    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client

    def evaluate(self, question: str, context: str) -> float:
        """Evaluate relevancy of context to question."""
        if self.llm_client is None:
            return self._heuristic(question, context)

        prompt = self.PROMPT.format(
            question=question,
            context=context[:3000],
        )
        try:
            response = _call_llm(self.llm_client, prompt)
            return _extract_score(response)
        except Exception as exc:
            logger.error("LLM relevancy evaluation failed: %s", exc)
            return self._heuristic(question, context)

    @staticmethod
    def _heuristic(question: str, context: str) -> float:
        """Simple heuristic: keyword overlap between question and context."""
        q_words = set(question.lower().split())
        c_words = set(context.lower().split())
        if not q_words:
            return 0.0
        overlap = q_words & c_words
        # Remove common stop words from overlap count
        stop_words = {"的", "是", "在", "和", "有", "了", "不", "与", "为", "对",
                       "the", "is", "a", "an", "in", "of", "and", "to", "what", "how"}
        meaningful_overlap = overlap - stop_words
        meaningful_question = q_words - stop_words
        if not meaningful_question:
            return 0.5
        return min(1.0, len(meaningful_overlap) / len(meaningful_question))


class ContextRecallMetric:
    """Measures whether the retrieved context covers the expected answer content."""

    PROMPT = """Evaluate the context recall: does the retrieved context contain the information needed to answer correctly?

## Question:
{question}

## Expected Answer (reference):
{reference}

## Retrieved Context:
{context}

## Instructions:
Rate the context recall on a scale of 0.0 to 1.0:
- 1.0 = The context contains ALL information present in the expected answer
- 0.5 = The context contains about half of the needed information
- 0.0 = The context contains none of the needed information

Respond with ONLY a JSON object: {{"score": <float>, "reason": "<brief explanation>"}}"""

    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client

    def evaluate(
        self, question: str, context: str, reference: str
    ) -> float:
        """Evaluate context recall against a reference answer."""
        if self.llm_client is None:
            return self._heuristic(reference, context)

        prompt = self.PROMPT.format(
            question=question,
            reference=reference[:2000],
            context=context[:3000],
        )
        try:
            response = _call_llm(self.llm_client, prompt)
            return _extract_score(response)
        except Exception as exc:
            logger.error("LLM context recall evaluation failed: %s", exc)
            return self._heuristic(reference, context)

    @staticmethod
    def _heuristic(reference: str, context: str) -> float:
        """Simple heuristic: check if reference keywords appear in context."""
        ref_words = set(reference.lower().split())
        ctx_words = set(context.lower().split())
        if not ref_words:
            return 0.0
        overlap = ref_words & ctx_words
        return min(1.0, len(overlap) / max(len(ref_words) * 0.5, 1))


class AnswerCompletenessMetric:
    """Measures the completeness and thoroughness of the generated answer."""

    PROMPT = """Evaluate how complete and thorough the generated answer is compared to the expected answer.

## Question:
{question}

## Expected Answer (reference):
{reference}

## Generated Answer:
{answer}

## Instructions:
Rate the answer completeness on a scale of 0.0 to 1.0:
- 1.0 = The generated answer covers all key points from the expected answer
- 0.5 = The generated answer covers about half of the key points
- 0.0 = The generated answer misses all key points

Respond with ONLY a JSON object: {{"score": <float>, "reason": "<brief explanation>"}}"""

    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client

    def evaluate(
        self, question: str, answer: str, reference: str
    ) -> float:
        """Evaluate answer completeness against a reference."""
        if self.llm_client is None:
            return self._heuristic(answer, reference)

        prompt = self.PROMPT.format(
            question=question,
            reference=reference[:2000],
            answer=answer[:2000],
        )
        try:
            response = _call_llm(self.llm_client, prompt)
            return _extract_score(response)
        except Exception as exc:
            logger.error("LLM completeness evaluation failed: %s", exc)
            return self._heuristic(answer, reference)

    @staticmethod
    def _heuristic(answer: str, reference: str) -> float:
        """Simple heuristic: check key content overlap."""
        ref_words = set(reference.lower().split())
        ans_words = set(answer.lower().split())
        if not ref_words:
            return 0.0 if not ans_words else 0.5
        overlap = ref_words & ans_words
        return min(1.0, len(overlap) / max(len(ref_words) * 0.4, 1))


def evaluate_single(
    question: str,
    answer: str,
    context: str,
    reference: str | None = None,
    *,
    llm_client: Any | None = None,
) -> EvaluationResult:
    """Evaluate a single question-answer pair across all available metrics.

    Args:
        question: The input question.
        answer: The generated answer.
        context: The retrieved context.
        reference: Optional expected/reference answer for recall and completeness metrics.
        llm_client: Optional LLM client for LLM-based evaluation.

    Returns:
        EvaluationResult with all metric scores.
    """
    result = EvaluationResult(question=question, answer=answer)

    faithfulness = FaithfulnessMetric(llm_client)
    relevancy = RelevancyMetric(llm_client)
    result.faithfulness = faithfulness.evaluate(question, answer, context)
    result.relevancy = relevancy.evaluate(question, context)

    if reference:
        context_recall = ContextRecallMetric(llm_client)
        completeness = AnswerCompletenessMetric(llm_client)
        result.context_recall = context_recall.evaluate(question, context, reference)
        result.answer_completeness = completeness.evaluate(question, answer, reference)

    return result
