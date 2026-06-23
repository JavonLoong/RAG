from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.smoke import SMOKE_COLLECTION, run_ingest_search_evaluation_smoke


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a tiny ingest-search-evaluation smoke path.")
    parser.add_argument("--persist-dir", type=Path, default=REPO_ROOT / "outputs" / "smoke_chroma")
    parser.add_argument("--report-dir", type=Path, default=REPO_ROOT / "evaluation" / "reports")
    parser.add_argument("--collection", default=SMOKE_COLLECTION)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="Print the full result payload as JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_ingest_search_evaluation_smoke(
        persist_dir=args.persist_dir,
        report_dir=args.report_dir,
        collection_name=args.collection,
        top_k=args.top_k,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            "gate_status={status} graphrag_query={graphrag_status} graphrag_global={global_status} chunks_written={chunks} search_results={results} report_json={json_path}".format(
                status=result["evaluation"]["gate_status"],
                graphrag_status="pass" if result["graphrag_query"].get("passed") else "fail",
                global_status="pass" if result["graphrag_global_answer"].get("passed") else "fail",
                chunks=result["ingest"]["chunks_written"],
                results=len(result["search"]["results"]),
                json_path=result["reports"]["json"],
            )
        )
    smoke_passed = (
        result["evaluation"]["gate_status"] == "pass"
        and bool(result["graphrag_query"].get("passed"))
        and bool(result["graphrag_global_answer"].get("passed"))
    )
    return 0 if smoke_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
