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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
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
from fmea_application.governance_contracts import (
    ApprovalCommand,
    AssembleRevisionCommand,
    PublishCommand,
    RevisionAssemblyRequest,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    WithdrawApprovalCommand,
    WithdrawPublicationCommand,
)
from fmea_application.ports import GovernanceRepositoryProviders
from fmea_application.review_contracts import ActorContext
from fmea_application.revision_assembler import (
    GovernanceArtifactSet,
    GovernanceRetrievalProvenance,
    ResolvedAnalysisRecord,
    ResolvedArtifactIdentity,
)
from fmea_application.snapshot_contracts import (
    NormalizedSnapshotInput,
    build_normalized_snapshot,
    iter_normalized_snapshot_pages,
)
from fmea_infrastructure.composition import build_workspace_governance_runtime
from fmea_infrastructure.domain_pack_registry import load_domain_pack_manifest
from fmea_infrastructure.governance_repository_sqlite import SqliteGovernanceRepository
from scripts.verify_fmea_governance_acceptance import (
    VerificationResult,
    verify_acceptance_directory,
)

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

    def get_artifacts(self, analysis_id: str, workspace_id: str, analysis: ResolvedAnalysisRecord) -> GovernanceArtifactSet:
        _require_scope(analysis_id, workspace_id)
        if analysis.analysis_id != ANALYSIS_ID:
            raise ValueError("fixture analysis is outside the acceptance scope")
        return self.artifacts

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
            evidence_hash=_hash_text(evidence_id),
            acl_scope=("engineering",),
            source_type="primary_document",
            source_trust="reviewed",
            is_primary=True,
            created_at=TIMESTAMP,
            expires_at=None,
        )
        for evidence_id, document_id, locator, quote in (
            ("ev-pressure", "fuel-pressure-spec", "page:1#pressure", "pressure trip threshold is defined"),
            ("ev-flame", "flame-stability-spec", "page:2#flame", "flame stability control is defined"),
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


def _fixture_artifacts() -> tuple[DomainPackManifest, GovernanceArtifactSet]:
    domain_source = (_REPO_ROOT / "domain_packs" / "fuel-combustion" / "manifest.yaml").read_bytes()
    domain = load_domain_pack_manifest(domain_source)
    template_source = (_REPO_ROOT / "templates" / "examples" / "fuel-combustion-fmea.yaml").read_bytes()
    propagation_source = (
        _REPO_ROOT / "domain_packs" / "fuel-combustion" / "propagation" / "fuel-combustion-1.0.0.yaml"
    ).read_bytes()
    scoring_source = (
        _REPO_ROOT / "domain_packs" / "fuel-combustion" / "scoring" / "sod-rpn-1.0.0.yaml"
    ).read_bytes()
    templates = tuple(
        _artifact_identity("template", artifact_id, version, template_source)
        for artifact_id, version in domain.template_identities
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
                "propagation_rule", domain.propagation_rule_identities[0][0], domain.propagation_rule_identities[0][1], propagation_source
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
            (analysis.analysis_id, WORKSPACE_ID, "sha256:" + sha256(analysis_json.encode("utf-8")).hexdigest(), analysis_json, TIMESTAMP, TIMESTAMP),
        )
        connection.commit()
    finally:
        connection.close()


def _actor(actor_id: str, role: str) -> ActorContext:
    return ActorContext(actor_id, ActorType.HUMAN, frozenset({role}), WORKSPACE_ID)


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
        "retrieval_provenance": RetrievalProvenanceSnapshot("combined", "combined", ("graph", "text"), (("graph", 1), ("text", 1)), ()),
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


def make_normalized_snapshot_input(*, revision: FmeaRevision, rows: int | Sequence[Mapping[str, object]]) -> NormalizedSnapshotInput:
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


def _execute_lifecycle(database_path: Path, providers: _FixtureProviders) -> dict[str, object]:
    repository = SqliteGovernanceRepository(database_path)
    repository.initialize()
    _seed_analysis(database_path, providers.analysis)
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
    submitted = service.submit_for_approval(
        SubmitApprovalCommand(parent.revision_id, parent.revision_hash, assembled.record_version, _key(742)), reviewer
    )
    approval_command = ApprovalCommand(
        submitted.submission_id, parent.revision_id, parent.revision_hash, submitted.record_version, "approved by human", _key(743)
    )
    approved = service.approve(approval_command, approver)
    approved_replay = service.approve(approval_command, approver)
    publish_command = PublishCommand(parent.revision_id, parent.revision_hash, approved.approval_id, assembled.record_version, _key(744))
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
        SubmitApprovalCommand(child.revision_id, child.revision_hash, child_assembled.record_version, _key(746)), reviewer
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
    try:
        service.publish(
            PublishCommand(child.revision_id, child.revision_hash, approved.approval_id, child_assembled.record_version, _key(748)),
            publisher,
        )
    except Exception as error:
        stale_code = getattr(error, "code", "")
        if stale_code != "FMEA_GOVERNANCE_APPROVAL_STALE":
            raise
        stale_approval_code = stale_code
    else:
        raise AcceptanceRunError("STALE_APPROVAL_ACCEPTED")
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
    parent_approval_withdrawal = service.withdraw_approval(
        WithdrawApprovalCommand(approved.approval_id, parent.revision_hash, approved.record_version, "approval withdrawn after correction", _key(751)),
        approver,
    )
    publication_withdrawal_command = WithdrawPublicationCommand(
        published_child.publication_id, 1, "withdraw corrected publication for closure test", None, _key(752)
    )
    publication_withdrawal = service.withdraw_publication(publication_withdrawal_command, publisher)
    publication_withdrawal_replay = service.withdraw_publication(publication_withdrawal_command, publisher)

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
    submissions = [repository.get_approval_submission(submitted.submission_id, WORKSPACE_ID), repository.get_approval_submission(child_submitted.submission_id, WORKSPACE_ID)]
    approvals = [repository.get_approval_decision(approved.approval_id, WORKSPACE_ID), repository.get_approval_decision(child_approved.approval_id, WORKSPACE_ID)]
    approval_withdrawals = [repository.get_approval_withdrawal(approved.approval_id, WORKSPACE_ID)]
    parent_lifecycle = service.get_publication(published_parent.publication_id, publisher)
    child_lifecycle = service.get_publication(published_child.publication_id, publisher)
    publications = [parent_lifecycle.publication, child_lifecycle.publication]
    snapshots = [service.get_snapshot(published_parent.publication_id, publisher), service.get_snapshot(published_child.publication_id, publisher)]
    lifecycle = [parent_lifecycle, child_lifecycle]
    if any(item is None for item in submissions + approvals + approval_withdrawals):
        raise AcceptanceRunError("PERSISTED_LIFECYCLE_INCOMPLETE")
    return {
        "revisions": revisions,
        "readiness": readiness,
        "approval_submissions": submissions,
        "approvals": approvals,
        "approval_withdrawals": approval_withdrawals,
        "publications": publications,
        "snapshots": snapshots,
        "lifecycle": lifecycle,
        "publication_withdrawals": [publication_withdrawal],
        "profile_cases": profile_cases,
        "profile_records": profile_records,
        "retrieval_call_count": providers.retrieval_calls,
        "summary": {
            "approval_actor_type": approver.actor_type.value,
            "publisher_actor_type": publisher.actor_type.value,
            "model_publication_count": 0,
            "withdrawn_publication_retained": child_lifecycle.withdrawal is not None and child_lifecycle.publication.publication_id == published_child.publication_id,
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
    outbox = _read_table(database_path, "fmea_outbox_events", json_column="payload_json")
    idempotency = _read_table(database_path, "idempotency_records", json_column="response_json")
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
        "supersessions.json": _collection("supersessions", [item.supersession for item in lifecycle["lifecycle"] if item.supersession is not None]),
        "audits.json": _collection("audits", audits),
        "outbox.json": _collection("outbox", outbox),
        "idempotency.json": _collection("idempotency", idempotency),
        "provenance-profiles.json": _collection(
            "provenance_profiles",
            lifecycle["profile_records"].values(),
        ),
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
        summary.update({"schema_version": SCHEMA_VERSION, "resource_type": "summary", "artifact_id": artifact_id})
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
        print(json.dumps({"status": "failed", "error": {"code": "FMEA_GOVERNANCE_ACCEPTANCE_FAILED"}}, separators=(",", ":")))
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
