from __future__ import annotations

import inspect
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from retrieval_engine import DocumentChunk, RetrievalResult

LightRagMode = Literal["naive", "local", "global", "hybrid", "mix"]

_MODE_PATHS: dict[LightRagMode, tuple[str, ...]] = {
    "naive": ("naive",),
    "local": ("local",),
    "global": ("global",),
    "hybrid": ("local", "global"),
    "mix": ("naive", "local", "global"),
}


@dataclass(slots=True)
class LightRagDiagnostics:
    question: str = ""
    mode: LightRagMode = "mix"
    top_k: int = 5
    route_strategy: str = ""
    naive_count: int = 0
    local_count: int = 0
    global_count: int = 0
    final_count: int = 0
    fusion_mode: str = "rrf"
    active_paths: tuple[str, ...] = field(default_factory=tuple)
    source_type_counts: dict[str, int] = field(default_factory=dict)
    global_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LightRagContextResult:
    question: str
    mode: LightRagMode
    context: str
    results: list[RetrievalResult]
    diagnostics: LightRagDiagnostics

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "mode": self.mode,
            "context": self.context,
            "results": [_result_to_dict(result) for result in self.results],
            "diagnostics": self.diagnostics.to_dict(),
        }


class LightRagQueryEngine:
    """LightRAG-style retrieval coordinator over existing text, graph, and global search.

    It implements LightRAG's practical query modes without replacing the
    repository's current retrievers:
    - naive: text/vector/keyword retrieval only.
    - local: low-level entity neighborhood graph retrieval.
    - global: high-level community summary retrieval.
    - hybrid: local + global.
    - mix: naive + local + global.
    """

    def __init__(
        self,
        *,
        text_retriever: Any,
        graph_retriever: Any,
        global_searcher: Any | None = None,
        rrf_k: float = 60.0,
    ) -> None:
        self.text_retriever = text_retriever
        self.graph_retriever = graph_retriever
        self.global_searcher = global_searcher
        self.rrf_k = float(rrf_k)
        self.last_diagnostics = LightRagDiagnostics()

    def retrieve(self, question: str, *, mode: LightRagMode = "mix", top_k: int = 5) -> list[RetrievalResult]:
        question = (question or "").strip()
        if not question:
            raise ValueError("question must not be empty")
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if mode not in _MODE_PATHS:
            raise ValueError(f"Unsupported LightRAG mode: {mode}")

        diagnostics = LightRagDiagnostics(question=question, mode=mode, top_k=top_k)
        self.last_diagnostics = diagnostics

        path_results: dict[str, list[RetrievalResult]] = {}
        if "naive" in _MODE_PATHS[mode]:
            path_results["naive"] = _tag_results(
                _call_retriever(self.text_retriever, question, top_k),
                path="naive",
            )
            diagnostics.naive_count = len(path_results["naive"])

        if "local" in _MODE_PATHS[mode]:
            path_results["local"] = _tag_results(
                _call_retriever(self.graph_retriever, question, top_k),
                path="local",
            )
            diagnostics.local_count = len(path_results["local"])

        if "global" in _MODE_PATHS[mode]:
            try:
                path_results["global"] = self._global_results(question, top_k)
            except Exception as exc:  # noqa: BLE001
                diagnostics.global_error = f"{exc.__class__.__name__}: {exc}"
                path_results["global"] = []
            diagnostics.global_count = len(path_results["global"])

        results = _fuse_rrf(path_results, top_k=top_k, rrf_k=self.rrf_k)
        diagnostics.final_count = len(results)
        return results

    def build_context(self, question: str, *, mode: LightRagMode = "mix", top_k: int = 5) -> LightRagContextResult:
        results = self.retrieve(question, mode=mode, top_k=top_k)
        context = _build_context(question=question, mode=mode, results=results)
        return LightRagContextResult(
            question=question,
            mode=mode,
            context=context,
            results=results,
            diagnostics=self.last_diagnostics,
        )

    def query(self, question: str, *, mode: LightRagMode = "mix", top_k: int = 5) -> LightRagContextResult:
        return self.build_context(question, mode=mode, top_k=top_k)

    def _global_results(self, question: str, top_k: int) -> list[RetrievalResult]:
        if self.global_searcher is None:
            return []
        search = getattr(self.global_searcher, "search", None)
        if not callable(search):
            return []
        result = _call_global_search(search, question)
        partial_answers = _lookup(result, "partial_answers") or []
        output: list[RetrievalResult] = []
        for index, item in enumerate(_as_items(partial_answers), start=1):
            if not isinstance(item, Mapping):
                continue
            answer = str(item.get("answer") or item.get("summary") or "").strip()
            if not answer:
                continue
            community_id = str(item.get("community_id") or f"global-{index}")
            entity_count = _as_float(item.get("entity_count")) or 1.0
            chunk = DocumentChunk.from_text(
                answer,
                metadata={
                    "chunk_id": f"community-{community_id}",
                    "source_type": "community_summary",
                    "community_id": community_id,
                    "title": item.get("title"),
                    "entity_count": item.get("entity_count"),
                    "lightrag_path": "global",
                },
                source=f"community:{community_id}",
                chunk_id=f"community-{community_id}",
            )
            output.append(
                RetrievalResult(
                    chunk=chunk,
                    score=min(1.0, 0.5 + entity_count / 100.0),
                    retriever_name="lightrag_global",
                    component_scores={"global": min(1.0, 0.5 + entity_count / 100.0)},
                )
            )
            if len(output) >= top_k:
                break
        return output


def _call_retriever(retriever: Any, question: str, top_k: int) -> list[RetrievalResult]:
    method = getattr(retriever, "retrieve", None)
    if callable(method):
        raw = method(question, top_k=top_k)
    elif callable(retriever):
        raw = retriever(question, top_k=top_k)
    else:
        return []
    return [_coerce_result(item) for item in _as_items(raw)]


def _call_global_search(search: Any, question: str) -> Any:
    try:
        signature = inspect.signature(search)
    except (TypeError, ValueError):
        return search(question, context_only=True)
    if "context_only" in signature.parameters or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()
    ):
        return search(question, context_only=True)
    return search(question)


def _coerce_result(item: Any) -> RetrievalResult:
    if isinstance(item, RetrievalResult):
        return item
    chunk = _lookup(item, "chunk")
    text = _lookup(item, "text", "document", "content") or _lookup(chunk, "text", "content") or str(item)
    metadata = _lookup(item, "metadata") or _lookup(chunk, "metadata") or {}
    score = _as_float(_lookup(item, "score", "similarity")) or 0.0
    source = _lookup(item, "source") or _lookup(chunk, "source")
    chunk_id = _lookup(item, "chunk_id", "id") or _lookup(chunk, "chunk_id", "id")
    return RetrievalResult(
        chunk=DocumentChunk.from_text(str(text), metadata=_as_metadata(metadata), source=source, chunk_id=chunk_id),
        score=score,
        retriever_name=str(_lookup(item, "retriever_name") or "unknown"),
    )


def _tag_results(results: list[RetrievalResult], *, path: str) -> list[RetrievalResult]:
    tagged: list[RetrievalResult] = []
    for result in results:
        metadata = dict(result.metadata)
        metadata["lightrag_path"] = path
        chunk = DocumentChunk.from_text(
            result.text,
            metadata=metadata,
            source=result.source,
            page=result.page,
            chunk_id=result.chunk_id,
        )
        tagged.append(
            RetrievalResult(
                chunk=chunk,
                score=result.score,
                retriever_name=f"lightrag_{path}",
                component_scores={**result.component_scores, path: result.score},
            )
        )
    return tagged


def _fuse_rrf(path_results: dict[str, list[RetrievalResult]], *, top_k: int, rrf_k: float) -> list[RetrievalResult]:
    merged: dict[tuple[str, str], RetrievalResult] = {}
    first_seen: dict[tuple[str, str], int] = {}
    seen_index = 0
    for path, results in path_results.items():
        for rank, result in enumerate(results, start=1):
            key = result.chunk.identity_key
            score = 1.0 / (rrf_k + rank)
            if key not in merged:
                first_seen[key] = seen_index
                seen_index += 1
                merged[key] = RetrievalResult(
                    chunk=result.chunk,
                    score=score,
                    retriever_name="lightrag",
                    component_scores={f"rrf:{path}": score},
                )
                continue
            merged[key].score += score
            merged[key].component_scores[f"rrf:{path}"] = merged[key].component_scores.get(f"rrf:{path}", 0.0) + score

    return sorted(
        merged.values(),
        key=lambda item: (-item.score, first_seen[item.chunk.identity_key]),
    )[:top_k]


def _build_context(*, question: str, mode: LightRagMode, results: list[RetrievalResult]) -> str:
    parts = [f"# LightRAG context\n\nQuestion: {question}\nMode: {mode}"]
    sections = (
        ("naive", "## Naive text evidence"),
        ("local", "## Local graph evidence"),
        ("global", "## Global community evidence"),
    )
    for path, title in sections:
        path_items = [result for result in results if result.metadata.get("lightrag_path") == path]
        parts.append(title)
        if not path_items:
            parts.append("No evidence returned.")
            continue
        for index, result in enumerate(path_items, start=1):
            source = result.source or result.metadata.get("source_file") or "unknown source"
            parts.append(f"[{path.upper()}-{index}] {source} score={result.score:.4g}\n{result.text}")
    return "\n\n".join(parts)


def _result_to_dict(result: RetrievalResult) -> dict[str, Any]:
    return {
        "text": result.text,
        "score": result.score,
        "source": result.source,
        "page": result.page,
        "chunk_id": result.chunk_id,
        "metadata": dict(result.metadata),
        "component_scores": dict(result.component_scores),
    }


def _as_items(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        if "results" in raw:
            return _as_items(raw["results"])
        if "hits" in raw:
            return _as_items(raw["hits"])
        return [raw]
    if isinstance(raw, Iterable) and not isinstance(raw, str | bytes):
        return list(raw)
    return [raw]


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
    return dict(value) if isinstance(value, Mapping) else {}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
