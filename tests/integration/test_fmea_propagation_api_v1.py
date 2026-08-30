from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from chroma_rag_poc.api import create_app
from chroma_rag_poc.workspace_registry import WorkspaceConfig
from fastapi.testclient import TestClient

from core_domain.fmea.states import ActorType, RunStatus
from core_domain.query_contracts import QueryMode
from fmea_application.propagation_service import PropagationError, PropagationReviewResult, PropagationRun
from fmea_application.review_contracts import ActorContext
from tests.fmea_propagation_fixtures import _graph

TOKEN = "a" * 32
TOKEN2 = "b" * 32
UUID1 = "00000000-0000-4000-8000-000000000501"
REPO_ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY_ROOT = REPO_ROOT / "domain_packs" / "fuel-combustion" / "topology"
TOPOLOGY_SHA256 = "53559c5c6ed45e1a9e787a5452268cc5c1fc8259d0694459546162af418304e5"
PROPAGATION_ENV_KEYS = (
    "FMEA_PROPAGATION_TOPOLOGY_ROOT",
    "FMEA_PROPAGATION_TOPOLOGY_ID",
    "FMEA_PROPAGATION_TOPOLOGY_VERSION",
    "FMEA_PROPAGATION_TOPOLOGY_SHA256",
    "FMEA_PROPAGATION_SOURCE_ROW_IDS",
    "FMEA_PROPAGATION_EVIDENCE_PACK_ID",
    "FMEA_PROPAGATION_DOMAIN_PACK_ID",
    "FMEA_PROPAGATION_DOMAIN_PACK_VERSION",
    "FMEA_PROPAGATION_RULE_PACK_ID",
    "FMEA_PROPAGATION_RULE_PACK_VERSION",
)
SERVER_DEFAULTS = {
    "source_row_ids": ("server-row",),
    "evidence_pack_id": "server-pack",
    "topology_id": "server-topology",
    "topology_version": "2.0.0",
    "domain_pack_id": "server-domain",
    "domain_pack_version": "2.0.0",
    "rule_pack_id": "server-rule",
    "rule_pack_version": "2.0.0",
}


class FakeAuth:
    def authenticate(self, bearer_token: str | None, remote_host: str | None) -> ActorContext:
        assert bearer_token == TOKEN
        assert remote_host in {"127.0.0.1", "testclient"}
        return ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"propagation_reviewer"}), "ws-1")


class MultiWorkspaceAuth:
    def authenticate(self, bearer_token: str | None, remote_host: str | None) -> ActorContext:
        workspace_id = "ws-2" if bearer_token == TOKEN2 else "ws-1"
        return ActorContext(
            f"reviewer-{workspace_id}",
            ActorType.HUMAN,
            frozenset({"propagation_reviewer"}),
            workspace_id,
        )


class DefaultWorkspaceAuth:
    def authenticate(self, bearer_token: str | None, remote_host: str | None) -> ActorContext:
        return ActorContext(
            "reviewer-fuel",
            ActorType.HUMAN,
            frozenset({"propagation_reviewer"}),
            "fuel-combustion",
        )


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
    start_commands: list[Any] = field(default_factory=list)
    start_error_code: str | None = None

    def __post_init__(self) -> None:
        self.run = _run(self.graph)

    def start_analysis(self, command: Any, actor: ActorContext) -> PropagationRun:
        self.calls.append("start_analysis")
        self.start_commands.append(command)
        assert command.analysis_id == "analysis-1"
        assert actor.workspace_id == "ws-1"
        if self.start_error_code is not None:
            raise PropagationError(self.start_error_code, "bounded propagation validation failed")
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
    runtime = SimpleNamespace(service=service, start_defaults=SERVER_DEFAULTS)
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


def _workspace_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": UUID1}


def _legacy_review_cursor(client: TestClient, graph_revision_id: str, path_id: str) -> str:
    raw = f"{graph_revision_id}\x00{path_id}".encode()
    payload = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(client.app.state.review_cursor_secret, payload, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return f"{payload.decode('ascii')}.{encoded_signature.decode('ascii')}"


def _workspace(tmp_path: Path) -> WorkspaceConfig:
    return WorkspaceConfig(
        workspace_id="fuel-combustion",
        chroma_persist_dir=tmp_path / "chroma",
        chroma_collection="fuel-combustion",
        graph_db_path=tmp_path / "graph" / "graph.sqlite3",
        fmea_db_path=tmp_path / "fmea" / "fmea.sqlite3",
        fmea_template_registry_path=tmp_path / "fmea" / "template_registry",
        supported_modes=frozenset({QueryMode.VECTOR}),
        default_mode=QueryMode.VECTOR,
    )


def _set_complete_propagation_env(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "FMEA_PROPAGATION_TOPOLOGY_ROOT": str(TOPOLOGY_ROOT),
        "FMEA_PROPAGATION_TOPOLOGY_ID": "demo",
        "FMEA_PROPAGATION_TOPOLOGY_VERSION": "1.0.0",
        "FMEA_PROPAGATION_TOPOLOGY_SHA256": TOPOLOGY_SHA256,
        "FMEA_PROPAGATION_SOURCE_ROW_IDS": "server-row",
        "FMEA_PROPAGATION_EVIDENCE_PACK_ID": "server-pack",
        "FMEA_PROPAGATION_DOMAIN_PACK_ID": "fuel-combustion",
        "FMEA_PROPAGATION_DOMAIN_PACK_VERSION": "1.0.0",
        "FMEA_PROPAGATION_RULE_PACK_ID": "fuel-combustion-propagation",
        "FMEA_PROPAGATION_RULE_PACK_VERSION": "1.0.0",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _start_body() -> dict[str, object]:
    return {
        "source_row_ids": ["row-1"],
        "evidence_pack_id": "pack-1",
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
    command = service.start_commands[0]
    assert command.source_row_ids == ("row-1",)
    assert command.evidence_pack_id == "pack-1"
    assert command.topology_id == SERVER_DEFAULTS["topology_id"]
    assert command.topology_version == SERVER_DEFAULTS["topology_version"]
    assert command.domain_pack_id == SERVER_DEFAULTS["domain_pack_id"]
    assert command.domain_pack_version == SERVER_DEFAULTS["domain_pack_version"]
    assert command.rule_pack_id == SERVER_DEFAULTS["rule_pack_id"]
    assert command.rule_pack_version == SERVER_DEFAULTS["rule_pack_version"]

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


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("topology_id", "client-topology"),
        ("topology_version", "9.9.9"),
        ("domain_pack_id", "client-domain"),
        ("domain_pack_version", "9.9.9"),
        ("rule_pack_id", "client-rule"),
        ("rule_pack_version", "9.9.9"),
        ("model", "client-model"),
    ],
)
def test_start_rejects_client_resource_override(
    propagation_client: tuple[TestClient, FakePropagationService],
    field_name: str,
    value: str,
) -> None:
    client, service = propagation_client
    body = _start_body()
    body[field_name] = value
    response = client.post(
        "/api/v1/fmea/analyses/analysis-1/propagation-runs",
        headers=_headers(version=1),
        json=body,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "FMEA_REVIEW_REQUEST_INVALID"
    assert service.calls == []


@pytest.mark.parametrize(
    "error_code",
    [
        "FMEA_PROPAGATION_ENDPOINT_INVALID",
        "FMEA_PROPAGATION_RELATION_INVALID",
        "FMEA_PROPAGATION_EVIDENCE_INVALID",
        "FMEA_PROPAGATION_SOURCE_INVALID",
    ],
)
def test_propagation_validation_error_code_is_preserved_by_rest(
    propagation_client: tuple[TestClient, FakePropagationService],
    error_code: str,
) -> None:
    client, service = propagation_client
    service.start_error_code = error_code

    response = client.post(
        "/api/v1/fmea/analyses/analysis-1/propagation-runs",
        headers=_headers(version=1),
        json=_start_body(),
    )

    assert response.status_code == 422
    assert response.json()["code"] == error_code


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


def test_paths_cursor_rejects_cross_workspace_replay() -> None:
    services: dict[str, FakePropagationService] = {}

    def runtime_factory(workspace: Any) -> Any:
        service = FakePropagationService(_graph(workspace.workspace_id))
        services[workspace.workspace_id] = service
        return SimpleNamespace(service=service, start_defaults=SERVER_DEFAULTS)

    app = create_app(
        review_auth_provider=MultiWorkspaceAuth(),
        propagation_runtime_factory=runtime_factory,
    )
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: SimpleNamespace(workspace_id=workspace_id))
    client = TestClient(app, client=("127.0.0.1", 50000))
    first = client.get(
        "/api/v1/fmea/propagation-graphs/graph-1/paths?limit=1",
        headers=_workspace_headers(TOKEN),
    )
    cursor = first.json()["data"]["next_cursor"]

    replay = client.get(
        "/api/v1/fmea/propagation-graphs/graph-1/paths?limit=1&cursor=" + cursor,
        headers=_workspace_headers(TOKEN2),
    )

    assert first.status_code == 200
    assert replay.status_code == 400
    assert replay.json()["code"] == "FMEA_REVIEW_REQUEST_INVALID"
    assert set(services) == {"ws-1", "ws-2"}


def test_paths_cursor_rejects_cursor_from_another_resource(
    propagation_client: tuple[TestClient, FakePropagationService],
) -> None:
    client, _service = propagation_client
    path_id = sorted(_graph("ws-1").paths, key=lambda item: item.path_id)[0].path_id
    cursor = _legacy_review_cursor(client, "graph-1", path_id)

    response = client.get(
        "/api/v1/fmea/propagation-graphs/graph-1/paths?limit=1&cursor=" + cursor,
        headers=_headers(),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "FMEA_REVIEW_REQUEST_INVALID"


def test_paths_cursor_rejects_wrong_graph(
    propagation_client: tuple[TestClient, FakePropagationService],
) -> None:
    client, service = propagation_client
    first = client.get(
        "/api/v1/fmea/propagation-graphs/graph-1/paths?limit=1",
        headers=_headers(),
    )
    service.graph = replace(service.graph, graph_revision_id="graph-2")

    response = client.get(
        "/api/v1/fmea/propagation-graphs/graph-2/paths?limit=1&cursor="
        + first.json()["data"]["next_cursor"],
        headers=_headers(),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "FMEA_REVIEW_REQUEST_INVALID"


def test_paths_cursor_rejects_signature_tampering(
    propagation_client: tuple[TestClient, FakePropagationService],
) -> None:
    client, _service = propagation_client
    first = client.get(
        "/api/v1/fmea/propagation-graphs/graph-1/paths?limit=1",
        headers=_headers(),
    )
    cursor = first.json()["data"]["next_cursor"]
    tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")

    response = client.get(
        "/api/v1/fmea/propagation-graphs/graph-1/paths?limit=1&cursor=" + tampered,
        headers=_headers(),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "FMEA_REVIEW_REQUEST_INVALID"


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


def test_default_create_app_lazily_builds_workspace_propagation_runtime_from_server_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _set_complete_propagation_env(monkeypatch)
    workspace = _workspace(tmp_path)
    app = create_app(
        persist_dir=tmp_path / "rag" / "chroma",
        upload_dir=tmp_path / "rag" / "uploads",
        log_dir=tmp_path / "rag" / "logs",
        review_auth_provider=DefaultWorkspaceAuth(),
    )
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: workspace)
    client = TestClient(app, client=("127.0.0.1", 50000))

    response = client.get(
        "/api/v1/fmea/propagation-graphs/missing/paths",
        headers=_headers(),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "FMEA_PROPAGATION_GRAPH_NOT_FOUND"
    runtime = app.state.propagation_runtimes["fuel-combustion"]
    assert runtime.service is not None
    assert runtime.start_defaults["topology_id"] == "demo"
    assert runtime.start_defaults["rule_pack_id"] == "fuel-combustion-propagation"


@pytest.mark.parametrize("partial", [False, True], ids=["missing", "incomplete"])
def test_default_create_app_fails_closed_on_first_propagation_access_when_server_env_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    partial: bool,
) -> None:
    for key in PROPAGATION_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    if partial:
        monkeypatch.setenv("FMEA_PROPAGATION_TOPOLOGY_ROOT", str(TOPOLOGY_ROOT))
    workspace = _workspace(tmp_path)
    app = create_app(
        persist_dir=tmp_path / "rag" / "chroma",
        upload_dir=tmp_path / "rag" / "uploads",
        log_dir=tmp_path / "rag" / "logs",
        review_auth_provider=DefaultWorkspaceAuth(),
    )
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: workspace)
    client = TestClient(app, client=("127.0.0.1", 50000))

    response = client.get(
        "/api/v1/fmea/propagation-graphs/missing",
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "FMEA_WORKSPACE_CONFIGURATION_INVALID"
    assert app.state.propagation_runtimes == {}


def test_explicit_runtime_with_incomplete_start_defaults_fails_as_workspace_configuration() -> None:
    service = FakePropagationService(_graph("ws-1"))
    runtime = SimpleNamespace(service=service, start_defaults={"topology_id": "server-topology"})
    app = create_app(
        review_auth_provider=FakeAuth(),
        propagation_runtime_factory=lambda _workspace: runtime,
    )
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: SimpleNamespace(workspace_id=workspace_id))
    client = TestClient(app, client=("127.0.0.1", 50000), raise_server_exceptions=False)

    response = client.post(
        "/api/v1/fmea/analyses/analysis-1/propagation-runs",
        headers=_headers(version=1),
        json=_start_body(),
    )

    assert response.status_code == 503
    assert response.json()["code"] == "FMEA_WORKSPACE_CONFIGURATION_INVALID"
    assert service.calls == []
