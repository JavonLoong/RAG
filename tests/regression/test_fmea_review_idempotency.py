from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from hashlib import sha256

import pytest

from core_domain.fmea.codec import encode_json
from core_domain.fmea.scoring import RiskAssessment
from core_domain.fmea.states import ClaimStatus, EvidenceSupportStatus, PublicationStatus, ReviewStatus
from fmea_application.review_contracts import ReviewAction, ReviewReasonCode, encode_review_json
from fmea_application.review_errors import ReviewError


@pytest.fixture
def sqlite_review_counts():
    allowed_tables = {"review_decisions", "audit_events", "idempotency_records"}
    count_queries = {
        "review_decisions": "SELECT COUNT(*) FROM review_decisions WHERE row_id = ?",
        "audit_events": "SELECT COUNT(*) FROM audit_events WHERE row_id = ?",
        "idempotency_records": (
            "SELECT COUNT(*) FROM idempotency_records AS i "
            "JOIN review_decisions AS d ON d.decision_id = i.resource_id WHERE d.row_id = ?"
        ),
    }

    def count(repository, table: str, row_id: str, command: str | None = None) -> int:
        if table not in allowed_tables:
            raise ValueError("unsupported review count table")  # noqa: TRY003
        connection = sqlite3.connect(f"file:{repository.database_path}?mode=ro", uri=True)
        try:
            sql = count_queries[table]
            parameters: list[str] = [row_id]
            if command is not None and table != "idempotency_records":
                sql += " AND command = ?"
                parameters.append(command)
            return int(connection.execute(sql, tuple(parameters)).fetchone()[0])
        finally:
            connection.close()

    return count


def test_completed_replay_returns_original_result_after_version_increment(
    sqlite_review_service,
    seeded_review_repository,
    sqlite_review_counts,
    fixture_human_reviewer,
    fixture_decision_command,
) -> None:
    first = sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)
    replay = sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)

    assert replay == first
    assert seeded_review_repository.get_row("row-1", "ws-1").record_version == 2
    assert sqlite_review_counts(seeded_review_repository, "review_decisions", "row-1") == 1
    assert sqlite_review_counts(seeded_review_repository, "audit_events", "row-1", command="review.decision") == 1


def test_same_key_different_payload_is_conflict_without_writes(
    sqlite_review_service,
    seeded_review_repository,
    sqlite_review_counts,
    fixture_human_reviewer,
    fixture_decision_command,
) -> None:
    first_row = seeded_review_repository.get_row("row-1", "ws-1")
    sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)
    changed = replace(fixture_decision_command, reason="different payload")

    with pytest.raises(ReviewError) as captured:
        sqlite_review_service.submit_decision(changed, fixture_human_reviewer)

    assert captured.value.code == "FMEA_IDEMPOTENCY_CONFLICT"
    assert seeded_review_repository.get_row("row-1", "ws-1").record_version == 2
    assert sqlite_review_counts(seeded_review_repository, "review_decisions", "row-1") == 1
    assert sqlite_review_counts(seeded_review_repository, "audit_events", "row-1", command="review.decision") == 1
    assert first_row is not None


def test_decision_transaction_rolls_back_all_mutable_effects_on_audit_failure(
    sqlite_review_service,
    seeded_review_repository,
    sqlite_review_counts,
    fixture_human_reviewer,
    fixture_decision_command,
    monkeypatch,
) -> None:
    import fmea_infrastructure.repository_sqlite as repository_module

    original_insert_audit = repository_module.SqliteFmeaRepository._insert_audit

    def fail_audit(connection, audit, extra=None):
        raise sqlite3.IntegrityError("injected audit failure")  # noqa: TRY003

    monkeypatch.setattr(repository_module.SqliteFmeaRepository, "_insert_audit", staticmethod(fail_audit))
    with pytest.raises(sqlite3.IntegrityError):
        sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)
    monkeypatch.setattr(repository_module.SqliteFmeaRepository, "_insert_audit", original_insert_audit)

    row = seeded_review_repository.get_row("row-1", "ws-1")
    assert row is not None
    assert row.record_version == 1
    assert sqlite_review_counts(seeded_review_repository, "review_decisions", "row-1") == 0
    assert sqlite_review_counts(seeded_review_repository, "audit_events", "row-1", command="review.decision") == 0
    assert sqlite_review_counts(seeded_review_repository, "idempotency_records", "row-1") == 0


@pytest.mark.parametrize(
    "forged_field",
    (
        "row_id",
        "analysis_id",
        "evidence_pack_id",
        "item_id",
        "function_id",
        "risk_assessment",
        "controls",
        "field_evidence",
        "field_support",
        "claim_status",
        "review_status",
        "publication_status",
        "record_version",
    ),
)
def test_forged_prepared_next_row_is_rejected_without_any_writes(  # noqa: C901
    sqlite_review_service,
    seeded_review_repository,
    sqlite_review_counts,
    fixture_human_reviewer,
    fixture_decision_command,
    forged_field,
    monkeypatch,
) -> None:
    captured: list[object] = []

    class PreparedCaptured(Exception):
        pass

    def capture(prepared):
        captured.append(prepared)
        raise PreparedCaptured

    monkeypatch.setattr(seeded_review_repository, "commit_review_decision", capture)
    with pytest.raises(PreparedCaptured):
        sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)
    monkeypatch.undo()

    prepared = captured[0]
    row = prepared.next_row
    if forged_field == "row_id":
        forged_row = replace(row, row_id="forged-row")
    elif forged_field == "analysis_id":
        forged_row = replace(row, analysis_id="forged-analysis")
    elif forged_field == "evidence_pack_id":
        forged_row = replace(row, evidence_pack_id="forged-pack")
    elif forged_field == "item_id":
        forged_row = replace(row, item_id="forged-item")
    elif forged_field == "function_id":
        forged_row = replace(row, function_id="forged-function")
    elif forged_field == "risk_assessment":
        forged_row = replace(
            row,
            risk_assessment=RiskAssessment(
                severity_by_consequence_class=(("safety", 7),),
                decision_severity=7,
                occurrence=4,
                detection=3,
                rpn=84,
                decision_priority="normal",
                inherent_risk=100,
                current_risk=84,
                target_residual_risk=20,
                verified_residual_risk=20,
                uncertainty=None,
                reason="forged risk",
                scoring_rule_pack_id="forged-pack",
                scoring_rule_pack_version="1.0.0",
                evidence_ids=("ev-1",),
            ),
        )
    elif forged_field == "controls":
        forged_row = replace(row, controls=("forged control",))
    elif forged_field == "field_evidence":
        forged_row = replace(
            row,
            field_evidence=tuple(
                (field, ("forged-evidence",)) if field == "controls" else binding
                for binding in row.field_evidence
                for field in (binding[0],)
            ),
        )
    elif forged_field == "field_support":
        forged_row = replace(
            row,
            field_support=tuple(
                (field, EvidenceSupportStatus.NOT_SUPPORTED) if field == "controls" else binding
                for binding in row.field_support
                for field in (binding[0],)
            ),
        )
    elif forged_field == "claim_status":
        forged_row = replace(row, claim_status=ClaimStatus.CONFLICT)
    elif forged_field == "review_status":
        forged_row = replace(row, review_status=ReviewStatus.IN_REVIEW)
    elif forged_field == "publication_status":
        forged_row = replace(row, publication_status=PublicationStatus.PUBLISHED)
    else:
        forged_row = replace(row, record_version=99)

    forged_after_hash = "sha256:" + sha256(encode_json(forged_row).encode("utf-8")).hexdigest()
    forged = replace(
        prepared,
        next_row=forged_row,
        audit=replace(prepared.audit, after_hash=forged_after_hash),
    )
    with pytest.raises(ReviewError) as captured_error:
        seeded_review_repository.commit_review_decision(forged)

    assert captured_error.value.code == "FMEA_REVIEW_REQUEST_INVALID"
    assert seeded_review_repository.get_row("row-1", "ws-1").record_version == 1
    assert sqlite_review_counts(seeded_review_repository, "review_decisions", "row-1") == 0
    assert sqlite_review_counts(seeded_review_repository, "audit_events", "row-1", command="review.decision") == 0
    assert sqlite_review_counts(seeded_review_repository, "idempotency_records", "row-1") == 0


def test_tampered_completed_response_is_unavailable_without_new_writes(
    sqlite_review_service,
    seeded_review_repository,
    sqlite_review_counts,
    fixture_human_reviewer,
    fixture_decision_command,
) -> None:
    first = sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)
    connection = seeded_review_repository._connect()
    try:
        stored = connection.execute("SELECT response_json FROM idempotency_records").fetchone()
        assert stored is not None
        payload = json.loads(stored["response_json"])
        payload["row"]["controls"] = ["tampered control"]
        payload["review_status"] = "rejected"
        payload["evidence_requests"] = [
            {
                "target_field": "controls",
                "question": "tampered request",
                "preferred_source_types": ["primary_document"],
                "priority": "normal",
            }
        ]
        payload["request_id"] = "tampered-request"
        connection.execute("UPDATE idempotency_records SET response_json = ?", (encode_review_json(payload),))
    finally:
        connection.close()

    with pytest.raises(ReviewError) as captured:
        sqlite_review_service.submit_decision(fixture_decision_command, fixture_human_reviewer)

    assert captured.value.code == "FMEA_REVIEW_STORAGE_UNAVAILABLE"
    assert first.row.record_version == 2
    assert seeded_review_repository.get_row("row-1", "ws-1").record_version == 2
    assert sqlite_review_counts(seeded_review_repository, "review_decisions", "row-1") == 1
    assert sqlite_review_counts(seeded_review_repository, "audit_events", "row-1", command="review.decision") == 1
    assert sqlite_review_counts(seeded_review_repository, "idempotency_records", "row-1") == 1


def test_chinese_decision_result_replays_byte_exactly(
    sqlite_review_service,
    seeded_review_repository,
    fixture_human_reviewer,
    fixture_decision_command,
    fixture_review_edit,
) -> None:
    command = replace(
        fixture_decision_command,
        action=ReviewAction.MODIFY_AND_ACCEPT,
        reason_code=ReviewReasonCode.FIELD_CORRECTION,
        edits=(replace(fixture_review_edit, value=("启动压力检查",)),),
    )
    first = sqlite_review_service.submit_decision(command, fixture_human_reviewer)
    connection = seeded_review_repository._connect()
    try:
        response_before = connection.execute("SELECT response_json FROM idempotency_records").fetchone()[0]
    finally:
        connection.close()

    replay = sqlite_review_service.submit_decision(command, fixture_human_reviewer)

    connection = seeded_review_repository._connect()
    try:
        response_after = connection.execute("SELECT response_json FROM idempotency_records").fetchone()[0]
    finally:
        connection.close()
    assert first == replay
    assert first.row.controls == ("启动压力检查",)
    assert "启动压力检查" in response_before
    assert response_after == response_before
