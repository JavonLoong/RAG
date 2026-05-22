from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "Lib" / "site-packages"
POC_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"

for path in (str(REPO_ROOT), str(SITE_PACKAGES), str(POC_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from rag_orchestrator.adapters import ChromaTextRetriever, CommandLLM, SQLiteGraphRetriever  # noqa: E402
from rag_orchestrator.graphrag_qa import GraphRagConfigurationError, GraphRagQAOrchestrator  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run minimal GraphRAG QA: text retrieval + graph retrieval + explicit LLM generation.",
    )
    parser.add_argument("--question", required=True, help="User question to answer.")
    parser.add_argument("--chroma-path", required=True, help="ChromaDB persistent directory or chroma.sqlite3 path.")
    parser.add_argument(
        "--graph-store-sqlite-path",
        "--graph-path",
        dest="graph_store_sqlite_path",
        required=True,
        help="SQLite graph store path containing triples/relationships/edges.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Number of text and graph results to retrieve.")
    parser.add_argument("--format", choices=("json", "md"), default="json", help="Output format.")
    parser.add_argument("--output", default="", help="Optional output file. Defaults to stdout.")
    parser.add_argument("--collection", default="", help="Chroma collection name. Required when multiple exist.")
    parser.add_argument("--graph-table", default="", help="SQLite table name. Defaults to auto-detection.")
    parser.add_argument(
        "--context-only",
        action="store_true",
        help="Show retrieved context only. This does not generate an LLM answer.",
    )
    parser.add_argument(
        "--llm-command",
        default=os.environ.get("GRAPHRAG_QA_LLM_COMMAND", ""),
        help=(
            "Command used as the LLM adapter. The prompt is sent on stdin and stdout is used as the answer. "
            "Can also be set with GRAPHRAG_QA_LLM_COMMAND."
        ),
    )
    parser.add_argument("--llm-timeout", type=int, default=120, help="LLM command timeout in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    llm = None
    if args.llm_command:
        llm = CommandLLM(args.llm_command, timeout_seconds=args.llm_timeout)

    try:
        text_retriever = ChromaTextRetriever(
            args.chroma_path,
            collection_name=args.collection or None,
        )
        graph_retriever = SQLiteGraphRetriever(
            args.graph_store_sqlite_path,
            table_name=args.graph_table or None,
        )
        orchestrator = GraphRagQAOrchestrator(
            text_retriever=text_retriever,
            graph_retriever=graph_retriever,
            llm=llm,
        )
        result = orchestrator.answer(
            args.question,
            top_k=args.top_k,
            context_only=args.context_only,
        )
    except GraphRagConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    rendered = render_markdown(result.to_dict()) if args.format == "md" else json.dumps(
        result.to_dict(),
        ensure_ascii=False,
        indent=2,
    )
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# GraphRAG QA",
        "",
        f"**Question:** {payload['question']}",
        "",
    ]
    if payload["context_only"]:
        lines.extend(
            [
                "**Context-only debug mode:** no LLM answer was generated.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Answer",
                "",
                str(payload["answer"] or ""),
                "",
            ]
        )

    lines.extend(["## Citations", ""])
    citations = payload.get("citations") or []
    if citations:
        for citation in citations:
            source = citation.get("source") or "unknown source"
            score = citation.get("score")
            score_text = f", score={score:.4g}" if isinstance(score, int | float) else ""
            lines.append(
                f"- [{citation['id']}] {citation['source_type']} evidence from {source}{score_text}"
            )
    else:
        lines.append("- No citations returned.")

    lines.extend(["", "## Retrieved Context", "", str(payload["context"])])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
