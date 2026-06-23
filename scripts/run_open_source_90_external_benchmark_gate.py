from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation import (  # noqa: E402
    benchmark_gate_to_json,
    evaluate_external_benchmark_gate,
    render_external_benchmark_gate_markdown,
)
from scripts.run_external_benchmark_evaluation import (  # noqa: E402
    DEFAULT_PERSIST_ROOT,
    DEFAULT_REPORT_DIR,
    build_aggregate_payload,
    build_suite,
    run_suite,
    write_aggregate_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run external benchmark gate against the open_source_90 profile.")
    parser.add_argument("--benchmarks", nargs="+", default=["legal", "ragbench-hotpotqa-validation"])
    parser.add_argument("--case-limit", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--backend", default="hashing")
    parser.add_argument("--model-name", default="")
    parser.add_argument("--reranker", default="auto", help="auto, none, noop, or cross_encoder.")
    parser.add_argument("--persist-root", type=Path, default=DEFAULT_PERSIST_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--run-name", default="")
    parser.add_argument("--allow-fail", action="store_true", help="Write reports and return 0 even when the gate fails.")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = _safe_run_id(args.run_name or f"open_source_90_external_{datetime.now():%Y%m%d_%H%M%S}")
    persist_dir = args.persist_root / run_id
    case_limit = None if args.case_limit <= 0 else args.case_limit
    model_name = args.model_name.strip() or None

    summaries = []
    for benchmark in args.benchmarks:
        suite = build_suite(benchmark, case_limit=case_limit)
        selected_reranker = select_open_source_90_reranker(benchmark, args.reranker)
        summaries.append(
            run_suite(
                suite,
                persist_dir=persist_dir,
                report_dir=args.report_dir,
                collection_name=f"external_{_safe_run_id(suite.name)}_{run_id}",
                top_k=args.top_k,
                backend=args.backend,
                model_name=model_name,
                reranker=selected_reranker,
                chunk_size=args.chunk_size,
                overlap=args.overlap,
            )
        )

    aggregate = build_aggregate_payload(
        run_id=run_id,
        summaries=summaries,
        persist_dir=persist_dir,
        report_dir=args.report_dir,
        top_k=args.top_k,
        case_limit=case_limit,
    )
    aggregate_paths = write_aggregate_report(args.report_dir, aggregate)
    aggregate["aggregate_reports"] = {name: str(path) for name, path in aggregate_paths.items()}

    gate = evaluate_external_benchmark_gate(aggregate)
    gate_paths = write_gate_report(args.report_dir, run_id, aggregate, gate)
    result = {
        "status": gate.status,
        "overall_score_100": gate.overall_score_100,
        "total_cases": gate.total_cases,
        "aggregate_reports": aggregate["aggregate_reports"],
        "gate_reports": {name: str(path) for name, path in gate_paths.items()},
        "failure_count": len(gate.failures),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "open_source_90_external_gate={status} score={score} cases={cases} failures={failures} report={report}".format(
                status=gate.status,
                score=gate.overall_score_100,
                cases=gate.total_cases,
                failures=len(gate.failures),
                report=result["gate_reports"]["md"],
            )
        )
    if gate.status == "pass" or args.allow_fail:
        return 0
    return 2


def select_open_source_90_reranker(benchmark: str, configured: str | None) -> str | None:
    normalized = (configured or "auto").strip().lower().replace("-", "_")
    if normalized not in {"", "auto"}:
        return normalized
    benchmark_name = benchmark.strip().lower()
    if benchmark_name.startswith("ragbench") or "hotpotqa" in benchmark_name:
        return "cross_encoder"
    return "none"


def write_gate_report(report_dir: Path, run_id: str, aggregate: dict, gate) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = f"open_source_90_external_benchmark_gate_{run_id}"
    json_path = report_dir / f"{stem}.json"
    md_path = report_dir / f"{stem}.md"
    json_path.write_text(benchmark_gate_to_json(aggregate, gate), encoding="utf-8")
    md_path.write_text(render_external_benchmark_gate_markdown(aggregate, gate), encoding="utf-8")
    return {"json": json_path, "md": md_path}


def _safe_run_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value.strip())
    return safe.strip("._-") or "open_source_90_external"


if __name__ == "__main__":
    raise SystemExit(main())
