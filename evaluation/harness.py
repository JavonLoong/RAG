"""Runnable RAG evaluation harness with quality gates."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from scripts.run_system_evaluation import evaluate_records


@dataclass(frozen=True, slots=True)
class RAGEvaluationCase:
    id: str
    question: str
    expected_evidence_keywords: list[str]
    reference_answer: str = ""
    task_type: str = "general"
    source_scope: str | list[str] = "unspecified"
    grading_notes: str = ""
    expected_modes: list[str] = field(default_factory=list)

    def to_dataset_record(self) -> dict[str, Any]:
        if not self.question.strip():
            raise ValueError("Evaluation case question cannot be empty.")
        keywords = [keyword.strip() for keyword in self.expected_evidence_keywords if keyword.strip()]
        if not keywords:
            raise ValueError(f"Evaluation case {self.id!r} must define expected evidence keywords.")
        return {
            "id": str(self.id),
            "question": self.question.strip(),
            "reference_answer": self.reference_answer,
            "expected_evidence_keywords": keywords,
            "task_type": self.task_type,
            "source_scope": self.source_scope,
            "grading_notes": self.grading_notes,
            "expected_modes": list(self.expected_modes),
        }


@dataclass(frozen=True, slots=True)
class EvaluationThresholds:
    min_keyword_recall_at_k: float = 0.7
    min_answer_completeness: float = 0.7
    max_missing_citation_rate: float = 0.2
    max_medium_or_high_risk_rate: float = 0.4
    max_no_result_rate: float = 0.05

    def check(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        metrics = payload.get("metrics", {})
        failures: list[dict[str, Any]] = []

        def read(path: str) -> float | None:
            current: Any = metrics
            for part in path.split("."):
                if not isinstance(current, dict):
                    return None
                current = current.get(part)
            return float(current) if current is not None else None

        checks = [
            ("retrieval.keyword_recall_at_k", ">=", self.min_keyword_recall_at_k, read("retrieval.keyword_recall_at_k")),
            (
                "answer.answer_completeness_avg",
                ">=",
                self.min_answer_completeness,
                read("answer.answer_completeness_avg"),
            ),
            (
                "citation.missing_citation_rate",
                "<=",
                self.max_missing_citation_rate,
                read("citation.missing_citation_rate"),
            ),
            (
                "hallucination_risk.medium_or_high_risk_rate",
                "<=",
                self.max_medium_or_high_risk_rate,
                read("hallucination_risk.medium_or_high_risk_rate"),
            ),
            ("retrieval.no_result_rate", "<=", self.max_no_result_rate, read("retrieval.no_result_rate")),
        ]
        for metric, operator, threshold, actual in checks:
            if actual is None:
                continue
            failed = actual < threshold if operator == ">=" else actual > threshold
            if failed:
                failures.append(
                    {
                        "metric": metric,
                        "operator": operator,
                        "threshold": threshold,
                        "actual": round(actual, 6),
                    }
                )
        return failures


@dataclass(slots=True)
class RAGEvaluationReport:
    payload: dict[str, Any]
    thresholds: EvaluationThresholds
    gate_failures: list[dict[str, Any]]
    failure_cases: list[dict[str, Any]]
    run_name: str = "rag_eval"
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def gate_status(self) -> str:
        return "pass" if not self.gate_failures else "fail"

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.payload)
        result["run_name"] = self.run_name
        result["evaluation_gate"] = {
            "status": self.gate_status,
            "thresholds": {
                "min_keyword_recall_at_k": self.thresholds.min_keyword_recall_at_k,
                "min_answer_completeness": self.thresholds.min_answer_completeness,
                "max_missing_citation_rate": self.thresholds.max_missing_citation_rate,
                "max_medium_or_high_risk_rate": self.thresholds.max_medium_or_high_risk_rate,
                "max_no_result_rate": self.thresholds.max_no_result_rate,
            },
            "failures": self.gate_failures,
            "failure_case_count": len(self.failure_cases),
        }
        result["failure_cases"] = self.failure_cases
        result["retrieval_default_policy"] = _build_retrieval_default_policy(
            result,
            self.thresholds,
            self.gate_failures,
        )
        return result

    def save(self, output_dir: str | Path) -> dict[str, Path]:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = self.generated_at.strftime("%Y%m%d_%H%M%S")
        stem = f"rag_eval_{_sanitize_run_name(self.run_name)}_{stamp}".strip("_")
        json_path = target_dir / f"{stem}.json"
        md_path = target_dir / f"{stem}.md"

        json_path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(self.to_markdown(), encoding="utf-8")
        return {"json": json_path, "md": md_path}

    def to_markdown(self) -> str:
        payload = self.to_dict()
        metrics = payload.get("metrics", {})
        lines = [
            "# RAG Evaluation Report",
            "",
            f"- Run: `{self.run_name}`",
            f"- Gate status: `{self.gate_status}`",
            f"- Total questions: {payload.get('summary', {}).get('total_questions', 0)}",
            "",
            "## Metrics",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
        ]
        for section, values in metrics.items():
            if not isinstance(values, dict):
                continue
            for name, value in values.items():
                lines.append(f"| {section}.{name} | {value} |")

        lines.extend(["", "## Gate Failures", ""])
        if self.gate_failures:
            lines.extend(["| Metric | Actual | Rule | Threshold |", "| --- | ---: | --- | ---: |"])
            for failure in self.gate_failures:
                lines.append(
                    "| {metric} | {actual} | {operator} | {threshold} |".format(**failure)
                )
        else:
            lines.append("No gate failures.")

        policy = payload.get("retrieval_default_policy", {})
        defaults = policy.get("recommended_defaults", {}) if isinstance(policy, dict) else {}
        lines.extend(["", "## Retrieval Default Policy", ""])
        if defaults:
            lines.extend(["| Setting | Recommendation |", "| --- | --- |"])
            for name, value in defaults.items():
                lines.append(f"| {name} | {_markdown_cell(value)} |")
            triggered_by = policy.get("triggered_by_metrics") or []
            lines.extend(["", f"Triggered by metrics: `{', '.join(triggered_by) or 'none'}`."])
        else:
            lines.append("No retrieval default policy recommendation was generated.")

        lines.extend(["", "## Failure Cases", ""])
        if self.failure_cases:
            lines.extend(
                [
                    "| ID | Question | Retrieval Coverage | Missing Citation | Risk |",
                    "| --- | --- | ---: | --- | --- |",
                ]
            )
            for case in self.failure_cases:
                lines.append(
                    "| {id} | {question} | {coverage} | {missing} | {risk} |".format(
                        id=_markdown_cell(case.get("id", "")),
                        question=_markdown_cell(case.get("question", "")),
                        coverage=case.get("retrieval_keyword_coverage"),
                        missing=case.get("missing_citation"),
                        risk=case.get("hallucination_risk"),
                    )
                )
        else:
            lines.append("No failure cases.")

        lines.extend(["", "## Results", ""])
        results = payload.get("results", [])
        if results:
            lines.extend(
                [
                    "| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |",
                    "| --- | --- | ---: | ---: | --- | --- |",
                ]
            )
            for result in results:
                lines.append(
                    "| {id} | {question} | {retrieval} | {answer} | {missing} | {risk} |".format(
                        id=_markdown_cell(result.get("id", "")),
                        question=_markdown_cell(result.get("question", "")),
                        retrieval=result.get("retrieval_keyword_coverage"),
                        answer=result.get("answer_keyword_coverage"),
                        missing=result.get("missing_citation"),
                        risk=result.get("hallucination_risk"),
                    )
                )
        else:
            lines.append("No evaluated results.")

        return "\n".join(lines).rstrip() + "\n"


class RAGEvaluationHarness:
    """Runs a question set against a live RAG object and applies quality gates."""

    def __init__(
        self,
        rag_system: Any,
        *,
        thresholds: EvaluationThresholds | None = None,
        top_k: int = 5,
        retrieval_only: bool = False,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be greater than 0.")
        self.rag_system = rag_system
        self.thresholds = thresholds or EvaluationThresholds()
        self.top_k = top_k
        self.retrieval_only = retrieval_only

    def run(self, cases: Iterable[RAGEvaluationCase], *, run_name: str = "rag_eval") -> RAGEvaluationReport:
        dataset = [case.to_dataset_record() for case in cases]
        outputs = [self._run_case(case) for case in dataset]
        payload = evaluate_records(dataset, outputs, top_k=self.top_k, retrieval_only=self.retrieval_only)
        gate_failures = self.thresholds.check(payload)
        failure_cases = _select_failure_cases(payload, self.thresholds)
        return RAGEvaluationReport(
            payload=payload,
            thresholds=self.thresholds,
            gate_failures=gate_failures,
            failure_cases=failure_cases,
            run_name=run_name,
        )

    def _run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        question = str(case["question"])
        output = self._query_case(case)
        output["id"] = case["id"]
        output["question"] = question
        return output

    def _query_case(self, case: dict[str, Any]) -> dict[str, Any]:
        method = getattr(self.rag_system, "query_case", None)
        if callable(method):
            return _normalize_rag_output(method(case))
        return self._query(str(case["question"]))

    def _query(self, question: str) -> dict[str, Any]:
        for method_name in ("answer", "query", "search"):
            method = getattr(self.rag_system, method_name, None)
            if callable(method):
                return _normalize_rag_output(method(question))
        if callable(self.rag_system):
            return _normalize_rag_output(self.rag_system(question))
        raise TypeError("RAG system must expose answer/query/search or be callable.")


def _normalize_rag_output(output: Any) -> dict[str, Any]:
    if isinstance(output, dict):
        normalized = dict(output)
    else:
        normalized = {
            "answer": getattr(output, "answer", ""),
            "context": getattr(output, "context", ""),
            "citations": getattr(output, "citations", []),
            "retrieval_results": getattr(output, "retrieval_results", []),
        }

    if "retrieval_results" not in normalized:
        for key in ("hits", "contexts", "documents", "evidence"):
            if key in normalized:
                normalized["retrieval_results"] = normalized[key]
                break
    if "retrieval_results" not in normalized and normalized.get("context"):
        normalized["retrieval_results"] = [{"text": normalized["context"]}]
    normalized.setdefault("answer", "")
    normalized.setdefault("citations", [])
    normalized.setdefault("retrieval_results", [])
    return normalized


def _select_failure_cases(payload: dict[str, Any], thresholds: EvaluationThresholds) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for result in payload.get("results", []):
        coverage = result.get("retrieval_keyword_coverage")
        answer_coverage = result.get("answer_keyword_coverage")
        risk = result.get("hallucination_risk")
        failed = (
            coverage is not None
            and coverage < thresholds.min_keyword_recall_at_k
            or answer_coverage is not None
            and answer_coverage < thresholds.min_answer_completeness
            or bool(result.get("missing_citation"))
            or risk in {"medium", "high"}
            or not result.get("has_retrieval_result")
        )
        if failed:
            failures.append(result)
    return failures


def _build_retrieval_default_policy(
    payload: dict[str, Any],
    thresholds: EvaluationThresholds,
    gate_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics"), dict) else {}
    triggered = [str(failure.get("metric")) for failure in gate_failures if failure.get("metric")]
    triggered_set = set(triggered)

    retrieval = metrics.get("retrieval", {}) if isinstance(metrics.get("retrieval"), dict) else {}
    citation = metrics.get("citation", {}) if isinstance(metrics.get("citation"), dict) else {}
    risk = metrics.get("hallucination_risk", {}) if isinstance(metrics.get("hallucination_risk"), dict) else {}

    recall_failed = "retrieval.keyword_recall_at_k" in triggered_set
    answer_failed = "answer.answer_completeness_avg" in triggered_set
    citation_failed = "citation.missing_citation_rate" in triggered_set
    risk_failed = "hallucination_risk.medium_or_high_risk_rate" in triggered_set
    no_result_failed = "retrieval.no_result_rate" in triggered_set

    defaults = {
        "hybrid_rrf": True,
        "metadata_filters": "explicit_and_auto_source_filters",
        "graph_retriever": "enable_when_graph_db_path_and_graph_quality_pass",
        "query_rewrite": "enable_by_default" if recall_failed else "keep_optional",
        "reranker": "cross_encoder" if recall_failed or answer_failed else "none",
        "no_answer_gate": (
            "enable_with_calibrated_threshold"
            if citation_failed or risk_failed or no_result_failed
            else "keep_optional"
        ),
    }
    if no_result_failed:
        defaults["no_answer_min_results"] = 1
    if citation_failed or risk_failed:
        defaults["no_answer_min_score"] = "calibrate_from_validation_set"

    reasons: list[str] = []
    if recall_failed:
        reasons.append(
            "retrieval recall missed the configured threshold; default query rewrite and rerank should be evaluated."
        )
    if answer_failed:
        reasons.append("answer completeness missed the configured threshold; reranking or stronger evidence selection is recommended.")
    if citation_failed:
        reasons.append("missing citations exceeded the configured threshold; no-answer gating should block weak evidence.")
    if risk_failed:
        reasons.append("hallucination risk exceeded the configured threshold; stricter evidence gating is recommended.")
    if no_result_failed:
        reasons.append("no-result rate exceeded the configured threshold; retrieval coverage and fallback behavior need adjustment.")
    if not reasons:
        reasons.append("all configured gates passed; keep risky retrieval switches optional until a broader corpus validates defaults.")

    return {
        "status": "needs_policy_change" if triggered else "keep_current_defaults",
        "recommended_defaults": defaults,
        "triggered_by_metrics": triggered,
        "observed_metrics": {
            "keyword_recall_at_k": retrieval.get("keyword_recall_at_k"),
            "no_result_rate": retrieval.get("no_result_rate"),
            "missing_citation_rate": citation.get("missing_citation_rate"),
            "medium_or_high_risk_rate": risk.get("medium_or_high_risk_rate"),
        },
        "threshold_basis": {
            "min_keyword_recall_at_k": thresholds.min_keyword_recall_at_k,
            "max_missing_citation_rate": thresholds.max_missing_citation_rate,
            "max_medium_or_high_risk_rate": thresholds.max_medium_or_high_risk_rate,
            "max_no_result_rate": thresholds.max_no_result_rate,
        },
        "reasons": reasons,
    }


def _sanitize_run_name(run_name: str) -> str:
    sanitized = re.sub(r"[^0-9A-Za-z_.-]+", "_", run_name.strip())
    return sanitized.strip("._-") or "rag_eval"


def _markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")
