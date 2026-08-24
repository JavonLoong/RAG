"""Integration tests for the deterministic versioned query stream."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, PACKAGE_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc import query_service as query_service_module  # noqa: E402
from chroma_rag_poc.api import create_app  # noqa: E402
from chroma_rag_poc.query_service import (  # noqa: E402
    QueryExecutionError,
    QueryRuntime,
    QueryService,
)
from chroma_rag_poc.routes_query_v1 import get_query_service  # noqa: E402

from core_domain.query_contracts import (  # noqa: E402
    AnswerPayload,
    Citation,
    CitationEvent,
    CitationType,
    ErrorDetail,
    ErrorEvent,
    FinalEvent,
    MetaEvent,
    ModeDecision,
    QueryMode,
    QueryRequest,
    QueryResponse,
    QueryStatus,
    QueryStreamEvent,
    RetrievalSummary,
    UsageMetrics,
)


class FakeRetriever:
    def retrieve(self, _query: str, *, top_k: int) -> list[dict[str, Any]]:
        return [
            {
                "id": "T1",
                "text": "Compressor fouling is caused by deposits.",
                "source": "manual.pdf",
                "page": 3,
                "chunk_id": "chunk-1",
            },
        ][:top_k]


class FakeRegistry:
    def get(self, _workspace_id: str) -> Any:
        return SimpleNamespace()


class FakeRuntimeFactory:
    def create(self, _workspace: Any) -> QueryRuntime:
        return QueryRuntime(
            text_retriever=FakeRetriever(),
            graph_retriever=None,
            global_searcher=None,
            query_router=None,
            reranker=None,
            hallucination_guard=None,
            llm=None,
        )


class FakeStreamService:
    def __init__(self, stream_factory: Callable[[Any], Iterator[QueryStreamEvent]]) -> None:
        self.stream_factory = stream_factory
        self.requests: list[Any] = []

    def stream(self, payload: Any) -> Iterator[QueryStreamEvent]:
        self.requests.append(payload)
        return self.stream_factory(payload)


class SecretStreamFailure(RuntimeError):
    def __str__(self) -> str:
        return "secret path C:\\private\\graph.sqlite3"


def _mode() -> ModeDecision:
    return ModeDecision(requested=QueryMode.LOCAL, used=QueryMode.LOCAL, reason="test mode")


def _response() -> QueryResponse:
    return QueryResponse(
        request_id="req-1",
        trace_id="trace-1",
        status=QueryStatus.OK,
        mode=_mode(),
        answer=AnswerPayload(text="Compressor fouling is caused by deposits.", finish_reason="stop"),
        citations=[Citation(id="T1", type=CitationType.TEXT, quote="Deposits cause fouling.")],
        retrieval=RetrievalSummary(text_hits=1),
        usage=UsageMetrics(latency_ms=1.0),
    )


def _parse_sse(body: str) -> list[QueryStreamEvent]:
    parsed: list[QueryStreamEvent] = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        event_name = lines[0].removeprefix("event: ")
        payload = json.loads(lines[1].removeprefix("data: "))
        event: QueryStreamEvent = TypeAdapter(QueryStreamEvent).validate_python(payload)
        assert event.event == event_name
        parsed.append(event)
    return parsed


@pytest.fixture
def app(tmp_path: Path) -> Iterator[FastAPI]:
    application = create_app(
        persist_dir=tmp_path / "persist",
        upload_dir=tmp_path / "uploads",
        log_dir=tmp_path / "logs",
    )
    yield application
    application.dependency_overrides.clear()


def _client(application: Any, service: FakeStreamService) -> TestClient:
    application.dependency_overrides[get_query_service] = lambda: service
    return TestClient(application)


def test_encode_sse_uses_event_line_typed_json_and_blank_frame() -> None:
    event = ErrorEvent(
        request_id="req-1",
        sequence=2,
        error=ErrorDetail(code="STREAM_FAILED", message="stream generation failed", retryable=True),
    )

    encoded = query_service_module.encode_sse(event)

    assert encoded == (
        b'event: error\n'
        b'data: {"event":"error","request_id":"req-1","sequence":2,'
        b'"error":{"code":"STREAM_FAILED","message":"stream generation failed",'
        b'"retryable":true,"details":{}}}\n\n'
    )
    assert "ErrorDetail(" not in encoded.decode()


def test_query_service_stream_orders_sync_events_without_fake_deltas() -> None:
    service = QueryService(
        FakeRegistry(),
        FakeRuntimeFactory(),
        id_factory=iter(("req-1", "trace-1")).__next__,
        clock=iter((10.0, 10.001)).__next__,
    )
    request = {
        "query": "What causes compressor fouling?",
        "workspace_id": "power-equipment",
        "mode": "vector",
    }

    events = list(service.stream(QueryRequest.model_validate(request)))

    assert [event.event for event in events] == ["meta", "citation", "final"]
    assert [event.sequence for event in events] == [1, 2, 3]
    assert isinstance(events[0], MetaEvent)
    assert events[0].token_streaming is False
    assert isinstance(events[1], CitationEvent)
    assert isinstance(events[2], FinalEvent)
    assert events[2].response.model_validate(events[2].response.model_dump())


def test_stream_endpoint_returns_typed_events_in_contract_order(app: Any) -> None:
    response = _response()

    def stream(_payload: Any) -> Iterator[QueryStreamEvent]:
        yield MetaEvent(request_id="req-1", sequence=1, mode=response.mode, token_streaming=False)
        yield CitationEvent(request_id="req-1", sequence=2, citation=response.citations[0])
        yield FinalEvent(request_id="req-1", sequence=3, response=response)

    with _client(app, FakeStreamService(stream)) as client:
        result = client.post(
            "/api/v1/query/stream",
            json={"query": "What causes compressor fouling?", "workspace_id": "power-equipment"},
        )

    events = _parse_sse(result.text)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-cache"
    assert result.headers["x-accel-buffering"] == "no"
    assert [event.event for event in events] == ["meta", "citation", "final"]


def test_evidence_only_stream_orders_citations_before_final_without_delta(app: Any) -> None:
    response = QueryResponse(
        request_id="req-1",
        trace_id="trace-1",
        status=QueryStatus.OK,
        mode=_mode(),
        answer=AnswerPayload(text="", finish_reason="stop"),
        citations=[
            Citation(id="T1", type=CitationType.TEXT, quote="Fuel pressure is monitored."),
            Citation(id="G1", type=CitationType.GRAPH, quote="Fuel pressure relates to combustion stability."),
        ],
        retrieval=RetrievalSummary(text_hits=1),
        usage=UsageMetrics(latency_ms=1.0),
    )

    def stream(_payload: Any) -> Iterator[QueryStreamEvent]:
        yield MetaEvent(request_id="req-1", sequence=1, mode=response.mode, token_streaming=False)
        yield CitationEvent(request_id="req-1", sequence=2, citation=response.citations[0])
        yield CitationEvent(request_id="req-1", sequence=3, citation=response.citations[1])
        yield FinalEvent(request_id="req-1", sequence=4, response=response)

    service = FakeStreamService(stream)
    with _client(app, service) as client:
        result = client.post(
            "/api/v1/query/stream",
            json={
                "query": "fuel pressure",
                "workspace_id": "power-equipment",
                "mode": "auto",
                "evidence_only": True,
                "evidence_profile": "combined",
            },
        )

    events = _parse_sse(result.text)
    assert result.status_code == 200
    assert service.requests[0].evidence_only is True
    assert [event.event for event in events] == ["meta", "citation", "citation", "final"]
    assert not any(event.event == "delta" for event in events)
    assert isinstance(events[-1], FinalEvent)
    assert events[-1].response.answer.text == ""


def test_stream_error_before_meta_uses_v1_http_error_envelope(app: Any) -> None:
    def stream(_payload: Any) -> Iterator[QueryStreamEvent]:
        raise QueryExecutionError(
            "LLM_UNAVAILABLE",
            "internal adapter secret",
            retryable=False,
            details={"cause": "internal adapter secret"},
        )
        yield  # pragma: no cover

    with _client(app, FakeStreamService(stream)) as client:
        response = client.post(
            "/api/v1/query/stream",
            json={"query": "question", "workspace_id": "power-equipment"},
        )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "LLM_UNAVAILABLE",
        "message": "The language model service is unavailable.",
        "retryable": True,
        "details": {},
    }
    assert "internal adapter secret" not in response.text


def test_stream_error_after_meta_emits_one_redacted_error_and_closes(app: Any) -> None:
    response = _response()

    def stream(_payload: Any) -> Iterator[QueryStreamEvent]:
        yield MetaEvent(request_id="req-1", sequence=1, mode=response.mode, token_streaming=True)
        raise SecretStreamFailure

    with _client(app, FakeStreamService(stream)) as client:
        result = client.post(
            "/api/v1/query/stream",
            json={"query": "question", "workspace_id": "power-equipment"},
        )

    events = _parse_sse(result.text)
    assert result.status_code == 200
    assert [event.event for event in events] == ["meta", "error"]
    assert isinstance(events[1], ErrorEvent)
    assert events[1].request_id == "req-1"
    assert events[1].sequence == 2
    assert events[1].error.model_dump() == {
        "code": "STREAM_FAILED",
        "message": "stream generation failed",
        "retryable": True,
        "details": {},
    }
    assert "secret path" not in result.text
    assert "final" not in result.text


def test_stream_validation_uses_v1_error_envelope(app: Any) -> None:
    service = FakeStreamService(lambda _payload: iter(()))
    with _client(app, service) as client:
        response = client.post(
            "/api/v1/query/stream",
            json={"query": "   ", "workspace_id": "power-equipment"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "detail" not in response.json()
