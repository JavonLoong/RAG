"""Integration tests for the versioned non-streaming query endpoint."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, PACKAGE_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc.api import create_app  # noqa: E402
from chroma_rag_poc.query_service import QueryExecutionError, QueryRuntime, QueryService  # noqa: E402
from chroma_rag_poc.routes_query_v1 import get_query_service  # noqa: E402
from chroma_rag_poc.workspace_registry import WorkspaceRegistry  # noqa: E402

from core_domain.query_contracts import EvidenceSelectionProfile, QueryMode  # noqa: E402


def _query_response(*, mode: QueryMode = QueryMode.LOCAL) -> dict[str, Any]:
    return {
        "request_id": "request-1",
        "trace_id": "trace-1",
        "status": "ok",
        "mode": {"requested": mode.value, "used": mode.value, "reason": "explicit test mode"},
        "answer": {"text": "Compressor fouling is caused by deposits.", "finish_reason": "stop"},
        "citations": [],
        "retrieval": {"text_hits": 0},
        "usage": {"latency_ms": 1.0},
    }


class FakeQueryService:
    def __init__(self, result: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.result = result or _query_response()
        self.error = error
        self.requests: list[Any] = []

    def query(self, payload: Any) -> dict[str, Any]:
        self.requests.append(payload)
        if self.error is not None:
            raise self.error
        return self.result


class ControlledRuntimeFactory:
    def __init__(self, runtime: QueryRuntime, error: Exception | None = None) -> None:
        self.runtime = runtime
        self.error = error
        self.calls: list[Any] = []

    def create(self, workspace: Any) -> QueryRuntime:
        self.calls.append(workspace)
        if self.error is not None:
            raise self.error
        return self.runtime


def _real_service(
    tmp_path: Path,
    *,
    supported_modes: list[QueryMode],
    mode: QueryMode,
    create_chroma: bool = True,
    llm: Any | None = None,
    factory_error: Exception | None = None,
) -> tuple[QueryService, ControlledRuntimeFactory, Path]:
    runtime_root = tmp_path / "runtime"
    chroma_path = runtime_root / "chroma"
    if create_chroma:
        chroma_path.mkdir(parents=True)
    registry_path = tmp_path / "workspaces.json"
    registry_path.write_text(
        json.dumps({
            "allowed_root": str(runtime_root),
            "workspaces": {
                "power-equipment": {
                    "chroma_persist_dir": str(chroma_path),
                    "chroma_collection": "power_equipment",
                    "graph_db_path": None,
                    "supported_modes": [item.value for item in supported_modes],
                    "default_mode": mode.value,
                }
            },
        }),
        encoding="utf-8",
    )
    registry = WorkspaceRegistry.from_file(registry_path)
    workspace = registry.get("power-equipment")
    assert workspace.fmea_db_path is None
    assert workspace.fmea_template_registry_path is None
    runtime = QueryRuntime(
        text_retriever=object(),
        graph_retriever=None,
        global_searcher=None,
        query_router=None,
        reranker=None,
        hallucination_guard=None,
        llm=llm,
    )
    factory = ControlledRuntimeFactory(runtime, error=factory_error)
    service = QueryService(
        registry,
        factory,
        id_factory=iter(("request-1", "trace-1")).__next__,
        clock=iter((10.0, 10.025)).__next__,
    )
    return service, factory, chroma_path


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    monkeypatch.delenv("RAG_WORKSPACE_CONFIG", raising=False)
    application = create_app(
        persist_dir=tmp_path / "persist",
        upload_dir=tmp_path / "uploads",
        log_dir=tmp_path / "logs",
    )
    assert isinstance(application.state.query_service, QueryService)
    yield application
    application.dependency_overrides.clear()


def _client(application: Any, service: FakeQueryService) -> TestClient:
    application.dependency_overrides[get_query_service] = lambda: service
    return TestClient(application)


def _real_client(application: Any, service: QueryService) -> TestClient:
    application.dependency_overrides[get_query_service] = lambda: service
    return TestClient(application)


def test_query_endpoint_returns_versioned_response_and_uses_dependency_override(app: Any) -> None:
    service = FakeQueryService()
    with _client(app, service) as client:
        response = client.post(
            "/api/v1/query",
            json={
                "query": "What causes compressor fouling?",
                "workspace_id": "power-equipment",
                "mode": "local",
                "top_k": 5,
            },
        )

    assert response.status_code == 200
    assert response.json()["schema_version"] == "graphrag.query.v1"
    assert response.json()["mode"]["used"] == "local"
    assert service.requests[0].query == "What causes compressor fouling?"


def test_query_endpoint_accepts_evidence_selection_through_injected_service(app: Any) -> None:
    service = FakeQueryService()
    with _client(app, service) as client:
        response = client.post(
            "/api/v1/query",
            json={
                "query": "fuel pressure",
                "workspace_id": "power-equipment",
                "mode": "auto",
                "evidence_only": True,
                "evidence_profile": "graphrag_only",
            },
        )

    assert response.status_code == 200
    captured_request = service.requests[0]
    assert captured_request.evidence_only is True
    assert captured_request.evidence_profile is EvidenceSelectionProfile.GRAPHRAG_ONLY


def test_empty_query_returns_v1_invalid_request_envelope(app: Any) -> None:
    service = FakeQueryService()
    with _client(app, service) as client:
        response = client.post(
            "/api/v1/query",
            json={"query": "   ", "workspace_id": "power-equipment"},
        )

    body = response.json()
    assert response.status_code == 422
    assert body["schema_version"] == "graphrag.query.v1"
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert "detail" not in body
    assert isinstance(body["error"]["details"], dict)
    assert service.requests == []


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("INVALID_REQUEST", 422),
        ("WORKSPACE_NOT_FOUND", 404),
        ("INDEX_NOT_READY", 409),
        ("MODE_UNAVAILABLE", 409),
        ("LLM_UNAVAILABLE", 503),
        ("QUERY_FAILED", 500),
    ],
)
def test_query_execution_errors_use_stable_status_mapping(app: Any, code: str, status: int) -> None:
    service = FakeQueryService(
        error=QueryExecutionError(
            code,
            "internal exception detail C:\\absolute\\runtime\\graph.sqlite3 sk-secret-value",
            retryable=True,
            details={"cause": "RuntimeError: C:\\absolute\\runtime\\graph.sqlite3", "token": "sk-secret-value"},
        )
    )
    with _client(app, service) as client:
        response = client.post(
            "/api/v1/query",
            json={"query": "public question", "workspace_id": "power-equipment"},
        )

    body = response.json()
    assert response.status_code == status
    assert body["schema_version"] == "graphrag.query.v1"
    assert body["status"] == "error"
    assert body["error"]["code"] == code
    assert body["error"]["retryable"] is (code in {"INDEX_NOT_READY", "LLM_UNAVAILABLE", "QUERY_FAILED"})
    assert "detail" not in body


def test_unexpected_500_does_not_leak_exception_or_request_only_fields(app: Any) -> None:
    service = FakeQueryService(
        error=RuntimeError(
            "RuntimeError: failed at C:\\absolute\\runtime\\graph.sqlite3; "
            "api_key=sk-super-secret-value; query=private request payload"
        )
    )
    with _client(app, service) as client:
        response = client.post(
            "/api/v1/query",
            json={
                "query": "private request payload",
                "workspace_id": "power-equipment",
                "include_debug": True,
            },
        )

    body_text = response.text
    assert response.status_code == 500
    body = response.json()
    assert body["schema_version"] == "graphrag.query.v1"
    assert body["status"] == "error"
    assert body["error"] == {
        "code": "QUERY_FAILED",
        "message": "Query execution failed.",
        "retryable": True,
        "details": {},
    }
    assert "RuntimeError" not in body_text
    assert "C:\\absolute\\runtime\\graph.sqlite3" not in body_text
    assert "private request payload" not in body_text
    assert "sk-super-secret-value" not in body_text


def test_openapi_documents_success_and_v1_error_models(app: Any) -> None:
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/api/v1/query"]["post"]
    assert operation["responses"]["200"]["content"]["application/json"]
    assert "QueryResponse" in schema["components"]["schemas"]
    assert "QueryErrorResponse" in schema["components"]["schemas"]
    for status in ("404", "409", "422", "500", "503"):
        assert operation["responses"][status]["content"]["application/json"]["schema"]["$ref"].endswith(
            "/QueryErrorResponse"
        )


def test_legacy_health_route_remains_available(app: Any) -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_real_query_service_rejects_unsupported_mode_before_runtime_execution(app: Any, tmp_path: Path) -> None:
    service, factory, _ = _real_service(
        tmp_path,
        supported_modes=[QueryMode.VECTOR],
        mode=QueryMode.LOCAL,
    )
    with _real_client(app, service) as client:
        response = client.post(
            "/api/v1/query",
            json={"query": "question", "workspace_id": "power-equipment", "mode": "local"},
        )

    body = response.json()
    assert response.status_code == 409
    assert body["error"]["code"] == "MODE_UNAVAILABLE"
    assert body["error"]["retryable"] is False
    assert factory.calls == []


def test_real_query_service_maps_missing_index_path_to_conflict(app: Any, tmp_path: Path) -> None:
    service, factory, _ = _real_service(
        tmp_path,
        supported_modes=[QueryMode.VECTOR],
        mode=QueryMode.VECTOR,
        create_chroma=False,
    )
    with _real_client(app, service) as client:
        response = client.post(
            "/api/v1/query",
            json={"query": "question", "workspace_id": "power-equipment", "mode": "vector"},
        )

    body = response.json()
    assert response.status_code == 409
    assert body["error"]["code"] == "INDEX_NOT_READY"
    assert body["error"]["retryable"] is True
    assert factory.calls == []


def test_real_query_service_maps_missing_llm_to_service_unavailable(app: Any, tmp_path: Path) -> None:
    service, factory, _ = _real_service(
        tmp_path,
        supported_modes=[QueryMode.LOCAL],
        mode=QueryMode.LOCAL,
        llm=None,
    )
    with _real_client(app, service) as client:
        response = client.post(
            "/api/v1/query",
            json={"query": "question", "workspace_id": "power-equipment", "mode": "local"},
        )

    body = response.json()
    assert response.status_code == 503
    assert body["error"]["code"] == "LLM_UNAVAILABLE"
    assert body["error"]["retryable"] is True
    assert len(factory.calls) == 1


def test_real_query_service_keeps_unknown_runtime_failure_as_query_failed(app: Any, tmp_path: Path) -> None:
    service, factory, _ = _real_service(
        tmp_path,
        supported_modes=[QueryMode.VECTOR],
        mode=QueryMode.VECTOR,
        factory_error=RuntimeError("unexpected runtime failure"),
    )
    with _real_client(app, service) as client:
        response = client.post(
            "/api/v1/query",
            json={"query": "question", "workspace_id": "power-equipment", "mode": "vector"},
        )

    body = response.json()
    assert response.status_code == 500
    assert body["error"]["code"] == "QUERY_FAILED"
    assert body["error"]["retryable"] is True
    assert "unexpected runtime failure" not in response.text
    assert len(factory.calls) == 1


def test_non_v1_validation_keeps_fastapi_detail_array(app: Any) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/search",
            json={"query": "", "collection": "power_equipment", "top_k": 5},
        )

    body = response.json()
    assert response.status_code == 422
    assert isinstance(body["detail"], list)
    assert "error" not in body
