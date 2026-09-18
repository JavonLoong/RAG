from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation import LocalChromaRegressionRag, run_graphrag_triage_regression


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run promoted GraphRAG triage regression cases.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "outputs" / "smoke_chroma" / "evaluation" / "graphrag_triage_regression.jsonl",
    )
    parser.add_argument("--report-dir", type=Path, default=REPO_ROOT / "evaluation" / "reports")
    parser.add_argument("--persist-dir", type=Path, default=REPO_ROOT / "outputs" / "smoke_chroma")
    parser.add_argument("--collection", default="", help="Chroma collection name; defaults to the first non-empty collection.")
    parser.add_argument("--backend", default=None, help="Embedding backend override for querying, for example 'hashing'.")
    parser.add_argument("--model-name", default=None, help="Embedding model override for querying.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--allow-empty", action="store_true", help="Return success when no promoted cases exist.")
    parser.add_argument("--json", action="store_true", help="Print the full result payload as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rag = LocalChromaRegressionRag(
        persist_dir=args.persist_dir,
        collection_name=args.collection,
        top_k=args.top_k,
        backend=args.backend,
        model_name=args.model_name,
    )
    result = run_graphrag_triage_regression(
        rag_system=rag,
        dataset_path=args.dataset,
        report_dir=args.report_dir,
        top_k=args.top_k,
    )
    if result["status"] == "skipped" and not args.allow_empty:
        result["gate_status"] = "fail"
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "triage_regression={status} case_count={case_count} dataset={dataset}".format(
                status="pass" if result["gate_status"] == "pass" else "fail",
                case_count=result["case_count"],
                dataset=result["dataset_path"],
            )
        )
    return 0 if result["gate_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
