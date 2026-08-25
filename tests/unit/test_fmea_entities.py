from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from core_domain.fmea.codec import decode_analysis, decode_evidence_pack, decode_row, encode_json
from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.policies import (
    validate_publication_transition,
    validate_review_transition,
    validate_row_evidence,
)
from core_domain.fmea.scoring import RiskAssessment
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
)


def test_known_row_requires_current_pack_evidence(fixture_pack, fixture_row) -> None:
    validate_row_evidence(fixture_row, fixture_pack)
    missing = replace(fixture_row, field_evidence=(), field_support=())
    with pytest.raises(FmeaDomainError, match="known claim requires evidence"):
        validate_row_evidence(missing, fixture_pack)


def test_unknown_and_not_applicable_remain_distinct_without_evidence(fixture_pack, fixture_row) -> None:
    for status in (ClaimStatus.UNKNOWN, ClaimStatus.INSUFFICIENT_EVIDENCE, ClaimStatus.NOT_APPLICABLE):
        row = replace(fixture_row, claim_status=status, field_evidence=(), field_support=())
        validate_row_evidence(row, fixture_pack)
    assert ClaimStatus.NOT_APPLICABLE is not ClaimStatus.UNKNOWN


def test_model_cannot_accept_or_publish() -> None:
    with pytest.raises(FmeaDomainError, match="human actor"):
        validate_review_transition(
            current=ReviewStatus.IN_REVIEW,
            requested=ReviewStatus.ACCEPTED,
            actor_type=ActorType.MODEL,
        )
    with pytest.raises(FmeaDomainError, match="human actor"):
        validate_publication_transition(
            current=PublicationStatus.UNPUBLISHED,
            requested=PublicationStatus.PUBLISHED,
            actor_type=ActorType.MODEL,
        )


@pytest.mark.parametrize("requested", (ReviewStatus.IN_REVIEW, ReviewStatus.REJECTED))
def test_model_cannot_make_any_review_decision(requested: ReviewStatus) -> None:
    with pytest.raises(FmeaDomainError, match="human actor"):
        validate_review_transition(
            current=ReviewStatus.SUGGESTED,
            requested=requested,
            actor_type=ActorType.MODEL,
        )


def test_review_policy_allows_audited_in_review_self_event_but_not_rejected_reopen() -> None:
    validate_review_transition(
        current=ReviewStatus.IN_REVIEW,
        requested=ReviewStatus.IN_REVIEW,
        actor_type=ActorType.HUMAN,
    )
    with pytest.raises(FmeaDomainError, match="invalid review transition"):
        validate_review_transition(
            current=ReviewStatus.REJECTED,
            requested=ReviewStatus.DRAFT,
            actor_type=ActorType.HUMAN,
        )


def test_human_can_accept_and_publish() -> None:
    validate_review_transition(
        current=ReviewStatus.IN_REVIEW,
        requested=ReviewStatus.ACCEPTED,
        actor_type=ActorType.HUMAN,
    )
    validate_publication_transition(
        current=PublicationStatus.UNPUBLISHED,
        requested=PublicationStatus.PUBLISHED,
        actor_type=ActorType.HUMAN,
    )


def test_invalid_evidence_id_is_rejected(fixture_pack, fixture_row) -> None:
    row = replace(fixture_row, field_evidence=(("failure_mode", ("missing-id",)),))
    with pytest.raises(FmeaDomainError, match="EvidencePack"):
        validate_row_evidence(row, fixture_pack)


def test_row_evidence_rejects_unknown_and_duplicate_fields(fixture_pack, fixture_row) -> None:
    unknown = replace(
        fixture_row,
        field_evidence=(("unknown_field", ("ev-1",)),),
        field_support=(("unknown_field", EvidenceSupportStatus.SUPPORTED),),
    )
    with pytest.raises(FmeaDomainError, match="unknown field"):
        validate_row_evidence(unknown, fixture_pack)

    duplicate = replace(
        fixture_row,
        field_evidence=(("failure_mode", ("ev-1",)), ("failure_mode", ("ev-1",))),
        field_support=(("failure_mode", EvidenceSupportStatus.SUPPORTED),),
    )
    with pytest.raises(FmeaDomainError, match="duplicate field"):
        validate_row_evidence(duplicate, fixture_pack)


def test_row_evidence_requires_matching_support_bindings(fixture_pack, fixture_row) -> None:
    missing_support = replace(fixture_row, field_support=())
    with pytest.raises(FmeaDomainError, match="field_support"):
        validate_row_evidence(missing_support, fixture_pack)

    support_without_evidence = replace(
        fixture_row,
        field_evidence=(),
        field_support=(("failure_mode", EvidenceSupportStatus.SUPPORTED),),
        claim_status=ClaimStatus.UNKNOWN,
    )
    with pytest.raises(FmeaDomainError, match="field_support"):
        validate_row_evidence(support_without_evidence, fixture_pack)


@pytest.mark.parametrize(
    "support_status",
    (EvidenceSupportStatus.CONTRADICTED, EvidenceSupportStatus.NOT_SUPPORTED),
)
def test_known_row_rejects_contradicted_or_not_supported_bindings(fixture_pack, fixture_row, support_status) -> None:
    row = replace(fixture_row, field_support=(("failure_mode", support_status),))
    with pytest.raises(FmeaDomainError, match="known claim"):
        validate_row_evidence(row, fixture_pack)


def test_row_evidence_requires_the_current_pack(fixture_pack, fixture_row) -> None:
    row = replace(fixture_row, evidence_pack_id="other-pack")
    with pytest.raises(FmeaDomainError, match="EvidencePack"):
        validate_row_evidence(row, fixture_pack)


def test_entities_are_frozen_and_slotted(fixture_analysis, fixture_row) -> None:
    assert hasattr(FmeaAnalysis, "__slots__")
    assert hasattr(FmeaRow, "__slots__")
    assert tuple(field.name for field in fields(FmeaAnalysis))[-1] == "record_version"
    assert tuple(field.name for field in fields(FmeaRow))[-1] == "record_version"
    with pytest.raises(FrozenInstanceError):
        fixture_analysis.analysis_id = "changed"
    with pytest.raises(FrozenInstanceError):
        fixture_row.row_id = "changed"


def test_codec_round_trips_analysis_row_and_evidence_pack(fixture_analysis, fixture_pack, fixture_row) -> None:
    analysis_payload = encode_json(fixture_analysis)
    row_payload = encode_json(fixture_row)
    pack_payload = encode_json(fixture_pack)

    assert decode_analysis(analysis_payload) == fixture_analysis
    assert decode_row(row_payload) == fixture_row
    assert decode_evidence_pack(pack_payload) == fixture_pack


def test_codec_round_trips_non_null_risk_assessment(fixture_row) -> None:
    assessment = RiskAssessment(
        severity_by_consequence_class=(("safety", 7), ("asset", 5)),
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
        reason="reviewed operating data",
        scoring_rule_pack_id="gas-turbine-risk",
        scoring_rule_pack_version="1.0.0",
        evidence_ids=("ev-1",),
    )
    row = replace(fixture_row, risk_assessment=assessment)

    assert decode_row(encode_json(row)) == row


def test_codec_is_canonical_and_rejects_nan() -> None:
    assert encode_json({"b": (2, 3), "a": 1}) == '{"a":1,"b":[2,3]}'
    with pytest.raises(ValueError):
        encode_json(float("nan"))
