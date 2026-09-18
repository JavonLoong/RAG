from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .core import BaseRetriever, DocumentChunk, RetrievalResult

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_MAPPING_CHUNK_TEXT_REQUIRED = "KeywordRetriever mapping chunks must include text, document, or content."
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "from",
    "for",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "must",
    "not",
    "of",
    "on",
    "or",
    "our",
    "she",
    "should",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "whether",
    "which",
    "while",
    "who",
    "why",
    "will",
    "with",
    "would",
}
_METADATA_SEARCH_FIELDS = (
    "passage_id",
    "passage_title",
    "section_id",
    "section_path",
    "section_title",
    "sentence_id",
    "document_id",
    "ragbench_id",
    "source_file",
    "filename",
    "record_id",
    "chunk_id",
    "citation_anchor",
)


def _tokenize(text: str, *, case_sensitive: bool) -> list[str]:
    normalized = text if case_sensitive else text.casefold()
    raw_tokens = [token for token in _TOKEN_RE.findall(normalized) if token]
    filtered = [
        token
        for token in raw_tokens
        if token not in _STOP_WORDS and (len(token) > 1 or not token.isascii() or token.isdigit())
    ]
    return filtered or raw_tokens


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


def _metadata_search_text(metadata: Mapping[str, Any]) -> str:
    values: list[str] = []
    for field in _METADATA_SEARCH_FIELDS:
        value = metadata.get(field)
        if value is None or value == "":
            continue
        values.append(str(value))
    return " ".join(values)


def _token_counts(text: str, *, case_sensitive: bool) -> Counter[str]:
    return Counter(_tokenize(text, case_sensitive=case_sensitive))


def _term_count(counts: Counter[str], term: str) -> int:
    count = counts.get(term, 0)
    if not term.isascii() or not term.isalpha() or len(term) < 4:
        return count
    variants = {f"{term}s", f"{term}es", f"{term}ed", f"{term}d", f"{term}ing"}
    if term.endswith("e"):
        variants.add(f"{term[:-1]}ing")
    if term.endswith("y"):
        variants.add(f"{term[:-1]}ies")
    for variant in variants:
        count += counts.get(variant, 0)
    return count


def _field_exact_match_bonus(query_text: str, metadata: Mapping[str, Any]) -> float:
    if not query_text.strip():
        return 0.0
    bonus = 0.0
    for field in ("passage_id", "section_id", "sentence_id", "chunk_id", "record_id"):
        value = str(metadata.get(field) or "").strip()
        if value and value.casefold() in query_text:
            bonus += 8.0
    return bonus


def _filter_field_value(chunk: DocumentChunk, field: str) -> Any:
    normalized = field.removeprefix("meta.").removeprefix("metadata.")
    if normalized == "source":
        return chunk.source
    if normalized == "page":
        return chunk.page
    if normalized == "chunk_id":
        return chunk.chunk_id
    value: Any = chunk.metadata
    for part in normalized.split("."):
        if isinstance(value, Mapping):
            value = value.get(part)
        else:
            return None
    return value


def _as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compare_filter_value(actual: Any, operator: str, expected: Any) -> bool:
    operator = operator.lower()
    if operator in {"==", "=", "eq"}:
        return actual == expected
    if operator in {"!=", "ne"}:
        return actual != expected
    if operator == "contains":
        if actual is None:
            return False
        return str(expected).casefold() in str(actual).casefold()
    if operator == "in":
        if isinstance(expected, Sequence) and not isinstance(expected, str | bytes):
            if isinstance(actual, Sequence) and not isinstance(actual, str | bytes):
                return any(item in expected for item in actual)
            return actual in expected
        return actual == expected
    if operator in {"not in", "nin"}:
        return not _compare_filter_value(actual, "in", expected)
    if operator in {">", ">=", "<", "<="}:
        left = _as_number(actual)
        right = _as_number(expected)
        if left is None or right is None:
            return False
        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right
        if operator == "<":
            return left < right
        return left <= right
    return actual == expected


def _matches_metadata_filters(chunk: DocumentChunk, filters: Mapping[str, Any] | None) -> bool:
    if not filters:
        return True
    if "conditions" in filters:
        operator = str(filters.get("operator") or "AND").upper()
        conditions = filters.get("conditions") or []
        matches = [
            _matches_metadata_filters(chunk, condition)
            for condition in conditions
            if isinstance(condition, Mapping)
        ]
        if operator == "OR":
            return any(matches)
        if operator == "NOT":
            return not all(matches)
        return all(matches)
    if "field" in filters:
        field = str(filters.get("field") or "")
        operator = str(filters.get("operator") or "==")
        expected = filters.get("value")
        return _compare_filter_value(_filter_field_value(chunk, field), operator, expected)
    return all(
        _compare_filter_value(_filter_field_value(chunk, str(key)), "==", value)
        for key, value in filters.items()
    )


def _tf_saturation(count: int) -> float:
    if count <= 0:
        return 0.0
    k1 = 1.4
    return (count * (k1 + 1.0)) / (count + k1)


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
        self._text_token_counts = [_token_counts(chunk.text, case_sensitive=case_sensitive) for chunk in self.chunks]
        self._metadata_token_counts = [
            _token_counts(_metadata_search_text(chunk.metadata), case_sensitive=case_sensitive)
            for chunk in self.chunks
        ]
        self._idf = self._build_idf()

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        if top_k <= 0:
            return []
        terms = _tokenize(query, case_sensitive=self.case_sensitive)
        if not terms:
            return []

        query_text = query if self.case_sensitive else query.casefold()
        scored: list[tuple[float, int, DocumentChunk]] = []
        for index, chunk in enumerate(self.chunks):
            if filters and not _matches_metadata_filters(chunk, filters):
                continue
            text = chunk.text if self.case_sensitive else chunk.text.casefold()
            metadata_text = _metadata_search_text(chunk.metadata)
            metadata_text = metadata_text if self.case_sensitive else metadata_text.casefold()
            text_counts = self._text_token_counts[index]
            metadata_counts = self._metadata_token_counts[index]
            score = 0.0
            matched_terms = 0
            for term in terms:
                count = _term_count(text_counts, term)
                metadata_count = _term_count(metadata_counts, term) if metadata_text else 0
                if count or metadata_count:
                    matched_terms += 1
                    term_weight = (1.0 + math.log1p(len(term))) * self._idf.get(term, 1.0)
                    score += _tf_saturation(count) * term_weight
                    score += _tf_saturation(metadata_count) * term_weight * 2.5
            if query_text.strip() and query_text.strip() in text:
                score += 0.5
            if query_text.strip() and metadata_text and query_text.strip() in metadata_text:
                score += 2.0
            score += _field_exact_match_bonus(query_text, chunk.metadata)
            if score > 0:
                coverage = matched_terms / len(terms)
                scored.append((score * (1.0 + coverage), index, chunk))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            RetrievalResult(chunk=chunk, score=score, retriever_name=self.name)
            for score, _index, chunk in scored[:top_k]
        ]

    def _build_idf(self) -> dict[str, float]:
        if not self.chunks:
            return {}
        document_frequency: dict[str, int] = {}
        for chunk in self.chunks:
            text = chunk.text
            metadata_text = _metadata_search_text(chunk.metadata)
            terms = set(_tokenize(f"{text} {metadata_text}", case_sensitive=self.case_sensitive))
            for term in terms:
                document_frequency[term] = document_frequency.get(term, 0) + 1
        total = len(self.chunks)
        return {
            term: math.log((total + 1) / (frequency + 1)) + 1.0
            for term, frequency in document_frequency.items()
        }
