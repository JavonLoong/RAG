from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "Lib" / "site-packages"
POC_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"

for path in (str(SITE_PACKAGES), str(POC_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

import chromadb  # noqa: E402
from chromadb.config import Settings  # noqa: E402

from chroma_rag_poc.embeddings import HashingEmbeddingFunction  # noqa: E402


DEFAULT_LIBRARY = REPO_ROOT / "storage_layer" / "runtime" / "representative_rag_chroma"
DEFAULT_COLLECTION = "gas_turbine_representative_rag"
DEFAULT_QUESTIONS = REPO_ROOT / "evaluation" / "retrieval_smoke_questions.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "evaluation" / "reports"


os.chdir(REPO_ROOT)


def chroma_path_arg(path: Path) -> str:
    """Use repo-relative ASCII paths to avoid hnswlib failures on Windows Chinese paths."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(resolved)


def load_questions(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Questions file must be a JSON list: {path}")

    questions: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, str):
            question = item.strip()
            question_id = f"rq{index:03d}"
            topic = ""
        elif isinstance(item, dict):
            question = str(item.get("question", "")).strip()
            question_id = str(item.get("id") or f"rq{index:03d}").strip()
            topic = str(item.get("topic", "")).strip()
            required_terms = [str(term).strip() for term in item.get("required_terms", []) if str(term).strip()]
            expected_terms = [str(term).strip() for term in item.get("expected_terms", []) if str(term).strip()]
        else:
            raise ValueError(f"Question #{index} must be a string or object.")

        if not question:
            raise ValueError(f"Question #{index} is empty.")
        if isinstance(item, str):
            required_terms = []
            expected_terms = []
        questions.append(
            {
                "id": question_id,
                "topic": topic,
                "question": question,
                "required_terms": required_terms,
                "expected_terms": expected_terms,
            }
        )
    return questions


def normalize_library(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate


def require_collection(library: Path, collection_name: str) -> Any:
    if not library.exists():
        raise FileNotFoundError(
            "Representative ChromaDB library does not exist: "
            f"{library}\n"
            "Please run the representative RAG build script first. Expected collection: "
            f"{collection_name}"
        )

    client = chromadb.PersistentClient(
        path=chroma_path_arg(library),
        settings=Settings(anonymized_telemetry=False, is_persistent=True),
    )
    try:
        return client.get_collection(collection_name)
    except Exception as exc:
        raise LookupError(
            "Representative ChromaDB collection does not exist: "
            f"{collection_name} in {library}\n"
            "Please run the representative RAG build script first and keep the configured "
            "collection name unchanged."
        ) from exc


def compact_text(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def metadata_page_or_evidence(metadata: dict[str, Any]) -> str:
    evidence = metadata.get("evidence") or metadata.get("supporting_evidence")
    if evidence:
        return compact_text(evidence, 180)

    page = metadata.get("page_num")
    if page in (None, ""):
        page = metadata.get("page_nums")
    if page not in (None, ""):
        return f"page={page}"
    return ""


def classify_result(question: dict[str, Any], hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "需要改进"

    top_hit = hits[0]
    has_traceable_top_hit = bool(
        top_hit.get("source_file") and top_hit.get("page_or_evidence") and top_hit.get("preview")
    )
    required_terms = [str(term).lower() for term in question.get("required_terms", []) if str(term).strip()]
    expected_terms = [str(term).lower() for term in question.get("expected_terms", []) if str(term).strip()]
    top_hit_text = (
        str(top_hit.get("preview", "")) + " " + str(top_hit.get("page_or_evidence", ""))
    ).lower()
    matched_terms = [term for term in expected_terms if term in top_hit_text]
    matched_required = [term for term in required_terms if term in top_hit_text]

    if has_traceable_top_hit and expected_terms and matched_terms and (not required_terms or matched_required):
        return "能检索到证据"
    if has_traceable_top_hit and not expected_terms:
        return "结果弱"
    if any(hit.get("source_file") or hit.get("preview") for hit in hits):
        return "结果弱"
    return "需要改进"


def run_queries(collection: Any, questions: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    embedder = HashingEmbeddingFunction(dimension=384)
    results: list[dict[str, Any]] = []

    for question in questions:
        query_result = collection.query(
            query_embeddings=[embedder.embed_query(question["question"])],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        ids = query_result.get("ids", [[]])[0]
        documents = query_result.get("documents", [[]])[0]
        metadatas = query_result.get("metadatas", [[]])[0]
        distances = query_result.get("distances", [[]])[0]

        hits: list[dict[str, Any]] = []
        for rank, (doc_id, document, metadata, distance) in enumerate(
            zip(ids, documents, metadatas, distances),
            start=1,
        ):
            metadata = metadata or {}
            hits.append(
                {
                    "rank": rank,
                    "id": doc_id,
                    "distance": distance,
                    "source_file": metadata.get("source_file") or metadata.get("filename") or "",
                    "page_or_evidence": metadata_page_or_evidence(metadata),
                    "preview": compact_text(document, 260),
                }
            )

        results.append(
            {
                "id": question["id"],
                "topic": question["topic"],
                "question": question["question"],
                "required_terms": question.get("required_terms", []),
                "expected_terms": question.get("expected_terms", []),
                "status": classify_result(question, hits),
                "hits": hits,
            }
        )

    return results


def markdown_cell(value: Any) -> str:
    text = compact_text(value, 160)
    return text.replace("|", "\\|")


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Retrieval Smoke Test",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Library: `{payload['library']}`",
        f"- Collection: `{payload['collection']}`",
        f"- Collection count: {payload['collection_count']}",
        f"- Top K: {payload['top_k']}",
        "",
        "## Summary",
        "",
        "| ID | 问题 | 判断 | Top1 distance | 来源 | 页码/证据 | Top1 preview |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for item in payload["results"]:
        top_hit = item["hits"][0] if item["hits"] else {}
        distance = top_hit.get("distance", "")
        if isinstance(distance, float):
            distance = f"{distance:.6f}"
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(item["id"]),
                    markdown_cell(item["question"]),
                    markdown_cell(item["status"]),
                    markdown_cell(distance),
                    markdown_cell(top_hit.get("source_file", "")),
                    markdown_cell(top_hit.get("page_or_evidence", "")),
                    markdown_cell(top_hit.get("preview", "")),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Hits", ""])
    for item in payload["results"]:
        lines.extend(
            [
                f"### {item['id']} {item['question']}",
                "",
                f"- 判断: {item['status']}",
                "",
                "| Rank | Doc ID | Distance | Source file | Page/Evidence | Preview |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        if not item["hits"]:
            lines.append("| - | - | - | - | - | - |")
            lines.append("")
            continue
        for hit in item["hits"]:
            distance = hit.get("distance", "")
            if isinstance(distance, float):
                distance = f"{distance:.6f}"
            lines.append(
                "| "
                + " | ".join(
                    [
                        markdown_cell(hit["rank"]),
                        markdown_cell(hit["id"]),
                        markdown_cell(distance),
                        markdown_cell(hit["source_file"]),
                        markdown_cell(hit["page_or_evidence"]),
                        markdown_cell(hit["preview"]),
                    ]
                )
                + " |"
            )
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a small retrieval smoke test against the representative gas-turbine ChromaDB."
    )
    parser.add_argument("--library", default=str(DEFAULT_LIBRARY), help="Representative ChromaDB directory.")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="Representative collection name.")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS), help="Smoke questions JSON file.")
    parser.add_argument("--top-k", type=int, default=3, help="Number of hits per question.")
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR), help="Report output directory.")
    args = parser.parse_args()

    if args.top_k <= 0:
        raise ValueError("--top-k must be greater than 0.")

    library = normalize_library(args.library)
    questions_path = normalize_library(args.questions)
    output_dir = normalize_library(args.output_dir)

    questions = load_questions(questions_path)
    collection = require_collection(library, args.collection)
    collection_count = collection.count()
    results = run_queries(collection, questions, args.top_k)

    generated_at = datetime.now().isoformat(timespec="seconds")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "generated_at": generated_at,
        "library": str(library),
        "collection": args.collection,
        "collection_count": collection_count,
        "top_k": args.top_k,
        "questions_file": str(questions_path),
        "results": results,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_report = output_dir / f"retrieval_smoke_test_{stamp}.json"
    markdown_report = output_dir / f"retrieval_smoke_test_{stamp}.md"
    write_json_report(json_report, payload)
    write_markdown_report(markdown_report, payload)

    print(f"Wrote JSON report: {json_report}")
    print(f"Wrote Markdown report: {markdown_report}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, LookupError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
