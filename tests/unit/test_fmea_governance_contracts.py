from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

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
    RevisionPublicationStatus,
    project_publication_lifecycle,
    validate_approval_binding,
    validate_supersession_binding,
)
from core_domain.fmea.states import PublicationStatus
from fmea_application.governance_contracts import (
    ApprovalCommand,
    PreparedApproval,
    PreparedRevision,
    canonical_governance_payload,
    governance_payload_hash,
)


def test_approval_decision_binds_exact_revision_hash() -> None:
    decision = make_approval_decision(revision_hash="a" * 64)
    with pytest.raises(FmeaDomainError, match="approval revision hash mismatch"):
        validate_approval_binding(decision, make_fmea_revision(revision_hash="b" * 64))


def test_approval_submission_is_pending_and_decision_has_terminal_status() -> None:
    submission = make_approval_submission()
    assert submission.status is ApprovalStatus.PENDING

    with pytest.raises(FmeaDomainError, match="approval decision status"):
        make_approval_decision(status=ApprovalStatus.PENDING)


def test_supersession_is_a_link_and_does_not_mutate_old_publication() -> None:
    old_revision = make_fmea_revision(revision_id="rev-old")
    new_revision = make_fmea_revision(revision_id="rev-new", parent_revision_id=old_revision.revision_id)
    old = make_published_revision(publication_id="pub-old", revision_id=old_revision.revision_id)
    new = make_published_revision(publication_id="pub-new", revision_id=new_revision.revision_id)
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
    revision = make_fmea_revision(revision_hash="a" * 64, created_at="2026-08-30T00:00:00Z")
    changed_metadata = replace(revision, revision_hash="b" * 64, created_at="2026-08-31T00:00:00Z")
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
