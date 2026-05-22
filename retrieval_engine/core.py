from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

Metadata = dict[str, Any]


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _metadata_first(metadata: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = metadata.get(key)
        if _present(value):
            return value
    return None


def _normalize_page(value: Any) -> int | str | None:
    if not _present(value):
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else str(value)
    text = str(value).strip()
    if not text:
        return None
    return int(text) if text.isdigit() else text


def _normalize_chunk_id(
    metadata: Mapping[str, Any],
    source: str | None,
    page: int | str | None,
    explicit_chunk_id: str | None,
) -> str | None:
    if _present(explicit_chunk_id):
        return str(explicit_chunk_id)

    metadata_id = _metadata_first(metadata, ("chunk_id", "id", "doc_id", "document_id"))
    if _present(metadata_id):
        return str(metadata_id)

    chunk_index = _metadata_first(metadata, ("chunk_index", "chunk", "chunk_num", "chunk_number"))
    if _present(source) and _present(page) and _present(chunk_index):
        return f"{source}:{page}:{chunk_index}"
    if _present(source) and _present(page):
        return f"{source}:{page}"
    return None


@dataclass(slots=True)
class DocumentChunk:
    """A normalized document fragment returned by retrievers."""

    text: str
    source: str | None = None
    page: int | str | None = None
    chunk_id: str | None = None
    metadata: Metadata = field(default_factory=dict)

    @classmethod
    def from_text(
        cls,
        text: str,
        metadata: Mapping[str, Any] | None = None,
        *,
        source: str | None = None,
        page: int | str | None = None,
        chunk_id: str | None = None,
    ) -> DocumentChunk:
        copied_metadata = dict(metadata or {})
        normalized_source = source or _metadata_first(
            copied_metadata,
            ("source", "source_file", "filename", "file_name", "file_path", "path"),
        )
        normalized_source = str(normalized_source) if _present(normalized_source) else None
        normalized_page = _normalize_page(
            page if _present(page) else _metadata_first(copied_metadata, ("page", "page_num", "page_number"))
        )
        normalized_chunk_id = _normalize_chunk_id(copied_metadata, normalized_source, normalized_page, chunk_id)
        return cls(
            text=text,
            source=normalized_source,
            page=normalized_page,
            chunk_id=normalized_chunk_id,
            metadata=copied_metadata,
        )

    @property
    def identity_key(self) -> tuple[str, str]:
        if self.chunk_id:
            return ("chunk_id", self.chunk_id)
        if self.source is not None or self.page is not None:
            return ("source_page_text", f"{self.source}|{self.page}|{self.text}")
        return ("text", self.text)


@dataclass(slots=True)
class RetrievalResult:
    """A scored retrieval hit with convenient access to normalized chunk fields."""

    chunk: DocumentChunk
    score: float
    retriever_name: str | None = None
    component_scores: dict[str, float] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.chunk.text

    @property
    def source(self) -> str | None:
        return self.chunk.source

    @property
    def page(self) -> int | str | None:
        return self.chunk.page

    @property
    def chunk_id(self) -> str | None:
        return self.chunk.chunk_id

    @property
    def metadata(self) -> Metadata:
        return self.chunk.metadata


class BaseRetriever(ABC):
    """Minimal interface shared by dense, sparse, graph, and hybrid retrievers."""

    name = "base"

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """Return up to top_k scored hits, sorted from strongest to weakest."""
