"""Focused behavioral tests for the unified GraphRAG query service."""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, PACKAGE_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc import engine_bridge  # noqa: E402
from chroma_rag_poc.engine_bridge import (  # noqa: E402
    get_graphrag_orchestrator,
    get_hybrid_retriever,
)
from chroma_rag_poc.query_service import (  # noqa: E402
    EngineQueryRuntimeFactory,
    QueryExecutionError,
    QueryRuntime,
    QueryService,
)

from core_domain.query_contracts import (  # noqa: E402
    CitationType,
    EvidenceSelectionProfile,
    QueryMode,
    QueryRequest,
    QueryStatus,
)

_retrieval_core = import_module("retrieval_engine.core")
DocumentChunk: Any = _retrieval_core.DocumentChunk
RetrievalResult: Any = _retrieval_core.RetrievalResult


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


class RecordingReranker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], int | None]] = []

    def rerank(self, query: str, documents: list[str], *, top_k: int | None = None) -> list[tuple[int, float]]:
        self.calls.append((query, documents, top_k))
        return [(index, 0.99 - index * 0.01) for index in range(len(documents))]


class RecordingGuard:
    def __init__(self, *, is_safe: bool = True) -> None:
        self.is_safe = is_safe
        self.calls: list[tuple[str, str]] = []

    def verify(self, answer: str, context: str) -> Any:
        self.calls.append((answer, context))
        return SimpleNamespace(
            is_safe=self.is_safe,
            hallucinated_claims=["unsupported claim"] if not self.is_safe else [],
        )


class FakeRegistry:
    def __init__(self, workspace: Any | None = None) -> None:
        self.workspace = workspace or FakeWorkspace()
        self.calls: list[str] = []

    def get(self, workspace_id: str) -> Any:
        self.calls.append(workspace_id)
        return self.workspace


class FakeRuntimeFactory:
    def __init__(self, runtime: QueryRuntime) -> None:
        self.runtime = runtime
        self.calls: list[FakeWorkspace] = []

    def create(self, workspace: FakeWorkspace) -> QueryRuntime:
        self.calls.append(workspace)
        return self.runtime


class FailingRuntimeFactory:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def create(self, workspace: FakeWorkspace) -> QueryRuntime:
        raise self.error


def _text_result(
    text: str = "text evidence",
    *,
    source: str | None = "manual.pdf",
    page: int | str | None = 12,
    chunk_id: str | None = "chunk-1",
    score: float | None = 0.91,
) -> Any:
    return RetrievalResult(
        chunk=DocumentChunk(text=text, source=source, page=page, chunk_id=chunk_id),
        score=score,
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
    reranker: RecordingReranker | None = None,
    guard: RecordingGuard | None = None,
    include_context: bool = False,
    include_debug: bool = False,
) -> tuple[QueryService, FakeRegistry, FakeRuntimeFactory, dict[str, Any]]:
    components: dict[str, Any] = {
        "text": text or RecordingRetriever([_text_result()]),
        "graph": graph or RecordingRetriever([_graph_result()]),
        "global": global_searcher or RecordingGlobalSearcher(_global_result()),
        "router": router,
        "llm": llm or RecordingLLM(),
        "reranker": reranker,
        "guard": guard,
    }
    runtime = QueryRuntime(
        text_retriever=components["text"],
        graph_retriever=components["graph"],
        global_searcher=components["global"],
        query_router=components["router"],
        reranker=components["reranker"],
        hallucination_guard=components["guard"],
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


@pytest.mark.parametrize(
    ("profile", "selected"),
    [
        (EvidenceSelectionProfile.RAG_ONLY, {"text"}),
        (EvidenceSelectionProfile.GRAPHRAG_LOCAL_ONLY, {"graph"}),
        (EvidenceSelectionProfile.GRAPHRAG_GLOBAL_ONLY, {"global"}),
        (EvidenceSelectionProfile.GRAPHRAG_ONLY, {"graph", "global"}),
        (EvidenceSelectionProfile.COMBINED, {"text", "graph", "global"}),
    ],
)
def test_evidence_profile_calls_only_selected_components(profile, selected) -> None:
    service, _, _, components = _service()
    request = components["request"].model_copy(
        update={
            "mode": QueryMode.AUTO,
            "evidence_only": True,
            "evidence_profile": profile,
            "include_context": True,
        }
    )

    response = service.query(request)

    assert response.mode.requested is QueryMode.AUTO
    assert response.mode.used is QueryMode.AUTO
    assert bool(components["text"].calls) is ("text" in selected)
    assert bool(components["graph"].calls) is ("graph" in selected)
    assert bool(components["global"].calls) is ("global" in selected)
    assert components["llm"].prompts == []
    assert response.answer.text == ""
    assert response.answer.finish_reason == "stop"
    assert response.context is not None
    if "global" in selected:
        assert components["global"].calls == [(request.query, True)]


def test_custom_evidence_types_call_only_requested_sources() -> None:
    service, _, _, components = _service()
    request = components["request"].model_copy(
        update={
            "mode": QueryMode.AUTO,
            "evidence_only": True,
            "evidence_profile": EvidenceSelectionProfile.CUSTOM,
            "evidence_types": (CitationType.COMMUNITY, CitationType.TEXT),
        }
    )
    response = service.query(request)
    assert components["text"].calls
    assert not components["graph"].calls
    assert components["global"].calls
    assert [item.type for item in response.citations] == [CitationType.TEXT, CitationType.COMMUNITY]


def test_auto_evidence_profile_uses_every_configured_source_without_final_llm() -> None:
    service, _, _, components = _service()
    request = components["request"].model_copy(
        update={"mode": QueryMode.AUTO, "evidence_only": True}
    )
    response = service.query(request)
    assert components["text"].calls
    assert components["graph"].calls
    assert components["global"].calls
    assert components["llm"].prompts == []
    assert {item.type for item in response.citations} == {
        CitationType.TEXT,
        CitationType.GRAPH,
        CitationType.COMMUNITY,
    }
    assert components["router"] is None


def test_auto_evidence_profile_warns_for_missing_graph_and_global_sources() -> None:
    router = RecordingRouter()
    service, _, factory, components = _service(router=router)
    factory.runtime = replace(factory.runtime, graph_retriever=None, global_searcher=None)
    request = components["request"].model_copy(
        update={"mode": QueryMode.AUTO, "evidence_only": True}
    )

    response = service.query(request)

    assert components["text"].calls
    assert components["llm"].prompts == []
    assert router.calls == []
    assert [item.type for item in response.citations] == [CitationType.TEXT]
    assert response.status is QueryStatus.PARTIAL
    assert response.mode.used is QueryMode.AUTO
    assert response.mode.reason == "evidence profile auto selected sources"
    assert {item.code for item in response.warnings} == {
        "GRAPH_RETRIEVAL_DEGRADED",
        "GLOBAL_SEARCH_DEGRADED",
    }


def test_stream_auto_evidence_profile_preserves_partial_missing_source_response() -> None:
    service, _, factory, components = _service()
    factory.runtime = replace(factory.runtime, graph_retriever=None, global_searcher=None)
    request = components["request"].model_copy(
        update={"mode": QueryMode.AUTO, "evidence_only": True}
    )

    events = list(service.stream(request))

    assert [event.event for event in events] == ["meta", "citation", "final"]
    assert not any(event.event == "delta" for event in events)
    final_response = events[-1].response
    assert final_response.mode.used is QueryMode.AUTO
    assert final_response.status is QueryStatus.PARTIAL
    assert {item.code for item in final_response.warnings} == {
        "GRAPH_RETRIEVAL_DEGRADED",
        "GLOBAL_SEARCH_DEGRADED",
    }


def test_explicit_rag_only_failure_does_not_fall_back_to_graph() -> None:
    text = RecordingRetriever(error=RuntimeError("text unavailable"))
    service, _, _, components = _service(text=text)
    request = components["request"].model_copy(
        update={
            "mode": QueryMode.AUTO,
            "evidence_only": True,
            "evidence_profile": EvidenceSelectionProfile.RAG_ONLY,
        }
    )
    response = service.query(request)
    assert not components["graph"].calls
    assert not components["global"].calls
    assert response.citations == []
    assert any(item.code == "TEXT_RETRIEVAL_DEGRADED" for item in response.warnings)


def test_evidence_only_bypasses_router_and_identifies_profile_reason() -> None:
    router = RecordingRouter("LOCAL_SEARCH")
    service, _, _, components = _service(router=router)
    request = components["request"].model_copy(
        update={
            "mode": QueryMode.AUTO,
            "evidence_only": True,
            "evidence_profile": EvidenceSelectionProfile.RAG_ONLY,
        }
    )

    response = service.query(request)

    assert router.calls == []
    assert response.mode.reason == "evidence profile rag_only selected sources"


def test_graph_evidence_failure_is_partial_without_unselected_sources_or_llm() -> None:
    graph = RecordingRetriever(error=RuntimeError("graph unavailable"))
    service, _, _, components = _service(graph=graph)
    request = components["request"].model_copy(
        update={
            "mode": QueryMode.AUTO,
            "evidence_only": True,
            "evidence_profile": EvidenceSelectionProfile.GRAPHRAG_LOCAL_ONLY,
        }
    )

    response = service.query(request)

    assert response.status is QueryStatus.PARTIAL
    assert any(item.code == "GRAPH_RETRIEVAL_DEGRADED" for item in response.warnings)
    assert not components["text"].calls
    assert not components["global"].calls
    assert components["llm"].prompts == []


def test_global_evidence_failure_is_partial_without_unselected_sources_or_llm() -> None:
    global_searcher = RecordingGlobalSearcher(
        _global_result(),
        error=RuntimeError("global search unavailable"),
    )
    service, _, _, components = _service(global_searcher=global_searcher)
    request = components["request"].model_copy(
        update={
            "mode": QueryMode.AUTO,
            "evidence_only": True,
            "evidence_profile": EvidenceSelectionProfile.GRAPHRAG_GLOBAL_ONLY,
        }
    )

    response = service.query(request)

    assert response.status is QueryStatus.PARTIAL
    assert any(item.code == "GLOBAL_SEARCH_DEGRADED" for item in response.warnings)
    assert global_searcher.calls == [(request.query, True)]
    assert not components["text"].calls
    assert not components["graph"].calls
    assert components["llm"].prompts == []


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


def test_supplied_reranker_and_guard_are_executed_and_guard_changes_response() -> None:
    reranker = RecordingReranker()
    guard = RecordingGuard(is_safe=False)
    service, _, _, components = _service(reranker=reranker, guard=guard)
    request = components["request"].model_copy(update={"mode": QueryMode.LOCAL})

    response = service.query(request)

    assert reranker.calls == [(request.query, ["text evidence"], request.top_k)]
    assert guard.calls and guard.calls[0][0] == "generated answer [T1]"
    assert response.retrieval.reranked is True
    assert response.status is QueryStatus.PARTIAL
    assert response.warnings[-1].code == "HALLUCINATION_GUARD_FLAGGED"
    assert "unsupported claim" in response.answer.text


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


def test_unknown_runtime_factory_failure_is_wrapped_as_query_failed() -> None:
    service = QueryService(
        FakeRegistry(),
        FailingRuntimeFactory(RuntimeError("runtime construction failed")),
        id_factory=iter(("request-1", "trace-1")).__next__,
        clock=iter((10.0, 10.025)).__next__,
    )

    with pytest.raises(QueryExecutionError) as error:
        service.query(QueryRequest(query="question", workspace_id="power-equipment", mode=QueryMode.VECTOR))

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


def test_partial_warning_does_not_expose_runtime_details() -> None:
    sensitive_error = RuntimeError(
        "api_key=sk-secret-value; path=C:\\private\\rag\\index; "
        "Traceback (most recent call last)"
    )
    service, _, _, components = _service(
        text=RecordingRetriever(error=sensitive_error),
        include_debug=True,
    )

    response = service.query(components["request"])

    assert response.status is QueryStatus.PARTIAL
    assert response.warnings[0].code == "TEXT_RETRIEVAL_DEGRADED"
    response_text = response.model_dump_json()
    for marker in ("sk-", "api_key", "Authorization", "C:\\", "/home/", "Traceback (most recent call last)"):
        assert marker not in response_text


def test_debug_redacts_unkeyed_sk_values_but_preserves_ordinary_text() -> None:
    text = RecordingRetriever([_text_result()])
    text.results[0].chunk.metadata.update({
        "ordinary_note": "ordinary debug context",
        "note": "unkeyed sk-live-secret-value-123456",
    })
    service, _, _, components = _service(text=text, include_debug=True)

    response = service.query(components["request"])

    assert response.debug is not None
    debug_text = str(response.debug.model_dump(mode="json"))
    assert "sk-live-secret-value-123456" not in debug_text
    assert "ordinary debug context" in debug_text


def test_debug_redacts_spaced_windows_and_unc_database_paths() -> None:
    text = RecordingRetriever([_text_result()])
    text.results[0].chunk.metadata.update({
        "ordinary_note": "ordinary debug context",
        "windows_path": r"database at C:\Program Files\RAG Data\graph database.sqlite3",
        "unc_path": r"database at \\server\Shared Folder\graph database.sqlite3",
    })
    service, _, _, components = _service(text=text, include_debug=True)

    response = service.query(components["request"])

    assert response.debug is not None
    debug_text = str(response.debug.model_dump(mode="json"))
    assert r"C:\Program Files\RAG Data\graph database.sqlite3" not in debug_text
    assert r"\\server\Shared Folder\graph database.sqlite3" not in debug_text
    assert "Program Files" not in debug_text
    assert "RAG Data\\graph database.sqlite3" not in debug_text
    assert "server\\Shared Folder" not in debug_text
    assert "graph database.sqlite3" not in debug_text
    assert "ordinary debug context" in debug_text


def test_vector_query_does_not_initialize_graph_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    text_retriever = RecordingRetriever([_text_result()])
    chroma_path = tmp_path / "chroma"
    chroma_path.mkdir()
    monkeypatch.setattr(engine_bridge, "get_chroma_retriever", lambda *_args, **_kwargs: text_retriever)
    monkeypatch.setattr(
        engine_bridge,
        "get_graph_store",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("graph store must stay lazy")),
    )
    from chroma_rag_poc.workspace_registry import WorkspaceConfig

    workspace = WorkspaceConfig(
        workspace_id="power-equipment",
        chroma_persist_dir=chroma_path,
        chroma_collection="power_equipment",
        graph_db_path=tmp_path / "graph" / "graph.sqlite3",
        supported_modes=frozenset({QueryMode.VECTOR}),
        default_mode=QueryMode.VECTOR,
    )
    service = QueryService(
        FakeRegistry(workspace),
        EngineQueryRuntimeFactory(),
        id_factory=iter(("request-1", "trace-1")).__next__,
        clock=iter((10.0, 10.025)).__next__,
    )

    response = service.query(
        QueryRequest(query="vector question", workspace_id="power-equipment", mode=QueryMode.VECTOR)
    )

    assert response.mode.used is QueryMode.VECTOR
    assert response.answer.text == "text evidence"


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
