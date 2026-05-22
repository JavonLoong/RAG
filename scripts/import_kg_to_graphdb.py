from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from storage_layer.graph_store import import_kg_file


DEFAULT_INPUT = PROJECT_ROOT / "kg_pipeline" / "experiments" / "four_books_kg_construction" / "poc_run" / "triples.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "storage_layer" / "runtime" / "four_books_graph_store"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import triples.json or graph.json into a local SQLite graph store and emit a Neo4j Cypher file.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Path to triples.json or graph.json. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for generated graph store artifacts. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help="SQLite graph store path. Default: <output-dir>/graph_store.sqlite",
    )
    parser.add_argument(
        "--cypher",
        type=Path,
        default=None,
        help="Neo4j Cypher output path. Default: <output-dir>/neo4j_import.cypher",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Import summary JSON path. Default: <output-dir>/import_summary.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_dir = args.output_dir
    sqlite_path = args.sqlite or output_dir / "graph_store.sqlite"
    cypher_path = args.cypher or output_dir / "neo4j_import.cypher"
    summary_path = args.summary or output_dir / "import_summary.json"

    summary = import_kg_file(args.input, sqlite_path, cypher_path)
    summary["summary_path"] = str(summary_path)

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
