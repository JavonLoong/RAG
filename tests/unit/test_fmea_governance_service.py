"""Unit coverage for revision governance orchestration."""

from __future__ import annotations

import pytest
from fmea_governance_fixtures import (
    make_approval_decision,
    make_approval_submission,
    make_fmea_revision,
    make_governance_actor,
    make_governance_assembler,
    make_governance_inputs,
    make_published_revision,
    make_runtime_readiness,
    make_supersession_record,
)

from core_domain.fmea.governance import (
    ApprovalStatus,
    PublicationWithdrawalRecord,
    project_publication_lifecycle,
)
from fmea_application.governance_contracts import (
    ApprovalCommand,
    ApprovalRejectionCommand,
    ApprovalResult,
    ApprovalSubmissionResult,
    AssembleRevisionCommand,
    PublicationResult,
    PublicationWithdrawalResult,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    SupersessionResult,
    WithdrawApprovalCommand,
    WithdrawPublicationCommand,
)
from fmea_application.governance_service import RevisionGovernanceService
from fmea_application.ports import ApprovalWithdrawalResult
from fmea_application.review_errors import ReviewError


class _Repository:
    """Small repository double that records prepared writes for service tests."""

    def __init__(self) -> None:
        self.revisions = {}
        self.submissions = {}
        self.approvals = {}
        self.publications = {}
        self.snapshots = {}
        self.approval_withdrawals = {}
        self.publication_withdrawals = {}
        self.supersessions = {}
        self.writes: list[object] = []

    def replay_governance_command(self, *_args):
        return None

    def get_revision(self, revision_id: str, workspace_id: str):
        value = self.revisions.get((workspace_id, revision_id))
        return None if value is None else value.revision

    def get_revision_record_version(self, revision_id: str, workspace_id: str):
        value = self.revisions.get((workspace_id, revision_id))
        return None if value is None else 1

    def get_approval_submission(self, submission_id: str, workspace_id: str):
        return self.submissions.get((workspace_id, submission_id))

    def get_approval_decision(self, approval_id: str, workspace_id: str):
        return self.approvals.get((workspace_id, approval_id))

    def get_approval_decision_for_submission(self, submission_id: str, workspace_id: str):
        return next(
            (
                value
                for (item_workspace, _), value in self.approvals.items()
                if item_workspace == workspace_id and value.submission_id == submission_id
            ),
            None,
        )

    def get_approval_withdrawal(self, approval_id: str, workspace_id: str):
        return self.approval_withdrawals.get((workspace_id, approval_id))

    def get_publication_lifecycle(self, publication_id: str, workspace_id: str):
        value = self.publications.get((workspace_id, publication_id))
        if value is None:
            return None
        publication = value.publication
        return project_publication_lifecycle(
            publication,
            withdrawal=self.publication_withdrawals.get((workspace_id, publication_id)),
            supersession=self.supersessions.get((workspace_id, publication_id)),
        )

    def get_current_publication_audit_head(self, workspace_id: str):
        values = [
            value.publication.audit_chain_head
            for (item_workspace, _), value in self.publications.items()
            if item_workspace == workspace_id
        ]
        return None if not values else values[-1]

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
        self.approval_withdrawals[(prepared.scope.workspace_id, prepared.withdrawal.approval_id)] = prepared.withdrawal
        self.writes.append(prepared)
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
        self.publication_withdrawals[(prepared.scope.workspace_id, prepared.withdrawal.publication_id)] = (
            prepared.withdrawal
        )
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
        self.supersessions[(prepared.scope.workspace_id, prepared.supersession.old_publication_id)] = (
            prepared.supersession
        )
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


class _EarlyReplayRepository:
    def __init__(self, expected_kind: str, expected_command: object, result: object) -> None:
        self.expected_kind = expected_kind
        self.expected_command = expected_command
        self.result = result

    def replay_governance_command(self, kind, _scope, command):
        if kind != self.expected_kind or command != self.expected_command:
            raise ReviewError(
                "FMEA_IDEMPOTENCY_CONFLICT",
                "Idempotency key was already used with a different command.",
            )
        return self.result


def _early_replay_service(repository: object) -> RevisionGovernanceService:
    return RevisionGovernanceService(repository, assembler=None, readiness_policy=None, source=None)


def test_approval_same_command_replays_before_current_decision_guard() -> None:
    command = __import__("fmea_governance_fixtures", fromlist=["make_approval_command"]).make_approval_command()
    expected = ApprovalResult("approval-1", 2, "audit-1", "outbox-1", replayed=True)
    service = _early_replay_service(_EarlyReplayRepository("approve", command, expected))
    actor = make_governance_actor(actor_id="approver-1", roles=frozenset({"approver"}))

    assert service.approve(command, actor) == expected


def test_publish_same_command_replays_before_current_publication_guards() -> None:
    command = __import__("fmea_governance_fixtures", fromlist=["make_publish_command"]).make_publish_command()
    expected = PublicationResult("publication-1", "manifest-1", "snapshot-1", 1, "audit-1", "outbox-1", replayed=True)
    service = _early_replay_service(_EarlyReplayRepository("publish", command, expected))
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    assert service.publish(command, actor) == expected


@pytest.mark.parametrize(
    "result",
    [
        ApprovalResult("approval-1", 2, "audit-1", "outbox-1", replayed=True),
        PublicationResult("publication-1", "manifest-1", "snapshot-1", 1, "audit-1", "outbox-1"),
    ],
)
def test_early_replay_wrong_result_type_or_flag_fails_closed(result: object) -> None:
    command = __import__("fmea_governance_fixtures", fromlist=["make_publish_command"]).make_publish_command()
    service = _early_replay_service(_EarlyReplayRepository("publish", command, result))
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    with pytest.raises(ReviewError) as captured:
        service.publish(command, actor)

    assert captured.value.code == "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID"


def test_changed_approval_command_in_same_scope_is_idempotency_conflict() -> None:
    command = __import__("fmea_governance_fixtures", fromlist=["make_approval_command"]).make_approval_command()
    changed = ApprovalCommand(
        command.submission_id,
        command.revision_id,
        command.revision_hash,
        command.expected_submission_version,
        "changed reason",
        command.idempotency_key,
    )
    expected = ApprovalResult("approval-1", 2, "audit-1", "outbox-1", replayed=True)
    service = _early_replay_service(_EarlyReplayRepository("approve", command, expected))
    actor = make_governance_actor(actor_id="approver-1", roles=frozenset({"approver"}))

    with pytest.raises(ReviewError) as captured:
        service.approve(changed, actor)
    assert captured.value.code == "FMEA_GOVERNANCE_IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize(
    ("kind", "method_name", "command", "actor", "result"),
    [
        (
            "assemble",
            "assemble",
            AssembleRevisionCommand(
                __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request(),
                "00000000-0000-4000-8000-000000000752",
            ),
            make_governance_actor(actor_id="reviewer-1", roles=frozenset({"reviewer"})),
            __import__("fmea_application.governance_contracts", fromlist=["RevisionResult"]).RevisionResult(
                "revision-1", 1, "audit-1", "outbox-1", replayed=True
            ),
        ),
        (
            "submit",
            "submit_for_approval",
            SubmitApprovalCommand("revision-1", "a" * 64, 1, "00000000-0000-4000-8000-000000000753"),
            make_governance_actor(actor_id="reviewer-1", roles=frozenset({"reviewer"})),
            ApprovalSubmissionResult("submission-1", 1, "audit-1", "outbox-1", replayed=True),
        ),
        (
            "reject",
            "reject",
            ApprovalRejectionCommand(
                "submission-1",
                "revision-1",
                "a" * 64,
                1,
                "rejected",
                "00000000-0000-4000-8000-000000000754",
            ),
            make_governance_actor(actor_id="approver-1", roles=frozenset({"approver"})),
            ApprovalResult("approval-1", 2, "audit-1", "outbox-1", replayed=True),
        ),
        (
            "withdraw_approval",
            "withdraw_approval",
            WithdrawApprovalCommand("approval-1", "a" * 64, 2, "withdrawn", "00000000-0000-4000-8000-000000000755"),
            make_governance_actor(actor_id="approver-1", roles=frozenset({"approver"})),
            ApprovalWithdrawalResult("approval-withdrawal-1", "approval-1", "audit-1", "outbox-1", replayed=True),
        ),
        (
            "withdraw_publication",
            "withdraw_publication",
            WithdrawPublicationCommand("publication-1", 1, "withdrawn", None, "00000000-0000-4000-8000-000000000756"),
            make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"})),
            PublicationWithdrawalResult(
                "publication-withdrawal-1", "publication-1", "audit-1", "outbox-1", replayed=True
            ),
        ),
        (
            "supersede",
            "supersede",
            SupersedePublicationCommand(
                "publication-1",
                "publication-2",
                1,
                1,
                "superseded",
                "00000000-0000-4000-8000-000000000757",
            ),
            make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"})),
            SupersessionResult(
                "supersession-1", "publication-1", "publication-2", "audit-1", "outbox-1", replayed=True
            ),
        ),
    ],
)
def test_each_governance_write_replays_before_mutable_state_guards(
    kind: str,
    method_name: str,
    command: object,
    actor: object,
    result: object,
) -> None:
    service = _early_replay_service(_EarlyReplayRepository(kind, command, result))

    assert getattr(service, method_name)(command, actor) == result


class _MissingRevisionVersionRepository:
    def __init__(self) -> None:
        self.revision = make_fmea_revision()

    def replay_governance_command(self, *_args):
        return None

    def get_revision(self, _revision_id, _workspace_id):
        return self.revision

    def replay_approval_submission(self, *_args):
        return None

    def commit_approval_submission(self, prepared):
        from fmea_application.governance_contracts import ApprovalSubmissionResult

        return ApprovalSubmissionResult(
            prepared.submission.submission_id,
            1,
            prepared.audit.event_id,
            prepared.outbox.event_id,
        )


def test_missing_revision_version_getter_cannot_default_to_version_one() -> None:
    repository = _MissingRevisionVersionRepository()
    service = _early_replay_service(repository)
    actor = make_governance_actor(actor_id="reviewer-1", roles=frozenset({"reviewer"}))
    from fmea_application.governance_contracts import SubmitApprovalCommand

    command = SubmitApprovalCommand(
        repository.revision.revision_id,
        repository.revision.revision_hash,
        1,
        "00000000-0000-4000-8000-000000000751",
    )

    with pytest.raises(ReviewError) as captured:
        service.submit_for_approval(command, actor)
    assert captured.value.code == "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE"


def test_none_submission_read_cannot_fall_back_to_process_local_authority() -> None:
    service, repository, _inputs = _service()
    revision = make_fmea_revision()
    repository.revisions[(revision.workspace_id, revision.revision_id)] = type("Prepared", (), {"revision": revision})()
    actor = make_governance_actor(actor_id="approver-1", roles=frozenset({"approver"}))
    command = __import__("fmea_governance_fixtures", fromlist=["make_approval_command"]).make_approval_command(
        revision_hash=revision.revision_hash
    )

    with pytest.raises(ReviewError) as captured:
        service.approve(command, actor)
    assert captured.value.code == "FMEA_GOVERNANCE_APPROVAL_NOT_FOUND"


@pytest.mark.parametrize("invalid_lifecycle", [object(), "not-a-lifecycle"])
def test_invalid_publication_lifecycle_type_fails_closed(invalid_lifecycle: object) -> None:
    class _InvalidLifecycleRepository:
        def get_publication_lifecycle(self, _publication_id, _workspace_id):
            return invalid_lifecycle

    service = _early_replay_service(_InvalidLifecycleRepository())
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    with pytest.raises(ReviewError) as captured:
        service.get_publication("publication-1", actor)
    assert captured.value.code == "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID"


def test_cross_workspace_publication_lifecycle_fails_closed() -> None:
    publication = __import__("fmea_governance_fixtures", fromlist=["make_published_revision"]).make_published_revision(
        workspace_id="ws-other"
    )

    class _CrossWorkspaceRepository:
        def get_publication_lifecycle(self, _publication_id, _workspace_id):
            return project_publication_lifecycle(publication, withdrawal=None, supersession=None)

    service = _early_replay_service(_CrossWorkspaceRepository())
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    with pytest.raises(ReviewError) as captured:
        service.get_publication(publication.publication_id, actor)
    assert captured.value.code == "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID"


def test_revision_getter_cannot_return_a_different_revision_id() -> None:
    class _WrongRevisionRepository:
        def get_revision(self, _revision_id, _workspace_id):
            return make_fmea_revision(revision_id="revision-other")

        def get_revision_record_version(self, _revision_id, _workspace_id):
            return 1

    service = _early_replay_service(_WrongRevisionRepository())
    actor = make_governance_actor(actor_id="reviewer-1", roles=frozenset({"reviewer"}))

    with pytest.raises(ReviewError) as captured:
        service.get_revision("revision-expected", actor)

    assert captured.value.code == "FMEA_GOVERNANCE_REVISION_NOT_FOUND"


def test_submission_getter_cannot_return_a_different_submission_id() -> None:
    class _WrongSubmissionRepository:
        def get_approval_submission(self, _submission_id, _workspace_id):
            return make_approval_submission(submission_id="submission-other")

    service = _early_replay_service(_WrongSubmissionRepository())

    with pytest.raises(ReviewError) as captured:
        service._submission("submission-expected", "ws-1")

    assert captured.value.code == "FMEA_GOVERNANCE_APPROVAL_NOT_FOUND"


@pytest.mark.parametrize(
    ("helper", "arguments"),
    [
        ("_revision_state", ("revision-1", "ws-1")),
        ("_submission", ("submission-1", "ws-1")),
        ("_approval", ("approval-1", "ws-1")),
        ("_approval_for_submission", ("submission-1", "ws-1")),
        ("_approval_withdrawal", ("approval-1", "ws-1")),
        ("_lifecycle", ("publication-1", "ws-1")),
    ],
)
def test_missing_mandatory_public_getters_fail_closed(helper: str, arguments: tuple[str, str]) -> None:
    service = _early_replay_service(object())

    with pytest.raises(ReviewError) as captured:
        getattr(service, helper)(*arguments)

    assert captured.value.code == "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE"


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
        SubmitApprovalCommand(
            revision.revision_id,
            revision.revision_hash,
            assembled.record_version,
            "00000000-0000-4000-8000-000000000712",
        ),
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
        AssembleRevisionCommand(RevisionAssemblyRequest("analysis-1", None, 1), "00000000-0000-4000-8000-000000000714"),
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
    repository.approvals[("ws-1", "approval-1")] = make_approval_decision(
        approval_id="approval-1",
        submission_id="submission-1",
        revision_id=revision.revision_id,
        revision_hash=revision.revision_hash,
        status=ApprovalStatus.APPROVED,
        reason="ok",
    )

    with pytest.raises(ReviewError) as captured:
        service.publish(
            PublishCommand(revision.revision_id, "b" * 64, "approval-1", 1, "00000000-0000-4000-8000-000000000713"),
            actor,
        )
    assert captured.value.code == "FMEA_GOVERNANCE_APPROVAL_STALE"


def _prepared_publication_with_factory(factory):
    service, repository, inputs = _service()
    service._id_factory = factory
    request = __import__(
        "fmea_application.governance_contracts", fromlist=["RevisionAssemblyRequest"]
    ).RevisionAssemblyRequest("analysis-1", None, 1)
    revision = service._assembler.assemble(request, inputs)
    submission = make_approval_submission(
        revision_id=revision.revision_id,
        revision_hash=revision.revision_hash,
    )
    approval = make_approval_decision(
        revision_id=revision.revision_id,
        revision_hash=revision.revision_hash,
    )
    repository.revisions[(revision.workspace_id, revision.revision_id)] = type("Prepared", (), {"revision": revision})()
    repository.submissions[(revision.workspace_id, submission.submission_id)] = submission
    repository.approvals[(revision.workspace_id, approval.approval_id)] = approval

    from fmea_application.revision_assembler import PublicationReadinessReport

    class _AlwaysReady:
        def evaluate(self, value, _context):
            return PublicationReadinessReport(
                value.revision_id,
                value.workspace_id,
                value.analysis_id,
                value.revision_hash,
                value.analysis_record_version,
                tuple(pack_id for pack_id, _ in value.evidence_pack_hashes),
                True,
                (),
                (),
            )

    service._readiness_policy = _AlwaysReady()
    command = __import__("fmea_governance_fixtures", fromlist=["make_publish_command"]).make_publish_command(
        revision_id=revision.revision_id, revision_hash=revision.revision_hash
    )
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))
    service.publish(command, actor)
    return repository.writes[-1]


def test_publication_aggregate_ids_are_scope_stable_despite_random_factory() -> None:
    first = _prepared_publication_with_factory(lambda prefix: f"random-a-{prefix}")
    second = _prepared_publication_with_factory(lambda prefix: f"random-b-{prefix}")

    assert (
        first.publication.publication_id,
        first.manifest.manifest_id,
        first.snapshot.snapshot_id,
        first.export_eligibility.eligibility_id,
    ) == (
        second.publication.publication_id,
        second.manifest.manifest_id,
        second.snapshot.snapshot_id,
        second.export_eligibility.eligibility_id,
    )


def _supersession_service(*, existing_links: dict[str, str], withdrawals: set[str] | None = None):
    repository = _Repository()
    repository.lifecycle_calls = []
    original_get_lifecycle = repository.get_publication_lifecycle

    def recording_get_lifecycle(publication_id, workspace_id):
        repository.lifecycle_calls.append(publication_id)
        return original_get_lifecycle(publication_id, workspace_id)

    repository.get_publication_lifecycle = recording_get_lifecycle
    old_revision = make_fmea_revision(revision_id="revision-old")
    replacement_revision = make_fmea_revision(
        revision_id="revision-new",
        parent_revision_id=old_revision.revision_id,
        parent_revision_hash=old_revision.revision_hash,
    )
    repository.revisions[("ws-1", old_revision.revision_id)] = type("Prepared", (), {"revision": old_revision})()
    repository.revisions[("ws-1", replacement_revision.revision_id)] = type(
        "Prepared", (), {"revision": replacement_revision}
    )()
    publications = {
        "pub-old": make_published_revision(
            publication_id="pub-old",
            revision_id=old_revision.revision_id,
            revision_hash=old_revision.revision_hash,
        ),
        "pub-new": make_published_revision(
            publication_id="pub-new",
            revision_id=replacement_revision.revision_id,
            revision_hash=replacement_revision.revision_hash,
        ),
    }
    for source, target in existing_links.items():
        publications.setdefault(source, make_published_revision(publication_id=source))
        publications.setdefault(target, make_published_revision(publication_id=target))
        repository.supersessions[("ws-1", source)] = make_supersession_record(
            supersession_id=f"supersession-{source}",
            old_publication_id=source,
            new_publication_id=target,
        )
    for publication_id, publication in publications.items():
        repository.publications[("ws-1", publication_id)] = type("Prepared", (), {"publication": publication})()
    for publication_id in withdrawals or set():
        repository.publication_withdrawals[("ws-1", publication_id)] = PublicationWithdrawalRecord(
            f"withdrawal-{publication_id}",
            publication_id,
            None,
            "publisher-1",
            "withdrawn",
            "2026-08-30T00:00:00Z",
        )
    return _early_replay_service(repository), repository


def _supersede_command() -> SupersedePublicationCommand:
    return SupersedePublicationCommand(
        "pub-old",
        "pub-new",
        1,
        1,
        "replacement",
        "00000000-0000-4000-8000-000000000760",
    )


def test_supersession_traverses_persisted_multihop_lifecycle() -> None:
    service, repository = _supersession_service(existing_links={"pub-new": "pub-next", "pub-next": "pub-final"})
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    result = service.supersede(_supersede_command(), actor)

    assert result.old_publication_id == "pub-old"
    assert repository.lifecycle_calls.count("pub-next") >= 1
    assert repository.lifecycle_calls.count("pub-final") >= 1


def test_supersession_cycle_fails_after_persisted_lifecycle_traversal() -> None:
    service, repository = _supersession_service(existing_links={"pub-new": "pub-old"})
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    with pytest.raises(ReviewError) as captured:
        service.supersede(_supersede_command(), actor)

    assert captured.value.code == "FMEA_GOVERNANCE_SUPERSESSION_INVALID"
    assert repository.lifecycle_calls.count("pub-old") >= 2


def test_supersession_fails_closed_beyond_fixed_maximum_depth() -> None:
    links = {"pub-new": "pub-hop-0"}
    links.update({f"pub-hop-{index}": f"pub-hop-{index + 1}" for index in range(70)})
    service, repository = _supersession_service(existing_links=links)
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    with pytest.raises(ReviewError) as captured:
        service.supersede(_supersede_command(), actor)

    assert captured.value.code == "FMEA_GOVERNANCE_SUPERSESSION_INVALID"
    assert len(repository.lifecycle_calls) >= 64


@pytest.mark.parametrize("withdrawn_id", ["pub-old", "pub-new"])
def test_supersession_rejects_withdrawn_old_or_replacement(withdrawn_id: str) -> None:
    service, _repository = _supersession_service(existing_links={}, withdrawals={withdrawn_id})
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))

    with pytest.raises(ReviewError) as captured:
        service.supersede(_supersede_command(), actor)

    assert captured.value.code == "FMEA_GOVERNANCE_SUPERSESSION_INVALID"
