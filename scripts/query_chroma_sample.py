from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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


SAMPLES_DIR = REPO_ROOT / "storage_layer" / "runtime" / "chroma_samples"


DEFAULT_COLLECTIONS = {
    "qa_jsonl_sample": "gas_turbine_qa_sample",
    "pdf_text_sample": "gas_turbine_pdf_text_sample",
    "mixed_demo_sample": "gas_turbine_mixed_demo",
}


def resolve_library(value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate
    return SAMPLES_DIR / value


def main() -> None:
    parser = argparse.ArgumentParser(description="Query one generated ChromaDB sample library.")
    parser.add_argument("--library", default="qa_jsonl_sample", help="Library directory or sample name.")
    parser.add_argument("--collection", default="", help="Collection name. Defaults by sample name.")
    parser.add_argument("--query", default="燃气轮机有哪些优点？")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    library = resolve_library(args.library)
    if not library.exists():
        raise FileNotFoundError(f"Library does not exist: {library}")

    collection_name = args.collection or DEFAULT_COLLECTIONS.get(library.name)
    if not collection_name:
        raise ValueError("Please pass --collection for this library.")

    client = chromadb.PersistentClient(
        path=str(library),
        settings=Settings(anonymized_telemetry=False, is_persistent=True),
    )
    collection = client.get_collection(collection_name)
    embedder = HashingEmbeddingFunction(dimension=384)
    result = collection.query(
        query_embeddings=[embedder.embed_query(args.query)],
        n_results=args.top_k,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for rank, (doc_id, document, metadata, distance) in enumerate(
        zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ),
        start=1,
    ):
        hits.append(
            {
                "rank": rank,
                "id": doc_id,
                "distance": distance,
                "source_file": metadata.get("source_file"),
                "page_num": metadata.get("page_num", ""),
                "evidence": metadata.get("evidence", ""),
                "text_preview": document[:300],
            }
        )

    print(
        json.dumps(
            {
                "library": str(library),
                "collection": collection_name,
                "collection_count": collection.count(),
                "query": args.query,
                "hits": hits,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
