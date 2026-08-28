"""Structural application ports for FMEA evidence handoff."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from core_domain.fmea.contracts import (
    ActorType,
    EvidencePack,
    EvidenceRef,
    FmeaAnalysis,
    FmeaRow,
    PropagationEdge,
    VersionSet,
)
from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.propagation import PropagationRulePack, TopologyInterface, TopologySnapshot
from core_domain.fmea.scoring import RiskAssessmentRecord, RiskProposal, ScoringRulePack
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile

from .assistance_contracts import (
    AssistanceDecision,
    AssistanceHandlerCheckpoint,
    AssistanceRequest,
    AssistanceSuggestion,
)
from .review_contracts import (
    ActorContext,
    AuditEvent,
    IdempotencyScope,
    PreparedReviewDecision,
    PreparedSuggestionRun,
    ReviewCandidateBundle,
    ReviewDecisionRecord,
    ReviewDecisionResult,
    ReviewModelManifest,
    ReviewModelRequest,
    ReviewSourceSnapshot,
    ReviewSuggestion,
    ReviewSuggestionDraft,
    ReviewSuggestionRun,
    SuggestionRunReservation,
)
from .risk_contracts import (
    OutboxEvent,
    PreparedAssistanceDecision,
    PreparedAssistanceSuggestion,
    PreparedRiskConfirmation,
    PreparedRiskInvalidation,
    PreparedRiskProposal,
    PreparedRiskRejection,
    RiskConfirmationResult,
    RiskModelRequest,
)

ReviewHistoryPosition = tuple[str, str]


@dataclass(frozen=True, slots=True)
class EvidenceRequest:
    workspace_id: str
    analysis_id: str
    query: str
    versions: VersionSet
    acl_scope: tuple[str, ...]
    evidence_profile: EvidenceSelectionProfile = EvidenceSelectionProfile.COMBINED
    evidence_types: tuple[CitationType, ...] = ()
    max_hits: int = 20

    def __post_init__(self) -> None:
        object.__setattr__(self, "acl_scope", tuple(self.acl_scope))
        object.__setattr__(self, "evidence_types", tuple(self.evidence_types))
        if not 1 <= self.max_hits <= 100:
            raise ValueError("max_hits must be between 1 and 100")  # noqa: TRY003
        if self.evidence_profile is EvidenceSelectionProfile.CUSTOM:
            if not self.evidence_types:
                raise ValueError("custom evidence profile requires evidence_types")  # noqa: TRY003
        elif self.evidence_types:
            raise ValueError("evidence_types require the custom evidence profile")  # noqa: TRY003
        if len(self.evidence_types) != len(set(self.evidence_types)):
            raise ValueError("evidence_types must not contain duplicates")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    pack: EvidencePack
    profile: EvidenceSelectionProfile
    source_counts: tuple[tuple[CitationType, int], ...]
    warnings: tuple[str, ...]
    incomplete: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_counts", tuple(self.source_counts))
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True, slots=True)
class PropagationRequest:
    analysis: FmeaAnalysis
    evidence_pack: EvidencePack
    source_row_ids: tuple[str, ...]
    target_system: Literal["fuel", "combustion"]
    max_hops: int = 2
    max_edges: int = 40

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_row_ids", tuple(self.source_row_ids))


class EvidenceProvider(Protocol):
    def create_snapshot(self, request: EvidenceRequest) -> EvidenceSnapshot: ...

    def read_refs(self, pack: EvidencePack, evidence_ids: tuple[str, ...]) -> tuple[EvidenceRef, ...]: ...

    def load_pack(self, workspace_id: str, pack_id: str) -> EvidencePack: ...


class PropagationEvidenceProvider(Protocol):
    def find_propagation_edges(self, request: PropagationRequest) -> tuple[PropagationEdge, ...]: ...


class DomainPackRegistry(Protocol):
    def register(self, manifest: DomainPackManifest, source_bytes: bytes) -> DomainPackManifest: ...

    def get(self, pack_id: str, version: str) -> DomainPackManifest: ...


class ScoringRuleRegistry(Protocol):
    def register(self, rule_pack: ScoringRulePack, source_bytes: bytes) -> ScoringRulePack: ...

    def get(self, rule_pack_id: str, version: str) -> ScoringRulePack: ...


class PropagationRuleRegistry(Protocol):
    def get(self, rule_pack_id: str, version: str) -> PropagationRulePack: ...


class SystemTopologyPort(Protocol):
    def load_snapshot(self, topology_id: str, version: str) -> TopologySnapshot: ...

    def neighbors(self, snapshot: TopologySnapshot, entity_id: str) -> tuple[TopologyInterface, ...]: ...


class FmeaRepository(Protocol):
    def initialize(self) -> None: ...

    def save_analysis(
        self,
        analysis: FmeaAnalysis,
        *,
        actor_id: str,
        actor_type: ActorType,
        expected_record_version: int | None = None,
    ) -> FmeaAnalysis: ...

    def get_analysis(self, analysis_id: str) -> FmeaAnalysis | None: ...

    def save_evidence_pack(self, pack: EvidencePack, *, actor_id: str, actor_type: ActorType) -> EvidencePack: ...

    def get_evidence_pack(self, pack_id: str) -> EvidencePack | None: ...

    def save_row(
        self,
        row: FmeaRow,
        *,
        actor_id: str,
        actor_type: ActorType,
        expected_record_version: int | None = None,
    ) -> FmeaRow: ...

    def get_row(self, row_id: str) -> FmeaRow | None: ...

    def save_propagation_edge(
        self,
        edge: PropagationEdge,
        *,
        actor_id: str,
        actor_type: ActorType,
        expected_record_version: int | None = None,
    ) -> PropagationEdge: ...

    def get_propagation_edge(self, edge_id: str) -> PropagationEdge | None: ...

    def append_audit_event(
        self,
        *,
        actor_id: str,
        actor_type: ActorType,
        command: str,
        aggregate_type: str,
        aggregate_id: str,
        before_hash: str | None,
        after_hash: str | None,
        reason: str,
        versions: VersionSet,
    ) -> str: ...


class ReviewRepository(Protocol):
    def initialize(self) -> None: ...

    def save_review_candidate_bundle(
        self, bundle: ReviewCandidateBundle, actor: ActorContext
    ) -> tuple[FmeaRow, ...]: ...

    def get_row(self, row_id: str, workspace_id: str) -> FmeaRow | None: ...

    def get_review_source(self, row_id: str, workspace_id: str) -> ReviewSourceSnapshot | None: ...

    def get_evidence_pack(self, pack_id: str, workspace_id: str) -> EvidencePack | None: ...

    def list_suggestions(self, row_id: str, workspace_id: str) -> tuple[ReviewSuggestion, ...]: ...

    def page_suggestions(
        self,
        row_id: str,
        workspace_id: str,
        *,
        after: ReviewHistoryPosition | None = None,
        limit: int = 50,
    ) -> tuple[ReviewSuggestion, ...]: ...

    def list_decisions(self, row_id: str, workspace_id: str) -> tuple[ReviewDecisionRecord, ...]: ...

    def page_decisions(
        self,
        row_id: str,
        workspace_id: str,
        *,
        after: ReviewHistoryPosition | None = None,
        limit: int = 50,
    ) -> tuple[ReviewDecisionRecord, ...]: ...

    def reserve_suggestion_run(self, prepared: PreparedSuggestionRun) -> SuggestionRunReservation: ...

    def get_suggestion_run(self, run_id: str, workspace_id: str) -> ReviewSuggestionRun | None: ...

    def mark_suggestion_run_running(self, run_id: str, workspace_id: str) -> ReviewSuggestionRun: ...

    def complete_suggestion_run(
        self, run_id: str, workspace_id: str, suggestion: ReviewSuggestion, audit: AuditEvent
    ) -> ReviewSuggestionRun: ...

    def fail_suggestion_run(
        self, run_id: str, workspace_id: str, error_code: str, retryable: bool, audit: AuditEvent
    ) -> ReviewSuggestionRun: ...

    def replay_decision(self, scope: IdempotencyScope, payload_hash: str) -> ReviewDecisionResult | None: ...

    def commit_review_decision(self, prepared: PreparedReviewDecision) -> ReviewDecisionResult: ...


class ReviewSuggestionGenerator(Protocol):
    def generate(self, request: ReviewModelRequest) -> tuple[ReviewSuggestionDraft, ReviewModelManifest]: ...


class AnalysisAssistanceGenerator(Protocol):
    def generate(self, request: AssistanceRequest[object]) -> AssistanceSuggestion[object]: ...


class RiskSuggestionGenerator(Protocol):
    def generate(self, request: RiskModelRequest) -> AssistanceSuggestion[object]: ...


class AssistanceRepository(Protocol):
    """Persistence boundary for immutable model suggestions and human decisions."""

    def initialize(self) -> None: ...

    def save_suggestion(self, prepared: PreparedAssistanceSuggestion) -> AssistanceSuggestion[object]: ...

    def get_suggestion(self, suggestion_id: str, workspace_id: str) -> AssistanceSuggestion[object] | None: ...

    def append_decision(self, prepared: PreparedAssistanceDecision) -> AssistanceDecision: ...

    def get_decision(self, decision_id: str, workspace_id: str) -> AssistanceDecision | None: ...

    def reserve_decision(
        self,
        scope: IdempotencyScope,
        reservation_hash: str,
        decision_id: str,
        created_at: str,
    ) -> AssistanceDecision | None: ...

    def get_decision_handler_checkpoint(
        self,
        scope: IdempotencyScope,
        reservation_hash: str,
        decision_id: str,
    ) -> AssistanceHandlerCheckpoint | None: ...

    def claim_decision_handler(
        self,
        scope: IdempotencyScope,
        reservation_hash: str,
        decision_id: str,
    ) -> bool: ...

    def save_decision_handler_checkpoint(
        self,
        scope: IdempotencyScope,
        checkpoint: AssistanceHandlerCheckpoint,
    ) -> None: ...

    def replay_decision(self, scope: IdempotencyScope, payload_hash: str) -> AssistanceDecision | None: ...


class RiskRepository(Protocol):
    """Atomic storage boundary for risk proposals and human-reviewed lifecycle state."""

    def initialize(self) -> None: ...

    def register_pack_snapshots(
        self,
        workspace_id: str,
        domain_pack: DomainPackManifest,
        domain_source: bytes,
        rule_pack: ScoringRulePack,
        rule_source: bytes,
        created_at: str,
    ) -> None: ...

    def get_row(self, row_id: str, workspace_id: str) -> FmeaRow | None: ...

    def get_evidence_pack(self, pack_id: str, workspace_id: str) -> EvidencePack | None: ...

    def get_current_assessment(self, row_id: str, workspace_id: str) -> RiskAssessmentRecord | None: ...

    def get_assessment_version(
        self, row_id: str, workspace_id: str, record_version: int
    ) -> RiskAssessmentRecord | None: ...

    def get_proposal(self, proposal_id: str, workspace_id: str) -> RiskProposal | None: ...

    def save_proposal(self, prepared: PreparedRiskProposal) -> RiskAssessmentRecord: ...

    def replay_confirmation(self, scope: IdempotencyScope, payload_hash: str) -> RiskConfirmationResult | None: ...

    def replay_rejection(self, scope: IdempotencyScope, payload_hash: str) -> RiskAssessmentRecord | None: ...

    def commit_confirmation(self, prepared: PreparedRiskConfirmation) -> RiskConfirmationResult: ...

    def reject(self, prepared: PreparedRiskRejection) -> RiskAssessmentRecord: ...

    def invalidate(self, prepared: PreparedRiskInvalidation) -> RiskAssessmentRecord: ...

    def list_outbox_events(self, aggregate_id: str, workspace_id: str) -> tuple[OutboxEvent, ...]: ...


class ReviewRunExecutor(Protocol):
    def submit(self, run_id: str, operation: Callable[[], None]) -> None: ...

    def close(self) -> None: ...


__all__ = [
    "AnalysisAssistanceGenerator",
    "AssistanceRepository",
    "DomainPackRegistry",
    "EvidenceProvider",
    "EvidenceRequest",
    "EvidenceSnapshot",
    "FmeaRepository",
    "PropagationEvidenceProvider",
    "PropagationRequest",
    "PropagationRuleRegistry",
    "ReviewRepository",
    "ReviewRunExecutor",
    "ReviewSuggestionGenerator",
    "RiskRepository",
    "RiskSuggestionGenerator",
    "ScoringRuleRegistry",
    "SystemTopologyPort",
]
