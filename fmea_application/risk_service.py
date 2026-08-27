"""Provider-neutral orchestration for evidence-bound FMEA risk proposals."""

# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Protocol

from core_domain.fmea.entities import FmeaRow
from core_domain.fmea.scoring import (
    RiskAssessmentRecord,
    RiskProposal,
    ScoreDimension,
    ScoringRulePack,
    validate_risk_confirmation,
)
from core_domain.fmea.states import ActorType, RiskStatus
from core_domain.fmea.value_objects import EvidencePack

from .assistance_contracts import AssistanceKind, AssistanceSuggestion
from .assistance_service import make_audit, stable_id, utc_now
from .ports import (
    AssistanceRepository,
    DomainPackRegistry,
    RiskRepository,
    RiskSuggestionGenerator,
    ScoringRuleRegistry,
)
from .review_contracts import ActorContext, IdempotencyScope, ReviewContext, idempotency_key_hash
from .review_errors import ReviewError
from .risk_contracts import (
    ConfirmRiskCommand,
    PreparedAssistanceSuggestion,
    PreparedRiskConfirmation,
    PreparedRiskInvalidation,
    PreparedRiskProposal,
    PreparedRiskRejection,
    RejectRiskCommand,
    RiskConfirmationResult,
    RiskDependencySnapshot,
    RiskModelRequest,
    StartRiskProposalCommand,
    assistance_suggestion_payload_hash,
    risk_confirmation_payload_hash,
    risk_context_hash,
    risk_dependency_hash,
    risk_invalidation_payload_hash,
    risk_proposal_payload_hash,
    risk_rejection_payload_hash,
)


class RiskContextProvider(Protocol):
    def get_context(self, row_id: str, actor: ActorContext) -> ReviewContext: ...


def _invalid(message: str) -> ReviewError:
    return ReviewError("FMEA_REVIEW_REQUEST_INVALID", message)


def _require_model(actor: ActorContext) -> None:
    if actor.actor_type is not ActorType.MODEL:
        raise ReviewError("FMEA_REVIEW_FORBIDDEN", "a model actor is required to create a risk proposal")


def _require_risk_reviewer(actor: ActorContext) -> None:
    if actor.actor_type is not ActorType.HUMAN:
        raise ReviewError(
            "FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED",
            "FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED: a human risk reviewer is required",
        )
    if "risk_reviewer" not in actor.roles:
        raise ReviewError("FMEA_REVIEW_FORBIDDEN", "the risk_reviewer role is required")


def _scope(actor: ActorContext, command: str, path: str, idempotency_key: str) -> IdempotencyScope:
    return IdempotencyScope(
        workspace_id=actor.workspace_id,
        actor_id=actor.actor_id,
        command=command,
        resource_path=path,
        key_hash=idempotency_key_hash(idempotency_key),
    )


def _dimension(value: object) -> ScoreDimension:
    if not isinstance(value, Mapping):
        raise _invalid("risk proposal dimension is invalid")
    if set(value) != {"name", "value", "evidence_ids", "reason", "uncertainty"}:
        raise _invalid("risk proposal dimension fields are invalid")
    evidence_ids = value["evidence_ids"]
    if isinstance(evidence_ids, str | bytes) or not isinstance(evidence_ids, Sequence):
        raise _invalid("risk proposal evidence IDs are invalid")
    try:
        return ScoreDimension(
            name=value["name"],
            value=value["value"],
            evidence_ids=tuple(evidence_ids),
            reason=value["reason"],
            uncertainty=value["uncertainty"],
        )
    except (TypeError, ValueError) as exc:
        raise _invalid("risk proposal dimension is invalid") from exc


def _proposal_from_suggestion(
    suggestion: AssistanceSuggestion[object],
    *,
    proposal_id: str,
    created_at: str,
) -> RiskProposal:
    payload = suggestion.payload
    if not isinstance(payload, Mapping) or set(payload) != {"dimensions", "reason", "uncertainty", "binding"}:
        raise _invalid("risk suggestion payload is invalid")
    dimensions_value = payload["dimensions"]
    if isinstance(dimensions_value, str | bytes) or not isinstance(dimensions_value, Sequence):
        raise _invalid("risk suggestion dimensions are invalid")
    try:
        dimensions = tuple(_dimension(item) for item in dimensions_value)
        return RiskProposal(
            proposal_id=proposal_id,
            workspace_id=suggestion.workspace_id,
            row_id=suggestion.target_id,
            source_record_version=suggestion.target_record_version,
            evidence_pack_id=suggestion.evidence_pack_ids[0],
            dimensions=dimensions,
            domain_pack_id=suggestion.domain_pack_id or "",
            domain_pack_version=suggestion.domain_pack_version or "",
            rule_pack_id=suggestion.rule_pack_id or "",
            rule_pack_version=suggestion.rule_pack_version or "",
            reason=payload["reason"],
            created_at=created_at,
            assistance_suggestion_id=suggestion.suggestion_id,
            uncertainty=payload["uncertainty"],
        )
    except (TypeError, ValueError) as exc:
        raise _invalid("risk suggestion cannot form a proposal") from exc


def _binding(suggestion: AssistanceSuggestion[object]) -> Mapping[str, object]:
    payload = suggestion.payload
    if not isinstance(payload, Mapping):
        raise _invalid("risk suggestion binding is invalid")
    binding = payload.get("binding")
    if not isinstance(binding, Mapping) or set(binding) != {
        "operating_context_hash",
        "evidence_pack_hash",
        "model_template_id",
        "model_template_version",
    }:
        raise _invalid("risk suggestion binding is invalid")
    return binding


def _bounded_context_matches(row: FmeaRow, evidence_pack: EvidencePack, context: ReviewContext) -> bool:
    return (
        context.row == row
        and row.evidence_pack_id == evidence_pack.pack_id
        and context.evidence.pack_id == evidence_pack.pack_id
        and context.evidence.pack_hash.removeprefix("sha256:")
        == evidence_pack.pack_hash.removeprefix("sha256:")
    )


def _suggestion_matches_command(
    suggestion: AssistanceSuggestion[object],
    command: StartRiskProposalCommand,
    workspace_id: str,
) -> bool:
    return (
        suggestion.kind is AssistanceKind.SCORE_RECOMMENDATION
        and not suggestion.applied
        and suggestion.workspace_id == workspace_id
        and suggestion.target_type == "fmea_row"
        and suggestion.target_id == command.row_id
        and suggestion.target_record_version == command.expected_record_version
        and suggestion.evidence_pack_ids == (command.evidence_pack_id,)
        and suggestion.domain_pack_id == command.domain_pack_id
        and suggestion.domain_pack_version == command.domain_pack_version
        and suggestion.template_id == command.template_id
        and suggestion.template_version == command.template_version
        and suggestion.rule_pack_id == command.rule_pack_id
        and suggestion.rule_pack_version == command.rule_pack_version
    )


def _validate_server_binding(
    suggestion: AssistanceSuggestion[object], context: ReviewContext, evidence_pack: EvidencePack
) -> None:
    binding = _binding(suggestion)
    if (
        binding["operating_context_hash"] != risk_context_hash(context)
        or binding["evidence_pack_hash"] != evidence_pack.pack_hash.removeprefix("sha256:")
        or binding["model_template_id"] != "fmea-risk-proposal"
        or binding["model_template_version"] != "1.0.0"
    ):
        raise _invalid("risk generator changed a server-owned binding")


class RiskAssessmentService:
    def __init__(
        self,
        repository: RiskRepository,
        *,
        assistance_repository: AssistanceRepository,
        domain_pack_registry: DomainPackRegistry,
        scoring_rule_registry: ScoringRuleRegistry,
        generator: RiskSuggestionGenerator,
        context_provider: RiskContextProvider,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self._repository = repository
        self._assistance = assistance_repository
        self._domain_packs = domain_pack_registry
        self._rule_packs = scoring_rule_registry
        self._generator = generator
        self._contexts = context_provider
        self._clock = clock

    def _replay_proposal(
        self,
        command: StartRiskProposalCommand,
        actor: ActorContext,
        proposal_id: str,
    ) -> RiskAssessmentRecord | None:
        existing = self._repository.get_proposal(proposal_id, actor.workspace_id)
        if existing is None:
            return None
        initial = self._repository.get_assessment_version(command.row_id, actor.workspace_id, 1)
        suggestion = self._assistance.get_suggestion(existing.assistance_suggestion_id or "", actor.workspace_id)
        exact_replay = (
            initial is not None
            and suggestion is not None
            and initial.proposal_id == existing.proposal_id
            and existing.row_id == command.row_id
            and existing.source_record_version == command.expected_record_version
            and existing.evidence_pack_id == command.evidence_pack_id
            and existing.domain_pack_id == command.domain_pack_id
            and existing.domain_pack_version == command.domain_pack_version
            and existing.rule_pack_id == command.rule_pack_id
            and existing.rule_pack_version == command.rule_pack_version
            and suggestion.template_id == command.template_id
            and suggestion.template_version == command.template_version
        )
        if not exact_replay:
            raise ReviewError("FMEA_IDEMPOTENCY_CONFLICT", "risk proposal key is already bound")
        return initial

    def propose(self, command: StartRiskProposalCommand, actor: ActorContext) -> RiskAssessmentRecord:
        _require_model(actor)
        proposal_id = stable_id("risk-proposal", command.idempotency_key)
        replayed = self._replay_proposal(command, actor, proposal_id)
        if replayed is not None:
            return replayed
        row = self._repository.get_row(command.row_id, actor.workspace_id)
        if row is None:
            raise ReviewError("FMEA_REVIEW_ROW_NOT_FOUND", "risk row was not found")
        if row.record_version != command.expected_record_version:
            raise ReviewError("FMEA_VERSION_CONFLICT", "risk row version is stale")
        evidence_pack = self._repository.get_evidence_pack(command.evidence_pack_id, actor.workspace_id)
        if evidence_pack is None:
            raise ReviewError("FMEA_REVIEW_EVIDENCE_NOT_FOUND", "risk EvidencePack was not found")
        domain_pack = self._domain_packs.get(command.domain_pack_id, command.domain_pack_version)
        rule_pack = self._rule_packs.get(command.rule_pack_id, command.rule_pack_version)
        if (command.template_id, command.template_version) not in domain_pack.template_identities:
            raise _invalid("template identity is outside the DomainPack")
        if (command.rule_pack_id, command.rule_pack_version) not in domain_pack.scoring_rule_identities:
            raise _invalid("rule pack identity is outside the DomainPack")
        context = self._contexts.get_context(command.row_id, actor)
        if not _bounded_context_matches(row, evidence_pack, context):
            raise _invalid("bounded review context does not match the requested row and evidence")

        run_id = stable_id("risk-run", command.idempotency_key)
        suggestion = self._generator.generate(
            RiskModelRequest(
                run_id=run_id,
                context=context,
                evidence_pack=evidence_pack,
                domain_pack=domain_pack,
                rule_pack=rule_pack,
                template_id=command.template_id,
                template_version=command.template_version,
            )
        )
        if not isinstance(suggestion, AssistanceSuggestion):
            raise _invalid("risk generator returned an invalid suggestion")
        if not _suggestion_matches_command(suggestion, command, actor.workspace_id):
            raise _invalid("risk generator changed an immutable binding")
        _validate_server_binding(suggestion, context, evidence_pack)

        created_at = suggestion.created_at or self._clock()
        proposal = _proposal_from_suggestion(
            suggestion,
            proposal_id=proposal_id,
            created_at=created_at,
        )
        assessment = RiskAssessmentRecord(
            assessment_id=stable_id("risk-assessment", command.idempotency_key),
            workspace_id=actor.workspace_id,
            row_id=row.row_id,
            source_record_version=row.record_version,
            evidence_pack_id=evidence_pack.pack_id,
            domain_pack_id=domain_pack.pack_id,
            domain_pack_version=domain_pack.version,
            rule_pack_id=rule_pack.rule_pack_id,
            rule_pack_version=rule_pack.version,
            status=RiskStatus.PROPOSED,
            dimensions=proposal.dimensions,
            derived=None,
            proposal_id=proposal.proposal_id,
            assistance_suggestion_id=suggestion.suggestion_id,
            confirmer_actor_id=None,
            invalidated_reason=None,
            record_version=1,
            created_at=created_at,
            updated_at=created_at,
        )

        suggestion_scope = _scope(
            actor,
            "fmea.risk.suggestion.create",
            f"/fmea/rows/{row.row_id}/risk-suggestions/{suggestion.suggestion_id}",
            command.idempotency_key,
        )
        suggestion_hash = assistance_suggestion_payload_hash(suggestion_scope, suggestion)
        suggestion_audit = make_audit(
            actor=actor,
            scope=suggestion_scope,
            payload_hash=suggestion_hash,
            command=suggestion_scope.command,
            reason="model risk proposal",
            row_id=row.row_id,
            analysis_id=row.analysis_id,
            suggestion_id=suggestion.suggestion_id,
            decision_id=None,
            expected_record_version=row.record_version,
            applied_record_version=None,
            evidence_ids=suggestion.evidence_ids,
            template_id=command.template_id,
            template_version=command.template_version,
            scoring_version=rule_pack.version,
            occurred_at=created_at,
            event_id=stable_id("risk-suggestion-audit", command.idempotency_key),
            request_id=run_id,
            trace_id=suggestion.trace_id,
            run_id=run_id,
        )
        self._assistance.save_suggestion(
            PreparedAssistanceSuggestion(suggestion_scope, suggestion_hash, suggestion, suggestion_audit)
        )

        proposal_scope = _scope(
            actor,
            "fmea.risk.propose",
            f"/fmea/rows/{row.row_id}/risk-assessments",
            command.idempotency_key,
        )
        proposal_hash = risk_proposal_payload_hash(proposal_scope, proposal, assessment)
        proposal_audit = make_audit(
            actor=actor,
            scope=proposal_scope,
            payload_hash=proposal_hash,
            command=proposal_scope.command,
            reason=proposal.reason,
            row_id=row.row_id,
            analysis_id=row.analysis_id,
            suggestion_id=suggestion.suggestion_id,
            decision_id=None,
            expected_record_version=row.record_version,
            applied_record_version=assessment.record_version,
            evidence_ids=suggestion.evidence_ids,
            template_id=command.template_id,
            template_version=command.template_version,
            scoring_version=rule_pack.version,
            occurred_at=created_at,
            event_id=stable_id("risk-proposal-audit", command.idempotency_key),
            request_id=run_id,
            trace_id=suggestion.trace_id,
            run_id=run_id,
        )
        return self._repository.save_proposal(
            PreparedRiskProposal(proposal_scope, proposal_hash, proposal, assessment, proposal_audit)
        )

    def _replay_transition(
        self,
        command: ConfirmRiskCommand | RejectRiskCommand,
        actor: ActorContext,
    ) -> RiskConfirmationResult | RiskAssessmentRecord | None:
        proposal = self._repository.get_proposal(command.proposal_id, actor.workspace_id)
        if proposal is None or proposal.row_id != command.row_id:
            return None
        previous = self._repository.get_assessment_version(
            command.row_id, actor.workspace_id, command.expected_assessment_version
        )
        assessment = self._repository.get_assessment_version(
            command.row_id, actor.workspace_id, command.expected_assessment_version + 1
        )
        if previous is None or assessment is None or previous.proposal_id != proposal.proposal_id:
            return None
        if isinstance(command, ConfirmRiskCommand):
            if assessment.status is not RiskStatus.CONFIRMED:
                return None
            scope = _scope(
                actor,
                "fmea.risk.confirm",
                f"/fmea/rows/{proposal.row_id}/risk-confirmations",
                command.idempotency_key,
            )
            decision_id = stable_id("risk-confirmation", command.idempotency_key)
            payload_hash = risk_confirmation_payload_hash(
                scope, proposal, previous, assessment, command.expected_assessment_version, decision_id
            )
            return self._repository.replay_confirmation(scope, payload_hash)
        if assessment.status is not RiskStatus.REVIEWED:
            return None
        scope = _scope(
            actor,
            "fmea.risk.reject",
            f"/fmea/rows/{proposal.row_id}/risk-rejections",
            command.idempotency_key,
        )
        decision_id = stable_id("risk-rejection", command.idempotency_key)
        payload_hash = risk_rejection_payload_hash(
            scope,
            proposal,
            previous,
            assessment,
            command.expected_assessment_version,
            decision_id,
            command.reason,
        )
        return self._repository.replay_rejection(scope, payload_hash)

    def get(self, row_id: str, actor: ActorContext) -> RiskAssessmentRecord | None:
        return self._repository.get_current_assessment(row_id, actor.workspace_id)

    def _proposal_for_command(
        self,
        command: ConfirmRiskCommand | RejectRiskCommand,
        actor: ActorContext,
    ) -> tuple[
        RiskProposal,
        RiskAssessmentRecord,
        EvidencePack,
        ScoringRulePack,
        AssistanceSuggestion[object],
        FmeaRow,
    ]:
        current = self._repository.get_current_assessment(command.row_id, actor.workspace_id)
        if current is None:
            raise ReviewError("FMEA_REVIEW_ROW_NOT_FOUND", "risk assessment was not found")
        if current.record_version != command.expected_assessment_version:
            raise ReviewError("FMEA_VERSION_CONFLICT", "risk assessment version is stale")
        proposal = self._repository.get_proposal(command.proposal_id, actor.workspace_id)
        if proposal is None:
            raise _invalid("the exact risk proposal was not found")
        if current.proposal_id != proposal.proposal_id or current.dimensions != proposal.dimensions:
            raise ReviewError("FMEA_VERSION_CONFLICT", "risk proposal does not match current assessment")
        evidence_pack = self._repository.get_evidence_pack(proposal.evidence_pack_id, actor.workspace_id)
        if evidence_pack is None:
            raise ReviewError("FMEA_REVIEW_EVIDENCE_NOT_FOUND", "risk EvidencePack was not found")
        rule_pack = self._rule_packs.get(proposal.rule_pack_id, proposal.rule_pack_version)
        suggestion = self._assistance.get_suggestion(proposal.assistance_suggestion_id or "", actor.workspace_id)
        if suggestion is None:
            raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "risk suggestion was not found")
        row = self._repository.get_row(proposal.row_id, actor.workspace_id)
        if row is None:
            raise ReviewError("FMEA_REVIEW_ROW_NOT_FOUND", "risk row was not found")
        context = self._contexts.get_context(proposal.row_id, actor)
        domain_pack = self._domain_packs.get(proposal.domain_pack_id, proposal.domain_pack_version)
        binding = _binding(suggestion)
        if (
            row.record_version != proposal.source_record_version
            or row.evidence_pack_id != proposal.evidence_pack_id
            or context.row != row
            or context.evidence.pack_id != evidence_pack.pack_id
            or context.evidence.pack_hash.removeprefix("sha256:") != evidence_pack.pack_hash.removeprefix("sha256:")
            or binding["operating_context_hash"] != risk_context_hash(context)
            or binding["evidence_pack_hash"] != evidence_pack.pack_hash.removeprefix("sha256:")
            or (suggestion.template_id, suggestion.template_version) not in domain_pack.template_identities
            or (proposal.rule_pack_id, proposal.rule_pack_version) not in domain_pack.scoring_rule_identities
        ):
            self.invalidate_if_stale(
                proposal.row_id,
                RiskDependencySnapshot(
                    workspace_id=actor.workspace_id,
                    row_id=proposal.row_id,
                    row_version=row.record_version,
                    evidence_pack_id=evidence_pack.pack_id,
                    evidence_pack_hash=evidence_pack.pack_hash.removeprefix("sha256:"),
                    domain_pack_id=domain_pack.pack_id,
                    domain_pack_version=domain_pack.version,
                    template_id=suggestion.template_id or "unbound",
                    template_version=suggestion.template_version or "unbound",
                    rule_pack_id=rule_pack.rule_pack_id,
                    rule_pack_version=rule_pack.version,
                    operating_context_hash=risk_context_hash(context),
                ),
                actor,
            )
            raise ReviewError("FMEA_VERSION_CONFLICT", "risk proposal dependencies are stale")
        return proposal, current, evidence_pack, rule_pack, suggestion, row

    def confirm(self, command: ConfirmRiskCommand, actor: ActorContext) -> RiskConfirmationResult:
        _require_risk_reviewer(actor)
        replayed = self._replay_transition(command, actor)
        if isinstance(replayed, RiskConfirmationResult):
            return replayed
        proposal, previous, evidence_pack, rule_pack, suggestion, row = self._proposal_for_command(command, actor)
        if suggestion.conflict_ids and rule_pack.conflict_score_policy == "block_rpn":
            raise _invalid("conflicting risk evidence cannot be confirmed")
        try:
            derived = validate_risk_confirmation(proposal, rule_pack=rule_pack, evidence_pack=evidence_pack)
        except (TypeError, ValueError) as exc:
            raise _invalid("risk proposal cannot be confirmed") from exc
        updated_at = self._clock()
        assessment = replace(
            previous,
            status=RiskStatus.CONFIRMED,
            derived=derived,
            confirmer_actor_id=actor.actor_id,
            invalidated_reason=None,
            record_version=previous.record_version + 1,
            updated_at=updated_at,
        )
        scope = _scope(actor, "fmea.risk.confirm", f"/fmea/rows/{proposal.row_id}/risk-confirmations", command.idempotency_key)
        decision_id = stable_id("risk-confirmation", command.idempotency_key)
        payload_hash = risk_confirmation_payload_hash(
            scope, proposal, previous, assessment, command.expected_assessment_version, decision_id
        )
        replayed = self._repository.replay_confirmation(scope, payload_hash)
        if replayed is not None:
            return replayed
        audit = make_audit(
            actor=actor,
            scope=scope,
            payload_hash=payload_hash,
            command=scope.command,
            reason="human risk confirmation",
            row_id=proposal.row_id,
            analysis_id=row.analysis_id,
            suggestion_id=proposal.assistance_suggestion_id,
            decision_id=decision_id,
            expected_record_version=previous.record_version,
            applied_record_version=assessment.record_version,
            evidence_ids=derived.evidence_ids,
            template_id=suggestion.template_id or "unbound",
            template_version=suggestion.template_version or "unbound",
            scoring_version=proposal.rule_pack_version,
            occurred_at=updated_at,
            event_id=stable_id("risk-confirmation-audit", command.idempotency_key),
            request_id=decision_id,
            trace_id=suggestion.trace_id,
            run_id=suggestion.run_id,
        )
        return self._repository.commit_confirmation(
            PreparedRiskConfirmation(
                scope,
                payload_hash,
                proposal,
                previous,
                assessment,
                command.expected_assessment_version,
                decision_id,
                audit,
            )
        )

    def reject(self, command: RejectRiskCommand, actor: ActorContext) -> RiskAssessmentRecord:
        _require_risk_reviewer(actor)
        replayed = self._replay_transition(command, actor)
        if isinstance(replayed, RiskAssessmentRecord):
            return replayed
        proposal, previous, _evidence_pack, _rule_pack, suggestion, row = self._proposal_for_command(command, actor)
        updated_at = self._clock()
        assessment = replace(
            previous,
            status=RiskStatus.REVIEWED,
            derived=None,
            confirmer_actor_id=None,
            invalidated_reason=None,
            record_version=previous.record_version + 1,
            updated_at=updated_at,
        )
        scope = _scope(actor, "fmea.risk.reject", f"/fmea/rows/{proposal.row_id}/risk-rejections", command.idempotency_key)
        decision_id = stable_id("risk-rejection", command.idempotency_key)
        payload_hash = risk_rejection_payload_hash(
            scope,
            proposal,
            previous,
            assessment,
            command.expected_assessment_version,
            decision_id,
            command.reason,
        )
        replayed = self._repository.replay_rejection(scope, payload_hash)
        if replayed is not None:
            return replayed
        audit = make_audit(
            actor=actor,
            scope=scope,
            payload_hash=payload_hash,
            command=scope.command,
            reason=command.reason,
            row_id=proposal.row_id,
            analysis_id=row.analysis_id,
            suggestion_id=proposal.assistance_suggestion_id,
            decision_id=decision_id,
            expected_record_version=previous.record_version,
            applied_record_version=assessment.record_version,
            evidence_ids=suggestion.evidence_ids,
            template_id=suggestion.template_id or "unbound",
            template_version=suggestion.template_version or "unbound",
            scoring_version=proposal.rule_pack_version,
            occurred_at=updated_at,
            event_id=stable_id("risk-rejection-audit", command.idempotency_key),
            request_id=decision_id,
            trace_id=suggestion.trace_id,
            run_id=suggestion.run_id,
        )
        return self._repository.reject(
            PreparedRiskRejection(
                scope,
                payload_hash,
                proposal,
                previous,
                assessment,
                command.expected_assessment_version,
                decision_id,
                audit,
            )
        )

    def invalidate_if_stale(
        self,
        row_id: str,
        dependencies: RiskDependencySnapshot,
        actor: ActorContext,
    ) -> RiskAssessmentRecord | None:
        if actor.actor_type is ActorType.MODEL:
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "a model actor cannot invalidate risk")
        if actor.workspace_id != dependencies.workspace_id or row_id != dependencies.row_id:
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "risk dependency workspace or row does not match")
        previous = self._repository.get_current_assessment(row_id, actor.workspace_id)
        if previous is None or previous.status is RiskStatus.INVALIDATED:
            return previous
        evidence_pack = self._repository.get_evidence_pack(previous.evidence_pack_id, actor.workspace_id)
        suggestion = self._assistance.get_suggestion(previous.assistance_suggestion_id or "", actor.workspace_id)
        if evidence_pack is None or suggestion is None:
            stale_reasons = ["bound dependency is missing"]
        else:
            binding = _binding(suggestion)
            stale_reasons = []
            checks = (
                (previous.source_record_version, dependencies.row_version, "row version"),
                (previous.evidence_pack_id, dependencies.evidence_pack_id, "evidence pack"),
                (evidence_pack.pack_hash, dependencies.evidence_pack_hash, "evidence hash"),
                (previous.domain_pack_id, dependencies.domain_pack_id, "domain pack"),
                (previous.domain_pack_version, dependencies.domain_pack_version, "domain pack version"),
                (suggestion.template_id, dependencies.template_id, "template"),
                (suggestion.template_version, dependencies.template_version, "template version"),
                (previous.rule_pack_id, dependencies.rule_pack_id, "rule pack"),
                (previous.rule_pack_version, dependencies.rule_pack_version, "rule pack version"),
                (binding["operating_context_hash"], dependencies.operating_context_hash, "operating context"),
            )
            stale_reasons.extend(label for actual, expected, label in checks if actual != expected)
        if not stale_reasons:
            return previous

        idempotency_key = stable_id(
            "risk-invalidation-key",
            actor.workspace_id,
            row_id,
            previous.record_version,
            dependencies,
        ).removeprefix("risk-invalidation-key-")
        # stable_id embeds a UUID after the prefix; the repository contract requires the UUID itself.
        scope = _scope(actor, "fmea.risk.invalidate", f"/fmea/rows/{row_id}/risk-invalidations", idempotency_key)
        updated_at = self._clock()
        assessment_id = (
            stable_id("risk-invalidated-assessment", idempotency_key)
            if previous.status is RiskStatus.CONFIRMED
            else previous.assessment_id
        )
        assessment = replace(
            previous,
            assessment_id=assessment_id,
            status=RiskStatus.INVALIDATED,
            derived=None,
            confirmer_actor_id=None,
            invalidated_reason=(
                f"stale dependencies [sha256:{risk_dependency_hash(dependencies)}]: "
                + ", ".join(stale_reasons)
            ),
            record_version=previous.record_version + 1,
            updated_at=updated_at,
        )
        decision_id = stable_id("risk-invalidation", idempotency_key)
        payload_hash = risk_invalidation_payload_hash(
            scope, previous, assessment, previous.record_version, decision_id
        )
        source_row = self._repository.get_row(row_id, actor.workspace_id)
        audit = make_audit(
            actor=actor,
            scope=scope,
            payload_hash=payload_hash,
            command=scope.command,
            reason=assessment.invalidated_reason or "stale dependencies",
            row_id=row_id,
            analysis_id=source_row.analysis_id if source_row is not None else row_id,
            suggestion_id=previous.assistance_suggestion_id,
            decision_id=decision_id,
            expected_record_version=previous.record_version,
            applied_record_version=assessment.record_version,
            evidence_ids=tuple(item.evidence_id for item in evidence_pack.refs) if evidence_pack is not None else (),
            template_id=(suggestion.template_id if suggestion is not None else None) or "unbound",
            template_version=(suggestion.template_version if suggestion is not None else None) or "unbound",
            scoring_version=previous.rule_pack_version,
            occurred_at=updated_at,
            event_id=stable_id("risk-invalidation-audit", idempotency_key),
            request_id=decision_id,
            trace_id=suggestion.trace_id if suggestion is not None else decision_id,
            run_id=suggestion.run_id if suggestion is not None else None,
        )
        return self._repository.invalidate(
            PreparedRiskInvalidation(
                scope,
                payload_hash,
                previous,
                assessment,
                previous.record_version,
                decision_id,
                audit,
            )
        )


__all__ = ["RiskAssessmentService", "RiskContextProvider"]
