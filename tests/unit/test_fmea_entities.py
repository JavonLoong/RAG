from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from core_domain.fmea.codec import decode_analysis, decode_evidence_pack, decode_row, encode_json
from core_domain.fmea.entities import FieldClaim, FieldValue, FmeaAnalysis, FmeaRow, validate_extension_values
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
from fmea_application.review_contracts import ReviewDecisionResult, encode_review_json


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
    row_field_names = tuple(field.name for field in fields(FmeaRow))
    assert row_field_names[-3:] == ("record_version", "extension_values", "field_claims")
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


def test_typed_extensions_round_trip(fixture_row) -> None:
    row = replace(
        fixture_row,
        extension_values=(FieldValue("gas_turbine.fuel.wobbe_index", "decimal", "48.2"),),
    )
    validate_extension_values(row, {"extension_fields": {"gas_turbine.fuel.wobbe_index": "decimal"}})
    assert decode_row(encode_json(row)) == row


@pytest.mark.parametrize("value", (["48"], [{"value": 48}], [[48]]))
def test_integer_array_rejects_non_integer_elements(value) -> None:
    with pytest.raises(FmeaDomainError, match="field value"):
        FieldValue("gas_turbine.fuel.pressure_steps", "integer[]", value)


def test_field_value_snapshots_mutable_list_as_tuple() -> None:
    raw_values = [1, 2]
    field_value = FieldValue("gas_turbine.fuel.pressure_steps", "integer[]", raw_values)

    raw_values[0] = 99
    raw_values.append(3)

    assert field_value.value == (1, 2)
    assert isinstance(field_value.value, tuple)


@pytest.mark.parametrize(
    ("value_type", "value"),
    (("object", "not-allowed"), ("number", float("nan")), ("float", float("inf")), ("decimal", float("-inf"))),
)
def test_field_value_rejects_unknown_or_non_finite_types(value_type, value) -> None:
    with pytest.raises(FmeaDomainError, match="value_type|field value"):
        FieldValue("gas_turbine.fuel.pressure_steps", value_type, value)


@pytest.mark.parametrize(
    "claim",
    (
        FieldClaim("failure_mode", ClaimStatus.KNOWN, EvidenceSupportStatus.SUPPORTED, ("missing-id",)),
        FieldClaim("failure_mode", ClaimStatus.KNOWN, EvidenceSupportStatus.PARTIALLY_SUPPORTED, ("ev-1",)),
        FieldClaim("failure_mode", ClaimStatus.UNKNOWN, EvidenceSupportStatus.SUPPORTED, ()),
    ),
)
def test_canonical_field_claim_must_match_legacy_bindings_and_row_status(fixture_pack, fixture_row, claim) -> None:
    row = replace(fixture_row, field_claims=(claim,))

    with pytest.raises(FmeaDomainError, match="field claim"):
        validate_row_evidence(row, fixture_pack)


def test_matching_canonical_field_claim_is_accepted(fixture_pack, fixture_row) -> None:
    claim = FieldClaim("failure_mode", ClaimStatus.KNOWN, EvidenceSupportStatus.SUPPORTED, ("ev-1",))
    validate_row_evidence(replace(fixture_row, field_claims=(claim,)), fixture_pack)


def test_extension_field_claim_requires_an_extension_value(fixture_pack, fixture_row) -> None:
    claim = FieldClaim(
        "gas_turbine.fuel.wobbe_index",
        ClaimStatus.KNOWN,
        EvidenceSupportStatus.SUPPORTED,
        ("ev-1",),
    )

    with pytest.raises(FmeaDomainError, match="extension value"):
        validate_row_evidence(replace(fixture_row, field_claims=(claim,)), fixture_pack)


def test_extension_field_claim_evidence_must_belong_to_pack(fixture_pack, fixture_row) -> None:
    extension_value = FieldValue("gas_turbine.fuel.wobbe_index", "decimal", "48.2")
    claim = FieldClaim(
        "gas_turbine.fuel.wobbe_index",
        ClaimStatus.KNOWN,
        EvidenceSupportStatus.SUPPORTED,
        ("missing-id",),
    )
    row = replace(fixture_row, extension_values=(extension_value,), field_claims=(claim,))

    with pytest.raises(FmeaDomainError, match="EvidencePack"):
        validate_row_evidence(row, fixture_pack)


def test_legacy_row_json_keeps_old_canonical_bytes(fixture_row) -> None:
    payload = json.loads(encode_json(fixture_row))
    payload.pop("extension_values", None)
    payload.pop("field_claims", None)
    legacy_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert encode_json(decode_row(legacy_json)) == legacy_json


def test_review_result_serializer_omits_empty_new_row_fields(fixture_row) -> None:
    result = ReviewDecisionResult(
        decision_id="decision-1",
        row=fixture_row,
        previous_record_version=1,
        record_version=2,
        review_status=ReviewStatus.ACCEPTED,
        publication_status=PublicationStatus.UNPUBLISHED,
        audit_event_id="audit-1",
        suggestion_id=None,
        evidence_requests=(),
        persisted=True,
        request_id="request-1",
        trace_id="trace-1",
    )
    row_payload = json.loads(encode_review_json(result))["row"]
    assert "extension_values" not in row_payload
    assert "field_claims" not in row_payload


def test_codec_is_canonical_and_rejects_nan() -> None:
    assert encode_json({"b": (2, 3), "a": 1}) == '{"a":1,"b":[2,3]}'
    with pytest.raises(ValueError):
        encode_json(float("nan"))
