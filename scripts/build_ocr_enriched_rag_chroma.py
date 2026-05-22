from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "Lib" / "site-packages"
POC_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
SCRIPTS_DIR = REPO_ROOT / "scripts"

for path in (str(SITE_PACKAGES), str(POC_SRC), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import chromadb  # noqa: E402
from chromadb.config import Settings  # noqa: E402

from chroma_rag_poc.chunking import split_text_with_overlap  # noqa: E402
from chroma_rag_poc.embeddings import HashingEmbeddingFunction  # noqa: E402
from chroma_rag_poc.pipeline import _close_client  # noqa: E402
from build_representative_rag_chroma import (  # noqa: E402
    JsonLogger,
    build_pdf_documents,
    build_qa_documents,
    find_extractable_pdf,
    metadata_value,
    stable_id,
    storage_size_bytes,
    truncate,
)


OCR_ROOT = REPO_ROOT / "data_pipeline" / "ocr" / "tsinghua_gas_turbine_books"
OUT_DIR = REPO_ROOT / "storage_layer" / "runtime" / "ocr_enriched_rag_chroma"
LOG_DIR = REPO_ROOT / "observability" / "logs" / "ocr_enriched_chroma"
DOCS_PATH = REPO_ROOT / "docs" / "ocr_enriched_rag_chroma_build.md"
COLLECTION_NAME = "gas_turbine_ocr_enriched_rag"
EMBEDDING_DIMENSION = 384


os.chdir(REPO_ROOT)


def chroma_path_arg(path: Path) -> str:
    """Use a repo-relative ASCII path so hnswlib can persist on Windows Chinese paths."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(resolved)


@dataclass(slots=True)
class DocRecord:
    doc_id: str
    text: str
    metadata: dict[str, str | int | float | bool]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def reset_output_dir(path: Path) -> None:
    target = path.resolve()
    expected = OUT_DIR.resolve()
    if target != expected:
        raise ValueError(f"Refusing to reset unexpected path: {target}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def load_ocr_documents(max_pages_per_pdf: int, chunk_size: int, overlap: int) -> tuple[list[DocRecord], dict[str, Any]]:
    docs: list[DocRecord] = []
    manifests: list[dict[str, Any]] = []
    if not OCR_ROOT.exists():
        raise FileNotFoundError(f"OCR root does not exist: {OCR_ROOT}. Run scripts/ocr_scanned_pdfs.py first.")

    for manifest_path in sorted(OCR_ROOT.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pages_path = Path(manifest["pages_jsonl"])
        source_file = str(manifest["source_file"])
        pages_loaded = 0
        pages_with_text = 0
        chars_loaded = 0
        with pages_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                page = json.loads(line)
                page_num = int(page["page_num"])
                if max_pages_per_pdf and page_num > max_pages_per_pdf:
                    continue
                text = normalize_space(str(page.get("text") or ""))
                pages_loaded += 1
                if not text:
                    continue
                pages_with_text += 1
                chars_loaded += len(text)
                chunks = split_text_with_overlap(text, chunk_size=chunk_size, overlap=overlap)
                for chunk_index, chunk in enumerate(chunks):
                    docs.append(
                        DocRecord(
                            doc_id=stable_id("ocr", source_file, page_num, chunk_index, chunk[:120]),
                            text=chunk,
                            metadata={
                                "source_file": source_file,
                                "source_type": "ocr_pdf",
                                "ocr_output_dir": metadata_value(manifest.get("output_dir")),
                                "page_num": page_num,
                                "chunk_index": chunk_index,
                                "line_count": int(page.get("line_count") or 0),
                                "avg_confidence": float(page.get("avg_confidence") or 0.0),
                                "evidence": truncate(chunk, 500),
                                "context": truncate(chunk, 500),
                                "char_count": len(chunk),
                            },
                        )
                    )

        manifests.append(
            {
                "source_file": source_file,
                "pages_loaded": pages_loaded,
                "pages_with_text": pages_with_text,
                "chars_loaded": chars_loaded,
                "chunks": sum(1 for doc in docs if doc.metadata.get("source_file") == source_file),
                "manifest": str(manifest_path),
            }
        )

    if not docs:
        raise RuntimeError(f"No OCR documents were loaded from {OCR_ROOT}.")

    return docs, {
        "ocr_pdf_count": len(manifests),
        "ocr_pages_loaded": sum(item["pages_loaded"] for item in manifests),
        "ocr_pages_with_text": sum(item["pages_with_text"] for item in manifests),
        "ocr_chars_loaded": sum(item["chars_loaded"] for item in manifests),
        "ocr_chunks": len(docs),
        "ocr_sources": manifests,
    }


def add_documents(
    collection: Any,
    docs: list[Any],
    embedder: HashingEmbeddingFunction,
    logger: JsonLogger,
    batch_size: int,
) -> None:
    for start in range(0, len(docs), batch_size):
        batch = docs[start : start + batch_size]
        try:
            embeddings = embedder([doc.text for doc in batch])
            collection.add(
                ids=[doc.doc_id for doc in batch],
                documents=[doc.text for doc in batch],
                metadatas=[doc.metadata for doc in batch],
                embeddings=embeddings,
            )
        except Exception as exc:
            logger.write(
                "chroma_add_failed",
                start=start,
                count=len(batch),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise
        logger.write("chroma_add_batch", start=start, count=len(batch))


def verify_persisted_count(path: Path, collection_name: str) -> int:
    client = chromadb.PersistentClient(
        path=chroma_path_arg(path),
        settings=Settings(anonymized_telemetry=False, is_persistent=True),
    )
    try:
        collection = client.get_collection(collection_name)
        return int(collection.count())
    finally:
        _close_client(client)


def write_docs(summary: dict[str, Any]) -> None:
    lines = [
        "# OCR-enriched ordinary RAG ChromaDB build",
        "",
        "This library extends the representative ordinary RAG baseline with OCR text from scanned PDFs.",
        "",
        "## Build output",
        "",
        f"- Library path: `{summary['library_dir']}`",
        f"- Collection: `{summary['collection']}`",
        f"- Collection count: {summary['collection_count']}",
        f"- QA chunks: {summary['qa_chunks']}",
        f"- Direct PDF chunks: {summary['direct_pdf_chunks']}",
        f"- OCR PDF chunks: {summary['ocr_chunks']}",
        f"- OCR PDFs loaded: {summary['ocr_stats']['ocr_pdf_count']}",
        f"- OCR pages with text: {summary['ocr_stats']['ocr_pages_with_text']}",
        f"- OCR chars loaded: {summary['ocr_stats']['ocr_chars_loaded']}",
        "",
        "## Boundary",
        "",
        "The library still uses local hashing embedding, so it proves ingestion/query plumbing, not final semantic retrieval quality.",
    ]
    DOCS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_library(args: argparse.Namespace, logger: JsonLogger) -> dict[str, Any]:
    logger.write(
        "build_start",
        output_dir=str(OUT_DIR),
        collection=COLLECTION_NAME,
        qa_limit=args.qa_limit,
        direct_pdf_pages=args.direct_pdf_pages,
        ocr_max_pages_per_pdf=args.ocr_max_pages_per_pdf,
    )
    qa_docs = build_qa_documents(args.qa_limit, args.chunk_size, args.overlap)
    pdf_docs, pdf_stats = build_pdf_documents(
        pdf_path=find_extractable_pdf(),
        max_pages=args.direct_pdf_pages,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        logger=logger,
    )
    ocr_docs, ocr_stats = load_ocr_documents(args.ocr_max_pages_per_pdf, args.chunk_size, args.overlap)
    docs = qa_docs + pdf_docs + ocr_docs
    if not docs:
        raise RuntimeError("No documents generated for OCR-enriched Chroma ingestion.")

    reset_output_dir(OUT_DIR)
    embedder = HashingEmbeddingFunction(dimension=EMBEDDING_DIMENSION)
    client = chromadb.PersistentClient(
        path=chroma_path_arg(OUT_DIR),
        settings=Settings(anonymized_telemetry=False, is_persistent=True),
    )
    try:
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={
                "description": "OCR-enriched ordinary RAG library from gas turbine QA JSONL, direct PDF text, and OCR scanned PDF text.",
                "embedding_backend": HashingEmbeddingFunction.name(),
                "embedding_dimension": EMBEDDING_DIMENSION,
                "created_by": "scripts/build_ocr_enriched_rag_chroma.py",
            },
        )
        add_documents(collection, docs, embedder, logger, args.batch_size)
        count = collection.count()
        if count <= 0:
            raise RuntimeError(f"Collection count must be > 0, got {count}.")
    finally:
        _close_client(client)

    persisted_count = verify_persisted_count(OUT_DIR, COLLECTION_NAME)
    if persisted_count <= 0:
        raise RuntimeError(f"Persisted collection count must be > 0, got {persisted_count}.")
    if persisted_count != count:
        raise RuntimeError(f"Persisted count mismatch: in-process={count}, reopened={persisted_count}.")

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "library_dir": str(OUT_DIR),
        "collection": COLLECTION_NAME,
        "collection_count": count,
        "persisted_collection_count": persisted_count,
        "qa_chunks": len(qa_docs),
        "direct_pdf_chunks": len(pdf_docs),
        "ocr_chunks": len(ocr_docs),
        "embedding_backend": HashingEmbeddingFunction.name(),
        "embedding_dimension": EMBEDDING_DIMENSION,
        "chunk_size": args.chunk_size,
        "overlap": args.overlap,
        "direct_pdf_stats": pdf_stats,
        "ocr_stats": ocr_stats,
        "storage_bytes": storage_size_bytes(OUT_DIR),
        "boundary": "Hashing embedding is deterministic/offline and is not the final retrieval-quality embedding.",
    }
    (OUT_DIR / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_docs(summary)
    logger.write("build_done", **summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an OCR-enriched ordinary RAG ChromaDB library.")
    parser.add_argument("--qa-limit", type=int, default=240)
    parser.add_argument("--direct-pdf-pages", type=int, default=80)
    parser.add_argument("--ocr-max-pages-per-pdf", type=int, default=0, help="0 means all OCR pages.")
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=80)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = JsonLogger(LOG_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-ocr-enriched-rag-chroma.jsonl")
    started = time.perf_counter()
    try:
        summary = build_library(args, logger)
    except Exception as exc:
        logger.write(
            "build_failed",
            elapsed_s=round(time.perf_counter() - started, 3),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise
    summary["elapsed_s"] = round(time.perf_counter() - started, 3)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
