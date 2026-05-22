from __future__ import annotations

import argparse
import hashlib
import json
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

for path in (str(SITE_PACKAGES), str(POC_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

import chromadb  # noqa: E402
from chromadb.config import Settings  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from chroma_rag_poc.chunking import split_text_with_overlap  # noqa: E402
from chroma_rag_poc.embeddings import HashingEmbeddingFunction  # noqa: E402


RAW_DIR = REPO_ROOT / "data_pipeline" / "raw" / "tsinghua_gas_turbine_books"
QA_JSONL = RAW_DIR / "canonical_qa_auto_13423.jsonl"
OUT_DIR = REPO_ROOT / "storage_layer" / "runtime" / "representative_rag_chroma"
LOG_DIR = REPO_ROOT / "observability" / "logs" / "representative_chroma"
COLLECTION_NAME = "gas_turbine_representative_rag"
PDF_NAME_KEYWORD = "燃气-蒸汽联合循环发电机组运行技术问答"
EMBEDDING_DIMENSION = 384


@dataclass(slots=True)
class DocRecord:
    doc_id: str
    text: str
    metadata: dict[str, str | int | float | bool]


class JsonLogger:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **fields: Any) -> None:
        payload = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            **fields,
        }
        line = json.dumps(payload, ensure_ascii=False)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        print(line)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def truncate(text: str, limit: int) -> str:
    text = normalize_space(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def stable_id(*parts: object) -> str:
    raw = "||".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:28]


def metadata_value(value: Any) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def reset_output_dir(path: Path) -> None:
    target = path.resolve()
    expected = OUT_DIR.resolve()
    if target != expected:
        raise ValueError(f"Refusing to reset unexpected path: {target}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def read_jsonl_records(path: Path, limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_num, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_num}: {exc}") from exc
            if len(records) >= limit:
                break
    return records


def build_qa_documents(limit: int, chunk_size: int, overlap: int) -> list[DocRecord]:
    docs: list[DocRecord] = []
    for row in read_jsonl_records(QA_JSONL, limit=limit):
        qa_id = str(row.get("id") or stable_id("qa", len(docs)))
        meta = row.get("metadata") or {}
        evidence = str(meta.get("supporting_evidence") or "")
        context = str(row.get("context") or "")
        composed = "\n".join(
            part
            for part in (
                f"Question: {row.get('question', '')}",
                f"Answer: {row.get('answer', '')}",
                f"Evidence: {evidence}",
                f"Context: {truncate(context, 1200)}",
            )
            if normalize_space(part)
        )
        chunks = split_text_with_overlap(composed, chunk_size=chunk_size, overlap=overlap)
        for chunk_index, chunk in enumerate(chunks):
            docs.append(
                DocRecord(
                    doc_id=f"{qa_id}::chunk_{chunk_index:03d}",
                    text=chunk,
                    metadata={
                        "source_file": QA_JSONL.name,
                        "source_type": "qa_jsonl",
                        "qa_id": qa_id,
                        "chunk_index": chunk_index,
                        "source_pages": metadata_value(row.get("source_pages")),
                        "original_source": metadata_value(row.get("source")),
                        "question_type": metadata_value(row.get("question_type")),
                        "difficulty": metadata_value(row.get("difficulty")),
                        "split": metadata_value(row.get("split")),
                        "evidence": truncate(evidence, 500),
                        "context": truncate(context, 500),
                        "char_count": len(chunk),
                    },
                )
            )
    return docs


def find_extractable_pdf() -> Path:
    preferred = sorted(path for path in RAW_DIR.glob("*.pdf") if PDF_NAME_KEYWORD in path.name)
    if preferred:
        return preferred[0]
    for path in sorted(RAW_DIR.glob("*.pdf")):
        reader = PdfReader(str(path))
        if any(normalize_space(page.extract_text() or "") for page in reader.pages[:5]):
            return path
    raise FileNotFoundError("No PDF with extractable text was found in the raw materials.")


def build_pdf_documents(
    pdf_path: Path,
    max_pages: int,
    chunk_size: int,
    overlap: int,
    logger: JsonLogger,
) -> tuple[list[DocRecord], dict[str, Any]]:
    reader = PdfReader(str(pdf_path))
    docs: list[DocRecord] = []
    pages_scanned = min(max_pages, len(reader.pages))
    pages_with_text = 0
    extracted_chars = 0

    for page_index, page in enumerate(reader.pages[:pages_scanned], start=1):
        text = normalize_space(page.extract_text() or "")
        extracted_chars += len(text)
        if not text:
            logger.write(
                "pdf_page_skipped_no_text",
                source_file=pdf_path.name,
                page_num=page_index,
            )
            continue
        pages_with_text += 1
        chunks = split_text_with_overlap(text, chunk_size=chunk_size, overlap=overlap)
        for chunk_index, chunk in enumerate(chunks):
            docs.append(
                DocRecord(
                    doc_id=stable_id("pdf", pdf_path.name, page_index, chunk_index, chunk[:120]),
                    text=chunk,
                    metadata={
                        "source_file": pdf_path.name,
                        "source_type": "pdf_text",
                        "page_num": page_index,
                        "chunk_index": chunk_index,
                        "evidence": truncate(chunk, 500),
                        "context": truncate(chunk, 500),
                        "char_count": len(chunk),
                    },
                )
            )

    stats = {
        "source_file": pdf_path.name,
        "total_pages": len(reader.pages),
        "pages_scanned": pages_scanned,
        "pages_with_text": pages_with_text,
        "extractable_chars": extracted_chars,
        "pdf_chunks": len(docs),
    }
    return docs, stats


def add_documents(
    collection: Any,
    docs: list[DocRecord],
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


def storage_size_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def write_summary(summary_path: Path, payload: dict[str, Any]) -> None:
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_library(args: argparse.Namespace, logger: JsonLogger) -> dict[str, Any]:
    logger.write(
        "build_start",
        raw_dir=str(RAW_DIR),
        output_dir=str(OUT_DIR),
        collection=COLLECTION_NAME,
        qa_limit=args.qa_limit,
        pdf_pages=args.pdf_pages,
    )

    if not QA_JSONL.exists():
        raise FileNotFoundError(f"QA JSONL not found: {QA_JSONL}")

    pdf_path = find_extractable_pdf()
    qa_docs = build_qa_documents(args.qa_limit, args.chunk_size, args.overlap)
    pdf_docs, pdf_stats = build_pdf_documents(
        pdf_path=pdf_path,
        max_pages=args.pdf_pages,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
        logger=logger,
    )
    docs = qa_docs + pdf_docs

    if not qa_docs:
        raise RuntimeError("No QA chunks were generated.")
    if not pdf_docs:
        raise RuntimeError(f"No PDF chunks were generated from {pdf_path.name}.")
    if not docs:
        raise RuntimeError("No documents generated for Chroma ingestion.")

    reset_output_dir(OUT_DIR)
    embedder = HashingEmbeddingFunction(dimension=EMBEDDING_DIMENSION)
    client = chromadb.PersistentClient(
        path=str(OUT_DIR),
        settings=Settings(anonymized_telemetry=False, is_persistent=True),
    )
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "Representative ordinary RAG baseline from gas turbine QA JSONL and extractable PDF text.",
            "embedding_backend": HashingEmbeddingFunction.name(),
            "embedding_dimension": EMBEDDING_DIMENSION,
            "created_by": "scripts/build_representative_rag_chroma.py",
        },
    )
    add_documents(collection, docs, embedder, logger, args.batch_size)

    count = collection.count()
    if count <= 0:
        logger.write("collection_count_invalid", count=count)
        raise RuntimeError(f"Collection count must be > 0, got {count}.")

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "library_dir": str(OUT_DIR),
        "collection": COLLECTION_NAME,
        "collection_count": count,
        "qa_chunks": len(qa_docs),
        "pdf_chunks": len(pdf_docs),
        "embedding_backend": HashingEmbeddingFunction.name(),
        "embedding_dimension": EMBEDDING_DIMENSION,
        "chunk_size": args.chunk_size,
        "overlap": args.overlap,
        "qa_source": str(QA_JSONL),
        "pdf_source": str(pdf_path),
        "pdf_extraction": pdf_stats,
        "storage_bytes": storage_size_bytes(OUT_DIR),
        "boundary": "Hashing embedding is deterministic/offline and is not the final retrieval-quality embedding.",
    }
    write_summary(OUT_DIR / "build_summary.json", summary)
    logger.write("build_done", **summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a representative ordinary RAG ChromaDB library.")
    parser.add_argument("--qa-limit", type=int, default=240, help="Number of QA JSONL records to sample.")
    parser.add_argument("--pdf-pages", type=int, default=60, help="Number of PDF pages to scan for extractable text.")
    parser.add_argument("--chunk-size", type=int, default=900)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=80)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = JsonLogger(LOG_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-representative-rag-chroma.jsonl")
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
