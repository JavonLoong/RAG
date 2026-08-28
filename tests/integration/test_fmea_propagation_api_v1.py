from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from chroma_rag_poc.api import create_app
from core_domain.fmea.states import ActorType, RunStatus
from fmea_application.propagation_service import PropagationError, PropagationReviewResult, PropagationRun
from fmea_application.review_contracts import ActorContext
from tests.fmea_propagation_fixtures import _graph


TOKEN = "a" * 32
UUID1 = "00000000-0000-4000-8000-000000000501"


class FakeAuth:
    def authenticate(self, bearer_token: str | None, remote_host: str | None) -> ActorContext:
        assert bearer_token == TOKEN
        assert remote_host in {"127.0.0.1", "testclient"}
        return ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"propagation_reviewer"}), "ws-1")


def _run(graph: Any) -> PropagationRun:
    return PropagationRun(
        run_id="run-1",
        workspace_id="ws-1",
        analysis_id=graph.analysis_id,
        status=RunStatus.SUCCEEDED,
        graph=graph,
        error_code=None,
        error_message=None,
        assistance_suggestion_ids=("suggestion-1",),
        created_at="2026-08-28T00:00:00Z",
        updated_at="2026-08-28T00:00:01Z",
    )


@dataclass
class FakePropagationService:
    graph: Any
    calls: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.run = _run(self.graph)

    def start_analysis(self, command: Any, actor: ActorContext) -> PropagationRun:
        self.calls.append("start_analysis")
        assert command.analysis_id == "analysis-1"
        assert actor.workspace_id == "ws-1"
        return self.run

    def get_run(self, run_id: str, actor: ActorContext) -> PropagationRun:
        self.calls.append("get_run")
        assert run_id == self.run.run_id
        return self.run

    def get_graph(self, graph_revision_id: str, actor: ActorContext) -> Any:
        self.calls.append("get_graph")
        assert graph_revision_id == self.graph.graph_revision_id
        return self.graph

    def confirm_graph(self, command: Any, actor: ActorContext) -> PropagationReviewResult:
        self.calls.append("confirm_graph")
        if command.expected_graph_record_version != self.graph.record_version:
            raise PropagationError("FMEA_PROPAGATION_VERSION_CONFLICT", "propagation graph revision is stale")
        return PropagationReviewResult(
            graph=self.graph,
            decision_id="decision-1",
            audit_event_id="audit-1",
            outbox_event_id="outbox-1",
        )


@pytest.fixture
def propagation_client() -> tuple[TestClient, FakePropagationService]:
    service = FakePropagationService(_graph("ws-1"))
    runtime = SimpleNamespace(service=service)
    app = create_app(
        review_auth_provider=FakeAuth(),
        propagation_runtime_factory=lambda _workspace: runtime,
    )
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: SimpleNamespace(workspace_id=workspace_id))
    return TestClient(app, client=("127.0.0.1", 50000)), service


def _headers(*, version: int | None = None, key: str = UUID1) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": key}
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return headers


def _start_body() -> dict[str, object]:
    return {
        "source_row_ids": ["row-1"],
        "evidence_pack_id": "pack-1",
        "topology_id": "topology-1",
        "topology_version": "1.0.0",
        "domain_pack_id": "fuel-combustion",
        "domain_pack_version": "1.0.0",
        "rule_pack_id": "fuel-combustion-propagation",
        "rule_pack_version": "1.0.0",
    }


def _review_body() -> dict[str, object]:
    return {
        "edge_decisions": [
            {"edge_id": edge.edge_id, "action": "accept", "reason": "accepted by reviewer"}
            for edge in _graph("ws-1").edges
        ],
        "acknowledgements": [],
    }


def test_start_status_and_graph_are_service_backed(propagation_client: tuple[TestClient, FakePropagationService]) -> None:
    client, service = propagation_client
    started = client.post(
        "/api/v1/fmea/analyses/analysis-1/propagation-runs",
        headers=_headers(version=1),
        json=_start_body(),
    )
    assert started.status_code == 202
    assert started.json()["resource_type"] == "propagation_run"
    assert started.headers["location"].endswith("run-1")

    status = client.get("/api/v1/fmea/propagation-runs/run-1", headers=_headers())
    graph = client.get("/api/v1/fmea/propagation-graphs/graph-1", headers=_headers())
    assert status.status_code == graph.status_code == 200
    assert service.calls == ["start_analysis", "get_run", "get_graph"]


def test_graph_review_rejects_stale_etag(propagation_client: tuple[TestClient, FakePropagationService]) -> None:
    client, service = propagation_client
    service.graph = replace(service.graph, record_version=2)
    response = client.post(
        "/api/v1/fmea/propagation-graphs/graph-1/reviews",
        headers=_headers(version=1),
        json=_review_body(),
    )
    assert response.status_code == 412
    assert response.json()["code"] == "FMEA_PROPAGATION_VERSION_CONFLICT"
    assert service.calls == ["confirm_graph"]


def test_start_rejects_client_topology_or_model_override(
    propagation_client: tuple[TestClient, FakePropagationService],
) -> None:
    client, service = propagation_client
    body = _start_body()
    body["model"] = "client-model"
    response = client.post(
        "/api/v1/fmea/analyses/analysis-1/propagation-runs",
        headers=_headers(version=1),
        json=body,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "FMEA_REVIEW_REQUEST_INVALID"
    assert service.calls == []


def test_paths_are_paginated_with_signed_cursor(propagation_client: tuple[TestClient, FakePropagationService]) -> None:
    client, service = propagation_client
    first = client.get(
        "/api/v1/fmea/propagation-graphs/graph-1/paths?limit=1",
        headers=_headers(),
    )
    assert first.status_code == 200
    assert len(first.json()["data"]["items"]) == 1
    cursor = first.json()["data"]["next_cursor"]
    assert cursor

    second = client.get(
        "/api/v1/fmea/propagation-graphs/graph-1/paths?limit=1&cursor=" + cursor,
        headers=_headers(),
    )
    assert second.status_code == 200
    assert len(second.json()["data"]["items"]) == 1
    assert service.calls == ["get_graph", "get_graph"]


def test_review_replay_response_is_identical_for_same_request(
    propagation_client: tuple[TestClient, FakePropagationService],
) -> None:
    client, service = propagation_client
    first = client.post(
        "/api/v1/fmea/propagation-graphs/graph-1/reviews",
        headers=_headers(version=1),
        json=_review_body(),
    )
    replay = client.post(
        "/api/v1/fmea/propagation-graphs/graph-1/reviews",
        headers=_headers(version=1),
        json=_review_body(),
    )
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert service.calls == ["confirm_graph", "confirm_graph"]
