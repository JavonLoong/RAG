from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from core_domain.fmea.states import ActorType, RiskStatus
from fmea_application.review_contracts import ActorContext
from scripts import fmea_skill

UUID1 = "00000000-0000-4000-8000-000000000201"


def _assessment() -> SimpleNamespace:
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
        status=RiskStatus.PROPOSED,
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
        record_version=1,
        created_at="2026-08-28T00:00:00Z",
        updated_at="2026-08-28T00:00:00Z",
    )


@dataclass
class FakeRiskService:
    assessment: SimpleNamespace = field(default_factory=_assessment)
    actors: list[ActorContext] = field(default_factory=list)

    def get(self, row_id: str, actor: ActorContext) -> SimpleNamespace:
        assert row_id == "row-1"
        self.actors.append(actor)
        return self.assessment

    def propose(self, command: Any, actor: ActorContext) -> SimpleNamespace:
        self.actors.append(actor)
        return self.assessment

    def get_proposal_run(self, run_id: str, actor: ActorContext) -> SimpleNamespace:
        assert run_id == "suggestion-1"
        self.actors.append(actor)
        return self.assessment


def _runtime(service: FakeRiskService, closed: list[int]) -> SimpleNamespace:
    human = ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer", "risk_reviewer"}), "ws-1")
    model = ActorContext("fmea-model-assistant", ActorType.MODEL, frozenset(), "ws-1")
    return SimpleNamespace(
        service=SimpleNamespace(),
        actor=human,
        model_actor=model,
        risk_service=service,
        analysis_service=SimpleNamespace(),
        decision_service=SimpleNamespace(),
        close=lambda: closed.append(1),
    )


def test_risk_show_emits_the_same_assessment_shape_as_rest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    service = FakeRiskService()
    closed: list[int] = []
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service, closed))

    assert fmea_skill.main(["risk", "show", "--row-id", "row-1"]) == 0
    payload = json.loads(capsys.readouterr().out)
    from chroma_rag_poc.routes_fmea_risk_v1 import assessment_data

    assert payload["data"] == assessment_data(service.assessment).model_dump(mode="json")
    assert payload["resource_type"] == "risk_assessment"
    assert closed == [1]


def test_risk_propose_and_status_use_model_then_authenticated_actor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    service = FakeRiskService()
    monkeypatch.setattr(fmea_skill, "build_cli_runtime", lambda: _runtime(service, []))

    propose = fmea_skill.main(
        [
            "risk", "propose", "--row-id", "row-1", "--record-version", "1",
            "--evidence-pack-id", "pack-1", "--domain-pack-id", "fuel-combustion",
            "--domain-pack-version", "1.0.0", "--template-id", "fmea-risk-proposal",
            "--template-version", "1.0.0", "--rule-pack-id", "fuel-sod-rpn",
            "--rule-pack-version", "1.0.0", "--idempotency-key", UUID1,
        ]
    )
    proposed_payload = json.loads(capsys.readouterr().out)
    status = fmea_skill.main(["risk", "proposal-status", "--run-id", "suggestion-1"])
    status_payload = json.loads(capsys.readouterr().out)

    assert propose == status == 0
    assert proposed_payload["data"]["run_id"] == status_payload["data"]["run_id"] == "suggestion-1"
    assert service.actors[0].actor_type is ActorType.MODEL
    assert service.actors[1].actor_type is ActorType.HUMAN


@pytest.mark.parametrize(
    ("args", "expected_code"),
    [
        (["assist", "decide", "--request-file", "request.json"], "FMEA_REVIEW_CONFIRMATION_REQUIRED"),
        (["risk", "confirm", "--request-file", "request.json"], "FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED"),
        (["risk", "reject", "--request-file", "request.json"], "FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED"),
    ],
)
def test_human_mutations_require_explicit_cli_confirmation(
    args: list[str], expected_code: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert fmea_skill.main(args) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == expected_code


def test_task5_cli_never_accepts_model_or_provider_override(capsys: pytest.CaptureFixture[str]) -> None:
    assert fmea_skill.main(["risk", "show", "--row-id", "row-1", "--model", "attacker"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "FMEA_REVIEW_REQUEST_INVALID"
    assert "attacker" not in json.dumps(payload)
