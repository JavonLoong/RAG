from __future__ import annotations

from hashlib import sha256
from typing import Any

from core_domain.fmea.governance import (
    ApprovalDecision,
    ApprovalStatus,
    ApprovalSubmission,
    FmeaRevision,
    ReadinessIssue,
    RetrievalProvenanceSnapshot,
    SupersessionRecord,
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
from fmea_application.review_contracts import ActorContext, AuditEvent, IdempotencyScope, idempotency_key_hash
from fmea_application.risk_contracts import OutboxEvent, outbox_payload_hash

HASH = "a" * 64
PREFIXED_HASH = "sha256:" + HASH
TIMESTAMP = "2026-08-30T00:00:00Z"


def _record_hash(seed: str) -> str:
    return sha256(seed.encode("utf-8")).hexdigest()


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
        "analysis_hash": HASH,
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
    return FmeaRevision(**values)


def make_large_revision(row_count: int = 10_000, **overrides: Any) -> FmeaRevision:
    values = {
        "row_versions": tuple((f"row-{index}", 1, _record_hash(f"row-{index}")) for index in range(row_count)),
        "risk_versions": (),
    }
    values.update(overrides)
    return make_fmea_revision(**values)


def make_blocked_readiness_report(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"ready": False, "issues": (make_readiness_issue(),)}
    result.update(overrides)
    return result


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
    return PublishedRevision(**values)


def make_normalized_snapshot_input(**overrides: Any):
    from fmea_application.snapshot_contracts import NormalizedSnapshotInput

    revision = overrides.pop("revision", make_fmea_revision())
    row_payload = overrides.pop("row_payload", None)
    rows = overrides.pop("rows", None)
    if isinstance(rows, int):
        rows = tuple(
            {"row_id": f"row-{index}", "failure_mode": "low pressure"}
            for index in range(rows)
        )
    elif rows is None and len(revision.row_versions) > 1:
        rows = tuple(
            {"row_id": row_id, "failure_mode": "low pressure"}
            for row_id, _, _ in revision.row_versions
        )
    values: dict[str, Any] = {
        "revision": revision,
        "publication_id": "publication-1",
        "manifest_id": "manifest-1",
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
    from fmea_application.snapshot_contracts import build_normalized_snapshot, validate_snapshot_publication_binding

    publication_revision_id = overrides.pop("publication_revision_id", None)
    revision_id = overrides.get("revision_id", "revision-1")
    revision = overrides.pop("revision", make_fmea_revision(revision_id=revision_id))
    if publication_revision_id is not None:
        validate_snapshot_publication_binding(revision.revision_id, publication_revision_id)
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


def make_governance_inputs(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "workspace_id": "ws-1",
        "analysis_id": "analysis-1",
        "rows": (),
        "risk_records": (),
        "propagation_graph_revision": None,
        "evidence_packs": (),
        "domain_pack": make_domain_policy(),
        "version_identities": (),
    }
    values.update(overrides)
    return values


def make_assemble_request(**overrides: Any) -> RevisionAssemblyRequest:
    values: dict[str, Any] = {"analysis_id": "analysis-1", "parent_revision_id": None, "expected_analysis_version": 1}
    values.update(overrides)
    return RevisionAssemblyRequest(**values)


def make_readiness_context(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {"required_fields_accepted": True, "required_risk_confirmed": True, "propagation_confirmed": True}
    values.update(overrides)
    return values


def make_domain_policy(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {"allow_acknowledged_blocking": True, "required_risk": True, "required_propagation": True}
    values.update(overrides)
    return values


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


def _audit(scope: IdempotencyScope, payload_hash: str, *, aggregate_id: str, analysis_id: str = "analysis-1") -> AuditEvent:
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


def _prepared_events(scope: IdempotencyScope, payload_hash: str, payload: dict[str, Any], aggregate_id: str) -> tuple[AuditEvent, OutboxEvent]:
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
    command = __import__("fmea_application.governance_contracts", fromlist=["AssembleRevisionCommand"]).AssembleRevisionCommand(
        request=make_assemble_request(), idempotency_key=key
    )
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
    return PreparedApprovalSubmission(scope, payload_hash, command, submission, audit, outbox)


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
    values = {"scope": scope, "payload_hash": payload_hash, "command": command, "submission": submission, "decision": decision, "audit": audit, "outbox": outbox}
    values.update(overrides)
    return PreparedApproval(**values)


def prepared_approval_withdrawal(**overrides: Any):
    from fmea_application.governance_contracts import PreparedApprovalWithdrawal, WithdrawApprovalCommand

    actor = make_governance_actor()
    key = "00000000-0000-4000-8000-000000000708"
    command = WithdrawApprovalCommand("approval-1", HASH, 2, "approval withdrawn", key)
    decision = make_approval_decision()
    withdrawal = __import__("core_domain.fmea.governance", fromlist=["ApprovalWithdrawalRecord"]).ApprovalWithdrawalRecord(
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
    command = make_publish_command()
    revision = make_fmea_revision()
    approval = make_approval_decision()
    snapshot = make_normalized_snapshot()
    manifest = __import__("core_domain.fmea.governance", fromlist=["PublicationManifest"]).PublicationManifest(
        "manifest-1",
        "revision-1",
        HASH,
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
        manifest_hash=manifest.manifest_hash,
        snapshot_id=snapshot.snapshot_id,
        snapshot_hash=snapshot.snapshot_hash,
    )
    key = command.idempotency_key
    scope = _scope(actor, "fmea.publication.publish", "/fmea/revisions/revision-1/publications", key)
    payload = canonical_governance_payload("publication.publish", command, revision=revision, approval=approval, manifest=manifest, publication=publication, snapshot=snapshot)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, publication.publication_id)
    values = {"scope": scope, "payload_hash": payload_hash, "command": command, "revision": revision, "approval": approval, "manifest": manifest, "publication": publication, "snapshot": snapshot, "audit": audit, "outbox": outbox}
    values.update(overrides)
    return PreparedPublication(**values)


def prepared_publication_withdrawal(**overrides: Any):
    from fmea_application.governance_contracts import PreparedPublicationWithdrawal, WithdrawPublicationCommand

    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))
    command = WithdrawPublicationCommand("publication-1", 1, "withdrawn", None, "00000000-0000-4000-8000-000000000709")
    publication = make_published_revision()
    withdrawal = __import__("core_domain.fmea.governance", fromlist=["PublicationWithdrawalRecord"]).PublicationWithdrawalRecord(
        "publication-withdrawal-1", "publication-1", None, actor.actor_id, command.reason, TIMESTAMP
    )
    scope = _scope(actor, "fmea.publication.withdraw", "/fmea/publications/publication-1/withdrawal", command.idempotency_key)
    payload = canonical_governance_payload("publication.withdraw", command, publication=publication, withdrawal=withdrawal)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, withdrawal.withdrawal_id)
    return PreparedPublicationWithdrawal(scope, payload_hash, command, publication, withdrawal, audit, outbox)


def prepared_supersession(**overrides: Any):
    from fmea_application.governance_contracts import PreparedSupersession, SupersedePublicationCommand

    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))
    command = SupersedePublicationCommand("pub-old", "pub-new", 1, 1, "replacement", "00000000-0000-4000-8000-000000000710")
    old = make_published_revision(publication_id="pub-old")
    replacement = make_published_revision(publication_id="pub-new")
    link = make_supersession_record(old_publication_id="pub-old", new_publication_id="pub-new")
    scope = _scope(actor, "fmea.publication.supersede", "/fmea/publications/pub-old/supersession", command.idempotency_key)
    payload = canonical_governance_payload("publication.supersede", command, old=old, replacement=replacement, supersession=link)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, payload, link.supersession_id)
    values = {"scope": scope, "payload_hash": payload_hash, "command": command, "old_publication": old, "replacement_publication": replacement, "supersession": link, "audit": audit, "outbox": outbox}
    values.update(overrides)
    return PreparedSupersession(**values)


def persisted_publication_pair(**overrides: Any):
    result = {"old": make_published_revision(publication_id="pub-old"), "new": make_published_revision(publication_id="pub-new")}
    result.update(overrides)
    return result
