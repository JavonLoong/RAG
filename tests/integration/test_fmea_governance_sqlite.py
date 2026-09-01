from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from fmea_governance_fixtures import (
    _export_eligibility,
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
    seed_authoritative_analysis,
)

from core_domain.fmea.codec import encode_json
from core_domain.fmea.governance import PublicationManifest
from fmea_application.governance_contracts import (
    ApprovalCommand,
    ExportEligibilityRecord,
    GovernanceHistoryQuery,
    PersistReadinessCommand,
    PreparedApproval,
    PreparedApprovalSubmission,
    PreparedApprovalWithdrawal,
    PreparedPublication,
    PreparedReadinessReport,
    PreparedSupersession,
    PublishCommand,
    ReadinessReportRecord,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    WithdrawApprovalCommand,
    canonical_governance_payload,
    governance_payload_hash,
)
from fmea_application.review_contracts import IdempotencyScope, idempotency_key_hash
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.governance_repository_sqlite import SqliteGovernanceRepository
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository


@pytest.fixture
def repository(tmp_path: Path) -> SqliteGovernanceRepository:
    value = SqliteGovernanceRepository(tmp_path / "fmea.sqlite3")
    value.initialize()
    seed_authoritative_analysis(value.database_path)
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
    export_eligibility = _export_eligibility(
        publication=publication,
        manifest=manifest,
        revision=revision,
        snapshot=snapshot,
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
        export_eligibility=export_eligibility,
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
        export_eligibility,
    )


def _prepared_publication_reusing_manifest_id() -> PreparedPublication:
    revision = make_fmea_revision(revision_id="revision-collision")
    base = _prepared_publication_bundle(
        revision,
        "publication-collision",
        "collision",
        "00000000-0000-4000-8000-000000000714",
    )
    snapshot = make_normalized_snapshot(
        revision=revision,
        publication_id=base.publication.publication_id,
        manifest_id="manifest-1",
    )
    manifest = PublicationManifest(
        "manifest-1",
        revision.revision_id,
        revision.revision_hash,
        base.approval.approval_id,
        snapshot.snapshot_id,
        snapshot.snapshot_hash,
        "b" * 64,
        None,
        False,
        "b" * 64,
        "2026-08-30T00:00:00Z",
    )
    publication = replace(
        base.publication,
        revision_id=revision.revision_id,
        revision_hash=revision.revision_hash,
        approval_id=base.approval.approval_id,
        manifest_id=manifest.manifest_id,
        manifest_hash=manifest.manifest_hash,
        snapshot_id=snapshot.snapshot_id,
        snapshot_hash=snapshot.snapshot_hash,
    )
    export_eligibility = _export_eligibility(
        publication=publication,
        manifest=manifest,
        revision=revision,
        snapshot=snapshot,
    )
    payload = canonical_governance_payload(
        "publication.publish",
        base.command,
        revision=revision,
        approval=base.approval,
        submission=base.submission,
        manifest=manifest,
        publication=publication,
        snapshot=snapshot,
        export_eligibility=export_eligibility,
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(base.scope, payload_hash, dict(payload), publication.publication_id)
    return PreparedPublication(
        base.scope,
        payload_hash,
        base.command,
        1,
        revision,
        base.approval,
        base.submission,
        manifest,
        publication,
        snapshot,
        audit,
        outbox,
        export_eligibility,
    )


def _prepared_supersession_for_publications(old: PreparedPublication, replacement: PreparedPublication):
    base = prepared_supersession()
    link = make_supersession_record(
        old_publication_id=old.publication.publication_id,
        new_publication_id=replacement.publication.publication_id,
    )
    command = SupersedePublicationCommand(
        old.publication.publication_id,
        replacement.publication.publication_id,
        old.publication.record_version,
        replacement.publication.record_version,
        link.reason,
        base.command.idempotency_key,
    )
    scope = IdempotencyScope(
        old.scope.workspace_id,
        base.scope.actor_id,
        base.scope.command,
        f"/fmea/publications/{old.publication.publication_id}/supersession",
        idempotency_key_hash(command.idempotency_key),
    )
    payload = canonical_governance_payload(
        "publication.supersede",
        command,
        old=old.publication,
        replacement=replacement.publication,
        old_revision=old.revision,
        replacement_revision=replacement.revision,
        supersession=link,
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, dict(payload), link.supersession_id)
    return type(base)(
        scope,
        payload_hash,
        command,
        old.publication,
        replacement.publication,
        old.revision,
        replacement.revision,
        link,
        audit,
        outbox,
    )


def _prepared_readiness() -> PreparedReadinessReport:
    revision = prepared_revision()
    report = __import__(
        "fmea_governance_fixtures", fromlist=["make_blocked_readiness_report"]
    ).make_blocked_readiness_report(
        revision_hash=revision.revision.revision_hash,
    )
    command = PersistReadinessCommand(
        revision.revision.revision_id,
        revision.revision.revision_hash,
        1,
        "readiness-1",
        "00000000-0000-4000-8000-000000000715",
    )
    scope = IdempotencyScope(
        revision.scope.workspace_id,
        revision.scope.actor_id,
        "fmea.revision.readiness",
        f"/fmea/revisions/{revision.revision.revision_id}/readiness",
        idempotency_key_hash(command.idempotency_key),
    )
    source_hashes = (
        ("analysis", revision.revision.analysis_hash),
        ("revision", revision.revision.revision_hash),
    )
    payload = canonical_governance_payload(
        "revision.readiness",
        command,
        report=report,
        source_hashes=source_hashes,
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, dict(payload), command.readiness_id)
    return PreparedReadinessReport(
        scope,
        payload_hash,
        command,
        1,
        command.readiness_id,
        revision.revision,
        report,
        source_hashes,
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


def test_publication_persists_typed_export_eligibility_and_replays_it(
    repository: SqliteGovernanceRepository,
) -> None:
    prepared = prepared_publication()

    result = repository.commit_publication(prepared)

    eligibility = repository.get_export_eligibility(result.publication_id, prepared.scope.workspace_id)
    assert isinstance(eligibility, ExportEligibilityRecord)
    assert eligibility.publication_id == result.publication_id
    assert eligibility.manifest_id == prepared.manifest.manifest_id
    assert eligibility.eligible is prepared.manifest.export_eligible
    assert ("manifest", prepared.manifest.manifest_hash) in eligibility.source_hashes
    assert repository.replay_publication(prepared.scope, prepared.payload_hash) == replace(result, replayed=True)


def test_readiness_report_is_immutable_and_exactly_replayable(
    repository: SqliteGovernanceRepository,
) -> None:
    prepared = _prepared_readiness()

    repository.commit_revision(prepared_revision())
    result = repository.commit_readiness(prepared)

    record = repository.get_readiness(prepared.readiness_id, prepared.scope.workspace_id)
    assert isinstance(record, ReadinessReportRecord)
    assert record.report == prepared.report
    assert record.source_hashes == prepared.source_hashes
    assert repository.replay_readiness(prepared.scope, prepared.payload_hash) == replace(result, replayed=True)
    with (
        pytest.raises(sqlite3.IntegrityError, match="immutable fmea_revision_readiness_reports"),
        sqlite3.connect(repository.database_path) as connection,
    ):
        connection.execute(
            "UPDATE fmea_revision_readiness_reports SET ready=1 WHERE workspace_id=? AND readiness_id=?",
            (prepared.scope.workspace_id, prepared.readiness_id),
        )
    with (
        pytest.raises(sqlite3.IntegrityError, match="immutable fmea_revision_readiness_reports"),
        sqlite3.connect(repository.database_path) as connection,
    ):
        connection.execute(
            "DELETE FROM fmea_revision_readiness_reports WHERE workspace_id=? AND readiness_id=?",
            (prepared.scope.workspace_id, prepared.readiness_id),
        )


def test_publication_rejects_manifest_id_reuse_with_different_lineage(
    repository: SqliteGovernanceRepository,
) -> None:
    first = prepared_publication()
    repository.commit_publication(first)
    collision = _prepared_publication_reusing_manifest_id()

    with pytest.raises((ReviewError, ValueError)):
        repository.commit_publication(collision)

    assert repository.get_publication(collision.publication.publication_id, collision.scope.workspace_id) is None
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_publication_manifests").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM fmea_normalized_snapshots").fetchone() == (1,)


@pytest.mark.parametrize(
    "tamper",
    (
        "authority_audit",
        "authority_outbox",
        "audit_scope",
        "audit_hash",
        "audit_payload",
        "outbox_scope",
        "outbox_hash",
        "outbox_payload",
        "eligibility",
        "response_publication",
        "response_manifest",
        "response_snapshot",
        "response_version",
        "lineage_binding",
    ),
)
def test_publication_replay_rejects_tampered_authority_chain_and_response(  # noqa: C901
    repository: SqliteGovernanceRepository,
    tamper: str,
) -> None:
    prepared = prepared_publication()
    result = repository.commit_publication(prepared)

    with sqlite3.connect(repository.database_path) as connection:
        if tamper in {"authority_audit", "authority_outbox"}:
            connection.execute("DROP TRIGGER fmea_publications_no_update")
            column = "audit_event_id" if tamper == "authority_audit" else "outbox_event_id"
            connection.execute(
                f"UPDATE fmea_publications SET {column}=? WHERE workspace_id=? AND publication_id=?",  # noqa: S608
                (f"tampered-{column}", prepared.scope.workspace_id, result.publication_id),
            )
        elif tamper == "audit_scope":
            connection.execute("DROP TRIGGER fmea_audit_events_no_update")
            connection.execute(
                "UPDATE fmea_audit_events SET idempotency_scope=? WHERE workspace_id=? AND event_id=?",
                ("tampered-audit-scope", prepared.scope.workspace_id, result.audit_event_id),
            )
        elif tamper == "audit_hash":
            connection.execute("DROP TRIGGER fmea_audit_events_no_update")
            connection.execute(
                "UPDATE fmea_audit_events SET canonical_payload_hash=? WHERE workspace_id=? AND event_id=?",
                ("sha256:" + "b" * 64, prepared.scope.workspace_id, result.audit_event_id),
            )
        elif tamper == "audit_payload":
            connection.execute("DROP TRIGGER fmea_audit_events_no_update")
            event_json = connection.execute(
                "SELECT event_json FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
                (prepared.scope.workspace_id, result.audit_event_id),
            ).fetchone()[0]
            event = json.loads(event_json)
            event["canonical_payload_hash"] = "sha256:" + "c" * 64
            connection.execute(
                "UPDATE fmea_audit_events SET event_json=? WHERE workspace_id=? AND event_id=?",
                (
                    json.dumps(event, sort_keys=True, separators=(",", ":")),
                    prepared.scope.workspace_id,
                    result.audit_event_id,
                ),
            )
        elif tamper in {"outbox_scope", "outbox_hash", "outbox_payload"}:
            connection.execute("DROP TRIGGER fmea_outbox_events_no_update")
            column = {
                "outbox_scope": "idempotency_scope",
                "outbox_hash": "payload_hash",
                "outbox_payload": "payload_json",
            }[tamper]
            value = "tampered-outbox-scope" if tamper == "outbox_scope" else "sha256:" + "d" * 64
            if tamper == "outbox_payload":
                value = (
                    connection.execute(  # noqa: S608
                        "SELECT payload_json FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
                        (prepared.scope.workspace_id, result.outbox_event_id),
                    ).fetchone()[0]
                    + " "
                )
            connection.execute(
                f"UPDATE fmea_outbox_events SET {column}=? WHERE workspace_id=? AND event_id=?",  # noqa: S608
                (value, prepared.scope.workspace_id, result.outbox_event_id),
            )
        elif tamper == "eligibility":
            connection.execute("DROP TRIGGER fmea_export_eligibility_no_update")
            connection.execute(
                "UPDATE fmea_export_eligibility SET eligible=0 WHERE workspace_id=? AND publication_id=?",
                (prepared.scope.workspace_id, result.publication_id),
            )
        elif tamper == "lineage_binding":
            connection.execute("DROP TRIGGER fmea_publication_lineage_bindings_no_delete")
            connection.execute(
                "DELETE FROM fmea_publication_lineage_bindings WHERE workspace_id=? AND publication_id=?",
                (prepared.scope.workspace_id, result.publication_id),
            )
        else:
            response_json = connection.execute(
                "SELECT response_json FROM idempotency_records WHERE scope_key=?", (prepared.scope.scope_key,)
            ).fetchone()[0]
            response = json.loads(response_json)
            if tamper == "response_publication":
                response["publication_id"] = "publication-tampered"
            elif tamper == "response_manifest":
                response["manifest_id"] = "manifest-tampered"
            elif tamper == "response_snapshot":
                response["snapshot_id"] = "snapshot-tampered"
            else:
                response["record_version"] = 99
            connection.execute(
                "UPDATE idempotency_records SET response_json=? WHERE scope_key=?",
                (json.dumps(response, sort_keys=True, separators=(",", ":")), prepared.scope.scope_key),
            )

    restarted = SqliteGovernanceRepository(repository.database_path)
    restarted.initialize()
    with pytest.raises((ReviewError, ValueError)):
        restarted.replay_publication(prepared.scope, prepared.payload_hash)


@pytest.mark.parametrize("mutation", ("hash", "version", "workspace"))
def test_commit_revision_rejects_stale_or_cross_workspace_analysis_state(
    repository: SqliteGovernanceRepository,
    mutation: str,
) -> None:
    from fmea_governance_fixtures import _governance_analysis

    prepared = prepared_revision()
    with sqlite3.connect(repository.database_path) as connection:
        if mutation == "hash":
            connection.execute(
                "UPDATE fmea_analyses SET analysis_hash=? WHERE analysis_id=?",
                ("b" * 64, "analysis-1"),
            )
        elif mutation == "version":
            analysis = _governance_analysis()
            stale_analysis = replace(analysis, record_version=2)
            stale_json = encode_json(stale_analysis)
            connection.execute(
                "UPDATE fmea_analyses SET analysis_hash=?, analysis_json=? WHERE analysis_id=?",
                ("sha256:" + sha256(stale_json.encode("utf-8")).hexdigest(), stale_json, "analysis-1"),
            )
        else:
            connection.execute(
                "UPDATE fmea_analyses SET workspace_id=? WHERE analysis_id=?",
                ("other-workspace", "analysis-1"),
            )

    with pytest.raises((ReviewError, ValueError)):
        repository.commit_revision(prepared)


def _governance_counts(path: Path) -> dict[str, int]:
    tables = (
        "fmea_revisions",
        "fmea_revision_readiness_reports",
        "fmea_approval_submissions",
        "fmea_approval_decisions",
        "fmea_approval_withdrawals",
        "fmea_publication_manifests",
        "fmea_normalized_snapshots",
        "fmea_publications",
        "fmea_publication_withdrawals",
        "fmea_supersessions",
        "fmea_export_eligibility",
        "fmea_revision_analysis_bindings",
        "fmea_publication_lineage_bindings",
        "fmea_audit_events",
        "fmea_outbox_events",
        "fmea_governance_event_bindings",
        "idempotency_records",
    )
    with sqlite3.connect(path) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in tables
        }


def test_revision_fault_rolls_back_shared_chain(tmp_path: Path) -> None:
    path = tmp_path / "fmea.sqlite3"
    repository = SqliteGovernanceRepository(path, fault_injector=lambda step: _raise_at(step, "revision.record"))
    repository.initialize()
    seed_authoritative_analysis(path)

    with pytest.raises(RuntimeError, match="injected revision.record failure"):
        repository.commit_revision(prepared_revision())

    assert all(value == 0 for value in _governance_counts(path).values())


def _raise_at(step: str, expected: str) -> None:
    if step == expected:
        raise RuntimeError(f"injected {expected} failure")  # noqa: TRY003


def test_approval_submission_fault_preserves_prior_revision_and_rolls_back_chain(tmp_path: Path) -> None:
    path = tmp_path / "fmea.sqlite3"
    base = SqliteGovernanceRepository(path)
    base.initialize()
    seed_authoritative_analysis(path)
    base.commit_revision(prepared_revision())
    publication = prepared_publication()
    submission = _prepared_submission_for(publication)
    repository = SqliteGovernanceRepository(path, fault_injector=lambda step: _raise_at(step, "approval.submission"))

    with pytest.raises(RuntimeError, match="injected approval.submission failure"):
        repository.commit_approval_submission(submission)

    counts = _governance_counts(path)
    assert counts["fmea_revisions"] == 1
    assert counts["fmea_approval_submissions"] == 0
    assert counts["fmea_audit_events"] == 1
    assert counts["fmea_outbox_events"] == 1
    assert counts["idempotency_records"] == 1


def test_approval_decision_fault_preserves_prior_state_and_rolls_back_chain(tmp_path: Path) -> None:
    path = tmp_path / "fmea.sqlite3"
    base = SqliteGovernanceRepository(path)
    base.initialize()
    seed_authoritative_analysis(path)
    base.commit_revision(prepared_revision())
    publication = prepared_publication()
    submission = _prepared_submission_for(publication)
    base.commit_approval_submission(submission)
    repository = SqliteGovernanceRepository(path, fault_injector=lambda step: _raise_at(step, "approval.decision"))

    with pytest.raises(RuntimeError, match="injected approval.decision failure"):
        repository.commit_approval(_prepared_approval_for(publication, submission))

    counts = _governance_counts(path)
    assert counts["fmea_approval_submissions"] == 1
    assert counts["fmea_approval_decisions"] == 0
    assert counts["fmea_audit_events"] == 2
    assert counts["fmea_outbox_events"] == 2
    assert counts["idempotency_records"] == 2


def test_approval_withdrawal_fault_preserves_prior_state_and_rolls_back_chain(tmp_path: Path) -> None:
    path = tmp_path / "fmea.sqlite3"
    base = SqliteGovernanceRepository(path)
    base.initialize()
    seed_authoritative_analysis(path)
    publication = prepared_publication()
    base.commit_publication(publication)
    repository = SqliteGovernanceRepository(path, fault_injector=lambda step: _raise_at(step, "approval.withdrawal"))

    with pytest.raises(RuntimeError, match="injected approval.withdrawal failure"):
        repository.commit_approval_withdrawal(_prepared_approval_withdrawal_for(publication))

    counts = _governance_counts(path)
    assert counts["fmea_approval_decisions"] == 1
    assert counts["fmea_approval_withdrawals"] == 0
    assert counts["fmea_audit_events"] == 4
    assert counts["fmea_outbox_events"] == 4
    assert counts["idempotency_records"] == 4


def test_publication_withdrawal_fault_preserves_publication_and_rolls_back_chain(tmp_path: Path) -> None:
    path = tmp_path / "fmea.sqlite3"
    base = SqliteGovernanceRepository(path)
    base.initialize()
    seed_authoritative_analysis(path)
    publication = prepared_publication()
    base.commit_publication(publication)
    repository = SqliteGovernanceRepository(path, fault_injector=lambda step: _raise_at(step, "publication.withdrawal"))

    with pytest.raises(RuntimeError, match="injected publication.withdrawal failure"):
        repository.commit_publication_withdrawal(_prepared_publication_withdrawal_for(publication))

    counts = _governance_counts(path)
    assert counts["fmea_publications"] == 1
    assert counts["fmea_publication_withdrawals"] == 0
    assert counts["fmea_audit_events"] == 4
    assert counts["fmea_outbox_events"] == 4
    assert counts["idempotency_records"] == 4


def test_supersession_fault_preserves_both_publications_and_rolls_back_chain(tmp_path: Path) -> None:
    path = tmp_path / "fmea.sqlite3"
    base = SqliteGovernanceRepository(path)
    base.initialize()
    seed_authoritative_analysis(path)
    old_revision = make_fmea_revision()
    replacement_revision = make_fmea_revision(
        revision_id="revision-2",
        parent_revision_id=old_revision.revision_id,
        parent_revision_hash=old_revision.revision_hash,
    )
    old = _prepared_publication_bundle(old_revision, "pub-old", "old", "00000000-0000-4000-8000-000000000711")
    replacement = _prepared_publication_bundle(
        replacement_revision, "pub-new", "new", "00000000-0000-4000-8000-000000000712"
    )
    base.commit_publication(old)
    base.commit_publication(replacement)
    repository = SqliteGovernanceRepository(path, fault_injector=lambda step: _raise_at(step, "supersession.record"))

    with pytest.raises(RuntimeError, match="injected supersession.record failure"):
        repository.commit_supersession(_prepared_supersession_for_publications(old, replacement))

    counts = _governance_counts(path)
    assert counts["fmea_publications"] == 2
    assert counts["fmea_supersessions"] == 0
    assert counts["fmea_audit_events"] == 2 * 4
    assert counts["fmea_outbox_events"] == 2 * 4
    assert counts["idempotency_records"] == 2 * 4


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
    seed_authoritative_analysis(path)
    with pytest.raises(RuntimeError, match="injected publication failure"):
        repository.commit_publication(prepared_publication())

    count_queries = (
        "SELECT COUNT(*) FROM fmea_revisions",
        "SELECT COUNT(*) FROM fmea_approval_submissions",
        "SELECT COUNT(*) FROM fmea_approval_decisions",
        "SELECT COUNT(*) FROM fmea_publication_manifests",
        "SELECT COUNT(*) FROM fmea_publications",
        "SELECT COUNT(*) FROM fmea_normalized_snapshots",
        "SELECT COUNT(*) FROM fmea_revision_analysis_bindings",
        "SELECT COUNT(*) FROM fmea_publication_lineage_bindings",
        "SELECT COUNT(*) FROM fmea_audit_events",
        "SELECT COUNT(*) FROM fmea_outbox_events",
        "SELECT COUNT(*) FROM fmea_governance_event_bindings",
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


def test_migration_007_enforces_workspace_qualified_publication_and_revision_lineage(
    repository: SqliteGovernanceRepository,
) -> None:
    first = prepared_publication()
    repository.commit_publication(first)
    second_revision = make_fmea_revision(revision_id="revision-2")
    second = _prepared_publication_bundle(second_revision, "pub-2", "second", "00000000-0000-4000-8000-000000000720")
    repository.commit_publication(second)

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        assert connection.execute("SELECT COUNT(*) FROM fmea_publication_lineage_bindings").fetchone() == (2,)
        assert connection.execute("SELECT COUNT(*) FROM fmea_revision_analysis_bindings").fetchone() == (2,)
        first_lineage = connection.execute(
            "SELECT publication_id,manifest_id,snapshot_id,revision_id,analysis_id,revision_hash,manifest_hash,snapshot_hash "
            "FROM fmea_publication_lineage_bindings WHERE workspace_id=? AND publication_id=?",
            ("ws-1", first.publication.publication_id),
        ).fetchone()
        second_lineage = connection.execute(
            "SELECT publication_id,manifest_id,snapshot_id,revision_id,analysis_id,revision_hash,manifest_hash,snapshot_hash "
            "FROM fmea_publication_lineage_bindings WHERE workspace_id=? AND publication_id=?",
            ("ws-1", second.publication.publication_id),
        ).fetchone()
        assert first_lineage is not None and second_lineage is not None

        connection.execute("DROP TRIGGER fmea_publication_lineage_bindings_no_delete")
        connection.execute(
            "DELETE FROM fmea_publication_lineage_bindings WHERE workspace_id=? AND publication_id=?",
            ("ws-1", first.publication.publication_id),
        )
        with pytest.raises(sqlite3.IntegrityError, match="lineage"):
            connection.execute(
                "INSERT INTO fmea_publication_lineage_bindings "
                "(workspace_id,publication_id,manifest_id,snapshot_id,revision_id,analysis_id,revision_hash,manifest_hash,snapshot_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("ws-1", first.publication.publication_id, *second_lineage[1:]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO fmea_publication_lineage_bindings "
                "(workspace_id,publication_id,manifest_id,snapshot_id,revision_id,analysis_id,revision_hash,manifest_hash,snapshot_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("ws-1", *second_lineage),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO fmea_publication_lineage_bindings "
                "(workspace_id,publication_id,manifest_id,snapshot_id,revision_id,analysis_id,revision_hash,manifest_hash,snapshot_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("other-workspace", *first_lineage),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO fmea_publication_lineage_bindings "
                "(workspace_id,publication_id,manifest_id,snapshot_id,revision_id,analysis_id,revision_hash,manifest_hash,snapshot_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("ws-1", "orphan", *first_lineage[1:]),
            )

        revision_lineage = connection.execute(
            "SELECT workspace_id,revision_id,analysis_id,analysis_record_version,analysis_hash "
            "FROM fmea_revision_analysis_bindings WHERE workspace_id=? AND revision_id=?",
            ("ws-1", first.revision.revision_id),
        ).fetchone()
        assert revision_lineage is not None
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO fmea_revision_analysis_bindings "
                "(workspace_id,revision_id,analysis_id,analysis_record_version,analysis_hash) VALUES (?,?,?,?,?)",
                ("other-workspace", *revision_lineage[1:]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO fmea_revision_analysis_bindings "
                "(workspace_id,revision_id,analysis_id,analysis_record_version,analysis_hash) VALUES (?,?,?,?,?)",
                ("ws-1", first.revision.revision_id, "missing-analysis", 1, first.revision.analysis_hash),
            )


def test_migration_007_rejects_ambiguous_legacy_analysis_workspaces(tmp_path: Path) -> None:
    path = tmp_path / "ambiguous.sqlite3"
    base = SqliteFmeaRepository(path)
    connection = base._connect()
    try:
        connection.execute("BEGIN EXCLUSIVE")
        for version, migration_path in base._migration_files():
            if version > 6:
                break
            for statement in base._iter_migration_statements(migration_path.read_text(encoding="utf-8")):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version,filename,migration_hash,applied_at) VALUES (?,?,?,?)",
                (
                    version,
                    migration_path.name,
                    "sha256:" + sha256(migration_path.read_bytes()).hexdigest(),
                    "2026-08-30T00:00:00Z",
                ),
            )
        connection.execute("COMMIT")
    finally:
        connection.close()
    seed_authoritative_analysis(path)
    with sqlite3.connect(path) as connection:
        connection.executemany(
            "INSERT INTO evidence_packs(pack_id,workspace_id,pack_hash,pack_json,created_at) VALUES (?,?,?,?,?)",
            (
                ("pack-ws-1", "ws-1", "hash-ws-1", "{}", "2026-08-30T00:00:00Z"),
                ("pack-ws-2", "ws-2", "hash-ws-2", "{}", "2026-08-30T00:00:00Z"),
            ),
        )
        connection.executemany(
            "INSERT INTO fmea_rows "
            "(row_id,workspace_id,analysis_id,evidence_pack_id,review_status,publication_status,record_version,row_hash,row_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    "row-ws-1",
                    "ws-1",
                    "analysis-1",
                    "pack-ws-1",
                    "draft",
                    "unpublished",
                    1,
                    "row-hash-1",
                    "{}",
                    "2026-08-30T00:00:00Z",
                    "2026-08-30T00:00:00Z",
                ),
                (
                    "row-ws-2",
                    "ws-2",
                    "analysis-1",
                    "pack-ws-2",
                    "draft",
                    "unpublished",
                    1,
                    "row-hash-2",
                    "{}",
                    "2026-08-30T00:00:00Z",
                    "2026-08-30T00:00:00Z",
                ),
            ),
        )

    with pytest.raises((sqlite3.IntegrityError, ValueError), match="ambiguous|workspace"):
        SqliteGovernanceRepository(path).initialize()

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone() == (6,)
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fmea_publication_lineage_bindings'"
            ).fetchone()
            is None
        )
        assert connection.execute("SELECT COUNT(*) FROM fmea_rows").fetchone() == (2,)


def test_publication_dependency_revision_has_its_own_authority_chain_and_replay_requires_it(
    repository: SqliteGovernanceRepository,
) -> None:
    prepared = prepared_publication()
    result = repository.commit_publication(prepared)

    with sqlite3.connect(repository.database_path) as connection:
        revision = connection.execute(
            "SELECT audit_event_id,outbox_event_id FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            (prepared.scope.workspace_id, prepared.revision.revision_id),
        ).fetchone()
        publication = connection.execute(
            "SELECT audit_event_id,outbox_event_id FROM fmea_publications WHERE workspace_id=? AND publication_id=?",
            (prepared.scope.workspace_id, result.publication_id),
        ).fetchone()
        assert revision is not None and publication is not None
        assert all(revision)
        assert all(publication)
        assert tuple(revision) != tuple(publication)
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_governance_event_bindings WHERE workspace_id=? AND resource_type='revision' AND resource_id=?",
            (prepared.scope.workspace_id, prepared.revision.revision_id),
        ).fetchone() == (1,)

        connection.execute("DROP TRIGGER fmea_revisions_no_update")
        connection.execute(
            "UPDATE fmea_revisions SET audit_event_id=? WHERE workspace_id=? AND revision_id=?",
            ("tampered-revision-audit", prepared.scope.workspace_id, prepared.revision.revision_id),
        )

    restarted = SqliteGovernanceRepository(repository.database_path)
    restarted.initialize()
    with pytest.raises((ReviewError, ValueError)):
        restarted.replay_publication(prepared.scope, prepared.payload_hash)


def test_readiness_fault_at_actual_write_cut_point_rolls_back_every_readiness_dependency(tmp_path: Path) -> None:
    path = tmp_path / "readiness-fault.sqlite3"
    base = SqliteGovernanceRepository(path)
    base.initialize()
    seed_authoritative_analysis(path)
    base.commit_revision(prepared_revision())
    repository = SqliteGovernanceRepository(path, fault_injector=lambda step: _raise_at(step, "revision.readiness"))

    with pytest.raises(RuntimeError, match="injected revision.readiness failure"):
        repository.commit_readiness(_prepared_readiness())

    counts = _governance_counts(path)
    assert counts["fmea_revisions"] == 1
    assert counts["fmea_revision_readiness_reports"] == 0
    assert counts["fmea_audit_events"] == 1
    assert counts["fmea_outbox_events"] == 1
    assert counts["fmea_governance_event_bindings"] == 1
    assert counts["idempotency_records"] == 1


def _commit_replay_case(repository: SqliteGovernanceRepository, kind: str):
    if kind == "revision":
        prepared = prepared_revision()
        return prepared, repository.commit_revision(prepared)
    if kind == "readiness":
        revision = prepared_revision()
        repository.commit_revision(revision)
        prepared = _prepared_readiness()
        return prepared, repository.commit_readiness(prepared)
    publication = prepared_publication()
    if kind == "approval_submission":
        revision = prepared_revision()
        repository.commit_revision(revision)
        prepared = _prepared_submission_for(publication)
        return prepared, repository.commit_approval_submission(prepared)
    if kind == "approval":
        revision = prepared_revision()
        repository.commit_revision(revision)
        submission = _prepared_submission_for(publication)
        repository.commit_approval_submission(submission)
        prepared = _prepared_approval_for(publication, submission)
        return prepared, repository.commit_approval(prepared)
    if kind == "approval_withdrawal":
        repository.commit_publication(publication)
        prepared = _prepared_approval_withdrawal_for(publication)
        return prepared, repository.commit_approval_withdrawal(prepared)
    if kind == "publication_withdrawal":
        repository.commit_publication(publication)
        prepared = _prepared_publication_withdrawal_for(publication)
        return prepared, repository.commit_publication_withdrawal(prepared)
    old = _prepared_publication_bundle(make_fmea_revision(), "pub-old", "old", "00000000-0000-4000-8000-000000000721")
    replacement_revision = make_fmea_revision(
        revision_id="revision-2",
        parent_revision_id=old.revision.revision_id,
        parent_revision_hash=old.revision.revision_hash,
    )
    replacement = _prepared_publication_bundle(
        replacement_revision, "pub-new", "new", "00000000-0000-4000-8000-000000000722"
    )
    repository.commit_publication(old)
    repository.commit_publication(replacement)
    prepared = _prepared_supersession_for_publications(old, replacement)
    return prepared, repository.commit_supersession(prepared)


def _replay_case(repository: SqliteGovernanceRepository, kind: str, prepared):
    if kind == "revision":
        return repository.replay_revision(prepared.scope, prepared.payload_hash)
    if kind == "readiness":
        return repository.replay_readiness(prepared.scope, prepared.payload_hash)
    if kind == "approval_submission":
        return repository.replay_approval_submission(prepared.scope, prepared.payload_hash)
    if kind == "approval":
        return repository.replay_approval_decision(prepared.scope, prepared.payload_hash)
    if kind == "approval_withdrawal":
        return repository.replay_approval_withdrawal(prepared.scope, prepared.payload_hash)
    if kind == "publication_withdrawal":
        return repository.replay_publication_withdrawal(prepared.scope, prepared.payload_hash)
    return repository.replay_supersession(prepared.scope, prepared.payload_hash)


@pytest.mark.parametrize(
    "kind,field,value",
    (
        ("revision", "record_version", 99),
        ("readiness", "readiness_id", "tampered-readiness"),
        ("approval_submission", "record_version", 99),
        ("approval", "record_version", 99),
        ("approval_withdrawal", "approval_id", "tampered-approval"),
        ("publication_withdrawal", "publication_id", "tampered-publication"),
        ("supersession", "new_publication_id", "tampered-publication"),
    ),
)
def test_replay_rejects_tampered_result_record_and_dependency_ids(
    repository: SqliteGovernanceRepository, kind: str, field: str, value: object
) -> None:
    prepared, _ = _commit_replay_case(repository, kind)
    with sqlite3.connect(repository.database_path) as connection:
        response = json.loads(
            connection.execute(
                "SELECT response_json FROM idempotency_records WHERE scope_key=?", (prepared.scope.scope_key,)
            ).fetchone()[0]
        )
        response[field] = value
        connection.execute(
            "UPDATE idempotency_records SET response_json=? WHERE scope_key=?",
            (json.dumps(response, sort_keys=True, separators=(",", ":")), prepared.scope.scope_key),
        )

    restarted = SqliteGovernanceRepository(repository.database_path)
    restarted.initialize()
    with pytest.raises((ReviewError, ValueError)):
        _replay_case(restarted, kind, prepared)


@pytest.mark.parametrize(
    "kind,tamper",
    (
        ("readiness", "authority_scope"),
        ("approval_submission", "authority_payload"),
        ("approval", "authority_audit"),
        ("approval_withdrawal", "authority_outbox"),
        ("publication_withdrawal", "audit_hash"),
        ("supersession", "outbox_scope"),
        ("readiness", "outbox_type"),
        ("approval_submission", "outbox_hash"),
        ("approval", "outbox_payload"),
        ("approval_withdrawal", "event_binding"),
        ("publication_withdrawal", "audit_payload"),
    ),
)
def test_nonpublication_replay_rejects_tampered_exact_authority_chain(
    repository: SqliteGovernanceRepository, kind: str, tamper: str
) -> None:
    prepared, result = _commit_replay_case(repository, kind)
    table, identifier = {
        "readiness": ("fmea_revision_readiness_reports", "readiness_id"),
        "approval_submission": ("fmea_approval_submissions", "submission_id"),
        "approval": ("fmea_approval_decisions", "approval_id"),
        "approval_withdrawal": ("fmea_approval_withdrawals", "withdrawal_id"),
        "publication_withdrawal": ("fmea_publication_withdrawals", "withdrawal_id"),
        "supersession": ("fmea_supersessions", "supersession_id"),
    }[kind]
    resource_id = getattr(result, identifier)
    with sqlite3.connect(repository.database_path) as connection:
        if tamper.startswith("authority_"):
            connection.execute(f"DROP TRIGGER {table}_no_update")
            column = {
                "authority_scope": "idempotency_scope",
                "authority_payload": "payload_hash",
                "authority_audit": "audit_event_id",
                "authority_outbox": "outbox_event_id",
            }[tamper]
            value = "sha256:" + "e" * 64 if column == "payload_hash" else f"tampered-{column}"
            connection.execute(
                f"UPDATE {table} SET {column}=? WHERE workspace_id=? AND {identifier}=?",  # noqa: S608
                (value, prepared.scope.workspace_id, resource_id),
            )
        elif tamper.startswith("audit_"):
            connection.execute("DROP TRIGGER fmea_audit_events_no_update")
            if tamper == "audit_hash":
                connection.execute(
                    "UPDATE fmea_audit_events SET canonical_payload_hash=? WHERE workspace_id=? AND event_id=?",
                    ("sha256:" + "e" * 64, prepared.scope.workspace_id, result.audit_event_id),
                )
            else:
                event_json = connection.execute(
                    "SELECT event_json FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
                    (prepared.scope.workspace_id, result.audit_event_id),
                ).fetchone()[0]
                connection.execute(
                    "UPDATE fmea_audit_events SET event_json=? WHERE workspace_id=? AND event_id=?",
                    (event_json + " ", prepared.scope.workspace_id, result.audit_event_id),
                )
        elif tamper == "event_binding":
            connection.execute("DROP TRIGGER fmea_governance_event_bindings_no_update")
            connection.execute(
                "UPDATE fmea_governance_event_bindings SET audit_event_id=? "
                "WHERE workspace_id=? AND resource_type=? AND resource_id=?",
                ("tampered-binding-audit", prepared.scope.workspace_id, kind, resource_id),
            )
        else:
            connection.execute("DROP TRIGGER fmea_outbox_events_no_update")
            column = {
                "outbox_scope": "idempotency_scope",
                "outbox_type": "event_type",
                "outbox_hash": "payload_hash",
                "outbox_payload": "payload_json",
            }[tamper]
            value = {
                "outbox_scope": "tampered-outbox-scope",
                "outbox_type": "tampered.event",
                "outbox_hash": "sha256:" + "e" * 64,
                "outbox_payload": "{}",
            }[tamper]
            connection.execute(
                f"UPDATE fmea_outbox_events SET {column}=? WHERE workspace_id=? AND event_id=?",  # noqa: S608
                (value, prepared.scope.workspace_id, result.outbox_event_id),
            )

    restarted = SqliteGovernanceRepository(repository.database_path)
    restarted.initialize()
    with pytest.raises((ReviewError, ValueError)):
        _replay_case(restarted, kind, prepared)


@pytest.mark.parametrize("dependency", ("revision", "submission", "approval"))
def test_publication_replay_recursively_rejects_tampered_dependency_chain(
    repository: SqliteGovernanceRepository, dependency: str
) -> None:
    prepared = prepared_publication()
    repository.commit_publication(prepared)
    table = {
        "revision": "fmea_revisions",
        "submission": "fmea_approval_submissions",
        "approval": "fmea_approval_decisions",
    }[dependency]
    identifier = {
        "revision": "revision_id",
        "submission": "submission_id",
        "approval": "approval_id",
    }[dependency]
    resource_id = {
        "revision": prepared.revision.revision_id,
        "submission": prepared.submission.submission_id,
        "approval": prepared.approval.approval_id,
    }[dependency]
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(f"DROP TRIGGER {table}_no_update")
        connection.execute(
            f"UPDATE {table} SET audit_event_id=? WHERE workspace_id=? AND {identifier}=?",  # noqa: S608
            ("tampered-dependency-audit", prepared.scope.workspace_id, resource_id),
        )

    restarted = SqliteGovernanceRepository(repository.database_path)
    restarted.initialize()
    with pytest.raises((ReviewError, ValueError)):
        restarted.replay_publication(prepared.scope, prepared.payload_hash)
