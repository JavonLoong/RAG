"""Immutable, bounded normalized snapshot contracts for FMEA exports."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Literal, NoReturn

from core_domain.fmea.entities import FieldValue
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.governance import (
    FmeaRevision,
    canonical_hash,
    canonical_json_bytes,
)

_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")
_FORBIDDEN_KEY_PARTS = frozenset({
    "access_token",
    "api_key",
    "authorization",
    "credential",
    "password",
    "private_key",
    "private_path",
    "prompt",
    "provider_output",
    "raw_output",
    "secret",
    "source_url",
    "url",
})
_MAX_DEPTH = 8
_MAX_ITEMS = 500
_MAX_STRING_LENGTH = 65_536
_MAX_CANONICAL_ARRAY_ITEMS = 10_000
DRAFT_PREVIEW_MARKER = "DRAFT PREVIEW — NOT PUBLISHED"
PUBLICATION_BODY_SCHEMA_VERSION = "graphrag.fmea.body.v1"
_PUBLICATION_BODY_REQUIRED_ROW_FIELDS = frozenset(
    {
        "row_id",
        "analysis_id",
        "evidence_pack_id",
        "item_id",
        "function_id",
        "failure_mode",
        "causes",
        "mechanisms",
        "effects",
        "symptoms",
        "controls",
        "barriers",
        "actions",
        "claim_status",
        "review_status",
        "publication_status",
        "record_version",
        "row_hash",
        "risk_assessment",
        "field_evidence",
        "field_support",
        "field_claims",
        "extension_values",
    }
)

_PUBLICATION_BODY_ROW_TEXT_FIELDS = frozenset(
    {
        "row_id",
        "analysis_id",
        "evidence_pack_id",
        "item_id",
        "function_id",
        "failure_mode",
        "claim_status",
        "review_status",
        "publication_status",
    }
)
_PUBLICATION_BODY_ROW_STRING_SEQUENCE_FIELDS = frozenset(
    {"causes", "mechanisms", "effects", "symptoms", "controls", "barriers", "actions"}
)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    return value.strip()


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    if _HASH.fullmatch(normalized) is None:
        raise FmeaDomainError(f"{field_name} must be a lowercase SHA-256 hash")  # noqa: TRY003
    return normalized


def _timestamp(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FmeaDomainError(f"{field_name} must be an ISO-8601 UTC timestamp") from exc  # noqa: TRY003
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise FmeaDomainError(f"{field_name} must be an ISO-8601 UTC timestamp")  # noqa: TRY003
    return normalized


def _reject_unsafe_key(key: str) -> None:
    normalized = key.casefold().replace("-", "_")
    if normalized in _FORBIDDEN_KEY_PARTS or any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
        raise FmeaDomainError("snapshot contains non-export-safe field")  # noqa: TRY003


def _freeze_export_value(value: object, *, depth: int = 0) -> object:  # noqa: C901
    if depth > _MAX_DEPTH:
        raise FmeaDomainError("snapshot exceeds maximum JSON depth")  # noqa: TRY003
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise FmeaDomainError("snapshot numbers must be finite")  # noqa: TRY003
        return value
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            raise FmeaDomainError("snapshot string exceeds maximum length")  # noqa: TRY003
        if _URI_SCHEME.match(value) or _ABSOLUTE_PATH.match(value):
            raise FmeaDomainError("snapshot contains non-export-safe value")  # noqa: TRY003
        return value
    if isinstance(value, Mapping):
        if len(value) > _MAX_ITEMS:
            raise FmeaDomainError("snapshot mapping exceeds maximum size")  # noqa: TRY003
        items: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise FmeaDomainError("snapshot object keys must be non-empty strings")  # noqa: TRY003
            normalized_key = key.strip()
            _reject_unsafe_key(normalized_key)
            if normalized_key in items:
                raise FmeaDomainError("snapshot contains duplicate object keys")  # noqa: TRY003
            items[normalized_key] = _freeze_export_value(item, depth=depth + 1)
        return MappingProxyType(dict(sorted(items.items())))
    if isinstance(value, tuple | list):
        if len(value) > _MAX_ITEMS:
            raise FmeaDomainError("snapshot array exceeds maximum size")  # noqa: TRY003
        return tuple(_freeze_export_value(item, depth=depth + 1) for item in value)
    raise FmeaDomainError("snapshot contains a non-JSON value")  # noqa: TRY003


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FmeaDomainError(f"{field_name} must be a mapping")  # noqa: TRY003
    frozen = _freeze_export_value(value)
    if not isinstance(frozen, Mapping):  # pragma: no cover - _freeze_export_value preserves mappings.
        raise FmeaDomainError(f"{field_name} must be a mapping")  # noqa: TRY003
    return frozen


def _mapping_tuple(
    value: object,
    field_name: str,
    *,
    identity_field: str | None = None,
) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        items = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc  # noqa: TRY003
    normalized = tuple(_mapping(item, field_name) for item in items)
    if identity_field is None:
        return normalized
    identities: list[str] = []
    for item in normalized:
        identity = item.get(identity_field)
        if not isinstance(identity, str) or not identity.strip():
            raise FmeaDomainError(f"{field_name} items must contain {identity_field}")  # noqa: TRY003
        identities.append(identity.strip())
    if len(identities) != len(set(identities)):
        raise FmeaDomainError(f"{field_name} must not contain duplicate identities")  # noqa: TRY003
    return tuple(item for _, item in sorted(zip(identities, normalized, strict=True), key=lambda pair: pair[0]))


def _publication_body_incomplete() -> NoReturn:
    raise FmeaDomainError("publication body is incomplete")  # noqa: TRY003


def _publication_body_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _publication_body_incomplete()
    return value


def _publication_body_sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple | list) or len(value) > _MAX_ITEMS:
        _publication_body_incomplete()
    return tuple(value)


def _publication_body_text(value: object) -> str:
    try:
        return _text(value, "publication body field")
    except FmeaDomainError as exc:
        raise FmeaDomainError("publication body is incomplete") from exc  # noqa: TRY003


def _publication_body_hash(value: object) -> str:
    try:
        return _hash(value, "publication body hash")
    except FmeaDomainError as exc:
        raise FmeaDomainError("publication body is incomplete") from exc  # noqa: TRY003


def _publication_body_positive(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _publication_body_incomplete()
    return value


def _publication_body_strings(value: object) -> tuple[str, ...]:
    values = _publication_body_sequence(value)
    result: list[str] = []
    for item in values:
        result.append(_publication_body_text(item))
    return tuple(result)


def _publication_body_required(item: Mapping[str, object], fields: frozenset[str]) -> None:
    if not fields.issubset(item):
        _publication_body_incomplete()


def _validate_publication_body_row(  # noqa: C901
    row: Mapping[str, object], row_ids: set[str]
) -> tuple[str, set[str]]:
    if not _PUBLICATION_BODY_REQUIRED_ROW_FIELDS.issubset(row):
        _publication_body_incomplete()
    for field_name in _PUBLICATION_BODY_ROW_TEXT_FIELDS:
        _publication_body_text(row[field_name])
    row_id = _publication_body_text(row["row_id"])
    if row_id in row_ids:
        _publication_body_incomplete()
    row_ids.add(row_id)
    _publication_body_positive(row["record_version"])
    _publication_body_hash(row["row_hash"])
    if row["risk_assessment"] is not None:
        _publication_body_mapping(row["risk_assessment"])
    for field_name in _PUBLICATION_BODY_ROW_STRING_SEQUENCE_FIELDS:
        _publication_body_strings(row[field_name])

    evidence_ids: set[str] = set()
    evidence_fields: set[str] = set()
    for item in _publication_body_sequence(row["field_evidence"]):
        binding = _publication_body_mapping(item)
        _publication_body_required(binding, frozenset({"field_key", "evidence_ids"}))
        evidence_fields.add(_publication_body_text(binding["field_key"]))
        evidence_ids.update(_publication_body_strings(binding["evidence_ids"]))
    support_fields: set[str] = set()
    for item in _publication_body_sequence(row["field_support"]):
        binding = _publication_body_mapping(item)
        _publication_body_required(binding, frozenset({"field_key", "support_status"}))
        support_fields.add(_publication_body_text(binding["field_key"]))
        _publication_body_text(binding["support_status"])
    if evidence_fields != support_fields:
        _publication_body_incomplete()
    for item in _publication_body_sequence(row["field_claims"]):
        claim = _publication_body_mapping(item)
        _publication_body_required(
            claim,
            frozenset({"field_key", "claim_status", "support_status", "evidence_ids", "uncertainty", "conflict_ids"}),
        )
        _publication_body_text(claim["field_key"])
        _publication_body_text(claim["claim_status"])
        _publication_body_text(claim["support_status"])
        evidence_ids.update(_publication_body_strings(claim["evidence_ids"]))
        _publication_body_strings(claim["conflict_ids"])
        if claim["uncertainty"] is not None:
            _publication_body_text(claim["uncertainty"])
    for item in _publication_body_sequence(row["extension_values"]):
        extension = _publication_body_mapping(item)
        _publication_body_required(extension, frozenset({"field_key", "value_type", "value"}))
        try:
            FieldValue(extension["field_key"], extension["value_type"], extension["value"])
        except FmeaDomainError as exc:
            raise FmeaDomainError("publication body is incomplete") from exc  # noqa: TRY003
    return _publication_body_text(row["evidence_pack_id"]), evidence_ids


def _validate_publication_body_evidence(
    evidence_summary: tuple[Mapping[str, object], ...], referenced_pack_ids: set[str]
) -> set[str]:
    pack_ids: set[str] = set()
    evidence_ids: set[str] = set()
    evidence_refs_by_id: dict[str, Mapping[str, object]] = {}
    for pack in evidence_summary:
        _publication_body_required(pack, frozenset({"pack_id", "pack_hash", "evidence_pack_version", "refs"}))
        pack_id = _publication_body_text(pack["pack_id"])
        if pack_id in pack_ids:
            _publication_body_incomplete()
        pack_ids.add(pack_id)
        _publication_body_hash(pack["pack_hash"])
        _publication_body_text(pack["evidence_pack_version"])
        pack_evidence_ids: set[str] = set()
        for ref in _publication_body_sequence(pack["refs"]):
            evidence_ref = _publication_body_mapping(ref)
            _publication_body_required(
                evidence_ref,
                frozenset(
                    {
                        "evidence_id",
                        "document_id",
                        "document_version",
                        "content_hash",
                        "evidence_hash",
                        "locator",
                        "quote",
                        "source_type",
                        "source_trust",
                    }
                ),
            )
            evidence_id = _publication_body_text(evidence_ref["evidence_id"])
            if evidence_id in pack_evidence_ids:
                _publication_body_incomplete()
            previous_ref = evidence_refs_by_id.get(evidence_id)
            if previous_ref is not None and previous_ref != evidence_ref:
                _publication_body_incomplete()
            pack_evidence_ids.add(evidence_id)
            evidence_refs_by_id[evidence_id] = evidence_ref
            evidence_ids.add(evidence_id)
            _publication_body_text(evidence_ref["document_id"])
            _publication_body_text(evidence_ref["document_version"])
            _publication_body_hash(evidence_ref["content_hash"])
            _publication_body_hash(evidence_ref["evidence_hash"])
            _publication_body_mapping(evidence_ref["locator"])
            _publication_body_text(evidence_ref["quote"])
            _publication_body_text(evidence_ref["source_type"])
            _publication_body_text(evidence_ref["source_trust"])
    if not referenced_pack_ids.issubset(pack_ids):
        _publication_body_incomplete()
    return evidence_ids


def _validate_publication_body_risks(  # noqa: C901
    risk_records: tuple[Mapping[str, object], ...], rows: Mapping[str, Mapping[str, object]]
) -> tuple[set[str], set[str]]:
    pack_ids: set[str] = set()
    evidence_ids: set[str] = set()
    required = frozenset(
        {
            "assessment_id",
            "assessment_hash",
            "workspace_id",
            "row_id",
            "source_record_version",
            "evidence_pack_id",
            "domain_pack_id",
            "domain_pack_version",
            "rule_pack_id",
            "rule_pack_version",
            "status",
            "dimensions",
            "derived",
            "proposal_id",
            "invalidated_reason",
            "record_version",
            "confirmation_basis",
        }
    )
    for risk in risk_records:
        _publication_body_required(risk, required)
        _publication_body_text(risk["assessment_id"])
        _publication_body_hash(risk["assessment_hash"])
        _publication_body_text(risk["workspace_id"])
        row_id = _publication_body_text(risk["row_id"])
        row = rows.get(row_id)
        if row is None:
            _publication_body_incomplete()
        _publication_body_positive(risk["source_record_version"])
        if risk["source_record_version"] != row["record_version"]:
            _publication_body_incomplete()
        pack_ids.add(_publication_body_text(risk["evidence_pack_id"]))
        for field_name in ("domain_pack_id", "domain_pack_version", "rule_pack_id", "rule_pack_version", "status"):
            _publication_body_text(risk[field_name])
        _publication_body_positive(risk["record_version"])
        for field_name in ("proposal_id", "invalidated_reason"):
            if risk[field_name] is not None:
                _publication_body_text(risk[field_name])
        for dimension in _publication_body_sequence(risk["dimensions"]):
            value = _publication_body_mapping(dimension)
            _publication_body_required(value, frozenset({"name", "value", "evidence_ids", "reason", "uncertainty"}))
            _publication_body_text(value["name"])
            if value["value"] is not None and (
                isinstance(value["value"], bool) or not isinstance(value["value"], int | float)
            ):
                _publication_body_incomplete()
            evidence_ids.update(_publication_body_strings(value["evidence_ids"]))
            _publication_body_text(value["reason"])
            if value["uncertainty"] is not None:
                _publication_body_text(value["uncertainty"])
        if risk["derived"] is not None:
            derived = _publication_body_mapping(risk["derived"])
            if "evidence_ids" not in derived:
                _publication_body_incomplete()
            evidence_ids.update(_publication_body_strings(derived["evidence_ids"]))
        if risk["confirmation_basis"] is not None:
            basis = _publication_body_mapping(risk["confirmation_basis"])
            _publication_body_required(basis, frozenset({"proposal_id"}))
            _publication_body_text(basis["proposal_id"])
            if "confirmer_actor_id" in basis:
                _publication_body_incomplete()
    return pack_ids, evidence_ids


def _validate_publication_body_graph(  # noqa: C901
    propagation: Mapping[str, object] | None,
    row_ids: set[str],
    workspace_id: str,
    analysis_id: str,
) -> tuple[set[str], set[str]]:
    if propagation is None:
        return set(), set()
    _publication_body_required(
        propagation,
        frozenset(
            {
                "graph_revision_id",
                "workspace_id",
                "analysis_id",
                "analysis_record_version",
                "topology_snapshot_id",
                "topology_hash",
                "domain_pack_id",
                "domain_pack_version",
                "rule_pack_id",
                "rule_pack_version",
                "status",
                "record_version",
                "nodes",
                "edges",
                "paths",
                "row_lineage",
            }
        ),
    )
    for field_name in (
        "graph_revision_id",
        "workspace_id",
        "analysis_id",
        "topology_snapshot_id",
        "domain_pack_id",
        "domain_pack_version",
        "rule_pack_id",
        "rule_pack_version",
        "status",
    ):
        _publication_body_text(propagation[field_name])
    if propagation["workspace_id"] != workspace_id or propagation["analysis_id"] != analysis_id:
        _publication_body_incomplete()
    _publication_body_hash(propagation["topology_hash"])
    _publication_body_positive(propagation["analysis_record_version"])
    _publication_body_positive(propagation["record_version"])
    for node in _publication_body_sequence(propagation["nodes"]):
        value = _publication_body_mapping(node)
        _publication_body_required(value, frozenset({"node_id", "node_type", "operating_modes"}))
        _publication_body_text(value["node_id"])
        _publication_body_text(value["node_type"])
        _publication_body_strings(value["operating_modes"])

    edge_ids: set[str] = set()
    pack_ids: set[str] = set()
    evidence_ids: set[str] = set()
    edge_required = frozenset(
        {
            "edge_id",
            "analysis_id",
            "source_entity_id",
            "target_entity_id",
            "evidence_pack_id",
            "evidence_ids",
            "review_status",
            "publication_status",
            "record_version",
        }
    )
    for edge in _publication_body_sequence(propagation["edges"]):
        value = _publication_body_mapping(edge)
        _publication_body_required(value, edge_required)
        edge_id = _publication_body_text(value["edge_id"])
        if edge_id in edge_ids:
            _publication_body_incomplete()
        edge_ids.add(edge_id)
        for field_name in ("analysis_id", "source_entity_id", "target_entity_id", "review_status", "publication_status"):
            _publication_body_text(value[field_name])
        if value["analysis_id"] != analysis_id:
            _publication_body_incomplete()
        if value["review_status"] != "accepted":
            _publication_body_incomplete()
        _publication_body_positive(value["record_version"])
        pack_ids.add(_publication_body_text(value["evidence_pack_id"]))
        evidence_ids.update(_publication_body_strings(value["evidence_ids"]))
    for path in _publication_body_sequence(propagation["paths"]):
        value = _publication_body_mapping(path)
        _publication_body_required(
            value, frozenset({"path_id", "analysis_id", "source_entity_id", "target_entity_id", "edges"})
        )
        for field_name in ("path_id", "analysis_id", "source_entity_id", "target_entity_id"):
            _publication_body_text(value[field_name])
        if value["analysis_id"] != analysis_id:
            _publication_body_incomplete()
        for edge in _publication_body_sequence(value["edges"]):
            path_edge = _publication_body_mapping(edge)
            _publication_body_required(path_edge, frozenset({"edge_id"}))
            if _publication_body_text(path_edge["edge_id"]) not in edge_ids:
                _publication_body_incomplete()
    lineage = set(_publication_body_strings(propagation["row_lineage"]))
    if not lineage.issubset(row_ids):
        _publication_body_incomplete()
    return pack_ids, evidence_ids


def _validate_publication_body_reviews(  # noqa: C901
    decision_summary: tuple[Mapping[str, object], ...],
    rows: Mapping[str, Mapping[str, object]],
    workspace_id: str,
    analysis_id: str,
) -> None:
    covered_rows: set[str] = set()
    required = frozenset(
        {
            "record_type",
            "decision_id",
            "workspace_id",
            "analysis_id",
            "row_id",
            "record_version",
            "row_hash",
            "role_category",
            "decision",
            "reason",
            "decided_at",
        }
    )
    for decision in decision_summary:
        _publication_body_required(decision, required)
        if decision["record_type"] != "row_review":
            _publication_body_incomplete()
        _publication_body_text(decision["decision_id"])
        if _publication_body_text(decision["workspace_id"]) != workspace_id:
            _publication_body_incomplete()
        if _publication_body_text(decision["analysis_id"]) != analysis_id:
            _publication_body_incomplete()
        row_id = _publication_body_text(decision["row_id"])
        row = rows.get(row_id)
        if row is None or row_id in covered_rows:
            _publication_body_incomplete()
        covered_rows.add(row_id)
        _publication_body_positive(decision["record_version"])
        if _publication_body_positive(decision["record_version"]) != row["record_version"]:
            _publication_body_incomplete()
        if _publication_body_hash(decision["row_hash"]).removeprefix("sha256:") != str(row["row_hash"]).removeprefix(
            "sha256:"
        ):
            _publication_body_incomplete()
        if decision["role_category"] != "human_reviewer" or decision["decision"] != "accepted":
            _publication_body_incomplete()
        _publication_body_text(decision["role_category"])
        _publication_body_text(decision["decision"])
        _publication_body_text(decision["reason"])
        try:
            _timestamp(decision["decided_at"], "decided_at")
        except FmeaDomainError as exc:
            raise FmeaDomainError("publication body is incomplete") from exc  # noqa: TRY003
    if covered_rows != set(rows):
        _publication_body_incomplete()


def _validate_publication_body_marker(
    version_manifest: Mapping[str, object],
    rows: tuple[Mapping[str, object], ...],
    risk_records: tuple[Mapping[str, object], ...],
    propagation: Mapping[str, object] | None,
    evidence_summary: tuple[Mapping[str, object], ...],
    decision_summary: tuple[Mapping[str, object], ...],
    *,
    workspace_id: str,
    analysis_id: str,
) -> None:
    if "report_layout" in version_manifest:
        from fmea_application.report_view import validate_report_layout

        validate_report_layout(version_manifest["report_layout"], version_manifest.get("template_identities"))
    if "body_schema_version" not in version_manifest:
        return
    marker = version_manifest["body_schema_version"]
    if marker != PUBLICATION_BODY_SCHEMA_VERSION:
        raise FmeaDomainError("publication body schema version is invalid")  # noqa: TRY003
    if any(
        len(section) > _MAX_CANONICAL_ARRAY_ITEMS
        for section in (rows, risk_records, evidence_summary, decision_summary)
    ):
        _publication_body_incomplete()
    row_ids: set[str] = set()
    row_pack_ids: set[str] = set()
    row_evidence_ids: set[str] = set()
    rows_by_id: dict[str, Mapping[str, object]] = {}
    for row in rows:
        pack_id, evidence_ids = _validate_publication_body_row(row, row_ids)
        row_pack_ids.add(pack_id)
        row_evidence_ids.update(evidence_ids)
        rows_by_id[row["row_id"]] = row
    for row in rows:
        if row["analysis_id"] != analysis_id:
            _publication_body_incomplete()
    risk_pack_ids, risk_evidence_ids = _validate_publication_body_risks(risk_records, rows_by_id)
    graph_pack_ids, graph_evidence_ids = _validate_publication_body_graph(
        propagation, row_ids, workspace_id, analysis_id
    )
    evidence_ids = _validate_publication_body_evidence(
        evidence_summary, row_pack_ids | risk_pack_ids | graph_pack_ids
    )
    if not (row_evidence_ids | risk_evidence_ids | graph_evidence_ids).issubset(evidence_ids):
        _publication_body_incomplete()
    _validate_publication_body_reviews(decision_summary, rows_by_id, workspace_id, analysis_id)


@dataclass(frozen=True, slots=True)
class NormalizedFmeaSnapshot:
    schema_version: Literal["graphrag.fmea.normalized-snapshot.v1"]
    snapshot_id: str
    workspace_id: str
    analysis_id: str
    revision_id: str
    revision_hash: str
    publication_id: str
    manifest_id: str
    rows: tuple[Mapping[str, object], ...]
    risk_records: tuple[Mapping[str, object], ...]
    propagation: Mapping[str, object] | None
    evidence_summary: tuple[Mapping[str, object], ...]
    decision_summary: tuple[Mapping[str, object], ...]
    version_manifest: Mapping[str, object]
    unresolved_items: tuple[Mapping[str, object], ...]
    audit_summary: Mapping[str, object]
    row_count: int
    snapshot_hash: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != "graphrag.fmea.normalized-snapshot.v1":
            raise FmeaDomainError("snapshot schema_version is invalid")  # noqa: TRY003
        for field_name in (
            "snapshot_id",
            "workspace_id",
            "analysis_id",
            "revision_id",
            "publication_id",
            "manifest_id",
        ):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(self, "revision_hash", _hash(self.revision_hash, "revision_hash"))
        object.__setattr__(self, "rows", _mapping_tuple(self.rows, "rows", identity_field="row_id"))
        object.__setattr__(
            self, "risk_records", _mapping_tuple(self.risk_records, "risk_records", identity_field="assessment_id")
        )
        object.__setattr__(
            self, "propagation", None if self.propagation is None else _mapping(self.propagation, "propagation")
        )
        object.__setattr__(
            self,
            "evidence_summary",
            _mapping_tuple(self.evidence_summary, "evidence_summary", identity_field="pack_id"),
        )
        object.__setattr__(
            self,
            "decision_summary",
            _mapping_tuple(self.decision_summary, "decision_summary", identity_field="decision_id"),
        )
        object.__setattr__(self, "version_manifest", _mapping(self.version_manifest, "version_manifest"))
        _validate_publication_body_marker(
            self.version_manifest,
            self.rows,
            self.risk_records,
            self.propagation,
            self.evidence_summary,
            self.decision_summary,
            workspace_id=self.workspace_id,
            analysis_id=self.analysis_id,
        )
        object.__setattr__(self, "unresolved_items", _mapping_tuple(self.unresolved_items, "unresolved_items"))
        object.__setattr__(self, "audit_summary", _mapping(self.audit_summary, "audit_summary"))
        if isinstance(self.row_count, bool) or not isinstance(self.row_count, int) or self.row_count < 0:
            raise FmeaDomainError("row_count must be a non-negative integer")  # noqa: TRY003
        if self.row_count != len(self.rows):
            raise FmeaDomainError("row_count does not match rows")  # noqa: TRY003
        object.__setattr__(self, "snapshot_hash", _hash(self.snapshot_hash, "snapshot_hash"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        if self.snapshot_hash.removeprefix("sha256:") != snapshot_content_hash(self):
            raise FmeaDomainError("snapshot hash does not match snapshot content")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class NormalizedSnapshotPage:
    rows: tuple[Mapping[str, object], ...]
    next_offset: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", _mapping_tuple(self.rows, "rows"))
        if self.next_offset is not None and (
            isinstance(self.next_offset, bool) or not isinstance(self.next_offset, int) or self.next_offset < 0
        ):
            raise FmeaDomainError("next_offset must be a non-negative integer or None")  # noqa: TRY003


@dataclass(frozen=True, slots=True)
class NormalizedSnapshotInput:
    revision: FmeaRevision
    publication_id: str
    manifest_id: str
    publication_revision_id: str
    publication_revision_hash: str
    publication_workspace_id: str
    publication_analysis_id: str
    rows: tuple[Mapping[str, object], ...]
    risk_records: tuple[Mapping[str, object], ...]
    propagation: Mapping[str, object] | None
    evidence_summary: tuple[Mapping[str, object], ...]
    decision_summary: tuple[Mapping[str, object], ...]
    version_manifest: Mapping[str, object]
    audit_summary: Mapping[str, object]
    created_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.revision, FmeaRevision):
            raise FmeaDomainError("revision must be an FmeaRevision")  # noqa: TRY003
        object.__setattr__(self, "publication_id", _text(self.publication_id, "publication_id"))
        object.__setattr__(self, "manifest_id", _text(self.manifest_id, "manifest_id"))
        object.__setattr__(
            self, "publication_revision_id", _text(self.publication_revision_id, "publication_revision_id")
        )
        object.__setattr__(
            self, "publication_revision_hash", _hash(self.publication_revision_hash, "publication_revision_hash")
        )
        object.__setattr__(
            self, "publication_workspace_id", _text(self.publication_workspace_id, "publication_workspace_id")
        )
        object.__setattr__(
            self, "publication_analysis_id", _text(self.publication_analysis_id, "publication_analysis_id")
        )
        object.__setattr__(self, "rows", _mapping_tuple(self.rows, "rows", identity_field="row_id"))
        object.__setattr__(
            self, "risk_records", _mapping_tuple(self.risk_records, "risk_records", identity_field="assessment_id")
        )
        object.__setattr__(
            self, "propagation", None if self.propagation is None else _mapping(self.propagation, "propagation")
        )
        object.__setattr__(
            self,
            "evidence_summary",
            _mapping_tuple(self.evidence_summary, "evidence_summary", identity_field="pack_id"),
        )
        object.__setattr__(
            self,
            "decision_summary",
            _mapping_tuple(self.decision_summary, "decision_summary", identity_field="decision_id"),
        )
        object.__setattr__(self, "version_manifest", _mapping(self.version_manifest, "version_manifest"))
        _validate_publication_body_marker(
            self.version_manifest,
            self.rows,
            self.risk_records,
            self.propagation,
            self.evidence_summary,
            self.decision_summary,
            workspace_id=self.publication_workspace_id,
            analysis_id=self.publication_analysis_id,
        )
        object.__setattr__(self, "audit_summary", _mapping(self.audit_summary, "audit_summary"))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))


def validate_snapshot_publication_binding(source: NormalizedSnapshotInput) -> None:
    if (
        source.publication_revision_id != source.revision.revision_id
        or source.publication_revision_hash != source.revision.revision_hash
    ):
        raise FmeaDomainError("snapshot publication binding does not match revision")  # noqa: TRY003
    if (
        source.publication_workspace_id != source.revision.workspace_id
        or source.publication_analysis_id != source.revision.analysis_id
    ):
        raise FmeaDomainError("snapshot publication workspace/analysis binding is invalid")  # noqa: TRY003


def canonical_normalized_snapshot_body(source: NormalizedSnapshotInput) -> Mapping[str, object]:
    if not isinstance(source, NormalizedSnapshotInput):
        raise FmeaDomainError("source must be a NormalizedSnapshotInput")  # noqa: TRY003
    validate_snapshot_publication_binding(source)
    snapshot_id = f"snapshot:{source.revision.revision_id}:{source.publication_id}"
    unresolved_items = tuple(
        {
            "acknowledgement_decision_id": item.acknowledgement_decision_id,
            "code": item.code,
            "evidence_ids": item.evidence_ids,
            "severity": item.severity,
            "source_id": item.source_id,
            "source_type": item.source_type,
        }
        for item in source.revision.unresolved_items
    )
    return {
        "schema_version": "graphrag.fmea.normalized-snapshot.v1",
        "snapshot_id": snapshot_id,
        "workspace_id": source.revision.workspace_id,
        "analysis_id": source.revision.analysis_id,
        "revision_id": source.revision.revision_id,
        "revision_hash": source.revision.revision_hash,
        "publication_id": source.publication_id,
        "manifest_id": source.manifest_id,
        "rows": source.rows,
        "risk_records": source.risk_records,
        "propagation": source.propagation,
        "evidence_summary": source.evidence_summary,
        "decision_summary": source.decision_summary,
        "version_manifest": source.version_manifest,
        "unresolved_items": unresolved_items,
        "audit_summary": source.audit_summary,
        "row_count": len(source.rows),
        "created_at": source.created_at,
    }


def _canonical_snapshot_body(snapshot: NormalizedFmeaSnapshot) -> Mapping[str, object]:
    return {
        "schema_version": snapshot.schema_version,
        "snapshot_id": snapshot.snapshot_id,
        "workspace_id": snapshot.workspace_id,
        "analysis_id": snapshot.analysis_id,
        "revision_id": snapshot.revision_id,
        "revision_hash": snapshot.revision_hash,
        "publication_id": snapshot.publication_id,
        "manifest_id": snapshot.manifest_id,
        "rows": snapshot.rows,
        "risk_records": snapshot.risk_records,
        "propagation": snapshot.propagation,
        "evidence_summary": snapshot.evidence_summary,
        "decision_summary": snapshot.decision_summary,
        "version_manifest": snapshot.version_manifest,
        "unresolved_items": snapshot.unresolved_items,
        "audit_summary": snapshot.audit_summary,
        "row_count": snapshot.row_count,
        "created_at": snapshot.created_at,
    }


def _plain_snapshot_value(value: object, *, depth: int = 0) -> object:
    """Copy only exact plain JSON values without invoking custom protocols."""

    if depth > _MAX_DEPTH + 1:
        raise ValueError("snapshot value depth is invalid")  # noqa: TRY003
    value_type = type(value)
    if value_type is str:
        return _plain_snapshot_string(value)
    if value is None or value_type in {bool, int, float}:
        return value
    if value_type in {tuple, list}:
        if len(value) > _MAX_CANONICAL_ARRAY_ITEMS:  # type: ignore[arg-type]
            raise ValueError("snapshot sequence is too large")  # noqa: TRY003
        copied = tuple(_plain_snapshot_value(item, depth=depth + 1) for item in value)  # type: ignore[union-attr]
        return copied
    if value_type in {dict, MappingProxyType}:
        if len(value) > _MAX_ITEMS:  # type: ignore[arg-type]
            raise ValueError("snapshot mapping is too large")  # noqa: TRY003
        copied_mapping: dict[str, object] = {}
        for key, item in value.items():  # type: ignore[union-attr]
            if type(key) is not str:
                raise ValueError("snapshot mapping key is invalid")  # noqa: TRY003
            _plain_snapshot_string(key)
            copied_mapping[key] = _plain_snapshot_value(item, depth=depth + 1)
        return copied_mapping
    raise ValueError("snapshot value is not plain JSON")  # noqa: TRY003


def _plain_snapshot_string(value: object) -> str:
    if type(value) is not str or DRAFT_PREVIEW_MARKER in value:
        raise ValueError("snapshot string is invalid")  # noqa: TRY003
    return value


def _snapshot_revalidation_invalid() -> NoReturn:
    raise ValueError


def revalidate_normalized_snapshot(value: object) -> NormalizedFmeaSnapshot:
    """Rebuild an exact immutable snapshot and replay every constructor invariant."""

    try:
        if type(value) is not NormalizedFmeaSnapshot:
            _snapshot_revalidation_invalid()
        values = {
            "schema_version": _plain_snapshot_string(value.schema_version),
            "snapshot_id": _plain_snapshot_string(value.snapshot_id),
            "workspace_id": _plain_snapshot_string(value.workspace_id),
            "analysis_id": _plain_snapshot_string(value.analysis_id),
            "revision_id": _plain_snapshot_string(value.revision_id),
            "revision_hash": _plain_snapshot_string(value.revision_hash),
            "publication_id": _plain_snapshot_string(value.publication_id),
            "manifest_id": _plain_snapshot_string(value.manifest_id),
            "rows": _plain_snapshot_value(value.rows),
            "risk_records": _plain_snapshot_value(value.risk_records),
            "propagation": None if value.propagation is None else _plain_snapshot_value(value.propagation),
            "evidence_summary": _plain_snapshot_value(value.evidence_summary),
            "decision_summary": _plain_snapshot_value(value.decision_summary),
            "version_manifest": _plain_snapshot_value(value.version_manifest),
            "unresolved_items": _plain_snapshot_value(value.unresolved_items),
            "audit_summary": _plain_snapshot_value(value.audit_summary),
            "row_count": value.row_count,
            "snapshot_hash": _plain_snapshot_string(value.snapshot_hash),
            "created_at": _plain_snapshot_string(value.created_at),
        }
        if type(values["row_count"]) is not int:
            _snapshot_revalidation_invalid()
        return NormalizedFmeaSnapshot(**values)  # type: ignore[arg-type]
    except Exception:
        raise FmeaDomainError("snapshot revalidation failed") from None  # noqa: TRY003


def snapshot_content_hash(snapshot: NormalizedFmeaSnapshot) -> str:
    if not isinstance(snapshot, NormalizedFmeaSnapshot):
        raise FmeaDomainError("snapshot must be a NormalizedFmeaSnapshot")  # noqa: TRY003
    return canonical_hash(_canonical_snapshot_body(snapshot), max_array_items=_MAX_CANONICAL_ARRAY_ITEMS)


def build_normalized_snapshot(source: NormalizedSnapshotInput) -> NormalizedFmeaSnapshot:
    validate_snapshot_publication_binding(source)
    body = canonical_normalized_snapshot_body(source)
    snapshot_hash = canonical_hash(body, max_array_items=_MAX_CANONICAL_ARRAY_ITEMS)
    return NormalizedFmeaSnapshot(**body, snapshot_hash=snapshot_hash)  # type: ignore[arg-type]


def iter_normalized_snapshot_pages(
    snapshot: NormalizedFmeaSnapshot, *, page_size: int
) -> Iterator[NormalizedSnapshotPage]:
    if not isinstance(snapshot, NormalizedFmeaSnapshot):
        raise FmeaDomainError("snapshot must be a NormalizedFmeaSnapshot")  # noqa: TRY003
    if isinstance(page_size, bool) or not 1 <= page_size <= 500:
        raise ValueError("page_size must be between 1 and 500")  # noqa: TRY003

    for offset in range(0, snapshot.row_count, page_size):
        end = offset + page_size
        yield NormalizedSnapshotPage(
            rows=snapshot.rows[offset:end],
            next_offset=end if end < snapshot.row_count else None,
        )


__all__ = [
    "DRAFT_PREVIEW_MARKER",
    "PUBLICATION_BODY_SCHEMA_VERSION",
    "NormalizedFmeaSnapshot",
    "NormalizedSnapshotInput",
    "NormalizedSnapshotPage",
    "build_normalized_snapshot",
    "canonical_json_bytes",
    "canonical_normalized_snapshot_body",
    "iter_normalized_snapshot_pages",
    "revalidate_normalized_snapshot",
    "snapshot_content_hash",
    "validate_snapshot_publication_binding",
]
