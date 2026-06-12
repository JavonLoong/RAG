"""Chroma-backed semantic store for conversation memory summaries."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

COLLECTION_NAME = "conversation_memory"
_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_\u4e00-\u9fff]+")


class HashingEmbedder:
    """Lightweight local embedder; no GPU or model download required."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
        tokens = _TOKEN_PATTERN.findall(normalized)
        vector = np.zeros(self.dimension, dtype=np.float32)
        if not tokens:
            return vector.tolist()
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], byteorder="little") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 8) / 8
            vector[index] += sign * weight
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector.tolist()


@dataclass(frozen=True, slots=True)
class MemoryVectorHit:
    vector_id: str
    content: str
    score: float
    metadata: dict[str, Any]


class ConversationMemoryVectorStore:
    """Separate Chroma collection for long-term conversation summaries."""

    def __init__(self, persist_dir: str | Path) -> None:
        self.persist_dir = Path(persist_dir)
        self._embedder = HashingEmbedder()
        self._client: Any | None = None
        self._collection: Any | None = None

    def initialize(self) -> None:
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        import chromadb
        from chromadb.config import Settings

        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False, is_persistent=True),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={
                "hnsw:space": "cosine",
                "embedding_backend": "power_equipment_hashing",
                "purpose": "conversation_memory_summaries",
            },
        )

    def upsert_summary(
        self,
        vector_id: str,
        content: str,
        *,
        session_id: str,
        summary_id: int,
    ) -> None:
        self._ensure_ready()
        self._collection.upsert(
            ids=[vector_id],
            documents=[content],
            embeddings=[self._embedder.embed_query(content)],
            metadatas=[
                {
                    "session_id": session_id,
                    "summary_id": int(summary_id),
                    "type": "summary",
                }
            ],
        )

    def search(
        self,
        query: str,
        *,
        session_id: str | None = None,
        top_k: int = 3,
    ) -> list[MemoryVectorHit]:
        self._ensure_ready()
        text = str(query or "").strip()
        if not text:
            return []
        top_k = max(1, min(int(top_k), 10))
        where = {"session_id": session_id} if session_id else None
        try:
            result = self._collection.query(
                query_embeddings=[self._embedder.embed_query(text)],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []

        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[MemoryVectorHit] = []
        for idx, vector_id in enumerate(ids):
            distance = distances[idx] if idx < len(distances) else None
            score = 1.0 / (1.0 + float(distance or 0.0))
            hits.append(
                MemoryVectorHit(
                    vector_id=str(vector_id),
                    content=str(docs[idx] if idx < len(docs) else ""),
                    score=round(score, 4),
                    metadata=dict(metas[idx] if idx < len(metas) else {}),
                )
            )
        return hits

    def delete_session(self, session_id: str) -> int:
        self._ensure_ready()
        try:
            existing = self._collection.get(where={"session_id": session_id}, include=[])
            ids = list(existing.get("ids") or [])
            if ids:
                self._collection.delete(ids=ids)
            return len(ids)
        except Exception:
            return 0

    def _ensure_ready(self) -> None:
        if self._collection is None:
            self.initialize()
