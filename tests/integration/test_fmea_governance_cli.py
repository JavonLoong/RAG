from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from chroma_rag_poc.api import create_app
from chroma_rag_poc.fmea_governance_contracts import derive_governance_cursor_secret
from fastapi.testclient import TestClient

from core_domain.fmea.states import ActorType
from fmea_application.governance_contracts import (
    ApprovalCommand,
    ApprovalRejectionCommand,
    AssembleRevisionCommand,
    PublishCommand,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    WithdrawApprovalCommand,
    WithdrawPublicationCommand,
)
from fmea_application.governance_service import GovernanceServiceError
from fmea_application.review_contracts import ActorContext
from scripts import fmea_skill

REVISION_HASH = "sha256:" + "c" * 64
UUID1 = "00000000-0000-4000-8000-0000000005ab"
TOKEN = "a" * 32


class FakeAuth:
    def authenticate(self, bearer_token: str, remote_host: str | None) -> ActorContext:
        assert bearer_token == TOKEN
        assert remote_host in {"127.0.0.1", "testclient"}
        return ActorContext(
            "human-1",
            ActorType.HUMAN,
            frozenset({"reviewer", "approver", "publisher"}),
            "ws-1",
        )


def _revision() -> SimpleNamespace:
    return SimpleNamespace(
        revision_id="revision-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        analysis_record_version=3,
        analysis_hash="sha256:" + "a" * 64,
        parent_revision_id=None,
        parent_revision_hash=None,
        row_versions=(),
        risk_versions=(),
        propagation_graph_revision_id=None,
        propagation_graph_hash=None,
        evidence_pack_hashes=(),
        retrieval_provenance=SimpleNamespace(
            requested_profile="default",
            resolved_profile="default",
            evidence_types=(),
            source_counts=(),
            warnings=(),
        ),
        domain_pack_identity=("domain", "1.0.0", "sha256:" + "b" * 64),
        template_identities=(),
        scoring_rule_identities=(),
        propagation_rule_identity=None,
        unresolved_items=(),
        revision_hash=REVISION_HASH,
        created_at="2026-08-30T00:00:00Z",
    )


def _snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        schema_version="graphrag.fmea.normalized-snapshot.v1",
        snapshot_id="snapshot-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        revision_id="revision-1",
        revision_hash=REVISION_HASH,
        publication_id="publication-1",
        manifest_id="manifest-1",
        rows=(),
        risk_records=(),
        propagation=None,
        evidence_summary=(),
        decision_summary=(),
        version_manifest={},
        unresolved_items=(),
        audit_summary={},
        row_count=0,
        snapshot_hash="sha256:" + "d" * 64,
        created_at="2026-08-30T00:00:00Z",
    )


def _publication() -> SimpleNamespace:
    return SimpleNamespace(
        publication_id="publication-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        revision_id="revision-1",
        revision_hash=REVISION_HASH,
        approval_id="approval-1",
        manifest_id="manifest-1",
        manifest_hash="sha256:" + "e" * 64,
        snapshot_id="snapshot-1",
        snapshot_hash="sha256:" + "d" * 64,
        audit_chain_head="sha256:" + "f" * 64,
        publisher_actor_id="human-1",
        record_version=1,
        created_at="2026-08-30T00:00:00Z",
    )


def _event() -> SimpleNamespace:
    return SimpleNamespace(
        event_id="event-1",
        occurred_at_server="2026-08-30T00:00:00Z",
        workspace_id="ws-1",
        actor_id="human-1",
        actor_type=ActorType.HUMAN,
        actor_roles=("approver",),
        command="fmea.approval.submit",
        reason="submitted",
        analysis_id="analysis-1",
        row_id="revision-1",
        decision_id=None,
        expected_record_version=11,
        applied_record_version=1,
        after_hash=REVISION_HASH,
    )


def _mutation(**identities: str) -> SimpleNamespace:
    return SimpleNamespace(
        replayed=False,
        audit_event_id="audit-1",
        outbox_event_id="outbox-1",
        record_version=1,
        **identities,
    )


class FakeGovernanceService:
    def __init__(self) -> None:
        self.snapshot = _snapshot()
        self.revision = _revision()
        self.calls: list[str] = []
        self.commands: list[object] = []
        self.history_queries: list[object] = []

    def get_snapshot(self, publication_id: str, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("get_snapshot")
        assert publication_id == "publication-1"
        assert actor.workspace_id == "ws-1"
        return self.snapshot

    def get_publication(self, publication_id: str, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("get_publication")
        assert publication_id == "publication-1"
        assert actor.workspace_id == "ws-1"
        return SimpleNamespace(
            publication=_publication(), effective_status="published", withdrawal=None, supersession=None
        )

    def withdraw_publication(self, command: WithdrawPublicationCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("withdraw_publication")
        self.commands.append(command)
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(withdrawal_id="withdrawal-1", publication_id="publication-1")

    def supersede(self, command: SupersedePublicationCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("supersede")
        self.commands.append(command)
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(
            supersession_id="supersession-1",
            old_publication_id="publication-1",
            new_publication_id="publication-2",
        )

    def list_approval_events(self, query: object, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("list_approval_events")
        self.history_queries.append(query)
        assert actor.workspace_id == "ws-1"
        return SimpleNamespace(events=(_event(),), next_cursor="internal|approval-event-1")

    def list_publication_events(self, query: object, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("list_publication_events")
        self.history_queries.append(query)
        assert actor.workspace_id == "ws-1"
        return SimpleNamespace(events=(_event(),), next_cursor="internal|publication-event-1")

    def get_revision_record(self, revision_id: str, actor: ActorContext) -> tuple[SimpleNamespace, int]:
        self.calls.append("get_revision_record")
        assert revision_id == "revision-1"
        return self.revision, 11

    def assemble(self, command: AssembleRevisionCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("assemble")
        self.commands.append(command)
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(revision_id="revision-1")

    def readiness(self, revision_id: str, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("readiness")
        assert revision_id == "revision-1"
        assert actor.workspace_id == "ws-1"
        return SimpleNamespace(
            revision_id="revision-1",
            workspace_id="ws-1",
            analysis_id="analysis-1",
            revision_hash=REVISION_HASH,
            target_record_version=3,
            evidence_pack_ids=(),
            ready=True,
            issues=(),
            blocking_codes=(),
            deterministic=True,
        )

    def submit_for_approval(self, command: SubmitApprovalCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("submit_for_approval")
        self.commands.append(command)
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(submission_id="submission-1")

    def approve(self, command: ApprovalCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("approve")
        self.commands.append(command)
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(approval_id="approval-1")

    def reject(self, command: ApprovalRejectionCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("reject")
        self.commands.append(command)
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(approval_id="approval-1")

    def withdraw_approval(self, command: WithdrawApprovalCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("withdraw_approval")
        self.commands.append(command)
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(withdrawal_id="withdrawal-1", approval_id="approval-1")

    def publish(self, command: object, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("publish")
        self.commands.append(command)
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(publication_id="publication-1", manifest_id="manifest-1", snapshot_id="snapshot-1")


def _runtime(service: FakeGovernanceService, *, cursor_secret: bytes | None = b"s" * 32) -> SimpleNamespace:
    human = ActorContext("human-1", ActorType.HUMAN, frozenset({"reviewer", "approver", "publisher"}), "ws-1")
    model = ActorContext("fmea-model-assistant", ActorType.MODEL, frozenset(), "ws-1")
    assistance = SimpleNamespace(
        suggest_readiness_checklist=lambda report, actor: SimpleNamespace(
            suggestion_id="suggestion-1",
            run_id="run-1",
            target_type="fmea_revision_readiness",
            target_id=report.revision_id,
            target_record_version=report.target_record_version,
            ready=report.ready,
            blocking_codes=report.blocking_codes,
            checklist=(),
            applied=False,
            trace_id="trace-1",
            created_at="2026-08-30T00:00:00Z",
        )
    )
    return SimpleNamespace(
        governance_service=service,
        governance_assistance_service=assistance,
        actor=human,
        model_actor=model,
        governance_cursor_secret=cursor_secret,
        close=lambda: None,
    )


def _configure_real_cli_runtime(monkeypatch: pytest.MonkeyPatch, service: FakeGovernanceService) -> None:
    import core_domain.fmea.states as states
    import fmea_application.review_contracts as review_contracts
    import fmea_infrastructure.composition as composition

    workspace = SimpleNamespace(workspace_id="ws-1")
    actor = ActorContext("human-1", ActorType.HUMAN, frozenset({"reviewer", "approver", "publisher"}), "ws-1")
    registry = SimpleNamespace(get=lambda workspace_id: workspace)
    auth = SimpleNamespace(authenticate=lambda _token, _remote: actor)
    dependencies = SimpleNamespace(
        workspace_registry=SimpleNamespace(WorkspaceRegistry=SimpleNamespace(from_env=lambda: registry)),
        local_auth=SimpleNamespace(LocalReviewAuthProvider=SimpleNamespace(from_env=lambda: auth)),
        review_contracts=review_contracts,
        states=states,
    )
    review_runtime = SimpleNamespace(
        service=object(),
        executor=SimpleNamespace(close_nonblocking=lambda: None),
    )
    risk_runtime = SimpleNamespace(
        analysis_service=object(), decision_service=object(), risk_service=object(), risk_repository=object()
    )
    governance_runtime = SimpleNamespace(
        service=service,
        assistance_service=_runtime(service).governance_assistance_service,
    )
    monkeypatch.setattr(fmea_skill, "_load_project_dependencies", lambda: dependencies)
    monkeypatch.setattr(fmea_skill, "build_workspace_review_runtime", lambda _workspace: review_runtime)
    monkeypatch.setattr(composition, "build_default_workspace_risk_runtime", lambda _workspace, **_kwargs: risk_runtime)
    monkeypatch.setattr(composition, "propagation_server_environment_present", lambda: False)
    monkeypatch.setattr(
        composition,
        "build_default_workspace_governance_runtime",
        lambda _workspace: governance_runtime,
    )


def test_cli_snapshot_emits_one_bounded_json_object(capsys, monkeypatch) -> None:
    service = FakeGovernanceService()
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service))

    exit_code = fmea_skill.main(["publication", "snapshot", "--publication-id", "publication-1"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["schema_version"] == "graphrag.fmea.v1"
    assert payload["resource_type"] == "publication_snapshot"
    assert payload["data"]["publication_id"] == "publication-1"
    assert service.calls == ["get_snapshot"]


def test_cli_snapshot_budgets_the_final_pretty_stdout_bytes_without_partial_payload(capsys, monkeypatch) -> None:
    service = FakeGovernanceService()
    service.snapshot.rows = tuple({"domain_note": "x" * 1285} for _ in range(200))
    service.snapshot.row_count = 200
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service))

    compact_exit = fmea_skill.main(["publication", "snapshot", "--publication-id", "publication-1"])
    compact = capsys.readouterr().out
    assert compact_exit == 0
    assert len(compact.encode("utf-8")) < 256 * 1024

    pretty_exit = fmea_skill.main([
        "publication",
        "snapshot",
        "--publication-id",
        "publication-1",
        "--pretty",
    ])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert pretty_exit == 7
    assert captured.err == ""
    assert len(captured.out.encode("utf-8")) <= 256 * 1024
    assert payload["resource_type"] == "error"
    assert payload["error"]["code"] == "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE"
    assert "domain_note" not in captured.out


def test_cli_snapshot_projection_rejects_nested_private_output_as_single_safe_json(capsys, monkeypatch) -> None:
    service = FakeGovernanceService()
    service.snapshot.rows = ({"domain_extension": {"provider_output": "sensitive-provider-result"}},)
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service))

    exit_code = fmea_skill.main(["publication", "snapshot", "--publication-id", "publication-1"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 7
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["error"]["code"] == "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE"
    assert "sensitive-provider-result" not in captured.out


def test_cli_snapshot_data_matches_shared_rest_projection(capsys, monkeypatch) -> None:
    from chroma_rag_poc.fmea_governance_contracts import snapshot_data

    service = FakeGovernanceService()
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service))
    assert fmea_skill.main(["publication", "snapshot", "--publication-id", "publication-1"]) == 0
    cli_data = json.loads(capsys.readouterr().out)["data"]
    assert cli_data == snapshot_data(service.snapshot).model_dump(mode="json")


def test_rest_and_cli_snapshot_history_parity_and_cursor_interoperability(capsys, monkeypatch) -> None:
    service = FakeGovernanceService()
    cursor_configuration = "task5-shared-cross-transport-cursor-secret"
    monkeypatch.setenv("FMEA_GOVERNANCE_CURSOR_SECRET", cursor_configuration)
    _configure_real_cli_runtime(monkeypatch, service)
    cli_runtime = fmea_skill.build_cli_runtime()
    rest_runtime = SimpleNamespace(
        service=service,
        assistance_service=cli_runtime.governance_assistance_service,
        repository=object(),
    )
    app = create_app(review_auth_provider=FakeAuth())
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: SimpleNamespace(workspace_id=workspace_id))
    app.state.governance_runtime_factory = lambda _workspace: rest_runtime
    client = TestClient(app, client=("127.0.0.1", 50000))
    cli_runtime.close()

    with client:
        rest_snapshot = client.get(
            "/api/v1/fmea/publications/publication-1/snapshot",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert fmea_skill.main(["publication", "snapshot", "--publication-id", "publication-1"]) == 0
        cli_snapshot = json.loads(capsys.readouterr().out)
        rest_history = client.get(
            "/api/v1/fmea/revisions/revision-1/approval-events",
            headers={"Authorization": f"Bearer {TOKEN}"},
            params={"limit": 1},
        )
        rest_cursor = rest_history.json()["data"]["next_cursor"]
        assert (
            fmea_skill.main([
                "approval",
                "history",
                "--revision-id",
                "revision-1",
                "--limit",
                "1",
                "--cursor",
                rest_cursor,
            ])
            == 0
        )
        cli_history = json.loads(capsys.readouterr().out)
        cli_cursor = cli_history["data"]["next_cursor"]
        rest_from_cli_cursor = client.get(
            "/api/v1/fmea/revisions/revision-1/approval-events",
            headers={"Authorization": f"Bearer {TOKEN}"},
            params={"limit": 1, "cursor": cli_cursor},
        )

    assert rest_snapshot.status_code == 200
    assert rest_snapshot.json()["data"] == cli_snapshot["data"]
    assert rest_history.status_code == rest_from_cli_cursor.status_code == 200
    assert rest_history.json()["data"]["items"] == cli_history["data"]["items"]
    assert service.history_queries[-2].cursor == service.history_queries[-1].cursor == "internal|approval-event-1"


def test_cli_forwards_expected_version_to_application_command(capsys, monkeypatch) -> None:
    from fmea_application.governance_contracts import PublicationResult

    service = FakeGovernanceService()

    def publish(command: object, actor: ActorContext) -> PublicationResult:
        service.commands.append(command)
        assert actor.actor_type is ActorType.HUMAN
        return PublicationResult("publication-1", "manifest-1", "snapshot-1", 1, "audit-1", "outbox-1")

    service.publish = publish  # type: ignore[attr-defined]
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service))
    exit_code = fmea_skill.main([
        "publication",
        "publish",
        "--revision-id",
        "revision-1",
        "--revision-hash",
        REVISION_HASH,
        "--approval-id",
        "approval-1",
        "--record-version",
        "11",
        "--idempotency-key",
        UUID1,
        "--confirm-publication",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["resource_type"] == "publication"
    assert service.commands[0].expected_revision_version == 11
    assert service.commands[0].idempotency_key == UUID1


def test_cli_authority_confirmation_happens_before_runtime_creation(capsys, monkeypatch) -> None:
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: (_ for _ in ()).throw(AssertionError()))

    exit_code = fmea_skill.main([
        "publication",
        "publish",
        "--revision-id",
        "revision-1",
        "--revision-hash",
        REVISION_HASH,
        "--approval-id",
        "approval-1",
        "--record-version",
        "11",
        "--idempotency-key",
        UUID1,
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code != 0
    assert payload["error"]["code"] == "FMEA_GOVERNANCE_PUBLICATION_CONFIRMATION_REQUIRED"


def test_cli_rejects_provider_or_snapshot_path_overrides_without_echoing_input(capsys) -> None:
    exit_code = fmea_skill.main([
        "publication",
        "show",
        "--publication-id",
        "publication-1",
        "--snapshot-path",
        "attacker.json",
    ])
    output = capsys.readouterr()
    assert exit_code != 0
    assert "attacker.json" not in output.out + output.err
    assert output.err == ""
    assert json.loads(output.out)["error"]["code"] == "FMEA_GOVERNANCE_REQUEST_INVALID"


@pytest.mark.parametrize(
    "argv",
    [
        [
            "approval",
            "approve",
            "--submission-id",
            "submission-1",
            "--revision-id",
            "revision-1",
            "--revision-hash",
            REVISION_HASH,
            "--record-version",
            "11",
            "--reason",
            "x" * 501,
            "--idempotency-key",
            UUID1,
            "--confirm-human-approval",
        ],
        [
            "publication",
            "publish",
            "--revision-id",
            "revision-1",
            "--revision-hash",
            REVISION_HASH,
            "--approval-id",
            "a" * 257,
            "--record-version",
            "11",
            "--idempotency-key",
            UUID1,
            "--confirm-publication",
        ],
    ],
)
def test_cli_governance_commands_enforce_shared_id_and_reason_bounds(argv: list[str], capsys, monkeypatch) -> None:
    service = FakeGovernanceService()
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service))

    exit_code = fmea_skill.main(argv)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["error"]["code"] == "FMEA_GOVERNANCE_REQUEST_INVALID"
    assert service.commands == []


@pytest.mark.parametrize(
    ("argv", "service_call", "command_type", "resource_type"),
    [
        (
            [
                "revision",
                "assemble",
                "--analysis-id",
                "analysis-1",
                "--record-version",
                "3",
                "--idempotency-key",
                UUID1,
                "--parent-revision-id",
                "parent-1",
                "--parent-revision-hash",
                REVISION_HASH,
                "--confirm-human-approval",
            ],
            "assemble",
            AssembleRevisionCommand,
            "revision",
        ),
        (["revision", "show", "--revision-id", "revision-1"], "get_revision_record", None, "revision"),
        (["revision", "readiness", "--revision-id", "revision-1"], "readiness", None, "revision_readiness"),
        (
            ["approval", "readiness-suggest", "--revision-id", "revision-1"],
            "readiness",
            None,
            "readiness_suggestion",
        ),
        (
            [
                "approval",
                "submit",
                "--revision-id",
                "revision-1",
                "--revision-hash",
                REVISION_HASH,
                "--record-version",
                "11",
                "--idempotency-key",
                UUID1,
                "--confirm-human-approval",
            ],
            "submit_for_approval",
            SubmitApprovalCommand,
            "approval_submission",
        ),
        (
            [
                "approval",
                "approve",
                "--submission-id",
                "submission-1",
                "--revision-id",
                "revision-1",
                "--revision-hash",
                REVISION_HASH,
                "--record-version",
                "11",
                "--reason",
                "approved",
                "--idempotency-key",
                UUID1,
                "--confirm-human-approval",
            ],
            "approve",
            ApprovalCommand,
            "approval",
        ),
        (
            [
                "approval",
                "reject",
                "--submission-id",
                "submission-1",
                "--revision-id",
                "revision-1",
                "--revision-hash",
                REVISION_HASH,
                "--record-version",
                "11",
                "--reason",
                "needs changes",
                "--idempotency-key",
                UUID1,
                "--confirm-human-approval",
            ],
            "reject",
            ApprovalRejectionCommand,
            "approval_rejection",
        ),
        (
            [
                "approval",
                "withdraw",
                "--approval-id",
                "approval-1",
                "--revision-hash",
                REVISION_HASH,
                "--record-version",
                "11",
                "--reason",
                "withdraw",
                "--idempotency-key",
                UUID1,
                "--confirm-approval-withdrawal",
            ],
            "withdraw_approval",
            WithdrawApprovalCommand,
            "approval_withdrawal",
        ),
        (
            ["approval", "history", "--revision-id", "revision-1", "--limit", "1"],
            "list_approval_events",
            None,
            "revision_history",
        ),
        (
            [
                "publication",
                "publish",
                "--revision-id",
                "revision-1",
                "--revision-hash",
                REVISION_HASH,
                "--approval-id",
                "approval-1",
                "--record-version",
                "11",
                "--idempotency-key",
                UUID1,
                "--confirm-publication",
            ],
            "publish",
            None,
            "publication",
        ),
        (["publication", "show", "--publication-id", "publication-1"], "get_publication", None, "publication"),
        (
            ["publication", "snapshot", "--publication-id", "publication-1"],
            "get_snapshot",
            None,
            "publication_snapshot",
        ),
        (
            [
                "publication",
                "withdraw",
                "--publication-id",
                "publication-1",
                "--record-version",
                "11",
                "--reason",
                "withdraw",
                "--idempotency-key",
                UUID1,
                "--confirm-publication-withdrawal",
            ],
            "withdraw_publication",
            WithdrawPublicationCommand,
            "publication_withdrawal",
        ),
        (
            [
                "publication",
                "supersede",
                "--publication-id",
                "publication-1",
                "--replacement-publication-id",
                "publication-2",
                "--record-version",
                "11",
                "--replacement-record-version",
                "2",
                "--reason",
                "replace",
                "--idempotency-key",
                UUID1,
                "--confirm-supersession",
            ],
            "supersede",
            SupersedePublicationCommand,
            "publication_supersession",
        ),
        (
            ["publication", "history", "--publication-id", "publication-1", "--limit", "1"],
            "list_publication_events",
            None,
            "publication_history",
        ),
    ],
)
def test_cli_dispatches_every_governance_command_to_application_service(
    capsys,
    monkeypatch,
    argv: list[str],
    service_call: str,
    command_type: type | None,
    resource_type: str,
) -> None:
    service = FakeGovernanceService()
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service))
    exit_code = fmea_skill.main(argv)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["resource_type"] == resource_type
    assert service_call in service.calls
    if command_type is not None:
        command = next(item for item in service.commands if isinstance(item, command_type))
        assert command.idempotency_key == UUID1
        if isinstance(command, AssembleRevisionCommand):
            assert command.request.analysis_id == "analysis-1"
            assert command.request.expected_analysis_version == 3
            assert command.request.parent_revision_id == "parent-1"
            assert command.request.parent_revision_hash == REVISION_HASH
        elif isinstance(command, SubmitApprovalCommand):
            assert command.revision_id == "revision-1"
            assert command.revision_hash == REVISION_HASH
            assert command.expected_revision_version == 11
        elif isinstance(command, ApprovalRejectionCommand):
            assert command.revision_id == "revision-1"
            assert command.revision_hash == REVISION_HASH
            assert command.expected_submission_version == 11
            assert command.reason == "needs changes"
        elif isinstance(command, ApprovalCommand):
            assert command.revision_id == "revision-1"
            assert command.revision_hash == REVISION_HASH
            assert command.expected_submission_version == 11
            assert command.reason == "approved"
        elif isinstance(command, WithdrawApprovalCommand):
            assert command.revision_hash == REVISION_HASH
            assert command.expected_approval_version == 11
            assert command.reason == "withdraw"
        elif isinstance(command, PublishCommand):
            assert command.revision_id == "revision-1"
            assert command.revision_hash == REVISION_HASH
            assert command.approval_id == "approval-1"
            assert command.expected_revision_version == 11
        elif isinstance(command, WithdrawPublicationCommand):
            assert command.expected_publication_version == 11
            assert command.reason == "withdraw"
        elif isinstance(command, SupersedePublicationCommand):
            assert command.replacement_publication_id == "publication-2"
            assert command.expected_publication_version == 11
            assert command.expected_replacement_version == 2
            assert command.reason == "replace"


@pytest.mark.parametrize(
    "argv",
    [
        ["revision", "assemble", "--analysis-id", "analysis-1", "--record-version", "3", "--idempotency-key", UUID1],
        [
            "approval",
            "submit",
            "--revision-id",
            "revision-1",
            "--revision-hash",
            REVISION_HASH,
            "--record-version",
            "11",
            "--idempotency-key",
            UUID1,
        ],
        [
            "approval",
            "approve",
            "--submission-id",
            "submission-1",
            "--revision-id",
            "revision-1",
            "--revision-hash",
            REVISION_HASH,
            "--record-version",
            "11",
            "--reason",
            "approved",
            "--idempotency-key",
            UUID1,
        ],
        [
            "approval",
            "reject",
            "--submission-id",
            "submission-1",
            "--revision-id",
            "revision-1",
            "--revision-hash",
            REVISION_HASH,
            "--record-version",
            "11",
            "--reason",
            "reject",
            "--idempotency-key",
            UUID1,
        ],
        [
            "approval",
            "withdraw",
            "--approval-id",
            "approval-1",
            "--revision-hash",
            REVISION_HASH,
            "--record-version",
            "11",
            "--reason",
            "withdraw",
            "--idempotency-key",
            UUID1,
        ],
        [
            "publication",
            "publish",
            "--revision-id",
            "revision-1",
            "--revision-hash",
            REVISION_HASH,
            "--approval-id",
            "approval-1",
            "--record-version",
            "11",
            "--idempotency-key",
            UUID1,
        ],
        [
            "publication",
            "withdraw",
            "--publication-id",
            "publication-1",
            "--record-version",
            "11",
            "--reason",
            "withdraw",
            "--idempotency-key",
            UUID1,
        ],
        [
            "publication",
            "supersede",
            "--publication-id",
            "publication-1",
            "--replacement-publication-id",
            "publication-2",
            "--record-version",
            "11",
            "--replacement-record-version",
            "2",
            "--reason",
            "replace",
            "--idempotency-key",
            UUID1,
        ],
    ],
)
def test_cli_authority_confirmation_blocks_runtime_creation_for_every_write(
    capsys, monkeypatch, argv: list[str]
) -> None:
    monkeypatch.setattr(
        fmea_skill, "build_cli_runtime", lambda: (_ for _ in ()).throw(AssertionError("runtime created"))
    )
    exit_code = fmea_skill.main(argv)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code != 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["error"]["code"].endswith("CONFIRMATION_REQUIRED")


@pytest.mark.parametrize(
    "argv",
    [
        [
            "revision",
            "assemble",
            "--analysis-id",
            "analysis-1",
            "--record-version",
            "3",
            "--idempotency-key",
            UUID1.upper(),
            "--confirm-human-approval",
        ],
        [
            "approval",
            "submit",
            "--revision-id",
            "revision-1",
            "--revision-hash",
            REVISION_HASH,
            "--record-version",
            "11",
            "--idempotency-key",
            UUID1.upper(),
            "--confirm-human-approval",
        ],
        [
            "approval",
            "approve",
            "--submission-id",
            "submission-1",
            "--revision-id",
            "revision-1",
            "--revision-hash",
            REVISION_HASH,
            "--record-version",
            "11",
            "--reason",
            "approved",
            "--idempotency-key",
            UUID1.upper(),
            "--confirm-human-approval",
        ],
        [
            "approval",
            "reject",
            "--submission-id",
            "submission-1",
            "--revision-id",
            "revision-1",
            "--revision-hash",
            REVISION_HASH,
            "--record-version",
            "11",
            "--reason",
            "reject",
            "--idempotency-key",
            UUID1.upper(),
            "--confirm-human-approval",
        ],
        [
            "approval",
            "withdraw",
            "--approval-id",
            "approval-1",
            "--revision-hash",
            REVISION_HASH,
            "--record-version",
            "11",
            "--reason",
            "withdraw",
            "--idempotency-key",
            UUID1.upper(),
            "--confirm-approval-withdrawal",
        ],
        [
            "publication",
            "publish",
            "--revision-id",
            "revision-1",
            "--revision-hash",
            REVISION_HASH,
            "--approval-id",
            "approval-1",
            "--record-version",
            "11",
            "--idempotency-key",
            UUID1.upper(),
            "--confirm-publication",
        ],
        [
            "publication",
            "withdraw",
            "--publication-id",
            "publication-1",
            "--record-version",
            "11",
            "--reason",
            "withdraw",
            "--idempotency-key",
            UUID1.upper(),
            "--confirm-publication-withdrawal",
        ],
        [
            "publication",
            "supersede",
            "--publication-id",
            "publication-1",
            "--replacement-publication-id",
            "publication-2",
            "--record-version",
            "11",
            "--replacement-record-version",
            "2",
            "--reason",
            "replace",
            "--idempotency-key",
            UUID1.upper(),
            "--confirm-supersession",
        ],
    ],
)
def test_cli_every_authority_write_rejects_noncanonical_idempotency_key(capsys, monkeypatch, argv: list[str]) -> None:
    service = FakeGovernanceService()
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service))
    exit_code = fmea_skill.main(argv)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code != 0
    assert captured.err == ""
    assert payload["error"]["code"] == "FMEA_GOVERNANCE_REQUEST_INVALID"
    assert service.commands == []


@pytest.mark.parametrize("option", ["--provider", "--topology", "--domain-pack", "--rule-pack", "--snapshot-path"])
def test_cli_rejects_all_server_owned_identity_overrides(capsys, option: str) -> None:
    exit_code = fmea_skill.main(["publication", "show", "--publication-id", "publication-1", option, "attacker-value"])
    captured = capsys.readouterr()
    assert exit_code != 0
    assert captured.err == ""
    assert "attacker-value" not in captured.out
    assert json.loads(captured.out)["error"]["code"] == "FMEA_GOVERNANCE_REQUEST_INVALID"


def test_cli_governance_failure_is_one_stable_json_object(capsys, monkeypatch) -> None:
    service = FakeGovernanceService()

    def submit(_command: object, _actor: ActorContext) -> None:
        raise GovernanceServiceError("FMEA_GOVERNANCE_VERSION_CONFLICT", "version conflict")

    service.submit_for_approval = submit  # type: ignore[method-assign]
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service))
    exit_code = fmea_skill.main([
        "approval",
        "submit",
        "--revision-id",
        "revision-1",
        "--revision-hash",
        REVISION_HASH,
        "--record-version",
        "11",
        "--idempotency-key",
        UUID1,
        "--confirm-human-approval",
    ])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code != 0
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert payload["error"]["code"] == "FMEA_GOVERNANCE_VERSION_CONFLICT"
    assert payload["error"]["detail"] == "version conflict"


def test_cli_history_uses_signed_shared_cursor_without_exposing_inner_cursor(capsys, monkeypatch) -> None:
    service = FakeGovernanceService()
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service))
    assert fmea_skill.main(["approval", "history", "--revision-id", "revision-1", "--limit", "1"]) == 0
    first = json.loads(capsys.readouterr().out)
    cursor = first["data"]["next_cursor"]
    assert "internal|approval-event-1" not in json.dumps(first)
    assert (
        fmea_skill.main(["approval", "history", "--revision-id", "revision-1", "--limit", "1", "--cursor", cursor]) == 0
    )
    second = json.loads(capsys.readouterr().out)
    assert service.history_queries[-1].cursor == "internal|approval-event-1"
    assert "internal|approval-event-1" not in json.dumps(second)


def test_cli_history_requires_dedicated_cursor_secret_without_review_token_fallback(capsys, monkeypatch) -> None:
    service = FakeGovernanceService()
    monkeypatch.setenv("FMEA_REVIEW_TOKEN", "review-token-must-not-sign-governance-cursors")
    monkeypatch.delenv("FMEA_GOVERNANCE_CURSOR_SECRET", raising=False)
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service, cursor_secret=None))

    exit_code = fmea_skill.main(["approval", "history", "--revision-id", "revision-1", "--limit", "1"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 3
    assert payload["error"]["code"] == "FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID"
    assert service.history_queries == []


def test_cli_default_runtime_missing_source_providers_maps_to_configuration(capsys, monkeypatch, tmp_path) -> None:
    from chroma_rag_poc.workspace_registry import WorkspaceConfig

    from core_domain.query_contracts import QueryMode
    from fmea_infrastructure.composition import build_default_workspace_governance_runtime

    workspace = WorkspaceConfig(
        workspace_id="ws-1",
        chroma_persist_dir=tmp_path / "chroma",
        chroma_collection="fmea",
        graph_db_path=tmp_path / "graph.sqlite3",
        fmea_db_path=tmp_path / "fmea.sqlite3",
        fmea_template_registry_path=tmp_path / "templates",
        supported_modes=frozenset({QueryMode.VECTOR}),
        default_mode=QueryMode.VECTOR,
    )
    governance_runtime = build_default_workspace_governance_runtime(workspace)
    runtime = SimpleNamespace(
        governance_service=governance_runtime.service,
        actor=ActorContext("human-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1"),
        governance_cursor_secret=derive_governance_cursor_secret("task5-cli-provider-test-secret"),
        close=lambda: None,
    )
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: runtime)

    exit_code = fmea_skill.main([
        "revision",
        "assemble",
        "--analysis-id",
        "analysis-1",
        "--record-version",
        "1",
        "--idempotency-key",
        UUID1,
        "--confirm-human-approval",
    ])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 3
    assert payload["error"]["code"] == "FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID"


def test_cli_runtime_acquires_the_governance_application_service(monkeypatch) -> None:
    service = FakeGovernanceService()
    monkeypatch.setenv("FMEA_GOVERNANCE_CURSOR_SECRET", "task5-runtime-acquisition-cursor-secret")
    _configure_real_cli_runtime(monkeypatch, service)

    runtime = fmea_skill.build_cli_runtime()

    assert runtime.governance_service is service
    assert runtime.governance_cursor_secret == derive_governance_cursor_secret(
        "task5-runtime-acquisition-cursor-secret"
    )
    runtime.close()


def test_cli_runtime_without_cursor_secret_keeps_non_history_governance_available(capsys, monkeypatch) -> None:
    service = FakeGovernanceService()
    monkeypatch.delenv("FMEA_GOVERNANCE_CURSOR_SECRET", raising=False)
    _configure_real_cli_runtime(monkeypatch, service)

    runtime = fmea_skill.build_cli_runtime()

    assert runtime.governance_cursor_secret is None
    assert runtime.service is not None
    assert runtime.analysis_service is not None
    assert runtime.decision_service is not None
    assert runtime.risk_service is not None
    runtime.close()
    assert fmea_skill.main(["publication", "snapshot", "--publication-id", "publication-1"]) == 0
    assert json.loads(capsys.readouterr().out)["resource_type"] == "publication_snapshot"

    for history_args in (
        ["approval", "history", "--revision-id", "revision-1", "--limit", "1"],
        ["publication", "history", "--publication-id", "publication-1", "--limit", "1"],
    ):
        assert fmea_skill.main(history_args) == 3
        payload = json.loads(capsys.readouterr().out)
        assert payload["error"]["code"] == "FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID"
    assert service.history_queries == []
