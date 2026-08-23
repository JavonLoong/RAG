from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import cast

from .entities import FmeaAnalysis, FmeaRow
from .errors import FmeaDomainError
from .scoring import RiskAssessment
from .states import ClaimStatus, EvidenceSupportStatus, PublicationStatus, ReviewStatus
from .value_objects import EvidencePack, EvidenceRef, VersionSet


def _encode(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
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
    result = EvidencePack.build(
        pack_id=cast(str, data["pack_id"]),
        workspace_id=cast(str, data["workspace_id"]),
        acl_scope=_tuple_strings(data["acl_scope"], "acl_scope"),
        versions=_decode_versions(data["versions"]),
        refs=refs,
        created_at=cast(str, data["created_at"]),
        expires_at=cast(str | None, data["expires_at"]),
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
    data["claim_status"] = ClaimStatus(cast(str, data["claim_status"]))
    data["review_status"] = ReviewStatus(cast(str, data["review_status"]))
    data["publication_status"] = PublicationStatus(cast(str, data["publication_status"]))
    return FmeaRow(**data)


def decode_analysis(payload: str) -> FmeaAnalysis:
    return _decode_analysis_payload(json.loads(payload))


def decode_row(payload: str) -> FmeaRow:
    return _decode_row_payload(json.loads(payload))


def decode_evidence_pack(payload: str) -> EvidencePack:
    return _decode_evidence_pack_payload(json.loads(payload))
