"""Build the deterministic, offline FMEA propagation acceptance pack."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core_domain.fmea.propagation import (  # noqa: E402
    PropagationEdge,
    PropagationGraphRevision,
    PropagationPath,
    PropagationRulePack,
    TopologySnapshot,
    validate_graph_revision,
)
from core_domain.fmea.states import (  # noqa: E402
    ClaimStatus,
    EvidenceSupportStatus,
    PropagationStatus,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.fmea.value_objects import (  # noqa: E402
    EVIDENCE_LINEAGE_SCHEMA,
    EvidencePack,
    EvidenceRef,
    VersionSet,
    validate_evidence_lineage,
)
from fmea_infrastructure.domain_pack_registry import domain_pack_content_hash, load_domain_pack_manifest  # noqa: E402
from fmea_infrastructure.propagation_rule_registry import (  # noqa: E402
    canonical_propagation_rule_body,
    load_propagation_rule_pack,
    propagation_rule_content_hash,
)
from fmea_infrastructure.topology_json import JsonTopologyRepository, topology_snapshot_hash  # noqa: E402

SCHEMA_VERSION = "graphrag.fmea.propagation.acceptance.v1"
FIXTURE_SCHEMA_VERSION = "graphrag.fmea.propagation.fixture.v1"
CASE_IDS = ("forward", "reverse", "cycle", "conflict", "long_path")
EVIDENCE_PROFILES = (
    "rag_only",
    "graphrag_local_only",
    "graphrag_global_only",
    "graphrag_only",
    "combined",
    "auto",
    "custom",
)
ARTIFACT_NAMES = (
    "topology.json",
    "proposal.json",
    "reviewed-graph.json",
    "paths.json",
    "decisions.json",
    "issues.json",
    "audit-summary.json",
    "acceptance-summary.json",
)

_UTC = "2026-08-30T00:00:00Z"
_TOPOLOGY_PATH = ROOT / "domain_packs" / "fuel-combustion" / "topology" / "demo-1.0.0.json"
_TOPOLOGY_ROOT = _TOPOLOGY_PATH.parent
_RULE_PATH = ROOT / "domain_packs" / "fuel-combustion" / "propagation" / "fuel-combustion-1.0.0.yaml"
_DOMAIN_MANIFEST_PATH = ROOT / "domain_packs" / "fuel-combustion" / "manifest.yaml"
_FIXTURE_PATH = ROOT / "examples" / "fmea" / "propagation" / "fuel-combustion" / "fixtures.json"
_TOPOLOGY_SOURCE_HASH = "53559c5c6ed45e1a9e787a5452268cc5c1fc8259d0694459546162af418304e5"
_RULE_SOURCE_HASH = "a7d3c2299d977698fba37f0c4a5c5950fba3fc2bc8bc1b9ed0b651a0caefbf15"
_MANIFEST_SOURCE_HASH = "ae0badff0ed70914a6c989580998d2e06a3e05c8d6a42e2763e775cff6d81570"


class AcceptanceRunError(ValueError):
    """Stable runner failure without paths, input text, or provider details."""

    def __init__(self, code: str) -> None:
        super().__init__("FMEA propagation acceptance failed.")
        self.code = code


@dataclass(frozen=True, slots=True)
class AcceptanceRun(Mapping[str, object]):
    artifact_dir: Path
    summary: dict[str, object]
    artifact_bytes: tuple[bytes, ...]

    def __getitem__(self, key: str) -> object:
        return self.summary[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.summary)

    def __len__(self) -> int:
        return len(self.summary)


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _hash_bytes(_canonical_bytes(value))


def _json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


def _read_fixture() -> dict[str, Any]:
    try:
        value = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceRunError("FIXTURE_INVALID") from exc
    if not isinstance(value, dict) or value.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        raise AcceptanceRunError("FIXTURE_INVALID")
    return value


def _load_resources() -> tuple[TopologySnapshot, PropagationRulePack, dict[str, object], bytes]:
    try:
        source = _TOPOLOGY_PATH.read_bytes()
        rule_source = _RULE_PATH.read_bytes()
        manifest_source = _DOMAIN_MANIFEST_PATH.read_bytes()
        if sha256(source).hexdigest() != _TOPOLOGY_SOURCE_HASH or sha256(rule_source).hexdigest() != _RULE_SOURCE_HASH or sha256(manifest_source).hexdigest() != _MANIFEST_SOURCE_HASH:
            raise AcceptanceRunError("RESOURCE_PIN_MISMATCH")
        topology = JsonTopologyRepository(
            _TOPOLOGY_ROOT,
            source_hashes={("demo", "1.0.0"): _TOPOLOGY_SOURCE_HASH},
        ).load_snapshot("demo", "1.0.0")
        rule_pack = load_propagation_rule_pack(rule_source)
        manifest = load_domain_pack_manifest(manifest_source)
    except (OSError, ValueError, TypeError) as exc:
        raise AcceptanceRunError("RESOURCE_INVALID") from exc
    if manifest.pack_id != "fuel-combustion" or manifest.version != "1.0.0":
        raise AcceptanceRunError("RESOURCE_INVALID")
    if topology_snapshot_hash(topology) != topology.topology_hash:
        raise AcceptanceRunError("RESOURCE_INVALID")
    if domain_pack_content_hash(manifest) != manifest.content_hash:
        raise AcceptanceRunError("RESOURCE_INVALID")
    domain = {
        "id": manifest.pack_id,
        "version": manifest.version,
        "content_hash": manifest.content_hash,
    }
    return topology, rule_pack, domain, source


def _topology_payload(topology: TopologySnapshot) -> dict[str, object]:
    return {
        "id": topology.topology_snapshot_id,
        "workspace_id": topology.workspace_id,
        "analysis_id": topology.analysis_id,
        "topology_hash": topology.topology_hash,
        "nodes": [
            {"node_id": node.node_id, "node_type": node.node_type, "operating_modes": list(node.operating_modes)}
            for node in topology.nodes
        ],
        "interfaces": [
            {
                "interface_id": item.interface_id,
                "source_node_id": item.source_node_id,
                "target_node_id": item.target_node_id,
                "interface_variable": item.interface_variable,
                "unit": item.unit,
                "direction": item.direction,
                "operating_modes": list(item.operating_modes),
            }
            for item in topology.interfaces
        ],
        "record_version": topology.record_version,
        "created_at": topology.created_at,
    }


def _rule_payload(rule_pack: PropagationRulePack) -> dict[str, object]:
    return json.loads(canonical_propagation_rule_body(rule_pack))


def _version_payload(profile: str) -> dict[str, object]:
    return {
        "schema_id": "graphrag.fmea.v1",
        "data_version": "propagation-fixture-v1",
        "graph_version": "fuel-combustion-propagation-v1",
        "evidence_pack_version": "1.0.0",
        "profile_version": profile,
        "template_version": "fmea-propagation-hypothesis@1.0.0",
        "scoring_version": "fuel-sod-rpn@1.0.0",
        "prompt_version": "offline-fixture-v1",
        "model_version": "deterministic-offline-model-v1",
        "input_snapshot_hash": sha256((profile + "|propagation-fixture-v1").encode("utf-8")).hexdigest(),
    }


def _evidence_ref(raw: Mapping[str, object]) -> EvidenceRef:
    evidence_id = raw.get("evidence_id")
    source_type = raw.get("source_type")
    quote = raw.get("quote")
    document_id = raw.get("document_id")
    locator = raw.get("locator")
    if not all(isinstance(value, str) and value.strip() for value in (evidence_id, source_type, quote, document_id, locator)):
        raise AcceptanceRunError("FIXTURE_INVALID")
    source_type_map = {"text": "primary_document", "graph": "graphrag_relation", "community": "graphrag_community"}
    if source_type not in source_type_map:
        raise AcceptanceRunError("FIXTURE_INVALID")
    return EvidenceRef(
        evidence_id=evidence_id,
        workspace_id="fuel-combustion",
        document_id=document_id,
        document_version="fixture-v1",
        content_hash=sha256(quote.encode("utf-8")).hexdigest(),
        locator=locator,
        quote=quote,
        normalized_quote=quote,
        evidence_hash=sha256((evidence_id + "|" + quote).encode("utf-8")).hexdigest(),
        acl_scope=("acceptance",),
        source_type=source_type_map[source_type],
        source_trust="reviewed",
        is_primary=source_type == "text",
        created_at=_UTC,
        expires_at=None,
    )


def _evidence_ref_payload(ref: EvidenceRef) -> dict[str, object]:
    return {
        "evidence_id": ref.evidence_id,
        "workspace_id": ref.workspace_id,
        "document_id": ref.document_id,
        "document_version": ref.document_version,
        "content_hash": ref.content_hash,
        "locator": ref.locator,
        "quote": ref.quote,
        "normalized_quote": ref.normalized_quote,
        "evidence_hash": ref.evidence_hash,
        "acl_scope": list(ref.acl_scope),
        "source_type": ref.source_type,
        "source_trust": ref.source_trust,
        "is_primary": ref.is_primary,
        "created_at": ref.created_at,
        "expires_at": ref.expires_at,
    }


def _pack_payload(pack: EvidencePack) -> dict[str, object]:
    return {
        "pack_id": pack.pack_id,
        "workspace_id": pack.workspace_id,
        "acl_scope": list(pack.acl_scope),
        "versions": _json_value(pack.versions.__dict__) if hasattr(pack.versions, "__dict__") else {
            "schema_id": pack.versions.schema_id,
            "data_version": pack.versions.data_version,
            "graph_version": pack.versions.graph_version,
            "evidence_pack_version": pack.versions.evidence_pack_version,
            "profile_version": pack.versions.profile_version,
            "template_version": pack.versions.template_version,
            "scoring_version": pack.versions.scoring_version,
            "prompt_version": pack.versions.prompt_version,
            "model_version": pack.versions.model_version,
            "input_snapshot_hash": pack.versions.input_snapshot_hash,
        },
        "refs": [_evidence_ref_payload(ref) for ref in pack.refs],
        "pack_hash": pack.pack_hash,
        "created_at": pack.created_at,
        "expires_at": pack.expires_at,
        "lineage": {
            "parent_pack_refs": [
                {"pack_id": pack_id, "pack_hash": pack_hash} for pack_id, pack_hash in pack.parent_pack_refs
            ],
            "lineage_reason": pack.lineage_reason,
            "lineage_schema_version": pack.lineage_schema_version,
        },
    }


def _build_evidence_packs(fixture: Mapping[str, object]) -> tuple[dict[str, EvidencePack], dict[str, object]]:  # noqa: C901
    raw_profiles = fixture.get("profiles")
    raw_evidence = fixture.get("evidence")
    if not isinstance(raw_profiles, dict) or not isinstance(raw_evidence, list):
        raise AcceptanceRunError("FIXTURE_INVALID")
    refs_by_type: dict[str, EvidenceRef] = {}
    for raw in raw_evidence:
        if not isinstance(raw, dict):
            raise AcceptanceRunError("FIXTURE_INVALID")
        ref = _evidence_ref(raw)
        refs_by_type[str(raw["source_type"])] = ref
    unique_pack_profiles: list[tuple[str, str]] = []
    for profile in EVIDENCE_PROFILES:
        raw = raw_profiles.get(profile)
        if not isinstance(raw, dict):
            raise AcceptanceRunError("FIXTURE_INVALID")
        pack_id = raw.get("pack_id")
        if not isinstance(pack_id, str) or (pack_id, profile) not in unique_pack_profiles:
            if not isinstance(pack_id, str):
                raise AcceptanceRunError("FIXTURE_INVALID")
            if pack_id not in {item[0] for item in unique_pack_profiles}:
                unique_pack_profiles.append((pack_id, profile))
    packs: dict[str, EvidencePack] = {}
    for pack_id, profile in unique_pack_profiles:
        raw = raw_profiles[profile]
        evidence_types = raw.get("evidence_types")
        parents = raw.get("parents")
        if not isinstance(evidence_types, list) or not isinstance(parents, list):
            raise AcceptanceRunError("FIXTURE_INVALID")
        try:
            refs = tuple(refs_by_type[str(item)] for item in evidence_types)
            parent_refs = tuple((str(parent), packs[str(parent)].pack_hash) for parent in parents)
            pack = EvidencePack.build(
                pack_id=pack_id,
                workspace_id="fuel-combustion",
                acl_scope=("acceptance",),
                versions=VersionSet(**_version_payload(profile)),
                refs=refs,
                created_at=_UTC,
                expires_at=None,
                parent_pack_refs=parent_refs,
                lineage_reason="deterministic evidence profile composition" if parent_refs else None,
                lineage_schema_version=EVIDENCE_LINEAGE_SCHEMA if parent_refs else None,
            )
            validate_evidence_lineage(pack, packs)
        except (KeyError, TypeError, ValueError) as exc:
            raise AcceptanceRunError("FIXTURE_INVALID") from exc
        packs[pack_id] = pack
    profiles_payload = {
        profile: {
            "requested_profile": profile,
            "resolved_profile": str(raw_profiles[profile]["resolved_profile"]),
            "evidence_types": list(raw_profiles[profile]["evidence_types"]),
            "evidence_pack_id": str(raw_profiles[profile]["pack_id"]),
            "evidence_pack_hash": packs[str(raw_profiles[profile]["pack_id"])].pack_hash,
            "retrieval_incomplete": False,
        }
        for profile in EVIDENCE_PROFILES
    }
    return packs, profiles_payload


def _find_interface(topology: TopologySnapshot, source: str, target: str) -> Any:
    return next(
        (item for item in topology.interfaces if item.source_node_id == source and item.target_node_id == target),
        None,
    )


def _edge(
    raw: Mapping[str, object],
    *,
    case_id: str,
    analysis_id: str,
    topology: TopologySnapshot,
    evidence_pack_id: str,
    path_length: int,
) -> PropagationEdge:
    source = raw.get("source_entity_id")
    target = raw.get("target_entity_id")
    interface = _find_interface(topology, str(source), str(target))
    if interface is None:
        raise AcceptanceRunError("FIXTURE_INVALID")
    try:
        return PropagationEdge(
            edge_id=str(raw["edge_id"]),
            analysis_id=analysis_id,
            source_entity_id=str(source),
            target_entity_id=str(target),
            relation_type="propagation",
            interface_variable=interface.interface_variable,
            unit=interface.unit,
            direction=interface.direction,
            threshold="fixture-bound",
            operating_modes=("steady_state",),
            delay_ms=10,
            response_time_ms=25,
            fault_tolerance_time_ms=100,
            barrier_ids=(),
            evidence_pack_id=evidence_pack_id,
            evidence_ids=tuple(str(item) for item in raw["evidence_ids"]),
            evidence_support=EvidenceSupportStatus(str(raw["evidence_support"])),
            claim_status=ClaimStatus(str(raw["claim_status"])),
            review_status=ReviewStatus.SUGGESTED,
            publication_status=PublicationStatus.UNPUBLISHED,
            path_length=path_length,
            is_cyclic=bool(raw["is_cyclic"]),
            is_unprocessed=bool(raw["is_unprocessed"]),
            is_external=bool(raw["is_external"]),
            is_terminal=bool(raw["is_terminal"]),
            risk_priority=str(raw["risk_priority"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AcceptanceRunError("FIXTURE_INVALID") from exc


def _edge_payload(edge: PropagationEdge, case_id: str) -> dict[str, object]:
    return {
        "edge_id": edge.edge_id,
        "case_id": case_id,
        "analysis_id": edge.analysis_id,
        "source_entity_id": edge.source_entity_id,
        "target_entity_id": edge.target_entity_id,
        "relation_type": edge.relation_type,
        "interface_variable": edge.interface_variable,
        "unit": edge.unit,
        "direction": edge.direction,
        "threshold": edge.threshold,
        "operating_modes": list(edge.operating_modes),
        "delay_ms": edge.delay_ms,
        "response_time_ms": edge.response_time_ms,
        "fault_tolerance_time_ms": edge.fault_tolerance_time_ms,
        "barrier_ids": list(edge.barrier_ids),
        "evidence_pack_id": edge.evidence_pack_id,
        "evidence_ids": list(edge.evidence_ids),
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


def _case_issue_codes(edges: tuple[PropagationEdge, ...], path: PropagationPath) -> tuple[str, ...]:
    codes: set[str] = set()
    if path.path_length > 2:
        codes.add("long_path")
    if path.is_cyclic:
        codes.add("cyclic")
    if any(edge.risk_priority in {"high", "critical"} for edge in edges):
        codes.add("high_risk")
    if any(edge.is_external for edge in edges):
        codes.add("external")
    if any(edge.is_unprocessed for edge in edges):
        codes.add("incomplete")
    if any(edge.claim_status is ClaimStatus.CONFLICT for edge in edges):
        codes.add("conflicting")
    if any(not edge.evidence_ids or edge.evidence_support in {EvidenceSupportStatus.CONTRADICTED, EvidenceSupportStatus.NOT_SUPPORTED} for edge in edges):
        codes.add("evidence_gap")
    return tuple(sorted(codes))


def _graph_hash(graph: dict[str, object]) -> str:
    body = {key: value for key, value in graph.items() if key != "graph_hash"}
    return _hash_json(body)


def _build_artifacts() -> dict[str, object]:  # noqa: C901
    fixture = _read_fixture()
    topology, rule_pack, domain, topology_source = _load_resources()
    if fixture.get("workspace_id") != topology.workspace_id:
        raise AcceptanceRunError("FIXTURE_INVALID")
    analysis_id = fixture.get("analysis_id")
    if not isinstance(analysis_id, str) or not analysis_id:
        raise AcceptanceRunError("FIXTURE_INVALID")
    packs, profiles_payload = _build_evidence_packs(fixture)
    raw_cases = fixture.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != len(CASE_IDS):
        raise AcceptanceRunError("FIXTURE_INVALID")

    all_proposal_edges: list[dict[str, object]] = []
    all_reviewed_edges: list[dict[str, object]] = []
    issue_payloads: list[dict[str, object]] = []
    decision_payloads: list[dict[str, object]] = []
    proposal_edges: list[PropagationEdge] = []
    reviewed_edges: list[PropagationEdge] = []
    paths: list[PropagationPath] = []
    seen_cases: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise AcceptanceRunError("FIXTURE_INVALID")
        case_id = raw_case.get("case_id")
        raw_edge_values = raw_case.get("edges")
        if not isinstance(case_id, str) or case_id in seen_cases or case_id not in CASE_IDS or not isinstance(raw_edge_values, list) or not raw_edge_values:
            raise AcceptanceRunError("FIXTURE_INVALID")
        seen_cases.add(case_id)
        path_length = len(raw_edge_values)
        case_proposal_edges = tuple(
            _edge(
                raw_edge,
                case_id=case_id,
                analysis_id=analysis_id,
                topology=topology,
                evidence_pack_id="pack-combined",
                path_length=path_length,
            )
            for raw_edge in raw_edge_values
            if isinstance(raw_edge, dict)
        )
        if len(case_proposal_edges) != len(raw_edge_values):
            raise AcceptanceRunError("FIXTURE_INVALID")
        case_reviewed_edges = tuple(
            replace(
                edge,
                review_status=(
                    ReviewStatus.ACCEPTED if case_id in {"forward", "reverse"} else ReviewStatus.IN_REVIEW
                ),
            )
            for edge in case_proposal_edges
        )
        case_path = PropagationPath(
            path_id=f"path-{case_id}",
            analysis_id=analysis_id,
            source_entity_id=case_reviewed_edges[0].source_entity_id,
            target_entity_id=case_reviewed_edges[-1].target_entity_id,
            edges=case_reviewed_edges,
            path_length=path_length,
            is_cyclic=case_id == "cycle",
            requires_human_review=case_id not in {"forward", "reverse"},
        )
        proposal_edges.extend(case_proposal_edges)
        reviewed_edges.extend(case_reviewed_edges)
        paths.append(case_path)
        all_proposal_edges.extend(_edge_payload(edge, case_id) for edge in case_proposal_edges)
        all_reviewed_edges.extend(_edge_payload(edge, case_id) for edge in case_reviewed_edges)
        codes = _case_issue_codes(case_reviewed_edges, case_path)
        requires_review = bool(codes)
        issue_payloads.extend(
            {
                "issue_id": f"issue-{case_id}-{index}",
                "case_id": case_id,
                "code": code,
                "severity": "important",
                "edge_ids": [edge.edge_id for edge in case_reviewed_edges],
                "requires_human_review": requires_review,
            }
            for index, code in enumerate(codes, start=1)
        )
        confirmed = case_id in {"forward", "reverse"}
        decision_payloads.append(
            {
                "decision_id": f"decision-{case_id}",
                "case_id": case_id,
                "edge_ids": [edge.edge_id for edge in case_reviewed_edges],
                "action": "confirm" if confirmed else "retain_for_human_review",
                "confirmed": confirmed,
                "actor": {
                    "actor_id": "propagation-reviewer-1",
                    "actor_type": "human",
                    "roles": ["propagation_reviewer"],
                },
                "reason": "deterministic acceptance fixture review",
                "expected_graph_record_version": 1,
                "applied_graph_record_version": 2 if confirmed else 1,
            }
        )
    if seen_cases != set(CASE_IDS):
        raise AcceptanceRunError("FIXTURE_INVALID")

    resolution = (packs["pack-combined"],)
    proposal_graph = PropagationGraphRevision(
        graph_revision_id="graph-proposal-1",
        workspace_id=topology.workspace_id,
        analysis_id=analysis_id,
        analysis_record_version=1,
        topology_snapshot_id=topology.topology_snapshot_id,
        topology_hash=topology.topology_hash,
        evidence_pack_ids=("pack-combined",),
        domain_pack_id=domain["id"],
        domain_pack_version=domain["version"],
        rule_pack_id=rule_pack.rule_pack_id,
        rule_pack_version=rule_pack.version,
        status=PropagationStatus.PROPOSED,
        assistance_suggestion_ids=("suggestion-propagation-offline",),
        nodes=topology.nodes,
        edges=tuple(proposal_edges),
        paths=tuple(
            PropagationPath(
                path_id=path.path_id,
                analysis_id=path.analysis_id,
                source_entity_id=path.source_entity_id,
                target_entity_id=path.target_entity_id,
                edges=tuple(proposal_edges_by_id for proposal_edges_by_id in proposal_edges if any(item.edge_id == proposal_edges_by_id.edge_id for item in path.edges)),
                path_length=path.path_length,
                is_cyclic=path.is_cyclic,
                requires_human_review=path.requires_human_review,
            )
            for path in paths
        ),
        unresolved_issue_codes=tuple(sorted({item["code"] for item in issue_payloads})),
        parent_graph_revision_id=None,
        record_version=1,
        created_at=_UTC,
    )
    try:
        validate_graph_revision(proposal_graph, topology, rule_pack, resolution)
    except Exception as exc:
        raise AcceptanceRunError("FIXTURE_INVALID") from exc

    graph = {
        "schema_version": SCHEMA_VERSION,
        "resource_type": "propagation_reviewed_graph",
        "graph_revision_id": "graph-reviewed-1",
        "workspace_id": topology.workspace_id,
        "analysis_id": analysis_id,
        "analysis_record_version": 1,
        "topology_snapshot_id": topology.topology_snapshot_id,
        "topology_hash": topology.topology_hash,
        "domain_pack": domain,
        "rule_pack": {"id": rule_pack.rule_pack_id, "version": rule_pack.version, "hash": propagation_rule_content_hash(rule_pack)},
        "evidence_pack_ids": ["pack-combined"],
        "assistance_suggestion_ids": ["suggestion-propagation-offline"],
        "status": "reviewed",
        "record_version": 1,
        "nodes": [
            {"node_id": node.node_id, "node_type": node.node_type, "operating_modes": list(node.operating_modes)}
            for node in topology.nodes
        ],
        "edges": all_reviewed_edges,
        "accepted_case_ids": ["forward", "reverse"],
        "human_review_case_ids": ["cycle", "conflict", "long_path"],
        "graph_hash": "",
    }
    graph["graph_hash"] = _graph_hash(graph)

    proposal = {
        "schema_version": SCHEMA_VERSION,
        "resource_type": "propagation_proposal",
        "actor": {"actor_id": "deterministic-offline-model", "actor_type": "model"},
        "lineage": {
            "workspace_id": topology.workspace_id,
            "analysis_id": analysis_id,
            "topology_snapshot_id": topology.topology_snapshot_id,
            "topology_hash": topology.topology_hash,
            "domain_pack_id": domain["id"],
            "domain_pack_version": domain["version"],
            "rule_pack_id": rule_pack.rule_pack_id,
            "rule_pack_version": rule_pack.version,
            "evidence_pack_ids": ["pack-combined"],
        },
        "case_ids": list(CASE_IDS),
        "edges": all_proposal_edges,
    }
    paths_artifact = {
        "schema_version": SCHEMA_VERSION,
        "resource_type": "propagation_paths",
        "graph_revision_id": graph["graph_revision_id"],
        "paths": [
            {
                "path_id": path.path_id,
                "case_id": next(case for case in CASE_IDS if path.path_id == f"path-{case}"),
                "analysis_id": path.analysis_id,
                "source_entity_id": path.source_entity_id,
                "target_entity_id": path.target_entity_id,
                "edge_ids": [edge.edge_id for edge in path.edges],
                "edges": [_edge_payload(edge, next(case for case in CASE_IDS if path.path_id == f"path-{case}")) for edge in path.edges],
                "path_length": path.path_length,
                "is_cyclic": path.is_cyclic,
                "requires_human_review": path.requires_human_review,
            }
            for path in paths
        ],
    }
    decisions = {"schema_version": SCHEMA_VERSION, "resource_type": "propagation_decisions", "graph_revision_id": graph["graph_revision_id"], "decisions": decision_payloads}
    issues = {"schema_version": SCHEMA_VERSION, "resource_type": "propagation_issues", "graph_revision_id": graph["graph_revision_id"], "issues": issue_payloads}
    events: list[dict[str, object]] = []
    for case_id in CASE_IDS:
        events.append(
            {
                "event_id": f"event-proposal-{case_id}",
                "event_type": "propagation.proposed",
                "actor_id": "deterministic-offline-model",
                "actor_type": "model",
                "case_id": case_id,
                "resource_id": f"path-{case_id}",
            }
        )
        decision = next(item for item in decision_payloads if item["case_id"] == case_id)
        events.append(
            {
                "event_id": f"event-review-{case_id}",
                "event_type": "propagation.confirmed" if decision["confirmed"] else "propagation.review_required",
                "actor_id": "propagation-reviewer-1",
                "actor_type": "human",
                "case_id": case_id,
                "resource_id": decision["decision_id"],
            }
        )
    audit = {
        "schema_version": SCHEMA_VERSION,
        "resource_type": "propagation_audit_summary",
        "events": [{**event, "event_hash": _hash_json(event)} for event in events],
        "model_proposal_count": len(CASE_IDS),
        "model_confirmation_count": 0,
        "human_confirmation_count": 2,
        "human_review_required_count": 3,
    }
    topology_artifact = {
        "schema_version": SCHEMA_VERSION,
        "resource_type": "propagation_topology",
        "workspace_id": topology.workspace_id,
        "analysis_id": analysis_id,
        "domain_pack": domain,
        "topology_source_hash": _hash_bytes(topology_source),
        "topology_snapshot": _topology_payload(topology),
        "rule_pack": _rule_payload(rule_pack),
        "rule_pack_hash": propagation_rule_content_hash(rule_pack),
        "evidence_selection_profiles": profiles_payload,
        "evidence_packs": [_pack_payload(packs[pack_id]) for pack_id in sorted(packs)],
    }
    return {
        "topology.json": topology_artifact,
        "proposal.json": proposal,
        "reviewed-graph.json": graph,
        "paths.json": paths_artifact,
        "decisions.json": decisions,
        "issues.json": issues,
        "audit-summary.json": audit,
    }


def _safe_existing_components(path: Path) -> bool:
    absolute = path.absolute()
    anchor_parts = Path(absolute.anchor).parts if absolute.anchor else ()
    current = Path(absolute.anchor) if absolute.anchor else Path()
    for part in absolute.parts[len(anchor_parts) :]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return False
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            return False
    return True


def _require_artifact_mappings(artifacts: Mapping[str, object]) -> None:
    if not all(isinstance(artifacts[name], dict) for name in ARTIFACT_NAMES[:-1]):
        raise AcceptanceRunError("ARTIFACT_BUILD_INVALID")


def _safe_output_directory(output_root: str | Path) -> Path:
    final = Path(output_root).expanduser().absolute()
    if final.exists() or final.is_symlink():
        raise AcceptanceRunError("OUTPUT_EXISTS")
    parent = final.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AcceptanceRunError("OUTPUT_ROOT_INVALID") from exc
    if not _safe_existing_components(parent):
        raise AcceptanceRunError("OUTPUT_ROOT_INVALID")
    return final


def run_acceptance(output_root: str | Path | None = None) -> AcceptanceRun:
    requested = Path(output_root) if output_root is not None else _default_output_root() / _timestamp()
    if requested.exists() and requested.is_dir() and not requested.is_symlink():
        target = requested / _timestamp()
    else:
        target = requested
    final = _safe_output_directory(target)
    temporary = Path(tempfile.mkdtemp(prefix=f".{final.name}.tmp-", dir=final.parent))
    try:
        artifacts = _build_artifacts()
        for name in ARTIFACT_NAMES[:-1]:
            (temporary / name).write_bytes(_canonical_bytes(artifacts[name]))
        graph = artifacts["reviewed-graph.json"]
        topology = artifacts["topology.json"]
        decisions = artifacts["decisions.json"]
        paths = artifacts["paths.json"]
        issues = artifacts["issues.json"]
        audit = artifacts["audit-summary.json"]
        _require_artifact_mappings(artifacts)
        decision_items = decisions["decisions"]
        path_items = paths["paths"]
        issue_items = issues["issues"]
        audit_events = audit["events"]
        summary = {
            "schema_version": SCHEMA_VERSION,
            "resource_type": "propagation_acceptance_summary",
            "status": "passed",
            "case_ids": list(CASE_IDS),
            "evidence_profiles": list(EVIDENCE_PROFILES),
            "topology_hash": topology["topology_snapshot"]["topology_hash"],
            "rule_pack_hash": topology["rule_pack_hash"],
            "graph_hash": graph["graph_hash"],
            "edge_count": len(graph["edges"]),
            "path_count": len(path_items),
            "issue_count": len(issue_items),
            "decision_count": len(decision_items),
            "audit_event_count": len(audit_events),
            "invented_endpoint_count": 0,
            "model_confirmation_count": 0,
            "human_confirmation_count": sum(1 for item in decision_items if item["confirmed"]),
            "human_review_required_count": sum(1 for item in decision_items if not item["confirmed"]),
            "artifact_hashes": {
                name: _hash_bytes((temporary / name).read_bytes()) for name in ARTIFACT_NAMES[:-1]
            },
        }
        (temporary / "acceptance-summary.json").write_bytes(_canonical_bytes(summary))
        os.replace(temporary, final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    artifact_bytes = tuple((final / name).read_bytes() for name in ARTIFACT_NAMES)
    return AcceptanceRun(final, summary, artifact_bytes)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _default_output_root() -> Path:
    return ROOT / ".local" / "fmea-propagation-acceptance"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--output-root", default=str(_default_output_root()))
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        result = run_acceptance(Path(args.output_root) / _timestamp())
        sys.stdout.write(json.dumps({"status": "passed", "output_directory": str(result.artifact_dir)}, separators=(",", ":")) + "\n")
    except Exception:
        sys.stdout.write(json.dumps({"status": "failed", "error": {"code": "FMEA_PROPAGATION_ACCEPTANCE_FAILED"}}, separators=(",", ":")) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_NAMES",
    "CASE_IDS",
    "EVIDENCE_PROFILES",
    "SCHEMA_VERSION",
    "AcceptanceRun",
    "AcceptanceRunError",
    "main",
    "run_acceptance",
]
