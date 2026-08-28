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
    risk_context_hash,
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
        self.history = {}
        self.confirmation_replays = {}
        self.rejection_replays = {}

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

    def get_assessment_version(self, row_id: str, workspace_id: str, record_version: int):
        if row_id != self.row.row_id or workspace_id != "ws-1":
            return None
        return self.history.get(record_version)

    def get_proposal(self, proposal_id: str, workspace_id: str):
        if self.proposal is not None and self.proposal.proposal_id == proposal_id and workspace_id == "ws-1":
            return self.proposal
        return None

    def save_proposal(self, prepared):
        self.calls.append("proposal")
        self.proposal = prepared.proposal
        self.current = prepared.assessment
        self.history[self.current.record_version] = self.current
        return self.current

    def replay_confirmation(self, scope, payload_hash):
        result = self.confirmation_replays.get((scope.scope_key, payload_hash))
        if result is None and any(key == scope.scope_key for key, _ in self.confirmation_replays):
            raise ReviewError("FMEA_IDEMPOTENCY_CONFLICT", "confirmation key is already bound")
        return result

    def commit_confirmation(self, prepared):
        self.calls.append("confirm")
        self.current = prepared.assessment
        self.history[self.current.record_version] = self.current
        result = RiskConfirmationResult(
            assessment=prepared.assessment,
            decision_id=prepared.decision_id,
            audit_event_id=prepared.audit.event_id,
            outbox_event_id=f"outbox-{prepared.decision_id}",
        )
        self.confirmation_replays[(prepared.scope.scope_key, prepared.payload_hash)] = replace(result, replayed=True)
        return result

    def replay_rejection(self, scope, payload_hash):
        result = self.rejection_replays.get((scope.scope_key, payload_hash))
        if result is None and any(key == scope.scope_key for key, _ in self.rejection_replays):
            raise ReviewError("FMEA_IDEMPOTENCY_CONFLICT", "rejection key is already bound")
        return result

    def reject(self, prepared):
        self.calls.append("reject")
        self.current = prepared.assessment
        self.history[self.current.record_version] = self.current
        self.rejection_replays[(prepared.scope.scope_key, prepared.payload_hash)] = self.current
        return self.current

    def invalidate(self, prepared):
        self.calls.append("invalidate")
        self.current = prepared.assessment
        self.history[self.current.record_version] = self.current
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
                "binding": {
                    "operating_context_hash": risk_context_hash(request.context),
                    "evidence_pack_hash": request.evidence_pack.pack_hash.removeprefix("sha256:"),
                    "model_template_id": "fmea-risk-proposal",
                    "model_template_version": "1.0.0",
                },
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
    generator = _RiskGenerator()
    risk.generator = generator
    service = _service_type()(
        risk,
        assistance_repository=assistance,
        domain_pack_registry=_Registry(_domain_pack()),
        scoring_rule_registry=_Registry(_rule_pack()),
        generator=generator,
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


def test_proposal_run_is_durably_resolved_by_persisted_suggestion_identity(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, _, _ = _service(fixture_review_row, fixture_pack, fixture_review_context)
    proposal = service.propose(_start(), _model())

    assert service.get_proposal_run("risk-suggestion-1", _reviewer()) is proposal
    with pytest.raises(ReviewError) as captured:
        service.get_proposal_run("missing-run", _reviewer())
    assert captured.value.code == "FMEA_REVIEW_SUGGESTION_NOT_FOUND"


def test_missing_row_and_evidence_use_declared_transport_safe_error_codes(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, _, _ = _service(fixture_review_row, fixture_pack, fixture_review_context)

    with pytest.raises(ReviewError) as missing_row:
        service.propose(replace(_start(), row_id="missing-row"), _model())
    assert missing_row.value.code == "FMEA_ROW_NOT_FOUND"

    with pytest.raises(ReviewError) as missing_evidence:
        service.propose(replace(_start(), evidence_pack_id="missing-pack"), _model())
    assert missing_evidence.value.code == "FMEA_EVIDENCE_INVALID"


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
        operating_context_hash=risk_context_hash(fixture_review_context),
    )

    invalidated = service.invalidate_if_stale("row-1", dependencies, ActorContext("risk-system", ActorType.SYSTEM, frozenset(), "ws-1"))

    assert confirmed.assessment.status is RiskStatus.CONFIRMED
    assert invalidated is not None
    assert invalidated.status is RiskStatus.INVALIDATED
    assert invalidated.derived is None
    assert invalidated.invalidated_reason is not None
    assert "sha256:" in invalidated.invalidated_reason
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


def test_confirmation_invalidates_instead_of_confirming_after_row_change(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, risk, _ = _service(fixture_review_row, fixture_pack, fixture_review_context)
    proposal = service.propose(_start(), _model())
    risk.row = replace(risk.row, record_version=2)

    with pytest.raises(ReviewError) as captured:
        service.confirm(
            ConfirmRiskCommand(
                row_id="row-1",
                proposal_id=proposal.proposal_id,
                expected_assessment_version=1,
                idempotency_key="00000000-0000-4000-8000-000000000006",
            ),
            _reviewer(),
        )

    assert captured.value.code == "FMEA_VERSION_CONFLICT"
    assert risk.current.status is RiskStatus.INVALIDATED
    assert risk.current.derived is None


def test_same_proposal_command_replays_without_calling_model_again(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, risk, assistance = _service(fixture_review_row, fixture_pack, fixture_review_context)

    first = service.propose(_start(), _model())
    second = service.propose(_start(), _model())

    assert second == first
    assert len(risk.generator.calls) == 1
    assert assistance.calls == ["suggestion"]
    assert risk.calls == ["proposal"]


def test_same_confirmation_command_replays_before_current_version_check(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, risk, _ = _service(fixture_review_row, fixture_pack, fixture_review_context)
    proposed = service.propose(_start(), _model())
    command = ConfirmRiskCommand(
        row_id="row-1",
        proposal_id=proposed.proposal_id,
        expected_assessment_version=1,
        idempotency_key="00000000-0000-4000-8000-000000000003",
    )

    first = service.confirm(command, _reviewer())
    replayed = service.confirm(command, _reviewer())

    assert replayed.assessment == first.assessment
    assert replayed.replayed is True
    assert risk.calls.count("confirm") == 1


def test_same_rejection_command_replays_before_current_version_check(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, risk, _ = _service(fixture_review_row, fixture_pack, fixture_review_context)
    proposed = service.propose(_start(), _model())
    command = RejectRiskCommand(
        row_id="row-1",
        proposal_id=proposed.proposal_id,
        expected_assessment_version=1,
        idempotency_key="00000000-0000-4000-8000-000000000004",
        reason="evidence is insufficient",
    )

    first = service.reject(command, _reviewer())
    replayed = service.reject(command, _reviewer())

    assert replayed == first
    assert risk.calls.count("reject") == 1


def test_rejection_replay_binds_the_human_reason(
    fixture_review_row, fixture_pack, fixture_review_context
) -> None:
    service, _, _ = _service(fixture_review_row, fixture_pack, fixture_review_context)
    proposed = service.propose(_start(), _model())
    first = RejectRiskCommand(
        row_id="row-1",
        proposal_id=proposed.proposal_id,
        expected_assessment_version=1,
        idempotency_key="00000000-0000-4000-8000-000000000004",
        reason="evidence is insufficient",
    )
    service.reject(first, _reviewer())

    with pytest.raises(ReviewError) as captured:
        service.reject(replace(first, reason="different human rationale"), _reviewer())

    assert captured.value.code == "FMEA_IDEMPOTENCY_CONFLICT"
