from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from chroma_rag_poc.api import create_app
from chroma_rag_poc.fmea_governance_contracts import encode_history_cursor
from chroma_rag_poc.workspace_registry import WorkspaceNotFoundError
from fastapi.testclient import TestClient

from core_domain.fmea.states import ActorType
from fmea_application.governance_contracts import (
    ApprovalCommand,
    ApprovalRejectionCommand,
    AssembleRevisionCommand,
    PublicationResult,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    WithdrawApprovalCommand,
    WithdrawPublicationCommand,
)
from fmea_application.review_contracts import ActorContext

TOKEN = "a" * 32
UUID1 = "00000000-0000-4000-8000-0000000005ab"
REVISION_HASH = "sha256:" + "c" * 64


class FakeAuth:
    def __init__(self, workspace_id: str = "ws-1") -> None:
        self.workspace_id = workspace_id

    def authenticate(self, bearer_token: str, remote_host: str | None) -> ActorContext:
        assert bearer_token == TOKEN
        assert remote_host in {"127.0.0.1", "testclient"}
        return ActorContext(
            "human-1",
            ActorType.HUMAN,
            frozenset({"reviewer", "approver", "publisher"}),
            self.workspace_id,
        )


def _revision(record_version: int = 11) -> SimpleNamespace:
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
        record_version=record_version,
    )


def _readiness() -> SimpleNamespace:
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


def _mutation(**identities: str) -> SimpleNamespace:
    return SimpleNamespace(
        replayed=False,
        audit_event_id="audit-1",
        outbox_event_id="outbox-1",
        record_version=1,
        **identities,
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
        row_id="submission-1",
        decision_id=None,
        expected_record_version=11,
        applied_record_version=1,
        after_hash=REVISION_HASH,
    )


@dataclass
class FakeGovernanceService:
    revision: SimpleNamespace = field(default_factory=_revision)
    readiness_report: SimpleNamespace = field(default_factory=_readiness)
    snapshot: SimpleNamespace = field(default_factory=_snapshot)
    publish_command: Any = None
    history_calls: int = 0
    history_queries: list[Any] = field(default_factory=list)
    commands: dict[str, Any] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def get_revision_record(self, revision_id: str, actor: ActorContext) -> tuple[SimpleNamespace, int]:
        assert revision_id == self.revision.revision_id
        assert actor.workspace_id == self.revision.workspace_id
        return self.revision, self.revision.record_version

    def assemble(self, command: AssembleRevisionCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("assemble")
        self.commands["assemble"] = command
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(revision_id="revision-1")

    def readiness(self, revision_id: str, actor: ActorContext) -> SimpleNamespace:
        assert revision_id == self.revision.revision_id
        assert actor.workspace_id == self.revision.workspace_id
        return self.readiness_report

    def submit_for_approval(self, command: SubmitApprovalCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("submit_for_approval")
        self.commands["submit"] = command
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(submission_id="submission-1")

    def approve(self, command: ApprovalCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("approve")
        self.commands["approve"] = command
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(approval_id="approval-1")

    def reject(self, command: ApprovalRejectionCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("reject")
        self.commands["reject"] = command
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(approval_id="approval-1")

    def withdraw_approval(self, command: WithdrawApprovalCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("withdraw_approval")
        self.commands["withdraw_approval"] = command
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(withdrawal_id="withdrawal-1", approval_id="approval-1")

    def publish(self, command: Any, actor: ActorContext) -> PublicationResult:
        self.calls.append("publish")
        self.publish_command = command
        self.commands["publish"] = command
        assert actor.actor_type is ActorType.HUMAN
        return PublicationResult("publication-1", "manifest-1", "snapshot-1", 1, "audit-1", "outbox-1")

    def get_publication(self, publication_id: str, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("get_publication")
        assert publication_id == "publication-1"
        assert actor.workspace_id == "ws-1"
        return SimpleNamespace(
            publication=_publication(), effective_status="published", withdrawal=None, supersession=None
        )

    def withdraw_publication(self, command: WithdrawPublicationCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("withdraw_publication")
        self.commands["withdraw_publication"] = command
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(withdrawal_id="withdrawal-1", publication_id="publication-1")

    def supersede(self, command: SupersedePublicationCommand, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("supersede")
        self.commands["supersede"] = command
        assert actor.actor_type is ActorType.HUMAN
        return _mutation(
            supersession_id="supersession-1", old_publication_id="publication-1", new_publication_id="publication-2"
        )

    def get_snapshot(self, publication_id: str, actor: ActorContext) -> SimpleNamespace:
        assert publication_id == self.snapshot.publication_id
        assert actor.workspace_id == self.snapshot.workspace_id
        return self.snapshot

    def list_approval_events(self, query: Any, actor: ActorContext) -> SimpleNamespace:
        self.history_calls += 1
        self.history_queries.append(query)
        assert query.workspace_id == actor.workspace_id == "ws-1"
        assert query.resource_type == "revision"
        return SimpleNamespace(events=(_event(),), next_cursor="internal|event-1")

    def list_publication_events(self, query: Any, actor: ActorContext) -> SimpleNamespace:
        self.calls.append("list_publication_events")
        self.history_calls += 1
        self.history_queries.append(query)
        assert query.workspace_id == actor.workspace_id == "ws-1"
        assert query.resource_type == "publication"
        return SimpleNamespace(events=(_event(),), next_cursor="internal|publication-event-1")


@dataclass
class FakeGovernanceAssistanceService:
    calls: int = 0
    actor_types: list[ActorType] = field(default_factory=list)

    def suggest_readiness_checklist(self, report: Any, actor: ActorContext) -> SimpleNamespace:
        self.calls += 1
        self.actor_types.append(actor.actor_type)
        return SimpleNamespace(
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


def _client() -> tuple[TestClient, FakeGovernanceService, FakeGovernanceAssistanceService]:
    service = FakeGovernanceService()
    assistance = FakeGovernanceAssistanceService()
    runtime = SimpleNamespace(service=service, assistance_service=assistance, repository=object())
    app = create_app(review_auth_provider=FakeAuth())
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: SimpleNamespace(workspace_id=workspace_id))
    app.state.governance_runtime_factory = lambda _workspace: runtime
    return TestClient(app, client=("127.0.0.1", 50000)), service, assistance


def _headers(version: int = 11) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "If-Match": f'"{version}"',
        "Idempotency-Key": UUID1,
    }


def test_all_task5_governance_routes_are_registered() -> None:
    client, _, _ = _client()
    paths = {route.path for route in client.app.routes if "fmea" in getattr(route, "path", "")}
    expected = {
        "/api/v1/fmea/analyses/{analysis_id}/revisions",
        "/api/v1/fmea/revisions/{revision_id}",
        "/api/v1/fmea/revisions/{revision_id}/readiness",
        "/api/v1/fmea/revisions/{revision_id}/readiness-suggestion-runs",
        "/api/v1/fmea/revisions/{revision_id}/approval-submissions",
        "/api/v1/fmea/approval-submissions/{submission_id}/approvals",
        "/api/v1/fmea/approval-submissions/{submission_id}/rejections",
        "/api/v1/fmea/approvals/{approval_id}/withdrawals",
        "/api/v1/fmea/revisions/{revision_id}/approval-events",
        "/api/v1/fmea/revisions/{revision_id}/publications",
        "/api/v1/fmea/publications/{publication_id}",
        "/api/v1/fmea/publications/{publication_id}/snapshot",
        "/api/v1/fmea/publications/{publication_id}/withdrawals",
        "/api/v1/fmea/publications/{publication_id}/supersessions",
        "/api/v1/fmea/publications/{publication_id}/lifecycle-events",
    }
    assert expected <= paths


@pytest.mark.parametrize(
    ("path", "body", "command_key", "command_type", "resource_type", "location", "etag"),
    [
        (
            "/api/v1/fmea/analyses/analysis-1/revisions",
            {
                "parent_revision_id": "parent-1",
                "parent_revision_hash": REVISION_HASH,
                "confirm_human_approval": True,
            },
            "assemble",
            AssembleRevisionCommand,
            "revision",
            "/api/v1/fmea/revisions/revision-1",
            '"1"',
        ),
        (
            "/api/v1/fmea/revisions/revision-1/approval-submissions",
            {"revision_hash": REVISION_HASH, "confirm_human_approval": True},
            "submit",
            SubmitApprovalCommand,
            "approval_submission",
            "/api/v1/fmea/approval-submissions/submission-1",
            '"1"',
        ),
        (
            "/api/v1/fmea/approval-submissions/submission-1/approvals",
            {
                "revision_id": "revision-1",
                "revision_hash": REVISION_HASH,
                "reason": "approved",
                "confirm_human_approval": True,
            },
            "approve",
            ApprovalCommand,
            "approval",
            "/api/v1/fmea/approvals/approval-1",
            '"1"',
        ),
        (
            "/api/v1/fmea/approval-submissions/submission-1/rejections",
            {
                "revision_id": "revision-1",
                "revision_hash": REVISION_HASH,
                "reason": "needs changes",
                "confirm_human_approval": True,
            },
            "reject",
            ApprovalRejectionCommand,
            "approval_rejection",
            "/api/v1/fmea/approvals/approval-1",
            '"1"',
        ),
        (
            "/api/v1/fmea/approvals/approval-1/withdrawals",
            {
                "revision_hash": REVISION_HASH,
                "reason": "withdraw approval",
                "confirm_approval_withdrawal": True,
            },
            "withdraw_approval",
            WithdrawApprovalCommand,
            "approval_withdrawal",
            "/api/v1/fmea/approvals/approval-1/withdrawals",
            None,
        ),
        (
            "/api/v1/fmea/publications/publication-1/withdrawals",
            {
                "reason": "withdraw publication",
                "replacement_publication_id": "publication-2",
                "confirm_publication_withdrawal": True,
            },
            "withdraw_publication",
            WithdrawPublicationCommand,
            "publication_withdrawal",
            "/api/v1/fmea/publications/publication-1/withdrawals",
            None,
        ),
        (
            "/api/v1/fmea/publications/publication-1/supersessions",
            {
                "replacement_publication_id": "publication-2",
                "replacement_record_version": 2,
                "reason": "replace",
                "confirm_supersession": True,
            },
            "supersede",
            SupersedePublicationCommand,
            "publication_supersession",
            "/api/v1/fmea/publications/publication-1/supersessions",
            None,
        ),
    ],
)
def test_rest_authority_commands_call_exact_application_commands(
    path: str,
    body: dict[str, object],
    command_key: str,
    command_type: type,
    resource_type: str,
    location: str,
    etag: str | None,
) -> None:
    client, service, _ = _client()
    version = 3 if command_key == "assemble" else 11
    with client:
        response = client.post(path, headers=_headers(version), json=body)
    assert response.status_code == 201
    assert response.json()["resource_type"] == resource_type
    assert response.headers["location"] == location
    assert response.headers.get("etag") == etag
    command = service.commands[command_key]
    assert isinstance(command, command_type)
    assert command.idempotency_key == UUID1
    if command_key == "assemble":
        assert command.request.analysis_id == "analysis-1"
        assert command.request.expected_analysis_version == 3
        assert command.request.parent_revision_id == "parent-1"
        assert command.request.parent_revision_hash == REVISION_HASH
    elif command_key == "submit":
        assert command.revision_id == "revision-1"
        assert command.revision_hash == REVISION_HASH
        assert command.expected_revision_version == 11
    elif command_key in {"approve", "reject"}:
        assert command.submission_id == "submission-1"
        assert command.revision_id == "revision-1"
        assert command.revision_hash == REVISION_HASH
        assert command.expected_submission_version == 11
        assert command.reason == ("approved" if command_key == "approve" else "needs changes")
    elif command_key == "withdraw_approval":
        assert command.approval_id == "approval-1"
        assert command.revision_hash == REVISION_HASH
        assert command.expected_approval_version == 11
        assert command.reason == "withdraw approval"
    elif command_key == "withdraw_publication":
        assert command.publication_id == "publication-1"
        assert command.expected_publication_version == 11
        assert command.reason == "withdraw publication"
        assert command.replacement_publication_id == "publication-2"
    else:
        assert command.publication_id == "publication-1"
        assert command.expected_publication_version == 11
        assert command.expected_replacement_version == 2
        assert command.replacement_publication_id == "publication-2"
        assert command.reason == "replace"


@pytest.mark.parametrize(
    ("path", "body", "code"),
    [
        (
            "/api/v1/fmea/analyses/analysis-1/revisions",
            {"confirm_human_approval": False},
            "FMEA_GOVERNANCE_APPROVAL_CONFIRMATION_REQUIRED",
        ),
        (
            "/api/v1/fmea/revisions/revision-1/approval-submissions",
            {"revision_hash": REVISION_HASH, "confirm_human_approval": False},
            "FMEA_GOVERNANCE_APPROVAL_CONFIRMATION_REQUIRED",
        ),
        (
            "/api/v1/fmea/approval-submissions/submission-1/approvals",
            {
                "revision_id": "revision-1",
                "revision_hash": REVISION_HASH,
                "reason": "approved",
                "confirm_human_approval": False,
            },
            "FMEA_GOVERNANCE_APPROVAL_CONFIRMATION_REQUIRED",
        ),
        (
            "/api/v1/fmea/approvals/approval-1/withdrawals",
            {"revision_hash": REVISION_HASH, "reason": "withdraw"},
            "FMEA_GOVERNANCE_APPROVAL_WITHDRAWAL_CONFIRMATION_REQUIRED",
        ),
        (
            "/api/v1/fmea/revisions/revision-1/publications",
            {"approval_id": "approval-1", "revision_hash": REVISION_HASH},
            "FMEA_GOVERNANCE_PUBLICATION_CONFIRMATION_REQUIRED",
        ),
        (
            "/api/v1/fmea/publications/publication-1/withdrawals",
            {"reason": "withdraw"},
            "FMEA_GOVERNANCE_PUBLICATION_WITHDRAWAL_CONFIRMATION_REQUIRED",
        ),
        (
            "/api/v1/fmea/publications/publication-1/supersessions",
            {"replacement_publication_id": "publication-2", "replacement_record_version": 2, "reason": "replace"},
            "FMEA_GOVERNANCE_SUPERSESSION_CONFIRMATION_REQUIRED",
        ),
    ],
)
def test_rest_authority_confirmation_blocks_service_call(path: str, body: dict[str, object], code: str) -> None:
    client, service, _ = _client()
    with client:
        response = client.post(path, headers=_headers(), json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert service.commands == {}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/fmea/analyses/analysis-1/revisions",
        "/api/v1/fmea/revisions/revision-1/approval-submissions",
        "/api/v1/fmea/approval-submissions/submission-1/approvals",
        "/api/v1/fmea/approvals/approval-1/withdrawals",
        "/api/v1/fmea/revisions/revision-1/publications",
        "/api/v1/fmea/publications/publication-1/withdrawals",
        "/api/v1/fmea/publications/publication-1/supersessions",
    ],
)
def test_rest_every_authority_write_rejects_noncanonical_idempotency_key(path: str) -> None:
    client, service, _ = _client()
    body: dict[str, object] = {"confirm_human_approval": True}
    if "approval-submissions" in path and path.endswith("approval-submissions"):
        body = {"revision_hash": REVISION_HASH, "confirm_human_approval": True}
    elif path.endswith("/approvals"):
        body = {
            "revision_id": "revision-1",
            "revision_hash": REVISION_HASH,
            "reason": "approved",
            "confirm_human_approval": True,
        }
    elif path.endswith("/withdrawals") and "/approvals/" in path:
        body = {"revision_hash": REVISION_HASH, "reason": "withdraw", "confirm_approval_withdrawal": True}
    elif path.endswith("/publications"):
        body = {"approval_id": "approval-1", "revision_hash": REVISION_HASH, "confirm_publication": True}
    elif path.endswith("/withdrawals"):
        body = {"reason": "withdraw", "confirm_publication_withdrawal": True}
    elif path.endswith("/supersessions"):
        body = {
            "replacement_publication_id": "publication-2",
            "replacement_record_version": 2,
            "reason": "replace",
            "confirm_supersession": True,
        }
    headers = {**_headers(), "Idempotency-Key": UUID1.upper()}
    with client:
        response = client.post(path, headers=headers, json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FMEA_GOVERNANCE_REQUEST_INVALID"
    assert service.commands == {}


@pytest.mark.parametrize("missing_header", ["If-Match", "Idempotency-Key"])
@pytest.mark.parametrize(
    ("path", "body"),
    [
        (
            "/api/v1/fmea/analyses/analysis-1/revisions",
            {
                "parent_revision_id": "parent-1",
                "parent_revision_hash": REVISION_HASH,
                "confirm_human_approval": True,
            },
        ),
        (
            "/api/v1/fmea/revisions/revision-1/approval-submissions",
            {"revision_hash": REVISION_HASH, "confirm_human_approval": True},
        ),
        (
            "/api/v1/fmea/approval-submissions/submission-1/approvals",
            {
                "revision_id": "revision-1",
                "revision_hash": REVISION_HASH,
                "reason": "approved",
                "confirm_human_approval": True,
            },
        ),
        (
            "/api/v1/fmea/approvals/approval-1/withdrawals",
            {
                "revision_hash": REVISION_HASH,
                "reason": "withdraw approval",
                "confirm_approval_withdrawal": True,
            },
        ),
        (
            "/api/v1/fmea/revisions/revision-1/publications",
            {
                "approval_id": "approval-1",
                "revision_hash": REVISION_HASH,
                "confirm_publication": True,
            },
        ),
        (
            "/api/v1/fmea/publications/publication-1/withdrawals",
            {"reason": "withdraw publication", "confirm_publication_withdrawal": True},
        ),
        (
            "/api/v1/fmea/publications/publication-1/supersessions",
            {
                "replacement_publication_id": "publication-2",
                "replacement_record_version": 2,
                "reason": "replace",
                "confirm_supersession": True,
            },
        ),
    ],
)
def test_rest_every_authority_write_requires_if_match_and_idempotency(
    path: str, body: dict[str, object], missing_header: str
) -> None:
    client, service, _ = _client()
    headers = _headers()
    headers.pop(missing_header)
    with client:
        response = client.post(path, headers=headers, json=body)
    assert response.status_code == 428
    assert response.json()["error"]["code"] == "FMEA_PRECONDITION_REQUIRED"
    assert service.commands == {}


def test_rest_publication_reads_and_history_are_real_service_operations() -> None:
    client, service, _ = _client()
    with client:
        publication = client.get(
            "/api/v1/fmea/publications/publication-1", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        history = client.get(
            "/api/v1/fmea/publications/publication-1/lifecycle-events",
            headers={"Authorization": f"Bearer {TOKEN}"},
            params={"limit": 1, "descending": True},
        )
    assert publication.status_code == 200
    assert publication.headers["etag"] == '"1"'
    assert publication.json()["resource_type"] == "publication"
    assert publication.json()["data"]["publication_id"] == "publication-1"
    assert history.status_code == 200
    assert history.json()["resource_type"] == "publication_history"
    assert history.json()["data"]["items"][0]["event_id"] == "event-1"
    assert "internal|publication-event-1" not in history.text
    assert service.calls == ["get_publication", "list_publication_events"]


def test_publish_requires_explicit_confirmation_before_service_or_storage() -> None:
    client, service, _ = _client()
    with client:
        response = client.post(
            "/api/v1/fmea/revisions/revision-1/publications",
            headers=_headers(),
            json={"approval_id": "approval-1", "confirm_publication": False},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FMEA_GOVERNANCE_PUBLICATION_CONFIRMATION_REQUIRED"
    assert service.publish_command is None


def test_publish_uses_exact_if_match_and_shared_application_command() -> None:
    client, service, _ = _client()
    with client:
        response = client.post(
            "/api/v1/fmea/revisions/revision-1/publications",
            headers=_headers(11),
            json={
                "approval_id": "approval-1",
                "revision_hash": REVISION_HASH,
                "confirm_publication": True,
            },
        )
    assert response.status_code == 201
    assert response.headers["etag"] == '"1"'
    assert service.publish_command.expected_revision_version == 11
    assert service.publish_command.idempotency_key == UUID1
    assert response.json()["schema_version"] == "graphrag.fmea.v1"


def test_rest_rejects_missing_or_noncanonical_authority_preconditions() -> None:
    client, _, _ = _client()
    with client:
        missing = client.post(
            "/api/v1/fmea/revisions/revision-1/publications",
            headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": UUID1},
            json={"approval_id": "approval-1", "revision_hash": REVISION_HASH, "confirm_publication": True},
        )
        uppercase = client.post(
            "/api/v1/fmea/revisions/revision-1/publications",
            headers={**_headers(), "Idempotency-Key": UUID1.upper()},
            json={"approval_id": "approval-1", "revision_hash": REVISION_HASH, "confirm_publication": True},
        )
    assert missing.status_code == 428
    assert missing.json()["error"]["code"] == "FMEA_PRECONDITION_REQUIRED"
    assert uppercase.status_code == 400
    assert uppercase.json()["error"]["code"] == "FMEA_GOVERNANCE_REQUEST_INVALID"


def test_rest_validation_uses_governance_problem_code_and_rejects_provider_overrides() -> None:
    client, _, _ = _client()
    with client:
        response = client.post(
            "/api/v1/fmea/revisions/revision-1/publications",
            headers=_headers(),
            json={
                "approval_id": "approval-1",
                "revision_hash": REVISION_HASH,
                "confirm_publication": True,
                "topology": "attacker-controlled",
            },
        )
    assert response.status_code == 400
    assert response.json()["code"] == "FMEA_GOVERNANCE_REQUEST_INVALID"
    assert "attacker-controlled" not in response.text


def test_revision_etag_uses_repository_backed_revision_version() -> None:
    client, _, _ = _client()
    with client:
        response = client.get(
            "/api/v1/fmea/revisions/revision-1",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == 200
    assert response.headers["etag"] == '"11"'
    assert response.json()["data"]["record_version"] == 11
    assert response.json()["data"]["analysis_record_version"] == 3


def test_readiness_uses_repository_backed_revision_version_and_envelope() -> None:
    client, _, _ = _client()
    with client:
        response = client.get(
            "/api/v1/fmea/revisions/revision-1/readiness",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == 200
    assert response.headers["etag"] == '"11"'
    assert response.json()["resource_type"] == "revision_readiness"
    assert response.json()["data"]["record_version"] == 11
    assert response.json()["data"]["target_record_version"] == 3


def test_readiness_suggestion_is_model_advisory_and_does_not_change_readiness() -> None:
    client, _, assistance = _client()
    with client:
        before = client.get(
            "/api/v1/fmea/revisions/revision-1/readiness",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        suggested = client.post(
            "/api/v1/fmea/revisions/revision-1/readiness-suggestion-runs",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={},
        )
        after = client.get(
            "/api/v1/fmea/revisions/revision-1/readiness",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert before.status_code == after.status_code == 200
    assert suggested.status_code == 202
    assert suggested.json()["data"]["applied"] is False
    assert after.json()["data"] == before.json()["data"]
    assert assistance.calls == 1
    assert assistance.actor_types == [ActorType.MODEL]


def test_history_uses_shared_projection_and_hides_repository_cursor() -> None:
    client, service, _ = _client()
    with client:
        response = client.get(
            "/api/v1/fmea/revisions/revision-1/approval-events",
            headers={"Authorization": f"Bearer {TOKEN}"},
            params={"limit": 1},
        )
    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["event_id"] == "event-1"
    assert response.json()["data"]["next_cursor"]
    assert "internal|event-1" not in response.text
    assert service.history_calls == 1


def test_history_cursor_is_bound_to_workspace_resource_direction_page_and_filter() -> None:
    client, service, _ = _client()
    secret = client.app.state.governance_cursor_secret
    cursor = encode_history_cursor(
        secret,
        workspace_id="ws-2",
        resource_type="revision",
        resource_id="revision-1",
        descending=False,
        page_size=1,
        repository_cursor="internal|event-1",
    )
    with client:
        response = client.get(
            "/api/v1/fmea/revisions/revision-1/approval-events",
            headers={"Authorization": f"Bearer {TOKEN}"},
            params={"cursor": cursor, "limit": 1},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FMEA_GOVERNANCE_CURSOR_INVALID"
    assert service.history_calls == 0


def test_rest_history_round_trips_opaque_cursor_through_application_service() -> None:
    client, service, _ = _client()
    with client:
        first = client.get(
            "/api/v1/fmea/revisions/revision-1/approval-events",
            headers={"Authorization": f"Bearer {TOKEN}"},
            params={"limit": 1},
        )
        cursor = first.json()["data"]["next_cursor"]
        second = client.get(
            "/api/v1/fmea/revisions/revision-1/approval-events",
            headers={"Authorization": f"Bearer {TOKEN}"},
            params={"limit": 1, "cursor": cursor},
        )
    assert first.status_code == second.status_code == 200
    assert service.history_calls == 2
    assert service.history_queries[-1].cursor == "internal|event-1"
    assert service.history_queries[-1].page_size == 1
    assert "internal|event-1" not in second.text


def test_workspace_lookup_is_authoritative_before_governance_runtime_access() -> None:
    app = create_app(review_auth_provider=FakeAuth(workspace_id="ws-2"))
    app.state.workspace_registry = SimpleNamespace(
        get=lambda workspace_id: (_ for _ in ()).throw(WorkspaceNotFoundError(workspace_id))
    )
    client = TestClient(app, client=("127.0.0.1", 50000))
    with client:
        response = client.get(
            "/api/v1/fmea/revisions/revision-1",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code in {403, 404}


def test_rest_runtime_acquisition_delegates_to_the_application_service(monkeypatch) -> None:
    service = FakeGovernanceService()
    assistance = FakeGovernanceAssistanceService()
    runtime = SimpleNamespace(service=service, assistance_service=assistance, repository=object())
    seen_workspaces: list[str] = []

    def factory(workspace: Any) -> SimpleNamespace:
        seen_workspaces.append(workspace.workspace_id)
        return runtime

    app = create_app(review_auth_provider=FakeAuth(), governance_runtime_factory=factory)
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: SimpleNamespace(workspace_id=workspace_id))
    client = TestClient(app, client=("127.0.0.1", 50000))
    with client:
        response = client.get(
            "/api/v1/fmea/revisions/revision-1",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == 200
    assert response.json()["data"]["revision_id"] == "revision-1"
    assert seen_workspaces == ["ws-1"]
