"""Compare governed local OCR results with optional Baidu Cloud OCR results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.ocr_benchmark import run_ocr_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Benchmark manifest JSON path")
    parser.add_argument("--output-dir", required=True, help="Directory for JSON and Markdown reports")
    parser.add_argument(
        "--include-cloud",
        action="store_true",
        help="Call Baidu OCR for samples explicitly marked external_allowed=true",
    )
    parser.add_argument(
        "--price-per-cloud-call",
        type=float,
        default=None,
        help="Optional actual account price used only for an estimated cost",
    )
    args = parser.parse_args()
    report = run_ocr_benchmark(
        args.manifest,
        args.output_dir,
        include_cloud=args.include_cloud,
        price_per_cloud_call=args.price_per_cloud_call,
    )
    print(
        json.dumps(
            {
                "json": str(Path(args.output_dir).resolve() / "ocr_benchmark.json"),
                "markdown": str(Path(args.output_dir).resolve() / "ocr_benchmark.md"),
                "summary": report["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
