from dataclasses import FrozenInstanceError

import pytest

from core_domain.fmea.states import ActorType, ClaimStatus, EvidenceSupportStatus
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from fmea_application.review_contracts import (
    EDITABLE_REVIEW_FIELDS,
    ActorContext,
    FieldReviewEdit,
    ReviewSourceSnapshot,
)


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
    snapshot = ReviewSourceSnapshot.build(
        row_id="row-1", source_record_version=1, candidate_id="candidate-1",
        item_label="filter", function_label="remove particles",
        template_id="fuel-combustion-fmea-full", template_version="1.0.0",
        profile_id="fuel-combustion-fmea-row", profile_version="1.0.0",
        generation_run_id="generation-1",
        requested_evidence_profile=EvidenceSelectionProfile.AUTO,
        resolved_evidence_profile=EvidenceSelectionProfile.COMBINED,
        evidence_types=tuple(CitationType), trace_id="trace-1",
        retrieval_warnings=(), retrieval_incomplete=False,
        field_claim_statuses=(("failure_mode", ClaimStatus.KNOWN),),
    )
    assert snapshot.source_hash.startswith("sha256:")
    assert snapshot.resolved_evidence_profile is EvidenceSelectionProfile.COMBINED
