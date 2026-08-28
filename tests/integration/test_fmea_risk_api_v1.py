from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
for import_path in (REPO_ROOT, PACKAGE_SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from chroma_rag_poc.api import create_app  # noqa: E402

from core_domain.fmea.states import ActorType, RiskStatus  # noqa: E402
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion  # noqa: E402
from fmea_application.review_contracts import ActorContext  # noqa: E402

TOKEN = "a" * 32
UUID1 = "00000000-0000-4000-8000-000000000101"


class FakeAuth:
    def __init__(self, actor_type: ActorType = ActorType.HUMAN) -> None:
        self.actor_type = actor_type

    def authenticate(self, bearer_token: str | None, remote_host: str | None) -> ActorContext:
        assert bearer_token == TOKEN
        assert remote_host in {"127.0.0.1", "testclient"}
        roles = frozenset({"reviewer", "risk_reviewer"}) if self.actor_type is ActorType.HUMAN else frozenset()
        return ActorContext("caller-1", self.actor_type, roles, "ws-1")


def _suggestion() -> AssistanceSuggestion[object]:
    return AssistanceSuggestion(
        suggestion_id="suggestion-1",
        kind=AssistanceKind.ANALYSIS_SCOPE_DRAFT,
        workspace_id="ws-1",
        target_type="fmea_analysis",
        target_id="analysis-1",
        target_record_version=1,
        evidence_pack_ids=("pack-1",),
        payload={
            "scope": "Fuel delivery and combustion",
            "system_boundary": "Tank to combustor",
            "exclusions": [],
            "operating_modes": ["start", "steady"],
            "assumptions": [],
            "limitations": ["Evidence-bound draft"],
        },
        evidence_ids=("ev-1",),
        model_hash="a" * 64,
        prompt_hash="b" * 64,
        run_id="scope-run-1",
        trace_id="scope-trace-1",
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        template_id="fmea-analysis-scope",
        template_version="1.0.0",
        rule_pack_id="fuel-sod-rpn",
        rule_pack_version="1.0.0",
        created_at="2026-08-28T00:00:00Z",
    )


def _assessment(status: RiskStatus = RiskStatus.PROPOSED, version: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        assessment_id="assessment-1",
        workspace_id="ws-1",
        row_id="row-1",
        source_record_version=1,
        evidence_pack_id="pack-1",
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        rule_pack_id="fuel-sod-rpn",
        rule_pack_version="1.0.0",
        status=status,
        dimensions=(
            SimpleNamespace(name="severity", value=9, evidence_ids=("ev-1",), reason="severe", uncertainty=None),
            SimpleNamespace(name="occurrence", value=3, evidence_ids=("ev-1",), reason="occasional", uncertainty=None),
            SimpleNamespace(name="detection", value=4, evidence_ids=("ev-1",), reason="detectable", uncertainty=None),
        ),
        derived=None,
        proposal_id="proposal-1",
        assistance_suggestion_id="suggestion-1",
        confirmer_actor_id=None,
        invalidated_reason=None,
        record_version=version,
        created_at="2026-08-28T00:00:00Z",
        updated_at="2026-08-28T00:00:00Z",
    )


@dataclass
class FakeAnalysisService:
    suggestion: AssistanceSuggestion[object] = field(default_factory=_suggestion)
    actors: list[ActorContext] = field(default_factory=list)

    def suggest_scope(self, request: Any, actor: ActorContext) -> AssistanceSuggestion[object]:
        self.actors.append(actor)
        return self.suggestion

    def get(self, suggestion_id: str, actor: ActorContext) -> AssistanceSuggestion[object]:
        assert suggestion_id == self.suggestion.suggestion_id
        return self.suggestion


@dataclass
class FakeDecisionService:
    actors: list[ActorContext] = field(default_factory=list)

    def decide(self, command: Any, actor: ActorContext) -> SimpleNamespace:
        self.actors.append(actor)
        return SimpleNamespace(
            decision_id="decision-1",
            suggestion_id=command.suggestion_id,
            suggestion_hash="sha256:" + "c" * 64,
            suggestion_record_version=command.expected_suggestion_version,
            target_record_version=command.expected_target_record_version,
            action=command.action,
            actor_id=actor.actor_id,
            actor_type=actor.actor_type,
            edits=command.edits,
            reason=command.reason,
            idempotency_key=command.idempotency_key,
            resulting_resource_identity=None,
            created_at="2026-08-28T00:00:01Z",
        )


@dataclass
class FakeRiskService:
    proposed: SimpleNamespace = field(default_factory=_assessment)
    actors: list[ActorContext] = field(default_factory=list)

    def propose(self, command: Any, actor: ActorContext) -> SimpleNamespace:
        self.actors.append(actor)
        return self.proposed

    def get(self, row_id: str, actor: ActorContext) -> SimpleNamespace:
        assert row_id == "row-1"
        return self.proposed

    def get_proposal_run(self, run_id: str, actor: ActorContext) -> SimpleNamespace:
        assert run_id == "suggestion-1"
        return self.proposed

    def confirm(self, command: Any, actor: ActorContext) -> SimpleNamespace:
        confirmed = _assessment(RiskStatus.CONFIRMED, 2)
        return SimpleNamespace(
            assessment=confirmed,
            decision_id="risk-decision-1",
            audit_event_id="audit-1",
            outbox_event_id="outbox-1",
            replayed=False,
            persisted=True,
        )

    def reject(self, command: Any, actor: ActorContext) -> SimpleNamespace:
        return _assessment(RiskStatus.REVIEWED, 2)


def _client(actor_type: ActorType = ActorType.HUMAN) -> tuple[TestClient, SimpleNamespace]:
    runtime = SimpleNamespace(
        analysis_service=FakeAnalysisService(),
        decision_service=FakeDecisionService(),
        risk_service=FakeRiskService(),
    )
    app = create_app(
        review_auth_provider=FakeAuth(actor_type),
        risk_runtime_factory=lambda _workspace: runtime,
    )
    app.state.workspace_registry = SimpleNamespace(get=lambda workspace_id: SimpleNamespace(workspace_id=workspace_id))
    return TestClient(app, client=("127.0.0.1", 50000)), runtime


def _headers(*, version: int | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": UUID1}
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return headers


def test_scope_assistance_returns_unapplied_suggestion_from_server_model_actor() -> None:
    client, runtime = _client()
    response = client.post(
        "/api/v1/fmea/assistance/analysis-scope-runs",
        headers=_headers(),
        json={
            "target_id": "analysis-1",
            "target_record_version": 1,
            "evidence_pack_ids": ["pack-1"],
            "payload": {"question": "Draft scope"},
            "domain_pack_id": "fuel-combustion",
            "domain_pack_version": "1.0.0",
            "template_id": "fmea-analysis-scope",
            "template_version": "1.0.0",
            "rule_pack_id": "fuel-sod-rpn",
            "rule_pack_version": "1.0.0",
        },
    )
    assert response.status_code == 202
    assert response.json()["data"]["applied"] is False
    assert runtime.analysis_service.actors[0].actor_type is ActorType.MODEL


def test_risk_proposal_returns_durable_run_identity_and_model_actor() -> None:
    client, runtime = _client()
    response = client.post(
        "/api/v1/fmea/rows/row-1/risk-proposal-runs",
        headers=_headers(version=1),
        json={
            "evidence_pack_id": "pack-1",
            "domain_pack_id": "fuel-combustion",
            "domain_pack_version": "1.0.0",
            "template_id": "fmea-risk-proposal",
            "template_version": "1.0.0",
            "rule_pack_id": "fuel-sod-rpn",
            "rule_pack_version": "1.0.0",
        },
    )
    assert response.status_code == 202
    assert response.json()["data"]["run_id"] == "suggestion-1"
    assert response.headers["location"].endswith("suggestion-1")
    assert runtime.risk_service.actors[0].actor_type is ActorType.MODEL
    status = client.get(
        "/api/v1/fmea/risk-proposal-runs/suggestion-1",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert status.status_code == 200
    assert status.json()["data"] == response.json()["data"]


def test_model_actor_cannot_submit_assistance_decision() -> None:
    client, runtime = _client(ActorType.MODEL)
    response = client.post(
        "/api/v1/fmea/assistance/suggestions/suggestion-1/decisions",
        headers=_headers(version=1),
        json={
            "action": "reject",
            "target_record_version": 1,
            "reason": "Model actors cannot decide.",
            "edits": [],
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FMEA_REVIEW_FORBIDDEN"
    assert runtime.decision_service.actors == []


def test_risk_confirm_requires_if_match_idempotency_and_human_actor() -> None:
    client, _ = _client()
    missing = client.post(
        "/api/v1/fmea/rows/row-1/risk-confirmations",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"proposal_id": "proposal-1"},
    )
    assert missing.status_code == 428
    assert missing.json()["code"] == "FMEA_PRECONDITION_REQUIRED"

    model_client, _ = _client(ActorType.MODEL)
    forbidden = model_client.post(
        "/api/v1/fmea/rows/row-1/risk-confirmations",
        headers=_headers(version=1),
        json={"proposal_id": "proposal-1"},
    )
    assert forbidden.status_code == 422
    assert forbidden.json()["code"] == "FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED"


def test_confirmed_risk_read_and_write_share_one_resource_shape() -> None:
    client, runtime = _client()
    confirmed = client.post(
        "/api/v1/fmea/rows/row-1/risk-confirmations",
        headers=_headers(version=1),
        json={"proposal_id": "proposal-1"},
    )
    assert confirmed.status_code == 200
    assert confirmed.headers["etag"] == '"2"'
    runtime.risk_service.proposed = confirmed_assessment = _assessment(RiskStatus.CONFIRMED, 2)
    shown = client.get("/api/v1/fmea/rows/row-1/risk", headers={"Authorization": f"Bearer {TOKEN}"})
    assert shown.status_code == 200
    assert shown.json()["data"] == confirmed.json()["data"]["assessment"]
    assert shown.json()["data"]["assessment_id"] == confirmed_assessment.assessment_id


def test_risk_storage_failure_returns_stable_safe_error() -> None:
    client, runtime = _client()

    def fail_get(row_id: str, actor: ActorContext) -> SimpleNamespace:
        del row_id, actor
        raise RuntimeError("sensitive database detail")  # noqa: TRY003

    runtime.risk_service.get = fail_get
    response = client.get(
        "/api/v1/fmea/rows/row-1/risk",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "FMEA_REVIEW_STORAGE_UNAVAILABLE"
    assert "sensitive database detail" not in response.text
