from dataclasses import FrozenInstanceError, replace

import pytest
from fmea_review_fixtures import make_review_source, make_start_suggestion_command

from core_domain.fmea.states import ActorType, ClaimStatus, EvidenceSupportStatus
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from fmea_application.review_contracts import (
    EDITABLE_REVIEW_FIELDS,
    ActorContext,
    AuditEvent,
    FieldReviewEdit,
    IdempotencyScope,
    RetrievalProvenance,
    ReviewAction,
    ReviewEvidenceProjection,
    ReviewReasonCode,
    ReviewSourceSnapshot,
    canonical_payload_hash,
    idempotency_key_hash,
)


def _source_kwargs() -> dict[str, object]:
    return {
        "row_id": "row-1",
        "source_record_version": 1,
        "candidate_id": "candidate-1",
        "item_label": "filter",
        "function_label": "remove particles",
        "template_id": "fuel-combustion-fmea-full",
        "template_version": "1.0.0",
        "profile_id": "fuel-combustion-fmea-row",
        "profile_version": "1.0.0",
        "generation_run_id": "generation-1",
        "requested_evidence_profile": EvidenceSelectionProfile.AUTO,
        "resolved_evidence_profile": EvidenceSelectionProfile.COMBINED,
        "evidence_types": tuple(CitationType),
        "trace_id": "trace-1",
        "retrieval_warnings": (),
        "retrieval_incomplete": False,
        "field_claim_statuses": (("failure_mode", ClaimStatus.KNOWN),),
    }


def _build_source(**overrides: object) -> ReviewSourceSnapshot:
    values = _source_kwargs()
    values.update(overrides)
    return ReviewSourceSnapshot.build(**values)  # type: ignore[arg-type]


def test_review_contracts_are_frozen_and_use_exact_field_allowlist() -> None:
    actor = ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1")
    assert frozenset({
        "failure_mode", "causes", "mechanisms", "effects",
        "symptoms", "controls", "barriers", "actions",
    }) == EDITABLE_REVIEW_FIELDS
    with pytest.raises(FrozenInstanceError):
        actor.actor_id = "changed"


def test_field_edit_rejects_identity_and_known_without_supported_evidence() -> None:
    with pytest.raises(ValueError, match="target_field"):
        FieldReviewEdit(
            target_field="item_id", operation="replace", value="changed",
            claim_status=ClaimStatus.KNOWN,
            support_status=EvidenceSupportStatus.SUPPORTED,
            evidence_ids=("ev-1",), reason="not allowed",
        )
    with pytest.raises(ValueError, match="known"):
        FieldReviewEdit(
            target_field="controls", operation="replace", value=("check",),
            claim_status=ClaimStatus.KNOWN,
            support_status=EvidenceSupportStatus.NOT_SUPPORTED,
            evidence_ids=(), reason="unsupported",
        )


def test_source_snapshot_keeps_requested_and_resolved_profiles() -> None:
    snapshot = _build_source()
    assert snapshot.source_hash.startswith("sha256:")
    assert snapshot.resolved_evidence_profile is EvidenceSelectionProfile.COMBINED


def test_source_snapshot_rejects_auto_as_resolved_profile() -> None:
    with pytest.raises(ValueError, match="resolved_evidence_profile cannot be AUTO"):
        _build_source(resolved_evidence_profile=EvidenceSelectionProfile.AUTO)


@pytest.mark.parametrize("invalid_hash", ("f" * 64, "sha256:" + "F" * 64))
def test_pack_and_audit_hashes_require_prefixed_sha256(invalid_hash, fixture_versions) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ReviewEvidenceProjection("pack-1", invalid_hash, None, ())

    with pytest.raises(ValueError, match="SHA-256"):
        AuditEvent(
            event_id="event-1",
            occurred_at_server="2026-08-23T00:00:00Z",
            workspace_id="ws-1",
            actor_id="reviewer-1",
            actor_type=ActorType.HUMAN,
            actor_roles=("reviewer",),
            command="review.decision",
            action=ReviewAction.ACCEPT,
            reason_code=ReviewReasonCode.ACCEPT_AS_IS,
            reason="accepted",
            analysis_id="analysis-1",
            row_id="row-1",
            suggestion_id=None,
            decision_id=None,
            expected_record_version=1,
            applied_record_version=2,
            before_hash=invalid_hash,
            after_hash="sha256:" + "a" * 64,
            changed_fields=(),
            evidence_ids=(),
            evidence_request_targets=(),
            idempotency_key_hash="sha256:" + "b" * 64,
            canonical_payload_hash="sha256:" + "c" * 64,
            versions=fixture_versions,
            template_id="fmea-row-review",
            template_version="1.0.0",
            profile_id="fuel-combustion-fmea-row",
            profile_version="1.0.0",
            model_manifest=None,
            request_id="request-1",
            trace_id="trace-1",
            retrieval_trace_id="retrieval-1",
        )


def test_source_fixture_recomputes_hash_when_content_is_overridden() -> None:
    original = make_review_source()
    changed = make_review_source(field_claim_statuses=(("failure_mode", ClaimStatus.UNKNOWN),))
    assert changed.field_claim_statuses != original.field_claim_statuses
    assert changed.source_hash != original.source_hash


def test_idempotency_hash_rejects_whitespace_wrapped_raw_uuid() -> None:
    key = "00000000-0000-4000-8000-000000000001"
    with pytest.raises(ValueError, match="canonical lowercase UUID"):
        make_start_suggestion_command(idempotency_key=f" {key} ")
    with pytest.raises(ValueError, match="canonical lowercase UUID"):
        idempotency_key_hash(f" {key} ")


def test_custom_legacy_projection_requires_warning_and_can_be_empty() -> None:
    projection = RetrievalProvenance(
        requested_profile=EvidenceSelectionProfile.CUSTOM,
        resolved_profile=EvidenceSelectionProfile.CUSTOM,
        evidence_types=(),
        trace_id="trace-legacy",
        warnings=("legacy projection has no evidence types",),
        incomplete=True,
    )
    assert projection.evidence_types == ()
    with pytest.raises(ValueError, match="unique evidence_types"):
        RetrievalProvenance(
            requested_profile=EvidenceSelectionProfile.CUSTOM,
            resolved_profile=EvidenceSelectionProfile.CUSTOM,
            evidence_types=(),
            trace_id="trace-legacy",
            warnings=(),
            incomplete=True,
        )


def test_timestamp_validation_rejects_naive_and_non_utc_values() -> None:
    for timestamp in ("2026-08-23T00:00:00", "2026-08-23T08:00:00+08:00"):
        with pytest.raises(ValueError, match="timezone-aware UTC"):
            ReviewEvidenceProjection("pack-1", "sha256:" + "f" * 64, timestamp, ())


def test_canonical_payload_and_scope_hashes_are_deterministic() -> None:
    first = make_start_suggestion_command()
    same_payload_different_key = replace(
        first,
        idempotency_key="00000000-0000-4000-8000-000000000002",
    )
    changed_version = replace(first, expected_record_version=2)
    assert canonical_payload_hash(first) == canonical_payload_hash(same_payload_different_key)
    assert canonical_payload_hash(first) != canonical_payload_hash(changed_version)

    key_hash = idempotency_key_hash(first.idempotency_key)
    scope = IdempotencyScope("ws-1", "reviewer-1", "review.suggestion.start", "/rows/row-1", key_hash)
    same_scope = IdempotencyScope("ws-1", "reviewer-1", "review.suggestion.start", "/rows/row-1", key_hash)
    different_scope = IdempotencyScope("ws-1", "reviewer-2", "review.suggestion.start", "/rows/row-1", key_hash)
    assert scope.scope_key == same_scope.scope_key
    assert scope.scope_key != different_scope.scope_key
