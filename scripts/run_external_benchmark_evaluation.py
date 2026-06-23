from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSOLE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(CONSOLE_SRC) not in sys.path:
    sys.path.insert(0, str(CONSOLE_SRC))

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

from chroma_rag_poc.pipeline import ingest_source_payloads  # noqa: E402
from chroma_rag_poc.embeddings import DEFAULT_SENTENCE_TRANSFORMER_MODEL  # noqa: E402
from evaluation import EvaluationThresholds, LocalChromaRegressionRag, RAGEvaluationHarness  # noqa: E402
from evaluation.external_benchmark_loader import (  # noqa: E402
    ExternalBenchmarkSuite,
    build_graphrag_bench_suite,
    build_legal_rag_bench_suite,
    build_ragbench_suite,
)

EXTERNAL_ROOT = REPO_ROOT / "evaluation" / "external_benchmarks"
DEFAULT_REPORT_DIR = REPO_ROOT / "evaluation" / "reports"
DEFAULT_PERSIST_ROOT = REPO_ROOT / "outputs" / "external_benchmark_eval"
DEFAULT_BENCHMARKS = (
    "legal",
    "graphrag-medical",
    "graphrag-novel",
    "ragbench-hotpotqa-validation",
)


def score_suite_payload(payload: dict[str, Any]) -> float:
    """Compute a retrieval-first benchmark score on a 0-100 scale."""
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    retrieval = metrics.get("retrieval") if isinstance(metrics.get("retrieval"), dict) else {}
    keyword_recall = _coerce_rate(retrieval.get("keyword_recall_at_k"))
    passage_recall = retrieval.get("gold_id_recall_at_k")
    if passage_recall is None:
        passage_recall = retrieval.get("passage_id_recall_at_k")
    passage_recall = keyword_recall if passage_recall is None else _coerce_rate(passage_recall)
    full_coverage = _coerce_rate(retrieval.get("full_evidence_coverage_rate"))
    no_result_rate = _coerce_rate(retrieval.get("no_result_rate"))
    score = 100.0 * (
        0.10 * keyword_recall
        + 0.75 * passage_recall
        + 0.05 * full_coverage
        + 0.10 * (1.0 - no_result_rate)
    )
    return round(max(0.0, min(100.0, score)), 2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local RAG against downloaded external RAG/GraphRAG benchmarks.")
    parser.add_argument(
        "--benchmarks",
        nargs="+",
        default=list(DEFAULT_BENCHMARKS),
        help=(
            "Benchmarks to run: legal, graphrag-medical, graphrag-novel, "
            "ragbench-hotpotqa-validation."
        ),
    )
    parser.add_argument("--case-limit", type=int, default=50, help="Max cases per benchmark. <=0 means all cases.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--backend", default="sentence-transformer", help="Embedding backend for this benchmark run.")
    parser.add_argument("--model-name", default=DEFAULT_SENTENCE_TRANSFORMER_MODEL, help="Embedding model for this benchmark run.")
    parser.add_argument("--reranker", default=None, help="Search reranker override: none, noop, cross_encoder, or omitted for default.")
    parser.add_argument("--persist-root", type=Path, default=DEFAULT_PERSIST_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--run-name", default="", help="Optional run name. Defaults to timestamp.")
    parser.add_argument("--json", action="store_true", help="Print full aggregate JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = _safe_name(args.run_name) if args.run_name else datetime.now().strftime("%Y%m%d_%H%M%S")
    persist_dir = args.persist_root / run_id
    report_dir = args.report_dir
    case_limit = None if args.case_limit <= 0 else args.case_limit

    summaries: list[dict[str, Any]] = []
    for benchmark in args.benchmarks:
        suite = build_suite(benchmark, case_limit=case_limit)
        summary = run_suite(
            suite,
            persist_dir=persist_dir,
            report_dir=report_dir,
            collection_name=f"external_{_safe_name(suite.name)}_{run_id}",
            top_k=args.top_k,
            backend=args.backend,
            model_name=args.model_name,
            reranker=args.reranker,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
        summaries.append(summary)

    aggregate = build_aggregate_payload(
        run_id=run_id,
        summaries=summaries,
        persist_dir=persist_dir,
        report_dir=report_dir,
        top_k=args.top_k,
        case_limit=case_limit,
    )
    paths = write_aggregate_report(report_dir, aggregate)
    aggregate["aggregate_reports"] = {name: str(path) for name, path in paths.items()}

    if args.json:
        print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    else:
        print(
            "external_benchmark_score={score} cases={cases} benchmarks={benchmarks} report={report}".format(
                score=aggregate["overall_score_100"],
                cases=aggregate["total_cases"],
                benchmarks=len(summaries),
                report=aggregate["aggregate_reports"]["md"],
            )
        )
    return 0


def build_suite(name: str, *, case_limit: int | None) -> ExternalBenchmarkSuite:
    normalized = name.strip().lower()
    if normalized == "legal":
        return build_legal_rag_bench_suite(
            EXTERNAL_ROOT / "isaacus__legal-rag-bench",
            case_limit=case_limit,
        )
    if normalized == "graphrag-medical":
        return build_graphrag_bench_suite(
            EXTERNAL_ROOT / "GraphRAG-Bench__GraphRAG-Bench",
            domain="medical",
            case_limit=case_limit,
        )
    if normalized == "graphrag-novel":
        return build_graphrag_bench_suite(
            EXTERNAL_ROOT / "GraphRAG-Bench__GraphRAG-Bench",
            domain="novel",
            case_limit=case_limit,
        )
    if normalized == "ragbench-hotpotqa-validation":
        return build_ragbench_suite(
            EXTERNAL_ROOT / "galileo-ai__ragbench",
            dataset="hotpotqa",
            split="validation",
            case_limit=case_limit,
        )
    raise ValueError(f"Unsupported benchmark: {name}")


def run_suite(
    suite: ExternalBenchmarkSuite,
    *,
    persist_dir: Path,
    report_dir: Path,
    collection_name: str,
    top_k: int,
    backend: str,
    model_name: str | None,
    reranker: str | None,
    chunk_size: int,
    overlap: int,
) -> dict[str, Any]:
    chroma_persist_dir = repo_relative_path(persist_dir)
    ingest = ingest_source_payloads(
        payloads=suite.payloads,
        persist_dir=chroma_persist_dir,
        collection_name=collection_name,
        chunk_size=chunk_size,
        overlap=overlap,
        backend=backend,
        model_name=model_name,
        clean=False,
        parser_backend="auto",
    )
    rag = LocalChromaRegressionRag(
        persist_dir=chroma_persist_dir,
        collection_name=collection_name,
        top_k=top_k,
        backend=backend,
        model_name=model_name,
        reranker=reranker,
    )
    harness = RAGEvaluationHarness(
        rag,
        thresholds=EvaluationThresholds(
            min_keyword_recall_at_k=0.60,
            min_answer_completeness=0.60,
            max_missing_citation_rate=0.00,
            max_medium_or_high_risk_rate=0.50,
            max_no_result_rate=0.05,
        ),
        top_k=top_k,
    )
    report = harness.run(suite.cases, run_name=f"external_{suite.name}")
    paths = report.save(report_dir)
    payload = report.to_dict()
    score = score_suite_payload(payload)
    return {
        "benchmark": suite.name,
        "score_100": score,
        "score_band": score_band(score),
        "case_count": len(suite.cases),
        "payload_count": len(suite.payloads),
        "collection_name": collection_name,
        "ingest": {
            "chunks_written": ingest.get("chunks_written"),
            "records_extracted": ingest.get("records_extracted"),
            "embedding_backend": ingest.get("embedding_backend"),
            "embedding_model": ingest.get("embedding_model"),
            "quality_gate_status": (ingest.get("quality") or {}).get("quality_gate_status"),
        },
        "gate_status": report.gate_status,
        "gate_failures": report.gate_failures,
        "metrics": payload.get("metrics", {}),
        "reports": {name: str(path) for name, path in paths.items()},
        "notes": suite.notes,
    }


def build_aggregate_payload(
    *,
    run_id: str,
    summaries: list[dict[str, Any]],
    persist_dir: Path,
    report_dir: Path,
    top_k: int,
    case_limit: int | None,
) -> dict[str, Any]:
    total_cases = sum(int(summary["case_count"]) for summary in summaries)
    weighted_score = 0.0
    if total_cases:
        weighted_score = sum(float(summary["score_100"]) * int(summary["case_count"]) for summary in summaries) / total_cases
    return {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "score_type": "retrieval_first_score",
        "score_formula": (
            "100 * (0.10 * keyword_recall_at_k + 0.75 * gold_id_or_passage_id_recall_at_k_or_keyword_recall "
            "+ 0.05 * full_evidence_coverage_rate + 0.10 * (1 - no_result_rate))"
        ),
        "overall_score_100": round(weighted_score, 2),
        "overall_score_band": score_band(weighted_score),
        "total_cases": total_cases,
        "top_k": top_k,
        "case_limit_per_benchmark": case_limit,
        "persist_dir": str(persist_dir),
        "report_dir": str(report_dir),
        "benchmarks": summaries,
        "limitations": [
            "This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.",
            "It is not yet a full LLM generation quality score.",
            "Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.",
        ],
    }


def write_aggregate_report(report_dir: Path, payload: dict[str, Any]) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = f"external_benchmark_eval_{payload['run_id']}"
    json_path = report_dir / f"{stem}.json"
    md_path = report_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_aggregate_markdown(payload), encoding="utf-8")
    return {"json": json_path, "md": md_path}


def score_band(score: float) -> str:
    if score >= 85:
        return "strong"
    if score >= 70:
        return "usable"
    if score >= 50:
        return "weak"
    return "poor"


def repo_relative_path(path: Path, *, repo_root: Path = REPO_ROOT) -> Path:
    resolved = path.resolve()
    try:
        return Path(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return path


def _aggregate_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# External RAG Benchmark Evaluation",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Score type: `{payload['score_type']}`",
        f"- Overall score: **{payload['overall_score_100']} / 100** ({payload['overall_score_band']})",
        f"- Total cases: {payload['total_cases']}",
        f"- Top K: {payload['top_k']}",
        "",
        "## Benchmark Scores",
        "",
        "| Benchmark | Cases | Score | Band | Gate | Keyword recall | Gold id recall | Full coverage | No result rate | Report |",
        "| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for summary in payload["benchmarks"]:
        retrieval = (summary.get("metrics") or {}).get("retrieval") or {}
        lines.append(
            "| {benchmark} | {cases} | {score} | {band} | {gate} | {recall} | {gold_recall} | {full} | {no_result} | {report} |".format(
                benchmark=_md_cell(summary["benchmark"]),
                cases=summary["case_count"],
                score=summary["score_100"],
                band=_md_cell(summary["score_band"]),
                gate=_md_cell(summary["gate_status"]),
                recall=_md_cell(retrieval.get("keyword_recall_at_k")),
                gold_recall=_md_cell(retrieval.get("gold_id_recall_at_k") or retrieval.get("passage_id_recall_at_k")),
                full=_md_cell(retrieval.get("full_evidence_coverage_rate")),
                no_result=_md_cell(retrieval.get("no_result_rate")),
                report=_md_cell(summary["reports"]["md"]),
            )
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in payload["limitations"])
    return "\n".join(lines).rstrip() + "\n"


def _coerce_rate(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", value.strip())
    return safe.strip("._-") or "run"


def _md_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
