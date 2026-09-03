"""Structural application ports for FMEA evidence handoff."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

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
from core_domain.fmea.governance import (
    ApprovalDecision,
    ApprovalSubmission,
    ApprovalWithdrawalRecord,
    FmeaRevision,
    PublicationLifecycleView,
    PublishedRevision,
)
from core_domain.fmea.propagation import (
    PropagationGraphRevision,
    PropagationRulePack,
    TopologyInterface,
    TopologySnapshot,
)
from core_domain.fmea.scoring import RiskAssessmentRecord, RiskProposal, ScoringRulePack
from core_domain.fmea.template_migration import (
    MigrationReport,
    TemplateDraft,
)
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile

from .assistance_contracts import (
    AssistanceDecision,
    AssistanceHandlerCheckpoint,
    AssistanceRequest,
    AssistanceSuggestion,
)
from .governance_contracts import (
    ApprovalResult,
    ApprovalSubmissionResult,
    ExportEligibilityRecord,
    GovernanceHistoryQuery,
    PreparedApproval,
    PreparedApprovalSubmission,
    PreparedApprovalWithdrawal,
    PreparedPublication,
    PreparedPublicationWithdrawal,
    PreparedReadinessReport,
    PreparedRevision,
    PreparedSupersession,
    PublicationResult,
    PublicationWithdrawalResult,
    ReadinessReportRecord,
    ReadinessResult,
    RevisionResult,
    SupersessionResult,
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
from .template_patch_contracts import TemplatePatchSuggestion

if TYPE_CHECKING:
    from fmea_application.snapshot_contracts import NormalizedFmeaSnapshot

    from .delivery_contracts import ExportArtifactManifest, ExportRun, VerifiedExportArtifact
    from .export_service import ExportNarrativeGenerationResult, ExportNarrativeRequest, StartExportCommand
    from .migration_service import (
        MigrationCandidate,
        MigrationCommand,
        MigrationResult,
        PreparedMigration,
    )
    from .propagation_service import (
        PreparedPropagationInvalidation,
        PreparedPropagationProposal,
        PreparedPropagationReview,
        PropagationReviewResult,
        PropagationRun,
    )
    from .revision_assembler import (
        GovernanceAcknowledgementRecord,
        GovernanceArtifactSet,
        GovernanceInputs,
        GovernanceRetrievalProvenance,
        ReadinessChecklistDraft,
        ReadinessChecklistProjection,
        ResolvedAnalysisRecord,
    )

ReviewHistoryPosition = tuple[str, str]


@dataclass(frozen=True, slots=True)
class GovernanceHistoryPage:
    """A bounded immutable page of persisted governance audit events."""

    events: tuple[AuditEvent, ...]
    next_cursor: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
        if self.next_cursor is not None and (not isinstance(self.next_cursor, str) or not self.next_cursor.strip()):
            raise ValueError("next_cursor must be non-empty when supplied")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class ApprovalWithdrawalResult:
    """Result shape for the append-only withdrawal of an approval decision."""

    withdrawal_id: str
    approval_id: str
    audit_event_id: str
    outbox_event_id: str
    replayed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("withdrawal_id", "approval_id", "audit_event_id", "outbox_event_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty")  # noqa: TRY003
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be a boolean")  # noqa: TRY003, TRY004


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


class PropagationRepository(Protocol):
    """Workspace-scoped persistence boundary for graph revisions and reviews."""

    def save_run_and_proposal(self, prepared: PreparedPropagationProposal) -> PropagationRun: ...

    def replay_propagation_start(self, scope: IdempotencyScope, payload_hash: str) -> PropagationRun | None: ...

    def get_graph(self, graph_revision_id: str, workspace_id: str) -> PropagationGraphRevision | None: ...

    def get_current_graph(self, analysis_id: str, workspace_id: str) -> PropagationGraphRevision | None: ...

    def replay_graph_review(self, scope: IdempotencyScope, payload_hash: str) -> PropagationReviewResult | None: ...

    def replay_invalidation(self, scope: IdempotencyScope, payload_hash: str) -> PropagationGraphRevision | None: ...

    def commit_graph_review(self, prepared: PreparedPropagationReview) -> PropagationReviewResult: ...

    def invalidate(self, prepared: PreparedPropagationInvalidation) -> PropagationGraphRevision: ...


class DomainPackRegistry(Protocol):
    def register(self, manifest: DomainPackManifest, source_bytes: bytes) -> DomainPackManifest: ...

    def get(self, pack_id: str, version: str) -> DomainPackManifest: ...

    def get_source_bytes(self, pack_id: str, version: str) -> bytes: ...


class MigrationAdapter(Protocol):
    """One explicitly registered, deterministic domain-pack migration edge."""

    source_identity: tuple[str, str]
    target_identity: tuple[str, str]

    def migrate(self, source: FmeaRevision) -> MigrationCandidate: ...


class MigrationReportRequestConflict(ValueError):
    """The stored dry run is bound to a different canonical request."""


class MigrationRepository(Protocol):
    """Provider-neutral persistence boundary for durable migration delivery."""

    def get_revision(self, revision_id: str, workspace_id: str) -> FmeaRevision | None: ...

    def get_revision_record_version(self, revision_id: str, workspace_id: str) -> int | None: ...

    def save_migration_report(
        self, report: MigrationReport, *, command: MigrationCommand, actor: ActorContext
    ) -> MigrationReport: ...

    def get_migration_report(
        self,
        migration_id: str,
        workspace_id: str,
        *,
        command: MigrationCommand,
    ) -> MigrationReport | None: ...

    def commit_migration(self, prepared: PreparedMigration) -> MigrationResult: ...


class ScoringRuleRegistry(Protocol):
    def register(self, rule_pack: ScoringRulePack, source_bytes: bytes) -> ScoringRulePack: ...

    def get(self, rule_pack_id: str, version: str) -> ScoringRulePack: ...

    def get_source_bytes(self, rule_pack_id: str, version: str) -> bytes: ...


class PropagationRuleRegistry(Protocol):
    def get(self, rule_pack_id: str, version: str) -> PropagationRulePack: ...

    def get_source_bytes(self, rule_pack_id: str, version: str) -> bytes: ...


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


class TemplateImporter(Protocol):
    """Safe, bounded source-to-draft boundary for one office format."""

    def parse(self, raw_bytes: bytes, filename: str, *, workspace_id: str) -> TemplateDraft: ...


class TemplateEvidenceProvider(Protocol):
    """Resolve the exact server-owned EvidencePack used for mapping assistance."""

    def load_pack(self, workspace_id: str, pack_id: str) -> EvidencePack: ...


@dataclass(frozen=True, slots=True)
class TemplatePatchRequest:
    """Bounded application request passed to a provider-neutral patch port."""

    patch_id: str
    draft: TemplateDraft
    evidence_pack: EvidencePack
    input_template_version: str
    target_template_id: str
    target_template_version: str
    target_template_hash: str
    domain_pack_id: str
    domain_pack_version: str
    domain_pack_hash: str
    evidence_pack_id: str
    evidence_pack_hash: str
    run_id: str
    trace_id: str
    model_version: str
    prompt_version: str
    created_at: str = ""
    target_record_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.draft, TemplateDraft):
            raise TypeError("draft must be a TemplateDraft")  # noqa: TRY003
        if not isinstance(self.evidence_pack, EvidencePack):
            raise TypeError("evidence_pack must be an EvidencePack")  # noqa: TRY003
        for field_name in (
            "patch_id",
            "input_template_version",
            "target_template_id",
            "target_template_version",
            "target_template_hash",
            "domain_pack_id",
            "domain_pack_version",
            "domain_pack_hash",
            "evidence_pack_id",
            "evidence_pack_hash",
            "run_id",
            "trace_id",
            "model_version",
            "prompt_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty")  # noqa: TRY003
        if self.created_at and not isinstance(self.created_at, str):
            raise TypeError("created_at must be a string when supplied")  # noqa: TRY003
        if isinstance(self.target_record_version, bool) or not isinstance(self.target_record_version, int):
            raise TypeError("target_record_version must be an integer")  # noqa: TRY003
        if self.target_record_version < 1:
            raise ValueError("target_record_version must be positive")  # noqa: TRY003
        if (
            self.evidence_pack.workspace_id != self.draft.workspace_id
            or self.evidence_pack.pack_id != self.evidence_pack_id
            or self.evidence_pack.pack_hash != self.evidence_pack_hash.removeprefix("sha256:")
        ):
            raise ValueError("evidence_pack identity does not match the template patch request")  # noqa: TRY003


class TemplatePatchGenerator(Protocol):
    """Provider-neutral mapping suggestions; never a template authority."""

    def suggest(self, request: object) -> TemplatePatchSuggestion: ...


class TemplateCompilerPort(Protocol):
    """The existing structured-output compiler behind the FMEA service."""

    def compile(self, source: Mapping[str, object]) -> object: ...


class TemplateRegistryPort(Protocol):
    """Immutable template registry boundary."""

    def register(self, template: object, source_bytes: bytes, source_suffix: str) -> object: ...

    def get(self, template_id: str, version: str) -> object: ...


class TemplateSourceBuilder(Protocol):
    """Build a declarative compiler input from an accepted immutable draft."""

    def build(
        self,
        base_source: Mapping[str, object],
        draft: TemplateDraft,
        patch: object,
        new_template_version: str,
    ) -> Mapping[str, object]: ...


class GovernanceSourcePort(Protocol):
    """Read server-owned accepted/confirmed governance state for one scope."""

    def load_inputs(self, analysis_id: str, workspace_id: str) -> GovernanceInputs: ...


class GovernanceAnalysisQueryPort(Protocol):
    def get_analysis(self, analysis_id: str, workspace_id: str) -> ResolvedAnalysisRecord | None: ...


class GovernanceReviewQueryPort(Protocol):
    def list_rows(self, analysis_id: str, workspace_id: str) -> tuple[FmeaRow, ...]: ...


class GovernanceRiskQueryPort(Protocol):
    def list_risk_records(self, analysis_id: str, workspace_id: str) -> tuple[RiskAssessmentRecord, ...]: ...


class GovernancePropagationQueryPort(Protocol):
    def get_current_graph(self, analysis_id: str, workspace_id: str) -> PropagationGraphRevision | None: ...


class GovernanceEvidenceQueryPort(Protocol):
    def list_evidence_packs(self, analysis_id: str, workspace_id: str) -> tuple[EvidencePack, ...]: ...


class GovernanceParentRevisionQueryPort(Protocol):
    def get_parent_revision(self, analysis_id: str, workspace_id: str) -> FmeaRevision | None: ...


class GovernanceArtifactQueryPort(Protocol):
    def get_artifacts(
        self, analysis_id: str, workspace_id: str, analysis: ResolvedAnalysisRecord
    ) -> GovernanceArtifactSet: ...


class GovernanceRunQueryPort(Protocol):
    def list_active_run_ids(self, analysis_id: str, workspace_id: str) -> tuple[str, ...]: ...


class GovernanceAcknowledgementQueryPort(Protocol):
    def list_human_acknowledgements(
        self, analysis_id: str, workspace_id: str
    ) -> tuple[GovernanceAcknowledgementRecord, ...]: ...


class RetrievalProvenanceQueryPort(Protocol):
    def get_provenance(self, analysis_id: str, workspace_id: str) -> GovernanceRetrievalProvenance: ...


@dataclass(frozen=True, slots=True)
class GovernanceRepositoryProviders:
    """Typed composition of the existing read/query repositories.

    Each provider owns one query concern. There is intentionally no generic
    callable or mapping loader through which a client can inject governance
    state.
    """

    analysis: GovernanceAnalysisQueryPort
    review: GovernanceReviewQueryPort
    risk: GovernanceRiskQueryPort
    propagation: GovernancePropagationQueryPort
    evidence: GovernanceEvidenceQueryPort
    artifacts: GovernanceArtifactQueryPort
    runs: GovernanceRunQueryPort
    acknowledgements: GovernanceAcknowledgementQueryPort
    retrieval: RetrievalProvenanceQueryPort
    parent: GovernanceParentRevisionQueryPort | None = None

    def __post_init__(self) -> None:
        required_methods = {
            "analysis": ("get_analysis",),
            "review": ("list_rows",),
            "risk": ("list_risk_records",),
            "propagation": ("get_current_graph",),
            "evidence": ("list_evidence_packs",),
            "artifacts": ("get_artifacts",),
            "runs": ("list_active_run_ids",),
            "acknowledgements": ("list_human_acknowledgements",),
            "retrieval": ("get_provenance",),
        }
        for provider_name, method_names in required_methods.items():
            provider = getattr(self, provider_name)
            if any(not callable(getattr(provider, method_name, None)) for method_name in method_names):
                raise TypeError(f"{provider_name} provider does not implement its typed query port")  # noqa: TRY003
        if self.parent is not None and not callable(getattr(self.parent, "get_parent_revision", None)):
            raise TypeError("parent provider does not implement its typed query port")  # noqa: TRY003


class GovernanceAssistanceGenerator(Protocol):
    """Provider-neutral bounded checklist generation; never an authority port."""

    def generate(self, projection: ReadinessChecklistProjection) -> ReadinessChecklistDraft | Mapping[str, object]: ...


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


class GovernanceRepository(Protocol):
    """Workspace-qualified persistence boundary for immutable FMEA governance."""

    def replay_governance_command(
        self,
        kind: Literal[
            "assemble",
            "submit",
            "approve",
            "reject",
            "withdraw_approval",
            "publish",
            "withdraw_publication",
            "supersede",
        ],
        scope: IdempotencyScope,
        command: object,
    ) -> (
        RevisionResult
        | ApprovalSubmissionResult
        | ApprovalResult
        | ApprovalWithdrawalResult
        | PublicationResult
        | PublicationWithdrawalResult
        | SupersessionResult
        | None
    ): ...

    def get_current_publication_audit_head(self, workspace_id: str) -> str | None: ...

    def replay_revision(self, scope: IdempotencyScope, payload_hash: str) -> RevisionResult | None: ...

    def commit_revision(self, prepared: PreparedRevision) -> RevisionResult: ...

    def get_revision(self, revision_id: str, workspace_id: str) -> FmeaRevision | None: ...

    def get_revision_record_version(self, revision_id: str, workspace_id: str) -> int | None: ...

    def replay_readiness(self, scope: IdempotencyScope, payload_hash: str) -> ReadinessResult | None: ...

    def commit_readiness(self, prepared: PreparedReadinessReport) -> ReadinessResult: ...

    def get_readiness(self, readiness_id: str, workspace_id: str) -> ReadinessReportRecord | None: ...

    def get_approval_submission(self, submission_id: str, workspace_id: str) -> ApprovalSubmission | None: ...

    def get_approval_decision(self, approval_id: str, workspace_id: str) -> ApprovalDecision | None: ...

    def get_approval_decision_for_submission(
        self, submission_id: str, workspace_id: str
    ) -> ApprovalDecision | None: ...

    def get_approval_withdrawal(self, approval_id: str, workspace_id: str) -> ApprovalWithdrawalRecord | None: ...

    def replay_approval_submission(
        self, scope: IdempotencyScope, payload_hash: str
    ) -> ApprovalSubmissionResult | None: ...

    def commit_approval_submission(self, prepared: PreparedApprovalSubmission) -> ApprovalSubmissionResult: ...

    def replay_approval_decision(self, scope: IdempotencyScope, payload_hash: str) -> ApprovalResult | None: ...

    def commit_approval(self, prepared: PreparedApproval) -> ApprovalResult: ...

    def replay_approval_withdrawal(
        self, scope: IdempotencyScope, payload_hash: str
    ) -> ApprovalWithdrawalResult | None: ...

    def commit_approval_withdrawal(self, prepared: PreparedApprovalWithdrawal) -> ApprovalWithdrawalResult: ...

    def replay_publication(self, scope: IdempotencyScope, payload_hash: str) -> PublicationResult | None: ...

    def commit_publication(self, prepared: PreparedPublication) -> PublicationResult: ...

    def replay_publication_withdrawal(
        self, scope: IdempotencyScope, payload_hash: str
    ) -> PublicationWithdrawalResult | None: ...

    def commit_publication_withdrawal(self, prepared: PreparedPublicationWithdrawal) -> PublicationWithdrawalResult: ...

    def replay_supersession(self, scope: IdempotencyScope, payload_hash: str) -> SupersessionResult | None: ...

    def commit_supersession(self, prepared: PreparedSupersession) -> SupersessionResult: ...

    def get_publication(self, publication_id: str, workspace_id: str) -> PublishedRevision | None: ...

    def get_publication_lifecycle(self, publication_id: str, workspace_id: str) -> PublicationLifecycleView | None: ...

    def get_snapshot(self, publication_id: str, workspace_id: str) -> NormalizedFmeaSnapshot | None: ...

    def get_export_eligibility(self, publication_id: str, workspace_id: str) -> ExportEligibilityRecord | None: ...

    def list_approval_events(self, query: GovernanceHistoryQuery) -> GovernanceHistoryPage: ...

    def list_publication_events(self, query: GovernanceHistoryQuery) -> GovernanceHistoryPage: ...


class SnapshotExporter(Protocol):
    """Provider-neutral renderer for one normalized snapshot format."""

    format: str
    media_type: str

    def render(self, snapshot: NormalizedFmeaSnapshot, *, draft_preview: bool | None = None) -> bytes: ...


class ExportNarrativeGenerator(Protocol):
    """Provider-neutral, review-only narrative assistance boundary."""

    def generate(self, request: ExportNarrativeRequest) -> ExportNarrativeGenerationResult: ...


class ArtifactStore(Protocol):
    """Immutable artifact publication and verification boundary."""

    def publish(
        self, run_id: str, filename: str, payload: bytes, manifest: ExportArtifactManifest
    ) -> VerifiedExportArtifact: ...

    def get(self, artifact_id: str, workspace_id: str) -> VerifiedExportArtifact: ...

    def latest(self, run_id: str) -> VerifiedExportArtifact | None: ...


class ExportRepository(Protocol):
    """Durable export-run and manifest lifecycle boundary."""

    def get_export_run(self, export_run_id: str, workspace_id: str) -> ExportRun | None: ...

    def get_export_artifact(self, artifact_id: str, workspace_id: str) -> ExportArtifactManifest | None: ...

    def verify_export_delivery(
        self, export_run_id: str, workspace_id: str
    ) -> tuple[ExportRun, ExportArtifactManifest]: ...

    def reserve_export_run(
        self,
        command: StartExportCommand,
        actor: ActorContext,
        request_json: str,
        request_hash: str,
        created_at: str,
    ) -> ExportRun: ...

    def mark_export_running(self, export_run_id: str, workspace_id: str, started_at: str) -> ExportRun: ...

    def request_export_cancellation(self, export_run_id: str, workspace_id: str, requested_at: str) -> ExportRun: ...

    def complete_export_cancellation(self, export_run_id: str, workspace_id: str, finished_at: str) -> ExportRun: ...

    def complete_export(
        self,
        run: ExportRun,
        manifest: ExportArtifactManifest,
        actor: ActorContext,
        request_json: str,
        request_hash: str,
        finished_at: str,
    ) -> ExportRun: ...

    def fail_export(self, export_run_id: str, workspace_id: str, error: str, finished_at: str) -> ExportRun: ...


class ReviewRunExecutor(Protocol):
    def submit(self, run_id: str, operation: Callable[[], None]) -> None: ...

    def close(self) -> None: ...


__all__ = [
    "AnalysisAssistanceGenerator",
    "ApprovalWithdrawalResult",
    "ArtifactStore",
    "AssistanceRepository",
    "DomainPackRegistry",
    "EvidenceProvider",
    "EvidenceRequest",
    "EvidenceSnapshot",
    "ExportNarrativeGenerator",
    "ExportRepository",
    "FmeaRepository",
    "GovernanceAcknowledgementQueryPort",
    "GovernanceAnalysisQueryPort",
    "GovernanceArtifactQueryPort",
    "GovernanceAssistanceGenerator",
    "GovernanceEvidenceQueryPort",
    "GovernanceHistoryPage",
    "GovernancePropagationQueryPort",
    "GovernanceRepository",
    "GovernanceRepositoryProviders",
    "GovernanceReviewQueryPort",
    "GovernanceRiskQueryPort",
    "GovernanceRunQueryPort",
    "GovernanceSourcePort",
    "MigrationAdapter",
    "MigrationReportRequestConflict",
    "MigrationRepository",
    "PropagationEvidenceProvider",
    "PropagationRepository",
    "PropagationRequest",
    "PropagationRuleRegistry",
    "RetrievalProvenanceQueryPort",
    "ReviewRepository",
    "ReviewRunExecutor",
    "ReviewSuggestionGenerator",
    "RiskRepository",
    "RiskSuggestionGenerator",
    "ScoringRuleRegistry",
    "SnapshotExporter",
    "SystemTopologyPort",
    "TemplateCompilerPort",
    "TemplateEvidenceProvider",
    "TemplateImporter",
    "TemplatePatchGenerator",
    "TemplatePatchRequest",
    "TemplateRegistryPort",
    "TemplateSourceBuilder",
]
