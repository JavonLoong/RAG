"""Version-aware Chroma index for published governed materials.

The governance database remains the source of truth.  This module is the
executable bridge that projects only published document versions into the
retrieval store and returns locators that resolve back to governance evidence.
"""
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from core_domain.delivery import CanonicalDocumentVersion, ContentStatus


class GovernedIndexError(RuntimeError):
    """Raised when the governed retrieval projection cannot be maintained."""


class GovernedDocumentIndex:
    """Persist and query the active published material versions in ChromaDB."""

    def __init__(
        self,
        persist_path: str | Path,
        *,
        embedding_function: Any,
        embedding_backend: str,
        embedding_model: str,
        embedding_warning: str | None = None,
        collection_name: str = "governed_materials",
    ) -> None:
        try:
            import chromadb
            from chromadb.config import Settings
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency gate
            raise GovernedIndexError("chromadb is required for governed material indexing") from exc

        self.persist_path = Path(persist_path)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self.embedding_function = embedding_function
        self.embedding_backend = str(embedding_backend)
        self.embedding_model = str(embedding_model)
        self.embedding_warning = embedding_warning
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(
            path=str(self.persist_path),
            settings=Settings(anonymized_telemetry=False, is_persistent=True),
        )
        self.collection = self._collection()

    def _collection(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
            metadata={
                "hnsw:space": "cosine",
                "delivery_schema": "governed-material-v1",
                "embedding_backend": self.embedding_backend,
                "embedding_model": self.embedding_model,
            },
        )

    def sync_document(self, document: CanonicalDocumentVersion) -> dict[str, Any]:
        if document.status is not ContentStatus.PUBLISHED:
            raise GovernedIndexError(f"Only published documents can be indexed: {document.version_id}")
        if not document.evidence:
            raise GovernedIndexError(f"Published document has no evidence: {document.version_id}")

        # One canonical version per document participates in default retrieval.
        self.collection.delete(where={"document_id": document.document_id})
        ids = [item.evidence_id for item in document.evidence]
        documents = [item.text for item in document.evidence]
        metadatas = [
            {
                "document_id": document.document_id,
                "document_version_id": document.version_id,
                "document_version": document.version,
                "content_hash": document.content_hash,
                "chunk_id": item.chunk_id,
                "source_file": item.source_file,
                "page": item.page or "",
                "block_id": item.block_id or "",
                "table_id": item.table_id or "",
                "image_id": item.image_id or "",
                "evidence_id": item.evidence_id,
                "status": document.status.value,
            }
            for item in document.evidence
        ]
        for start in range(0, len(ids), 100):
            end = start + 100
            self.collection.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                metadatas=metadatas[start:end],
            )
        return {
            "operation": "sync_document",
            "document_id": document.document_id,
            "document_version_id": document.version_id,
            "indexed_chunks": len(ids),
            **self.status(),
        }

    def rebuild(self, documents: Sequence[CanonicalDocumentVersion]) -> dict[str, Any]:
        with suppress(Exception):
            self.client.delete_collection(self.collection_name)
        self.collection = self._collection()
        synced: list[dict[str, Any]] = []
        for document in documents:
            if document.status is ContentStatus.PUBLISHED:
                synced.append(self.sync_document(document))
        return {
            "operation": "rebuild",
            "document_versions": [item["document_version_id"] for item in synced],
            "indexed_chunks": self.collection.count(),
            **self.status(),
        }

    def query(
        self,
        query: str,
        *,
        top_k: int = 5,
        document_version_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        clean_query = str(query).strip()
        if not clean_query:
            raise GovernedIndexError("query must not be empty")
        count = self.collection.count()
        if count == 0:
            return {"query": clean_query, "results": [], "no_answer": True, **self.status()}

        args: dict[str, Any] = {
            "n_results": min(max(1, int(top_k)), count),
            "include": ["documents", "metadatas", "distances"],
        }
        if document_version_ids:
            versions = list(dict.fromkeys(str(item) for item in document_version_ids if str(item).strip()))
            args["where"] = (
                {"document_version_id": versions[0]}
                if len(versions) == 1
                else {"document_version_id": {"$in": versions}}
            )
        vector = self.embedding_function.embed_query(clean_query)
        if isinstance(vector, list) and vector and isinstance(vector[0], list):
            vector = vector[0]
        args["query_embeddings"] = [list(vector)]
        raw = self.collection.query(**args)
        ids = _first_batch(raw.get("ids"))
        texts = _first_batch(raw.get("documents"))
        metadatas = _first_batch(raw.get("metadatas"))
        distances = _first_batch(raw.get("distances"))
        results = []
        for index, evidence_id in enumerate(ids):
            metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
            distance = float(distances[index]) if index < len(distances) else 1.0
            results.append({
                "evidence_id": str(evidence_id),
                "text": str(texts[index] or "") if index < len(texts) else "",
                "score": 1.0 / (1.0 + max(distance, 0.0)),
                "distance": distance,
                "locator": metadata,
            })
        return {
            "query": clean_query,
            "results": results,
            "no_answer": not results,
            "document_version_filter": list(document_version_ids),
            **self.status(),
        }

    def status(self) -> dict[str, Any]:
        return {
            "collection": self.collection_name,
            "collection_count": self.collection.count(),
            "persist_path": str(self.persist_path),
            "embedding_backend": self.embedding_backend,
            "embedding_model": self.embedding_model,
            "embedding_warning": self.embedding_warning,
            "production_embedding": self.embedding_backend != "hashing",
        }


def _first_batch(value: Any) -> list[Any]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return list(value[0])
    return list(value or []) if isinstance(value, list) else []
