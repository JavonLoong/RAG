"""Unit coverage for revision governance orchestration."""

from __future__ import annotations

import pytest
from fmea_governance_fixtures import (
    make_approval_submission,
    make_fmea_revision,
    make_governance_actor,
    make_governance_assembler,
    make_governance_inputs,
    make_runtime_readiness,
)

from core_domain.fmea.governance import ApprovalStatus
from fmea_application.governance_service import RevisionGovernanceService
from fmea_application.review_errors import ReviewError


class _Repository:
    """Small repository double that records prepared writes for service tests."""

    def __init__(self) -> None:
        self.revisions = {}
        self.submissions = {}
        self.approvals = {}
        self.publications = {}
        self.snapshots = {}
        self.writes: list[object] = []

    def get_revision(self, revision_id: str, workspace_id: str):
        value = self.revisions.get((workspace_id, revision_id))
        return None if value is None else value.revision

    def get_publication(self, publication_id: str, workspace_id: str):
        value = self.publications.get((workspace_id, publication_id))
        return None if value is None else value.publication

    def get_snapshot(self, publication_id: str, workspace_id: str):
        value = self.snapshots.get((workspace_id, publication_id))
        return None if value is None else value

    def replay_revision(self, *_args):
        return None

    def commit_revision(self, prepared):
        self.revisions[(prepared.revision.workspace_id, prepared.revision.revision_id)] = prepared
        self.writes.append(prepared)
        from fmea_application.governance_contracts import RevisionResult

        return RevisionResult(prepared.revision.revision_id, 1, prepared.audit.event_id, prepared.outbox.event_id)

    def replay_approval_submission(self, *_args):
        return None

    def commit_approval_submission(self, prepared):
        self.submissions[(prepared.submission.workspace_id, prepared.submission.submission_id)] = prepared.submission
        self.writes.append(prepared)
        from fmea_application.governance_contracts import ApprovalSubmissionResult

        return ApprovalSubmissionResult(
            prepared.submission.submission_id, 1, prepared.audit.event_id, prepared.outbox.event_id
        )

    def replay_approval_decision(self, *_args):
        return None

    def commit_approval(self, prepared):
        self.approvals[(prepared.submission.workspace_id, prepared.decision.approval_id)] = prepared.decision
        self.writes.append(prepared)
        from fmea_application.governance_contracts import ApprovalResult

        return ApprovalResult(prepared.decision.approval_id, 1, prepared.audit.event_id, prepared.outbox.event_id)

    def replay_approval_withdrawal(self, *_args):
        return None

    def commit_approval_withdrawal(self, prepared):
        self.writes.append(prepared)
        from fmea_application.governance_contracts import ApprovalWithdrawalResult

        return ApprovalWithdrawalResult(
            prepared.withdrawal.withdrawal_id,
            prepared.withdrawal.approval_id,
            prepared.audit.event_id,
            prepared.outbox.event_id,
        )

    def replay_publication(self, *_args):
        return None

    def commit_publication(self, prepared):
        self.publications[(prepared.publication.workspace_id, prepared.publication.publication_id)] = prepared
        self.snapshots[(prepared.snapshot.workspace_id, prepared.publication.publication_id)] = prepared.snapshot
        self.writes.append(prepared)
        from fmea_application.governance_contracts import PublicationResult

        return PublicationResult(
            prepared.publication.publication_id,
            prepared.manifest.manifest_id,
            prepared.snapshot.snapshot_id,
            1,
            prepared.audit.event_id,
            prepared.outbox.event_id,
        )

    def replay_publication_withdrawal(self, *_args):
        return None

    def commit_publication_withdrawal(self, prepared):
        self.writes.append(prepared)
        from fmea_application.governance_contracts import PublicationWithdrawalResult

        return PublicationWithdrawalResult(
            prepared.withdrawal.withdrawal_id,
            prepared.withdrawal.publication_id,
            prepared.audit.event_id,
            prepared.outbox.event_id,
        )

    def replay_supersession(self, *_args):
        return None

    def commit_supersession(self, prepared):
        self.writes.append(prepared)
        from fmea_application.governance_contracts import SupersessionResult

        return SupersessionResult(
            prepared.supersession.supersession_id,
            prepared.supersession.old_publication_id,
            prepared.supersession.new_publication_id,
            prepared.audit.event_id,
            prepared.outbox.event_id,
        )

    def list_approval_events(self, _query):
        return ()

    def list_publication_events(self, _query):
        return ()


def _service(repository: _Repository | None = None) -> tuple[RevisionGovernanceService, _Repository, object]:
    inputs = make_governance_inputs()
    assembler = make_governance_assembler(inputs)
    policy, _context = make_runtime_readiness(governance_inputs=inputs)
    repository = repository or _Repository()

    class _Source:
        def load_inputs(self, _analysis_id: str, _workspace_id: str):
            return inputs

    service = RevisionGovernanceService(
        repository,
        assembler=assembler,
        readiness_policy=policy,
        source=_Source(),
        clock=lambda: "2026-08-30T00:00:00Z",
        id_factory=lambda prefix: f"{prefix.replace(':', '-')}-test",
    )
    return service, repository, inputs


def test_assemble_and_submit_bind_to_server_revision() -> None:
    service, repository, _inputs = _service()
    actor = make_governance_actor(actor_id="reviewer-1", roles=frozenset({"reviewer"}))

    from fmea_application.governance_contracts import (
        AssembleRevisionCommand,
        RevisionAssemblyRequest,
        SubmitApprovalCommand,
    )

    assembled = service.assemble(
        AssembleRevisionCommand(RevisionAssemblyRequest("analysis-1", None, 1), "00000000-0000-4000-8000-000000000711"),
        actor,
    )
    revision = repository.get_revision(assembled.revision_id, actor.workspace_id)
    assert revision is not None

    submitted = service.submit_for_approval(
        SubmitApprovalCommand(revision.revision_id, revision.revision_hash, assembled.record_version, "00000000-0000-4000-8000-000000000712"),
        actor,
    )
    assert submitted.submission_id
    assert repository.submissions


def test_approval_publication_and_withdrawal_use_server_state() -> None:
    service, repository, _inputs = _service()
    from fmea_application.revision_assembler import PublicationReadinessReport

    class _AlwaysReady:
        def evaluate(self, revision, _context):
            return PublicationReadinessReport(
                revision.revision_id,
                revision.workspace_id,
                revision.analysis_id,
                revision.revision_hash,
                revision.analysis_record_version,
                tuple(pack_id for pack_id, _ in revision.evidence_pack_hashes),
                True,
                (),
                (),
            )

    service._readiness_policy = _AlwaysReady()
    reviewer = make_governance_actor(actor_id="reviewer-1", roles=frozenset({"reviewer"}))
    approver = make_governance_actor(actor_id="approver-1", roles=frozenset({"approver"}))
    publisher = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    from fmea_application.governance_contracts import (
        ApprovalCommand,
        AssembleRevisionCommand,
        PublishCommand,
        RevisionAssemblyRequest,
        SubmitApprovalCommand,
        WithdrawPublicationCommand,
    )

    assembled = service.assemble(
        AssembleRevisionCommand(
            RevisionAssemblyRequest("analysis-1", None, 1), "00000000-0000-4000-8000-000000000714"
        ),
        reviewer,
    )
    revision = repository.revisions[(reviewer.workspace_id, assembled.revision_id)].revision
    submitted = service.submit_for_approval(
        SubmitApprovalCommand(
            revision.revision_id,
            revision.revision_hash,
            assembled.record_version,
            "00000000-0000-4000-8000-000000000715",
        ),
        reviewer,
    )
    approved = service.approve(
        ApprovalCommand(
            submitted.submission_id,
            revision.revision_id,
            revision.revision_hash,
            submitted.record_version,
            "human approval",
            "00000000-0000-4000-8000-000000000716",
        ),
        approver,
    )
    published = service.publish(
        PublishCommand(
            revision.revision_id,
            revision.revision_hash,
            approved.approval_id,
            assembled.record_version,
            "00000000-0000-4000-8000-000000000717",
        ),
        publisher,
    )
    assert service.get_publication(published.publication_id, publisher).effective_status.value == "published"

    withdrawn = service.withdraw_publication(
        WithdrawPublicationCommand(
            published.publication_id,
            published.record_version,
            "replacement is ready",
            None,
            "00000000-0000-4000-8000-000000000718",
        ),
        publisher,
    )
    assert withdrawn.publication_id == published.publication_id
    assert service.get_publication(published.publication_id, publisher).effective_status.value == "withdrawn"


def test_publish_rejects_revision_hash_change_after_approval() -> None:
    service, repository, _inputs = _service()
    revision = make_fmea_revision()
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    from fmea_application.governance_contracts import PublishCommand

    repository.revisions[(revision.workspace_id, revision.revision_id)] = type("Prepared", (), {"revision": revision})()
    repository.submissions[(revision.workspace_id, "submission-1")] = make_approval_submission(
        revision_hash=revision.revision_hash
    )
    service._submissions[("ws-1", "submission-1")] = repository.submissions[("ws-1", "submission-1")]
    service._approvals[("ws-1", "approval-1")] = type("Approval", (), {"approval_id": "approval-1", "submission_id": "submission-1", "revision_id": revision.revision_id, "revision_hash": revision.revision_hash, "status": ApprovalStatus.APPROVED, "approver_actor_id": "approver-1", "reason": "ok", "record_version": 2, "created_at": "2026-08-30T00:00:00Z", "workspace_id": "ws-1"})()

    with pytest.raises(ReviewError) as captured:
        service.publish(
            PublishCommand(revision.revision_id, "b" * 64, "approval-1", 1, "00000000-0000-4000-8000-000000000713"),
            actor,
        )
    assert captured.value.code == "FMEA_GOVERNANCE_APPROVAL_STALE"
