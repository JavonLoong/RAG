"""Unified, contract-facing query execution for the GraphRAG console."""

from __future__ import annotations

import math
import os
import re
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Any, Generic, Literal, Protocol, TypeVar, cast

from core_domain.query_contracts import (
    AnswerPayload,
    Citation,
    CitationEvent,
    CitationType,
    ContextItem,
    ContextPayload,
    DebugPayload,
    FinalEvent,
    GraphTriple,
    MetaEvent,
    ModeDecision,
    QueryMode,
    QueryRequest,
    QueryResponse,
    QueryStatus,
    QueryStreamEvent,
    RetrievalSummary,
    SourceRef,
    UsageMetrics,
    WarningItem,
)

from .workspace_registry import WorkspaceConfig

LLM_NOT_CONFIGURED_ERROR = "LLM is not configured."
INVALID_ROUTER_ERROR = "Query router must expose route_query or be callable."
INVALID_RETRIEVER_ERROR = "Retriever must expose retrieve, search, query, or be callable."
INVALID_GLOBAL_SEARCH_ERROR = "Global searcher must expose search or be callable."
INVALID_LLM_ERROR = "LLM must expose generate, complete, invoke, or be callable."

FinishReason = Literal["stop", "length", "content_filter", "error"]
_FINISH_REASONS: tuple[FinishReason, ...] = ("stop", "length", "content_filter", "error")
WorkspaceT = TypeVar("WorkspaceT")
WorkspaceT_co = TypeVar("WorkspaceT_co", covariant=True)
WorkspaceT_contra = TypeVar("WorkspaceT_contra", contravariant=True)


@dataclass(frozen=True, slots=True)
class QueryRuntime:
    """Workspace-bound runtime dependencies used by one query."""

    text_retriever: Any
    graph_retriever: Any | None
    global_searcher: Any | None
    query_router: Any | None
    reranker: Any | None
    hallucination_guard: Any | None
    llm: Any | None


class QueryWorkspaceRegistry(Protocol[WorkspaceT_co]):
    """Registry boundary used by the query service."""

    def get(self, workspace_id: str) -> WorkspaceT_co:
        """Resolve one logical workspace."""


class QueryRuntimeFactory(Protocol[WorkspaceT_contra]):
    """Factory boundary that keeps workspace construction out of QueryService."""

    def create(self, workspace: WorkspaceT_contra) -> QueryRuntime:
        """Build the runtime dependencies for a resolved workspace."""


class _EngineBridge(Protocol):
    """Typed boundary for the dynamically loaded production bridge."""

    def get_chroma_retriever(
        self,
        persist_path: str | Path,
        collection_name: str,
        *,
        embedding_function: Any | None = None,
    ) -> Any: ...

    def get_hybrid_retriever(self, retrievers: list[Any], *, reranker: Any | None = None) -> Any: ...

    def get_llm_client(self, *, api_key: str, base_url: str, model: str) -> Any: ...

    def get_graph_store(self, db_path: str | Path) -> Any: ...

    def get_global_search(self, *, graph_store: Any, llm_client: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class NormalizedQueryResult:
    mode_used: QueryMode
    mode_reason: str
    answer_text: str
    finish_reason: FinishReason
    citations: list[Citation]
    context_items: list[ContextItem]
    rendered_context: str | None
    retrieval: RetrievalSummary
    llm_calls: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    warnings: list[WarningItem]
    prompt: str | None
    raw_mode_result: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class _ScoredResult:
    original: Any
    score: float


class _LazyComponent:
    """Construct one runtime dependency only when its selected path needs it."""

    def __init__(self, builder: Callable[[], Any]) -> None:
        self._builder = builder
        self._value: Any = None
        self._built = False

    def get(self) -> Any:
        if not self._built:
            self._value = self._builder()
            self._built = True
        return self._value

    def __getattr__(self, name: str) -> Any:
        return getattr(self.get(), name)


class QueryExecutionError(RuntimeError):
    """Stable internal error for the HTTP and CLI adapters to map."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = dict(details or {})
        super().__init__(message)


def encode_sse(event: QueryStreamEvent) -> bytes:
    """Serialize one typed query stream event as a complete SSE frame."""

    payload = event.model_dump_json(exclude_none=True)
    return f"event: {event.event}\ndata: {payload}\n\n".encode()


def uuid4_string() -> str:
    return str(uuid.uuid4())


class EngineQueryRuntimeFactory:
    """Build production runtimes through the existing bridge factories."""

    def __init__(
        self,
        *,
        embedding_function: Any | None = None,
        reranker: Any | None = None,
        llm: Any | None = None,
        query_router: Any | None = None,
        hallucination_guard: Any | None = None,
        global_searcher: Any | None = None,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4.1-mini",
    ) -> None:
        self.embedding_function = embedding_function
        self.reranker = reranker
        self.llm = llm
        self.query_router = query_router
        self.hallucination_guard = hallucination_guard
        self.global_searcher = global_searcher
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def create(self, workspace: WorkspaceConfig) -> QueryRuntime:
        from rag_orchestrator.hallucination_guard import HallucinationGuard
        from rag_orchestrator.router import AdaptiveQueryRouter

        engine_bridge = cast(_EngineBridge, import_module(f"{__package__}.engine_bridge"))
        graph_module = import_module("retrieval_engine.graph")
        sqlite_graph_retriever = cast(Callable[[Any], Any], graph_module.SQLiteGraphRetriever)

        text_retriever = engine_bridge.get_chroma_retriever(
            workspace.chroma_persist_dir,
            workspace.chroma_collection,
            embedding_function=self.embedding_function,
        )
        if self.reranker is not None:
            text_retriever = engine_bridge.get_hybrid_retriever(
                [text_retriever],
                reranker=self.reranker,
            )

        llm = self.llm
        api_key = (self.api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
        if llm is None and api_key:
            llm = engine_bridge.get_llm_client(
                api_key=api_key,
                base_url=self.base_url,
                model=self.model,
            )

        graph_retriever = None
        graph_bundle: _LazyComponent | None = None
        if workspace.graph_db_path is not None:
            graph_db_path = workspace.graph_db_path
            graph_bundle = _LazyComponent(
                lambda: _build_graph_bundle(
                    engine_bridge,
                    sqlite_graph_retriever,
                    graph_db_path,
                )
            )
            graph_retriever = _LazyComponent(lambda: graph_bundle.get()[1])

        global_searcher = self.global_searcher
        if global_searcher is None and graph_bundle is not None and llm is not None:
            global_searcher = _LazyComponent(
                lambda: engine_bridge.get_global_search(
                    graph_store=graph_bundle.get()[0],
                    llm_client=llm,
                )
            )

        query_router = self.query_router
        if query_router is None and llm is not None:
            query_router = AdaptiveQueryRouter(llm)

        hallucination_guard = self.hallucination_guard
        if hallucination_guard is None and llm is not None:
            hallucination_guard = HallucinationGuard(llm)

        return QueryRuntime(
            text_retriever=text_retriever,
            graph_retriever=graph_retriever,
            global_searcher=global_searcher,
            query_router=query_router,
            reranker=self.reranker,
            hallucination_guard=hallucination_guard,
            llm=llm,
        )


class QueryService(Generic[WorkspaceT]):
    """Execute one query and map runtime output to the v1 response contract."""

    def __init__(
        self,
        registry: QueryWorkspaceRegistry[WorkspaceT],
        runtime_factory: QueryRuntimeFactory[WorkspaceT],
        *,
        id_factory: Callable[[], str] = uuid4_string,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.registry = registry
        self.runtime_factory = runtime_factory
        self.id_factory = id_factory
        self.clock = clock

    def query(self, request: QueryRequest) -> QueryResponse:
        started = self.clock()
        request_id = self.id_factory()
        trace_id = self.id_factory()
        workspace = self.registry.get(request.workspace_id)
        if request.mode is not QueryMode.AUTO:
            _ensure_mode_supported(workspace, request.mode)
            _ensure_index_ready(workspace, request.mode)
        try:
            runtime = self.runtime_factory.create(workspace)
        except QueryExecutionError:
            raise
        except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
            raise _index_not_ready(exc, stage="runtime_factory") from exc
        except Exception as exc:
            raise _query_failed("Query runtime construction failed.", exc, stage="runtime_factory") from exc  # noqa: TRY003
        mode, mode_reason = self._select_mode(runtime, workspace, request)
        _ensure_mode_supported(workspace, mode)
        _ensure_index_ready(workspace, mode)
        _ensure_generation_available(runtime, mode)
        normalized = self._execute_mode(
            runtime,
            request,
            mode_used=mode,
            mode_reason=mode_reason,
        )
        return self._build_response(
            request=request,
            normalized=normalized,
            request_id=request_id,
            trace_id=trace_id,
            latency_ms=(self.clock() - started) * 1000,
        )

    def stream(self, request: QueryRequest) -> Iterator[QueryStreamEvent]:
        """Return deterministic typed events for the synchronous query adapters."""

        response = self.query(request)
        events: list[QueryStreamEvent] = [
            MetaEvent(
                request_id=response.request_id,
                sequence=1,
                mode=response.mode,
                token_streaming=False,
            )
        ]
        events.extend(
            CitationEvent(
                request_id=response.request_id,
                sequence=sequence,
                citation=citation,
            )
            for sequence, citation in enumerate(response.citations, start=2)
        )
        events.append(
            FinalEvent(
                request_id=response.request_id,
                sequence=len(events) + 1,
                response=response,
            )
        )
        return iter(events)

    def _select_mode(
        self,
        runtime: QueryRuntime,
        workspace: Any,
        request: QueryRequest,
    ) -> tuple[QueryMode, str]:
        if request.mode is not QueryMode.AUTO:
            return request.mode, f"explicit {request.mode.value} mode"

        if runtime.query_router is not None:
            try:
                route = _call_router(runtime.query_router, request.query)
                strategy = str(_lookup(route, "strategy") or route).upper()
                selected = {
                    "VECTOR_ONLY": QueryMode.VECTOR,
                    "VECTOR": QueryMode.VECTOR,
                    "LOCAL_SEARCH": QueryMode.LOCAL,
                    "LOCAL": QueryMode.LOCAL,
                    "GLOBAL_SEARCH": QueryMode.GLOBAL,
                    "GLOBAL": QueryMode.GLOBAL,
                    "HYBRID": QueryMode.HYBRID,
                }.get(strategy)
                if selected is not None:
                    return selected, "query router selected mode"
            except Exception:
                return _default_mode(workspace), "query router failed; workspace default mode used"

        selected = _default_mode(workspace)
        return selected, "workspace default mode"

    def _execute_mode(  # noqa: C901
        self,
        runtime: QueryRuntime,
        request: QueryRequest,
        *,
        mode_used: QueryMode | None = None,
        mode_reason: str | None = None,
    ) -> NormalizedQueryResult:
        mode_used = mode_used or request.mode
        if mode_used is QueryMode.AUTO:
            mode_used = QueryMode.LOCAL
        mode_reason = mode_reason or f"{mode_used.value} mode"

        text_raw: list[Any] = []
        graph_raw: list[Any] = []
        global_raw: Any | None = None
        warnings: list[WarningItem] = []
        text_reranked = False

        if mode_used in (QueryMode.VECTOR, QueryMode.LOCAL, QueryMode.HYBRID):
            try:
                text_raw = _retrieve(runtime.text_retriever, request.query, request.top_k)
                text_raw, text_reranked, rerank_error = _apply_reranker(
                    runtime.text_retriever,
                    runtime.reranker,
                    request.query,
                    text_raw,
                    request.top_k,
                )
                if rerank_error is not None:
                    warnings.append(
                        WarningItem(
                            code="RERANKING_DEGRADED",
                            message="Reranking degraded.",
                        )
                    )
            except Exception as exc:
                if mode_used is QueryMode.VECTOR:
                    raise _query_failed("Text retrieval failed.", exc, stage="text_retrieval") from exc  # noqa: TRY003
                warnings.append(
                    WarningItem(
                        code="TEXT_RETRIEVAL_DEGRADED",
                        message="Text retrieval degraded.",
                    )
                )

        if mode_used in (QueryMode.LOCAL, QueryMode.HYBRID):
            if runtime.graph_retriever is None:
                warnings.append(
                    WarningItem(
                        code="GRAPH_RETRIEVAL_DEGRADED",
                        message="Graph retrieval is not configured.",
                    )
                )
            else:
                try:
                    graph_raw = _retrieve(runtime.graph_retriever, request.query, request.top_k)
                except Exception:
                    warnings.append(
                        WarningItem(
                            code="GRAPH_RETRIEVAL_DEGRADED",
                            message="Graph retrieval degraded.",
                        )
                    )

        if mode_used in (QueryMode.GLOBAL, QueryMode.HYBRID):
            if runtime.global_searcher is None:
                warnings.append(
                    WarningItem(
                        code="GLOBAL_SEARCH_DEGRADED",
                        message="Global search is not configured.",
                    )
                )
            else:
                try:
                    global_raw = _global_search(
                        runtime.global_searcher,
                        request.query,
                        context_only=mode_used is QueryMode.HYBRID,
                    )
                except Exception:
                    warnings.append(
                        WarningItem(
                            code="GLOBAL_SEARCH_DEGRADED",
                            message="Global search degraded.",
                        )
                    )

        text_citations = [_text_citation(item, rank=index) for index, item in enumerate(text_raw, start=1)]
        graph_citations = [_graph_citation(item, rank=index) for index, item in enumerate(graph_raw, start=1)]
        community_citations = _community_citations(global_raw)
        citations = [*text_citations, *graph_citations, *community_citations]

        answer_text = ""
        finish_reason = "stop"
        prompt: str | None = None
        llm_calls: int | None = None
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        llm_raw: Any | None = None
        execution_context: str | None = None

        if mode_used is QueryMode.VECTOR:
            answer_text = "\n\n".join(citation.quote for citation in text_citations)
        elif mode_used is QueryMode.GLOBAL:
            answer_text = str(_lookup(global_raw, "answer") or "")
            if not answer_text:
                answer_text = "\n\n".join(citation.quote for citation in community_citations)
        else:
            execution_context = _render_context(citations, request.query)
            prompt = _build_prompt(request.query, execution_context, citations)
            try:
                if runtime.llm is None:
                    raise _llm_unavailable(stage="answer_generation")  # noqa: TRY301
                llm_value = _call_llm(runtime.llm, prompt)
                answer_text = llm_value[0]
                finish_reason = llm_value[1]
                llm_calls = 1
                prompt_tokens = llm_value[2]
                completion_tokens = llm_value[3]
                llm_raw = llm_value[4]
            except QueryExecutionError:
                raise
            except Exception as exc:
                if not citations:
                    raise _query_failed("Answer generation failed.", exc, stage="answer_generation") from exc  # noqa: TRY003
                warnings.append(
                    WarningItem(
                        code="ANSWER_GENERATION_DEGRADED",
                        message="Answer generation degraded.",
                    )
                )

        if mode_used in (QueryMode.LOCAL, QueryMode.HYBRID) and answer_text and runtime.hallucination_guard is not None:
            guard_warning, guard_suffix = _verify_answer(
                runtime.hallucination_guard,
                answer_text,
                execution_context or _render_context(citations, request.query),
            )
            if guard_warning is not None:
                warnings.append(guard_warning)
                answer_text += guard_suffix

        if not answer_text and not citations and warnings:
            raise _query_failed(  # noqa: TRY003
                "All query paths failed.", RuntimeError("no usable query output"), stage="query"
            )

        rendered_context = _render_context(citations, request.query) if citations else None
        context_items = [
            ContextItem(
                id=citation.id,
                type=citation.type,
                text=citation.quote,
                source=citation.source,
                score=citation.score,
            )
            for citation in citations
        ]
        retrieval = RetrievalSummary(
            text_hits=len(text_citations),
            graph_hits=len(graph_citations),
            community_hits=len(community_citations),
            communities_searched=_as_int(_lookup(global_raw, "communities_searched")) or 0,
            reranked=text_reranked,
        )
        raw_mode_result = {
            "mode": mode_used.value,
            "text_results": text_raw,
            "graph_results": graph_raw,
            "global_result": global_raw,
            "llm_result": llm_raw,
        }
        return NormalizedQueryResult(
            mode_used=mode_used,
            mode_reason=mode_reason,
            answer_text=answer_text,
            finish_reason=_normalize_finish_reason(finish_reason),
            citations=citations,
            context_items=context_items,
            rendered_context=rendered_context,
            retrieval=retrieval,
            llm_calls=llm_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            warnings=warnings,
            prompt=prompt,
            raw_mode_result=raw_mode_result,
        )

    def _build_response(
        self,
        *,
        request: QueryRequest,
        normalized: NormalizedQueryResult,
        request_id: str,
        trace_id: str,
        latency_ms: float,
    ) -> QueryResponse:
        context = None
        if request.include_context:
            context = ContextPayload(
                items=normalized.context_items,
                rendered_text=normalized.rendered_context,
            )
        debug = None
        if request.include_debug:
            debug = DebugPayload(
                prompt=_json_safe(normalized.prompt),
                raw_mode_result=_json_safe(normalized.raw_mode_result),
            )
        return QueryResponse(
            request_id=request_id,
            trace_id=trace_id,
            status=QueryStatus.PARTIAL if normalized.warnings else QueryStatus.OK,
            mode=ModeDecision(
                requested=request.mode,
                used=normalized.mode_used,
                reason=normalized.mode_reason,
            ),
            answer=AnswerPayload(text=normalized.answer_text, finish_reason=normalized.finish_reason),
            citations=normalized.citations,
            context=context,
            retrieval=normalized.retrieval,
            usage=UsageMetrics(
                latency_ms=latency_ms,
                llm_calls=normalized.llm_calls,
                prompt_tokens=normalized.prompt_tokens,
                completion_tokens=normalized.completion_tokens,
            ),
            warnings=normalized.warnings,
            debug=debug,
        )


def _ensure_mode_supported(workspace: Any, mode: QueryMode) -> None:
    supported_modes = getattr(workspace, "supported_modes", None)
    if supported_modes is None or mode is QueryMode.AUTO:
        return
    normalized_modes = {QueryMode(item) if isinstance(item, str) else item for item in supported_modes}
    if mode not in normalized_modes:
        raise QueryExecutionError(
            "MODE_UNAVAILABLE",
            f"Query mode '{mode.value}' is not available for this workspace.",
            retryable=False,
            details={"mode": mode.value},
        )


def _ensure_index_ready(workspace: Any, mode: QueryMode) -> None:
    required_paths: list[tuple[str, Path, bool]] = []
    chroma_path = getattr(workspace, "chroma_persist_dir", None)
    if mode in (QueryMode.VECTOR, QueryMode.LOCAL, QueryMode.HYBRID) and chroma_path is not None:
        required_paths.append(("chroma", Path(chroma_path), True))

    graph_path = getattr(workspace, "graph_db_path", None)
    if mode in (QueryMode.LOCAL, QueryMode.GLOBAL, QueryMode.HYBRID) and graph_path is not None:
        required_paths.append(("graph", Path(graph_path), False))

    for resource, path, require_directory in required_paths:
        if not path.exists() or (require_directory and not path.is_dir()):
            raise _index_not_ready(RuntimeError(f"{resource} query data is not ready."), stage=resource)


def _ensure_generation_available(runtime: QueryRuntime, mode: QueryMode) -> None:
    if mode in (QueryMode.LOCAL, QueryMode.HYBRID) and runtime.llm is None:
        raise _llm_unavailable(stage="answer_generation")


def _index_not_ready(cause: Exception, *, stage: str) -> QueryExecutionError:
    return QueryExecutionError(
        "INDEX_NOT_READY",
        "Required query data is not ready.",
        retryable=True,
        details={"stage": stage, "cause": str(cause)},
    )


def _llm_unavailable(*, stage: str) -> QueryExecutionError:
    return QueryExecutionError(
        "LLM_UNAVAILABLE",
        LLM_NOT_CONFIGURED_ERROR,
        retryable=True,
        details={"stage": stage},
    )


def _default_mode(workspace: Any) -> QueryMode:
    configured = getattr(workspace, "default_mode", QueryMode.LOCAL)
    if isinstance(configured, str):
        configured = QueryMode(configured)
    return configured if configured is not QueryMode.AUTO else QueryMode.LOCAL


def _normalize_finish_reason(value: str) -> FinishReason:
    if value in _FINISH_REASONS:
        return cast(FinishReason, value)
    return "stop"


def _build_graph_bundle(
    bridge: Any,
    graph_retriever_type: Callable[[Any], Any],
    db_path: Path,
) -> tuple[Any, Any]:
    graph_store = bridge.get_graph_store(db_path)
    return graph_store, graph_retriever_type(graph_store)


def _call_router(router: Any, question: str) -> Any:
    method = getattr(router, "route_query", None)
    if callable(method):
        return method(question)
    if callable(router):
        return router(question)
    raise TypeError(INVALID_ROUTER_ERROR)


def _retrieve(retriever: Any, query: str, top_k: int) -> list[Any]:
    for method_name in ("retrieve", "search", "query"):
        method = getattr(retriever, method_name, None)
        if callable(method):
            result = method(query, top_k=top_k)
            return list(result or [])
    if callable(retriever):
        return list(retriever(query, top_k=top_k) or [])
    raise TypeError(INVALID_RETRIEVER_ERROR)


def _apply_reranker(
    retriever: Any,
    reranker: Any | None,
    query: str,
    items: list[Any],
    top_k: int,
) -> tuple[list[Any], bool, Exception | None]:
    if reranker is None or not items:
        return items, False, None
    if getattr(retriever, "reranker", None) is reranker:
        return items, True, None
    method = getattr(reranker, "rerank", None)
    if not callable(method):
        return items, False, TypeError("Reranker must expose rerank.")
    try:
        documents = [_result_text(item) for item in items]
        ranked = list(method(query, documents, top_k=top_k))
        scored_items: list[_ScoredResult] = []
        for pair in ranked:
            index, score = pair
            if not isinstance(index, int) or not 0 <= index < len(items):
                continue
            parsed_score = _as_float(score)
            if parsed_score is not None:
                scored_items.append(_ScoredResult(original=items[index], score=parsed_score))
        return (scored_items, bool(scored_items), None) if scored_items else (items, False, None)
    except Exception as exc:
        return items, False, exc


def _result_text(item: Any) -> str:
    chunk = _lookup(item, "chunk") or item
    return str(_lookup(item, "text", "content", "document") or _lookup(chunk, "text", "content", "document") or item)


def _verify_answer(
    guard: Any,
    answer: str,
    context: str,
) -> tuple[WarningItem | None, str]:
    verify = getattr(guard, "verify", None)
    if not callable(verify):
        return (
            WarningItem(
                code="HALLUCINATION_GUARD_DEGRADED",
                message="Hallucination guard does not expose verify.",
            ),
            "",
        )
    try:
        result = verify(answer, context)
    except Exception:
        return (
            WarningItem(
                code="HALLUCINATION_GUARD_DEGRADED",
                message="Hallucination guard degraded.",
            ),
            "",
        )
    if bool(_lookup(result, "is_safe")):
        return None, ""
    warning = WarningItem(
        code="HALLUCINATION_GUARD_FLAGGED",
        message="Hallucination guard flagged unsupported claims.",
    )
    return warning, "\n\n[System Warning]: unsupported claims detected"


def _global_search(searcher: Any, query: str, *, context_only: bool) -> Any:
    method = getattr(searcher, "search", None)
    if callable(method):
        return method(query, context_only=context_only)
    if callable(searcher):
        return searcher(query, context_only=context_only)
    raise TypeError(INVALID_GLOBAL_SEARCH_ERROR)


def _call_llm(llm: Any, prompt: str) -> tuple[str, str, int | None, int | None, Any]:
    result: Any
    for method_name in ("generate", "complete", "invoke"):
        method = getattr(llm, method_name, None)
        if callable(method):
            result = method(prompt)
            break
    else:
        if not callable(llm):
            raise TypeError(INVALID_LLM_ERROR)
        result = llm(prompt)

    if isinstance(result, str):
        return result.strip(), "stop", None, None, None
    content = _lookup(result, "content", "answer", "text")
    if content is None:
        content = str(result)
    usage = _lookup(result, "usage")
    return (
        str(content).strip(),
        str(_lookup(result, "finish_reason") or "stop"),
        _as_int(_lookup(usage, "prompt_tokens")),
        _as_int(_lookup(usage, "completion_tokens")),
        _lookup(result, "raw") or result,
    )


def _text_citation(item: Any, *, rank: int) -> Citation:
    item, reranked_score = _unwrap_scored(item)
    chunk = _lookup(item, "chunk") or item
    metadata = _mapping(_lookup(item, "metadata")) or _mapping(_lookup(chunk, "metadata"))
    text = _lookup(item, "text", "content", "document") or _lookup(chunk, "text", "content", "document") or ""
    source = _lookup(item, "source", "source_file", "file") or _lookup(chunk, "source", "source_file", "file")
    page = _lookup(item, "page", "page_num", "page_number", "source_page")
    if page is None:
        page = _lookup(chunk, "page", "page_num", "page_number", "source_page") or _lookup(
            metadata, "page", "page_num", "page_number", "source_page"
        )
    chunk_id = (
        _lookup(item, "chunk_id", "id") or _lookup(chunk, "chunk_id", "id") or _lookup(metadata, "chunk_id", "id")
    )
    score = reranked_score if reranked_score is not None else _as_float(_lookup(item, "score", "confidence"))
    if score is None:
        score = _as_float(_lookup(metadata, "score", "confidence"))
    raw_id = _lookup(item, "id", "citation_id") or _lookup(metadata, "citation_id")
    return Citation(
        id=str(raw_id) if raw_id is not None else f"T{rank}",
        type=CitationType.TEXT,
        source=SourceRef(
            document_id=_optional_string(_lookup(metadata, "document_id", "doc_id")),
            file=_optional_string(source),
            page=_normalize_page(page),
            chunk_id=_optional_string(chunk_id),
        ),
        quote=str(text),
        score=score,
        metadata=_json_safe(metadata),
    )


def _unwrap_scored(item: Any) -> tuple[Any, float | None]:
    original = _lookup(item, "original")
    if original is None:
        return item, None
    return original, _as_float(_lookup(item, "score"))


def _graph_citation(item: Any, *, rank: int) -> Citation:
    chunk = _lookup(item, "chunk") or item
    metadata = _mapping(_lookup(item, "metadata")) or _mapping(_lookup(chunk, "metadata"))
    subject = _lookup(item, "subject", "head", "source_node", "from_node", "src") or _lookup(
        metadata, "subject", "head", "source_node", "from_node", "src"
    )
    predicate = _lookup(item, "predicate", "relation", "relationship", "edge_type", "label") or _lookup(
        metadata, "predicate", "relation", "relationship", "edge_type", "label"
    )
    object_value = _lookup(item, "object", "tail", "target_node", "to_node", "dst", "target") or _lookup(
        metadata, "object", "tail", "target_node", "to_node", "dst", "target"
    )
    evidence = _lookup(item, "evidence", "evidence_text", "text", "description", "content") or _lookup(
        chunk, "text", "content"
    )
    if not evidence and (subject or predicate or object_value):
        evidence = f"{subject or '?'} --{predicate or 'RELATED_TO'}--> {object_value or '?'}"
    source = _lookup(item, "source", "source_file", "file") or _lookup(metadata, "source", "source_file", "file")
    page = (
        _lookup(item, "page", "page_num", "page_number", "source_page")
        or _lookup(chunk, "page", "page_num", "page_number", "source_page")
        or _lookup(metadata, "page", "page_num", "page_number", "source_page")
    )
    chunk_id = (
        _lookup(item, "chunk_id", "id", "edge_id", "triple_id")
        or _lookup(chunk, "chunk_id", "id", "edge_id", "triple_id")
        or _lookup(metadata, "chunk_id", "id", "edge_id", "triple_id")
    )
    document_id = _lookup(item, "document_id", "doc_id") or _lookup(metadata, "document_id", "doc_id")
    score = _as_float(_lookup(item, "confidence", "score", "weight"))
    if score is None:
        score = _as_float(_lookup(metadata, "confidence", "score", "weight"))
    raw_id = _lookup(item, "id", "edge_id", "triple_id") or _lookup(metadata, "edge_id", "triple_id")
    triple = None
    if subject is not None and predicate is not None and object_value is not None:
        triple = GraphTriple(subject=str(subject), predicate=str(predicate), object=str(object_value))
    return Citation(
        id=str(raw_id) if raw_id is not None else f"G{rank}",
        type=CitationType.GRAPH,
        source=SourceRef(
            document_id=_optional_string(document_id),
            file=_optional_string(source),
            page=_normalize_page(page),
            chunk_id=_optional_string(chunk_id),
        ),
        quote=str(evidence or ""),
        score=score,
        metadata=_json_safe(metadata),
        triple=triple,
    )


def _community_citations(result: Any) -> list[Citation]:
    partial_answers = _lookup(result, "partial_answers") or []
    citations = []
    for rank, partial in enumerate(partial_answers, start=1):
        community_id = _lookup(partial, "community_id", "id")
        answer = _lookup(partial, "answer", "text", "summary") or ""
        title = _lookup(partial, "title")
        citations.append(
            Citation(
                id=str(community_id) if community_id is not None else f"C{rank}",
                type=CitationType.COMMUNITY,
                source=SourceRef(document_id=_optional_string(community_id), file=_optional_string(title)),
                quote=str(answer),
                score=None,
                metadata=_json_safe(dict(partial) if isinstance(partial, Mapping) else {}),
            )
        )
    return citations


def _render_context(citations: Sequence[Citation], query: str) -> str:
    parts = [f"Question: {query}"]
    for citation in citations:
        parts.append(f"[{citation.id}] {citation.quote}")
    return "\n\n".join(parts)


def _build_prompt(query: str, context: str, citations: Sequence[Citation]) -> str:
    from rag_orchestrator.graphrag_qa import build_default_prompt

    return build_default_prompt(
        query,
        context,
        [citation.model_dump(mode="python") for citation in citations],
    )


def _lookup(value: Any, *names: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        for name in names:
            if name in value and value[name] is not None:
                return value[name]
        return None
    for name in names:
        result = getattr(value, name, None)
        if result is not None:
            return result
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _normalize_page(value: Any) -> int | str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    return int(text) if text.isdigit() else text


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_SECRET_KEY_MARKERS = {
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "private_key",
    "access_key",
}
_KEY_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:(?:[A-Za-z]:[\\/])|(?:\\\\)|/)[^\"'<>;\r\n]*?"
    r"\.(?:db|sqlite3?|json|duckdb)(?=$|[\s,;\"'<>])",
    re.IGNORECASE,
)
_SECRET_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])")


def _is_secret_key(key: str) -> bool:
    normalized = _KEY_SEPARATOR_RE.sub("_", key.casefold()).strip("_")
    return any(marker in normalized for marker in _SECRET_KEY_MARKERS)


def _is_absolute_path(value: str) -> bool:
    return bool(re.match(r"^(?:[a-zA-Z]:[\\/]|\\\\|/)", value))


def _redact_string(value: str) -> str:
    if _is_absolute_path(value):
        return "[REDACTED_PATH]"
    redacted = _ABSOLUTE_PATH_RE.sub("[REDACTED_PATH]", value)
    return _SECRET_TOKEN_RE.sub("[REDACTED_SECRET]", redacted)


def _json_safe(value: Any, *, key: str | None = None) -> Any:  # noqa: C901
    if key is not None and _is_secret_key(key):
        return "[REDACTED]"
    if value is None or isinstance(value, (str, int, bool)):
        if isinstance(value, str):
            return _redact_string(value)
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return "[REDACTED_PATH]" if value.is_absolute() else str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value, key=key)
    if isinstance(value, Mapping):
        return {str(map_key): _json_safe(child, key=str(map_key)) for map_key, child in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(child) for child in value]
    if is_dataclass(value):
        return {field.name: _json_safe(getattr(value, field.name), key=field.name) for field in fields(value)}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_safe(model_dump(mode="json"), key=key)
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value), key=key)
    return str(value)


def _query_failed(message: str, cause: Exception, *, stage: str) -> QueryExecutionError:
    return QueryExecutionError(
        "QUERY_FAILED",
        message,
        retryable=True,
        details={"stage": stage, "cause": str(cause)},
    )


__all__ = [
    "EngineQueryRuntimeFactory",
    "NormalizedQueryResult",
    "QueryExecutionError",
    "QueryRuntime",
    "QueryRuntimeFactory",
    "QueryService",
    "QueryWorkspaceRegistry",
    "encode_sse",
    "uuid4_string",
]
