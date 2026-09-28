"""Version-aware Chroma index for published governed materials.

The governance database remains the source of truth.  This module is the
executable bridge that projects only published document versions into the
retrieval store and returns locators that resolve back to governance evidence.
"""
# ruff: noqa: TRY003

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
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
        project_id: str = "default",
        chunk_config: Mapping[str, Any] | None = None,
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
        self.project_id = str(project_id or "default")
        self.chunk_config = dict(chunk_config or {})
        self.snapshot_path = self.persist_path.parent / "snapshots"
        self.snapshot_path.mkdir(parents=True, exist_ok=True)
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

    def sync_document(
        self,
        document: CanonicalDocumentVersion,
        *,
        created_by: str = "system",
    ) -> dict[str, Any]:
        result = self._sync_document(document)
        result["index_snapshot"] = self._record_snapshot(
            "sync_document", (document,), created_by=created_by
        )
        return result

    def _sync_document(self, document: CanonicalDocumentVersion) -> dict[str, Any]:
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

    def rebuild(
        self,
        documents: Sequence[CanonicalDocumentVersion],
        *,
        created_by: str = "system",
    ) -> dict[str, Any]:
        with suppress(Exception):
            self.client.delete_collection(self.collection_name)
        self.collection = self._collection()
        synced: list[dict[str, Any]] = []
        for document in documents:
            if document.status is ContentStatus.PUBLISHED:
                synced.append(self._sync_document(document))
        result = {
            "operation": "rebuild",
            "document_versions": [item["document_version_id"] for item in synced],
            "indexed_chunks": self.collection.count(),
            **self.status(),
        }
        result["index_snapshot"] = self._record_snapshot(
            "rebuild",
            tuple(document for document in documents if document.status is ContentStatus.PUBLISHED),
            created_by=created_by,
        )
        return result

    def query(
        self,
        query: str,
        *,
        top_k: int = 5,
        document_version_ids: Sequence[str] = (),
        mode: str = "semantic",
    ) -> dict[str, Any]:
        clean_query = str(query).strip()
        if not clean_query:
            raise GovernedIndexError("query must not be empty")
        retrieval_mode = str(mode or "semantic").strip().lower()
        if retrieval_mode not in {"keyword", "semantic", "hybrid"}:
            raise GovernedIndexError(f"Unsupported governed retrieval mode: {mode}")
        count = self.collection.count()
        if count == 0:
            return {
                "query": clean_query,
                "retrieval_mode": retrieval_mode,
                "results": [],
                "no_answer": True,
                **self.status(),
            }

        limit = min(max(1, int(top_k)), count)
        versions = tuple(dict.fromkeys(str(item) for item in document_version_ids if str(item).strip()))
        semantic = self._semantic_query(clean_query, top_k=min(count, max(limit, limit * 4)), versions=versions)
        if retrieval_mode == "semantic":
            results = semantic[:limit]
        else:
            keyword = self._keyword_query(clean_query, versions=versions)
            results = (
                keyword[:limit]
                if retrieval_mode == "keyword"
                else _rrf_merge(semantic, keyword, limit=limit)
            )
        return {
            "query": clean_query,
            "retrieval_mode": retrieval_mode,
            "results": results,
            "no_answer": not results,
            "document_version_filter": list(versions),
            **self.status(),
        }

    def _semantic_query(
        self,
        query: str,
        *,
        top_k: int,
        versions: Sequence[str],
    ) -> list[dict[str, Any]]:
        count = self.collection.count()

        args: dict[str, Any] = {
            "n_results": min(max(1, int(top_k)), count),
            "include": ["documents", "metadatas", "distances"],
        }
        if versions:
            args["where"] = (
                {"document_version_id": versions[0]}
                if len(versions) == 1
                else {"document_version_id": {"$in": list(versions)}}
            )
        vector = self.embedding_function.embed_query(query)
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
                "semantic_score": 1.0 / (1.0 + max(distance, 0.0)),
                "distance": distance,
                "locator": metadata,
                "retrieval_paths": ["semantic"],
            })
        return results

    def _keyword_query(self, query: str, *, versions: Sequence[str]) -> list[dict[str, Any]]:
        where: dict[str, Any] | None = None
        if versions:
            where = (
                {"document_version_id": versions[0]}
                if len(versions) == 1
                else {"document_version_id": {"$in": list(versions)}}
            )
        raw = self.collection.get(where=where, include=["documents", "metadatas"])
        ids = list(raw.get("ids") or [])
        texts = list(raw.get("documents") or [])
        metadatas = list(raw.get("metadatas") or [])
        query_tokens = _retrieval_tokens(query)
        ranked: list[dict[str, Any]] = []
        for index, evidence_id in enumerate(ids):
            text = str(texts[index] or "") if index < len(texts) else ""
            text_tokens = _retrieval_tokens(text)
            overlap = len(query_tokens & text_tokens)
            if not overlap and query.casefold() not in text.casefold():
                continue
            score = overlap / max(1.0, math.sqrt(len(query_tokens) * max(1, len(text_tokens))))
            if query.casefold() in text.casefold():
                score += 1.0
            metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
            ranked.append({
                "evidence_id": str(evidence_id),
                "text": text,
                "score": score,
                "keyword_score": score,
                "distance": None,
                "locator": metadata,
                "retrieval_paths": ["keyword"],
            })
        return sorted(ranked, key=lambda item: (-float(item["score"]), item["evidence_id"]))

    def status(self) -> dict[str, Any]:
        snapshots = sorted(self.snapshot_path.glob("*.json"), key=lambda item: item.name, reverse=True)
        latest_snapshot = None
        if snapshots:
            with suppress(OSError, ValueError, json.JSONDecodeError):
                latest_snapshot = json.loads(snapshots[0].read_text(encoding="utf-8"))
        return {
            "project_id": self.project_id,
            "collection": self.collection_name,
            "collection_count": self.collection.count(),
            "persist_path": str(self.persist_path),
            "embedding_backend": self.embedding_backend,
            "embedding_model": self.embedding_model,
            "embedding_warning": self.embedding_warning,
            "production_embedding": self.embedding_backend != "hashing",
            "config_hash": self._config_hash(),
            "latest_snapshot": latest_snapshot,
        }

    def _config_hash(self) -> str:
        payload = {
            "collection": self.collection_name,
            "embedding_backend": self.embedding_backend,
            "embedding_model": self.embedding_model,
            "embedding_dimension": getattr(self.embedding_function, "dimension", None),
            "chunk_config": self.chunk_config,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def _record_snapshot(
        self,
        operation: str,
        documents: Sequence[CanonicalDocumentVersion],
        *,
        created_by: str,
    ) -> dict[str, Any]:
        created_at = datetime.now(UTC).isoformat()
        source_versions = [
            {
                "document_id": item.document_id,
                "version_id": item.version_id,
                "version": item.version,
                "content_hash": item.content_hash,
            }
            for item in documents
        ]
        payload = {
            "project_id": self.project_id,
            "operation": operation,
            "created_at": created_at,
            "created_by": str(created_by or "system"),
            "collection": self.collection_name,
            "document_versions": source_versions,
            "content_hash": hashlib.sha256(
                json.dumps(source_versions, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest(),
            "embedding_backend": self.embedding_backend,
            "embedding_model": self.embedding_model,
            "embedding_dimension": getattr(self.embedding_function, "dimension", None),
            "chunk_config": self.chunk_config,
            "config_hash": self._config_hash(),
            "indexed_chunks": self.collection.count(),
        }
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        payload["snapshot_id"] = f"idx-{digest[:20]}"
        target = self.snapshot_path / f"{created_at.replace(':', '').replace('+', '_')}-{payload['snapshot_id']}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload


def _first_batch(value: Any) -> list[Any]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return list(value[0])
    return list(value or []) if isinstance(value, list) else []


def _retrieval_tokens(text: str) -> set[str]:
    normalized = re.sub(r"\s+", " ", str(text or "").casefold()).strip()
    words = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    words.update(chinese[index:index + 2] for index in range(max(0, len(chinese) - 1)))
    return {item for item in words if item}


def _rrf_merge(
    semantic: Sequence[dict[str, Any]],
    keyword: Sequence[dict[str, Any]],
    *,
    limit: int,
    constant: int = 60,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for path, items in (("semantic", semantic), ("keyword", keyword)):
        for rank, item in enumerate(items, start=1):
            evidence_id = str(item["evidence_id"])
            current = merged.setdefault(evidence_id, dict(item))
            current["rrf_score"] = float(current.get("rrf_score") or 0.0) + 1.0 / (constant + rank)
            paths = set(current.get("retrieval_paths") or [])
            paths.add(path)
            current["retrieval_paths"] = sorted(paths)
            if path == "semantic":
                current["semantic_score"] = item.get("semantic_score", item.get("score"))
            else:
                current["keyword_score"] = item.get("keyword_score", item.get("score"))

    ranked = sorted(
        merged.values(),
        key=lambda item: (-float(item.get("rrf_score") or 0.0), str(item["evidence_id"])),
    )
    for item in ranked:
        item["score"] = item["rrf_score"]
    return ranked[:limit]
