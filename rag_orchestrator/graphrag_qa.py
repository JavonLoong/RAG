from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

EMPTY_QUESTION_ERROR = "question must not be empty"
INVALID_TOP_K_ERROR = "top_k must be >= 1"
MISSING_LLM_ERROR = (
    "LLM client is required for GraphRAG answer generation; pass llm=... "
    "or use context_only=True for retrieval debugging."
)
INVALID_RETRIEVER_ERROR = (
    "Retriever must expose retrieve/search/query/search_graph/query_related or be callable."
)
INVALID_LLM_ERROR = "LLM client must expose generate/complete/invoke/generate_answer or be callable."


class GraphRagConfigurationError(RuntimeError):
    """Raised when GraphRAG QA cannot run because a required adapter is missing."""


class RetrieverProtocol(Protocol):
    def retrieve(self, query: str, top_k: int) -> Iterable[Any]:
        """Return ranked retrieval records for a query."""


class LLMProtocol(Protocol):
    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate an answer from a prompt."""


@dataclass(slots=True)
class EvidenceItem:
    citation_id: str
    source_type: str
    rank: int
    text: str
    source: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_id: str | None = None
    subject: str | None = None
    predicate: str | None = None
    object_: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.citation_id,
            "source_type": self.source_type,
            "rank": self.rank,
            "text": self.text,
            "source": self.source,
            "score": self.score,
            "metadata": dict(self.metadata),
        }
        if self.raw_id:
            payload["raw_id"] = self.raw_id
        if self.subject or self.predicate or self.object_:
            payload["graph"] = {
                "subject": self.subject,
                "predicate": self.predicate,
                "object": self.object_,
            }
        return payload


@dataclass(slots=True)
class GraphRagQAResult:
    question: str
    answer: str | None
    context: str
    citations: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    context_only: bool
    prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "context": self.context,
            "citations": self.citations,
            "evidence": self.evidence,
            "context_only": self.context_only,
            "prompt": self.prompt,
        }


class GraphRagQAOrchestrator:
    """Minimal GraphRAG QA orchestration over text retrieval, graph retrieval, and an LLM.

    The optional ``global_searcher`` adds a third retrieval path using
    Map-Reduce over community summaries.  High-level questions benefit
    from this global context while fine-grained lookups still rely on
    the text and graph retrievers.
    """

    def __init__(
        self,
        *,
        text_retriever: Any,
        graph_retriever: Any,
        global_searcher: Any | None = None,
        query_router: Any | None = None,
        hallucination_guard: Any | None = None,
        llm: Any | None = None,
        prompt_builder: Callable[[str, str, list[dict[str, Any]]], str] | None = None,
    ) -> None:
        self.text_retriever = text_retriever
        self.graph_retriever = graph_retriever
        self.global_searcher = global_searcher
        self.query_router = query_router
        self.hallucination_guard = hallucination_guard
        self.llm = llm
        self.prompt_builder = prompt_builder or build_default_prompt

    def answer(self, question: str, *, top_k: int = 5, context_only: bool = False) -> GraphRagQAResult:
        question = (question or "").strip()
        if not question:
            raise ValueError(EMPTY_QUESTION_ERROR)
        if top_k < 1:
            raise ValueError(INVALID_TOP_K_ERROR)
        if self.llm is None and not context_only:
            raise GraphRagConfigurationError(MISSING_LLM_ERROR)

        # 1. Route the query if a router is available
        route_strategy = "LOCAL_SEARCH"
        if self.query_router is not None:
            route = self.query_router.route_query(question)
            route_strategy = route.strategy

        # 2. Retrieve evidence selectively based on routing strategy
        text_evidence = []
        graph_evidence = []
        global_context = ""

        # Run text retriever for VECTOR_ONLY and LOCAL_SEARCH (and optionally GLOBAL)
        if route_strategy in ("VECTOR_ONLY", "LOCAL_SEARCH", "GLOBAL_SEARCH"):
            text_raw = _call_retriever(self.text_retriever, question, top_k)
            text_evidence = [
                _normalize_text_evidence(item, rank=rank)
                for rank, item in enumerate(_as_items(text_raw), start=1)
            ]

        # Run graph retriever for LOCAL_SEARCH
        if route_strategy == "LOCAL_SEARCH":
            graph_raw = _call_retriever(self.graph_retriever, question, top_k)
            graph_evidence = [
                _normalize_graph_evidence(item, rank=rank)
                for rank, item in enumerate(_as_items(graph_raw), start=1)
            ]

        # Run global search only for GLOBAL_SEARCH
        if route_strategy == "GLOBAL_SEARCH" and self.global_searcher is not None:
            try:
                gs_result = self.global_searcher.search(question, context_only=True)
                if hasattr(gs_result, "partial_answers") and gs_result.partial_answers:
                    global_context = _format_global_context(gs_result)
            except Exception:  # noqa: BLE001
                pass  # Gracefully skip if global search fails

        context = build_context(question, text_evidence, graph_evidence, global_context)
        citations = [item.to_dict() for item in [*text_evidence, *graph_evidence]]

        if context_only:
            return GraphRagQAResult(
                question=question,
                answer=None,
                context=context,
                citations=citations,
                evidence=citations,
                context_only=True,
            )

        prompt = self.prompt_builder(question, context, citations)
        answer = _call_llm(self.llm, prompt, question=question, context=context, citations=citations)

        # 4. Verify answer if hallucination guard is present
        if self.hallucination_guard is not None and answer:
            guard_result = self.hallucination_guard.verify(answer, context)
            if not guard_result.is_safe:
                answer += "\n\n[System Warning]: Some claims in this answer might not be fully supported by the evidence: " + ", ".join(guard_result.hallucinated_claims)

        return GraphRagQAResult(
            question=question,
            answer=answer,
            context=context,
            citations=citations,
            evidence=citations,
            context_only=False,
            prompt=prompt,
        )


def build_default_prompt(question: str, context: str, citations: list[dict[str, Any]]) -> str:
    citation_ids = ", ".join(citation["id"] for citation in citations) or "none"
    return f"""You are a GraphRAG question-answering assistant.

Use only the retrieved evidence below. Text evidence and graph evidence are both required context.
If the evidence is insufficient, say so clearly. Cite sources with bracket IDs such as [T1] or [G1].

Available citation IDs: {citation_ids}

{context}

Question:
{question}

Answer:
"""


def build_context(
    question: str,
    text_evidence: list[EvidenceItem],
    graph_evidence: list[EvidenceItem],
    global_context: str = "",
) -> str:
    parts = [f"# GraphRAG QA context\n\nQuestion: {question}", "## Text retrieval evidence"]
    if text_evidence:
        for item in text_evidence:
            score = f" score={item.score:.4g}" if item.score is not None else ""
            source = item.source or "unknown source"
            parts.append(f"[{item.citation_id}] {source}{score}\n{item.text}")
    else:
        parts.append("No text retrieval evidence returned.")

    parts.append("## Graph retrieval evidence")
    if graph_evidence:
        for item in graph_evidence:
            triple = _format_graph_triple(item)
            score = f" confidence={item.score:.4g}" if item.score is not None else ""
            source = f" source={item.source}" if item.source else ""
            parts.append(f"[{item.citation_id}] {triple}{source}{score}\nEvidence: {item.text}")
    else:
        parts.append("No graph retrieval evidence returned.")

    if global_context:
        parts.append("## Global context (community-level analysis)")
        parts.append(global_context)

    return "\n\n".join(parts)


def _format_global_context(gs_result: Any) -> str:
    """Format GlobalSearchResult partial answers into context text."""
    sections: list[str] = []
    for pa in gs_result.partial_answers:
        title = pa.get("title", "Community")
        entity_count = pa.get("entity_count", 0)
        answer = pa.get("answer", "")
        sections.append(f"### {title} ({entity_count} entities)\n{answer}")
    return "\n\n".join(sections)


def _format_graph_triple(item: EvidenceItem) -> str:
    if item.subject or item.predicate or item.object_:
        return f"{item.subject or '?'} --{item.predicate or 'RELATED_TO'}--> {item.object_ or '?'}"
    return item.text


def _call_retriever(retriever: Any, question: str, top_k: int) -> Any:
    for method_name in (
        "retrieve",
        "search",
        "query",
        "search_hybrid",
        "search_graph",
        "query_related",
        "query_related_entities",
    ):
        method = getattr(retriever, method_name, None)
        if callable(method):
            return _call_with_top_k(method, question, top_k)
    if callable(retriever):
        return _call_with_top_k(retriever, question, top_k)
    raise TypeError(INVALID_RETRIEVER_ERROR)


def _call_with_top_k(method: Callable[..., Any], question: str, top_k: int) -> Any:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        try:
            return method(question, top_k=top_k)
        except TypeError:
            return method(question, top_k)

    params = signature.parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()) or "top_k" in params:
        return method(question, top_k=top_k)
    for name in ("k", "limit", "n_results"):
        if name in params:
            return method(question, **{name: top_k})
    positional = [
        param
        for param in params.values()
        if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 2:
        return method(question, top_k)
    return method(question)


def _call_llm(llm: Any, prompt: str, **kwargs: Any) -> str:
    if llm is None:
        raise GraphRagConfigurationError(MISSING_LLM_ERROR)

    for method_name in ("generate_answer", "generate", "complete", "invoke"):
        method = getattr(llm, method_name, None)
        if callable(method):
            if method_name == "generate_answer":
                raw = _call_llm_method(method, prompt, kwargs, prompt_as_keyword=True)
            else:
                raw = _call_llm_method(method, prompt, kwargs, prompt_as_keyword=False)
            return _stringify_llm_response(raw)
    if callable(llm):
        return _stringify_llm_response(_call_llm_method(llm, prompt, kwargs, prompt_as_keyword=False))
    raise TypeError(INVALID_LLM_ERROR)


def _call_llm_method(
    method: Callable[..., Any],
    prompt: str,
    kwargs: dict[str, Any],
    *,
    prompt_as_keyword: bool,
) -> Any:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        if prompt_as_keyword:
            return method(prompt=prompt, **kwargs)
        return method(prompt, **kwargs)

    params = signature.parameters
    accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())
    usable_kwargs = kwargs if accepts_kwargs else {key: value for key, value in kwargs.items() if key in params}
    if prompt_as_keyword and ("prompt" in params or accepts_kwargs):
        return method(prompt=prompt, **usable_kwargs)
    if prompt_as_keyword and any(name in params for name in ("question", "context", "citations")):
        return method(**usable_kwargs)
    return method(prompt, **usable_kwargs)


def _stringify_llm_response(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, Mapping):
        for key in ("answer", "content", "text", "output"):
            value = raw.get(key)
            if value is not None:
                return str(value)
    for attr in ("content", "text", "answer"):
        value = getattr(raw, attr, None)
        if value is not None:
            return str(value)
    return str(raw)


def _as_items(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        if "hits" in raw:
            return _as_items(raw["hits"])
        if "results" in raw:
            return _as_items(raw["results"])
        if {"ids", "documents"}.issubset(raw.keys()):
            return _chroma_result_items(raw)
        return [raw]
    if isinstance(raw, tuple):
        return list(raw)
    if isinstance(raw, Iterable) and not isinstance(raw, str | bytes):
        return list(raw)
    return [raw]


def _chroma_result_items(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    ids = _first_result_row(raw.get("ids"))
    documents = _first_result_row(raw.get("documents"))
    metadatas = _first_result_row(raw.get("metadatas"))
    distances = _first_result_row(raw.get("distances"))
    items = []
    for index, document in enumerate(documents):
        items.append(
            {
                "id": _safe_index(ids, index),
                "text": document,
                "metadata": _safe_index(metadatas, index) or {},
                "distance": _safe_index(distances, index),
            }
        )
    return items


def _first_result_row(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    if isinstance(value, list):
        return value
    return []


def _safe_index(values: list[Any], index: int) -> Any:
    if index < len(values):
        return values[index]
    return None


def _normalize_text_evidence(item: Any, *, rank: int) -> EvidenceItem:
    chunk = _lookup(item, "chunk")
    metadata = _as_metadata(_lookup(item, "metadata") or _lookup(chunk, "metadata"))
    text = (
        _lookup(item, "text", "document", "content", "page_content")
        or _lookup(chunk, "text", "content", "page_content")
        or str(item)
    )
    source = (
        _lookup(item, "source", "source_file", "document", "file")
        or metadata.get("source_file")
        or metadata.get("source")
        or metadata.get("document")
    )
    score = _as_float(
        _lookup(item, "score", "similarity", "rrf_score", "semantic_score")
        or _distance_to_score(_lookup(item, "distance"))
    )
    raw_id = _lookup(item, "id", "chunk_id") or _lookup(chunk, "id", "chunk_id")
    return EvidenceItem(
        citation_id=f"T{rank}",
        source_type="text",
        rank=rank,
        text=str(text).strip(),
        source=str(source) if source else None,
        score=score,
        metadata=metadata,
        raw_id=str(raw_id) if raw_id else None,
    )


def _normalize_graph_evidence(item: Any, *, rank: int) -> EvidenceItem:
    metadata = _as_metadata(_lookup(item, "metadata"))
    subject = _lookup(item, "subject", "head", "source_node", "from_node", "src")
    predicate = _lookup(item, "predicate", "relation", "relationship", "edge_type", "label")
    obj = _lookup(item, "object", "tail", "target_node", "to_node", "dst", "target")
    evidence_text = (
        _lookup(item, "evidence", "evidence_text", "text", "description", "content")
        or metadata.get("evidence")
        or metadata.get("evidence_text")
    )
    if not evidence_text and (subject or predicate or obj):
        evidence_text = f"{subject or '?'} --{predicate or 'RELATED_TO'}--> {obj or '?'}"
    source = (
        _lookup(item, "source", "source_file", "evidence_doc", "document", "file")
        or metadata.get("source_file")
        or metadata.get("evidence_doc")
        or metadata.get("source")
    )
    score = _as_float(_lookup(item, "confidence", "score", "weight"))
    raw_id = _lookup(item, "id", "edge_id", "triple_id")
    return EvidenceItem(
        citation_id=f"G{rank}",
        source_type="graph",
        rank=rank,
        text=str(evidence_text or item).strip(),
        source=str(source) if source else None,
        score=score,
        metadata=metadata,
        raw_id=str(raw_id) if raw_id else None,
        subject=str(subject) if subject else None,
        predicate=str(predicate) if predicate else None,
        object_=str(obj) if obj else None,
    )


def _lookup(item: Any, *names: str) -> Any:
    if item is None:
        return None
    if isinstance(item, Mapping):
        for name in names:
            if name in item and item[name] is not None:
                return item[name]
        return None
    for name in names:
        value = getattr(item, name, None)
        if value is not None:
            return value
    return None


def _as_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_to_score(value: Any) -> float | None:
    distance = _as_float(value)
    if distance is None:
        return None
    return 1.0 - distance
