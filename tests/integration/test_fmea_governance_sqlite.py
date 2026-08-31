from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from fmea_governance_fixtures import (
    _prepared_events,
    make_approval_decision,
    make_approval_submission,
    make_fmea_revision,
    make_governance_actor,
    make_normalized_snapshot,
    make_published_revision,
    make_supersession_record,
    prepared_approval,
    prepared_approval_submission,
    prepared_approval_withdrawal,
    prepared_publication,
    prepared_revision,
    prepared_supersession,
)

from core_domain.fmea.governance import PublicationManifest
from fmea_application.governance_contracts import (
    ApprovalCommand,
    GovernanceHistoryQuery,
    PreparedApproval,
    PreparedApprovalSubmission,
    PreparedApprovalWithdrawal,
    PreparedPublication,
    PreparedSupersession,
    PublishCommand,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    WithdrawApprovalCommand,
    canonical_governance_payload,
    governance_payload_hash,
)
from fmea_application.review_contracts import IdempotencyScope, idempotency_key_hash
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.governance_repository_sqlite import SqliteGovernanceRepository


@pytest.fixture
def repository(tmp_path: Path) -> SqliteGovernanceRepository:
    value = SqliteGovernanceRepository(tmp_path / "fmea.sqlite3")
    value.initialize()
    return value


def _prepared_submission_for(prepared_publication_value) -> PreparedApprovalSubmission:
    base = prepared_approval_submission()
    submission = replace(base.submission, revision_hash=prepared_publication_value.revision.revision_hash)
    command = SubmitApprovalCommand(
        submission.revision_id,
        submission.revision_hash,
        base.revision_record_version,
        base.command.idempotency_key,
    )
    payload = canonical_governance_payload("approval.submit", command, submission=submission)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(base.scope, payload_hash, dict(payload), submission.submission_id)
    return PreparedApprovalSubmission(
        base.scope, payload_hash, command, base.revision_record_version, submission, audit, outbox
    )


def _prepared_approval_for(prepared_publication_value, submission: PreparedApprovalSubmission) -> PreparedApproval:
    base = prepared_approval()
    decision = replace(base.decision, revision_hash=prepared_publication_value.revision.revision_hash)
    command = ApprovalCommand(
        submission.submission.submission_id,
        submission.submission.revision_id,
        submission.submission.revision_hash,
        submission.submission.record_version,
        decision.reason,
        base.command.idempotency_key,
    )
    payload = canonical_governance_payload(
        "approval.decide", command, submission=submission.submission, decision=decision
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(base.scope, payload_hash, dict(payload), decision.approval_id)
    return PreparedApproval(base.scope, payload_hash, command, submission.submission, decision, audit, outbox)


def _prepared_approval_withdrawal_for(prepared_publication_value) -> PreparedApprovalWithdrawal:
    base = prepared_approval_withdrawal()
    approval = replace(base.approval, revision_hash=prepared_publication_value.revision.revision_hash)
    withdrawal = replace(base.withdrawal, revision_hash=prepared_publication_value.revision.revision_hash)
    command = WithdrawApprovalCommand(
        approval.approval_id,
        approval.revision_hash,
        approval.record_version,
        withdrawal.reason,
        base.command.idempotency_key,
    )
    payload = canonical_governance_payload("approval.withdraw", command, approval=approval, withdrawal=withdrawal)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(base.scope, payload_hash, dict(payload), withdrawal.withdrawal_id)
    return PreparedApprovalWithdrawal(base.scope, payload_hash, command, approval, withdrawal, audit, outbox)


def _prepared_publication_withdrawal_for(prepared_publication_value):
    base = __import__(
        "fmea_governance_fixtures", fromlist=["prepared_publication_withdrawal"]
    ).prepared_publication_withdrawal()
    payload = canonical_governance_payload(
        "publication.withdraw",
        base.command,
        publication=prepared_publication_value.publication,
        withdrawal=base.withdrawal,
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(base.scope, payload_hash, dict(payload), base.withdrawal.withdrawal_id)
    return type(base)(
        base.scope, payload_hash, base.command, prepared_publication_value.publication, base.withdrawal, audit, outbox
    )


def _prepared_publication_bundle(revision, publication_id: str, suffix: str, key: str) -> PreparedPublication:
    submission = make_approval_submission(
        submission_id=f"submission-{suffix}", revision_id=revision.revision_id, revision_hash=revision.revision_hash
    )
    approval = make_approval_decision(
        approval_id=f"approval-{suffix}",
        submission_id=submission.submission_id,
        revision_id=revision.revision_id,
        revision_hash=revision.revision_hash,
    )
    snapshot = make_normalized_snapshot(
        revision=revision, publication_id=publication_id, manifest_id=f"manifest-{suffix}"
    )
    manifest = PublicationManifest(
        f"manifest-{suffix}",
        revision.revision_id,
        revision.revision_hash,
        approval.approval_id,
        snapshot.snapshot_id,
        snapshot.snapshot_hash,
        "a" * 64,
        None,
        True,
        "a" * 64,
        "2026-08-30T00:00:00Z",
    )
    publication = make_published_revision(
        publication_id=publication_id,
        revision_id=revision.revision_id,
        revision_hash=revision.revision_hash,
        approval_id=approval.approval_id,
        manifest_id=manifest.manifest_id,
        manifest_hash=manifest.manifest_hash,
        snapshot_id=snapshot.snapshot_id,
        snapshot_hash=snapshot.snapshot_hash,
    )
    command = PublishCommand(
        revision.revision_id,
        revision.revision_hash,
        approval.approval_id,
        1,
        key,
    )
    actor = make_governance_actor(actor_id="publisher-1", roles=frozenset({"publisher"}))
    scope = IdempotencyScope(
        revision.workspace_id,
        actor.actor_id,
        "fmea.publication.publish",
        f"/fmea/revisions/{revision.revision_id}/publications",
        idempotency_key_hash(key),
    )
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
    audit, outbox = _prepared_events(scope, payload_hash, dict(payload), publication.publication_id)
    return PreparedPublication(
        scope,
        payload_hash,
        command,
        1,
        revision,
        approval,
        submission,
        manifest,
        publication,
        snapshot,
        audit,
        outbox,
    )


def test_publication_commits_manifest_snapshot_audit_and_outbox_atomically(
    repository: SqliteGovernanceRepository,
) -> None:
    prepared = prepared_publication()

    result = repository.commit_publication(prepared)

    assert repository.get_revision(prepared.revision.revision_id, prepared.scope.workspace_id) == prepared.revision
    assert (
        repository.get_publication(prepared.publication.publication_id, prepared.scope.workspace_id)
        == prepared.publication
    )
    assert repository.get_snapshot(prepared.snapshot.snapshot_id, prepared.scope.workspace_id) == prepared.snapshot
    assert result.publication_id == prepared.publication.publication_id
    assert result.manifest_id == prepared.manifest.manifest_id
    assert result.snapshot_id == prepared.snapshot.snapshot_id
    assert repository.replay_publication(prepared.scope, prepared.payload_hash) == replace(result, replayed=True)


def test_published_payload_cannot_be_updated_or_deleted(
    repository: SqliteGovernanceRepository,
) -> None:
    result = repository.commit_publication(prepared_publication())

    with (
        pytest.raises(sqlite3.IntegrityError, match="immutable fmea_publications"),
        sqlite3.connect(repository.database_path) as connection,
    ):
        connection.execute(
            "UPDATE fmea_publications SET revision_hash=? WHERE workspace_id=? AND publication_id=?",
            ("f" * 64, "ws-1", result.publication_id),
        )
    with (
        pytest.raises(sqlite3.IntegrityError, match="immutable fmea_publications"),
        sqlite3.connect(repository.database_path) as connection,
    ):
        connection.execute(
            "DELETE FROM fmea_publications WHERE workspace_id=? AND publication_id=?",
            ("ws-1", result.publication_id),
        )


@pytest.mark.parametrize(
    "failure_step",
    (
        "idempotency.reserve",
        "audit",
        "publication.revision",
        "publication.decision",
        "publication.manifest",
        "publication.snapshot",
        "publication.record",
        "outbox",
        "idempotency.complete",
    ),
)
def test_fault_injected_publication_rolls_back_every_shared_write(tmp_path: Path, failure_step: str) -> None:
    path = tmp_path / "fmea.sqlite3"

    def fail(step: str) -> None:
        if step == failure_step:
            raise RuntimeError("injected publication failure")  # noqa: TRY003

    repository = SqliteGovernanceRepository(path, fault_injector=fail)
    repository.initialize()
    with pytest.raises(RuntimeError, match="injected publication failure"):
        repository.commit_publication(prepared_publication())

    count_queries = (
        "SELECT COUNT(*) FROM fmea_revisions",
        "SELECT COUNT(*) FROM fmea_approval_submissions",
        "SELECT COUNT(*) FROM fmea_approval_decisions",
        "SELECT COUNT(*) FROM fmea_publication_manifests",
        "SELECT COUNT(*) FROM fmea_publications",
        "SELECT COUNT(*) FROM fmea_normalized_snapshots",
        "SELECT COUNT(*) FROM fmea_audit_events",
        "SELECT COUNT(*) FROM fmea_outbox_events",
        "SELECT COUNT(*) FROM idempotency_records",
    )
    with sqlite3.connect(path) as connection:
        for query in count_queries:
            assert connection.execute(query).fetchone() == (0,)


def test_tampered_hash_or_noncanonical_json_is_rejected_on_read(
    repository: SqliteGovernanceRepository,
) -> None:
    prepared = prepared_publication()
    repository.commit_publication(prepared)

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_revisions_no_update")
        revision_json = connection.execute(
            "SELECT revision_json FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            ("ws-1", prepared.revision.revision_id),
        ).fetchone()[0]
        connection.execute(
            "UPDATE fmea_revisions SET revision_json=? WHERE workspace_id=? AND revision_id=?",
            (revision_json.replace('"analysis_id":"analysis-1"', '"analysis_id":"analysis-2"'), "ws-1", "revision-1"),
        )

    with pytest.raises(ValueError, match="persisted revision"):
        repository.get_revision("revision-1", "ws-1")


def test_revision_approval_withdrawal_lifecycle_is_atomic_and_replayable(
    repository: SqliteGovernanceRepository,
) -> None:
    publication = prepared_publication()
    submission = _prepared_submission_for(publication)
    approval = _prepared_approval_for(publication, submission)
    withdrawal = _prepared_approval_withdrawal_for(publication)

    revision = prepared_revision()
    repository.commit_revision(revision)
    submission_result = repository.commit_approval_submission(submission)
    approval_result = repository.commit_approval(approval)
    withdrawal_result = repository.commit_approval_withdrawal(withdrawal)

    assert repository.replay_revision(revision.scope, revision.payload_hash).replayed is True
    assert repository.replay_approval_submission(submission.scope, submission.payload_hash) == replace(
        submission_result, replayed=True
    )
    assert repository.replay_approval_decision(approval.scope, approval.payload_hash) == replace(
        approval_result, replayed=True
    )
    assert repository.replay_approval_withdrawal(withdrawal.scope, withdrawal.payload_hash) == replace(
        withdrawal_result, replayed=True
    )
    events = repository.list_approval_events(GovernanceHistoryQuery("ws-1", "revision", "revision-1", 50, None)).events
    assert {event.command for event in events} == {
        "fmea.approval.submit",
        "fmea.approval.decide",
        "fmea.approval.withdraw",
    }


def test_publication_withdrawal_is_append_only_and_workspace_qualified(
    repository: SqliteGovernanceRepository,
) -> None:
    publication = prepared_publication()
    repository.commit_publication(publication)
    withdrawal = _prepared_publication_withdrawal_for(publication)

    result = repository.commit_publication_withdrawal(withdrawal)

    assert repository.get_publication(withdrawal.publication.publication_id, "other-workspace") is None
    assert repository.replay_publication_withdrawal(withdrawal.scope, withdrawal.payload_hash) == replace(
        result, replayed=True
    )
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_publication_withdrawals WHERE workspace_id=? AND withdrawal_id=?",
            ("ws-1", result.withdrawal_id),
        ).fetchone() == (1,)


def test_supersession_preserves_both_publications_and_rejects_a_cycle(
    repository: SqliteGovernanceRepository,
) -> None:
    old_revision = make_fmea_revision()
    replacement_revision = make_fmea_revision(
        revision_id="revision-2",
        parent_revision_id=old_revision.revision_id,
        parent_revision_hash=old_revision.revision_hash,
    )
    old_publication = _prepared_publication_bundle(
        old_revision, "pub-old", "old", "00000000-0000-4000-8000-000000000711"
    )
    replacement_publication = _prepared_publication_bundle(
        replacement_revision, "pub-new", "new", "00000000-0000-4000-8000-000000000712"
    )
    repository.commit_publication(old_publication)
    repository.commit_publication(replacement_publication)
    base = prepared_supersession()
    link = make_supersession_record(
        supersession_id="supersession-1",
        old_publication_id=old_publication.publication.publication_id,
        new_publication_id=replacement_publication.publication.publication_id,
    )
    command = SupersedePublicationCommand(
        old_publication.publication.publication_id,
        replacement_publication.publication.publication_id,
        old_publication.publication.record_version,
        replacement_publication.publication.record_version,
        link.reason,
        "00000000-0000-4000-8000-000000000713",
    )
    scope = IdempotencyScope(
        "ws-1",
        base.scope.actor_id,
        "fmea.publication.supersede",
        f"/fmea/publications/{old_publication.publication.publication_id}/supersession",
        idempotency_key_hash(command.idempotency_key),
    )
    payload = canonical_governance_payload(
        "publication.supersede",
        command,
        old=old_publication.publication,
        replacement=replacement_publication.publication,
        old_revision=old_revision,
        replacement_revision=replacement_revision,
        supersession=link,
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, dict(payload), link.supersession_id)
    prepared = PreparedSupersession(
        scope,
        payload_hash,
        command,
        old_publication.publication,
        replacement_publication.publication,
        old_revision,
        replacement_revision,
        link,
        audit,
        outbox,
    )
    result = repository.commit_supersession(prepared)

    assert repository.get_publication("pub-old", "ws-1") == old_publication.publication
    assert repository.get_publication("pub-new", "ws-1") == replacement_publication.publication
    assert repository.replay_supersession(prepared.scope, prepared.payload_hash) == replace(result, replayed=True)

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            "INSERT INTO fmea_supersessions "
            "(workspace_id,supersession_id,old_publication_id,new_publication_id,actor_id,reason,supersession_json,canonical_json_hash,idempotency_scope,payload_hash,audit_event_id,outbox_event_id,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "ws-1",
                "forged-cycle",
                replacement_publication.publication.publication_id,
                old_publication.publication.publication_id,
                prepared.supersession.actor_id,
                "forged cycle edge",
                '{"actor_id":"publisher-1","created_at":"2026-08-30T00:00:00Z","new_publication_id":"pub-old","old_publication_id":"pub-new","reason":"forged cycle edge","supersession_id":"forged-cycle"}',
                "sha256:" + "f" * 64,
                "forged-cycle-scope",
                "sha256:" + "e" * 64,
                "forged-cycle-audit",
                "forged-cycle-outbox",
                "2026-08-30T00:00:00Z",
            ),
        )

    key = "00000000-0000-4000-8000-000000000799"
    command = SupersedePublicationCommand("pub-old", "pub-new", 1, 1, "cycle close", key)
    scope = IdempotencyScope(
        "ws-1",
        prepared.scope.actor_id,
        "fmea.publication.supersede",
        "/fmea/publications/pub-old/supersession",
        idempotency_key_hash(key),
    )
    link = make_supersession_record(
        supersession_id="cycle-close",
        old_publication_id="pub-old",
        new_publication_id="pub-new",
        reason="cycle close",
    )
    payload = canonical_governance_payload(
        "publication.supersede",
        command,
        old=old_publication.publication,
        replacement=replacement_publication.publication,
        old_revision=old_revision,
        replacement_revision=replacement_revision,
        supersession=link,
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, dict(payload), link.supersession_id)
    cycle = PreparedSupersession(
        scope,
        payload_hash,
        command,
        old_publication.publication,
        replacement_publication.publication,
        old_revision,
        replacement_revision,
        link,
        audit,
        outbox,
    )
    with pytest.raises(ReviewError) as captured:
        repository.commit_supersession(cycle)
    assert captured.value.code == "FMEA_REVIEW_REQUEST_INVALID"


def test_history_is_workspace_scoped_and_survives_restart(
    repository: SqliteGovernanceRepository,
    tmp_path: Path,
) -> None:
    prepared = prepared_publication()
    result = repository.commit_publication(prepared)

    restarted = SqliteGovernanceRepository(tmp_path / "fmea.sqlite3")
    restarted.initialize()
    assert restarted.replay_publication(prepared.scope, prepared.payload_hash) == replace(result, replayed=True)
    page = restarted.list_publication_events(
        GovernanceHistoryQuery("ws-1", "publication", prepared.publication.publication_id, 50, None)
    )

    assert page.events
    assert any(event.event_id == prepared.audit.event_id for event in page.events)
    assert (
        restarted.list_publication_events(
            GovernanceHistoryQuery("other-workspace", "publication", prepared.publication.publication_id, 50, None)
        ).events
        == ()
    )
