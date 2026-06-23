"""Quality gate for external open-source RAG benchmark runs."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .quality_profiles import OPEN_SOURCE_90_PROFILE, QualityTargetProfile


@dataclass(frozen=True, slots=True)
class BenchmarkQualityGateResult:
    status: str
    profile_name: str
    overall_score_100: float
    total_cases: int
    failures: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "profile_name": self.profile_name,
            "overall_score_100": self.overall_score_100,
            "total_cases": self.total_cases,
            "failures": self.failures,
            "warnings": self.warnings,
        }


def evaluate_external_benchmark_gate(
    payload: dict[str, Any],
    *,
    profile: QualityTargetProfile = OPEN_SOURCE_90_PROFILE,
) -> BenchmarkQualityGateResult:
    """Compare an external benchmark aggregate payload with the 90% target profile."""
    target_score = 100.0 * float(profile.benchmark_targets["recall_at_10"])
    target_recall = float(profile.benchmark_targets["recall_at_10"])
    max_no_result_rate = profile.thresholds.max_no_result_rate

    overall_score = _as_float(payload.get("overall_score_100"))
    total_cases = int(_as_float(payload.get("total_cases")))
    failures: list[dict[str, Any]] = []
    warnings: list[str] = []

    if total_cases <= 0:
        failures.append(_failure("total_cases", ">", 0, total_cases, scope="aggregate"))
    if overall_score < target_score:
        failures.append(_failure("overall_score_100", ">=", target_score, overall_score, scope="aggregate"))

    for summary in payload.get("benchmarks") or []:
        if not isinstance(summary, dict):
            continue
        benchmark = str(summary.get("benchmark") or "unknown")
        score = _as_float(summary.get("score_100"))
        if score < target_score:
            failures.append(_failure("score_100", ">=", target_score, score, scope=benchmark))

        metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
        retrieval = metrics.get("retrieval") if isinstance(metrics.get("retrieval"), dict) else {}
        keyword_recall = _as_float(retrieval.get("keyword_recall_at_k"))
        gold_recall_value = retrieval.get("gold_id_recall_at_k")
        if gold_recall_value is None:
            gold_recall_value = retrieval.get("passage_id_recall_at_k")
        effective_recall = keyword_recall if gold_recall_value is None else _as_float(gold_recall_value)
        no_result_rate = _as_float(retrieval.get("no_result_rate"))
        if effective_recall < target_recall:
            metric_name = (
                "retrieval.keyword_recall_at_k"
                if gold_recall_value is None
                else "retrieval.gold_id_recall_at_k"
            )
            failures.append(
                _failure(metric_name, ">=", target_recall, effective_recall, scope=benchmark)
            )
        if no_result_rate > max_no_result_rate:
            failures.append(
                _failure("retrieval.no_result_rate", "<=", max_no_result_rate, no_result_rate, scope=benchmark)
            )

        gate_status = str(summary.get("gate_status") or "")
        if gate_status and gate_status != "pass":
            warnings.append(f"{benchmark} harness gate_status={gate_status}")

    return BenchmarkQualityGateResult(
        status="pass" if not failures else "fail",
        profile_name=profile.name,
        overall_score_100=overall_score,
        total_cases=total_cases,
        failures=failures,
        warnings=warnings,
    )


def render_external_benchmark_gate_markdown(
    payload: dict[str, Any],
    gate: BenchmarkQualityGateResult,
) -> str:
    lines = [
        "# Open Source 90 External Benchmark Gate",
        "",
        f"- Profile: `{gate.profile_name}`",
        f"- Gate status: `{gate.status}`",
        f"- Overall score: {gate.overall_score_100} / 100",
        f"- Total cases: {gate.total_cases}",
        f"- Source run: `{payload.get('run_id', '')}`",
        "",
        "## Benchmark Scores",
        "",
        "| Benchmark | Cases | Score | Keyword recall | Gold id recall | No result rate | Gate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for summary in payload.get("benchmarks") or []:
        if not isinstance(summary, dict):
            continue
        retrieval = ((summary.get("metrics") or {}).get("retrieval") or {})
        lines.append(
            "| {benchmark} | {cases} | {score} | {recall} | {gold_recall} | {no_result} | {gate} |".format(
                benchmark=_md(summary.get("benchmark")),
                cases=_md(summary.get("case_count")),
                score=_md(summary.get("score_100")),
                recall=_md(retrieval.get("keyword_recall_at_k")),
                gold_recall=_md(retrieval.get("gold_id_recall_at_k") or retrieval.get("passage_id_recall_at_k")),
                no_result=_md(retrieval.get("no_result_rate")),
                gate=_md(summary.get("gate_status")),
            )
        )

    lines.extend(["", "## Failures", ""])
    if gate.failures:
        lines.extend(["| Scope | Metric | Actual | Rule | Threshold |", "| --- | --- | ---: | --- | ---: |"])
        for failure in gate.failures:
            lines.append(
                "| {scope} | {metric} | {actual} | {operator} | {threshold} |".format(**failure)
            )
    else:
        lines.append("No failures.")

    if gate.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in gate.warnings)

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This gate is the external benchmark counterpart to the local `quality:90` smoke gate. "
            "A pass here is required before claiming market-level 90% quality.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def benchmark_gate_to_json(payload: dict[str, Any], gate: BenchmarkQualityGateResult) -> str:
    return json.dumps({"benchmark_payload": payload, "quality_gate": gate.to_dict()}, ensure_ascii=False, indent=2) + "\n"


def _failure(metric: str, operator: str, threshold: float | int, actual: float | int, *, scope: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "metric": metric,
        "operator": operator,
        "threshold": threshold,
        "actual": round(float(actual), 6),
    }


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _md(value: Any) -> str:
    return "" if value is None else str(value).replace("|", "\\|").replace("\n", " ")
