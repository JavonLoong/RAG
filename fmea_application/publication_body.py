"""Version-bound, export-safe projection of authoritative FMEA governance state."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Final, NoReturn

from core_domain.fmea.entities import FmeaRow, validate_extension_values
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.governance import FmeaRevision, canonical_hash, revision_content_hash
from core_domain.fmea.policies import validate_evidence_ids, validate_propagation_edge, validate_row_evidence
from core_domain.fmea.propagation import PropagationEdge, PropagationGraphRevision, PropagationPath, TopologyNode
from core_domain.fmea.scoring import RiskAssessment, RiskAssessmentRecord, ScoreDimension
from core_domain.fmea.states import PropagationStatus, ReviewStatus, RiskStatus
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, validate_evidence_lineage
from fmea_application.governance_contracts import PublicationReviewAuthority
from fmea_application.revision_assembler import GovernanceInputs
from fmea_application.snapshot_contracts import _freeze_export_value

_HASH = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_LEGACY_LOCATOR = re.compile(r"^page:(?P<page>[1-9][0-9]*)#span:(?P<span>[1-9][0-9]*)$")
_BODY_ERROR_STALE: Final = "FMEA_PUBLICATION_BODY_STALE"
_BODY_ERROR_INCOMPLETE: Final = "FMEA_PUBLICATION_BODY_INCOMPLETE"
_BODY_ERROR_UNSAFE: Final = "FMEA_PUBLICATION_BODY_UNSAFE"

_ROW_FIELDS: Final = (
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
    "risk_assessment",
    "field_evidence",
    "field_support",
    "claim_status",
    "review_status",
    "publication_status",
    "record_version",
    "extension_values",
    "field_claims",
)
_RISK_FIELDS: Final = (
    "assessment_id",
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
)
_REVIEW_PUBLIC_FIELDS: Final = frozenset(
    {
        "role_category",
        "decision",
        "reason",
        "decided_at",
    }
)
_RISK_ASSESSMENT_FIELDS: Final = (
    "severity_by_consequence_class",
    "decision_severity",
    "occurrence",
    "detection",
    "rpn",
    "decision_priority",
    "inherent_risk",
    "current_risk",
    "target_residual_risk",
    "verified_residual_risk",
    "uncertainty",
    "reason",
    "scoring_rule_pack_id",
    "scoring_rule_pack_version",
    "evidence_ids",
)


def _raise(code: str, message: str) -> NoReturn:
    raise FmeaDomainError(f"{code}: {message}")  # noqa: TRY003


def _stale(message: str = "authoritative publication binding is stale") -> NoReturn:
    _raise(_BODY_ERROR_STALE, message)


def _incomplete(message: str = "authoritative publication body is incomplete") -> NoReturn:
    _raise(_BODY_ERROR_INCOMPLETE, message)


def _unsafe(message: str = "publication body contains a non-export-safe value") -> NoReturn:
    _raise(_BODY_ERROR_UNSAFE, message)


def _freeze(value: object) -> object:
    try:
        return _freeze_export_value(value)
    except FmeaDomainError:
        _unsafe()


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    frozen = _freeze(value)
    if not isinstance(frozen, Mapping):  # pragma: no cover - _freeze preserves mappings
        _unsafe()
    return frozen


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FmeaDomainError(f"{field_name} must not be empty")  # noqa: TRY003
    return value.strip()


def _positive(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FmeaDomainError(f"{field_name} must be positive")  # noqa: TRY003
    return value


def _hash(value: object, field_name: str) -> str:
    normalized = _text(value, field_name)
    if _HASH.fullmatch(normalized) is None:
        raise FmeaDomainError(f"{field_name} must be a lowercase SHA-256 hash")  # noqa: TRY003
    return normalized


def _same_hash(left: object, right: object) -> bool:
    return (
        isinstance(left, str)
        and isinstance(right, str)
        and left.removeprefix("sha256:") == right.removeprefix("sha256:")
    )


def _public_hash(value: object, field_name: str) -> str:
    """Use the existing hash identity without exposing a URI-like prefix."""

    try:
        return _hash(value, field_name).removeprefix("sha256:")
    except FmeaDomainError:
        _unsafe("public hash is not export-safe")


def _public_locator(locator: object) -> Mapping[str, object]:
    if not isinstance(locator, str) or not locator.strip():
        _unsafe("evidence locator is not export-safe")
    candidate = locator.strip()
    legacy_match = _LEGACY_LOCATOR.fullmatch(candidate)
    if legacy_match is not None:
        return {"page": int(legacy_match.group("page")), "span": int(legacy_match.group("span"))}

    try:
        parsed = json.loads(candidate)
    except (TypeError, ValueError):
        _unsafe("evidence locator encoding is not recognised")
    if not isinstance(parsed, Mapping):
        _unsafe("evidence locator must be structured")
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    if candidate != canonical:
        _unsafe("evidence locator encoding is not canonical")
    return _freeze_mapping(parsed)


def _evidence_content_identity(ref: EvidenceRef) -> str:
    payload = {
        "source_type": ref.source_type,
        "document_id": ref.document_id,
        "document_version": ref.document_version,
        "locator": ref.locator,
        "normalized_quote": ref.normalized_quote,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _verify_evidence_ref(ref: EvidenceRef) -> None:
    try:
        content_hash = _hash(ref.content_hash, "content_hash")
        evidence_hash = _hash(ref.evidence_hash, "evidence_hash")
    except FmeaDomainError:
        _stale("evidence hash shape is invalid")
    if not _same_hash(evidence_hash, _evidence_content_identity(ref)):
        _stale("evidence hash does not match native evidence content")
    if not content_hash:
        _stale("evidence content hash is missing")


def _verify_pack(pack: EvidencePack, packs_by_id: Mapping[str, EvidencePack], workspace_id: str) -> None:
    if pack.workspace_id != workspace_id:
        _stale("evidence pack is outside the governance scope")
    try:
        validate_evidence_lineage(pack, packs_by_id)
    except FmeaDomainError:
        _stale("evidence pack lineage does not match its contents")
    refs_by_id: dict[str, EvidenceRef] = {}
    for ref in pack.refs:
        if ref.evidence_id in refs_by_id:
            _stale("evidence pack contains duplicate evidence identities")
        if ref.workspace_id != workspace_id:
            _stale("evidence reference is outside the governance scope")
        _verify_evidence_ref(ref)
        _public_locator(ref.locator)
        refs_by_id[ref.evidence_id] = ref


def _verify_revision_and_inputs(  # noqa: C901
    revision: FmeaRevision, inputs: GovernanceInputs
) -> tuple[dict[str, FmeaRow], dict[str, RiskAssessmentRecord], dict[str, EvidencePack]]:
    if not isinstance(revision, FmeaRevision) or not isinstance(inputs, GovernanceInputs):
        _stale("publication inputs have an invalid type")
    if (
        revision.workspace_id != inputs.workspace_id
        or revision.analysis_id != inputs.analysis_id
        or revision.analysis_record_version != inputs.analysis.record_version
        or not _same_hash(revision.analysis_hash, inputs.analysis.canonical_hash)
    ):
        _stale("revision and source analysis bindings differ")
    try:
        inputs.analysis.verify()
        if revision_content_hash(revision) != revision.revision_hash.removeprefix("sha256:"):
            _stale("revision content hash does not match native revision")
    except FmeaDomainError:
        _stale("revision content hash cannot be recomputed")

    expected_domain = (
        inputs.domain_pack_identity.artifact_id,
        inputs.domain_pack_identity.version,
        inputs.domain_pack_identity.content_hash,
    )
    if revision.domain_pack_identity != expected_domain:
        _stale("domain pack identity differs from revision")
    if revision.template_identities != tuple(sorted(item.identity for item in inputs.template_identities)):
        _stale("template identities differ from revision")
    if revision.scoring_rule_identities != tuple(sorted(item.identity for item in inputs.scoring_rule_identities)):
        _stale("scoring rule identities differ from revision")
    expected_propagation_identity = (
        None
        if inputs.propagation_rule_identity is None
        else inputs.propagation_rule_identity.identity
    )
    if revision.propagation_rule_identity != expected_propagation_identity:
        _stale("propagation rule identity differs from revision")
    if revision.retrieval_provenance != inputs.retrieval_provenance.snapshot:
        _stale("retrieval provenance differs from revision")

    if inputs.parent_revision is None:
        if revision.parent_revision_id is not None or revision.parent_revision_hash is not None:
            _stale("revision parent binding is unexpected")
    elif (
        revision.parent_revision_id != inputs.parent_revision.revision_id
        or revision.parent_revision_hash != inputs.parent_revision.revision_hash
    ):
        _stale("revision parent binding differs from source")

    rows: dict[str, FmeaRow] = {}
    for row in inputs.rows:
        if row.row_id in rows:
            _stale("source contains duplicate row identities")
        if row.analysis_id != inputs.analysis_id:
            _stale("row is outside the governance scope")
        rows[row.row_id] = row
    expected_rows = tuple(
        sorted((row_id, row.record_version, canonical_hash(row)) for row_id, row in rows.items())
    )
    if expected_rows != revision.row_versions:
        _stale("row version or content hash differs from revision")

    risks: dict[str, RiskAssessmentRecord] = {}
    for risk in inputs.risk_records:
        if risk.assessment_id in risks:
            _stale("source contains duplicate risk identities")
        if risk.workspace_id != inputs.workspace_id or risk.row_id not in rows:
            _stale("risk record is outside the governance scope")
        row = rows[risk.row_id]
        if risk.source_record_version != row.record_version:
            _stale("risk source record version differs from row")
        risks[risk.assessment_id] = risk
    expected_risks = tuple(
        sorted((assessment_id, risk.record_version, canonical_hash(risk)) for assessment_id, risk in risks.items())
    )
    if expected_risks != revision.risk_versions:
        _stale("risk version or content hash differs from revision")

    packs: dict[str, EvidencePack] = {}
    for pack in inputs.evidence_packs:
        if pack.pack_id in packs:
            _stale("source contains duplicate evidence pack identities")
        packs[pack.pack_id] = pack
    for pack in packs.values():
        _verify_pack(pack, packs, inputs.workspace_id)
    expected_packs = tuple(sorted((pack_id, pack.pack_hash) for pack_id, pack in packs.items()))
    if expected_packs != revision.evidence_pack_hashes:
        _stale("evidence pack identity differs from revision")

    graph = inputs.propagation_graph_revision
    if graph is None:
        if revision.propagation_graph_revision_id is not None or revision.propagation_graph_hash is not None:
            _stale("revision contains an unexpected propagation graph")
    else:
        if (
            graph.workspace_id != inputs.workspace_id
            or graph.analysis_id != inputs.analysis_id
            or graph.analysis_record_version != inputs.analysis.record_version
            or revision.propagation_graph_revision_id != graph.graph_revision_id
            or revision.propagation_graph_hash != canonical_hash(graph)
        ):
            _stale("propagation graph identity differs from revision")
    return rows, risks, packs


def _verify_row(row: FmeaRow, inputs: GovernanceInputs, packs: Mapping[str, EvidencePack]) -> None:
    if row.review_status is not ReviewStatus.ACCEPTED:
        _incomplete("rows must be accepted before publication")
    pack = packs.get(row.evidence_pack_id)
    if pack is None:
        _stale("row evidence pack is missing")
    try:
        validate_row_evidence(row, pack)
        validate_extension_values(row, inputs.domain_pack)
    except FmeaDomainError:
        _stale("row evidence or extension binding is invalid")


def _verify_risk(
    risk: RiskAssessmentRecord,
    row: FmeaRow,
    packs: Mapping[str, EvidencePack],
    inputs: GovernanceInputs,
) -> None:
    if risk.status is not RiskStatus.CONFIRMED:
        _incomplete("risk records must be confirmed before publication")
    if (risk.domain_pack_id, risk.domain_pack_version) != (
        inputs.domain_pack.pack_id,
        inputs.domain_pack.version,
    ):
        _stale("risk domain pack identity differs from source")
    scoring_pairs = {(item.artifact_id, item.version) for item in inputs.scoring_rule_identities}
    if (risk.rule_pack_id, risk.rule_pack_version) not in scoring_pairs:
        _stale("risk scoring rule identity differs from source")
    pack = packs.get(risk.evidence_pack_id)
    if pack is None or pack.pack_id != row.evidence_pack_id:
        _stale("risk evidence pack is missing or does not match its row")
    if risk.derived is not None and (
        risk.derived.scoring_rule_pack_id != risk.rule_pack_id
        or risk.derived.scoring_rule_pack_version != risk.rule_pack_version
    ):
        _stale("derived risk scoring rule identity differs from risk record")
    try:
        for dimension in risk.dimensions:
            validate_evidence_ids(dimension.evidence_ids, pack)
        if risk.derived is not None:
            validate_evidence_ids(risk.derived.evidence_ids, pack)
    except FmeaDomainError:
        _stale("risk evidence binding is invalid")


def _verify_graph(  # noqa: C901
    graph: PropagationGraphRevision,
    rows: Mapping[str, FmeaRow],
    packs: Mapping[str, EvidencePack],
    inputs: GovernanceInputs,
) -> None:
    if graph.status is not PropagationStatus.CONFIRMED:
        _incomplete("propagation graph must be confirmed before publication")
    if (graph.domain_pack_id, graph.domain_pack_version) != (
        inputs.domain_pack.pack_id,
        inputs.domain_pack.version,
    ):
        _stale("propagation graph domain pack identity differs from source")
    expected_rule = (
        None
        if inputs.propagation_rule_identity is None
        else (inputs.propagation_rule_identity.artifact_id, inputs.propagation_rule_identity.version)
    )
    if expected_rule != (graph.rule_pack_id, graph.rule_pack_version):
        _stale("propagation graph rule identity differs from source")
    graph_pack_ids = tuple(graph.evidence_pack_ids)
    if len(graph_pack_ids) != len(set(graph_pack_ids)) or any(pack_id not in packs for pack_id in graph_pack_ids):
        _stale("propagation graph evidence packs are missing")
    edges_by_id: dict[str, PropagationEdge] = {}
    for edge in graph.edges:
        if edge.edge_id in edges_by_id:
            _stale("propagation graph contains duplicate edge identities")
        if edge.analysis_id != graph.analysis_id:
            _stale("propagation edge is outside the governance scope")
        if edge.review_status is not ReviewStatus.ACCEPTED:
            _incomplete("propagation edges must be accepted before publication")
        pack = packs.get(edge.evidence_pack_id)
        if pack is None:
            _stale("propagation edge evidence pack is missing")
        try:
            validate_propagation_edge(edge, pack)
        except FmeaDomainError:
            _stale("propagation edge evidence binding is invalid")
        edges_by_id[edge.edge_id] = edge
    for path in graph.paths:
        if path.analysis_id != graph.analysis_id:
            _stale("propagation path is not bound to the graph")
        for edge in path.edges:
            graph_edge = edges_by_id.get(edge.edge_id)
            if graph_edge is None or graph_edge != edge:
                _stale("propagation path edge differs from graph edge")


def _project_risk_assessment(assessment: RiskAssessment) -> Mapping[str, object]:
    result = {field_name: getattr(assessment, field_name) for field_name in _RISK_ASSESSMENT_FIELDS}
    return _freeze_mapping(result)


def _project_field_evidence(row: FmeaRow) -> tuple[Mapping[str, object], ...]:
    return tuple(
        _freeze_mapping({"field_key": field_key, "evidence_ids": evidence_ids})
        for field_key, evidence_ids in sorted(row.field_evidence, key=lambda item: item[0])
    )


def _project_field_support(row: FmeaRow) -> tuple[Mapping[str, object], ...]:
    return tuple(
        _freeze_mapping({"field_key": field_key, "support_status": status.value})
        for field_key, status in sorted(row.field_support, key=lambda item: item[0])
    )


def _project_field_claims(row: FmeaRow) -> tuple[Mapping[str, object], ...]:
    return tuple(
        _freeze_mapping(
            {
                "field_key": claim.field_key,
                "claim_status": claim.claim_status.value,
                "support_status": claim.support_status.value,
                "evidence_ids": claim.evidence_ids,
                "uncertainty": claim.uncertainty,
                "conflict_ids": claim.conflict_ids,
            }
        )
        for claim in sorted(row.field_claims, key=lambda item: item.field_key)
    )


def _project_extensions(row: FmeaRow) -> tuple[Mapping[str, object], ...]:
    return tuple(
        _freeze_mapping({"field_key": value.field_key, "value_type": value.value_type, "value": value.value})
        for value in sorted(row.extension_values, key=lambda item: item.field_key)
    )


def _project_row(row: FmeaRow, row_hash: str) -> Mapping[str, object]:
    result: dict[str, object] = {
        field_name: getattr(row, field_name)
        for field_name in _ROW_FIELDS
        if field_name not in {"risk_assessment", "field_evidence", "field_support", "field_claims", "extension_values"}
    }
    result["row_hash"] = _public_hash(row_hash, "row_hash")
    result["risk_assessment"] = (
        None if row.risk_assessment is None else _project_risk_assessment(row.risk_assessment)
    )
    result["field_evidence"] = _project_field_evidence(row)
    result["field_support"] = _project_field_support(row)
    result["field_claims"] = _project_field_claims(row)
    result["extension_values"] = _project_extensions(row)
    for field_name in ("claim_status", "review_status", "publication_status"):
        result[field_name] = getattr(row, field_name).value
    return _freeze_mapping(result)


def _project_dimension(dimension: ScoreDimension) -> Mapping[str, object]:
    return _freeze_mapping(
        {
            "name": dimension.name,
            "value": dimension.value,
            "evidence_ids": dimension.evidence_ids,
            "reason": dimension.reason,
            "uncertainty": dimension.uncertainty,
        }
    )


def _project_risk_record(risk: RiskAssessmentRecord, risk_hash: str) -> Mapping[str, object]:
    result: dict[str, object] = {
        field_name: getattr(risk, field_name)
        for field_name in _RISK_FIELDS
        if field_name not in {"dimensions", "derived", "status"}
    }
    result["assessment_hash"] = _public_hash(risk_hash, "assessment_hash")
    result["status"] = risk.status.value
    result["dimensions"] = tuple(_project_dimension(dimension) for dimension in sorted(risk.dimensions, key=lambda item: item.name))
    result["derived"] = None if risk.derived is None else _project_risk_assessment(risk.derived)
    result["confirmation_basis"] = None if risk.proposal_id is None else {"proposal_id": risk.proposal_id}
    return _freeze_mapping(result)


def _project_node(node: TopologyNode) -> Mapping[str, object]:
    return _freeze_mapping(
        {"node_id": node.node_id, "node_type": node.node_type, "operating_modes": node.operating_modes}
    )


def _project_edge(edge: PropagationEdge) -> Mapping[str, object]:
    return _freeze_mapping(
        {
            "edge_id": edge.edge_id,
            "analysis_id": edge.analysis_id,
            "source_entity_id": edge.source_entity_id,
            "target_entity_id": edge.target_entity_id,
            "relation_type": edge.relation_type,
            "interface_variable": edge.interface_variable,
            "unit": edge.unit,
            "direction": edge.direction,
            "threshold": edge.threshold,
            "operating_modes": edge.operating_modes,
            "delay_ms": edge.delay_ms,
            "response_time_ms": edge.response_time_ms,
            "fault_tolerance_time_ms": edge.fault_tolerance_time_ms,
            "barrier_ids": edge.barrier_ids,
            "evidence_pack_id": edge.evidence_pack_id,
            "evidence_ids": edge.evidence_ids,
            "evidence_support": edge.evidence_support.value,
            "claim_status": edge.claim_status.value,
            "review_status": edge.review_status.value,
            "publication_status": edge.publication_status.value,
            "path_length": edge.path_length,
            "is_cyclic": edge.is_cyclic,
            "is_unprocessed": edge.is_unprocessed,
            "is_external": edge.is_external,
            "is_terminal": edge.is_terminal,
            "risk_priority": edge.risk_priority,
            "record_version": edge.record_version,
        }
    )


def _project_path(path: PropagationPath) -> Mapping[str, object]:
    return _freeze_mapping(
        {
            "path_id": path.path_id,
            "analysis_id": path.analysis_id,
            "source_entity_id": path.source_entity_id,
            "target_entity_id": path.target_entity_id,
            "edges": tuple(_project_edge(edge) for edge in path.edges),
            "path_length": path.path_length,
            "is_cyclic": path.is_cyclic,
            "requires_human_review": path.requires_human_review,
        }
    )


def _project_graph(graph: PropagationGraphRevision, rows: Mapping[str, FmeaRow]) -> Mapping[str, object]:
    lineage_ids = {
        entity_id
        for edge in graph.edges
        for entity_id in (edge.source_entity_id, edge.target_entity_id)
        if entity_id in rows
    }
    return _freeze_mapping(
        {
            "graph_revision_id": graph.graph_revision_id,
            "workspace_id": graph.workspace_id,
            "analysis_id": graph.analysis_id,
            "analysis_record_version": graph.analysis_record_version,
            "topology_snapshot_id": graph.topology_snapshot_id,
            "topology_hash": _public_hash(graph.topology_hash, "topology_hash"),
            "domain_pack_id": graph.domain_pack_id,
            "domain_pack_version": graph.domain_pack_version,
            "rule_pack_id": graph.rule_pack_id,
            "rule_pack_version": graph.rule_pack_version,
            "status": graph.status.value,
            "record_version": graph.record_version,
            "nodes": tuple(_project_node(node) for node in sorted(graph.nodes, key=lambda item: item.node_id)),
            "edges": tuple(_project_edge(edge) for edge in sorted(graph.edges, key=lambda item: item.edge_id)),
            "paths": tuple(_project_path(path) for path in sorted(graph.paths, key=lambda item: item.path_id)),
            "row_lineage": tuple(sorted(lineage_ids)),
        }
    )


def _project_evidence_ref(ref: EvidenceRef) -> Mapping[str, object]:
    return _freeze_mapping(
        {
            "evidence_id": ref.evidence_id,
            "document_id": ref.document_id,
            "document_version": ref.document_version,
            "content_hash": _public_hash(ref.content_hash, "content_hash"),
            "evidence_hash": _public_hash(ref.evidence_hash, "evidence_hash"),
            "locator": _public_locator(ref.locator),
            "quote": ref.quote,
            "source_type": ref.source_type,
            "source_trust": ref.source_trust,
        }
    )


def _project_evidence(
    packs: Mapping[str, EvidencePack], referenced_ids: set[str]
) -> tuple[Mapping[str, object], ...]:
    result: list[Mapping[str, object]] = []
    for pack in sorted(packs.values(), key=lambda item: item.pack_id):
        refs = tuple(
            _project_evidence_ref(ref)
            for ref in sorted(pack.refs, key=lambda item: item.evidence_id)
            if ref.evidence_id in referenced_ids
        )
        result.append(
            _freeze_mapping(
                {
                    "pack_id": pack.pack_id,
                    "pack_hash": pack.pack_hash,
                    "evidence_pack_version": pack.versions.evidence_pack_version,
                    "refs": refs,
                }
            )
        )
    return tuple(result)


def _review_values(record: PublicationReviewRecord) -> Mapping[str, object]:
    if set(record.public_fields) != _REVIEW_PUBLIC_FIELDS:
        _incomplete("review record public fields are incomplete or contain unsupported fields")
    for field_name in _REVIEW_PUBLIC_FIELDS:
        value = record.public_fields[field_name]
        if not isinstance(value, str) or not value.strip():
            _incomplete("review record public fields must contain non-empty text")
    if record.public_fields["role_category"] != "human_reviewer":
        _incomplete("publication review must be a human reviewer decision")
    if record.public_fields["decision"] != "accepted":
        _incomplete("publication review decision must be accepted")
    decided_at = record.public_fields["decided_at"]
    try:
        parsed_timestamp = datetime.fromisoformat(str(decided_at).replace("Z", "+00:00"))
    except ValueError:
        _incomplete("publication review timestamp is invalid")
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() != timedelta(0):
        _incomplete("publication review timestamp must be UTC")
    result: dict[str, object] = {
        "record_type": "row_review",
        "decision_id": record.decision_id,
        "workspace_id": record.workspace_id,
        "analysis_id": record.analysis_id,
        "row_id": record.row_id,
        "record_version": record.record_version,
        "row_hash": _public_hash(record.row_hash, "row_hash"),
        **dict(record.public_fields),
    }
    return _freeze_mapping(result)


def _verify_reviews(
    reviews: tuple[PublicationReviewRecord, ...],
    rows: Mapping[str, FmeaRow],
    revision: FmeaRevision,
) -> tuple[Mapping[str, object], ...]:
    row_versions = {row_id: (version, row_hash) for row_id, version, row_hash in revision.row_versions}
    seen_decisions: set[str] = set()
    covered_rows: set[str] = set()
    projected: list[Mapping[str, object]] = []
    for record in reviews:
        if not isinstance(record, PublicationReviewRecord):
            _incomplete("review records must be typed server records")
        if record.decision_id in seen_decisions:
            _incomplete("review records contain duplicate decision identities")
        if record.row_id in covered_rows:
            _incomplete("each selected row requires exactly one repository review record")
        expected = row_versions.get(record.row_id)
        if (
            record.workspace_id != revision.workspace_id
            or record.analysis_id != revision.analysis_id
            or record.row_id not in rows
            or expected is None
            or record.record_version != expected[0]
            or not _same_hash(record.row_hash, expected[1])
        ):
            _stale("review record does not bind the selected row version")
        seen_decisions.add(record.decision_id)
        covered_rows.add(record.row_id)
        projected.append(_review_values(record))
    if covered_rows != set(rows):
        _incomplete("each selected row requires an exact repository review record")
    return tuple(sorted(projected, key=lambda item: str(item["decision_id"])))


@dataclass(frozen=True, slots=True)
class PublicationReviewRecord:
    """The minimal repository-owned review data allowed into a publication."""

    decision_id: str
    workspace_id: str
    analysis_id: str
    row_id: str
    record_version: int
    row_hash: str
    public_fields: Mapping[str, object]
    authority: PublicationReviewAuthority | None = None

    def __post_init__(self) -> None:
        for field_name in ("decision_id", "workspace_id", "analysis_id", "row_id"):
            object.__setattr__(self, field_name, _text(getattr(self, field_name), field_name))
        object.__setattr__(self, "record_version", _positive(self.record_version, "record_version"))
        object.__setattr__(self, "row_hash", _hash(self.row_hash, "row_hash"))
        if not isinstance(self.public_fields, Mapping):
            raise FmeaDomainError("public_fields must be a mapping")  # noqa: TRY003
        object.__setattr__(self, "public_fields", _freeze_mapping(self.public_fields))
        if self.authority is not None and not isinstance(self.authority, PublicationReviewAuthority):
            raise FmeaDomainError("authority must be a PublicationReviewAuthority")  # noqa: TRY003


def _publication_body_mappings(value: object, field_name: str) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, str | bytes) or value is None:
        raise FmeaDomainError(f"{field_name} must be a sequence")  # noqa: TRY003
    try:
        items: tuple[object, ...] = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise FmeaDomainError(f"{field_name} must be a sequence") from exc  # noqa: TRY003
    projected: list[Mapping[str, object]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise FmeaDomainError(f"{field_name} must contain mappings")  # noqa: TRY003
        frozen = _freeze(item)
        if not isinstance(frozen, Mapping):  # pragma: no cover
            raise FmeaDomainError(f"{field_name} must contain mappings")  # noqa: TRY003
        projected.append(frozen)
    return tuple(projected)


def _publication_body_authorities(value: object) -> tuple[PublicationReviewAuthority, ...]:
    authorities = tuple(value)  # type: ignore[arg-type]
    if any(not isinstance(authority, PublicationReviewAuthority) for authority in authorities):
        raise FmeaDomainError("review_authorities must contain typed authority receipts")  # noqa: TRY003
    normalized = tuple(sorted(authorities, key=lambda authority: authority.decision_id))
    if normalized != authorities:
        raise FmeaDomainError("review_authorities must be sorted")  # noqa: TRY003
    if len({authority.decision_id for authority in authorities}) != len(authorities):
        raise FmeaDomainError("review_authorities must be unique")  # noqa: TRY003
    return authorities


@dataclass(frozen=True, slots=True)
class PublicationBody:
    """Deeply immutable public projection bound to one authoritative revision."""

    rows: tuple[Mapping[str, object], ...]
    risk_records: tuple[Mapping[str, object], ...]
    propagation: Mapping[str, object] | None
    evidence_summary: tuple[Mapping[str, object], ...]
    decision_summary: tuple[Mapping[str, object], ...]
    review_authorities: tuple[PublicationReviewAuthority, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", _publication_body_mappings(self.rows, "rows"))
        object.__setattr__(self, "risk_records", _publication_body_mappings(self.risk_records, "risk_records"))
        if self.propagation is not None and not isinstance(self.propagation, Mapping):
            raise FmeaDomainError("propagation must be a mapping or None")  # noqa: TRY003
        frozen_propagation = None if self.propagation is None else _freeze(self.propagation)
        if frozen_propagation is not None and not isinstance(frozen_propagation, Mapping):  # pragma: no cover
            raise FmeaDomainError("propagation must be a mapping or None")  # noqa: TRY003
        object.__setattr__(
            self,
            "propagation",
            frozen_propagation,
        )
        object.__setattr__(self, "evidence_summary", _publication_body_mappings(self.evidence_summary, "evidence_summary"))
        object.__setattr__(self, "decision_summary", _publication_body_mappings(self.decision_summary, "decision_summary"))
        object.__setattr__(self, "review_authorities", _publication_body_authorities(self.review_authorities))


def _project_publication_body(
    revision: FmeaRevision,
    inputs: GovernanceInputs,
    *,
    review_records: tuple[PublicationReviewRecord, ...],
) -> PublicationBody:
    """Project already-attested typed inputs without making an authority claim."""

    rows, risks, packs = _verify_revision_and_inputs(revision, inputs)
    for row in rows.values():
        _verify_row(row, inputs, packs)
    for risk in risks.values():
        _verify_risk(risk, rows[risk.row_id], packs, inputs)
    graph = inputs.propagation_graph_revision
    if graph is not None:
        _verify_graph(graph, rows, packs, inputs)

    row_hashes = {row_id: row_hash for row_id, _version, row_hash in revision.row_versions}
    risk_hashes = {assessment_id: risk_hash for assessment_id, _version, risk_hash in revision.risk_versions}
    referenced_evidence: set[str] = set()
    for row in rows.values():
        referenced_evidence.update(evidence_id for _, ids in row.field_evidence for evidence_id in ids)
        referenced_evidence.update(claim_id for claim in row.field_claims for claim_id in claim.evidence_ids)
    for risk in risks.values():
        referenced_evidence.update(evidence_id for dimension in risk.dimensions for evidence_id in dimension.evidence_ids)
        if risk.derived is not None:
            referenced_evidence.update(risk.derived.evidence_ids)
    if graph is not None:
        referenced_evidence.update(evidence_id for edge in graph.edges for evidence_id in edge.evidence_ids)

    projected_rows = tuple(
        _project_row(rows[row_id], row_hashes[row_id]) for row_id in sorted(rows)
    )
    projected_risks = tuple(
        _project_risk_record(risks[assessment_id], risk_hashes[assessment_id])
        for assessment_id in sorted(risks)
    )
    projected_graph = None if graph is None else _project_graph(graph, rows)
    projected_reviews = _verify_reviews(tuple(review_records), rows, revision)
    authorities = tuple(record.authority for record in review_records)
    if any(authority is not None for authority in authorities) and any(authority is None for authority in authorities):
        _incomplete("review authority receipts must be complete")
    return PublicationBody(
        rows=projected_rows,
        risk_records=projected_risks,
        propagation=projected_graph,
        evidence_summary=_project_evidence(packs, referenced_evidence),
        decision_summary=projected_reviews,
        review_authorities=tuple(
            sorted(
                (authority for authority in authorities if authority is not None),
                key=lambda authority: authority.decision_id,
            )
        ),
    )


__all__ = ["PublicationBody", "PublicationReviewRecord"]
