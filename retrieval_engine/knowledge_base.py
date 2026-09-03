"""Bridge the versioned M3 store into the repository's retriever contract."""

from __future__ import annotations

from typing import Any

from knowledge_base.models import SearchMode
from knowledge_base.query import KnowledgeBaseQueryService

from .core import BaseRetriever, DocumentChunk, RetrievalResult


class KnowledgeBaseRetriever(BaseRetriever):
    name = "knowledge_base"

    def __init__(
        self,
        service: KnowledgeBaseQueryService,
        *,
        version: int | None = None,
        mode: SearchMode = SearchMode.HYBRID,
        embedder: Any | None = None,
        embedding_model: str | None = None,
        allowed_access_labels: set[str] | None = None,
    ) -> None:
        self.service = service
        self.version = version
        self.mode = mode
        self.embedder = embedder
        self.embedding_model = embedding_model
        self.allowed_access_labels = allowed_access_labels

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        hits = self.service.search(
            query,
            mode=self.mode,
            top_k=top_k,
            version=self.version,
            embedder=self.embedder,
            embedding_model=self.embedding_model,
            allowed_access_labels=self.allowed_access_labels,
        )
        return [
            RetrievalResult(
                chunk=DocumentChunk.from_text(
                    hit.text,
                    metadata={
                        "document_id": hit.document_id,
                        "revision_id": hit.revision_id,
                        "knowledge_base_version": hit.version,
                        "source": hit.source_uri,
                        "page": sorted({item.page_number for item in hit.evidence}),
                        "chunk_id": hit.chunk_id,
                        "document_metadata": dict(hit.metadata),
                        "evidence": [
                            {
                                "page_number": item.page_number,
                                "block_id": item.block_id,
                                "char_start": item.char_start,
                                "char_end": item.char_end,
                            }
                            for item in hit.evidence
                        ],
                    },
                    source=hit.source_uri,
                    chunk_id=hit.chunk_id,
                ),
                score=hit.score,
                retriever_name=self.name,
                component_scores=dict(hit.component_scores),
            )
            for hit in hits
        ]
