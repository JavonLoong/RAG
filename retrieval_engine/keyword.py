from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .core import BaseRetriever, DocumentChunk, RetrievalResult

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_MAPPING_CHUNK_TEXT_REQUIRED = "KeywordRetriever mapping chunks must include text, document, or content."


def _tokenize(text: str, *, case_sensitive: bool) -> list[str]:
    normalized = text if case_sensitive else text.casefold()
    return [token for token in _TOKEN_RE.findall(normalized) if token]


def _coerce_chunk(value: DocumentChunk | str | Mapping[str, Any]) -> DocumentChunk:
    if isinstance(value, DocumentChunk):
        return value
    if isinstance(value, str):
        return DocumentChunk.from_text(value)
    text = value.get("text") or value.get("document") or value.get("content")
    if text is None:
        raise ValueError(_MAPPING_CHUNK_TEXT_REQUIRED)
    metadata = value.get("metadata")
    if isinstance(metadata, Mapping):
        merged_metadata = dict(metadata)
    else:
        merged_metadata = {key: item for key, item in value.items() if key not in {"text", "document", "content"}}
    return DocumentChunk.from_text(str(text), metadata=merged_metadata)


class KeywordRetriever(BaseRetriever):
    """A deterministic sparse retriever for tests, demos, and explicit fallback paths."""

    name = "keyword"

    def __init__(
        self,
        chunks: Iterable[DocumentChunk | str | Mapping[str, Any]],
        *,
        name: str | None = None,
        case_sensitive: bool = False,
    ) -> None:
        self.chunks = [_coerce_chunk(chunk) for chunk in chunks]
        self.name = name or self.name
        self.case_sensitive = case_sensitive

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        if top_k <= 0:
            return []
        terms = _tokenize(query, case_sensitive=self.case_sensitive)
        if not terms:
            return []

        query_text = query if self.case_sensitive else query.casefold()
        scored: list[tuple[float, int, DocumentChunk]] = []
        for index, chunk in enumerate(self.chunks):
            text = chunk.text if self.case_sensitive else chunk.text.casefold()
            score = 0.0
            matched_terms = 0
            for term in terms:
                count = text.count(term)
                if count:
                    matched_terms += 1
                    score += count * (1.0 + math.log1p(len(term)))
            if query_text.strip() and query_text.strip() in text:
                score += 0.5
            if score > 0:
                coverage = matched_terms / len(terms)
                scored.append((score * (1.0 + coverage), index, chunk))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            RetrievalResult(chunk=chunk, score=score, retriever_name=self.name)
            for score, _index, chunk in scored[:top_k]
        ]
