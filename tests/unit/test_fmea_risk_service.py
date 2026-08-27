from __future__ import annotations

from dataclasses import replace

import pytest

from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.scoring import ScoringRulePack
from core_domain.fmea.states import ActorType, RiskStatus
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.review_contracts import ActorContext
from fmea_application.review_errors import ReviewError
from fmea_application.risk_contracts import (
    ConfirmRiskCommand,
    RejectRiskCommand,
    RiskConfirmationResult,
    RiskDependencySnapshot,
    StartRiskProposalCommand,
)


def _service_type():
    from fmea_application.risk_service import RiskAssessmentService

    return RiskAssessmentService


def _domain_pack() -> DomainPackManifest:
    return DomainPackManifest(
        pack_id="fuel-combustion",
        version="1.0.0",
        content_hash="a" * 64,
        compatible_schema_ids=("graphrag.fmea.v1",),
        analysis_types=("design_fmea",),
        template_identities=(("fuel-combustion-fmea", "1.0.0"),),
        scoring_rule_identities=(("fuel-sod-rpn", "1.0.0"),),
        propagation_rule_identities=(),
        extension_fields=(),
    )


def _rule_pack() -> ScoringRulePack:
    return ScoringRulePack(
        rule_pack_id="fuel-sod-rpn",
        version="1.0.0",
        applicable_analysis_types=("design_fmea",),
        severity_anchors=((1, "low"),),
        occurrence_window="operating_hours",
        occurrence_denominator="1000_hours",
        detection_positions=("sensor",),
        score_min=1,
        score_max=10,
        rpn_formula_version="S*O*D-1",
        risk_matrix_version="matrix-1",
        decision_priority_version="priority-1",
        high_priority_rpn=200,
    )


class _ContextProvider:
    def __init__(self, context):
        self.context = context

    def get_context(self, row_id: str, actor: ActorContext):
        assert row_id == self.context.row.row_id
        return self.context


class _Registry:
    def __init__(self, value):
        self.value = value

    def get(self, *_args):
        return self.value


class _AssistanceRepository:
    def __init__(self) -> None:
        self.saved = []
        self.calls = []

    def save_suggestion(self, prepared):
        self.calls.append("suggestion")
        self.saved.append(prepared)
        return prepared.suggestion

    def get_suggestion(self, suggestion_id: str, workspace_id: str):
        for prepared in self.saved:
            if prepared.suggestion.suggestion_id == suggestion_id and prepared.suggestion.workspace_id == workspace_id:
                return prepared.suggestion
        return None


class _RiskRepository:
    def __init__(self, row, pack) -> None:
        self.row = row
        self.pack = pack
        self.current = None
        self.proposal = None
        self.calls = []

    def get_row(self, row_id: str, workspace_id: str):
        if row_id == self.row.row_id and workspace_id == "ws-1":
            return self.row
        return None

    def get_evidence_pack(self, pack_id: str, workspace_id: str):
        if pack_id == self.pack.pack_id and workspace_id == self.pack.workspace_id:
            return self.pack
        return None

    def get_current_assessment(self, row_id: str, workspace_id: str):
        if row_id == self.row.row_id and workspace_id == "ws-1":
            return self.current
        return None

    def get_proposal(self, proposal_id: str, workspace_id: str):
        if self.proposal is not None and self.proposal.proposal_id == proposal_id and workspace_id == "ws-1":
            return self.proposal
        return None

    def save_proposal(self, prepared):
        self.calls.append("proposal")
        self.proposal = prepared.proposal
        self.current = prepared.assessment
        return self.current

    def replay_confirmation(self, scope, payload_hash):
        return None

    def commit_confirmation(self, prepared):
        self.calls.append("confirm")
        self.current = prepared.assessment
        return RiskConfirmationResult(
            assessment=prepared.assessment,
            decision_id=prepared.decision_id,
            audit_event_id=prepared.audit.event_id,
            outbox_event_id=f"outbox-{prepared.decision_id}",
        )

    def reject(self, prepared):
        self.calls.append("reject")
        self.current = prepared.assessment
        return self.current

    def invalidate(self, prepared):
        self.calls.append("invalidate")
        self.current = prepared.assessment
        return self.current


class _RiskGenerator:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, request):
        self.calls.append(request)
        return AssistanceSuggestion(
            suggestion_id="risk-suggestion-1",
            kind=AssistanceKind.SCORE_RECOMMENDATION,
            workspace_id="ws-1",
            target_type="fmea_row",
            target_id=request.context.row.row_id,
            target_record_version=request.context.row.record_version,
            evidence_pack_ids=(request.evidence_pack.pack_id,),
            payload={
                "dimensions": [
                    {"name": "severity", "value": 9, "evidence_ids": ["ev-1"], "reason": "severe", "uncertainty": None},
                    {"name": "occurrence", "value": 3, "evidence_ids": ["ev-1"], "reason": "occasional", "uncertainty": None},
                    {"name": "detection", "value": 4, "evidence_ids": ["ev-1"], "reason": "detectable", "uncertainty": None},
                ],
                "reason": "bounded evidence proposal",
                "uncertainty": None,
            },
            evidence_ids=("ev-1",),
            model_hash="a" * 64,
            prompt_hash="b" * 64,
            run_id=request.run_id,
            trace_id="risk-trace-1",
            domain_pack_id=request.domain_pack.pack_id,
            domain_pack_version=request.domain_pack.version,
            template_id=request.template_id,
            template_version=request.template_version,
            rule_pack_id=request.rule_pack.rule_pack_id,
            rule_pack_version=request.rule_pack.version,
            created_at="2026-08-28T00:00:00Z",
        )


def _service(fixture_review_row, fixture_pack, fixture_review_context):
    assistance = _AssistanceRepository()
    risk = _RiskRepository(fixture_review_row, fixture_pack)
    service = _service_type()(
        risk,
        assistance_repository=assistance,
        domain_pack_registry=_Registry(_domain_pack()),
        scoring_rule_registry=_Registry(_rule_pack()),
        generator=_RiskGenerator(),
        context_provider=_ContextProvider(fixture_review_context),
        clock=lambda: "2026-08-28T00:00:01Z",
    )
    return service, risk, assistance


def _start() -> StartRiskProposalCommand:
    return StartRiskProposalCommand(
        row_id="row-1",
        expected_record_version=1,
        evidence_pack_id="pack-1",
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        template_id="fuel-combustion-fmea",
        template_version="1.0.0",
        rule_pack_id="fuel-sod-rpn",
        rule_pack_version="1.0.0",
        idempotency_key="00000000-0000-4000-8000-000000000002",
    )


def _model() -> ActorContext:
    return ActorContext("model-1", ActorType.MODEL, frozenset(), "ws-1")


def _reviewer() -> ActorContext:
    return ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"risk_reviewer"}), "ws-1")


def test_model_proposal_is_proposed_only_and_cannot_confirm(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, risk, assistance = _service(fixture_review_row, fixture_pack, fixture_review_context)

    proposal = service.propose(_start(), _model())

    assert proposal.status is RiskStatus.PROPOSED
    assert proposal.derived is None
    assert assistance.calls + risk.calls == ["suggestion", "proposal"]
    with pytest.raises(ReviewError, match="FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED"):
        service.confirm(
            ConfirmRiskCommand(
                row_id="row-1",
                proposal_id=proposal.proposal_id,
                expected_assessment_version=1,
                idempotency_key="00000000-0000-4000-8000-000000000003",
                ),
            _model(),
        )


def test_human_confirmation_uses_deterministic_calculation_and_versions(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, risk, _ = _service(fixture_review_row, fixture_pack, fixture_review_context)
    proposal = service.propose(_start(), _model())

    result = service.confirm(
        ConfirmRiskCommand(
            row_id="row-1",
            proposal_id=proposal.proposal_id,
            expected_assessment_version=1,
            idempotency_key="00000000-0000-4000-8000-000000000003",
        ),
        _reviewer(),
    )

    assert result.assessment.status is RiskStatus.CONFIRMED
    assert result.assessment.record_version == 2
    assert result.assessment.derived is not None
    assert result.assessment.derived.rpn == 108
    assert risk.calls[-1] == "confirm"


def test_confirmed_risk_is_invalidated_once_after_row_version_change(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, risk, _ = _service(fixture_review_row, fixture_pack, fixture_review_context)
    proposal = service.propose(_start(), _model())
    confirmed = service.confirm(
        ConfirmRiskCommand(
            row_id="row-1",
            proposal_id=proposal.proposal_id,
            expected_assessment_version=1,
            idempotency_key="00000000-0000-4000-8000-000000000003",
        ),
        _reviewer(),
    )
    risk.row = replace(risk.row, record_version=2)
    dependencies = RiskDependencySnapshot(
        workspace_id="ws-1",
        row_id="row-1",
        row_version=2,
        evidence_pack_id="pack-1",
        evidence_pack_hash=fixture_pack.pack_hash,
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        template_id="fuel-combustion-fmea",
        template_version="1.0.0",
        rule_pack_id="fuel-sod-rpn",
        rule_pack_version="1.0.0",
    )

    invalidated = service.invalidate_if_stale("row-1", dependencies, ActorContext("risk-system", ActorType.SYSTEM, frozenset(), "ws-1"))

    assert confirmed.assessment.status is RiskStatus.CONFIRMED
    assert invalidated is not None
    assert invalidated.status is RiskStatus.INVALIDATED
    assert invalidated.derived is None
    assert service.invalidate_if_stale("row-1", dependencies, ActorContext("risk-system", ActorType.SYSTEM, frozenset(), "ws-1")) == invalidated
    assert risk.calls.count("invalidate") == 1


def test_reject_requires_risk_reviewer_and_exact_expected_version(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, _, _ = _service(fixture_review_row, fixture_pack, fixture_review_context)
    proposal = service.propose(_start(), _model())
    command = RejectRiskCommand(
        row_id="row-1",
        proposal_id=proposal.proposal_id,
        expected_assessment_version=1,
        idempotency_key="00000000-0000-4000-8000-000000000004",
        reason="evidence is insufficient",
    )

    with pytest.raises(ReviewError) as captured:
        service.reject(command, ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1"))
    assert captured.value.code == "FMEA_REVIEW_FORBIDDEN"
    assert service.reject(command, _reviewer()).status is RiskStatus.REVIEWED
