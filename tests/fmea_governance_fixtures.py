from __future__ import annotations

from dataclasses import fields, replace
from hashlib import sha256
from typing import Any

from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.entities import FmeaAnalysis
from core_domain.fmea.governance import (
    ApprovalDecision,
    ApprovalStatus,
    ApprovalSubmission,
    FmeaRevision,
    ReadinessIssue,
    RetrievalProvenanceSnapshot,
    SupersessionRecord,
    canonical_hash,
    canonical_json_value,
)
from core_domain.fmea.states import ActorType
from core_domain.fmea.value_objects import VersionSet
from fmea_application.governance_contracts import (
    ApprovalCommand,
    PreparedApproval,
    PreparedRevision,
    RevisionAssemblyRequest,
    canonical_governance_payload,
    governance_payload_hash,
)
from fmea_application.ports import GovernanceRepositoryProviders
from fmea_application.review_contracts import ActorContext, AuditEvent, IdempotencyScope, idempotency_key_hash
from fmea_application.revision_assembler import (
    GovernanceAcknowledgementRecord,
    GovernanceArtifactSet,
    GovernanceDomainPolicy,
    GovernanceInputs,
    GovernanceRetrievalProvenance,
    HumanAcknowledgementReference,
    PublicationReadinessContext,
    PublicationReadinessReport,
    ResolvedAnalysisRecord,
    ResolvedArtifactIdentity,
    RevisionAssembler,
)
from fmea_application.risk_contracts import OutboxEvent, outbox_payload_hash
from fmea_infrastructure.composition import build_workspace_governance_runtime

HASH = "a" * 64
PREFIXED_HASH = "sha256:" + HASH
TIMESTAMP = "2026-08-30T00:00:00Z"
_INPUT_VERIFIERS: dict[int, object] = {}


def _record_hash(seed: str) -> str:
    return sha256(seed.encode("utf-8")).hexdigest()


def _governance_analysis() -> FmeaAnalysis:
    return FmeaAnalysis(
        analysis_id="analysis-1",
        project_id="project-1",
        analysis_type="fuel_system",
        lifecycle_stage="draft",
        scope="generic system",
        system_boundary="generic boundary",
        exclusions=(),
        equipment_configuration="configuration-1",
        control_software_version="control-1",
        fuel_type="generic",
        operating_modes=("steady",),
        assumptions=(),
        limitations=(),
        unanalysed_parts=(),
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
        owner_actor_id="analyst-1",
        reviewer_actor_ids=("reviewer-1",),
        approver_actor_id=None,
        approved_at=None,
        parent_revision_id=None,
        current_revision_id="revision-1",
    )


def _identity(artifact_type: str, artifact_id: str, version: str, content_hash: str) -> ResolvedArtifactIdentity:
    return ResolvedArtifactIdentity(
        artifact_type,
        artifact_id,
        version,
        content_hash,
        content_hash,
    )


def _resolved_analysis(workspace_id: str, analysis: FmeaAnalysis) -> ResolvedAnalysisRecord:
    content_hash = canonical_hash(analysis)
    return ResolvedAnalysisRecord(
        workspace_id=workspace_id,
        analysis=analysis,
        record_version=analysis.record_version,
        canonical_hash=content_hash,
        source_hash=content_hash,
    )


def make_readiness_issue(**overrides: Any) -> ReadinessIssue:
    values: dict[str, Any] = {
        "code": "missing-review",
        "severity": "blocking",
        "source_type": "row",
        "source_id": "row-1",
        "evidence_ids": ("ev-1",),
        "acknowledgement_decision_id": None,
    }
    values.update(overrides)
    return ReadinessIssue(**values)


def _provenance(**overrides: Any) -> RetrievalProvenanceSnapshot:
    values: dict[str, Any] = {
        "requested_profile": "combined",
        "resolved_profile": "combined",
        "evidence_types": ("text", "graph"),
        "source_counts": (("text", 1), ("graph", 1)),
        "warnings": (),
    }
    values.update(overrides)
    return RetrievalProvenanceSnapshot(**values)


def make_fmea_revision(**overrides: Any) -> FmeaRevision:
    values: dict[str, Any] = {
        "revision_id": "revision-1",
        "workspace_id": "ws-1",
        "analysis_id": "analysis-1",
        "analysis_record_version": 1,
        "analysis_hash": canonical_hash(_governance_analysis()),
        "parent_revision_id": None,
        "parent_revision_hash": None,
        "row_versions": (("row-1", 1, HASH),),
        "risk_versions": (("row-1", 1, HASH),),
        "propagation_graph_revision_id": "graph-1",
        "propagation_graph_hash": PREFIXED_HASH,
        "evidence_pack_hashes": (("pack-1", HASH),),
        "retrieval_provenance": _provenance(),
        "domain_pack_identity": ("fuel-combustion", "1.0.0", HASH),
        "template_identities": (("fuel-fmea", "1.0.0", HASH),),
        "scoring_rule_identities": (("fuel-sod-rpn", "1.0.0", HASH),),
        "propagation_rule_identity": ("fuel-propagation", "1.0.0", HASH),
        "unresolved_items": (),
        "revision_hash": HASH,
        "created_at": TIMESTAMP,
    }
    values.update(overrides)
    if values.get("parent_revision_id") is not None and "parent_revision_hash" not in overrides:
        values["parent_revision_hash"] = HASH
    if "revision_hash" not in overrides:
        content = {key: value for key, value in values.items() if key not in {"revision_hash", "created_at"}}
        values["revision_hash"] = canonical_hash(canonical_json_value(content), max_array_items=10_000)
    return FmeaRevision(**values)


def make_large_revision(row_count: int = 10_000, **overrides: Any) -> FmeaRevision:
    values = {
        "row_versions": tuple(sorted((f"row-{index}", 1, _record_hash(f"row-{index}")) for index in range(row_count))),
        "risk_versions": (),
    }
    values.update(overrides)
    return make_fmea_revision(**values)


def make_blocked_readiness_report(**overrides: Any) -> PublicationReadinessReport:
    issue = make_readiness_issue()
    values: dict[str, Any] = {
        "revision_id": "revision-1",
        "workspace_id": "ws-1",
        "analysis_id": "analysis-1",
        "revision_hash": HASH,
        "target_record_version": 1,
        "evidence_pack_ids": ("pack-1",),
        "ready": False,
        "issues": (issue,),
        "blocking_codes": (issue.code,),
    }
    values.update(overrides)
    return PublicationReadinessReport(**values)


def _readiness_artifacts() -> GovernanceArtifactSet:
    revision = make_fmea_revision()
    domain = DomainPackManifest(
        pack_id=revision.domain_pack_identity[0],
        version=revision.domain_pack_identity[1],
        content_hash=revision.domain_pack_identity[2],
        compatible_schema_ids=("graphrag.fmea.v1",),
        analysis_types=("fuel_system",),
        template_identities=((revision.template_identities[0][0], revision.template_identities[0][1]),),
        scoring_rule_identities=((revision.scoring_rule_identities[0][0], revision.scoring_rule_identities[0][1]),),
        propagation_rule_identities=((revision.propagation_rule_identity[0], revision.propagation_rule_identity[1]),),
        extension_fields=(),
    )
    return GovernanceArtifactSet(
        domain_pack=domain,
        domain_pack_identity=_identity("domain_pack", *revision.domain_pack_identity),
        template_identities=(_identity("template", *revision.template_identities[0]),),
        scoring_rule_identities=(_identity("scoring_rule", *revision.scoring_rule_identities[0]),),
        propagation_rule_identity=_identity("propagation_rule", *revision.propagation_rule_identity),
    )


def _artifacts_for_inputs(inputs: GovernanceInputs) -> GovernanceArtifactSet:
    return GovernanceArtifactSet(
        domain_pack=inputs.domain_pack,
        domain_pack_identity=inputs.domain_pack_identity,
        template_identities=inputs.template_identities,
        scoring_rule_identities=inputs.scoring_rule_identities,
        propagation_rule_identity=inputs.propagation_rule_identity,
    )


def make_governance_acknowledgement_record(**overrides: Any) -> GovernanceAcknowledgementRecord:
    values: dict[str, Any] = {
        "decision_id": "decision-1",
        "decision_hash": HASH,
        "decision_record_version": 1,
        "status": "accepted",
        "workspace_id": "ws-1",
        "analysis_id": "analysis-1",
        "issue_code": "ACK_REQUIRED",
        "issue_source_type": "row",
        "issue_source_id": "row-1",
        "actor_id": "reviewer-1",
        "actor_type": ActorType.HUMAN,
        "revision_id": "revision-1",
        "revision_record_version": 1,
        "evidence_ids": ("ev-1",),
    }
    values.update(overrides)
    record = GovernanceAcknowledgementRecord(**values)
    record = replace(record, decision_hash=record.canonical_hash)
    return record


def make_human_acknowledgement_reference(**overrides: Any) -> HumanAcknowledgementReference:
    values = dict(overrides)
    foreign_scope = {
        key: values.pop(key) for key in ("workspace_id", "analysis_id", "issue_source_id") if key in values
    }
    record = make_governance_acknowledgement_record(**values)
    reference = make_governance_inputs(acknowledgement_records=(record,)).acknowledgement_references[0]
    if not foreign_scope:
        return reference
    forged = object.__new__(HumanAcknowledgementReference)
    for item in fields(reference):
        object.__setattr__(forged, item.name, getattr(reference, item.name))
    for field_name, value in foreign_scope.items():
        object.__setattr__(forged, field_name, value)
    return forged


def make_approval_submission(**overrides: Any) -> ApprovalSubmission:
    values: dict[str, Any] = {
        "submission_id": "submission-1",
        "workspace_id": "ws-1",
        "revision_id": "revision-1",
        "revision_hash": HASH,
        "status": ApprovalStatus.PENDING,
        "submitter_actor_id": "reviewer-1",
        "record_version": 1,
        "created_at": TIMESTAMP,
    }
    values.update(overrides)
    return ApprovalSubmission(**values)


def make_approval_decision(**overrides: Any) -> ApprovalDecision:
    values: dict[str, Any] = {
        "approval_id": "approval-1",
        "submission_id": "submission-1",
        "revision_id": "revision-1",
        "revision_hash": HASH,
        "status": ApprovalStatus.APPROVED,
        "approver_actor_id": "approver-1",
        "reason": "approved by human reviewer",
        "record_version": 2,
        "created_at": TIMESTAMP,
    }
    values.update(overrides)
    return ApprovalDecision(**values)


def make_published_revision(**overrides: Any):
    from core_domain.fmea.governance import PublishedRevision

    values: dict[str, Any] = {
        "publication_id": "publication-1",
        "workspace_id": "ws-1",
        "analysis_id": "analysis-1",
        "revision_id": "revision-1",
        "revision_hash": HASH,
        "approval_id": "approval-1",
        "manifest_id": "manifest-1",
        "manifest_hash": HASH,
        "snapshot_id": "snapshot-1",
        "snapshot_hash": HASH,
        "audit_chain_head": HASH,
        "publisher_actor_id": "publisher-1",
        "record_version": 1,
        "created_at": TIMESTAMP,
    }
    values.update(overrides)
    if "revision_hash" not in overrides:
        values["revision_hash"] = make_fmea_revision(
            revision_id=values["revision_id"],
            workspace_id=values["workspace_id"],
            analysis_id=values["analysis_id"],
        ).revision_hash
    return PublishedRevision(**values)


def make_normalized_snapshot_input(**overrides: Any):
    from fmea_application.snapshot_contracts import NormalizedSnapshotInput

    revision = overrides.pop("revision", make_fmea_revision())
    row_payload = overrides.pop("row_payload", None)
    rows = overrides.pop("rows", None)
    if isinstance(rows, int):
        rows = tuple({"row_id": f"row-{index}", "failure_mode": "low pressure"} for index in range(rows))
    elif rows is None and len(revision.row_versions) > 1:
        rows = tuple({"row_id": row_id, "failure_mode": "low pressure"} for row_id, _, _ in revision.row_versions)
    values: dict[str, Any] = {
        "revision": revision,
        "publication_id": "publication-1",
        "manifest_id": "manifest-1",
        "publication_revision_id": revision.revision_id,
        "publication_revision_hash": revision.revision_hash,
        "publication_workspace_id": revision.workspace_id,
        "publication_analysis_id": revision.analysis_id,
        "rows": tuple(rows if rows is not None else ({"row_id": "row-1", "failure_mode": "low pressure"},)),
        "risk_records": ({"assessment_id": "assessment-1", "status": "confirmed"},),
        "propagation": {"graph_revision_id": "graph-1"},
        "evidence_summary": ({"pack_id": "pack-1", "evidence_count": 1},),
        "decision_summary": ({"decision_id": "decision-1", "action": "accept"},),
        "version_manifest": {"schema_id": "graphrag.fmea.v1", "domain_pack": "fuel-combustion@1.0.0"},
        "audit_summary": {"event_count": 1},
        "created_at": TIMESTAMP,
    }
    if row_payload is not None:
        values["rows"] = (row_payload,)
    values.update(overrides)
    return NormalizedSnapshotInput(**values)


def make_normalized_snapshot(**overrides: Any):
    from fmea_application.snapshot_contracts import build_normalized_snapshot

    publication_revision_id = overrides.pop("publication_revision_id", None)
    revision_id = overrides.pop("revision_id", "revision-1")
    revision = overrides.pop("revision", make_fmea_revision(revision_id=revision_id))
    if publication_revision_id is not None:
        overrides["publication_revision_id"] = publication_revision_id
    source = make_normalized_snapshot_input(revision=revision, **overrides)
    return build_normalized_snapshot(source)


def make_supersession_record(**overrides: Any) -> SupersessionRecord:
    values: dict[str, Any] = {
        "supersession_id": "supersession-1",
        "old_publication_id": "pub-old",
        "new_publication_id": "pub-new",
        "actor_id": "publisher-1",
        "reason": "corrected revision published",
        "created_at": TIMESTAMP,
    }
    values.update(overrides)
    return SupersessionRecord(**values)


def make_governance_actor(**overrides: Any) -> ActorContext:
    values: dict[str, Any] = {
        "actor_id": "approver-1",
        "actor_type": ActorType.HUMAN,
        "roles": frozenset({"approver", "publisher"}),
        "workspace_id": "ws-1",
    }
    values.update(overrides)
    return ActorContext(**values)


def make_governance_inputs(**overrides: Any) -> GovernanceInputs:  # noqa: C901
    domain_pack = DomainPackManifest(
        pack_id="generic-domain",
        version="1.0.0",
        content_hash="a" * 64,
        compatible_schema_ids=("graphrag.fmea.v1",),
        analysis_types=("fuel_system",),
        template_identities=(("generic-template", "1.0.0"),),
        scoring_rule_identities=(("generic-scoring", "1.0.0"),),
        propagation_rule_identities=(("generic-propagation", "1.0.0"),),
        extension_fields=(),
    )
    analysis = _governance_analysis()
    values: dict[str, Any] = {
        "workspace_id": "ws-1",
        "analysis_id": "analysis-1",
        "analysis": _resolved_analysis("ws-1", analysis),
        "rows": (),
        "risk_records": (),
        "propagation_graph_revision": None,
        "evidence_packs": (),
        "domain_pack": domain_pack,
        "domain_pack_identity": _identity("domain_pack", "generic-domain", "1.0.0", "a" * 64),
        "template_identities": (_identity("template", "generic-template", "1.0.0", "b" * 64),),
        "scoring_rule_identities": (_identity("scoring_rule", "generic-scoring", "1.0.0", "c" * 64),),
        "propagation_rule_identity": _identity("propagation_rule", "generic-propagation", "1.0.0", "d" * 64),
        "retrieval_provenance": GovernanceRetrievalProvenance(
            workspace_id="ws-1",
            analysis_id="analysis-1",
            requested_profile="combined",
            resolved_profile="combined",
            evidence_types=("text", "graph"),
            source_counts=(("text", 1), ("graph", 1)),
            warnings=(),
        ),
    }
    acknowledgement_records = tuple(overrides.pop("acknowledgement_records", ()))
    parent_revision = overrides.get("parent_revision")
    supplied_provenance = overrides.pop("retrieval_provenance", None)
    provenance_values = {
        "requested_profile": values["retrieval_provenance"].requested_profile,
        "resolved_profile": values["retrieval_provenance"].resolved_profile,
        "evidence_types": values["retrieval_provenance"].evidence_types,
        "source_counts": values["retrieval_provenance"].source_counts,
        "warnings": values["retrieval_provenance"].warnings,
    }
    for key in tuple(provenance_values):
        if key in overrides:
            provenance_values[key] = overrides.pop(key)
    values.update(overrides)
    if supplied_provenance is not None:
        values["retrieval_provenance"] = supplied_provenance
    else:
        values["retrieval_provenance"] = GovernanceRetrievalProvenance(
            workspace_id=values["workspace_id"], analysis_id=values["analysis_id"], **provenance_values
        )

    class AnalysisProvider:
        def get_analysis(self, _analysis_id: str, _workspace_id: str) -> ResolvedAnalysisRecord:
            return values["analysis"]

    class ReviewProvider:
        def list_rows(self, _analysis_id: str, _workspace_id: str) -> tuple[Any, ...]:
            return tuple(values["rows"])

    class RiskProvider:
        def list_risk_records(self, _analysis_id: str, _workspace_id: str) -> tuple[Any, ...]:
            return tuple(values["risk_records"])

    class PropagationProvider:
        def get_current_graph(self, _analysis_id: str, _workspace_id: str) -> Any:
            return values["propagation_graph_revision"]

    class EvidenceProvider:
        def list_evidence_packs(self, _analysis_id: str, _workspace_id: str) -> tuple[Any, ...]:
            return tuple(values["evidence_packs"])

    class ArtifactProvider:
        def get_artifacts(self, _analysis_id: str, _workspace_id: str, _analysis: Any) -> GovernanceArtifactSet:
            return GovernanceArtifactSet(
                domain_pack=values["domain_pack"],
                domain_pack_identity=values["domain_pack_identity"],
                template_identities=tuple(values["template_identities"]),
                scoring_rule_identities=tuple(values["scoring_rule_identities"]),
                propagation_rule_identity=values["propagation_rule_identity"],
            )

    class RunProvider:
        def list_active_run_ids(self, _analysis_id: str, _workspace_id: str) -> tuple[str, ...]:
            return tuple(values.get("active_run_ids", ()))

    class AcknowledgementProvider:
        def list_human_acknowledgements(self, _analysis_id: str, _workspace_id: str) -> tuple[Any, ...]:
            return acknowledgement_records

    class RetrievalProvider:
        def get_provenance(self, _analysis_id: str, _workspace_id: str) -> GovernanceRetrievalProvenance:
            return values["retrieval_provenance"]

    class ParentProvider:
        def get_parent_revision(self, _analysis_id: str, _workspace_id: str) -> FmeaRevision | None:
            return parent_revision

    providers = GovernanceRepositoryProviders(
        analysis=AnalysisProvider(),
        review=ReviewProvider(),
        risk=RiskProvider(),
        propagation=PropagationProvider(),
        evidence=EvidenceProvider(),
        artifacts=ArtifactProvider(),
        runs=RunProvider(),
        acknowledgements=AcknowledgementProvider(),
        retrieval=RetrievalProvider(),
        parent=ParentProvider() if parent_revision is not None else None,
    )
    runtime = build_workspace_governance_runtime(providers)
    inputs = runtime.source.load_inputs(values["analysis_id"], values["workspace_id"])
    _INPUT_VERIFIERS[id(inputs._source_attestation)] = runtime.assembler._verifier
    return inputs


def make_governance_assembler(inputs: GovernanceInputs, **overrides: Any) -> RevisionAssembler:
    verifier = _INPUT_VERIFIERS.get(id(inputs._source_attestation))
    if verifier is None:
        raise TypeError("fixture inputs are not associated with a governance runtime")  # noqa: TRY003
    return RevisionAssembler(verifier=verifier, **overrides)


def make_assemble_request(**overrides: Any) -> RevisionAssemblyRequest:
    values: dict[str, Any] = {"analysis_id": "analysis-1", "parent_revision_id": None, "expected_analysis_version": 1}
    values.update(overrides)
    return RevisionAssemblyRequest(**values)


def make_readiness_context(**overrides: Any) -> PublicationReadinessContext:
    overrides = dict(overrides)
    values: dict[str, Any] = {
        "required_fields_accepted": True,
        "required_risk_confirmed": True,
        "propagation_confirmed": True,
        "authoritative_analysis": _resolved_analysis("ws-1", _governance_analysis()),
        "authoritative_artifacts": _readiness_artifacts(),
    }
    values.update(overrides)
    return PublicationReadinessContext(**values)


def make_domain_policy(**overrides: Any) -> GovernanceDomainPolicy:
    values: dict[str, Any] = {"allow_acknowledged_blocking": True, "required_risk": True, "required_propagation": True}
    values.update(overrides)
    return GovernanceDomainPolicy(**values)


def make_approval_command(**overrides: Any) -> ApprovalCommand:
    values: dict[str, Any] = {
        "submission_id": "submission-1",
        "revision_id": "revision-1",
        "revision_hash": HASH,
        "expected_submission_version": 1,
        "reason": "approved by human reviewer",
        "idempotency_key": "00000000-0000-4000-8000-000000000702",
    }
    values.update(overrides)
    return ApprovalCommand(**values)


def make_publish_command(**overrides: Any):
    from fmea_application.governance_contracts import PublishCommand

    values: dict[str, Any] = {
        "revision_id": "revision-1",
        "revision_hash": HASH,
        "approval_id": "approval-1",
        "expected_revision_version": 1,
        "idempotency_key": "00000000-0000-4000-8000-000000000703",
    }
    values.update(overrides)
    return PublishCommand(**values)


def make_cross_analysis_supersession_command(**overrides: Any):
    from fmea_application.governance_contracts import SupersedePublicationCommand

    values: dict[str, Any] = {
        "publication_id": "pub-old",
        "replacement_publication_id": "pub-other-analysis",
        "expected_publication_version": 1,
        "expected_replacement_version": 1,
        "reason": "replacement",
        "idempotency_key": "00000000-0000-4000-8000-000000000704",
    }
    values.update(overrides)
    return SupersedePublicationCommand(**values)


def _scope(actor: ActorContext, command: str, resource_path: str, key: str) -> IdempotencyScope:
    return IdempotencyScope(actor.workspace_id, actor.actor_id, command, resource_path, idempotency_key_hash(key))


def _audit(
    scope: IdempotencyScope, payload_hash: str, *, aggregate_id: str, analysis_id: str = "analysis-1"
) -> AuditEvent:
    versions = VersionSet("graphrag.fmea.v1", "1", "1", "1", "1", "1", "1", "1", "1", HASH)
    return AuditEvent(
        event_id=f"audit-{aggregate_id}",
        occurred_at_server=TIMESTAMP,
        workspace_id=scope.workspace_id,
        actor_id=scope.actor_id,
        actor_type=ActorType.HUMAN,
        actor_roles=("approver", "publisher"),
        command=scope.command,
        action=None,
        reason_code=None,
        reason="governance event",
        analysis_id=analysis_id,
        row_id=aggregate_id,
        suggestion_id=None,
        decision_id=None,
        expected_record_version=1,
        applied_record_version=1,
        before_hash=None,
        after_hash=PREFIXED_HASH,
        changed_fields=(),
        evidence_ids=(),
        evidence_request_targets=(),
        idempotency_key_hash=scope.key_hash,
        canonical_payload_hash=payload_hash,
        versions=versions,
        template_id="fuel-fmea",
        template_version="1.0.0",
        profile_id="combined",
        profile_version="1.0.0",
        model_manifest=None,
        request_id="request-governance",
        trace_id="trace-governance",
        retrieval_trace_id="retrieval-governance",
    )


def _prepared_events(
    scope: IdempotencyScope, payload_hash: str, payload: dict[str, Any], aggregate_id: str
) -> tuple[AuditEvent, OutboxEvent]:
    audit = _audit(scope, payload_hash, aggregate_id=aggregate_id)
    outbox = OutboxEvent(
        event_id=f"outbox-{aggregate_id}",
        workspace_id=scope.workspace_id,
        aggregate_type="fmea_governance",
        aggregate_id=aggregate_id,
        event_type=scope.command,
        payload=payload,
        payload_hash=outbox_payload_hash(payload),
        created_at=TIMESTAMP,
        scope_key=scope.scope_key,
    )
    return audit, outbox


def prepared_revision(**overrides: Any) -> PreparedRevision:
    actor = make_governance_actor(actor_id="assembler-1", roles=frozenset({"assembler"}))
    key = "00000000-0000-4000-8000-000000000705"
    command = __import__(
        "fmea_application.governance_contracts", fromlist=["AssembleRevisionCommand"]
    ).AssembleRevisionCommand(request=make_assemble_request(), idempotency_key=key)
    revision = make_fmea_revision()
    scope = _scope(actor, "fmea.revision.assemble", f"/fmea/analyses/{revision.analysis_id}/revisions", key)
    payload = canonical_governance_payload("revision.assemble", command, revision=revision)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, revision.revision_id)
    values: dict[str, Any] = {
        "scope": scope,
        "payload_hash": payload_hash,
        "command": command,
        "expected_analysis_version": 1,
        "revision": revision,
        "audit": audit,
        "outbox": outbox,
    }
    values.update(overrides)
    return PreparedRevision(**values)


def prepared_approval_submission(**overrides: Any):
    from fmea_application.governance_contracts import PreparedApprovalSubmission, SubmitApprovalCommand

    actor = make_governance_actor(actor_id="reviewer-1", roles=frozenset({"approver"}))
    key = "00000000-0000-4000-8000-000000000706"
    command = SubmitApprovalCommand("revision-1", HASH, 1, key)
    submission = make_approval_submission(submitter_actor_id=actor.actor_id)
    scope = _scope(actor, "fmea.approval.submit", "/fmea/revisions/revision-1/approval-submissions", key)
    payload = canonical_governance_payload("approval.submit", command, submission=submission)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, submission.submission_id)
    return PreparedApprovalSubmission(
        scope=scope,
        payload_hash=payload_hash,
        command=command,
        revision_record_version=1,
        submission=submission,
        audit=audit,
        outbox=outbox,
    )


def prepared_approval(**overrides: Any) -> PreparedApproval:
    actor = make_governance_actor()
    key = "00000000-0000-4000-8000-000000000707"
    command = make_approval_command(idempotency_key=key)
    submission = make_approval_submission()
    decision = make_approval_decision()
    scope = _scope(actor, "fmea.approval.decide", "/fmea/approval-submissions/submission-1/decision", key)
    payload = canonical_governance_payload("approval.decide", command, submission=submission, decision=decision)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, decision.approval_id)
    values = {
        "scope": scope,
        "payload_hash": payload_hash,
        "command": command,
        "submission": submission,
        "decision": decision,
        "audit": audit,
        "outbox": outbox,
    }
    values.update(overrides)
    return PreparedApproval(**values)


def prepared_approval_withdrawal(**overrides: Any):
    from fmea_application.governance_contracts import PreparedApprovalWithdrawal, WithdrawApprovalCommand

    actor = make_governance_actor()
    key = "00000000-0000-4000-8000-000000000708"
    command = WithdrawApprovalCommand("approval-1", HASH, 2, "approval withdrawn", key)
    decision = make_approval_decision()
    withdrawal = __import__(
        "core_domain.fmea.governance", fromlist=["ApprovalWithdrawalRecord"]
    ).ApprovalWithdrawalRecord(
        "approval-withdrawal-1", "approval-1", "revision-1", HASH, actor.actor_id, command.reason, TIMESTAMP
    )
    scope = _scope(actor, "fmea.approval.withdraw", "/fmea/approvals/approval-1/withdrawal", key)
    payload = canonical_governance_payload("approval.withdraw", command, approval=decision, withdrawal=withdrawal)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, withdrawal.withdrawal_id)
    return PreparedApprovalWithdrawal(scope, payload_hash, command, decision, withdrawal, audit, outbox)


def prepared_publication(**overrides: Any):
    from fmea_application.governance_contracts import PreparedPublication

    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))
    revision = make_fmea_revision()
    command = make_publish_command(revision_hash=revision.revision_hash)
    approval = make_approval_decision(revision_hash=revision.revision_hash)
    submission = make_approval_submission(revision_hash=revision.revision_hash)
    snapshot = make_normalized_snapshot()
    manifest = __import__("core_domain.fmea.governance", fromlist=["PublicationManifest"]).PublicationManifest(
        "manifest-1",
        "revision-1",
        revision.revision_hash,
        "approval-1",
        snapshot.snapshot_id,
        snapshot.snapshot_hash,
        HASH,
        None,
        True,
        HASH,
        TIMESTAMP,
    )
    publication = make_published_revision(
        publisher_actor_id=actor.actor_id,
        revision_hash=revision.revision_hash,
        manifest_hash=manifest.manifest_hash,
        snapshot_id=snapshot.snapshot_id,
        snapshot_hash=snapshot.snapshot_hash,
    )
    key = command.idempotency_key
    scope = _scope(actor, "fmea.publication.publish", "/fmea/revisions/revision-1/publications", key)
    payload = canonical_governance_payload(
        "publication.publish",
        command,
        revision=revision,
        approval=approval,
        submission=submission,
        manifest=manifest,
        publication=publication,
        snapshot=snapshot,
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, publication.publication_id)
    values = {
        "scope": scope,
        "payload_hash": payload_hash,
        "command": command,
        "revision_record_version": 1,
        "revision": revision,
        "approval": approval,
        "submission": submission,
        "manifest": manifest,
        "publication": publication,
        "snapshot": snapshot,
        "audit": audit,
        "outbox": outbox,
    }
    values.update(overrides)
    return PreparedPublication(**values)


def prepared_publication_withdrawal(**overrides: Any):
    from fmea_application.governance_contracts import PreparedPublicationWithdrawal, WithdrawPublicationCommand

    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))
    command = WithdrawPublicationCommand("publication-1", 1, "withdrawn", None, "00000000-0000-4000-8000-000000000709")
    publication = make_published_revision()
    withdrawal = __import__(
        "core_domain.fmea.governance", fromlist=["PublicationWithdrawalRecord"]
    ).PublicationWithdrawalRecord(
        "publication-withdrawal-1", "publication-1", None, actor.actor_id, command.reason, TIMESTAMP
    )
    scope = _scope(
        actor, "fmea.publication.withdraw", "/fmea/publications/publication-1/withdrawal", command.idempotency_key
    )
    payload = canonical_governance_payload(
        "publication.withdraw", command, publication=publication, withdrawal=withdrawal
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, withdrawal.withdrawal_id)
    return PreparedPublicationWithdrawal(scope, payload_hash, command, publication, withdrawal, audit, outbox)


def prepared_supersession(**overrides: Any):
    from fmea_application.governance_contracts import PreparedSupersession, SupersedePublicationCommand

    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))
    command = SupersedePublicationCommand(
        "pub-old", "pub-new", 1, 1, "replacement", "00000000-0000-4000-8000-000000000710"
    )
    old_revision = make_fmea_revision()
    replacement_revision = make_fmea_revision(
        revision_id="revision-2",
        parent_revision_id=old_revision.revision_id,
        parent_revision_hash=old_revision.revision_hash,
    )
    old = make_published_revision(publication_id="pub-old", revision_hash=old_revision.revision_hash)
    replacement = make_published_revision(
        publication_id="pub-new", revision_id="revision-2", revision_hash=replacement_revision.revision_hash
    )
    link = make_supersession_record(old_publication_id="pub-old", new_publication_id="pub-new")
    scope = _scope(
        actor, "fmea.publication.supersede", "/fmea/publications/pub-old/supersession", command.idempotency_key
    )
    payload = canonical_governance_payload(
        "publication.supersede",
        command,
        old=old,
        replacement=replacement,
        old_revision=old_revision,
        replacement_revision=replacement_revision,
        supersession=link,
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, link.supersession_id)
    values = {
        "scope": scope,
        "payload_hash": payload_hash,
        "command": command,
        "old_publication": old,
        "replacement_publication": replacement,
        "old_revision": old_revision,
        "replacement_revision": replacement_revision,
        "supersession": link,
        "audit": audit,
        "outbox": outbox,
    }
    values.update(overrides)
    return PreparedSupersession(**values)


def persisted_publication_pair(**overrides: Any):
    result = {
        "old": make_published_revision(publication_id="pub-old"),
        "new": make_published_revision(publication_id="pub-new"),
    }
    result.update(overrides)
    return result
