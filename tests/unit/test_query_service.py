"""Focused behavioral tests for the unified GraphRAG query service."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, PACKAGE_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc.engine_bridge import (  # noqa: E402
    get_graphrag_orchestrator,
    get_hybrid_retriever,
)
from chroma_rag_poc.query_service import (  # noqa: E402
    QueryExecutionError,
    QueryRuntime,
    QueryService,
)

from core_domain.query_contracts import (  # noqa: E402
    CitationType,
    QueryMode,
    QueryRequest,
    QueryStatus,
)
from retrieval_engine.core import DocumentChunk, RetrievalResult  # noqa: E402


@dataclass
class FakeWorkspace:
    workspace_id: str = "power-equipment"


class RecordingRetriever:
    def __init__(self, results: list[Any] | None = None, *, error: Exception | None = None) -> None:
        self.results = results or []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int = 5) -> list[Any]:
        self.calls.append((query, top_k))
        if self.error:
            raise self.error
        return self.results


class RecordingGlobalSearcher:
    def __init__(self, result: Any, *, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, bool]] = []

    def search(self, question: str, *, context_only: bool = False) -> Any:
        self.calls.append((question, context_only))
        if self.error:
            raise self.error
        return self.result


class RecordingRouter:
    def __init__(self, strategy: str = "LOCAL_SEARCH") -> None:
        self.strategy = strategy
        self.calls: list[str] = []

    def route_query(self, question: str) -> Any:
        self.calls.append(question)
        return type("Route", (), {"strategy": self.strategy, "reason": "fake route"})()


class RecordingLLM:
    def __init__(self, answer: str = "generated answer [T1]") -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def generate(self, prompt: str, **_: Any) -> str:
        self.prompts.append(prompt)
        return self.answer


class FakeRegistry:
    def __init__(self, workspace: FakeWorkspace | None = None) -> None:
        self.workspace = workspace or FakeWorkspace()
        self.calls: list[str] = []

    def get(self, workspace_id: str) -> FakeWorkspace:
        self.calls.append(workspace_id)
        return self.workspace


class FakeRuntimeFactory:
    def __init__(self, runtime: QueryRuntime) -> None:
        self.runtime = runtime
        self.calls: list[FakeWorkspace] = []

    def create(self, workspace: FakeWorkspace) -> QueryRuntime:
        self.calls.append(workspace)
        return self.runtime


def _text_result(
    text: str = "text evidence",
    *,
    source: str | None = "manual.pdf",
    page: int | str | None = 12,
    chunk_id: str | None = "chunk-1",
    score: float | None = 0.91,
) -> RetrievalResult:
    return RetrievalResult(
        chunk=DocumentChunk(text=text, source=source, page=page, chunk_id=chunk_id),
        score=score,  # type: ignore[arg-type]
        retriever_name="fake-text",
    )


def _graph_result() -> dict[str, Any]:
    return {
        "subject": "燃空比波动",
        "predicate": "CAUSES",
        "object": "燃烧不稳定",
        "evidence": "燃空比波动会导致燃烧不稳定。",
        "confidence": 0.88,
        "source": "graph-evidence.pdf",
    }


def _global_result() -> Any:
    return type(
        "GlobalResult",
        (),
        {
            "answer": "community synthesis",
            "communities_searched": 3,
            "communities_relevant": 1,
            "partial_answers": [
                {
                    "community_id": "C7",
                    "title": "燃烧系统",
                    "entity_count": 4,
                    "answer": "燃空比波动与燃烧不稳定相关。",
                }
            ],
        },
    )()


def _service(
    *,
    text: RecordingRetriever | None = None,
    graph: RecordingRetriever | None = None,
    global_searcher: RecordingGlobalSearcher | None = None,
    router: RecordingRouter | None = None,
    llm: RecordingLLM | None = None,
    include_context: bool = False,
    include_debug: bool = False,
) -> tuple[QueryService, FakeRegistry, FakeRuntimeFactory, dict[str, Any]]:
    components: dict[str, Any] = {
        "text": text or RecordingRetriever([_text_result()]),
        "graph": graph or RecordingRetriever([_graph_result()]),
        "global": global_searcher or RecordingGlobalSearcher(_global_result()),
        "router": router,
        "llm": llm or RecordingLLM(),
    }
    runtime = QueryRuntime(
        text_retriever=components["text"],
        graph_retriever=components["graph"],
        global_searcher=components["global"],
        query_router=components["router"],
        reranker=None,
        hallucination_guard=None,
        llm=components["llm"],
    )
    registry = FakeRegistry()
    factory = FakeRuntimeFactory(runtime)
    service = QueryService(
        registry,
        factory,
        id_factory=iter(("request-1", "trace-1")).__next__,
        clock=iter((10.0, 10.025)).__next__,
    )
    request = QueryRequest(
        query="燃空比波动的影响?",
        workspace_id="power-equipment",
        mode=QueryMode.LOCAL,
        top_k=3,
        include_context=include_context,
        include_debug=include_debug,
    )
    return service, registry, factory, {"request": request, **components}


@pytest.mark.parametrize(
    ("mode", "expected_used", "selected"),
    [
        (QueryMode.VECTOR, QueryMode.VECTOR, {"text"}),
        (QueryMode.LOCAL, QueryMode.LOCAL, {"text", "graph", "llm"}),
        (QueryMode.GLOBAL, QueryMode.GLOBAL, {"global"}),
        (QueryMode.HYBRID, QueryMode.HYBRID, {"text", "graph", "global", "llm"}),
    ],
)
def test_explicit_mode_calls_only_selected_runtime_components(
    mode: QueryMode,
    expected_used: QueryMode,
    selected: set[str],
) -> None:
    service, _, _, components = _service()
    request = components["request"].model_copy(update={"mode": mode})

    response = service.query(request)

    assert response.mode.used is expected_used
    assert bool(components["text"].calls) is ("text" in selected)
    assert bool(components["graph"].calls) is ("graph" in selected)
    assert bool(components["global"].calls) is ("global" in selected)
    assert bool(components["llm"].prompts) is ("llm" in selected)
    assert components["router"] is None


@pytest.mark.parametrize(
    ("strategy", "expected_used", "selected"),
    [
        ("VECTOR_ONLY", QueryMode.VECTOR, {"text"}),
        ("LOCAL_SEARCH", QueryMode.LOCAL, {"text", "graph", "llm"}),
        ("GLOBAL_SEARCH", QueryMode.GLOBAL, {"global"}),
    ],
)
def test_auto_routes_then_calls_only_selected_path(
    strategy: str,
    expected_used: QueryMode,
    selected: set[str],
) -> None:
    router = RecordingRouter(strategy)
    service, _, _, components = _service(router=router)
    request = components["request"].model_copy(update={"mode": QueryMode.AUTO})

    response = service.query(request)

    assert response.mode.used is expected_used
    assert router.calls == [request.query]
    assert bool(components["text"].calls) is ("text" in selected)
    assert bool(components["graph"].calls) is ("graph" in selected)
    assert bool(components["global"].calls) is ("global" in selected)
    assert bool(components["llm"].prompts) is ("llm" in selected)


def test_normalizes_text_graph_and_global_evidence_to_v1_citations() -> None:
    text = RecordingRetriever([_text_result()])
    graph = RecordingRetriever([_graph_result()])
    global_searcher = RecordingGlobalSearcher(_global_result())
    service, _, _, components = _service(text=text, graph=graph, global_searcher=global_searcher)
    request = components["request"].model_copy(update={"mode": QueryMode.HYBRID})

    response = service.query(request)

    assert [citation.type for citation in response.citations] == [
        CitationType.TEXT,
        CitationType.GRAPH,
        CitationType.COMMUNITY,
    ]
    graph_citation = response.citations[1]
    assert graph_citation.triple is not None
    assert graph_citation.triple.model_dump() == {
        "subject": "燃空比波动",
        "predicate": "CAUSES",
        "object": "燃烧不稳定",
    }
    community_citation = response.citations[2]
    assert community_citation.quote == "燃空比波动与燃烧不稳定相关。"
    assert community_citation.metadata["community_id"] == "C7"
    assert response.retrieval.text_hits == 1
    assert response.retrieval.graph_hits == 1
    assert response.retrieval.community_hits == 1
    assert response.retrieval.communities_searched == 3
    assert global_searcher.calls == [(request.query, True)]


def test_global_mode_requests_final_global_answer_without_other_paths() -> None:
    global_searcher = RecordingGlobalSearcher(_global_result())
    service, _, _, components = _service(global_searcher=global_searcher)
    request = components["request"].model_copy(update={"mode": QueryMode.GLOBAL})

    response = service.query(request)

    assert response.answer.text == "community synthesis"
    assert global_searcher.calls == [(request.query, False)]
    assert not components["text"].calls
    assert not components["graph"].calls
    assert not components["llm"].prompts


def test_missing_text_citation_fields_remain_null() -> None:
    text = RecordingRetriever([_text_result(source=None, page=None, chunk_id=None, score=None)])
    service, _, _, components = _service(text=text)
    request = components["request"].model_copy(update={"mode": QueryMode.VECTOR})

    citation = service.query(request).citations[0]

    assert citation.source is not None
    assert citation.source.file is None
    assert citation.source.page is None
    assert citation.source.chunk_id is None
    assert citation.score is None
    assert citation.source.page != -1
    assert citation.source.chunk_id != ""


def test_graph_failure_returns_partial_when_text_and_answer_are_available() -> None:
    graph = RecordingRetriever(error=RuntimeError("graph unavailable"))
    service, _, _, components = _service(graph=graph)
    request = components["request"].model_copy(update={"mode": QueryMode.LOCAL})

    response = service.query(request)

    assert response.status is QueryStatus.PARTIAL
    assert response.warnings[0].code == "GRAPH_RETRIEVAL_DEGRADED"
    assert response.answer.text == "generated answer [T1]"


def test_all_selected_paths_failing_raise_stable_query_execution_error() -> None:
    text = RecordingRetriever(error=RuntimeError("text unavailable"))
    graph = RecordingRetriever(error=RuntimeError("graph unavailable"))
    llm = RecordingLLM()
    llm.generate = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("llm unavailable"))  # type: ignore[method-assign]
    service, _, _, components = _service(text=text, graph=graph, llm=llm)
    request = components["request"].model_copy(update={"mode": QueryMode.LOCAL})

    with pytest.raises(QueryExecutionError) as error:
        service.query(request)

    assert error.value.code == "QUERY_FAILED"
    assert error.value.retryable is True


def test_context_and_debug_are_gated_and_debug_is_json_safe_and_redacted() -> None:
    text = RecordingRetriever([_text_result(source=r"C:\absolute\runtime\graph.sqlite3")])
    text.results[0].chunk.metadata.update({
        "api_key": "sk-secret-value",
        "nested": {"graph_db_path": r"C:\absolute\runtime\graph.sqlite3"},
        "path": Path(r"C:\absolute\runtime\file.json"),
    })
    service, _, _, components = _service(text=text, include_context=True, include_debug=True)
    request = components["request"].model_copy(update={"mode": QueryMode.LOCAL})

    response = service.query(request)

    assert response.context is not None
    assert response.context.items
    assert response.debug is not None
    debug_text = str(response.debug.model_dump(mode="json"))
    assert "sk-secret-value" not in debug_text
    assert r"C:\absolute\runtime\graph.sqlite3" not in debug_text
    assert r"C:\absolute\runtime\file.json" not in debug_text
    assert response.debug.prompt is not None
    assert r"C:\absolute\runtime\graph.sqlite3" not in response.debug.prompt


def test_context_and_debug_are_omitted_when_not_requested() -> None:
    service, _, _, components = _service()

    response = service.query(components["request"])

    assert response.context is None
    assert response.debug is None


def test_engine_bridge_forwards_reranker_and_orchestrator_dependencies() -> None:
    retriever_a = object()
    retriever_b = object()
    reranker = object()

    hybrid = get_hybrid_retriever([retriever_a, retriever_b], reranker=reranker)
    orchestrator = get_graphrag_orchestrator(
        text_retriever=retriever_a,
        graph_retriever=retriever_b,
        query_router="router",
        hallucination_guard="guard",
        llm="llm",
    )

    assert hybrid.reranker is reranker
    assert orchestrator.query_router == "router"
    assert orchestrator.hallucination_guard == "guard"
    assert orchestrator.llm == "llm"
