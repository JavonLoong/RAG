from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields

import pytest

from core_domain.fmea.codec import decode_propagation_edge, encode_json
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.policies import validate_propagation_edge as validate_policy_edge
from core_domain.fmea.propagation import PropagationEdge, PropagationRelation, validate_propagation_edge
from core_domain.fmea.states import (
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
)

EXPECTED_PROPAGATION_FIELDS = (
    "edge_id",
    "analysis_id",
    "source_entity_id",
    "target_entity_id",
    "relation_type",
    "interface_variable",
    "unit",
    "direction",
    "threshold",
    "operating_modes",
    "delay_ms",
    "response_time_ms",
    "fault_tolerance_time_ms",
    "barrier_ids",
    "evidence_pack_id",
    "evidence_ids",
    "evidence_support",
    "claim_status",
    "review_status",
    "publication_status",
    "path_length",
    "is_cyclic",
    "is_unprocessed",
    "is_external",
    "is_terminal",
    "risk_priority",
    "record_version",
)


def edge(**changes: object) -> PropagationEdge:
    values: dict[str, object] = {
        "edge_id": "edge-1",
        "analysis_id": "analysis-1",
        "source_entity_id": "fuel-filter",
        "target_entity_id": "combustor",
        "relation_type": "propagation",
        "interface_variable": "fuel_pressure",
        "unit": "kPa",
        "direction": "fuel_to_combustion",
        "threshold": "<250",
        "operating_modes": ("startup",),
        "delay_ms": 100,
        "response_time_ms": 200,
        "fault_tolerance_time_ms": 500,
        "barrier_ids": ("trip-1",),
        "evidence_pack_id": "pack-1",
        "evidence_ids": ("ev-1",),
        "evidence_support": EvidenceSupportStatus.SUPPORTED,
        "claim_status": ClaimStatus.KNOWN,
        "review_status": ReviewStatus.SUGGESTED,
        "publication_status": PublicationStatus.UNPUBLISHED,
        "path_length": 2,
        "is_cyclic": False,
        "is_unprocessed": False,
        "is_external": False,
        "is_terminal": False,
        "risk_priority": "normal",
    }
    values.update(changes)
    return PropagationEdge(**values)


def test_propagation_relation_values_are_closed() -> None:
    assert [item.value for item in PropagationRelation] == [
        "propagation",
        "common_cause",
        "dependency",
        "feedback",
    ]


@pytest.mark.parametrize("path_length", (1, 2))
def test_at_most_two_hops_can_be_auto_accepted(path_length: int) -> None:
    current = edge(path_length=path_length)
    assert current.inferred is False
    assert current.auto_accept_allowed is True


@pytest.mark.parametrize("path_length", (0, -1))
def test_non_positive_path_length_is_rejected(path_length: int) -> None:
    with pytest.raises(FmeaDomainError, match="path_length"):
        validate_propagation_edge(edge(path_length=path_length), None)


@pytest.mark.parametrize(
    "claim_status",
    (
        ClaimStatus.UNKNOWN,
        ClaimStatus.INSUFFICIENT_EVIDENCE,
        ClaimStatus.CONFLICT,
        ClaimStatus.NOT_APPLICABLE,
    ),
)
def test_only_known_claims_can_be_auto_accepted(claim_status: ClaimStatus) -> None:
    assert edge(claim_status=claim_status).auto_accept_allowed is False


@pytest.mark.parametrize("risk_priority", (None, "high", "critical", "urgent"))
def test_missing_high_or_unknown_risk_requires_review(risk_priority: str | None) -> None:
    assert edge(risk_priority=risk_priority).auto_accept_allowed is False


def test_unknown_risk_priority_is_rejected_by_validation() -> None:
    with pytest.raises(FmeaDomainError, match="risk_priority"):
        validate_propagation_edge(edge(risk_priority="urgent"), None)


def test_more_than_two_hops_is_inferred_and_requires_review() -> None:
    current = edge(path_length=3)
    assert current.inferred is True
    assert current.auto_accept_allowed is False


@pytest.mark.parametrize(
    "flag",
    ("is_cyclic", "is_unprocessed", "is_external"),
)
def test_cyclic_unprocessed_or_external_edges_require_review(flag: str) -> None:
    current = edge(**{flag: True})
    assert current.auto_accept_allowed is False


def test_terminal_flag_is_retained_without_changing_the_two_hop_policy() -> None:
    current = edge(is_terminal=True)
    assert current.is_terminal is True
    assert current.auto_accept_allowed is True


@pytest.mark.parametrize(
    "changes",
    [
        {"risk_priority": "high"},
        {"risk_priority": "critical"},
        {"evidence_ids": ()},
        {"evidence_support": EvidenceSupportStatus.CONTRADICTED},
        {"evidence_support": EvidenceSupportStatus.NOT_SUPPORTED},
        {"claim_status": ClaimStatus.CONFLICT},
    ],
)
def test_uncertain_or_high_risk_edges_require_human_review(changes: dict[str, object]) -> None:
    assert edge(**changes).auto_accept_allowed is False


def test_propagation_edge_is_frozen_slotted_and_keeps_field_order() -> None:
    assert hasattr(PropagationEdge, "__slots__")
    assert tuple(field.name for field in fields(PropagationEdge)) == EXPECTED_PROPAGATION_FIELDS
    current = edge()
    with pytest.raises(FrozenInstanceError):
        current.edge_id = "changed"


def test_edge_validation_binds_current_pack_and_evidence_ids(fixture_pack) -> None:
    validate_propagation_edge(edge(), fixture_pack)

    with pytest.raises(FmeaDomainError, match="evidence_pack_id"):
        validate_propagation_edge(edge(evidence_pack_id="other-pack"), fixture_pack)

    with pytest.raises(FmeaDomainError, match="EvidencePack"):
        validate_propagation_edge(edge(evidence_ids=("missing-id",)), fixture_pack)


def test_edge_validation_without_pack_still_checks_intrinsic_fields() -> None:
    validate_propagation_edge(edge(), None)


def test_policy_module_exposes_the_same_edge_validation_contract(fixture_pack) -> None:
    validate_policy_edge(edge(), fixture_pack)


def test_long_edge_validation_retains_source_statuses(fixture_pack) -> None:
    current = edge(path_length=3, review_status=ReviewStatus.SUGGESTED)
    validate_propagation_edge(current, fixture_pack)
    assert current.review_status is ReviewStatus.SUGGESTED
    assert current.publication_status is PublicationStatus.UNPUBLISHED


def test_edge_rejects_unknown_relation_type() -> None:
    with pytest.raises(FmeaDomainError, match="relation_type"):
        validate_propagation_edge(edge(relation_type="invented"), None)


def test_codec_round_trips_propagation_edge_canonically() -> None:
    current = edge()
    payload = encode_json(current)
    decoded = decode_propagation_edge(payload)

    assert decoded == current
    assert payload == encode_json(decoded)
    assert json.loads(payload)["evidence_support"] == "supported"
    assert json.loads(payload)["operating_modes"] == ["startup"]
    assert decoded.claim_status is ClaimStatus.KNOWN
    assert decoded.evidence_support is EvidenceSupportStatus.SUPPORTED
    assert tuple(field.name for field in fields(PropagationEdge)) == EXPECTED_PROPAGATION_FIELDS
