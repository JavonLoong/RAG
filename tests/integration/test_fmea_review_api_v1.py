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
from fmea_review_fixtures import (  # noqa: E402
    FakeReviewSuggestionGenerator,
    InlineReviewExecutor,
    valid_accept_body,
)

from fmea_infrastructure.composition import build_workspace_review_runtime  # noqa: E402


def write_headers(version: int) -> dict[str, str]:
    return {
        "Authorization": "Bearer " + "a" * 32,
        "If-Match": f'"{version}"',
        "Idempotency-Key": "f2308024-49d5-49ea-93ee-fcb95739d937",
    }


@pytest.fixture
def review_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixture_review_bundle: Any,
    fixture_system_actor: Any,
    valid_review_suggestion_draft: Any,
    fixture_review_model_manifest: Any,
) -> Iterator[TestClient]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    registry_path = config_dir / "workspaces.json"
    registry_path.write_text(
        json.dumps(
            {
                "allowed_root": "../runtime",
                "workspaces": {
                    "ws-1": {
                        "chroma_persist_dir": "../runtime/chroma",
                        "chroma_collection": "workspace",
                        "graph_db_path": "../runtime/graph/graph.sqlite3",
                        "fmea_db_path": "../runtime/fmea/fmea.sqlite3",
                        "fmea_template_registry_path": "../runtime/fmea/templates",
                        "supported_modes": ["vector"],
                        "default_mode": "vector",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))
    monkeypatch.setenv("FMEA_LOCAL_AUTH_ENABLED", "true")
    monkeypatch.setenv("FMEA_REVIEW_TOKEN", "a" * 32)
    monkeypatch.setenv("FMEA_REVIEW_ACTOR_ID", "reviewer-1")
    monkeypatch.setenv("FMEA_REVIEW_WORKSPACE_ID", "ws-1")

    from chroma_rag_poc.workspace_registry import WorkspaceRegistry

    workspace = WorkspaceRegistry.from_env().get("ws-1")
    runtime = build_workspace_review_runtime(
        workspace,
        generator=FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        executor=InlineReviewExecutor(),
    )
    runtime.repository.save_review_candidate_bundle(fixture_review_bundle, fixture_system_actor)
    app: FastAPI = create_app(review_runtime_factory=lambda _workspace: runtime)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        yield client


def test_context_returns_v1_envelope_and_etag(review_client: TestClient) -> None:
    response = review_client.get(
        "/api/v1/fmea/rows/row-1/review-context",
        headers={"Authorization": "Bearer " + "a" * 32},
    )
    assert response.status_code == 200
    assert response.headers["etag"] == '"1"'
    payload = response.json()
    assert payload["schema_version"] == "graphrag.fmea.v1"
    assert payload["resource_type"] == "review_context"
    assert payload["data"]["identity"]["item_label"] == "Fuel filter"


def test_start_suggestion_returns_202_location_without_waiting(review_client: TestClient) -> None:
    response = review_client.post(
        "/api/v1/fmea/rows/row-1/review-suggestion-runs",
        headers={
            "Authorization": "Bearer " + "a" * 32,
            "If-Match": '"1"',
            "Idempotency-Key": "f2308024-49d5-49ea-93ee-fcb95739d937",
        },
        json={"review_policy": "default", "focus_fields": ["controls"]},
    )
    assert response.status_code == 202
    assert response.headers["location"].endswith(response.json()["data"]["run_id"])


def test_decision_requires_preconditions_and_maps_stale_to_problem_json(review_client: TestClient) -> None:
    missing = review_client.post(
        "/api/v1/fmea/rows/row-1/review-decisions",
        headers={"Authorization": "Bearer " + "a" * 32},
        json=valid_accept_body(),
    )
    assert missing.status_code == 428
    assert missing.headers["content-type"].startswith("application/problem+json")
    stale = review_client.post(
        "/api/v1/fmea/rows/row-1/review-decisions",
        headers=write_headers(version=2),
        json=valid_accept_body(),
    )
    assert stale.status_code == 412
    assert stale.json()["code"] == "FMEA_VERSION_CONFLICT"


def test_decision_exact_replay_returns_original_response_with_old_if_match(review_client: TestClient) -> None:
    first = review_client.post(
        "/api/v1/fmea/rows/row-1/review-decisions",
        headers=write_headers(version=1),
        json=valid_accept_body(),
    )
    replay = review_client.post(
        "/api/v1/fmea/rows/row-1/review-decisions",
        headers=write_headers(version=1),
        json=valid_accept_body(),
    )
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert replay.headers["etag"] == '"2"'
