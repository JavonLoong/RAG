"""Behavioral tests for the public GraphRAG query v1 contracts."""

from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from core_domain.query_contracts import (
    AnswerPayload,
    Citation,
    CitationEvent,
    CitationType,
    ContextItem,
    ContextPayload,
    DebugPayload,
    DeltaEvent,
    ErrorDetail,
    ErrorEvent,
    EvidenceSelectionProfile,
    FinalEvent,
    GraphTriple,
    MetaEvent,
    ModeDecision,
    QueryErrorResponse,
    QueryMode,
    QueryRequest,
    QueryResponse,
    QueryStatus,
    QueryStreamEvent,
    RetrievalSummary,
    SourceRef,
    UsageMetrics,
    WarningItem,
    selected_citation_types,
)


def _response_payload() -> dict[str, Any]:
    return {
        "request_id": "req-1",
        "trace_id": "trace-1",
        "status": "ok",
        "mode": {"requested": "auto", "used": "local", "reason": "entity relation question"},
        "answer": {"text": "answer [T1]", "finish_reason": "stop"},
        "citations": [
            {
                "id": "T1",
                "type": "text",
                "source": {"file": "manual.pdf", "page": 12, "chunk_id": "c-1"},
                "quote": "supporting text",
                "score": 0.91,
            }
        ],
        "retrieval": {"text_hits": 1},
        "usage": {"latency_ms": 10.5},
    }


def _error_payload() -> dict[str, Any]:
    return {
        "request_id": "req-1",
        "trace_id": "trace-1",
        "error": {"code": "QUERY_FAILED", "message": "query failed", "retryable": True},
    }


def test_query_request_strips_query_and_applies_v1_defaults() -> None:
    request = QueryRequest(query="  hello  ", workspace_id="power-equipment")

    assert request.query == "hello"
    assert request.mode is QueryMode.AUTO
    assert request.top_k == 5
    assert request.include_context is False
    assert request.include_debug is False


def test_query_request_keeps_legacy_evidence_defaults() -> None:
    request = QueryRequest(query="pressure", workspace_id="ws-1")

    assert request.evidence_only is False
    assert request.evidence_profile is EvidenceSelectionProfile.AUTO
    assert request.evidence_types == ()
    assert selected_citation_types(request) is None


def test_legacy_query_request_serialization_preserves_pre_task_json_payload() -> None:
    request = QueryRequest(query="pressure", workspace_id="ws-1")

    assert request.model_dump(mode="json") == {
        "query": "pressure",
        "workspace_id": "ws-1",
        "mode": "auto",
        "top_k": 5,
        "include_context": False,
        "include_debug": False,
    }


def test_evidence_requests_serialize_selection_fields_for_reconstruction() -> None:
    requests_and_expected = [
        (
            QueryRequest(query="pressure", workspace_id="ws-1", evidence_only=True),
            {"evidence_only": True, "evidence_profile": "auto", "evidence_types": []},
        ),
        (
            QueryRequest(
                query="pressure",
                workspace_id="ws-1",
                evidence_only=True,
                evidence_profile="graphrag_only",
            ),
            {"evidence_only": True, "evidence_profile": "graphrag_only", "evidence_types": []},
        ),
        (
            QueryRequest(
                query="pressure",
                workspace_id="ws-1",
                evidence_only=True,
                evidence_profile="custom",
                evidence_types=(CitationType.COMMUNITY, CitationType.TEXT),
            ),
            {
                "evidence_only": True,
                "evidence_profile": "custom",
                "evidence_types": ["community", "text"],
            },
        ),
    ]

    for request, expected in requests_and_expected:
        payload = request.model_dump(mode="json")
        assert {field: payload[field] for field in expected} == expected


def test_legacy_serialization_preserves_pydantic_field_selection() -> None:
    request = QueryRequest(query="pressure", workspace_id="ws-1")

    assert request.model_dump(mode="json", include={"query", "evidence_only"}) == {
        "query": "pressure",
        "evidence_only": False,
    }
    assert request.model_dump(mode="json", exclude={"workspace_id"}) == {
        "query": "pressure",
        "mode": "auto",
        "top_k": 5,
        "include_context": False,
        "include_debug": False,
    }


def test_evidence_profile_values_are_stable() -> None:
    assert tuple(item.value for item in EvidenceSelectionProfile) == (
        "auto",
        "rag_only",
        "graphrag_local_only",
        "graphrag_global_only",
        "graphrag_only",
        "combined",
        "custom",
    )


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("rag_only", (CitationType.TEXT,)),
        ("graphrag_local_only", (CitationType.GRAPH,)),
        ("graphrag_global_only", (CitationType.COMMUNITY,)),
        ("graphrag_only", (CitationType.GRAPH, CitationType.COMMUNITY)),
        ("combined", (CitationType.TEXT, CitationType.GRAPH, CitationType.COMMUNITY)),
    ],
)
def test_evidence_profiles_resolve_to_exact_citation_types(profile: str, expected) -> None:
    request = QueryRequest(
        query="pressure",
        workspace_id="ws-1",
        evidence_only=True,
        evidence_profile=profile,
    )
    assert selected_citation_types(request) == expected


def test_custom_evidence_profile_preserves_requested_order() -> None:
    request = QueryRequest(
        query="pressure",
        workspace_id="ws-1",
        evidence_only=True,
        evidence_profile="custom",
        evidence_types=(CitationType.COMMUNITY, CitationType.TEXT),
    )
    assert selected_citation_types(request) == (CitationType.COMMUNITY, CitationType.TEXT)


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence_profile": "rag_only"},
        {"evidence_types": ("text",)},
        {"evidence_only": True, "mode": "local", "evidence_profile": "rag_only"},
        {"evidence_only": True, "evidence_profile": "custom"},
        {"evidence_only": True, "evidence_profile": "rag_only", "evidence_types": ("text",)},
        {
            "evidence_only": True,
            "evidence_profile": "custom",
            "evidence_types": ("text", "text"),
        },
    ],
)
def test_invalid_evidence_selection_combinations_fail_before_execution(changes) -> None:
    payload = {"query": "pressure", "workspace_id": "ws-1", **changes}
    with pytest.raises(ValidationError):
        QueryRequest.model_validate(payload)


def test_query_request_rejects_empty_query_and_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(query="", workspace_id="power-equipment")
    with pytest.raises(ValidationError):
        QueryRequest.model_validate({"query": "ok", "workspace_id": "power-equipment", "mode": "drift"})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("query", " "),
        ("query", "x" * 65537),
        ("workspace_id", ""),
        ("workspace_id", "x" * 129),
        ("top_k", 0),
        ("top_k", 101),
    ],
    ids=["blank-query", "query-too-long", "empty-workspace", "workspace-too-long", "top-k-too-low", "top-k-too-high"],
)
def test_query_request_enforces_field_bounds(field: str, value: Any) -> None:
    payload: dict[str, Any] = {"query": "ok", "workspace_id": "power-equipment"}
    payload[field] = value

    with pytest.raises(ValidationError):
        QueryRequest.model_validate(payload)


def test_query_response_serializes_stable_v1_shape() -> None:
    response = QueryResponse(
        request_id="req-1",
        trace_id="trace-1",
        status=QueryStatus.OK,
        mode=ModeDecision(
            requested=QueryMode.AUTO,
            used=QueryMode.LOCAL,
            reason="entity relation question",
        ),
        answer=AnswerPayload(text="answer [T1]", finish_reason="stop"),
        citations=[
            Citation(
                id="T1",
                type=CitationType.TEXT,
                source=SourceRef(file="manual.pdf", page=12, chunk_id="c-1"),
                quote="supporting text",
                score=0.91,
            )
        ],
        retrieval=RetrievalSummary(text_hits=1),
        usage=UsageMetrics(latency_ms=10.5),
    )

    payload = response.model_dump(mode="json")

    assert payload["schema_version"] == "graphrag.query.v1"
    assert payload["status"] == "ok"
    assert payload["citations"][0]["source"]["page"] == 12
    assert "evidence" not in payload


def test_query_response_top_level_fields_are_stable_for_v1() -> None:
    assert set(QueryResponse.model_fields) == {
        "schema_version",
        "request_id",
        "trace_id",
        "status",
        "mode",
        "answer",
        "citations",
        "context",
        "retrieval",
        "usage",
        "warnings",
        "debug",
    }


def test_query_error_response_serializes_fixed_error_shape() -> None:
    response = QueryErrorResponse.model_validate(_error_payload())

    assert response.model_dump(mode="json") == {
        "schema_version": "graphrag.query.v1",
        "request_id": "req-1",
        "trace_id": "trace-1",
        "status": "error",
        "error": {"code": "QUERY_FAILED", "message": "query failed", "retryable": True, "details": {}},
    }


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
def test_citation_rejects_non_finite_scores(score: float) -> None:
    with pytest.raises(ValidationError):
        Citation(id="T1", type=CitationType.TEXT, quote="text", score=score)


def test_citation_allows_missing_score() -> None:
    citation = Citation(id="T1", type=CitationType.TEXT, quote="text")

    assert citation.score is None


def test_context_and_debug_payloads_use_only_declared_fields() -> None:
    context = ContextPayload(
        items=[ContextItem(id="T1", type=CitationType.TEXT, text="context")],
        rendered_text="rendered context",
    )
    debug = DebugPayload(prompt="prompt", raw_mode_result={"mode": "local"})

    assert context.model_dump(mode="json") == {
        "items": [{"id": "T1", "type": "text", "text": "context", "source": None, "score": None}],
        "rendered_text": "rendered context",
    }
    assert debug.model_dump(mode="json") == {"prompt": "prompt", "raw_mode_result": {"mode": "local"}}


@pytest.mark.parametrize(
    ("model_type", "payload"),
    [
        (QueryRequest, {"query": "ok", "workspace_id": "power-equipment"}),
        (SourceRef, {"file": "manual.pdf"}),
        (GraphTriple, {"subject": "a", "predicate": "relates_to", "object": "b"}),
        (Citation, {"id": "T1", "type": "text", "quote": "text"}),
        (ModeDecision, {"requested": "auto", "used": "local", "reason": "reason"}),
        (AnswerPayload, {"text": "answer", "finish_reason": "stop"}),
        (RetrievalSummary, {}),
        (UsageMetrics, {"latency_ms": 1.0}),
        (WarningItem, {"code": "WARNING", "message": "warning"}),
        (ErrorDetail, {"code": "ERROR", "message": "error", "retryable": False}),
        (ContextItem, {"id": "T1", "type": "text", "text": "context"}),
        (ContextPayload, {}),
        (DebugPayload, {}),
        (QueryResponse, _response_payload()),
        (QueryErrorResponse, _error_payload()),
        (
            MetaEvent,
            {
                "request_id": "req-1",
                "sequence": 1,
                "mode": {"requested": "auto", "used": "local", "reason": "reason"},
                "token_streaming": True,
            },
        ),
        (
            CitationEvent,
            {"request_id": "req-1", "sequence": 1, "citation": {"id": "T1", "type": "text", "quote": "text"}},
        ),
        (DeltaEvent, {"request_id": "req-1", "sequence": 1, "text": "delta"}),
        (FinalEvent, {"request_id": "req-1", "sequence": 1, "response": _response_payload()}),
        (
            ErrorEvent,
            {
                "request_id": "req-1",
                "sequence": 1,
                "error": {"code": "ERROR", "message": "error", "retryable": False},
            },
        ),
    ],
)
def test_every_contract_model_forbids_unknown_fields(model_type: type[Any], payload: dict[str, Any]) -> None:
    payload_with_extra = {**payload, "unexpected": "not part of v1"}

    with pytest.raises(ValidationError):
        model_type.model_validate(payload_with_extra)


@pytest.mark.parametrize(
    ("event", "expected_type", "payload"),
    [
        (
            "meta",
            MetaEvent,
            {
                "event": "meta",
                "request_id": "req-1",
                "sequence": 1,
                "mode": {"requested": "auto", "used": "local", "reason": "reason"},
                "token_streaming": True,
            },
        ),
        (
            "citation",
            CitationEvent,
            {
                "event": "citation",
                "request_id": "req-1",
                "sequence": 2,
                "citation": {"id": "T1", "type": "text", "quote": "text"},
            },
        ),
        ("delta", DeltaEvent, {"event": "delta", "request_id": "req-1", "sequence": 3, "text": "answer"}),
        (
            "final",
            FinalEvent,
            {"event": "final", "request_id": "req-1", "sequence": 4, "response": _response_payload()},
        ),
        (
            "error",
            ErrorEvent,
            {
                "event": "error",
                "request_id": "req-1",
                "sequence": 5,
                "error": {"code": "ERROR", "message": "error", "retryable": False},
            },
        ),
    ],
)
def test_query_stream_event_dispatches_by_event(
    event: str,
    expected_type: type[Any],
    payload: dict[str, Any],
) -> None:
    parsed: QueryStreamEvent = TypeAdapter(QueryStreamEvent).validate_python(payload)

    assert isinstance(parsed, expected_type)
    assert parsed.event == event
    assert parsed.request_id == "req-1"


def test_query_stream_event_rejects_unknown_discriminator() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(QueryStreamEvent).validate_python({"event": "heartbeat", "request_id": "req-1", "sequence": 1})


def test_query_response_rejects_error_status() -> None:
    payload = _response_payload()
    payload["status"] = "error"

    with pytest.raises(ValidationError):
        QueryResponse.model_validate(payload)
