from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest

from core_domain.fmea.states import ActorType, RunStatus
from fmea_application.propagation_service import PropagationError, PropagationReviewResult, PropagationRun
from fmea_application.review_contracts import ActorContext
from scripts import fmea_skill
from tests.fmea_propagation_fixtures import _graph

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


@dataclass
class FakePropagationService:
    graph: Any = field(default_factory=lambda: _graph("ws-1"))
    calls: list[str] = field(default_factory=list)
    start_commands: list[Any] = field(default_factory=list)
    start_error_code: str | None = None

    def __post_init__(self) -> None:
        self.run = PropagationRun(
            run_id="run-1",
            workspace_id="ws-1",
            analysis_id=self.graph.analysis_id,
            status=RunStatus.SUCCEEDED,
            graph=self.graph,
            error_code=None,
            error_message=None,
            assistance_suggestion_ids=("suggestion-1",),
            created_at="2026-08-28T00:00:00Z",
            updated_at="2026-08-28T00:00:01Z",
        )

    def start_analysis(self, command: Any, actor: ActorContext) -> PropagationRun:
        self.calls.append("start_analysis")
        self.start_commands.append(command)
        assert command.analysis_id == "analysis-1"
        if self.start_error_code is not None:
            raise PropagationError(self.start_error_code, "private propagation validation detail")
        return self.run

    def get_run(self, run_id: str, actor: ActorContext) -> PropagationRun:
        self.calls.append("get_run")
        return self.run

    def get_graph(self, graph_revision_id: str, actor: ActorContext) -> Any:
        self.calls.append("get_graph")
        return self.graph

    def confirm_graph(self, command: Any, actor: ActorContext) -> PropagationReviewResult:
        self.calls.append("confirm_graph")
        return PropagationReviewResult(
            graph=self.graph,
            decision_id="decision-1",
            audit_event_id="audit-1",
            outbox_event_id="outbox-1",
        )


@dataclass(frozen=True)
class FakeCliRuntime:
    propagation_service: FakePropagationService
    propagation_start_defaults: dict[str, object] = field(default_factory=lambda: dict(SERVER_DEFAULTS))
    actor: ActorContext = field(
        default_factory=lambda: ActorContext(
            "reviewer-1", ActorType.HUMAN, frozenset({"propagation_reviewer"}), "ws-1"
        )
    )
    close_calls: list[int] = field(default_factory=list)

    def close(self) -> None:
        self.close_calls.append(1)


def _review_request() -> dict[str, object]:
    graph = _graph("ws-1")
    return {
        "graph_revision_id": graph.graph_revision_id,
        "expected_graph_record_version": graph.record_version,
        "edge_decisions": [
            {"edge_id": edge.edge_id, "action": "accept", "reason": "accepted by reviewer"}
            for edge in graph.edges
        ],
        "acknowledgements": [],
        "idempotency_key": "00000000-0000-4000-8000-000000000502",
    }


def test_propagation_start_status_and_show_emit_single_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = FakePropagationService()
    runtime = FakeCliRuntime(service)
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)

    assert fmea_skill.main(
        [
            "propagation",
            "start",
            "--analysis-id",
            "analysis-1",
            "--record-version",
            "1",
            "--idempotency-key",
            "00000000-0000-4000-8000-000000000501",
        ]
    ) == 0
    start_payload = json.loads(capsys.readouterr().out)
    assert start_payload["resource_type"] == "propagation_run"
    assert start_payload["data"]["run_id"] == "run-1"
    assert service.start_commands[0].topology_id == SERVER_DEFAULTS["topology_id"]

    assert fmea_skill.main(["propagation", "status", "--run-id", "run-1"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["data"] == start_payload["data"]

    assert fmea_skill.main(["propagation", "show", "--graph-id", "graph-1"]) == 0
    show_payload = json.loads(capsys.readouterr().out)
    assert show_payload["resource_type"] == "propagation_graph"
    assert show_payload["data"]["graph_revision_id"] == "graph-1"
    assert service.calls == ["start_analysis", "get_run", "get_graph"]
    assert runtime.close_calls == [1, 1, 1]


def test_cli_propagation_start_failed_run_returns_safe_nonzero_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = FakePropagationService()
    service.run = replace(
        service.run,
        status=RunStatus.FAILED,
        graph=None,
        error_code="FMEA_PROPAGATION_EDGE_INVALID",
        error_message="raw provider traceback must stay private",
    )
    runtime = FakeCliRuntime(service)
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)

    exit_code = fmea_skill.main(
        [
            "propagation",
            "start",
            "--analysis-id",
            "analysis-1",
            "--record-version",
            "1",
            "--idempotency-key",
            "00000000-0000-4000-8000-000000000501",
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code != 0
    assert payload["resource_type"] == "propagation_run"
    assert payload["error"]["code"] == "FMEA_PROPAGATION_EDGE_INVALID"
    assert "raw provider traceback" not in output
    assert "error_message" not in payload["data"]
    assert runtime.close_calls == [1]


def test_cli_propagation_status_failed_run_returns_safe_nonzero_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = FakePropagationService()
    service.run = replace(
        service.run,
        status=RunStatus.FAILED,
        graph=None,
        error_code="FMEA_PROPAGATION_GRAPH_INVALID",
        error_message="raw database detail must stay private",
    )
    runtime = FakeCliRuntime(service)
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)

    exit_code = fmea_skill.main(["propagation", "status", "--run-id", "run-1"])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code != 0
    assert payload["resource_type"] == "propagation_run"
    assert payload["error"]["code"] == "FMEA_PROPAGATION_GRAPH_INVALID"
    assert "raw database detail" not in output
    assert "error_message" not in payload["data"]
    assert runtime.close_calls == [1]


@pytest.mark.parametrize(
    "error_code",
    [
        "FMEA_PROPAGATION_ENDPOINT_INVALID",
        "FMEA_PROPAGATION_RELATION_INVALID",
        "FMEA_PROPAGATION_EVIDENCE_INVALID",
        "FMEA_PROPAGATION_SOURCE_INVALID",
    ],
)
def test_propagation_validation_error_code_is_preserved_by_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error_code: str,
) -> None:
    service = FakePropagationService(start_error_code=error_code)
    runtime = FakeCliRuntime(service)
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)

    exit_code = fmea_skill.main(
        [
            "propagation",
            "start",
            "--analysis-id",
            "analysis-1",
            "--record-version",
            "1",
            "--idempotency-key",
            "00000000-0000-4000-8000-000000000501",
        ]
    )
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 2
    assert payload["error"]["code"] == error_code
    assert "private propagation validation detail" not in output
    assert runtime.close_calls == [1]


def test_cli_start_rejects_incomplete_server_defaults_as_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = FakePropagationService()
    defaults = dict(SERVER_DEFAULTS)
    defaults["source_row_ids"] = ()
    defaults["evidence_pack_id"] = ""
    runtime = FakeCliRuntime(service, propagation_start_defaults=defaults)
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)

    exit_code = fmea_skill.main(
        [
            "propagation",
            "start",
            "--analysis-id",
            "analysis-1",
            "--record-version",
            "1",
            "--idempotency-key",
            "00000000-0000-4000-8000-000000000501",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 3
    assert payload["error"]["code"] == "FMEA_WORKSPACE_CONFIGURATION_INVALID"
    assert service.calls == []
    assert runtime.close_calls == [1]


def test_cli_graph_show_data_matches_rest_projection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = FakePropagationService()
    runtime = FakeCliRuntime(service)
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)
    assert fmea_skill.main(["propagation", "show", "--graph-id", "graph-1"]) == 0
    cli_data = json.loads(capsys.readouterr().out)["data"]

    from chroma_rag_poc.routes_fmea_propagation_v1 import graph_data

    assert cli_data == graph_data(service.graph).model_dump(mode="json")


def test_cli_review_requires_explicit_human_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_file = tmp_path / "review.json"
    request_file.write_text(json.dumps(_review_request()), encoding="utf-8")
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: pytest.fail("must not build runtime"))

    exit_code = fmea_skill.main(["propagation", "review", "--request-file", str(request_file)])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["error"]["code"] == "FMEA_REVIEW_CONFIRMATION_REQUIRED"


def test_cli_review_calls_service_after_confirmation_and_closes_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_file = tmp_path / "review.json"
    request_file.write_text(json.dumps(_review_request()), encoding="utf-8")
    service = FakePropagationService()
    runtime = FakeCliRuntime(service)
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)

    exit_code = fmea_skill.main(
        [
            "propagation",
            "review",
            "--request-file",
            str(request_file),
            "--confirm-human-propagation-review",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["resource_type"] == "propagation_review"
    assert service.calls == ["confirm_graph"]
    assert runtime.close_calls == [1]


def test_cli_rejects_secret_or_override_arguments_without_echoing_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = "TOPSECRET-propagation-token"
    exit_code = fmea_skill.main(["propagation", "show", "--graph-id", "graph-1", "--token", marker])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert marker not in captured.out + captured.err
    assert captured.err == ""
