from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace

import pytest
from fmea_governance_fixtures import (
    make_approval_decision,
    make_approval_submission,
    make_fmea_revision,
    make_governance_actor,
    make_published_revision,
    make_supersession_record,
    prepared_approval,
    prepared_approval_submission,
    prepared_approval_withdrawal,
    prepared_publication,
    prepared_publication_withdrawal,
    prepared_revision,
    prepared_supersession,
)

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.governance import (
    ApprovalStatus,
    FmeaRevision,
    RevisionPublicationStatus,
    project_publication_lifecycle,
    revision_content_hash,
    validate_approval_binding,
    validate_supersession_binding,
)
from core_domain.fmea.states import PublicationStatus
from fmea_application.governance_contracts import (
    ApprovalCommand,
    PreparedApproval,
    PreparedApprovalWithdrawal,
    PreparedPublication,
    PreparedRevision,
    PreparedSupersession,
    canonical_governance_payload,
    governance_payload_hash,
)
from fmea_application.risk_contracts import outbox_payload_hash


def _rebind_prepared_approval(prepared: PreparedApproval, *, submission: object) -> PreparedApproval:
    payload = canonical_governance_payload(
        "approval.decide",
        prepared.command,
        submission=submission,
        decision=prepared.decision,
    )
    payload_hash = governance_payload_hash(payload)
    return PreparedApproval(
        scope=prepared.scope,
        payload_hash=payload_hash,
        command=prepared.command,
        submission=submission,  # type: ignore[arg-type]
        decision=prepared.decision,
        audit=replace(prepared.audit, canonical_payload_hash=payload_hash),
        outbox=replace(prepared.outbox, payload=payload, payload_hash=outbox_payload_hash(payload)),
    )


def _rebind_prepared_publication(
    prepared: PreparedPublication,
    *,
    publication: object,
    snapshot: object,
    submission: object | None = None,
    audit: object | None = None,
    outbox: object | None = None,
) -> PreparedPublication:
    submission_value = prepared.submission if submission is None else submission
    payload = canonical_governance_payload(
        "publication.publish",
        prepared.command,
        revision=prepared.revision,
        approval=prepared.approval,
        submission=submission_value,
        manifest=prepared.manifest,
        publication=publication,
        snapshot=snapshot,
    )
    payload_hash = governance_payload_hash(payload)
    audit_value = prepared.audit if audit is None else audit
    outbox_value = prepared.outbox if outbox is None else outbox
    return PreparedPublication(
        scope=prepared.scope,
        payload_hash=payload_hash,
        command=prepared.command,
        revision=prepared.revision,
        approval=prepared.approval,
        submission=submission_value,  # type: ignore[arg-type]
        manifest=prepared.manifest,
        publication=publication,  # type: ignore[arg-type]
        snapshot=snapshot,  # type: ignore[arg-type]
        audit=replace(audit_value, canonical_payload_hash=payload_hash),  # type: ignore[arg-type]
        outbox=replace(outbox_value, payload=payload, payload_hash=outbox_payload_hash(payload)),  # type: ignore[arg-type]
    )


def _rebind_prepared_approval_withdrawal(
    prepared: PreparedApprovalWithdrawal,
    *,
    approval: object,
    withdrawal: object,
    command: object | None = None,
) -> PreparedApprovalWithdrawal:
    command_value = prepared.command if command is None else command
    payload = canonical_governance_payload(
        "approval.withdraw",
        command_value,
        approval=approval,
        withdrawal=withdrawal,
    )
    payload_hash = governance_payload_hash(payload)
    return PreparedApprovalWithdrawal(
        scope=prepared.scope,
        payload_hash=payload_hash,
        command=command_value,  # type: ignore[arg-type]
        approval=approval,  # type: ignore[arg-type]
        withdrawal=withdrawal,  # type: ignore[arg-type]
        audit=replace(prepared.audit, canonical_payload_hash=payload_hash),
        outbox=replace(prepared.outbox, payload=payload, payload_hash=outbox_payload_hash(payload)),
    )


def test_approval_decision_binds_exact_revision_hash() -> None:
    decision = make_approval_decision(revision_hash="a" * 64)
    with pytest.raises(FmeaDomainError, match="approval revision hash mismatch"):
        validate_approval_binding(decision, make_fmea_revision())


def test_approval_submission_is_pending_and_decision_has_terminal_status() -> None:
    submission = make_approval_submission()
    assert submission.status is ApprovalStatus.PENDING

    with pytest.raises(FmeaDomainError, match="approval decision status"):
        make_approval_decision(status=ApprovalStatus.PENDING)


def test_supersession_is_a_link_and_does_not_mutate_old_publication() -> None:
    old_revision = make_fmea_revision(revision_id="rev-old")
    new_revision = make_fmea_revision(
        revision_id="rev-new",
        parent_revision_id=old_revision.revision_id,
        parent_revision_hash=old_revision.revision_hash,
    )
    old = make_published_revision(
        publication_id="pub-old",
        revision_id=old_revision.revision_id,
        revision_hash=old_revision.revision_hash,
    )
    new = make_published_revision(
        publication_id="pub-new",
        revision_id=new_revision.revision_id,
        revision_hash=new_revision.revision_hash,
    )
    link = make_supersession_record(old_publication_id=old.publication_id, new_publication_id=new.publication_id)
    validate_supersession_binding(
        link,
        old=old,
        replacement=new,
        old_revision=old_revision,
        replacement_revision=new_revision,
    )
    view = project_publication_lifecycle(old, withdrawal=None, supersession=link)
    assert view.publication == old
    assert view.effective_status is RevisionPublicationStatus.SUPERSEDED
    assert old.publication_id == "pub-old"


def test_legacy_row_publication_status_remains_unchanged() -> None:
    assert tuple(status.value for status in PublicationStatus) == ("unpublished", "published", "withdrawn")
    assert RevisionPublicationStatus.SUPERSEDED.value == "superseded"


def test_revision_content_hash_excludes_revision_hash_and_created_at() -> None:
    revision = make_fmea_revision(created_at="2026-08-30T00:00:00Z")
    changed_metadata = replace(revision, created_at="2026-08-31T00:00:00Z")
    assert governance_payload_hash(
        canonical_governance_payload("revision", revision, exclude_fields=("revision_hash", "created_at"))
    ) == governance_payload_hash(
        canonical_governance_payload("revision", changed_metadata, exclude_fields=("revision_hash", "created_at"))
    )


def test_governance_contracts_are_immutable() -> None:
    revision = make_fmea_revision()
    with pytest.raises(FrozenInstanceError):
        revision.revision_id = "changed"  # type: ignore[misc]


def test_prepared_revision_binds_scope_command_audit_and_outbox() -> None:
    prepared = prepared_revision()
    assert isinstance(prepared, PreparedRevision)
    assert prepared.payload_hash == governance_payload_hash(prepared.payload)
    assert prepared.audit.actor_id == prepared.scope.actor_id
    assert prepared.outbox.scope_key == prepared.scope.scope_key


def test_prepared_approval_rejects_payload_hash_tampering() -> None:
    prepared = prepared_approval()
    with pytest.raises(ValueError, match="payload hash does not match canonical payload"):
        PreparedApproval(
            scope=prepared.scope,
            payload_hash="sha256:" + "c" * 64,
            command=prepared.command,
            submission=prepared.submission,
            decision=prepared.decision,
            audit=prepared.audit,
            outbox=prepared.outbox,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    (("revision_id", "revision-2"), ("revision_hash", "b" * 64)),
)
def test_prepared_approval_rejects_submission_command_revision_mismatch(field_name: str, value: str) -> None:
    prepared = prepared_approval()
    mismatched_submission = replace(prepared.submission, **{field_name: value})
    with pytest.raises(ValueError, match="approval revision binding is invalid"):
        _rebind_prepared_approval(prepared, submission=mismatched_submission)


def test_prepared_publication_requires_explicit_approval_submission_lineage() -> None:
    assert "submission" in {field.name for field in fields(PreparedPublication)}


def test_prepared_publication_rejects_cross_analysis_publication() -> None:
    prepared = prepared_publication()
    mismatched_publication = replace(prepared.publication, analysis_id="analysis-2")
    with pytest.raises(ValueError, match="publication analysis binding is invalid"):
        _rebind_prepared_publication(prepared, publication=mismatched_publication, snapshot=prepared.snapshot)


def test_prepared_publication_rejects_cross_workspace_snapshot() -> None:
    prepared = prepared_publication()
    mismatched_snapshot = __import__("fmea_governance_fixtures", fromlist=["make_normalized_snapshot"]).make_normalized_snapshot(
        revision=make_fmea_revision(workspace_id="ws-2")
    )
    with pytest.raises(ValueError, match="publication snapshot workspace binding is invalid"):
        _rebind_prepared_publication(prepared, publication=prepared.publication, snapshot=mismatched_snapshot)


def test_prepared_publication_rejects_cross_workspace_approval_submission() -> None:
    prepared = prepared_publication()
    mismatched_submission = replace(prepared.submission, workspace_id="ws-2")
    with pytest.raises(ValueError, match="publication approval submission binding is invalid"):
        _rebind_prepared_publication(
            prepared,
            publication=prepared.publication,
            snapshot=prepared.snapshot,
            submission=mismatched_submission,
        )


def test_prepared_publication_rejects_publication_actor_mismatch() -> None:
    prepared = prepared_publication()
    mismatched_publication = replace(prepared.publication, publisher_actor_id="publisher-2")
    with pytest.raises(ValueError, match="publication actor binding is invalid"):
        _rebind_prepared_publication(prepared, publication=mismatched_publication, snapshot=prepared.snapshot)


def test_prepared_publication_rejects_audit_actor_mismatch() -> None:
    prepared = prepared_publication()
    mismatched_audit = replace(prepared.audit, actor_id="publisher-2")
    with pytest.raises(ValueError, match="audit actor binding is invalid"):
        _rebind_prepared_publication(
            prepared,
            publication=prepared.publication,
            snapshot=prepared.snapshot,
            audit=mismatched_audit,
        )


def test_prepared_publication_rejects_outbox_scope_mismatch() -> None:
    prepared = prepared_publication()
    mismatched_outbox = replace(prepared.outbox, scope_key="f" * 64)
    with pytest.raises(ValueError, match="outbox command binding is invalid"):
        _rebind_prepared_publication(
            prepared,
            publication=prepared.publication,
            snapshot=prepared.snapshot,
            outbox=mismatched_outbox,
        )


def test_prepared_supersession_requires_exact_revision_evidence() -> None:
    assert {"old_revision", "replacement_revision"} <= {field.name for field in fields(PreparedSupersession)}


def _rebind_prepared_supersession(
    prepared: PreparedSupersession,
    *,
    replacement_revision: object,
) -> PreparedSupersession:
    replacement_publication = replace(
        prepared.replacement_publication,
        analysis_id=replacement_revision.analysis_id,  # type: ignore[union-attr]
        revision_hash=replacement_revision.revision_hash,  # type: ignore[union-attr]
    )
    payload = canonical_governance_payload(
        "publication.supersede",
        prepared.command,
        old=prepared.old_publication,
        replacement=replacement_publication,
        old_revision=prepared.old_revision,
        replacement_revision=replacement_revision,
        supersession=prepared.supersession,
    )
    payload_hash = governance_payload_hash(payload)
    return PreparedSupersession(
        scope=prepared.scope,
        payload_hash=payload_hash,
        command=prepared.command,
        old_publication=prepared.old_publication,
        replacement_publication=replacement_publication,
        old_revision=prepared.old_revision,
        replacement_revision=replacement_revision,  # type: ignore[arg-type]
        supersession=prepared.supersession,
        audit=replace(prepared.audit, canonical_payload_hash=payload_hash),
        outbox=replace(prepared.outbox, payload=payload, payload_hash=outbox_payload_hash(payload)),
    )


@pytest.mark.parametrize("replacement_revision", ("cross_analysis", "non_child", "wrong_parent_hash"))
def test_prepared_supersession_rejects_invalid_revision_lineage(replacement_revision: str) -> None:
    prepared = prepared_supersession()
    overrides = {
        "revision_id": prepared.replacement_revision.revision_id,
        "workspace_id": prepared.replacement_revision.workspace_id,
        "analysis_id": prepared.replacement_revision.analysis_id,
        "parent_revision_id": prepared.old_revision.revision_id,
        "parent_revision_hash": prepared.old_revision.revision_hash,
    }
    if replacement_revision == "cross_analysis":
        overrides["analysis_id"] = "analysis-2"
    elif replacement_revision == "non_child":
        overrides["parent_revision_id"] = None
        overrides["parent_revision_hash"] = None
    else:
        overrides["parent_revision_hash"] = "b" * 64
    invalid_revision = make_fmea_revision(**overrides)
    with pytest.raises(FmeaDomainError, match="supersession (analysis|parent revision)"):
        _rebind_prepared_supersession(prepared, replacement_revision=invalid_revision)


def test_revision_rejects_valid_format_but_wrong_content_hash() -> None:
    with pytest.raises(FmeaDomainError, match="revision hash"):
        make_fmea_revision(revision_hash="b" * 64)


def test_revision_factory_uses_the_real_content_hash() -> None:
    revision = make_fmea_revision()
    assert isinstance(revision, FmeaRevision)
    assert revision_content_hash(revision) == revision.revision_hash


def test_approval_withdrawal_rejects_rejected_decision() -> None:
    prepared = prepared_approval_withdrawal()
    rejected = replace(prepared.approval, status=ApprovalStatus.REJECTED)
    with pytest.raises(ValueError, match="approval withdrawal requires an approved decision"):
        _rebind_prepared_approval_withdrawal(prepared, approval=rejected, withdrawal=prepared.withdrawal)


def test_approval_withdrawal_rejects_revision_identity_mismatch() -> None:
    prepared = prepared_approval_withdrawal()
    mismatched_withdrawal = replace(prepared.withdrawal, revision_id="revision-2")
    with pytest.raises(ValueError, match="approval withdrawal revision binding is invalid"):
        _rebind_prepared_approval_withdrawal(prepared, approval=prepared.approval, withdrawal=mismatched_withdrawal)


def test_approval_withdrawal_rejects_expected_version_mismatch() -> None:
    prepared = prepared_approval_withdrawal()
    mismatched_command = replace(prepared.command, expected_approval_version=1)
    with pytest.raises(ValueError, match="approval withdrawal version binding is invalid"):
        _rebind_prepared_approval_withdrawal(
            prepared,
            approval=prepared.approval,
            withdrawal=prepared.withdrawal,
            command=mismatched_command,
        )


def test_approval_command_keeps_exact_revision_precondition() -> None:
    actor = make_governance_actor()
    command = ApprovalCommand(
        submission_id="submission-1",
        revision_id="revision-1",
        revision_hash="a" * 64,
        expected_submission_version=1,
        reason="approved by human reviewer",
        idempotency_key="00000000-0000-4000-8000-000000000701",
    )
    assert actor.workspace_id == "ws-1"
    assert command.revision_hash == "a" * 64


def test_deterministic_prepared_factories_bind_each_governance_write() -> None:
    assert prepared_approval_submission().submission.status is ApprovalStatus.PENDING
    assert prepared_approval().decision.status is ApprovalStatus.APPROVED
    assert prepared_approval_withdrawal().withdrawal.approval_id == "approval-1"
    assert prepared_publication().publication.revision_id == "revision-1"
    assert prepared_publication_withdrawal().withdrawal.publication_id == "publication-1"
    assert prepared_supersession().supersession.old_publication_id == "pub-old"
