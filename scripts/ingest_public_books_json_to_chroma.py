from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from chroma_rag_poc.pipeline import DEFAULT_PERSIST_DIR
from chroma_rag_poc.public_books_json import ingest_latest_snapshot_to_chroma, write_ingest_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest the latest public-books Label Studio JSON snapshot into ChromaDB.",
    )
    parser.add_argument("--input-root", required=True, help="Directory containing Label Studio JSON snapshots.")
    parser.add_argument(
        "--persist-dir",
        default=str(DEFAULT_PERSIST_DIR),
        help="ChromaDB persistence directory.",
    )
    parser.add_argument("--collection", default="public_books_labelstudio", help="Target Chroma collection name.")
    parser.add_argument(
        "--mode",
        choices=["create", "append"],
        default="append",
        help="create deletes/rebuilds the collection; append upserts into the existing collection.",
    )
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument(
        "--report-dir",
        default=str(REPO_ROOT / "data_pipeline" / "reports"),
        help="Directory for local ingest summary files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = ingest_latest_snapshot_to_chroma(
        input_root=args.input_root,
        persist_dir=args.persist_dir,
        collection_name=args.collection,
        mode=args.mode,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    summary["summary_files"] = write_ingest_summary(summary, args.report_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
