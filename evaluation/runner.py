"""Evaluation runner for batch evaluation of RAG systems."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .metrics import EvaluationResult, evaluate_single

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TestCase:
    question: str
    reference_answer: str | None = None
    expected_chapter: str | None = None
    question_type: str | None = None
    question_id: int | None = None


@dataclass(slots=True)
class EvaluationSuite:
    name: str
    test_cases: list[TestCase]
    description: str = ""

    @classmethod
    def from_json(cls, path: str | Path) -> EvaluationSuite:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        test_cases = [
            TestCase(
                question=tc["question"],
                reference_answer=tc.get("reference_answer"),
                expected_chapter=tc.get("expected_chapter"),
                question_type=tc.get("question_type"),
                question_id=tc.get("id"),
            )
            for tc in data.get("test_cases", [])
        ]
        return cls(name=data.get("name", Path(path).stem), test_cases=test_cases, description=data.get("description", ""))


@dataclass(slots=True)
class EvaluationReport:
    suite_name: str
    results: list[EvaluationResult]
    elapsed_seconds: float
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def avg_faithfulness(self) -> float | None:
        scores = [r.faithfulness for r in self.results if r.faithfulness is not None]
        return sum(scores) / len(scores) if scores else None

    @property
    def avg_relevancy(self) -> float | None:
        scores = [r.relevancy for r in self.results if r.relevancy is not None]
        return sum(scores) / len(scores) if scores else None

    @property
    def avg_overall(self) -> float:
        scores = [r.overall_score for r in self.results if r.overall_score > 0]
        return sum(scores) / len(scores) if scores else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "total_questions": len(self.results),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "timestamp": self.timestamp,
            "averages": {
                "faithfulness": round(self.avg_faithfulness, 4) if self.avg_faithfulness is not None else None,
                "relevancy": round(self.avg_relevancy, 4) if self.avg_relevancy is not None else None,
                "overall": round(self.avg_overall, 4),
            },
            "results": [r.to_dict() for r in self.results],
        }

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


class EvaluationRunner:
    """Runs evaluation suites against a RAG system."""

    def __init__(self, *, rag_system: Any, llm_client: Any | None = None) -> None:
        self.rag_system = rag_system
        self.llm_client = llm_client

    def _query_rag(self, question: str) -> dict[str, str]:
        for method_name in ("answer", "query", "search"):
            method = getattr(self.rag_system, method_name, None)
            if callable(method):
                result = method(question)
                return self._normalize_result(result)
        if callable(self.rag_system):
            return self._normalize_result(self.rag_system(question))
        raise TypeError("RAG system must expose answer/query/search or be callable.")

    @staticmethod
    def _normalize_result(result: Any) -> dict[str, str]:
        if isinstance(result, dict):
            return {"answer": str(result.get("answer", "")), "context": str(result.get("context", ""))}
        return {"answer": str(getattr(result, "answer", "") or ""), "context": str(getattr(result, "context", "") or "")}

    def run(self, suite: EvaluationSuite, *, max_questions: int | None = None) -> EvaluationReport:
        test_cases = suite.test_cases[:max_questions] if max_questions else suite.test_cases
        results: list[EvaluationResult] = []
        start_time = time.time()

        for index, tc in enumerate(test_cases, start=1):
            logger.info("Evaluating [%d/%d]: %s", index, len(test_cases), tc.question[:80])
            try:
                rag_output = self._query_rag(tc.question)
                result = evaluate_single(
                    question=tc.question, answer=rag_output["answer"],
                    context=rag_output["context"], reference=tc.reference_answer,
                    llm_client=self.llm_client,
                )
                result.details["question_type"] = tc.question_type
                results.append(result)
            except Exception as exc:
                logger.error("Failed to evaluate question %d: %s", index, exc)
                results.append(EvaluationResult(question=tc.question, answer=f"ERROR: {exc}"))

        return EvaluationReport(
            suite_name=suite.name, results=results,
            elapsed_seconds=time.time() - start_time,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
