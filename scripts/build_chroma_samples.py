from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_PACKAGES = REPO_ROOT / ".venv" / "Lib" / "site-packages"
POC_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"

for path in (str(SITE_PACKAGES), str(POC_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

import chromadb  # noqa: E402
from chromadb.config import Settings  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from chroma_rag_poc.embeddings import HashingEmbeddingFunction  # noqa: E402
from chroma_rag_poc.chunking import split_text_with_overlap  # noqa: E402


RAW_DIR = REPO_ROOT / "data_pipeline" / "raw" / "tsinghua_gas_turbine_books"
OUT_DIR = REPO_ROOT / "storage_layer" / "runtime" / "chroma_samples"
LOG_DIR = REPO_ROOT / "observability" / "logs" / "chroma_samples"

QA_JSONL = RAW_DIR / "canonical_qa_auto_13423.jsonl"
PDF_TEXT_SAMPLE_PATTERN = "燃气-蒸汽联合循环发电机组运行技术问答*.pdf"
PDF_SMALL_SCANNED_PATTERN = "燃气轮机 (南京燃气轮机研究所编)*.pdf"


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
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        print(f"[{payload['ts']}] {event} {fields}")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def truncate(text: str, limit: int) -> str:
    text = normalize_space(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def stable_id(*parts: object) -> str:
    import hashlib

    raw = "||".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def sanitize_metadata(value: Any) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def safe_reset_dir(path: Path) -> None:
    root = OUT_DIR.resolve()
    target = path.resolve()
    if root not in target.parents and target != root:
        raise ValueError(f"Refusing to reset path outside {root}: {target}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def read_jsonl_records(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
            if limit is not None and len(records) >= limit:
                break
    return records


def build_qa_documents(limit: int = 300) -> list[DocRecord]:
    docs: list[DocRecord] = []
    for row in read_jsonl_records(QA_JSONL, limit=limit):
        meta = row.get("metadata") or {}
        evidence = meta.get("supporting_evidence") or ""
        context = row.get("context") or ""
        text = "\n".join(
            part
            for part in (
                f"问题：{row.get('question', '')}",
                f"答案：{row.get('answer', '')}",
                f"证据：{evidence}",
                f"上下文摘录：{truncate(context, 700)}",
            )
            if normalize_space(part)
        )
        docs.append(
            DocRecord(
                doc_id=str(row.get("id") or stable_id("qa", len(docs))),
                text=text,
                metadata={
                    "sample": "qa_jsonl",
                    "source_file": QA_JSONL.name,
                    "source": sanitize_metadata(row.get("source", "")),
                    "source_pages": sanitize_metadata(row.get("source_pages", "")),
                    "question_type": sanitize_metadata(row.get("question_type", "")),
                    "difficulty": sanitize_metadata(row.get("difficulty", "")),
                    "split": sanitize_metadata(row.get("split", "")),
                    "has_evidence": bool(evidence),
                    "evidence": truncate(str(evidence), 500),
                },
            )
        )
    return docs


def extract_pdf_pages(pdf_path: Path, max_pages: int = 80) -> tuple[list[tuple[int, str]], dict[str, Any]]:
    reader = PdfReader(str(pdf_path))
    pages: list[tuple[int, str]] = []
    total_chars = 0
    pages_with_text = 0
    for index, page in enumerate(reader.pages[:max_pages], start=1):
        text = normalize_space(page.extract_text() or "")
        total_chars += len(text)
        if text:
            pages_with_text += 1
            pages.append((index, text))
    stats = {
        "source_file": pdf_path.name,
        "total_pages": len(reader.pages),
        "pages_scanned": min(max_pages, len(reader.pages)),
        "pages_with_text": pages_with_text,
        "extractable_chars": total_chars,
    }
    return pages, stats


def build_pdf_documents(pdf_path: Path, max_pages: int = 80, chunk_size: int = 900, overlap: int = 120) -> tuple[list[DocRecord], dict[str, Any]]:
    pages, stats = extract_pdf_pages(pdf_path, max_pages=max_pages)
    docs: list[DocRecord] = []
    for page_num, text in pages:
        chunks = split_text_with_overlap(text, chunk_size=chunk_size, overlap=overlap)
        for chunk_index, chunk in enumerate(chunks):
            docs.append(
                DocRecord(
                    doc_id=stable_id("pdf", pdf_path.name, page_num, chunk_index, chunk[:80]),
                    text=chunk,
                    metadata={
                        "sample": "pdf_text",
                        "source_file": pdf_path.name,
                        "page_num": page_num,
                        "chunk_index": chunk_index,
                        "source_kind": "PDF",
                        "char_count": len(chunk),
                    },
                )
            )
    return docs, stats


def build_ocr_context_documents(limit: int = 120) -> list[DocRecord]:
    docs: list[DocRecord] = []
    seen: set[str] = set()
    for row in read_jsonl_records(QA_JSONL, limit=limit * 4):
        source = str(row.get("source") or "")
        context = normalize_space(row.get("context") or "")
        if not context or source in seen:
            continue
        seen.add(source)
        for chunk_index, chunk in enumerate(split_text_with_overlap(context, chunk_size=900, overlap=120)[:3]):
            docs.append(
                DocRecord(
                    doc_id=stable_id("ocr-context", source, chunk_index, chunk[:80]),
                    text=chunk,
                    metadata={
                        "sample": "ocr_context_from_jsonl",
                        "source_file": source,
                        "source_pages": sanitize_metadata(row.get("source_pages", "")),
                        "chunk_index": chunk_index,
                        "source_kind": "OCR_CONTEXT",
                        "char_count": len(chunk),
                    },
                )
            )
            if len(docs) >= limit:
                return docs
    return docs


def create_chroma_library(
    library_dir: Path,
    collection_name: str,
    docs: list[DocRecord],
    logger: JsonLogger,
    description: str,
) -> dict[str, Any]:
    safe_reset_dir(library_dir)
    embedder = HashingEmbeddingFunction(dimension=384)
    client = chromadb.PersistentClient(
        path=str(library_dir),
        settings=Settings(anonymized_telemetry=False, is_persistent=True),
    )
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={
            "description": description,
            "embedding_backend": "power_equipment_hashing",
            "embedding_dimension": 384,
            "created_by": "scripts/build_chroma_samples.py",
        },
    )

    batch_size = 100
    for start in range(0, len(docs), batch_size):
        batch = docs[start : start + batch_size]
        embeddings = embedder([doc.text for doc in batch])
        collection.add(
            ids=[doc.doc_id for doc in batch],
            documents=[doc.text for doc in batch],
            metadatas=[doc.metadata for doc in batch],
            embeddings=embeddings,
        )
        logger.write(
            "upsert_batch",
            library=str(library_dir),
            collection=collection_name,
            start=start,
            count=len(batch),
        )

    count = collection.count()
    size_bytes = sum(path.stat().st_size for path in library_dir.rglob("*") if path.is_file())
    summary = {
        "library_dir": str(library_dir),
        "collection": collection_name,
        "document_count": count,
        "storage_bytes": size_bytes,
        "storage_mb": round(size_bytes / (1024 * 1024), 3),
        "description": description,
    }
    logger.write("library_done", **summary)
    return summary


def find_one(pattern: str) -> Path:
    matches = sorted(RAW_DIR.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matched {pattern}")
    return matches[0]


def write_summary(summary_path: Path, libraries: list[dict[str, Any]], pdf_stats: list[dict[str, Any]]) -> None:
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "raw_dir": str(RAW_DIR),
        "embedding_backend": "power_equipment_hashing",
        "embedding_dimension": 384,
        "libraries": libraries,
        "pdf_extraction_stats": pdf_stats,
        "notes": [
            "These are small ChromaDB samples for read/query/metadata operation tests.",
            "The hashing embedding backend is deterministic and offline; it is not intended as final retrieval quality.",
            "Many downloaded PDFs are scanned images; pypdf extraction may produce zero chars, so OCR is still needed for full production ingestion.",
        ],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build small ChromaDB sample libraries from downloaded turbine materials.")
    parser.add_argument("--qa-limit", type=int, default=300)
    parser.add_argument("--pdf-pages", type=int, default=80)
    parser.add_argument("--ocr-context-limit", type=int, default=120)
    args = parser.parse_args()

    started = time.perf_counter()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = JsonLogger(LOG_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-build-chroma-samples.log")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.write("build_start", raw_dir=str(RAW_DIR), output_dir=str(OUT_DIR))

    text_pdf = find_one(PDF_TEXT_SAMPLE_PATTERN)
    scanned_pdf = find_one(PDF_SMALL_SCANNED_PATTERN)
    _, scanned_stats = extract_pdf_pages(scanned_pdf, max_pages=20)
    logger.write("pdf_probe", **scanned_stats)

    qa_docs = build_qa_documents(limit=args.qa_limit)
    pdf_docs, pdf_stats = build_pdf_documents(text_pdf, max_pages=args.pdf_pages)
    ocr_docs = build_ocr_context_documents(limit=args.ocr_context_limit)
    mixed_docs = qa_docs[:120] + pdf_docs[:80] + ocr_docs[:80]

    if not qa_docs:
        raise RuntimeError("No QA documents generated.")
    if not pdf_docs:
        raise RuntimeError(f"No extractable PDF documents generated from {text_pdf.name}.")
    if not mixed_docs:
        raise RuntimeError("No mixed documents generated.")

    libraries = [
        create_chroma_library(
            OUT_DIR / "qa_jsonl_sample",
            "gas_turbine_qa_sample",
            qa_docs,
            logger,
            "QA JSONL sample built from canonical_qa_auto_13423.jsonl.",
        ),
        create_chroma_library(
            OUT_DIR / "pdf_text_sample",
            "gas_turbine_pdf_text_sample",
            pdf_docs,
            logger,
            f"PDF text sample built from {text_pdf.name}; scanned PDFs still need OCR.",
        ),
        create_chroma_library(
            OUT_DIR / "mixed_demo_sample",
            "gas_turbine_mixed_demo",
            mixed_docs,
            logger,
            "Mixed demo sample combining QA pairs, extractable PDF pages, and OCR contexts from JSONL.",
        ),
    ]

    summary_path = OUT_DIR / "sample_libraries_summary.json"
    write_summary(summary_path, libraries, pdf_stats=[pdf_stats, scanned_stats])
    logger.write("build_done", elapsed_s=round(time.perf_counter() - started, 3), summary=str(summary_path))
    print(json.dumps({"libraries": libraries, "summary": str(summary_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
