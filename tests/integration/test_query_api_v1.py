"""Integration tests for the versioned non-streaming query endpoint."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, PACKAGE_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc.api import create_app  # noqa: E402
from chroma_rag_poc.query_service import QueryExecutionError, QueryService  # noqa: E402
from chroma_rag_poc.routes_query_v1 import get_query_service  # noqa: E402

from core_domain.query_contracts import QueryMode  # noqa: E402


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


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
