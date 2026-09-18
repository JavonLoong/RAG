"""Generate the evidence-backed PowerRAG PRD acceptance package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.prd_acceptance import write_acceptance_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = write_acceptance_package(args.input_dir, args.output_dir)
    print(json.dumps({"overall_status": result["overall_status"], "package_dir": result["package_dir"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
