"""Offline, end-to-end Phase 3 FMEA governance acceptance runner.

The runner deliberately uses the same typed source composition and SQLite
governance service as the application.  Its source providers are deterministic
fixtures: they expose accepted/confirmed state and provenance metadata, but do
not call a retrieval backend or persist prompts/model output.
"""

# The standalone CLI adds its repository root before importing application
# packages; the remaining suppressions cover deliberate harness boundaries.
# ruff: noqa: E402, S608, TRY003, TRY301

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core_domain.fmea.codec import encode_json
from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.governance import (
    FmeaRevision,
    RetrievalProvenanceSnapshot,
    canonical_hash,
    canonical_json_bytes,
)
from core_domain.fmea.propagation import PropagationGraphRevision
from core_domain.fmea.scoring import RiskAssessment, RiskAssessmentRecord, ScoreDimension
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PropagationStatus,
    PublicationStatus,
    ReviewStatus,
    RiskStatus,
)
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.governance_contracts import (
    ApprovalCommand,
    ApprovalRejectionCommand,
    AssembleRevisionCommand,
    PublishCommand,
    RevisionAssemblyRequest,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    WithdrawApprovalCommand,
    WithdrawPublicationCommand,
)
from fmea_application.ports import GovernanceRepositoryProviders
from fmea_application.review_contracts import (
    ActorContext,
    ReviewAction,
    ReviewCandidateBundle,
    ReviewDecisionCommand,
    ReviewReasonCode,
    ReviewSourceSnapshot,
)
from fmea_application.review_projection import build_review_context
from fmea_application.review_service import ReviewService
from fmea_application.revision_assembler import (
    GovernanceArtifactSet,
    GovernanceRetrievalProvenance,
    ResolvedAnalysisRecord,
    ResolvedArtifactIdentity,
)
from fmea_application.risk_contracts import (
    ConfirmRiskCommand,
    StartRiskProposalCommand,
    risk_context_hash,
)
from fmea_application.risk_service import RiskAssessmentService
from fmea_application.snapshot_contracts import (
    PUBLICATION_BODY_SCHEMA_VERSION,
    NormalizedSnapshotInput,
    build_normalized_snapshot,
    iter_normalized_snapshot_pages,
)
from fmea_infrastructure.assistance_repository_sqlite import SqliteAssistanceRepository
from fmea_infrastructure.composition import build_workspace_governance_runtime
from fmea_infrastructure.domain_pack_registry import (
    FileDomainPackRegistry,
    FileScoringRuleRegistry,
    load_domain_pack_manifest,
    load_scoring_rule_pack,
)
from fmea_infrastructure.governance_repository_sqlite import SqliteGovernanceRepository
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository
from fmea_infrastructure.risk_repository_sqlite import SqliteRiskRepository
from scripts.verify_fmea_governance_acceptance import (
    VerificationResult,
    verify_acceptance_directory,
)
from structured_output_application.compiler import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source, load_template_source_bytes

SCHEMA_VERSION = "graphrag.fmea.governance.acceptance.v1"
WORKSPACE_ID = "fmea-governance-acceptance"
ANALYSIS_ID = "analysis-fuel-combustion"
TIMESTAMP = "2026-08-30T00:00:00Z"
ARTIFACT_NAMES = (
    "revisions.json",
    "readiness.json",
    "approval-submissions.json",
    "approvals.json",
    "approval-withdrawals.json",
    "manifests.json",
    "publications.json",
    "snapshots.json",
    "publication-withdrawals.json",
    "supersessions.json",
    "audits.json",
    "outbox.json",
    "idempotency.json",
    "authority-denials.json",
    "replay-evidence.json",
    "provenance-profiles.json",
    "lifecycle.json",
    "acceptance-summary.json",
)
_PROFILE_EXPECTATIONS = {
    "rag_only": ("rag_only", ("text",), (("text", 1),)),
    "graphrag_only": ("graphrag_only", ("graph", "community"), (("community", 1), ("graph", 1))),
    "combined": ("combined", ("text", "graph", "community"), (("community", 1), ("graph", 1), ("text", 1))),
    "auto": ("combined", ("text", "graph", "community"), (("community", 1), ("graph", 1), ("text", 1))),
}
_GOVERNANCE_COUNT_TABLES = (
    "fmea_revisions",
    "fmea_approval_submissions",
    "fmea_approval_decisions",
    "fmea_approval_withdrawals",
    "fmea_publication_manifests",
    "fmea_normalized_snapshots",
    "fmea_publications",
    "fmea_export_eligibility",
    "fmea_publication_withdrawals",
    "fmea_supersessions",
    "fmea_audit_events",
    "fmea_outbox_events",
    "idempotency_records",
)


class AcceptanceRunError(RuntimeError):
    """Stable, safe error envelope for runner failures."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"{code}: FMEA governance acceptance failed.")


class _FixtureProviders:
    """All typed repository query ports for the deterministic fixture."""

    def __init__(self, domain_pack: DomainPackManifest, artifacts: GovernanceArtifactSet) -> None:
        self.domain_pack = domain_pack
        self.artifacts = artifacts
        self.report_templates = {template.metadata.template_id: template for template, _raw in _fixture_report_templates()}
        self.profile = "combined"
        self.parent_revision: FmeaRevision | None = None
        self.retrieval_calls = 0
        self.analysis = _analysis()
        self.pack = _evidence_pack(self.analysis.versions)
        self.row = _row(self.pack.pack_id)
        self.risk = _risk(self.pack.pack_id)
        self.graph = _graph(self.pack.pack_id)

    def get_analysis(self, analysis_id: str, workspace_id: str) -> ResolvedAnalysisRecord:
        _require_scope(analysis_id, workspace_id)
        digest = canonical_hash(self.analysis)
        return ResolvedAnalysisRecord(WORKSPACE_ID, self.analysis, self.analysis.record_version, digest, digest)

    def list_rows(self, analysis_id: str, workspace_id: str) -> tuple[FmeaRow, ...]:
        _require_scope(analysis_id, workspace_id)
        return (self.row,)

    def list_risk_records(self, analysis_id: str, workspace_id: str) -> tuple[RiskAssessmentRecord, ...]:
        _require_scope(analysis_id, workspace_id)
        return (self.risk,)

    def get_current_graph(self, analysis_id: str, workspace_id: str) -> PropagationGraphRevision:
        _require_scope(analysis_id, workspace_id)
        return self.graph

    def list_evidence_packs(self, analysis_id: str, workspace_id: str) -> tuple[EvidencePack, ...]:
        _require_scope(analysis_id, workspace_id)
        return (self.pack,)

    def get_artifacts(
        self, analysis_id: str, workspace_id: str, analysis: ResolvedAnalysisRecord
    ) -> GovernanceArtifactSet:
        _require_scope(analysis_id, workspace_id)
        if analysis.analysis_id != ANALYSIS_ID:
            raise ValueError("fixture analysis is outside the acceptance scope")
        return self.artifacts

    def get_report_template(self, template_id: str, version: str) -> str:
        template = self.report_templates[template_id]
        if template.metadata.version != version:
            raise ValueError("fixture report template version differs")
        return template.canonical_json

    def list_active_run_ids(self, analysis_id: str, workspace_id: str) -> tuple[str, ...]:
        _require_scope(analysis_id, workspace_id)
        return ()

    def list_human_acknowledgements(self, analysis_id: str, workspace_id: str) -> tuple[object, ...]:
        _require_scope(analysis_id, workspace_id)
        return ()

    def get_provenance(self, analysis_id: str, workspace_id: str) -> GovernanceRetrievalProvenance:
        _require_scope(analysis_id, workspace_id)
        resolved, evidence_types, source_counts = _PROFILE_EXPECTATIONS[self.profile]
        return GovernanceRetrievalProvenance(
            WORKSPACE_ID,
            ANALYSIS_ID,
            self.profile,
            resolved,
            evidence_types,
            source_counts,
            (),
        )

    def get_parent_revision(self, analysis_id: str, workspace_id: str) -> FmeaRevision | None:
        _require_scope(analysis_id, workspace_id)
        return self.parent_revision


@dataclass(frozen=True)
class AcceptanceRun(Mapping[str, object]):
    artifact_dir: Path
    summary: dict[str, object]

    @property
    def artifact_id(self) -> str:
        return str(self.summary["artifact_id"])

    def __getitem__(self, key: str) -> object:
        if key == "artifact_dir":
            return self.artifact_dir
        return self.summary[key]

    def __iter__(self):
        yield from self.summary

    def __len__(self) -> int:
        return len(self.summary)


def _require_scope(analysis_id: str, workspace_id: str) -> None:
    if analysis_id != ANALYSIS_ID or workspace_id != WORKSPACE_ID:
        raise ValueError("fixture query is outside the acceptance scope")


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _analysis() -> FmeaAnalysis:
    return FmeaAnalysis(
        analysis_id=ANALYSIS_ID,
        project_id="project-fuel-combustion",
        analysis_type="system_fmea",
        lifecycle_stage="design",
        scope="fuel delivery and combustion safety boundary",
        system_boundary="fuel skid to burner and trip interface",
        exclusions=("plant electrical distribution",),
        equipment_configuration="fuel-combustion-configuration-1",
        control_software_version="control-acceptance-1",
        fuel_type="natural_gas",
        operating_modes=("startup", "steady_state"),
        assumptions=("pressure transmitter is calibrated",),
        limitations=("offline fixture contains no live retrieval response",),
        unanalysed_parts=("upstream pipeline",),
        versions=VersionSet(
            "graphrag.fmea.v1",
            "data-1",
            "graph-1",
            "evidence-1",
            "profile-1",
            "template-1",
            "score-1",
            "prompt-0",
            "model-0",
            "d" * 64,
        ),
        owner_actor_id="analyst-fuel",
        reviewer_actor_ids=("human-reviewer",),
        approver_actor_id=None,
        approved_at=None,
        parent_revision_id=None,
        current_revision_id=None,
    )


def _evidence_pack(versions: VersionSet) -> EvidencePack:
    refs = tuple(
        EvidenceRef(
            evidence_id=evidence_id,
            workspace_id=WORKSPACE_ID,
            document_id=document_id,
            document_version="v1",
            content_hash=_hash_text(document_id),
            locator=locator,
            quote=quote,
            normalized_quote=quote,
            evidence_hash=_hash_text(
                json.dumps(
                    {
                        "source_type": "primary_document",
                        "document_id": document_id,
                        "document_version": "v1",
                        "locator": locator,
                        "normalized_quote": quote,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
            acl_scope=("engineering",),
            source_type="primary_document",
            source_trust="reviewed",
            is_primary=True,
            created_at=TIMESTAMP,
            expires_at=None,
        )
        for evidence_id, document_id, locator, quote in (
            (
                "ev-pressure",
                "fuel-pressure-spec",
                json.dumps({"page": 1, "span": 1}, sort_keys=True, separators=(",", ":")),
                "pressure trip threshold is defined",
            ),
            (
                "ev-flame",
                "flame-stability-spec",
                json.dumps({"page": 2, "span": 1}, sort_keys=True, separators=(",", ":")),
                "flame stability control is defined",
            ),
        )
    )
    return EvidencePack.build(
        pack_id="evidence-pack-fuel-1",
        workspace_id=WORKSPACE_ID,
        acl_scope=("engineering",),
        versions=versions,
        refs=refs,
        created_at=TIMESTAMP,
        expires_at=None,
    )


def _row(pack_id: str) -> FmeaRow:
    return FmeaRow(
        row_id="row-fuel-pressure",
        analysis_id=ANALYSIS_ID,
        evidence_pack_id=pack_id,
        item_id="fuel-filter-1",
        function_id="fuel-pressure-control",
        failure_mode="low fuel pressure",
        causes=("filter blockage",),
        mechanisms=("flow restriction",),
        effects=("flame instability",),
        symptoms=("pressure alarm",),
        controls=("pressure transmitter",),
        barriers=("automatic trip logic",),
        actions=("inspect filter",),
        risk_assessment=None,
        field_evidence=(
            ("failure_mode", ("ev-pressure",)),
            ("effects", ("ev-flame",)),
        ),
        field_support=(
            ("failure_mode", EvidenceSupportStatus.SUPPORTED),
            ("effects", EvidenceSupportStatus.SUPPORTED),
        ),
        claim_status=ClaimStatus.KNOWN,
        review_status=ReviewStatus.ACCEPTED,
        publication_status=PublicationStatus.UNPUBLISHED,
    )


def _risk(pack_id: str) -> RiskAssessmentRecord:
    dimensions = (
        ScoreDimension("severity", 9, ("ev-pressure",), "confirmed consequence severity", None),
        ScoreDimension("occurrence", 3, ("ev-pressure",), "confirmed occurrence estimate", None),
        ScoreDimension("detection", 4, ("ev-flame",), "confirmed detection control", None),
    )
    derived = RiskAssessment(
        severity_by_consequence_class=(("safety", 9),),
        decision_severity=9,
        occurrence=3,
        detection=4,
        rpn=108,
        decision_priority="high",
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=None,
        verified_residual_risk=None,
        uncertainty=None,
        reason="human-confirmed deterministic scoring",
        scoring_rule_pack_id="fuel-sod-rpn",
        scoring_rule_pack_version="1.0.0",
        evidence_ids=("ev-pressure", "ev-flame"),
    )
    return RiskAssessmentRecord(
        assessment_id="risk-fuel-pressure",
        workspace_id=WORKSPACE_ID,
        row_id="row-fuel-pressure",
        source_record_version=1,
        evidence_pack_id=pack_id,
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        rule_pack_id="fuel-sod-rpn",
        rule_pack_version="1.0.0",
        status=RiskStatus.CONFIRMED,
        dimensions=dimensions,
        derived=derived,
        proposal_id="risk-proposal-fuel-pressure",
        assistance_suggestion_id=None,
        confirmer_actor_id="human-reviewer",
        invalidated_reason=None,
        record_version=1,
        created_at=TIMESTAMP,
        updated_at=TIMESTAMP,
    )


def _graph(pack_id: str) -> PropagationGraphRevision:
    return PropagationGraphRevision(
        graph_revision_id="graph-fuel-combustion-1",
        workspace_id=WORKSPACE_ID,
        analysis_id=ANALYSIS_ID,
        analysis_record_version=1,
        topology_snapshot_id="topology-fuel-combustion-1",
        topology_hash=_hash_text("fuel-topology"),
        evidence_pack_ids=(pack_id,),
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        rule_pack_id="fuel-combustion-propagation",
        rule_pack_version="1.0.0",
        status=PropagationStatus.CONFIRMED,
        assistance_suggestion_ids=(),
        nodes=(),
        edges=(),
        paths=(),
        unresolved_issue_codes=(),
        parent_graph_revision_id=None,
        record_version=1,
        created_at=TIMESTAMP,
    )


def _artifact_identity(artifact_type: str, artifact_id: str, version: str, source: bytes) -> ResolvedArtifactIdentity:
    digest = sha256(source).hexdigest()
    return ResolvedArtifactIdentity(artifact_type, artifact_id, version, digest, digest)


def _fixture_report_templates():
    compiler = TemplateCompiler(schema_validator=Draft202012SchemaAdapter(), source_loader=load_template_source)
    paths = (
        _REPO_ROOT / "templates" / "examples" / "fuel-combustion-fmea.yaml",
        _REPO_ROOT / "domain_packs" / "fuel-combustion" / "templates" / "fmea-propagation-hypothesis-1.0.0.yaml",
    )
    return tuple((compiler.compile(load_template_source_bytes(raw)), raw) for raw in (path.read_bytes() for path in paths))


def _fixture_artifacts() -> tuple[DomainPackManifest, GovernanceArtifactSet]:
    domain_source = (_REPO_ROOT / "domain_packs" / "fuel-combustion" / "manifest.yaml").read_bytes()
    domain = load_domain_pack_manifest(domain_source)
    propagation_source = (
        _REPO_ROOT / "domain_packs" / "fuel-combustion" / "propagation" / "fuel-combustion-1.0.0.yaml"
    ).read_bytes()
    scoring_source = (_REPO_ROOT / "domain_packs" / "fuel-combustion" / "scoring" / "sod-rpn-1.0.0.yaml").read_bytes()
    templates = tuple(
        ResolvedArtifactIdentity(
            "template", template.metadata.template_id, template.metadata.version,
            template.template_hash, sha256(raw).hexdigest(),
        )
        for template, raw in _fixture_report_templates()
    )
    artifacts = GovernanceArtifactSet(
        domain_pack=domain,
        domain_pack_identity=ResolvedArtifactIdentity(
            "domain_pack", domain.pack_id, domain.version, domain.content_hash, sha256(domain_source).hexdigest()
        ),
        template_identities=templates,
        scoring_rule_identities=tuple(
            _artifact_identity("scoring_rule", artifact_id, version, scoring_source)
            for artifact_id, version in domain.scoring_rule_identities
        ),
        propagation_rule_identity=(
            None
            if not domain.propagation_rule_identities
            else _artifact_identity(
                "propagation_rule",
                domain.propagation_rule_identities[0][0],
                domain.propagation_rule_identities[0][1],
                propagation_source,
            )
        ),
    )
    return domain, artifacts


def _seed_analysis(database_path: Path, analysis: FmeaAnalysis) -> None:
    analysis_json = encode_json(analysis)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "INSERT INTO fmea_analyses(analysis_id,workspace_id,analysis_hash,analysis_json,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (
                analysis.analysis_id,
                WORKSPACE_ID,
                "sha256:" + sha256(analysis_json.encode("utf-8")).hexdigest(),
                analysis_json,
                TIMESTAMP,
                TIMESTAMP,
            ),
        )
        connection.commit()
    finally:
        connection.close()


class _AcceptanceRiskContextProvider:
    def __init__(self, repository: SqliteFmeaRepository) -> None:
        self._repository = repository

    def get_context(self, row_id: str, actor: ActorContext):
        row = self._repository.get_row(row_id, actor.workspace_id)
        if row is None:
            raise AcceptanceRunError("PUBLICATION_SOURCE_SEED_INCOMPLETE")
        pack = self._repository.get_evidence_pack(row.evidence_pack_id, actor.workspace_id)
        source = self._repository.get_review_source(row_id, actor.workspace_id)
        if pack is None or source is None:
            raise AcceptanceRunError("PUBLICATION_SOURCE_SEED_INCOMPLETE")
        return build_review_context(
            row=row,
            source=source,
            pack=pack,
            suggestions=self._repository.list_suggestions(row_id, actor.workspace_id),
            decisions=self._repository.list_decisions(row_id, actor.workspace_id),
        )


class _AcceptanceRiskSuggestionGenerator:
    def generate(self, request: object) -> AssistanceSuggestion[object]:
        request = cast(Any, request)
        dimensions = tuple(
            {
                "name": name,
                "value": value,
                "evidence_ids": [evidence_id],
                "reason": f"Acceptance source supports {name}={value}.",
                "uncertainty": "bounded-acceptance-fixture",
            }
            for name, value, evidence_id in (
                ("severity", 9, "ev-pressure"),
                ("occurrence", 3, "ev-pressure"),
                ("detection", 4, "ev-flame"),
            )
        )
        return AssistanceSuggestion(
            suggestion_id="risk-suggestion-fuel-pressure",
            kind=AssistanceKind.SCORE_RECOMMENDATION,
            workspace_id=request.evidence_pack.workspace_id,
            target_type="fmea_row",
            target_id=request.context.row.row_id,
            target_record_version=request.context.row.record_version,
            evidence_pack_ids=(request.evidence_pack.pack_id,),
            payload={
                "dimensions": dimensions,
                "reason": "Deterministic acceptance risk proposal.",
                "uncertainty": "bounded-acceptance-fixture",
                "binding": {
                    "operating_context_hash": risk_context_hash(request.context),
                    "evidence_pack_hash": request.evidence_pack.pack_hash.removeprefix("sha256:"),
                    "model_template_id": "fmea-risk-proposal",
                    "model_template_version": "1.0.0",
                },
            },
            evidence_ids=("ev-pressure", "ev-flame"),
            uncertainty="bounded-acceptance-fixture",
            model_hash="sha256:" + "5" * 64,
            prompt_hash="sha256:" + "6" * 64,
            run_id=request.run_id,
            trace_id="risk-trace-fuel-pressure",
            domain_pack_id=request.domain_pack.pack_id,
            domain_pack_version=request.domain_pack.version,
            template_id=request.template_id,
            template_version=request.template_version,
            rule_pack_id=request.rule_pack.rule_pack_id,
            rule_pack_version=request.rule_pack.version,
            created_at=TIMESTAMP,
        )


def _persist_authoritative_publication_sources(database_path: Path, providers: _FixtureProviders) -> None:
    """Run the existing review/risk/propagation services against one SQLite case."""

    review_repository = SqliteFmeaRepository(database_path)
    source = ReviewSourceSnapshot.build(
        row_id=providers.row.row_id,
        source_record_version=providers.row.record_version,
        candidate_id="candidate-fuel-pressure",
        item_label="Fuel filter",
        function_label="Fuel pressure control",
        template_id="fuel-combustion-fmea-full",
        template_version="1.0.0",
        profile_id="fuel-combustion-fmea-row",
        profile_version="1.0.0",
        generation_run_id="generation-fuel-pressure",
        requested_evidence_profile=EvidenceSelectionProfile.RAG_ONLY,
        resolved_evidence_profile=EvidenceSelectionProfile.RAG_ONLY,
        evidence_types=(CitationType.TEXT,),
        trace_id="trace-fuel-pressure",
        retrieval_warnings=(),
        retrieval_incomplete=False,
        field_claim_statuses=(
            ("failure_mode", ClaimStatus.KNOWN),
            ("effects", ClaimStatus.KNOWN),
        ),
    )
    review_repository.save_review_candidate_bundle(
        ReviewCandidateBundle(
            analysis=providers.analysis,
            evidence_pack=providers.pack,
            rows=(providers.row,),
            source_snapshots=(source,),
        ),
        ActorContext("fixture-candidate-generator", ActorType.SYSTEM, frozenset(), WORKSPACE_ID),
    )
    id_counts: dict[str, int] = {}

    def id_factory(prefix: str) -> str:
        id_counts[prefix] = id_counts.get(prefix, 0) + 1
        return f"{prefix}-{id_counts[prefix]}"

    review_service = ReviewService(review_repository, clock=lambda: TIMESTAMP, id_factory=id_factory)
    review_service.submit_decision(
        ReviewDecisionCommand(
            row_id=providers.row.row_id,
            expected_record_version=providers.row.record_version,
            idempotency_key=_key(740),
            action=ReviewAction.ACCEPT,
            suggestion_id=None,
            reason_code=ReviewReasonCode.ACCEPT_AS_IS,
            reason="Human reviewer accepts the supported row.",
            edits=(),
            evidence_requests=(),
            unresolved_acknowledgements=(),
        ),
        _actor("human-reviewer", "reviewer"),
    )
    accepted_row = review_repository.get_row(providers.row.row_id, WORKSPACE_ID)
    if accepted_row is None:
        raise AcceptanceRunError("PUBLICATION_SOURCE_SEED_INCOMPLETE")

    registry_root = database_path.parent / "immutable-registries"
    domain_source = (_REPO_ROOT / "domain_packs" / "fuel-combustion" / "manifest.yaml").read_bytes()
    scoring_source = (_REPO_ROOT / "domain_packs" / "fuel-combustion" / "scoring" / "sod-rpn-1.0.0.yaml").read_bytes()
    domain_pack = load_domain_pack_manifest(domain_source)
    scoring_pack = load_scoring_rule_pack(scoring_source)
    domain_registry = FileDomainPackRegistry(registry_root / "domain")
    scoring_registry = FileScoringRuleRegistry(registry_root / "scoring")
    domain_registry.register(domain_pack, domain_source)
    scoring_registry.register(scoring_pack, scoring_source)
    risk_repository = SqliteRiskRepository(database_path)
    risk_repository.register_pack_snapshots(
        WORKSPACE_ID,
        domain_pack,
        domain_source,
        scoring_pack,
        scoring_source,
        TIMESTAMP,
    )
    assistance_repository = SqliteAssistanceRepository(database_path)
    assistance_repository.initialize()
    risk_service = RiskAssessmentService(
        risk_repository,
        assistance_repository=assistance_repository,
        domain_pack_registry=domain_registry,
        scoring_rule_registry=scoring_registry,
        generator=_AcceptanceRiskSuggestionGenerator(),
        context_provider=_AcceptanceRiskContextProvider(review_repository),
        clock=lambda: TIMESTAMP,
    )
    template_id, template_version = providers.artifacts.template_identities[0].artifact_id, providers.artifacts.template_identities[0].version
    proposed_risk = risk_service.propose(
        StartRiskProposalCommand(
            row_id=accepted_row.row_id,
            expected_record_version=accepted_row.record_version,
            evidence_pack_id=providers.pack.pack_id,
            domain_pack_id=domain_pack.pack_id,
            domain_pack_version=domain_pack.version,
            template_id=template_id,
            template_version=template_version,
            rule_pack_id=scoring_pack.rule_pack_id,
            rule_pack_version=scoring_pack.version,
            idempotency_key=_key(741),
        ),
        ActorContext("model-risk-fixture", ActorType.MODEL, frozenset(), WORKSPACE_ID),
    )
    confirmed = risk_service.confirm(
        ConfirmRiskCommand(
            row_id=accepted_row.row_id,
            proposal_id=proposed_risk.proposal_id or "",
            expected_assessment_version=1,
            idempotency_key=_key(742),
        ),
        ActorContext("human-risk-reviewer", ActorType.HUMAN, frozenset({"risk_reviewer"}), WORKSPACE_ID),
    )
    providers.row = review_repository.get_row(accepted_row.row_id, WORKSPACE_ID) or accepted_row
    providers.risk = confirmed.assessment

    from scripts.run_fmea_full_acceptance import _load_helper

    propagation = _load_helper("propagation_slice").run_propagation(
        database_path=database_path,
        analysis=providers.analysis,
        row=providers.row,
        assessment=providers.risk,
        evidence_pack=providers.pack,
        registry_root=registry_root,
    )
    providers.graph = propagation.graph


def _actor(actor_id: str, role: str) -> ActorContext:
    return ActorContext(actor_id, ActorType.HUMAN, frozenset({role}), WORKSPACE_ID)


def _typed_actor(actor_id: str, actor_type: ActorType, role: str) -> ActorContext:
    return ActorContext(actor_id, actor_type, frozenset({role}), WORKSPACE_ID)


def _key(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


def _json(value: object) -> object:
    return json.loads(canonical_json_bytes(value).decode("utf-8"))


def _collection(resource_type: str, items: Sequence[object]) -> dict[str, object]:
    return {"schema_version": SCHEMA_VERSION, "resource_type": resource_type, "items": [_json(item) for item in items]}


def _read_table(database_path: Path, table: str, *, json_column: str | None = None) -> list[dict[str, object]]:
    connection = sqlite3.connect(database_path)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    finally:
        connection.close()
    result: list[dict[str, object]] = []
    for row in rows:
        item = {key: row[key] for key in row.keys()}  # noqa: SIM118
        if json_column is not None and isinstance(item.get(json_column), str):
            item[json_column.removesuffix("_json")] = json.loads(item.pop(json_column))
        result.append(item)
    return result


def _readiness_item(report: object) -> object:
    return _json(report)


def _governance_counts(database_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(database_path)
    try:
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in _GOVERNANCE_COUNT_TABLES[:-2]
        }
        governance_event_types = (
            "revision.assembled",
            "approval.submitted",
            "approval.approved",
            "publication.published",
            "publication.superseded",
            "approval.withdrawn",
            "publication.withdrawn",
        )
        placeholders = ",".join("?" for _ in governance_event_types)
        counts["fmea_outbox_events"] = int(
            connection.execute(
                f"SELECT COUNT(*) FROM fmea_outbox_events WHERE event_type IN ({placeholders})",
                governance_event_types,
            ).fetchone()[0]
        )
        counts["idempotency_records"] = int(
            connection.execute(
                "SELECT COUNT(*) FROM idempotency_records AS idem "
                "WHERE EXISTS (SELECT 1 FROM fmea_audit_events AS audit "
                "WHERE audit.idempotency_scope=idem.scope_key)",
            ).fetchone()[0]
        )
        return counts
    finally:
        connection.close()


def _expected_denial(
    database_path: Path,
    *,
    probe: str,
    actor: ActorContext,
    command: str,
    expected_code: str,
    action: Callable[[], object],
) -> dict[str, object]:
    before = _governance_counts(database_path)
    try:
        action()
    except Exception as error:
        actual_code = getattr(error, "code", None)
    else:
        raise AcceptanceRunError("AUTHORITY_DENIAL_ACCEPTED")
    after = _governance_counts(database_path)
    if actual_code != expected_code:
        raise AcceptanceRunError("AUTHORITY_DENIAL_CODE_INVALID")
    return {
        "probe": probe,
        "actor_id": actor.actor_id,
        "actor_type": actor.actor_type.value,
        "command": command,
        "error_code": actual_code,
        "before_counts": before,
        "after_counts": after,
    }


def _replay_evidence(command: str, result: object, resource_id: str) -> dict[str, object]:
    return {
        "command": command,
        "resource_id": resource_id,
        "record_version": getattr(result, "record_version", None),
        "audit_event_id": result.audit_event_id,
        "outbox_event_id": result.outbox_event_id,
        "replayed": result.replayed,
    }


def make_large_revision(row_count: int = 10_000) -> FmeaRevision:
    if not isinstance(row_count, int) or isinstance(row_count, bool) or not 0 <= row_count <= 10_000:
        raise ValueError("row_count must be between zero and 10000")
    analysis = _analysis()
    values: dict[str, object] = {
        "revision_id": "revision-large",
        "workspace_id": WORKSPACE_ID,
        "analysis_id": ANALYSIS_ID,
        "analysis_record_version": 1,
        "analysis_hash": canonical_hash(analysis),
        "parent_revision_id": None,
        "parent_revision_hash": None,
        "row_versions": tuple(
            sorted(
                ((f"row-{index}", 1, _hash_text(f"row-{index}")) for index in range(row_count)),
                key=lambda item: item[0],
            )
        ),
        "risk_versions": (),
        "propagation_graph_revision_id": None,
        "propagation_graph_hash": None,
        "evidence_pack_hashes": (),
        "retrieval_provenance": RetrievalProvenanceSnapshot(
            "combined", "combined", ("graph", "text"), (("graph", 1), ("text", 1)), ()
        ),
        "domain_pack_identity": ("fuel-combustion", "1.0.0", "a" * 64),
        "template_identities": (("fuel-combustion-fmea", "1.0.0", "b" * 64),),
        "scoring_rule_identities": (("fuel-sod-rpn", "1.0.0", "c" * 64),),
        "propagation_rule_identity": None,
        "unresolved_items": (),
        "created_at": TIMESTAMP,
    }
    values["revision_hash"] = canonical_hash(
        {key: value for key, value in values.items() if key not in {"revision_hash", "created_at"}},
        max_array_items=10_000,
    )
    return FmeaRevision(**values)  # type: ignore[arg-type]


def make_normalized_snapshot_input(
    *, revision: FmeaRevision, rows: int | Sequence[Mapping[str, object]]
) -> NormalizedSnapshotInput:
    if isinstance(rows, int):
        row_values = tuple({"row_id": f"row-{index}", "failure_mode": "low pressure"} for index in range(rows))
    else:
        row_values = tuple(rows)
    return NormalizedSnapshotInput(
        revision=revision,
        publication_id="publication-large",
        manifest_id="manifest-large",
        publication_revision_id=revision.revision_id,
        publication_revision_hash=revision.revision_hash,
        publication_workspace_id=revision.workspace_id,
        publication_analysis_id=revision.analysis_id,
        rows=row_values,
        risk_records=({"assessment_id": "risk-large", "status": "confirmed"},),
        propagation=None,
        evidence_summary=(),
        decision_summary=(),
        version_manifest={"schema_id": "graphrag.fmea.v1"},
        audit_summary={"event_count": 0},
        created_at=TIMESTAMP,
    )


def _safe_component_walk(path: Path, *, create: bool) -> Path:
    candidate = Path(path).absolute()
    current = Path(candidate.anchor)
    for component in candidate.parts[1:]:
        current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not create:
                raise AcceptanceRunError("OUTPUT_ROOT_INVALID") from None
            current.mkdir()
            info = current.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise AcceptanceRunError("OUTPUT_ROOT_INVALID")
        if not stat.S_ISDIR(info.st_mode):
            raise AcceptanceRunError("OUTPUT_ROOT_INVALID")
    return candidate


def _safe_output_root(output_root: str | Path) -> Path:
    return _safe_component_walk(Path(output_root), create=True)


def _write_artifact(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_canonical(path: Path, payload: object) -> None:
    _write_artifact(path, canonical_json_bytes(payload) + b"\n")


def _execute_lifecycle(database_path: Path, providers: _FixtureProviders) -> dict[str, object]:  # noqa: C901
    repository = SqliteGovernanceRepository(database_path)
    repository.initialize()
    _seed_analysis(database_path, providers.analysis)
    _persist_authoritative_publication_sources(database_path, providers)
    runtime = build_workspace_governance_runtime(
        GovernanceRepositoryProviders(
            analysis=providers,
            review=providers,
            risk=providers,
            propagation=providers,
            evidence=providers,
            artifacts=providers,
            runs=providers,
            acknowledgements=providers,
            retrieval=providers,
            parent=providers,
        ),
        repository=repository,
        clock=lambda: TIMESTAMP,
    )
    service = runtime.service
    if service is None:
        raise AcceptanceRunError("RUNTIME_UNAVAILABLE")
    reviewer = _actor("human-reviewer", "reviewer")
    approver = _actor("human-approver", "approver")
    publisher = _actor("human-publisher", "publisher")

    assemble = AssembleRevisionCommand(RevisionAssemblyRequest(ANALYSIS_ID, None, 1), _key(741))
    assembled = service.assemble(assemble, reviewer)
    parent = service.get_revision(assembled.revision_id, reviewer)
    parent_readiness = service.readiness(parent.revision_id, reviewer)
    if not parent_readiness.ready:
        raise AcceptanceRunError("READINESS_FAILED")
    submitted_command = SubmitApprovalCommand(
        parent.revision_id, parent.revision_hash, assembled.record_version, _key(742)
    )
    submitted = service.submit_for_approval(submitted_command, reviewer)
    approval_command = ApprovalCommand(
        submitted.submission_id,
        parent.revision_id,
        parent.revision_hash,
        submitted.record_version,
        "approved by human",
        _key(743),
    )
    approved = service.approve(approval_command, approver)
    approved_replay = service.approve(approval_command, approver)
    publish_command = PublishCommand(
        parent.revision_id, parent.revision_hash, approved.approval_id, assembled.record_version, _key(744)
    )
    published_parent = service.publish(publish_command, publisher)
    published_parent_replay = service.publish(publish_command, publisher)

    providers.parent_revision = parent
    child_assemble = AssembleRevisionCommand(
        RevisionAssemblyRequest(parent.analysis_id, parent.revision_id, 1, parent.revision_hash), _key(745)
    )
    child_assembled = service.assemble(child_assemble, reviewer)
    child = service.get_revision(child_assembled.revision_id, reviewer)
    child_readiness = service.readiness(child.revision_id, reviewer)
    if not child_readiness.ready:
        raise AcceptanceRunError("CHILD_READINESS_FAILED")
    child_submitted = service.submit_for_approval(
        SubmitApprovalCommand(child.revision_id, child.revision_hash, child_assembled.record_version, _key(746)),
        reviewer,
    )
    child_approved = service.approve(
        ApprovalCommand(
            child_submitted.submission_id,
            child.revision_id,
            child.revision_hash,
            child_submitted.record_version,
            "approved corrected child by human",
            _key(747),
        ),
        approver,
    )
    stale_approval_code = ""
    stale_before_counts = _governance_counts(database_path)
    try:
        service.publish(
            PublishCommand(
                child.revision_id, child.revision_hash, approved.approval_id, child_assembled.record_version, _key(748)
            ),
            publisher,
        )
    except Exception as error:
        stale_code = getattr(error, "code", "")
        if stale_code != "FMEA_GOVERNANCE_APPROVAL_STALE":
            raise
        stale_approval_code = stale_code
    else:
        raise AcceptanceRunError("STALE_APPROVAL_ACCEPTED")
    stale_after_counts = _governance_counts(database_path)
    child_publish_command = PublishCommand(
        child.revision_id, child.revision_hash, child_approved.approval_id, child_assembled.record_version, _key(749)
    )
    published_child = service.publish(child_publish_command, publisher)
    supersede_command = SupersedePublicationCommand(
        published_parent.publication_id,
        published_child.publication_id,
        1,
        1,
        "corrected child supersedes parent",
        _key(750),
    )
    service.supersede(supersede_command, publisher)
    parent_approval_withdrawal_command = WithdrawApprovalCommand(
        approved.approval_id,
        parent.revision_hash,
        approved.record_version,
        "approval withdrawn after correction",
        _key(751),
    )
    parent_approval_withdrawal = service.withdraw_approval(parent_approval_withdrawal_command, approver)
    publication_withdrawal_command = WithdrawPublicationCommand(
        published_child.publication_id, 1, "withdraw corrected publication for closure test", None, _key(752)
    )
    publication_withdrawal = service.withdraw_publication(publication_withdrawal_command, publisher)
    publication_withdrawal_replay = service.withdraw_publication(publication_withdrawal_command, publisher)
    stale_probe = {
        "probe": "stale_approval",
        "actor_id": publisher.actor_id,
        "actor_type": publisher.actor_type.value,
        "command": "fmea.publication.publish",
        "error_code": stale_approval_code,
        "before_counts": stale_before_counts,
        "after_counts": stale_after_counts,
    }
    authority_denials = [stale_probe]
    negative_commands = (
        (
            "assemble",
            "fmea.revision.assemble",
            "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN",
            lambda actor: service.assemble(assemble, actor),
        ),
        (
            "submit",
            "fmea.approval.submit",
            "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN",
            lambda actor: service.submit_for_approval(submitted_command, actor),
        ),
        (
            "approve",
            "fmea.approval.decide",
            "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN",
            lambda actor: service.approve(approval_command, actor),
        ),
        (
            "reject",
            "fmea.approval.decide",
            "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN",
            lambda actor: service.reject(
                ApprovalRejectionCommand(
                    submitted.submission_id,
                    parent.revision_id,
                    parent.revision_hash,
                    submitted.record_version,
                    "rejection authority probe",
                    _key(760),
                ),
                actor,
            ),
        ),
        (
            "withdraw_approval",
            "fmea.approval.withdraw",
            "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN",
            lambda actor: service.withdraw_approval(parent_approval_withdrawal_command, actor),
        ),
        (
            "publish",
            "fmea.publication.publish",
            "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN",
            lambda actor: service.publish(publish_command, actor),
        ),
        (
            "withdraw_publication",
            "fmea.publication.withdraw",
            "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN",
            lambda actor: service.withdraw_publication(publication_withdrawal_command, actor),
        ),
        (
            "supersede",
            "fmea.publication.supersede",
            "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN",
            lambda actor: service.supersede(supersede_command, actor),
        ),
    )
    for actor_type in (ActorType.MODEL, ActorType.SYSTEM):
        actor = _typed_actor(f"{actor_type.value}-authority-probe", actor_type, "publisher")
        for probe, command, expected_code, action in negative_commands:
            authority_denials.append(
                _expected_denial(
                    database_path,
                    probe=probe,
                    actor=actor,
                    command=command,
                    expected_code=expected_code,
                    action=lambda actor=actor, action=action: action(actor),
                )
            )
    replay_evidence = [
        _replay_evidence("fmea.approval.decide", approved_replay, approved.approval_id),
        _replay_evidence("fmea.publication.publish", published_parent_replay, published_parent.publication_id),
        _replay_evidence(
            "fmea.publication.withdraw", publication_withdrawal_replay, publication_withdrawal.withdrawal_id
        ),
    ]

    # Profile probes exercise the same source/assembler authority without adding
    # retrieval calls, network access, REST pages, or governance rows.
    profile_cases: dict[str, list[str]] = {}
    profile_records: dict[str, dict[str, object]] = {}
    providers.parent_revision = None
    for requested_profile in _PROFILE_EXPECTATIONS:
        providers.profile = requested_profile
        inputs = runtime.source.load_inputs(ANALYSIS_ID, WORKSPACE_ID)
        runtime.assembler.assemble(RevisionAssemblyRequest(ANALYSIS_ID, None, 1), inputs)
        provenance = inputs.retrieval_provenance
        expected_order = _PROFILE_EXPECTATIONS[requested_profile][1]
        if (
            provenance.requested_profile != requested_profile
            or provenance.resolved_profile != _PROFILE_EXPECTATIONS[requested_profile][0]
            or set(provenance.evidence_types) != set(expected_order)
        ):
            raise AcceptanceRunError("PROFILE_PROVENANCE_INVALID")
        # The typed provenance contract sorts its internal set.  Keep the
        # acceptance-facing profile order explicit so every source profile is
        # auditable without changing the source contract.
        profile_cases[requested_profile] = [
            evidence_type for evidence_type in expected_order if evidence_type in provenance.evidence_types
        ]
        profile_records[requested_profile] = {
            "requested_profile": provenance.requested_profile,
            "resolved_profile": provenance.resolved_profile,
            "evidence_types": profile_cases[requested_profile],
            "source_counts": [list(pair) for pair in provenance.source_counts],
            "warnings": list(provenance.warnings),
        }
    providers.profile = "combined"

    revisions = [parent, child]
    readiness = [parent_readiness, child_readiness]
    submissions = [
        repository.get_approval_submission(submitted.submission_id, WORKSPACE_ID),
        repository.get_approval_submission(child_submitted.submission_id, WORKSPACE_ID),
    ]
    approvals = [
        repository.get_approval_decision(approved.approval_id, WORKSPACE_ID),
        repository.get_approval_decision(child_approved.approval_id, WORKSPACE_ID),
    ]
    approval_withdrawals = [repository.get_approval_withdrawal(approved.approval_id, WORKSPACE_ID)]
    parent_lifecycle = service.get_publication(published_parent.publication_id, publisher)
    child_lifecycle = service.get_publication(published_child.publication_id, publisher)
    publications = [parent_lifecycle.publication, child_lifecycle.publication]
    snapshots = [
        service.get_snapshot(published_parent.publication_id, publisher),
        service.get_snapshot(published_child.publication_id, publisher),
    ]
    lifecycle = [parent_lifecycle, child_lifecycle]
    if (
        any(item is None for item in submissions + approvals + approval_withdrawals)
        or child_lifecycle.withdrawal is None
    ):
        raise AcceptanceRunError("PERSISTED_LIFECYCLE_INCOMPLETE")
    publication_withdrawal_export = _json(child_lifecycle.withdrawal)
    if not isinstance(publication_withdrawal_export, dict):
        raise AcceptanceRunError("PERSISTED_LIFECYCLE_INCOMPLETE")
    publication_withdrawal_export.update({
        "audit_event_id": publication_withdrawal.audit_event_id,
        "outbox_event_id": publication_withdrawal.outbox_event_id,
        "replayed": False,
    })
    return {
        "revisions": revisions,
        "readiness": readiness,
        "approval_submissions": submissions,
        "approvals": approvals,
        "approval_withdrawals": approval_withdrawals,
        "publications": publications,
        "snapshots": snapshots,
        "lifecycle": lifecycle,
        "publication_withdrawals": [publication_withdrawal_export],
        "authority_denials": authority_denials,
        "replay_evidence": replay_evidence,
        "profile_cases": profile_cases,
        "profile_records": profile_records,
        "retrieval_call_count": providers.retrieval_calls,
        "summary": {
            "approval_actor_type": approver.actor_type.value,
            "publisher_actor_type": publisher.actor_type.value,
            "model_publication_count": 0,
            "withdrawn_publication_retained": child_lifecycle.withdrawal is not None
            and child_lifecycle.publication.publication_id == published_child.publication_id,
            "replay_checks": {
                "approve": approved_replay.replayed,
                "publish": published_parent_replay.replayed,
                "withdraw_publication": publication_withdrawal_replay.replayed,
            },
            "profile_cases": profile_cases,
            "profile_records": profile_records,
            "retrieval_call_count": providers.retrieval_calls,
            "parent_revision_id": parent.revision_id,
            "child_revision_id": child.revision_id,
            "parent_publication_id": published_parent.publication_id,
            "child_publication_id": published_child.publication_id,
            "approval_withdrawal_id": parent_approval_withdrawal.withdrawal_id,
            "stale_child_approval_code": stale_approval_code,
        },
    }


def _artifact_payloads(database_path: Path, lifecycle: dict[str, object], artifact_id: str) -> dict[str, object]:
    manifest_rows = _read_table(database_path, "fmea_publication_manifests", json_column="manifest_json")
    manifests = [item["manifest"] for item in manifest_rows if isinstance(item.get("manifest"), dict)]
    audit_rows = _read_table(database_path, "fmea_audit_events", json_column="event_json")
    audits = []
    for item in audit_rows:
        event = item.get("event")
        if isinstance(event, dict):
            item["event_hash"] = canonical_hash(event, prefixed=True)
        audits.append(item)
    outbox = [
        item
        for item in _read_table(database_path, "fmea_outbox_events", json_column="payload_json")
        if item.get("event_type") in {
            "revision.assembled",
            "approval.submitted",
            "approval.approved",
            "publication.published",
            "publication.superseded",
            "approval.withdrawn",
            "publication.withdrawn",
        }
    ]
    governance_scopes = {str(item.get("idempotency_scope")) for item in audits}
    idempotency = [
        item
        for item in _read_table(database_path, "idempotency_records", json_column="response_json")
        if str(item.get("scope_key")) in governance_scopes
    ]
    provenance_profiles = _collection("provenance_profiles", lifecycle["profile_records"].values())
    provenance_profiles["retrieval_call_count"] = lifecycle["retrieval_call_count"]
    revisions = lifecycle["revisions"]
    readiness = lifecycle["readiness"]
    publications = lifecycle["publications"]
    snapshots = lifecycle["snapshots"]
    payloads: dict[str, object] = {
        "revisions.json": _collection("revisions", revisions),
        "readiness.json": _collection("readiness", (_readiness_item(item) for item in readiness)),
        "approval-submissions.json": _collection("approval_submissions", lifecycle["approval_submissions"]),
        "approvals.json": _collection("approvals", lifecycle["approvals"]),
        "approval-withdrawals.json": _collection("approval_withdrawals", lifecycle["approval_withdrawals"]),
        "manifests.json": _collection("manifests", manifests),
        "publications.json": _collection("publications", publications),
        "snapshots.json": _collection("snapshots", snapshots),
        "publication-withdrawals.json": _collection("publication_withdrawals", lifecycle["publication_withdrawals"]),
        "supersessions.json": _collection(
            "supersessions", [item.supersession for item in lifecycle["lifecycle"] if item.supersession is not None]
        ),
        "audits.json": _collection("audits", audits),
        "outbox.json": _collection("outbox", outbox),
        "idempotency.json": _collection("idempotency", idempotency),
        "authority-denials.json": _collection("authority_denials", lifecycle["authority_denials"]),
        "replay-evidence.json": _collection("replay_evidence", lifecycle["replay_evidence"]),
        "provenance-profiles.json": provenance_profiles,
        "lifecycle.json": _collection("lifecycle", lifecycle["lifecycle"]),
    }
    return payloads


def _model_publication_count(payload: object) -> int:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise AcceptanceRunError("AUDIT_PAYLOAD_INVALID")
    return sum(
        1
        for item in payload["items"]
        if isinstance(item, dict)
        and item.get("command") == "fmea.publication.publish"
        and item.get("actor_type") == ActorType.MODEL.value
    )


def run_acceptance(*, output_root: str | Path | None = None) -> AcceptanceRun:
    root = _safe_output_root(output_root or (_REPO_ROOT / ".local" / "fmea-governance-acceptance"))
    artifact_id = f"acceptance-{uuid4()}"
    temp_dir: Path | None = None
    final_dir: Path | None = None
    database_dir: Path | None = None
    pointer_temp: Path | None = None
    try:
        temp_dir = Path(tempfile.mkdtemp(prefix=f".acceptance-{artifact_id}.", suffix=".tmp", dir=root))
        database_dir = Path(tempfile.mkdtemp(prefix="fmea-governance-db-"))
        database_path = database_dir / "governance.sqlite3"
        domain, artifacts = _fixture_artifacts()
        providers = _FixtureProviders(domain, artifacts)
        lifecycle = _execute_lifecycle(database_path, providers)
        payloads = _artifact_payloads(database_path, lifecycle, artifact_id)
        summary = dict(lifecycle["summary"])
        summary.update(
            {
                "schema_version": SCHEMA_VERSION,
                "resource_type": "summary",
                "artifact_id": artifact_id,
                "publication_body_schema_version": PUBLICATION_BODY_SCHEMA_VERSION,
            }
        )
        summary["model_publication_count"] = _model_publication_count(payloads["audits.json"])
        for name in ARTIFACT_NAMES:
            if name == "acceptance-summary.json":
                continue
            _write_canonical(temp_dir / name, payloads[name])
        artifact_hashes = {
            name: "sha256:" + sha256((temp_dir / name).read_bytes()).hexdigest()
            for name in ARTIFACT_NAMES
            if name != "acceptance-summary.json"
        }
        summary["artifact_hashes"] = artifact_hashes
        _write_canonical(temp_dir / "acceptance-summary.json", summary)
        verification = verify_acceptance_directory(temp_dir)
        if not verification.passed:
            raise AcceptanceRunError(verification.error_code or "FMEA_ARTIFACT_VERIFICATION_FAILED")
        final_dir = root / artifact_id
        os.replace(temp_dir, final_dir)
        temp_dir = None
        pointer_temp = root / f".latest-{artifact_id}.tmp"
        _write_artifact(pointer_temp, (artifact_id + "\n").encode("ascii"))
        os.replace(pointer_temp, root / "latest")
        pointer_temp = None
        return AcceptanceRun(final_dir, summary)
    except Exception:
        if pointer_temp is not None:
            pointer_temp.unlink(missing_ok=True)
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)
        if final_dir is not None:
            shutil.rmtree(final_dir, ignore_errors=True)
        raise
    finally:
        if database_dir is not None:
            shutil.rmtree(database_dir, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run offline Phase 3 FMEA governance acceptance")
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        result = run_acceptance(output_root=args.output_root)
    except Exception:
        print(
            json.dumps(
                {"status": "failed", "error": {"code": "FMEA_GOVERNANCE_ACCEPTANCE_FAILED"}}, separators=(",", ":")
            )
        )
        return 2
    print(json.dumps({"status": "passed", "artifact_id": result.summary["artifact_id"]}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AcceptanceRun",
    "AcceptanceRunError",
    "VerificationResult",
    "_safe_output_root",
    "_write_artifact",
    "build_normalized_snapshot",
    "iter_normalized_snapshot_pages",
    "make_large_revision",
    "make_normalized_snapshot_input",
    "run_acceptance",
]
