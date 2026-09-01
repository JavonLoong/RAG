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
    prepared_publication_withdrawal,
    prepared_revision,
    prepared_supersession,
    seed_authoritative_analysis,
)

from core_domain.fmea.codec import encode_json
from core_domain.fmea.governance import (
    ApprovalStatus,
    PublicationManifest,
    RevisionPublicationStatus,
    canonical_hash,
)
from fmea_application.governance_contracts import (
    ApprovalCommand,
    ApprovalRejectionCommand,
    ApprovalResult,
    ExportEligibilityRecord,
    GovernanceHistoryQuery,
    PersistReadinessCommand,
    PreparedApproval,
    PreparedApprovalSubmission,
    PreparedApprovalWithdrawal,
    PreparedPublication,
    PreparedPublicationWithdrawal,
    PreparedReadinessReport,
    PreparedSupersession,
    PublishCommand,
    ReadinessReportRecord,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    WithdrawApprovalCommand,
    WithdrawPublicationCommand,
    canonical_governance_payload,
    governance_payload_hash,
)
from fmea_application.review_contracts import IdempotencyScope, encode_review_json, idempotency_key_hash
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.governance_repository_sqlite import SqliteGovernanceRepository
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository

DEPENDENCY_KINDS = ("revision", "approval_submission", "approval")
STARTING_VERSIONS = (7, 8)


@pytest.fixture
def repository(tmp_path: Path) -> SqliteGovernanceRepository:
    value = SqliteGovernanceRepository(tmp_path / "fmea.sqlite3")
    value.initialize()
    seed_authoritative_analysis(value.database_path)
    return value


def _initialize_through(database_path: Path, maximum_version: int) -> None:
    base = SqliteFmeaRepository(database_path)
    connection = base._connect()
    try:
        connection.execute("BEGIN EXCLUSIVE")
        for version, migration_path in base._migration_files():
            if version > maximum_version:
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


def _prepared_publication_bundle(
    revision,
    publication_id: str,
    suffix: str,
    key: str,
    *,
    previous_audit_chain_head: str | None = None,
) -> PreparedPublication:
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
    version_manifest_hash = canonical_hash(
        {
            "revision_hash": revision.revision_hash,
            "analysis_hash": revision.analysis_hash,
            "domain_pack_identity": revision.domain_pack_identity,
            "template_identities": revision.template_identities,
            "scoring_rule_identities": revision.scoring_rule_identities,
            "propagation_rule_identity": revision.propagation_rule_identity,
        },
        prefixed=True,
    )
    manifest_body = {
        "manifest_id": f"manifest-{suffix}",
        "revision_id": revision.revision_id,
        "revision_hash": revision.revision_hash,
        "approval_id": approval.approval_id,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_hash": snapshot.snapshot_hash,
        "version_manifest_hash": version_manifest_hash,
        "previous_audit_chain_head": previous_audit_chain_head,
        "export_eligible": True,
    }
    manifest_hash = canonical_hash(manifest_body, prefixed=True)
    manifest = PublicationManifest(
        f"manifest-{suffix}",
        revision.revision_id,
        revision.revision_hash,
        approval.approval_id,
        snapshot.snapshot_id,
        snapshot.snapshot_hash,
        version_manifest_hash,
        previous_audit_chain_head,
        True,
        manifest_hash,
        "2026-08-30T00:00:00Z",
    )
    audit_chain_head = canonical_hash(
        {
            "previous_audit_chain_head": previous_audit_chain_head,
            "revision_hash": revision.revision_hash,
            "approval_hash": canonical_hash(approval, prefixed=True),
            "snapshot_hash": snapshot.snapshot_hash,
            "manifest_hash": manifest.manifest_hash,
        },
        prefixed=True,
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
        audit_chain_head=audit_chain_head,
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
    audit = replace(audit, after_hash=audit_chain_head)
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


def _rekey_approval(prepared: PreparedApproval, approval_id: str, key: str) -> PreparedApproval:
    command = ApprovalCommand(
        prepared.submission.submission_id,
        prepared.submission.revision_id,
        prepared.submission.revision_hash,
        prepared.submission.record_version,
        prepared.decision.reason,
        key,
    )
    scope = IdempotencyScope(
        prepared.scope.workspace_id,
        prepared.scope.actor_id,
        prepared.scope.command,
        prepared.scope.resource_path,
        idempotency_key_hash(key),
    )
    decision = replace(prepared.decision, approval_id=approval_id)
    payload = canonical_governance_payload(
        "approval.decide", command, submission=prepared.submission, decision=decision
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, dict(payload), approval_id)
    return PreparedApproval(scope, payload_hash, command, prepared.submission, decision, audit, outbox)


def _rekey_approval_withdrawal(
    prepared: PreparedApprovalWithdrawal, withdrawal_id: str, key: str
) -> PreparedApprovalWithdrawal:
    command = WithdrawApprovalCommand(
        prepared.approval.approval_id,
        prepared.approval.revision_hash,
        prepared.approval.record_version,
        prepared.withdrawal.reason,
        key,
    )
    scope = IdempotencyScope(
        prepared.scope.workspace_id,
        prepared.scope.actor_id,
        prepared.scope.command,
        prepared.scope.resource_path,
        idempotency_key_hash(key),
    )
    withdrawal = replace(prepared.withdrawal, withdrawal_id=withdrawal_id)
    payload = canonical_governance_payload(
        "approval.withdraw", command, approval=prepared.approval, withdrawal=withdrawal
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, dict(payload), withdrawal_id)
    return PreparedApprovalWithdrawal(scope, payload_hash, command, prepared.approval, withdrawal, audit, outbox)


def _rekey_publication_withdrawal(
    prepared: PreparedPublicationWithdrawal, withdrawal_id: str, key: str
) -> PreparedPublicationWithdrawal:
    command = WithdrawPublicationCommand(
        prepared.publication.publication_id,
        prepared.publication.record_version,
        prepared.withdrawal.reason,
        prepared.withdrawal.replacement_publication_id,
        key,
    )
    scope = IdempotencyScope(
        prepared.scope.workspace_id,
        prepared.scope.actor_id,
        prepared.scope.command,
        prepared.scope.resource_path,
        idempotency_key_hash(key),
    )
    withdrawal = replace(prepared.withdrawal, withdrawal_id=withdrawal_id)
    payload = canonical_governance_payload(
        "publication.withdraw", command, publication=prepared.publication, withdrawal=withdrawal
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, dict(payload), withdrawal_id)
    return PreparedPublicationWithdrawal(scope, payload_hash, command, prepared.publication, withdrawal, audit, outbox)


def _rekey_supersession(prepared: PreparedSupersession, supersession_id: str, key: str) -> PreparedSupersession:
    command = SupersedePublicationCommand(
        prepared.old_publication.publication_id,
        prepared.replacement_publication.publication_id,
        prepared.old_publication.record_version,
        prepared.replacement_publication.record_version,
        prepared.supersession.reason,
        key,
    )
    scope = IdempotencyScope(
        prepared.scope.workspace_id,
        prepared.scope.actor_id,
        prepared.scope.command,
        prepared.scope.resource_path,
        idempotency_key_hash(key),
    )
    supersession = replace(prepared.supersession, supersession_id=supersession_id)
    payload = canonical_governance_payload(
        "publication.supersede",
        command,
        old=prepared.old_publication,
        replacement=prepared.replacement_publication,
        old_revision=prepared.old_revision,
        replacement_revision=prepared.replacement_revision,
        supersession=supersession,
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(scope, payload_hash, dict(payload), supersession_id)
    return PreparedSupersession(
        scope,
        payload_hash,
        command,
        prepared.old_publication,
        prepared.replacement_publication,
        prepared.old_revision,
        prepared.replacement_revision,
        supersession,
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


def _supersession_endpoint_snapshot(path: Path) -> tuple[tuple[tuple[object, ...], ...], ...]:
    with sqlite3.connect(path) as connection:
        return (
            tuple(connection.execute("SELECT * FROM fmea_publications ORDER BY workspace_id,publication_id")),
            tuple(connection.execute("SELECT * FROM fmea_publication_withdrawals ORDER BY workspace_id,withdrawal_id")),
            tuple(connection.execute("SELECT * FROM fmea_supersessions ORDER BY workspace_id,supersession_id")),
            tuple(connection.execute("SELECT * FROM fmea_audit_events ORDER BY workspace_id,event_id")),
            tuple(connection.execute("SELECT * FROM fmea_outbox_events ORDER BY workspace_id,event_id")),
            tuple(
                connection.execute(
                    "SELECT * FROM fmea_governance_event_bindings ORDER BY workspace_id,resource_type,resource_id"
                )
            ),
            tuple(connection.execute("SELECT * FROM idempotency_records ORDER BY scope_key")),
        )


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
        replacement_revision,
        "pub-new",
        "new",
        "00000000-0000-4000-8000-000000000712",
        previous_audit_chain_head=old.publication.audit_chain_head,
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


def test_transaction_guard_rejects_second_decision_for_submission_atomically(
    repository: SqliteGovernanceRepository,
) -> None:
    publication = prepared_publication()
    repository.commit_revision(prepared_revision())
    submission = _prepared_submission_for(publication)
    repository.commit_approval_submission(submission)
    first = _prepared_approval_for(publication, submission)
    repository.commit_approval(first)
    second = _rekey_approval(first, "approval-duplicate", "00000000-0000-4000-8000-000000000733")

    with pytest.raises(ReviewError) as captured:
        SqliteGovernanceRepository(repository.database_path).commit_approval(second)

    assert captured.value.code == "FMEA_GOVERNANCE_APPROVAL_STATE_INVALID"
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_approval_decisions").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM fmea_audit_events").fetchone() == (3,)
        assert connection.execute("SELECT COUNT(*) FROM fmea_outbox_events").fetchone() == (3,)


def test_transaction_guard_rejects_second_approval_withdrawal_atomically(
    repository: SqliteGovernanceRepository,
) -> None:
    publication = prepared_publication()
    repository.commit_publication(publication)
    first = _prepared_approval_withdrawal_for(publication)
    repository.commit_approval_withdrawal(first)
    second = _rekey_approval_withdrawal(first, "approval-withdrawal-duplicate", "00000000-0000-4000-8000-000000000734")

    with pytest.raises(ReviewError) as captured:
        SqliteGovernanceRepository(repository.database_path).commit_approval_withdrawal(second)

    assert captured.value.code == "FMEA_GOVERNANCE_APPROVAL_STATE_INVALID"
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_approval_withdrawals").fetchone() == (1,)


def test_transaction_guard_rejects_publication_after_approval_withdrawal_atomically(
    repository: SqliteGovernanceRepository,
) -> None:
    publication = prepared_publication()
    repository.commit_revision(prepared_revision())
    submission = _prepared_submission_for(publication)
    repository.commit_approval_submission(submission)
    repository.commit_approval(_prepared_approval_for(publication, submission))
    approval_withdrawal = _prepared_approval_withdrawal_for(publication)
    repository.commit_approval_withdrawal(approval_withdrawal)

    with pytest.raises(ReviewError) as captured:
        SqliteGovernanceRepository(repository.database_path).commit_publication(publication)

    assert captured.value.code == "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID"
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_publications").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM fmea_publication_manifests").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM fmea_normalized_snapshots").fetchone() == (0,)


def test_transaction_guard_rejects_second_publication_withdrawal_atomically(
    repository: SqliteGovernanceRepository,
) -> None:
    publication = prepared_publication()
    repository.commit_publication(publication)
    first = _prepared_publication_withdrawal_for(publication)
    repository.commit_publication_withdrawal(first)
    second = _rekey_publication_withdrawal(
        first, "publication-withdrawal-duplicate", "00000000-0000-4000-8000-000000000735"
    )

    with pytest.raises(ReviewError) as captured:
        SqliteGovernanceRepository(repository.database_path).commit_publication_withdrawal(second)

    assert captured.value.code == "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID"
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_publication_withdrawals").fetchone() == (1,)


def test_transaction_guard_rejects_second_outgoing_supersession_atomically(
    repository: SqliteGovernanceRepository,
) -> None:
    old_revision = make_fmea_revision()
    replacement_revision = make_fmea_revision(
        revision_id="revision-2",
        parent_revision_id=old_revision.revision_id,
        parent_revision_hash=old_revision.revision_hash,
    )
    old = _prepared_publication_bundle(old_revision, "pub-old", "old", "00000000-0000-4000-8000-000000000736")
    replacement = _prepared_publication_bundle(
        replacement_revision,
        "pub-new",
        "new",
        "00000000-0000-4000-8000-000000000737",
        previous_audit_chain_head=old.publication.audit_chain_head,
    )
    repository.commit_publication(old)
    repository.commit_publication(replacement)
    first = _prepared_supersession_for_publications(old, replacement)
    repository.commit_supersession(first)
    second = _rekey_supersession(first, "supersession-duplicate", "00000000-0000-4000-8000-000000000738")

    with pytest.raises(ReviewError) as captured:
        SqliteGovernanceRepository(repository.database_path).commit_supersession(second)

    assert captured.value.code == "FMEA_GOVERNANCE_SUPERSESSION_INVALID"
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_supersessions").fetchone() == (1,)


@pytest.mark.parametrize("withdrawn_endpoint", ["old", "replacement"])
def test_transaction_guard_rejects_supersession_with_withdrawn_endpoint_atomically(
    repository: SqliteGovernanceRepository,
    withdrawn_endpoint: str,
) -> None:
    old_revision = make_fmea_revision()
    replacement_revision = make_fmea_revision(
        revision_id="revision-2",
        parent_revision_id=old_revision.revision_id,
        parent_revision_hash=old_revision.revision_hash,
    )
    old_id = "publication-1" if withdrawn_endpoint == "old" else "pub-old"
    replacement_id = "publication-1" if withdrawn_endpoint == "replacement" else "pub-new"
    old = _prepared_publication_bundle(
        old_revision,
        old_id,
        "old-withdrawal-guard",
        "00000000-0000-4000-8000-000000000760",
    )
    replacement = _prepared_publication_bundle(
        replacement_revision,
        replacement_id,
        "replacement-withdrawal-guard",
        "00000000-0000-4000-8000-000000000761",
        previous_audit_chain_head=old.publication.audit_chain_head,
    )
    repository.commit_publication(old)
    repository.commit_publication(replacement)
    withdrawn = old if withdrawn_endpoint == "old" else replacement
    repository.commit_publication_withdrawal(_prepared_publication_withdrawal_for(withdrawn))
    prepared = _prepared_supersession_for_publications(old, replacement)
    before = _supersession_endpoint_snapshot(repository.database_path)
    old_lifecycle = repository.get_publication_lifecycle(old_id, "ws-1")
    replacement_lifecycle = repository.get_publication_lifecycle(replacement_id, "ws-1")

    restarted = SqliteGovernanceRepository(repository.database_path)
    with pytest.raises(ReviewError) as captured:
        restarted.commit_supersession(prepared)

    assert captured.value.code == "FMEA_GOVERNANCE_SUPERSESSION_INVALID"
    assert _supersession_endpoint_snapshot(repository.database_path) == before
    assert restarted.get_publication_lifecycle(old_id, "ws-1") == old_lifecycle
    assert restarted.get_publication_lifecycle(replacement_id, "ws-1") == replacement_lifecycle
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_supersessions WHERE workspace_id=? AND supersession_id=?",
            ("ws-1", prepared.supersession.supersession_id),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            ("ws-1", prepared.audit.event_id),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            ("ws-1", prepared.outbox.event_id),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_governance_event_bindings "
            "WHERE workspace_id=? AND resource_type='supersession' AND resource_id=?",
            ("ws-1", prepared.supersession.supersession_id),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM idempotency_records WHERE scope_key=?",
            (prepared.scope.scope_key,),
        ).fetchone() == (0,)


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
        replacement_revision,
        "pub-new",
        "new",
        "00000000-0000-4000-8000-000000000712",
        previous_audit_chain_head=old_publication.publication.audit_chain_head,
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
    second = _prepared_publication_bundle(
        second_revision,
        "pub-2",
        "second",
        "00000000-0000-4000-8000-000000000720",
        previous_audit_chain_head=first.publication.audit_chain_head,
    )
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
        connection.execute(
            "INSERT INTO fmea_publication_lineage_bindings "
            "(workspace_id,publication_id,manifest_id,snapshot_id,revision_id,analysis_id,revision_hash,manifest_hash,snapshot_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("ws-1", *first_lineage),
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
    _initialize_through(path, 6)
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
    if kind == "publication":
        return publication, repository.commit_publication(publication)
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
        replacement_revision,
        "pub-new",
        "new",
        "00000000-0000-4000-8000-000000000722",
        previous_audit_chain_head=old.publication.audit_chain_head,
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
    if kind == "publication":
        return repository.replay_publication(prepared.scope, prepared.payload_hash)
    return repository.replay_supersession(prepared.scope, prepared.payload_hash)


@pytest.mark.parametrize(
    ("replay_kind", "commit_kind"),
    [
        ("assemble", "revision"),
        ("submit", "approval_submission"),
        ("approve", "approval"),
        ("withdraw_approval", "approval_withdrawal"),
        ("publish", "publication"),
        ("withdraw_publication", "publication_withdrawal"),
        ("supersede", "supersession"),
    ],
)
def test_generic_command_bound_replay_restores_each_typed_result(
    repository: SqliteGovernanceRepository,
    replay_kind: str,
    commit_kind: str,
) -> None:
    prepared, committed = _commit_replay_case(repository, commit_kind)

    assert repository.replay_governance_command(
        replay_kind,
        prepared.scope,
        prepared.command,
    ) == replace(committed, replayed=True)


def test_generic_command_bound_replay_distinguishes_reject_from_approve(
    repository: SqliteGovernanceRepository,
) -> None:
    publication = prepared_publication()
    repository.commit_revision(prepared_revision())
    submission = _prepared_submission_for(publication)
    repository.commit_approval_submission(submission)
    base = _prepared_approval_for(publication, submission)
    decision = replace(base.decision, status=ApprovalStatus.REJECTED, reason="rejected")
    command = ApprovalRejectionCommand(
        base.command.submission_id,
        base.command.revision_id,
        base.command.revision_hash,
        base.command.expected_submission_version,
        decision.reason,
        base.command.idempotency_key,
    )
    payload = canonical_governance_payload(
        "approval.decide",
        command,
        submission=submission.submission,
        decision=decision,
    )
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(base.scope, payload_hash, dict(payload), decision.approval_id)
    prepared = PreparedApproval(base.scope, payload_hash, command, submission.submission, decision, audit, outbox)
    committed = repository.commit_approval(prepared)

    assert repository.replay_governance_command("reject", prepared.scope, command) == replace(
        committed,
        replayed=True,
    )
    with pytest.raises(ValueError, match="operation"):
        repository.replay_governance_command(
            "approve",
            prepared.scope,
            ApprovalCommand(
                command.submission_id,
                command.revision_id,
                command.revision_hash,
                command.expected_submission_version,
                command.reason,
                command.idempotency_key,
            ),
        )


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


def _stored_json(value: object) -> tuple[str, str]:
    payload = encode_review_json(value)
    return payload, "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("operation", ("insert_without_binding", "delete_binding"))
def test_migration_008_requires_total_publication_lineage_binding(
    repository: SqliteGovernanceRepository,
    operation: str,
) -> None:
    prepared = prepared_publication()
    repository.commit_publication(prepared)

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        if operation == "delete_binding":
            connection.execute("DROP TRIGGER fmea_publication_lineage_bindings_no_delete")
            with pytest.raises(sqlite3.IntegrityError), connection:
                connection.execute(
                    "DELETE FROM fmea_publication_lineage_bindings WHERE workspace_id=? AND publication_id=?",
                    (prepared.scope.workspace_id, prepared.publication.publication_id),
                )
        else:
            unbound = replace(prepared.publication, publication_id="publication-without-lineage")
            publication_json, publication_hash = _stored_json(unbound)
            connection.execute("DROP TRIGGER fmea_publications_authority_required")
            with pytest.raises(sqlite3.IntegrityError), connection:
                connection.execute(
                    "INSERT INTO fmea_publications "
                    "(workspace_id,publication_id,analysis_id,revision_id,revision_hash,approval_id,manifest_id,"
                    "manifest_hash,snapshot_id,snapshot_hash,audit_chain_head,publisher_actor_id,record_version,"
                    "publication_json,canonical_json_hash,audit_event_id,outbox_event_id,idempotency_scope,"
                    "payload_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        unbound.workspace_id,
                        unbound.publication_id,
                        unbound.analysis_id,
                        unbound.revision_id,
                        unbound.revision_hash,
                        unbound.approval_id,
                        unbound.manifest_id,
                        unbound.manifest_hash,
                        unbound.snapshot_id,
                        unbound.snapshot_hash,
                        unbound.audit_chain_head,
                        unbound.publisher_actor_id,
                        unbound.record_version,
                        publication_json,
                        publication_hash,
                        None,
                        None,
                        None,
                        None,
                        unbound.created_at,
                    ),
                )


def test_migration_008_requires_total_revision_analysis_binding(
    repository: SqliteGovernanceRepository,
) -> None:
    unbound = make_fmea_revision(revision_id="revision-without-analysis-binding")
    revision_json, revision_json_hash = _stored_json(unbound)

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DROP TRIGGER fmea_revisions_authority_required")
        with pytest.raises(sqlite3.IntegrityError), connection:
            connection.execute(
                "INSERT INTO fmea_revisions "
                "(workspace_id,revision_id,analysis_id,analysis_record_version,parent_revision_id,"
                "parent_revision_hash,revision_hash,revision_json,record_version,canonical_json_hash,"
                "audit_event_id,outbox_event_id,idempotency_scope,payload_hash,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    unbound.workspace_id,
                    unbound.revision_id,
                    unbound.analysis_id,
                    unbound.analysis_record_version,
                    unbound.parent_revision_id,
                    unbound.parent_revision_hash,
                    unbound.revision_hash,
                    revision_json,
                    1,
                    revision_json_hash,
                    None,
                    None,
                    None,
                    None,
                    unbound.created_at,
                ),
            )


def test_migration_008_revision_binding_checks_authoritative_and_revision_json_hash(
    repository: SqliteGovernanceRepository,
) -> None:
    revision = make_fmea_revision(revision_id="revision-json-analysis-mismatch")
    revision_value = json.loads(encode_review_json(revision))
    revision_value["analysis_hash"] = "b" * 64
    revision_json = json.dumps(revision_value, sort_keys=True, separators=(",", ":"))
    revision_json_hash = "sha256:" + sha256(revision_json.encode("utf-8")).hexdigest()

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("DROP TRIGGER fmea_revisions_authority_required")
        with pytest.raises(sqlite3.IntegrityError, match="lineage"), connection:
            connection.execute(
                "INSERT INTO fmea_revisions "
                "(workspace_id,revision_id,analysis_id,analysis_record_version,parent_revision_id,"
                "parent_revision_hash,revision_hash,revision_json,record_version,canonical_json_hash,"
                "audit_event_id,outbox_event_id,idempotency_scope,payload_hash,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    revision.workspace_id,
                    revision.revision_id,
                    revision.analysis_id,
                    revision.analysis_record_version,
                    revision.parent_revision_id,
                    revision.parent_revision_hash,
                    revision.revision_hash,
                    revision_json,
                    1,
                    revision_json_hash,
                    None,
                    None,
                    None,
                    None,
                    revision.created_at,
                ),
            )
            connection.execute(
                "INSERT INTO fmea_revision_analysis_bindings "
                "(workspace_id,revision_id,analysis_id,analysis_record_version,analysis_hash) VALUES (?,?,?,?,?)",
                (
                    revision.workspace_id,
                    revision.revision_id,
                    revision.analysis_id,
                    revision.analysis_record_version,
                    revision.analysis_hash,
                ),
            )


@pytest.mark.parametrize(
    "kind",
    (
        "revision",
        "readiness",
        "approval_submission",
        "approval",
        "approval_withdrawal",
        "publication",
        "publication_withdrawal",
        "supersession",
    ),
)
def test_replay_cross_binds_authority_dto_to_canonical_outbox_payload(
    repository: SqliteGovernanceRepository,
    kind: str,
) -> None:
    if kind == "publication":
        prepared = prepared_publication()
        repository.commit_publication(prepared)
    else:
        prepared, _ = _commit_replay_case(repository, kind)

    with sqlite3.connect(repository.database_path) as connection:
        if kind == "readiness":
            connection.execute("DROP TRIGGER fmea_revision_readiness_reports_no_update")
            row = connection.execute(
                "SELECT report_json,source_hashes_json FROM fmea_revision_readiness_reports "
                "WHERE workspace_id=? AND readiness_id=?",
                (prepared.scope.workspace_id, prepared.readiness_id),
            ).fetchone()
            assert row is not None
            report = replace(
                prepared.report,
                evidence_pack_ids=(*prepared.report.evidence_pack_ids, "tampered-pack"),
            )
            report_json = encode_review_json(report)
            record_hash = canonical_hash(
                {
                    "readiness_id": prepared.readiness_id,
                    "report": report,
                    "source_hashes": prepared.source_hashes,
                },
                prefixed=True,
            )
            connection.execute(
                "UPDATE fmea_revision_readiness_reports SET report_json=?,report_hash=?,canonical_json_hash=? "
                "WHERE workspace_id=? AND readiness_id=?",
                (
                    report_json,
                    canonical_hash(report, prefixed=True),
                    record_hash,
                    prepared.scope.workspace_id,
                    prepared.readiness_id,
                ),
            )
        else:
            table, identifier, json_column = {
                "revision": ("fmea_revisions", "revision_id", "revision_json"),
                "approval_submission": ("fmea_approval_submissions", "submission_id", "submission_json"),
                "approval": ("fmea_approval_decisions", "approval_id", "decision_json"),
                "approval_withdrawal": ("fmea_approval_withdrawals", "withdrawal_id", "withdrawal_json"),
                "publication": ("fmea_publications", "publication_id", "publication_json"),
                "publication_withdrawal": (
                    "fmea_publication_withdrawals",
                    "withdrawal_id",
                    "withdrawal_json",
                ),
                "supersession": ("fmea_supersessions", "supersession_id", "supersession_json"),
            }[kind]
            if kind == "revision":
                resource_id = prepared.revision.revision_id
            elif kind == "approval_submission":
                resource_id = prepared.submission.submission_id
            elif kind == "approval":
                resource_id = prepared.decision.approval_id
            elif kind in {"approval_withdrawal", "publication_withdrawal"}:
                resource_id = prepared.withdrawal.withdrawal_id
            elif kind == "publication":
                resource_id = prepared.publication.publication_id
            else:
                resource_id = prepared.supersession.supersession_id
            connection.execute(f"DROP TRIGGER {table}_no_update")
            payload = json.loads(
                connection.execute(
                    f"SELECT {json_column} FROM {table} WHERE workspace_id=? AND {identifier}=?",  # noqa: S608
                    (prepared.scope.workspace_id, resource_id),
                ).fetchone()[0]
            )
            payload["created_at"] = "2026-08-30T01:00:00Z"
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            connection.execute(
                f"UPDATE {table} SET {json_column}=?,canonical_json_hash=?,created_at=? "  # noqa: S608
                f"WHERE workspace_id=? AND {identifier}=?",
                (
                    payload_json,
                    "sha256:" + sha256(payload_json.encode("utf-8")).hexdigest(),
                    payload["created_at"],
                    prepared.scope.workspace_id,
                    resource_id,
                ),
            )

    restarted = SqliteGovernanceRepository(repository.database_path)
    restarted.initialize()
    if kind == "readiness":
        assert restarted.get_readiness(prepared.readiness_id, prepared.scope.workspace_id) is not None
    with pytest.raises((ReviewError, ValueError)):
        _replay_case(restarted, kind, prepared)


@pytest.mark.parametrize("tamper", ("missing_event_binding", "outbox_payload"))
def test_publication_rejects_existing_revision_without_exact_authority_chain(
    repository: SqliteGovernanceRepository,
    tamper: str,
) -> None:
    revision_prepared = prepared_revision()
    revision_result = repository.commit_revision(revision_prepared)
    publication = prepared_publication()

    with sqlite3.connect(repository.database_path) as connection:
        if tamper == "missing_event_binding":
            connection.execute("DROP TRIGGER fmea_governance_event_bindings_no_delete")
            connection.execute(
                "DELETE FROM fmea_governance_event_bindings "
                "WHERE workspace_id=? AND resource_type='revision' AND resource_id=?",
                (revision_prepared.scope.workspace_id, revision_prepared.revision.revision_id),
            )
        else:
            connection.execute("DROP TRIGGER fmea_outbox_events_no_update")
            connection.execute(
                "UPDATE fmea_outbox_events SET payload_json='{}' WHERE workspace_id=? AND event_id=?",
                (revision_prepared.scope.workspace_id, revision_result.outbox_event_id),
            )

    with pytest.raises((ReviewError, ValueError)):
        repository.commit_publication(publication)
    assert repository.get_publication(publication.publication.publication_id, publication.scope.workspace_id) is None


def test_migration_008_backfills_reconstructable_v7_authority_and_preserves_replay(tmp_path: Path) -> None:
    path = tmp_path / "reconstructable-v7.sqlite3"
    _initialize_through(path, 7)
    repository = SqliteGovernanceRepository(path)
    seed_authoritative_analysis(path)
    revision = prepared_revision()
    revision_result = repository.commit_revision(revision)
    publication = prepared_publication()
    publication_result = repository.commit_publication(publication)

    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER fmea_revisions_no_update")
        connection.execute("DROP TRIGGER fmea_publications_no_update")
        connection.execute(
            "UPDATE fmea_revisions SET idempotency_scope=NULL,payload_hash=NULL WHERE workspace_id=? AND revision_id=?",
            (revision.scope.workspace_id, revision.revision.revision_id),
        )
        connection.execute(
            "UPDATE fmea_publications SET idempotency_scope=NULL,payload_hash=NULL "
            "WHERE workspace_id=? AND publication_id=?",
            (publication.scope.workspace_id, publication.publication.publication_id),
        )

    restarted = SqliteGovernanceRepository(path)
    restarted.initialize()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone() == (9,)
        assert connection.execute(
            "SELECT idempotency_scope,payload_hash FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            (revision.scope.workspace_id, revision.revision.revision_id),
        ).fetchone() == (revision.scope.scope_key, revision.payload_hash)
        assert connection.execute(
            "SELECT idempotency_scope,payload_hash FROM fmea_publications WHERE workspace_id=? AND publication_id=?",
            (publication.scope.workspace_id, publication.publication.publication_id),
        ).fetchone() == (publication.scope.scope_key, publication.payload_hash)
    assert restarted.replay_revision(revision.scope, revision.payload_hash) == replace(revision_result, replayed=True)
    assert restarted.replay_publication(publication.scope, publication.payload_hash) == replace(
        publication_result, replayed=True
    )


def test_migration_008_rejects_unreconstructable_v7_authority_atomically(tmp_path: Path) -> None:
    path = tmp_path / "unreconstructable-v7.sqlite3"
    _initialize_through(path, 7)
    repository = SqliteGovernanceRepository(path)
    seed_authoritative_analysis(path)
    publication = prepared_publication()
    repository.commit_publication(publication)

    with sqlite3.connect(path) as connection:
        revision = connection.execute(
            "SELECT audit_event_id,outbox_event_id,idempotency_scope FROM fmea_revisions "
            "WHERE workspace_id=? AND revision_id=?",
            (publication.scope.workspace_id, publication.revision.revision_id),
        ).fetchone()
        connection.execute("DROP TRIGGER fmea_governance_event_bindings_no_delete")
        connection.execute("DROP TRIGGER fmea_audit_events_no_delete")
        connection.execute("DROP TRIGGER fmea_outbox_events_no_delete")
        connection.execute("DROP TRIGGER fmea_revisions_no_update")
        connection.execute(
            "DELETE FROM fmea_governance_event_bindings "
            "WHERE workspace_id=? AND resource_type='revision' AND resource_id=?",
            (publication.scope.workspace_id, publication.revision.revision_id),
        )
        connection.execute(
            "DELETE FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            (publication.scope.workspace_id, revision[0]),
        )
        connection.execute(
            "DELETE FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            (publication.scope.workspace_id, revision[1]),
        )
        connection.execute("DELETE FROM idempotency_records WHERE scope_key=?", (revision[2],))
        connection.execute(
            "UPDATE fmea_revisions SET audit_event_id=NULL,outbox_event_id=NULL,idempotency_scope=NULL,payload_hash=NULL "
            "WHERE workspace_id=? AND revision_id=?",
            (publication.scope.workspace_id, publication.revision.revision_id),
        )

    with pytest.raises((sqlite3.IntegrityError, ValueError), match="authority|replay|binding"):
        SqliteGovernanceRepository(path).initialize()

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone() == (7,)
        assert connection.execute("SELECT COUNT(*) FROM fmea_publications").fetchone() == (1,)
        assert (
            connection.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'fmea_migration_008%'").fetchone() is None
        )


def test_migration_009_rejects_direct_manifest_without_lineage_binding(
    repository: SqliteGovernanceRepository,
) -> None:
    prepared = prepared_publication()
    repository.commit_publication(prepared)
    orphan = replace(prepared.manifest, manifest_id="manifest-without-lineage")
    manifest_json = encode_review_json(orphan)
    manifest_json_hash = "sha256:" + sha256(manifest_json.encode("utf-8")).hexdigest()

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY|lineage"), connection:
            connection.execute(
                "INSERT INTO fmea_publication_manifests "
                "(workspace_id,manifest_id,revision_id,revision_hash,approval_id,snapshot_id,snapshot_hash,"
                "version_manifest_hash,previous_audit_chain_head,export_eligible,manifest_hash,manifest_json,"
                "canonical_json_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    prepared.scope.workspace_id,
                    orphan.manifest_id,
                    orphan.revision_id,
                    orphan.revision_hash,
                    orphan.approval_id,
                    orphan.snapshot_id,
                    orphan.snapshot_hash,
                    orphan.version_manifest_hash,
                    orphan.previous_audit_chain_head,
                    int(orphan.export_eligible),
                    orphan.manifest_hash,
                    manifest_json,
                    manifest_json_hash,
                    orphan.created_at,
                ),
            )


def test_migration_009_adds_snapshot_reverse_lineage_foreign_key(
    repository: SqliteGovernanceRepository,
) -> None:
    with sqlite3.connect(repository.database_path) as connection:
        foreign_keys = connection.execute("PRAGMA foreign_key_list(fmea_normalized_snapshots)").fetchall()

    assert any(
        row[2] == "fmea_publication_lineage_bindings" and row[3] == "workspace_id" and row[4] == "workspace_id"
        for row in foreign_keys
    )
    assert any(
        row[2] == "fmea_publication_lineage_bindings" and row[3] == "snapshot_id" and row[4] == "snapshot_id"
        for row in foreign_keys
    )


def test_public_current_reads_are_workspace_qualified_and_project_lifecycle(
    repository: SqliteGovernanceRepository,
) -> None:
    revision_prepared = prepared_revision()
    repository.commit_revision(revision_prepared)
    assert repository.get_revision_record_version("revision-1", "ws-1") == 1
    assert repository.get_revision_record_version("revision-1", "ws-other") is None

    publication_prepared = prepared_publication()
    repository.commit_publication(publication_prepared)
    assert repository.get_approval_submission("submission-1", "ws-1") is not None
    assert repository.get_approval_submission("submission-1", "ws-other") is None
    approval = repository.get_approval_decision("approval-1", "ws-1")
    assert approval is not None
    assert approval.status is ApprovalStatus.APPROVED
    assert repository.get_approval_decision("approval-1", "ws-other") is None
    assert repository.get_approval_decision_for_submission("submission-1", "ws-1") == approval
    assert (
        repository.get_publication_lifecycle("publication-1", "ws-1").effective_status
        is RevisionPublicationStatus.PUBLISHED
    )

    base_withdrawal = prepared_publication_withdrawal()
    withdrawal_payload = canonical_governance_payload(
        "publication.withdraw",
        base_withdrawal.command,
        publication=publication_prepared.publication,
        withdrawal=base_withdrawal.withdrawal,
    )
    withdrawal_payload_hash = governance_payload_hash(withdrawal_payload)
    withdrawal_audit, withdrawal_outbox = _prepared_events(
        base_withdrawal.scope,
        withdrawal_payload_hash,
        dict(withdrawal_payload),
        base_withdrawal.withdrawal.withdrawal_id,
    )
    withdrawal_prepared = PreparedPublicationWithdrawal(
        base_withdrawal.scope,
        withdrawal_payload_hash,
        base_withdrawal.command,
        publication_prepared.publication,
        base_withdrawal.withdrawal,
        withdrawal_audit,
        withdrawal_outbox,
    )
    repository.commit_publication_withdrawal(withdrawal_prepared)
    lifecycle = repository.get_publication_lifecycle("publication-1", "ws-1")
    assert lifecycle is not None
    assert lifecycle.effective_status is RevisionPublicationStatus.WITHDRAWN
    assert lifecycle.withdrawal == withdrawal_prepared.withdrawal


def test_public_current_reads_fail_closed_on_canonical_corruption(
    repository: SqliteGovernanceRepository,
) -> None:
    prepared = prepared_revision()
    repository.commit_revision(prepared)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("DROP TRIGGER fmea_revisions_no_update")
        connection.execute(
            "UPDATE fmea_revisions SET canonical_json_hash=? WHERE workspace_id=? AND revision_id=?",
            ("sha256:" + "b" * 64, prepared.scope.workspace_id, prepared.revision.revision_id),
        )

    with pytest.raises((ReviewError, ValueError)):
        repository.get_revision_record_version(prepared.revision.revision_id, prepared.scope.workspace_id)


def _persist_publication_migration_fixture(path: Path) -> PreparedPublication:
    repository = SqliteGovernanceRepository(path)
    seed_authoritative_analysis(path)
    prepared = prepared_publication()
    repository.commit_publication(prepared)
    return prepared


def _tamper_publication_dependency_chain_consistently(
    path: Path,
    persisted: PreparedPublication,
    *,
    dependency_kind: str,
    clear_replay_metadata: bool,
) -> None:
    table, identifier, json_column, dto_key = {
        "revision": ("fmea_revisions", "revision_id", "revision_json", "revision"),
        "approval_submission": (
            "fmea_approval_submissions",
            "submission_id",
            "submission_json",
            "submission",
        ),
        "approval": ("fmea_approval_decisions", "approval_id", "decision_json", "decision"),
    }[dependency_kind]
    resource_id = {
        "revision": persisted.revision.revision_id,
        "approval_submission": persisted.submission.submission_id,
        "approval": persisted.approval.approval_id,
    }[dependency_kind]

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
        connection.execute("DROP TRIGGER IF EXISTS fmea_audit_events_no_update")
        connection.execute("DROP TRIGGER IF EXISTS fmea_outbox_events_no_update")
        dependency = connection.execute(
            f"SELECT * FROM {table} WHERE workspace_id=? AND {identifier}=?",  # noqa: S608
            (persisted.scope.workspace_id, resource_id),
        ).fetchone()
        assert dependency is not None
        outbox = connection.execute(
            "SELECT payload_json FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            (persisted.scope.workspace_id, dependency["outbox_event_id"]),
        ).fetchone()
        assert outbox is not None

        audit = connection.execute(
            "SELECT event_json,actor_type FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            (persisted.scope.workspace_id, dependency["audit_event_id"]),
        ).fetchone()
        assert audit is not None
        if dependency_kind == "revision":
            # Migration 009 validates the revision DTO/outbox/hash bundle but
            # does not compare the persisted audit actor_type column with the
            # decoded event. Keep the bundle self-consistent and create the
            # runtime-only chain drift.
            divergent_actor_type = "system" if audit["actor_type"] != "system" else "human"
            connection.execute(
                "UPDATE fmea_audit_events SET actor_type=? WHERE workspace_id=? AND event_id=?",
                (divergent_actor_type, persisted.scope.workspace_id, dependency["audit_event_id"]),
            )
        else:
            divergent_payload = json.loads(outbox["payload_json"])
            divergent_payload[dto_key]["created_at"] = "2026-08-30T00:00:01Z"
            assert json.loads(dependency[json_column])["created_at"] != divergent_payload[dto_key]["created_at"]
            divergent_outbox_json = json.dumps(
                divergent_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            divergent_payload_hash = "sha256:" + sha256(divergent_outbox_json.encode("utf-8")).hexdigest()
            divergent_audit = json.loads(audit["event_json"])
            divergent_audit["canonical_payload_hash"] = divergent_payload_hash
            divergent_audit_json = encode_review_json(divergent_audit)

            connection.execute(
                f"UPDATE {table} SET payload_hash=? WHERE workspace_id=? AND {identifier}=?",  # noqa: S608
                (divergent_payload_hash, persisted.scope.workspace_id, resource_id),
            )
            connection.execute(
                "UPDATE fmea_outbox_events SET payload_json=?,payload_hash=? WHERE workspace_id=? AND event_id=?",
                (
                    divergent_outbox_json,
                    divergent_payload_hash,
                    persisted.scope.workspace_id,
                    dependency["outbox_event_id"],
                ),
            )
            connection.execute(
                "UPDATE fmea_audit_events SET event_json=?,canonical_payload_hash=? WHERE workspace_id=? AND event_id=?",
                (
                    divergent_audit_json,
                    divergent_payload_hash,
                    persisted.scope.workspace_id,
                    dependency["audit_event_id"],
                ),
            )
            connection.execute(
                "UPDATE idempotency_records SET payload_hash=? WHERE resource_id=?",
                (divergent_payload_hash, resource_id),
            )

        if clear_replay_metadata:
            connection.execute("DROP TRIGGER IF EXISTS fmea_revisions_no_update")
            connection.execute("DROP TRIGGER IF EXISTS fmea_publications_no_update")
            connection.execute(
                "UPDATE fmea_revisions SET idempotency_scope=NULL,payload_hash=NULL "
                "WHERE workspace_id=? AND revision_id=?",
                (persisted.scope.workspace_id, persisted.revision.revision_id),
            )
            connection.execute(
                "UPDATE fmea_publications SET idempotency_scope=NULL,payload_hash=NULL "
                "WHERE workspace_id=? AND publication_id=?",
                (persisted.scope.workspace_id, persisted.publication.publication_id),
            )


def _publication_dependency_migration_probe_state(
    path: Path,
    persisted: PreparedPublication,
    dependency_kind: str,
) -> tuple[object, ...]:
    table, identifier = {
        "revision": ("fmea_revisions", "revision_id"),
        "approval_submission": ("fmea_approval_submissions", "submission_id"),
        "approval": ("fmea_approval_decisions", "approval_id"),
    }[dependency_kind]
    resource_id = {
        "revision": persisted.revision.revision_id,
        "approval_submission": persisted.submission.submission_id,
        "approval": persisted.approval.approval_id,
    }[dependency_kind]
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        dependency = connection.execute(
            f"SELECT * FROM {table} WHERE workspace_id=? AND {identifier}=?",  # noqa: S608
            (persisted.scope.workspace_id, resource_id),
        ).fetchone()
        assert dependency is not None
        audit = connection.execute(
            "SELECT * FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            (persisted.scope.workspace_id, dependency["audit_event_id"]),
        ).fetchone()
        outbox = connection.execute(
            "SELECT * FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            (persisted.scope.workspace_id, dependency["outbox_event_id"]),
        ).fetchone()
        binding = connection.execute(
            "SELECT * FROM fmea_governance_event_bindings WHERE workspace_id=? AND resource_type=? AND resource_id=?",
            (persisted.scope.workspace_id, dependency_kind, resource_id),
        ).fetchone()
        idempotency = connection.execute(
            "SELECT * FROM idempotency_records WHERE resource_id=?",
            (resource_id,),
        ).fetchone()
        publication = connection.execute(
            "SELECT * FROM fmea_publications WHERE workspace_id=? AND publication_id=?",
            (persisted.scope.workspace_id, persisted.publication.publication_id),
        ).fetchone()
        assert audit is not None
        assert outbox is not None
        assert binding is not None
        assert idempotency is not None
        assert publication is not None
        staging_names = tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE "
                "name LIKE 'fmea_migration_%' OR name IN "
                "('fmea_revisions_v8','fmea_publications_v8','fmea_publication_manifests_v9',"
                "'fmea_normalized_snapshots_v9') ORDER BY name"
            ).fetchall()
        )
        return (
            tuple(connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()),
            tuple(dependency),
            tuple(audit),
            tuple(outbox),
            tuple(binding),
            tuple(idempotency),
            tuple(publication),
            staging_names,
        )


@pytest.mark.parametrize("starting_version", STARTING_VERSIONS)
@pytest.mark.parametrize("dependency_kind", DEPENDENCY_KINDS)
def test_migration_009_rejects_publication_dependency_chain_divergence_atomically(
    tmp_path: Path,
    starting_version: int,
    dependency_kind: str,
) -> None:
    path = tmp_path / f"unsafe-{dependency_kind}-v{starting_version}.sqlite3"
    _initialize_through(path, starting_version)
    persisted = _persist_publication_migration_fixture(path)
    _tamper_publication_dependency_chain_consistently(
        path,
        persisted,
        dependency_kind=dependency_kind,
        clear_replay_metadata=starting_version == 7,
    )
    before = _publication_dependency_migration_probe_state(path, persisted, dependency_kind)

    with pytest.raises(
        (sqlite3.IntegrityError, sqlite3.OperationalError),
        match="authority|replay|binding|CHECK|user-defined function",
    ):
        SqliteGovernanceRepository(path).initialize()

    after = _publication_dependency_migration_probe_state(path, persisted, dependency_kind)
    assert after == before
    assert after[0] == (starting_version,)
    assert after[-1] == ()


def test_migration_009_rejects_v7_authority_dto_outbox_divergence_atomically(tmp_path: Path) -> None:
    path = tmp_path / "divergent-v7.sqlite3"
    _initialize_through(path, 7)
    repository = SqliteGovernanceRepository(path)
    seed_authoritative_analysis(path)
    prepared = prepared_publication()
    repository.commit_publication(prepared)

    with sqlite3.connect(path) as connection:
        revision_row = connection.execute(
            "SELECT revision_json,audit_event_id,outbox_event_id,idempotency_scope "
            "FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            (prepared.scope.workspace_id, prepared.revision.revision_id),
        ).fetchone()
        assert revision_row is not None
        _, audit_event_id, outbox_event_id, idempotency_scope = revision_row
        outbox_json = connection.execute(
            "SELECT payload_json FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            (prepared.scope.workspace_id, outbox_event_id),
        ).fetchone()[0]
        divergent_payload = json.loads(outbox_json)
        divergent_payload["revision"]["created_at"] = "2026-08-30T00:00:01Z"
        divergent_outbox_json = json.dumps(
            divergent_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        divergent_payload_hash = "sha256:" + sha256(divergent_outbox_json.encode("utf-8")).hexdigest()

        audit_json = connection.execute(
            "SELECT event_json FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            (prepared.scope.workspace_id, audit_event_id),
        ).fetchone()[0]
        audit_payload = json.loads(audit_json)
        audit_payload["canonical_payload_hash"] = divergent_payload_hash
        divergent_audit_json = encode_review_json(audit_payload)

        connection.execute("DROP TRIGGER fmea_revisions_no_update")
        connection.execute("DROP TRIGGER fmea_audit_events_no_update")
        connection.execute("DROP TRIGGER fmea_outbox_events_no_update")
        connection.execute(
            "UPDATE fmea_revisions SET idempotency_scope=NULL,payload_hash=NULL WHERE workspace_id=? AND revision_id=?",
            (prepared.scope.workspace_id, prepared.revision.revision_id),
        )
        connection.execute(
            "UPDATE fmea_outbox_events SET payload_json=?,payload_hash=? WHERE workspace_id=? AND event_id=?",
            (divergent_outbox_json, divergent_payload_hash, prepared.scope.workspace_id, outbox_event_id),
        )
        connection.execute(
            "UPDATE fmea_audit_events SET event_json=?,canonical_payload_hash=? WHERE workspace_id=? AND event_id=?",
            (divergent_audit_json, divergent_payload_hash, prepared.scope.workspace_id, audit_event_id),
        )
        connection.execute(
            "UPDATE idempotency_records SET payload_hash=? WHERE scope_key=?",
            (divergent_payload_hash, idempotency_scope),
        )

    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="authority|replay|binding|CHECK"):
        SqliteGovernanceRepository(path).initialize()

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone() == (7,)
        assert connection.execute(
            "SELECT idempotency_scope,payload_hash FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            (prepared.scope.workspace_id, prepared.revision.revision_id),
        ).fetchone() == (None, None)
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name IN ('fmea_revisions_v8','fmea_publications_v8')"
            ).fetchone()
            is None
        )


def _tamper_revision_id_consistently(path: Path, *, clear_replay_metadata: bool) -> None:
    divergent_revision_id = "revision-1-divergent"
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER fmea_revisions_no_update")
        connection.execute("DROP TRIGGER fmea_audit_events_no_update")
        connection.execute("DROP TRIGGER fmea_outbox_events_no_update")
        revision_row = connection.execute(
            "SELECT revision_id,audit_event_id,outbox_event_id,idempotency_scope,payload_hash "
            "FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
            ("ws-1", "revision-1"),
        ).fetchone()
        assert revision_row is not None
        _, audit_event_id, outbox_event_id, idempotency_scope, _ = revision_row
        divergent_revision = make_fmea_revision(revision_id=divergent_revision_id)
        divergent_revision_json = encode_json(divergent_revision)
        divergent_revision_hash = divergent_revision.revision_hash
        divergent_revision_canonical_hash = "sha256:" + sha256(divergent_revision_json.encode("utf-8")).hexdigest()

        outbox_json = connection.execute(
            "SELECT payload_json FROM fmea_outbox_events WHERE workspace_id=? AND event_id=?",
            ("ws-1", outbox_event_id),
        ).fetchone()[0]
        divergent_payload = json.loads(outbox_json)
        divergent_payload["revision"] = json.loads(divergent_revision_json)
        divergent_outbox_json = json.dumps(divergent_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        divergent_payload_hash = "sha256:" + sha256(divergent_outbox_json.encode("utf-8")).hexdigest()

        audit_json = connection.execute(
            "SELECT event_json FROM fmea_audit_events WHERE workspace_id=? AND event_id=?",
            ("ws-1", audit_event_id),
        ).fetchone()[0]
        divergent_audit = json.loads(audit_json)
        divergent_audit["canonical_payload_hash"] = divergent_payload_hash
        divergent_audit_json = encode_review_json(divergent_audit)

        connection.execute(
            "UPDATE fmea_revisions SET revision_hash=?,revision_json=?,canonical_json_hash=?,"
            "idempotency_scope=?,payload_hash=? WHERE workspace_id=? AND revision_id=?",
            (
                divergent_revision_hash,
                divergent_revision_json,
                divergent_revision_canonical_hash,
                None if clear_replay_metadata else idempotency_scope,
                None if clear_replay_metadata else divergent_payload_hash,
                "ws-1",
                "revision-1",
            ),
        )
        connection.execute(
            "UPDATE fmea_outbox_events SET payload_json=?,payload_hash=? WHERE workspace_id=? AND event_id=?",
            (divergent_outbox_json, divergent_payload_hash, "ws-1", outbox_event_id),
        )
        connection.execute(
            "UPDATE fmea_audit_events SET event_json=?,canonical_payload_hash=? WHERE workspace_id=? AND event_id=?",
            (divergent_audit_json, divergent_payload_hash, "ws-1", audit_event_id),
        )
        connection.execute(
            "UPDATE idempotency_records SET payload_hash=? WHERE scope_key=?",
            (divergent_payload_hash, idempotency_scope),
        )


def _migration_probe_state(path: Path) -> tuple[object, ...]:
    with sqlite3.connect(path) as connection:
        return (
            connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone(),
            connection.execute(
                "SELECT revision_id,revision_hash,revision_json,canonical_json_hash,idempotency_scope,payload_hash "
                "FROM fmea_revisions WHERE workspace_id=? AND revision_id=?",
                ("ws-1", "revision-1"),
            ).fetchone(),
            connection.execute(
                "SELECT payload_json,payload_hash FROM fmea_outbox_events "
                "WHERE workspace_id=? AND event_id=(SELECT outbox_event_id FROM fmea_revisions "
                "WHERE workspace_id=? AND revision_id=?)",
                ("ws-1", "ws-1", "revision-1"),
            ).fetchone(),
            connection.execute(
                "SELECT event_json,canonical_payload_hash FROM fmea_audit_events "
                "WHERE workspace_id=? AND event_id=(SELECT audit_event_id FROM fmea_revisions "
                "WHERE workspace_id=? AND revision_id=?)",
                ("ws-1", "ws-1", "revision-1"),
            ).fetchone(),
            connection.execute(
                "SELECT scope_key,payload_hash FROM idempotency_records "
                "WHERE scope_key=(SELECT idempotency_scope FROM fmea_revisions "
                "WHERE workspace_id=? AND revision_id=?)",
                ("ws-1", "revision-1"),
            ).fetchone(),
            tuple(
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE name IN "
                    "('fmea_migration_009_replay_guard','fmea_revisions_v8','fmea_publications_v8',"
                    "'fmea_publication_manifests_v9','fmea_normalized_snapshots_v9') ORDER BY name"
                )
            ),
        )


def _assert_migration_009_rejects_revision_id_divergence_atomically(tmp_path: Path, maximum_version: int) -> None:
    path = tmp_path / f"divergent-revision-v{maximum_version}.sqlite3"
    _initialize_through(path, maximum_version)
    repository = SqliteGovernanceRepository(path)
    seed_authoritative_analysis(path)
    repository.commit_revision(prepared_revision())

    _tamper_revision_id_consistently(path, clear_replay_metadata=maximum_version == 7)
    before = _migration_probe_state(path)

    with pytest.raises((sqlite3.IntegrityError, sqlite3.OperationalError), match="authority|replay|binding|CHECK"):
        SqliteGovernanceRepository(path).initialize()

    after = _migration_probe_state(path)
    assert after == before
    assert after[0] == (maximum_version,)
    assert after[-1] == ()


def test_migration_009_rejects_unsafe_v7_revision_id_divergence_atomically(tmp_path: Path) -> None:
    _assert_migration_009_rejects_revision_id_divergence_atomically(tmp_path, 7)


def test_migration_009_rejects_unsafe_v8_revision_id_divergence_atomically(tmp_path: Path) -> None:
    _assert_migration_009_rejects_revision_id_divergence_atomically(tmp_path, 8)


@pytest.mark.parametrize("after_hash", [None, "sha256:" + "b" * 64])
def test_publication_hash_chain_validation_cannot_be_disabled_by_audit_marker(
    repository: SqliteGovernanceRepository,
    after_hash: str | None,
) -> None:
    prepared = prepared_publication()
    forged = replace(prepared, audit=replace(prepared.audit, after_hash=after_hash))

    with pytest.raises(ReviewError) as captured:
        repository.commit_publication(forged)
    assert captured.value.code == "FMEA_REVIEW_REQUEST_INVALID"

    connection = sqlite3.connect(repository.database_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM fmea_publications").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM fmea_normalized_snapshots").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM idempotency_records").fetchone() == (0,)
    finally:
        connection.close()


def test_command_bound_replay_restores_approval_and_rejects_changed_command(
    repository: SqliteGovernanceRepository,
) -> None:
    publication = prepared_publication()
    repository.commit_revision(prepared_revision())
    submission = _prepared_submission_for(publication)
    repository.commit_approval_submission(submission)
    approval = _prepared_approval_for(publication, submission)
    committed = repository.commit_approval(approval)

    assert repository.replay_governance_command("approve", approval.scope, approval.command) == replace(
        committed,
        replayed=True,
    )

    changed = replace(approval.command, reason="changed command")
    with pytest.raises(ReviewError) as captured:
        repository.replay_governance_command("approve", approval.scope, changed)
    assert captured.value.code == "FMEA_IDEMPOTENCY_CONFLICT"


def test_command_bound_replay_restores_publication_and_rejects_result_type_mismatch(
    repository: SqliteGovernanceRepository,
) -> None:
    prepared = prepared_publication()
    committed = repository.commit_publication(prepared)

    assert repository.replay_governance_command("publish", prepared.scope, prepared.command) == replace(
        committed,
        replayed=True,
    )

    wrong_result = ApprovalResult("approval-1", 2, "audit-1", "outbox-1")
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            "UPDATE idempotency_records SET response_json=? WHERE scope_key=?",
            (encode_review_json(wrong_result), prepared.scope.scope_key),
        )
    with pytest.raises(ValueError, match="publication response"):
        repository.replay_governance_command("publish", prepared.scope, prepared.command)


def test_publication_audit_head_survives_repository_restart_and_advances_linearly(
    repository: SqliteGovernanceRepository,
) -> None:
    assert repository.get_current_publication_audit_head("ws-1") is None
    first = prepared_publication()
    repository.commit_publication(first)
    assert repository.get_current_publication_audit_head("ws-1") == first.publication.audit_chain_head

    second_revision = make_fmea_revision(revision_id="revision-2")
    second = _prepared_publication_bundle(
        second_revision,
        "publication-2",
        "second-head",
        "00000000-0000-4000-8000-000000000758",
        previous_audit_chain_head=first.publication.audit_chain_head,
    )
    SqliteGovernanceRepository(repository.database_path).commit_publication(second)

    restarted = SqliteGovernanceRepository(repository.database_path)
    assert restarted.get_current_publication_audit_head("ws-1") == second.publication.audit_chain_head


def test_stale_publication_predecessor_is_rejected_atomically_between_repository_instances(
    repository: SqliteGovernanceRepository,
) -> None:
    first = prepared_publication()
    stale = _prepared_publication_bundle(
        make_fmea_revision(revision_id="revision-2"),
        "publication-stale",
        "stale-head",
        "00000000-0000-4000-8000-000000000759",
        previous_audit_chain_head=None,
    )
    repository.commit_publication(first)

    competing = SqliteGovernanceRepository(repository.database_path)
    with pytest.raises(ReviewError) as captured:
        competing.commit_publication(stale)
    assert captured.value.code == "FMEA_VERSION_CONFLICT"
    assert repository.get_current_publication_audit_head("ws-1") == first.publication.audit_chain_head
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM fmea_publications WHERE publication_id=?",
            (stale.publication.publication_id,),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM idempotency_records WHERE scope_key=?",
            (stale.scope.scope_key,),
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    ("target", "field_name", "forged_value"),
    [
        ("snapshot", "snapshot_hash", "sha256:" + "b" * 64),
        ("manifest", "manifest_hash", "sha256:" + "b" * 64),
        ("publication", "audit_chain_head", "sha256:" + "b" * 64),
        ("export_eligibility", "eligibility_hash", "sha256:" + "b" * 64),
        ("outbox", "event_type", "forged.publication.event"),
        ("outbox", "payload_hash", "sha256:" + "b" * 64),
    ],
)
def test_publication_rejects_forged_snapshot_manifest_chain_and_outbox_fields(
    repository: SqliteGovernanceRepository,
    target: str,
    field_name: str,
    forged_value: str,
) -> None:
    prepared = prepared_publication()
    object.__setattr__(getattr(prepared, target), field_name, forged_value)

    with pytest.raises(ReviewError) as captured:
        repository.commit_publication(prepared)

    assert captured.value.code == "FMEA_REVIEW_REQUEST_INVALID"
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fmea_publications").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM idempotency_records").fetchone() == (0,)
