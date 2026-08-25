from __future__ import annotations

import asyncio
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
from chroma_rag_poc.routes_fmea_review_v1 import (  # noqa: E402
    FMEA_BODY_LIMIT,
    FmeaRequestBodyLimitMiddleware,
)
from fmea_review_fixtures import (  # noqa: E402
    FakeReviewSuggestionGenerator,
    InlineReviewExecutor,
    valid_accept_body,
)

from fmea_infrastructure.composition import build_workspace_review_runtime  # noqa: E402


def write_headers(version: int, idempotency_key: str = "f2308024-49d5-49ea-93ee-fcb95739d937") -> dict[str, str]:
    return {
        "Authorization": "Bearer " + "a" * 32,
        "If-Match": f'"{version}"',
        "Idempotency-Key": idempotency_key,
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
    generator = FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest)
    executor = InlineReviewExecutor()
    runtime = build_workspace_review_runtime(
        workspace,
        generator=generator,
        executor=executor,
    )
    runtime.repository.save_review_candidate_bundle(fixture_review_bundle, fixture_system_actor)
    app: FastAPI = create_app(review_runtime_factory=lambda _workspace: runtime)
    app.state.test_review_runtime = runtime
    app.state.test_review_generator = generator
    app.state.test_review_executor = executor
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


@pytest.mark.parametrize(
    ("headers", "expected_status", "expected_code"),
    (
        ({"Authorization": "Basic abc"}, 401, "FMEA_AUTH_REQUIRED"),
        ({"Authorization": "Bearer"}, 401, "FMEA_AUTH_REQUIRED"),
        ({**write_headers(1), "If-Match": "1"}, 400, "FMEA_REVIEW_REQUEST_INVALID"),
        ({**write_headers(1), "If-Match": '"01"'}, 400, "FMEA_REVIEW_REQUEST_INVALID"),
        ({**write_headers(1), "Idempotency-Key": "F2308024-49D5-49EA-93EE-FCB95739D937"}, 400, "FMEA_REVIEW_REQUEST_INVALID"),
    ),
)
def test_malformed_auth_and_write_preconditions_are_mapped(
    review_client: TestClient,
    headers: dict[str, str],
    expected_status: int,
    expected_code: str,
) -> None:
    response = review_client.post(
        "/api/v1/fmea/rows/row-1/review-suggestion-runs",
        headers=headers,
        json={"review_policy": "default", "focus_fields": []},
    )
    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code


@pytest.mark.parametrize(
    ("body_update", "expected_code"),
    (
        ({"action": "not-an-action"}, "FMEA_REVIEW_ACTION_INVALID"),
        (
            {
                "action": "modify_and_accept",
                "edits": [
                    {
                        "target_field": "controls",
                        "operation": "not-replace",
                        "value": "updated",
                        "claim_status": "known",
                        "support_status": "supported",
                        "evidence_ids": [],
                        "reason": "updated from evidence",
                    }
                ],
            },
            "FMEA_REVIEW_FIELD_INVALID",
        ),
        (
            {
                "action": "modify_and_accept",
                "edits": [
                    {
                        "target_field": "not-an-editable-field",
                        "operation": "replace",
                        "value": "updated",
                        "claim_status": "known",
                        "support_status": "supported",
                        "evidence_ids": [],
                        "reason": "updated from evidence",
                    }
                ],
            },
            "FMEA_REVIEW_FIELD_INVALID",
        ),
        (
            {
                "action": "modify_and_accept",
                "edits": [
                    {
                        "target_field": "controls",
                        "operation": "replace",
                        "value": "updated",
                        "claim_status": "not-a-claim-status",
                        "support_status": "supported",
                        "evidence_ids": [],
                        "reason": "updated from evidence",
                    }
                ],
            },
            "FMEA_REVIEW_FIELD_INVALID",
        ),
        (
            {
                "action": "modify_and_accept",
                "edits": [
                    {
                        "target_field": "controls",
                        "operation": "replace",
                        "value": "updated",
                        "claim_status": "known",
                        "support_status": "not-a-support-status",
                        "evidence_ids": [],
                        "reason": "updated from evidence",
                    }
                ],
            },
            "FMEA_REVIEW_FIELD_INVALID",
        ),
        (
            {
                "action": "request_evidence",
                "evidence_requests": [
                    {
                        "target_field": "controls",
                        "question": "Which source supports this control?",
                        "preferred_source_types": [],
                        "priority": "not-a-priority",
                    }
                ],
            },
            "FMEA_EVIDENCE_INVALID",
        ),
        (
            {
                "unresolved_acknowledgements": [
                    {"target_field": "controls", "claim_status": "not-a-claim-status", "reason": "acknowledged"}
                ],
            },
            "FMEA_UNRESOLVED_ACK_REQUIRED",
        ),
    ),
)
def test_invalid_enum_fields_map_to_stable_problem_codes(
    review_client: TestClient,
    body_update: dict[str, object],
    expected_code: str,
) -> None:
    body = valid_accept_body()
    body.update(body_update)
    response = review_client.post(
        "/api/v1/fmea/rows/row-1/review-decisions",
        headers=write_headers(1),
        json=body,
    )
    assert response.status_code == 422
    assert response.json()["code"] == expected_code


def test_unknown_deep_request_shape_remains_generic_invalid(review_client: TestClient) -> None:
    body = valid_accept_body()
    body["edits"] = [{"private": "must not be accepted"}]
    response = review_client.post(
        "/api/v1/fmea/rows/row-1/review-decisions",
        headers=write_headers(1),
        json=body,
    )
    assert response.status_code == 400
    assert response.json()["code"] == "FMEA_REVIEW_REQUEST_INVALID"


def test_history_uses_page_service_and_keeps_history_bounded(review_client: TestClient) -> None:
    first = review_client.post(
        "/api/v1/fmea/rows/row-1/review-suggestion-runs",
        headers=write_headers(1, "f2308024-49d5-49ea-93ee-fcb95739d938"),
        json={"review_policy": "default", "focus_fields": []},
    )
    second = review_client.post(
        "/api/v1/fmea/rows/row-1/review-suggestion-runs",
        headers=write_headers(1, "f2308024-49d5-49ea-93ee-fcb95739d939"),
        json={"review_policy": "default", "focus_fields": []},
    )
    assert first.status_code == second.status_code == 202
    runtime = review_client.app.state.test_review_runtime
    runtime.service.get_context = lambda *_args, **_kwargs: pytest.fail("history must not build full context")
    runtime.service.get_suggestion_run = lambda *_args, **_kwargs: pytest.fail("history must not load a run for trace")

    page = review_client.get(
        "/api/v1/fmea/rows/row-1/review-suggestions?limit=1",
        headers={"Authorization": "Bearer " + "a" * 32},
    )
    assert page.status_code == 200
    assert len(page.json()["data"]["items"]) == 1
    assert page.json()["data"]["next_cursor"]
    forged = review_client.get(
        "/api/v1/fmea/rows/row-1/review-suggestions?limit=1&cursor=" + page.json()["data"]["next_cursor"][:-1] + "x",
        headers={"Authorization": "Bearer " + "a" * 32},
    )
    assert forged.status_code == 400
    assert forged.json()["code"] == "FMEA_REVIEW_REQUEST_INVALID"


def test_failed_run_get_is_200_and_does_not_expose_provider_failure(review_client: TestClient) -> None:
    def fail_generate(_request: Any) -> Any:
        raise RuntimeError("provider secret must not be returned")  # noqa: TRY003

    review_client.app.state.test_review_generator.generate = fail_generate
    started = review_client.post(
        "/api/v1/fmea/rows/row-1/review-suggestion-runs",
        headers=write_headers(1, "f2308024-49d5-49ea-93ee-fcb95739d940"),
        json={"review_policy": "default", "focus_fields": []},
    )
    run_id = started.json()["data"]["run_id"]
    fetched = review_client.get(
        f"/api/v1/fmea/review-suggestion-runs/{run_id}",
        headers={"Authorization": "Bearer " + "a" * 32},
    )
    assert fetched.status_code == 200
    assert fetched.json()["data"]["status"] == "failed"
    assert fetched.json()["data"]["error_code"] == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    assert "provider secret" not in fetched.text


def test_chunked_body_guard_counts_bytes_and_replays_accepted_messages() -> None:
    async def exercise(messages: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        seen: list[dict[str, object]] = []
        sent: list[dict[str, object]] = []
        remaining = list(messages)

        async def receive() -> dict[str, object]:
            return remaining.pop(0)

        async def send(message: dict[str, object]) -> None:
            sent.append(message)

        async def app(_scope: dict[str, object], downstream: Any, _send: Any) -> None:
            while True:
                message = await downstream()
                seen.append(message)
                if not message.get("more_body", False):
                    return

        await FmeaRequestBodyLimitMiddleware(app)(
            {"type": "http", "method": "POST", "path": "/api/v1/fmea/rows/row-1/review-decisions"},
            receive,
            send,
        )
        return seen, sent

    accepted_messages = [
        {"type": "http.request", "body": b"first", "more_body": True},
        {"type": "http.request", "body": b"second", "more_body": False},
    ]
    seen, sent = asyncio.run(exercise(accepted_messages))
    assert seen == accepted_messages
    assert sent == []

    oversized = [
        {"type": "http.request", "body": b"x" * FMEA_BODY_LIMIT, "more_body": True},
        {"type": "http.request", "body": b"y", "more_body": False},
    ]
    seen, sent = asyncio.run(exercise(oversized))
    assert seen == []
    assert sent[0]["status"] == 400


@pytest.mark.parametrize(("auth_mode", "expected_status"), (("disabled", 401), ("invalid", 503)))
def test_invalid_or_disabled_auth_keeps_query_health_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auth_mode: str,
    expected_status: int,
) -> None:
    for name in (
        "RAG_WORKSPACE_CONFIG",
        "FMEA_REVIEW_TOKEN",
        "FMEA_REVIEW_ACTOR_ID",
        "FMEA_REVIEW_WORKSPACE_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FMEA_LOCAL_AUTH_ENABLED", "false" if auth_mode == "disabled" else "true")
    if auth_mode == "invalid":
        monkeypatch.setenv("FMEA_REVIEW_TOKEN", "short")
    app = create_app(persist_dir=tmp_path / "persist", upload_dir=tmp_path / "uploads")
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        health = client.get("/api/health")
        review = client.get(
            "/api/v1/fmea/rows/row-1/review-context",
            headers={"Authorization": "Bearer " + "a" * 32},
        )
    assert health.status_code == 200
    assert review.status_code == expected_status
    assert review.json()["code"] == (
        "FMEA_AUTH_REQUIRED" if auth_mode == "disabled" else "FMEA_AUTH_CONFIGURATION_INVALID"
    )


def test_shutdown_closes_cached_review_executor(review_client: TestClient) -> None:
    review_client.get(
        "/api/v1/fmea/rows/row-1/review-context",
        headers={"Authorization": "Bearer " + "a" * 32},
    )

    async def run_shutdown_handlers() -> None:
        for handler in review_client.app.router.on_shutdown:
            await handler()

    asyncio.run(run_shutdown_handlers())
    assert review_client.app.state.test_review_executor.closed is True
