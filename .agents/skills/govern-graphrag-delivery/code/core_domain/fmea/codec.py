from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import cast

from .entities import FmeaAnalysis, FmeaRow
from .errors import FmeaDomainError
from .policies import validate_propagation_edge
from .propagation import PropagationEdge
from .scoring import RiskAssessment
from .states import ClaimStatus, EvidenceSupportStatus, PublicationStatus, ReviewStatus
from .value_objects import EvidencePack, EvidenceRef, VersionSet


def _encode(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        encoded: dict[str, object] = {}
        for field in fields(value):
            field_value = getattr(value, field.name)
            if field.name in {"extension_values", "field_claims"} and field_value == ():
                continue
            if (
                field.name == "parent_pack_refs"
                and field_value == ()
                and getattr(value, "lineage_reason", None) is None
                and getattr(value, "lineage_schema_version", None) is None
            ):
                continue
            if field.name in {"lineage_reason", "lineage_schema_version"} and getattr(value, "parent_pack_refs", ()) == ():
                continue
            encoded[field.name] = _encode(field_value)
        return encoded
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    return value


def encode_json(value: object) -> str:
    return json.dumps(_encode(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _object_payload(payload: object, type_name: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise FmeaDomainError(f"{type_name} payload must be an object")  # noqa: TRY003
    return cast(dict[str, object], payload)


def _array_payload(payload: object, field_name: str) -> list[object]:
    if not isinstance(payload, list):
        raise FmeaDomainError(f"{field_name} payload must be an array")  # noqa: TRY003
    return payload


def _tuple_strings(payload: object, field_name: str) -> tuple[str, ...]:
    return tuple(cast(str, item) for item in _array_payload(payload, field_name))


def _decode_versions(payload: object) -> VersionSet:
    return VersionSet(**_object_payload(payload, "VersionSet"))


def _decode_evidence_ref(payload: object) -> EvidenceRef:
    data = _object_payload(payload, "EvidenceRef")
    data["acl_scope"] = _tuple_strings(data["acl_scope"], "acl_scope")
    return EvidenceRef(**data)


def _decode_evidence_pack_payload(payload: object) -> EvidencePack:
    data = _object_payload(payload, "EvidencePack")
    refs = tuple(_decode_evidence_ref(item) for item in _array_payload(data["refs"], "refs"))
    raw_parent_refs = data.get("parent_pack_refs", [])
    parent_refs_list = _array_payload(raw_parent_refs, "parent_pack_refs")
    parent_refs: list[tuple[str, str]] = []
    for item in parent_refs_list:
        if not isinstance(item, list) or len(item) != 2:
            raise FmeaDomainError(  # noqa: TRY003
                "parent_pack_refs entries must be length-2 lists"
            )
        pair = cast(list[object], item)
        parent_refs.append((cast(str, pair[0]), cast(str, pair[1])))
    result = EvidencePack.build(
        pack_id=cast(str, data["pack_id"]),
        workspace_id=cast(str, data["workspace_id"]),
        acl_scope=_tuple_strings(data["acl_scope"], "acl_scope"),
        versions=_decode_versions(data["versions"]),
        refs=refs,
        created_at=cast(str, data["created_at"]),
        expires_at=cast(str | None, data["expires_at"]),
        parent_pack_refs=tuple(parent_refs),
        lineage_reason=cast(str | None, data.get("lineage_reason")),
        lineage_schema_version=cast(str | None, data.get("lineage_schema_version")),
    )
    if data.get("pack_hash") != result.pack_hash:
        raise FmeaDomainError("EvidencePack pack_hash does not match contents")  # noqa: TRY003
    return result


def _decode_analysis_payload(payload: object) -> FmeaAnalysis:
    data = _object_payload(payload, "FmeaAnalysis")
    for field_name in (
        "exclusions",
        "operating_modes",
        "assumptions",
        "limitations",
        "unanalysed_parts",
        "reviewer_actor_ids",
    ):
        data[field_name] = _tuple_strings(data[field_name], field_name)
    data["versions"] = _decode_versions(data["versions"])
    return FmeaAnalysis(**data)


def _decode_risk_assessment(payload: object) -> RiskAssessment | None:
    if payload is None:
        return None

    data = _object_payload(payload, "RiskAssessment")
    severity_pairs = _array_payload(data["severity_by_consequence_class"], "severity_by_consequence_class")
    data["severity_by_consequence_class"] = tuple(
        (cast(str, pair[0]), cast(int | None, pair[1]))
        for pair in (cast(list[object], item) for item in severity_pairs)
    )
    data["evidence_ids"] = _tuple_strings(data["evidence_ids"], "evidence_ids")
    return RiskAssessment(**data)


def _decode_row_payload(payload: object) -> FmeaRow:
    data = _object_payload(payload, "FmeaRow")
    for field_name in ("causes", "mechanisms", "effects", "symptoms", "controls", "barriers", "actions"):
        data[field_name] = _tuple_strings(data[field_name], field_name)

    field_evidence = _array_payload(data["field_evidence"], "field_evidence")
    data["field_evidence"] = tuple(
        (cast(str, pair[0]), _tuple_strings(pair[1], "field_evidence"))
        for pair in (cast(list[object], item) for item in field_evidence)
    )
    field_support = _array_payload(data["field_support"], "field_support")
    data["field_support"] = tuple(
        (cast(str, pair[0]), EvidenceSupportStatus(cast(str, pair[1])))
        for pair in (cast(list[object], item) for item in field_support)
    )
    data["risk_assessment"] = _decode_risk_assessment(data["risk_assessment"])
    raw_extensions = data.get("extension_values", [])
    data["extension_values"] = tuple(
        _decode_field_value(item)
        for item in _array_payload(raw_extensions, "extension_values")
    )
    raw_claims = data.get("field_claims", [])
    data["field_claims"] = tuple(
        _decode_field_claim(item)
        for item in _array_payload(raw_claims, "field_claims")
    )
    data["claim_status"] = ClaimStatus(cast(str, data["claim_status"]))
    data["review_status"] = ReviewStatus(cast(str, data["review_status"]))
    data["publication_status"] = PublicationStatus(cast(str, data["publication_status"]))
    return FmeaRow(**data)


def _decode_field_value(payload: object):
    from .entities import FieldValue

    data = _object_payload(payload, "FieldValue")
    return FieldValue(
        field_key=cast(str, data["field_key"]),
        value_type=cast(str, data["value_type"]),
        value=data["value"],
    )


def _decode_field_claim(payload: object):
    from .entities import FieldClaim

    data = _object_payload(payload, "FieldClaim")
    return FieldClaim(
        field_key=cast(str, data["field_key"]),
        claim_status=ClaimStatus(cast(str, data["claim_status"])),
        support_status=EvidenceSupportStatus(cast(str, data["support_status"])),
        evidence_ids=_tuple_strings(data["evidence_ids"], "field_claim evidence_ids"),
        uncertainty=cast(str | None, data["uncertainty"]),
        conflict_ids=_tuple_strings(data["conflict_ids"], "field_claim conflict_ids"),
    )


def _decode_propagation_edge_payload(payload: object) -> PropagationEdge:
    data = _object_payload(payload, "PropagationEdge")
    for field_name in ("operating_modes", "barrier_ids", "evidence_ids"):
        data[field_name] = _tuple_strings(data[field_name], field_name)
    data["evidence_support"] = EvidenceSupportStatus(cast(str, data["evidence_support"]))
    data["claim_status"] = ClaimStatus(cast(str, data["claim_status"]))
    data["review_status"] = ReviewStatus(cast(str, data["review_status"]))
    data["publication_status"] = PublicationStatus(cast(str, data["publication_status"]))
    result = PropagationEdge(**data)
    validate_propagation_edge(result, None)
    return result


def decode_analysis(payload: str) -> FmeaAnalysis:
    return _decode_analysis_payload(json.loads(payload))


def decode_row(payload: str) -> FmeaRow:
    return _decode_row_payload(json.loads(payload))


def decode_evidence_pack(payload: str) -> EvidencePack:
    return _decode_evidence_pack_payload(json.loads(payload))


def decode_propagation_edge(payload: str) -> PropagationEdge:
    return _decode_propagation_edge_payload(json.loads(payload))
