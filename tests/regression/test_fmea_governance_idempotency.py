from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fmea_governance_fixtures import _prepared_events, prepared_approval_submission, prepared_revision

from fmea_application.governance_contracts import (
    PreparedApprovalSubmission,
    SubmitApprovalCommand,
    canonical_governance_payload,
    governance_payload_hash,
)
from fmea_application.review_errors import ReviewError
from fmea_infrastructure.governance_repository_sqlite import SqliteGovernanceRepository


@pytest.fixture
def repository(tmp_path: Path) -> SqliteGovernanceRepository:
    value = SqliteGovernanceRepository(tmp_path / "fmea.sqlite3")
    value.initialize()
    return value


def _same_scope_different_payload() -> PreparedApprovalSubmission:
    original = _prepared_submission_for_revision()
    submission = replace(original.submission, revision_hash="b" * 64)
    command = SubmitApprovalCommand(
        submission.revision_id,
        submission.revision_hash,
        original.revision_record_version,
        original.command.idempotency_key,
    )
    payload = canonical_governance_payload("approval.submit", command, submission=submission)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(original.scope, payload_hash, dict(payload), submission.submission_id)
    return PreparedApprovalSubmission(
        original.scope,
        payload_hash,
        command,
        original.revision_record_version,
        submission,
        audit,
        outbox,
    )


def _prepared_submission_for_revision() -> PreparedApprovalSubmission:
    original = prepared_approval_submission()
    revision = prepared_revision().revision
    submission = replace(original.submission, revision_hash=revision.revision_hash)
    command = SubmitApprovalCommand(
        submission.revision_id,
        submission.revision_hash,
        original.revision_record_version,
        original.command.idempotency_key,
    )
    payload = canonical_governance_payload("approval.submit", command, submission=submission)
    payload_hash = governance_payload_hash(payload)
    audit, outbox = _prepared_events(original.scope, payload_hash, dict(payload), submission.submission_id)
    return PreparedApprovalSubmission(
        original.scope,
        payload_hash,
        command,
        original.revision_record_version,
        submission,
        audit,
        outbox,
    )


def test_same_idempotency_key_with_different_payload_is_rejected(repository) -> None:
    repository.commit_revision(prepared_revision())
    first = _prepared_submission_for_revision()
    repository.commit_approval_submission(first)

    with pytest.raises(ReviewError) as captured:
        repository.commit_approval_submission(_same_scope_different_payload())
    assert captured.value.code == "FMEA_IDEMPOTENCY_CONFLICT"


def test_exact_replay_returns_the_persisted_response(repository) -> None:
    repository.commit_revision(prepared_revision())
    prepared = _prepared_submission_for_revision()
    result = repository.commit_approval_submission(prepared)

    replay = repository.replay_approval_submission(prepared.scope, prepared.payload_hash)

    assert replay == replace(result, replayed=True)
