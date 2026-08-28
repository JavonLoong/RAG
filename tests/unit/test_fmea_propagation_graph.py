from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace

import pytest

import core_domain.fmea.propagation as propagation_module
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.propagation import (
    PropagationEdge,
    PropagationEvidenceResolution,
    PropagationGraphRevision,
    PropagationPath,
    PropagationRulePack,
    TopologyInterface,
    TopologyNode,
    TopologySnapshot,
    validate_graph_revision,
    validate_path,
)
from core_domain.fmea.states import (
    FMEA_SCHEMA_ID,
    ClaimStatus,
    EvidenceSupportStatus,
    PropagationStatus,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet


def node(node_id: str, *, node_type: str = "equipment") -> TopologyNode:
    return TopologyNode(node_id=node_id, node_type=node_type, operating_modes=("startup", "steady_state"))


def interface(
    source: str,
    target: str,
    *,
    variable: str = "fuel_pressure",
    unit: str = "kPa",
    direction: str = "fuel_to_combustion",
    operating_modes: tuple[str, ...] = ("startup",),
) -> TopologyInterface:
    return TopologyInterface(
        interface_id=f"{source}->{target}",
        source_node_id=source,
        target_node_id=target,
        interface_variable=variable,
        unit=unit,
        direction=direction,
        operating_modes=operating_modes,
    )


def topology_snapshot(
    *,
    nodes: tuple[TopologyNode, ...],
    interfaces: tuple[TopologyInterface, ...] = (),
    workspace_id: str = "ws-1",
    analysis_id: str = "analysis-1",
) -> TopologySnapshot:
    return TopologySnapshot(
        topology_snapshot_id="topology-1",
        workspace_id=workspace_id,
        analysis_id=analysis_id,
        topology_hash="a" * 64,
        nodes=nodes,
        interfaces=interfaces,
        record_version=1,
        created_at="2026-08-28T00:00:00Z",
    )


def propagation_edge(
    *,
    source: str = "pump",
    target: str = "manifold",
    analysis_id: str = "analysis-1",
    evidence_pack_id: str = "pack-1",
    evidence_ids: tuple[str, ...] = ("E1",),
    interface_variable: str = "fuel_pressure",
    unit: str = "kPa",
    direction: str = "fuel_to_combustion",
    operating_modes: tuple[str, ...] = ("startup",),
    delay_ms: int | None = 100,
    response_time_ms: int | None = 200,
    fault_tolerance_time_ms: int | None = 500,
    path_length: int = 1,
    is_cyclic: bool = False,
    is_terminal: bool = True,
) -> PropagationEdge:
    return PropagationEdge(
        edge_id=f"{source}->{target}",
        analysis_id=analysis_id,
        source_entity_id=source,
        target_entity_id=target,
        relation_type="propagation",
        interface_variable=interface_variable,
        unit=unit,
        direction=direction,
        threshold="<250",
        operating_modes=operating_modes,
        delay_ms=delay_ms,
        response_time_ms=response_time_ms,
        fault_tolerance_time_ms=fault_tolerance_time_ms,
        barrier_ids=("trip-1",),
        evidence_pack_id=evidence_pack_id,
        evidence_ids=evidence_ids,
        evidence_support=EvidenceSupportStatus.SUPPORTED if evidence_ids else EvidenceSupportStatus.NOT_SUPPORTED,
        claim_status=ClaimStatus.KNOWN if evidence_ids else ClaimStatus.INSUFFICIENT_EVIDENCE,
        review_status=ReviewStatus.SUGGESTED,
        publication_status=PublicationStatus.UNPUBLISHED,
        path_length=path_length,
        is_cyclic=is_cyclic,
        is_unprocessed=False,
        is_external=False,
        is_terminal=is_terminal,
        risk_priority="normal",
    )


def propagation_rules(**changes: object) -> PropagationRulePack:
    values: dict[str, object] = {
        "rule_pack_id": "propagation-rules",
        "version": "1.0.0",
        "applicable_analysis_types": ("fuel_system",),
        "relation_types": ("propagation",),
        "interface_variables": ("fuel_pressure",),
        "units": ("kPa",),
        "directions": ("fuel_to_combustion",),
        "max_automatic_depth": 2,
        "mandatory_review_conditions": ("long_path", "cyclic", "high_risk", "external", "evidence_gap"),
        "barrier_semantics": "barriers are explicit controls",
        "risk_escalation": "high_and_critical_require_review",
        "prohibit_silent_fallback": True,
    }
    values.update(changes)
    return PropagationRulePack(**values)


def propagation_path(*, edges: tuple[PropagationEdge, ...], **changes: object) -> PropagationPath:
    values: dict[str, object] = {
        "path_id": "path-1",
        "analysis_id": "analysis-1",
        "source_entity_id": edges[0].source_entity_id,
        "target_entity_id": edges[-1].target_entity_id,
        "edges": edges,
        "path_length": len(edges),
        "is_cyclic": any(edge.is_cyclic for edge in edges),
        "requires_human_review": False,
    }
    values.update(changes)
    return PropagationPath(**values)


def graph_revision(
    *,
    edges: tuple[PropagationEdge, ...],
    paths: tuple[PropagationPath, ...] = (),
    **changes: object,
) -> PropagationGraphRevision:
    values: dict[str, object] = {
        "graph_revision_id": "graph-1",
        "workspace_id": "ws-1",
        "analysis_id": "analysis-1",
        "analysis_record_version": 1,
        "topology_snapshot_id": "topology-1",
        "topology_hash": "a" * 64,
        "evidence_pack_ids": ("pack-1",),
        "domain_pack_id": "fuel-combustion",
        "domain_pack_version": "1.0.0",
        "rule_pack_id": "propagation-rules",
        "rule_pack_version": "1.0.0",
        "status": PropagationStatus.PROPOSED,
        "assistance_suggestion_ids": (),
        "nodes": (),
        "edges": edges,
        "paths": paths,
        "unresolved_issue_codes": (),
        "parent_graph_revision_id": None,
        "record_version": 1,
        "created_at": "2026-08-28T00:00:00Z",
    }
    values.update(changes)
    return PropagationGraphRevision(**values)


def evidence_pack(*evidence_ids: str, workspace_id: str = "ws-1", pack_id: str = "pack-1") -> EvidencePack:
    versions = VersionSet(
        schema_id=FMEA_SCHEMA_ID,
        data_version="data-1",
        graph_version="graph-1",
        evidence_pack_version="evidence-1",
        profile_version="profile-1",
        template_version="template-1",
        scoring_version="score-1",
        prompt_version="prompt-0",
        model_version="model-0",
        input_snapshot_hash="d" * 64,
    )
    refs = tuple(
        EvidenceRef(
            evidence_id=evidence_id,
            workspace_id=workspace_id,
            document_id=f"doc-{evidence_id}",
            document_version="doc-v1",
            content_hash="e" * 64,
            locator=f"page:{index + 1}",
            quote="pressure is low",
            normalized_quote="pressure is low",
            evidence_hash=f"{index + 1:064x}",
            acl_scope=("engineering",),
            source_type="primary_document",
            source_trust="reviewed",
            is_primary=True,
            created_at="2026-08-28T00:00:00Z",
            expires_at=None,
        )
        for index, evidence_id in enumerate(evidence_ids)
    )
    return EvidencePack.build(
        pack_id=pack_id,
        workspace_id=workspace_id,
        acl_scope=("engineering",),
        versions=versions,
        refs=refs,
        created_at="2026-08-28T00:00:00Z",
        expires_at=None,
    )


def test_propagation_status_values_are_orthogonal_and_closed() -> None:
    assert [item.value for item in PropagationStatus] == [
        "not_analyzed",
        "proposed",
        "reviewed",
        "confirmed",
        "invalidated",
    ]


def test_rule_pack_defaults_to_two_hop_automatic_search() -> None:
    rule_pack = PropagationRulePack(
        rule_pack_id="propagation-rules",
        version="1.0.0",
        applicable_analysis_types=("fuel_system",),
        relation_types=("propagation",),
        interface_variables=("fuel_pressure",),
        units=("kPa",),
        directions=("fuel_to_combustion",),
    )
    assert rule_pack.max_automatic_depth == 2
    assert rule_pack.prohibit_silent_fallback is True


def test_graph_rejects_edge_endpoint_outside_topology() -> None:
    topology = topology_snapshot(nodes=(node("pump"), node("manifold")))
    edge = propagation_edge(source="pump", target="combustor")
    with pytest.raises(FmeaDomainError, match="endpoint is outside topology"):
        validate_graph_revision(graph_revision(edges=(edge,)), topology, propagation_rules())


def test_one_evidence_reference_cannot_implicitly_support_two_edges() -> None:
    path = propagation_path(
        edges=(
            propagation_edge(source="pump", target="nozzle", evidence_ids=("E1",)),
            propagation_edge(source="nozzle", target="flame", evidence_ids=()),
        ),
    )
    with pytest.raises(FmeaDomainError, match="edge evidence is required"):
        validate_path(path, evidence_pack("E1"), propagation_rules())


def test_graph_validates_interface_variable_unit_direction_and_mode() -> None:
    topology = topology_snapshot(
        nodes=(node("pump"), node("manifold")),
        interfaces=(interface("pump", "manifold"),),
    )
    validate_graph_revision(
        graph_revision(edges=(propagation_edge(),)),
        topology,
        propagation_rules(),
        evidence_packs=PropagationEvidenceResolution(packs=(evidence_pack("E1"),)),
    )

    with pytest.raises(FmeaDomainError, match="interface_variable"):
        validate_graph_revision(
            graph_revision(edges=(propagation_edge(interface_variable="temperature"),)),
            topology,
            propagation_rules(),
        )

    with pytest.raises(FmeaDomainError, match="unit"):
        validate_graph_revision(
            graph_revision(edges=(propagation_edge(unit="bar"),)),
            topology,
            propagation_rules(),
        )

    with pytest.raises(FmeaDomainError, match="direction"):
        validate_graph_revision(
            graph_revision(edges=(propagation_edge(direction="combustion_to_fuel"),)),
            topology,
            propagation_rules(),
        )

    with pytest.raises(FmeaDomainError, match="operating mode"):
        validate_graph_revision(
            graph_revision(edges=(propagation_edge(operating_modes=("shutdown",)),)),
            topology,
            propagation_rules(),
        )


def test_graph_rejects_edge_from_a_different_analysis() -> None:
    topology = topology_snapshot(
        nodes=(node("pump"), node("manifold")),
        interfaces=(interface("pump", "manifold"),),
    )
    with pytest.raises(FmeaDomainError, match="analysis_id"):
        validate_graph_revision(
            graph_revision(edges=(propagation_edge(analysis_id="other-analysis"),)),
            topology,
            propagation_rules(),
        )


def test_graph_requires_edge_modes_to_match_endpoint_node_modes() -> None:
    topology = topology_snapshot(
        nodes=(
            TopologyNode(node_id="pump", node_type="equipment", operating_modes=("startup",)),
            TopologyNode(node_id="manifold", node_type="equipment", operating_modes=("steady_state",)),
        ),
        interfaces=(interface("pump", "manifold"),),
    )
    with pytest.raises(FmeaDomainError, match="operating mode"):
        validate_graph_revision(graph_revision(edges=(propagation_edge(),)), topology, propagation_rules())


@pytest.mark.parametrize("field_name", ("delay_ms", "response_time_ms", "fault_tolerance_time_ms"))
def test_graph_rejects_negative_timing(field_name: str) -> None:
    topology = topology_snapshot(
        nodes=(node("pump"), node("manifold")),
        interfaces=(interface("pump", "manifold"),),
    )
    edge = propagation_edge(**{field_name: -1})
    with pytest.raises(FmeaDomainError, match="timing"):
        validate_graph_revision(graph_revision(edges=(edge,)), topology, propagation_rules())


def test_path_requires_continuity_and_exact_length() -> None:
    first = propagation_edge(source="pump", target="nozzle")
    second = propagation_edge(source="manifold", target="flame")
    path = propagation_path(edges=(first, second))
    with pytest.raises(FmeaDomainError, match="path continuity"):
        validate_path(path, evidence_pack("E1"), propagation_rules())

    continuous = propagation_path(
        edges=(first, propagation_edge(source="nozzle", target="flame")),
        path_length=3,
    )
    with pytest.raises(FmeaDomainError, match="path_length"):
        validate_path(continuous, evidence_pack("E1"), propagation_rules())


def test_long_paths_are_retained_as_human_review_candidates() -> None:
    path = propagation_path(
        edges=(
            propagation_edge(source="pump", target="nozzle", path_length=3),
            propagation_edge(source="nozzle", target="flame", path_length=3),
            propagation_edge(source="flame", target="trip", path_length=3),
        ),
        path_length=3,
    )
    validate_path(path, evidence_pack("E1"), propagation_rules())
    assert path.requires_human_review is True


def test_cycle_flags_are_consistent_and_require_human_review() -> None:
    first = propagation_edge(source="pump", target="nozzle", is_cyclic=True)
    second = propagation_edge(source="nozzle", target="pump", is_cyclic=True)
    path = propagation_path(edges=(first, second), is_cyclic=True)
    validate_path(path, evidence_pack("E1"), propagation_rules())
    assert path.requires_human_review is True

    with pytest.raises(FmeaDomainError, match="cycle flag"):
        validate_path(
            propagation_path(edges=(first, second), is_cyclic=False), evidence_pack("E1"), propagation_rules()
        )


def test_graph_rejects_path_edge_not_present_in_graph_revision() -> None:
    first = propagation_edge(source="pump", target="nozzle")
    second = propagation_edge(source="nozzle", target="flame")
    topology = topology_snapshot(
        nodes=(node("pump"), node("nozzle"), node("flame")),
        interfaces=(interface("pump", "nozzle"), interface("nozzle", "flame")),
    )
    path = propagation_path(edges=(first, second))
    with pytest.raises(FmeaDomainError, match="graph edge"):
        validate_graph_revision(graph_revision(edges=(first,), paths=(path,)), topology, propagation_rules())


def test_graph_rejects_path_edge_with_same_id_but_different_contents() -> None:
    canonical = propagation_edge()
    substituted = replace(canonical, target_entity_id="nozzle")
    topology = topology_snapshot(
        nodes=(node("pump"), node("manifold"), node("nozzle")),
        interfaces=(interface("pump", "manifold"), interface("pump", "nozzle")),
    )
    path = propagation_path(edges=(substituted,))
    with pytest.raises(FmeaDomainError, match="canonical graph edge"):
        validate_graph_revision(
            graph_revision(edges=(canonical,), paths=(path,)),
            topology,
            propagation_rules(),
            evidence_packs=PropagationEvidenceResolution(packs=(evidence_pack("E1"),)),
        )


@pytest.mark.parametrize("depth", (1, 3))
def test_rule_pack_rejects_automatic_depth_other_than_locked_two(depth: int) -> None:
    with pytest.raises(FmeaDomainError, match="max_automatic_depth.*2"):
        propagation_rules(max_automatic_depth=depth)


def test_task1_cannot_confirm_graph_from_caller_supplied_human_like_data() -> None:
    edge = replace(propagation_edge(), review_status=ReviewStatus.ACCEPTED)
    topology = topology_snapshot(
        nodes=(node("pump"), node("manifold")),
        interfaces=(interface("pump", "manifold"),),
    )
    graph = graph_revision(edges=(edge,), status=PropagationStatus.CONFIRMED)
    evidence = PropagationEvidenceResolution(packs=(evidence_pack("E1"),))
    assert not hasattr(propagation_module, "PropagationReviewReceipt")
    assert not hasattr(propagation_module, "PropagationDecisionResolution")
    assert not hasattr(propagation_module, "PropagationDecisionAuthorizationPort")
    assert not hasattr(propagation_module, "validate_confirmed_graph_revision")
    with pytest.raises(
        FmeaDomainError,
        match="authoritative human confirmation is unavailable until the propagation review service",
    ):
        validate_graph_revision(graph, topology, propagation_rules(), evidence_packs=evidence)


def test_graph_requires_declared_workspace_bound_evidence_packs() -> None:
    topology = topology_snapshot(
        nodes=(node("pump"), node("manifold")),
        interfaces=(interface("pump", "manifold"),),
    )
    graph = graph_revision(edges=(propagation_edge(),))
    rules = propagation_rules()
    with pytest.raises(FmeaDomainError, match="declared evidence pack"):
        validate_graph_revision(graph, topology, rules, evidence_packs=PropagationEvidenceResolution(packs=()))

    foreign_pack = evidence_pack("E1", workspace_id="ws-foreign")
    with pytest.raises(FmeaDomainError, match="workspace"):
        validate_graph_revision(
            graph,
            topology,
            rules,
            evidence_packs=PropagationEvidenceResolution(packs=(foreign_pack,)),
        )


def test_graph_preserves_per_edge_evidence_membership() -> None:
    topology = topology_snapshot(
        nodes=(node("pump"), node("manifold")),
        interfaces=(interface("pump", "manifold"),),
    )
    graph = graph_revision(edges=(propagation_edge(evidence_ids=("E2",)),))
    with pytest.raises(FmeaDomainError, match="evidence ID E2.*EvidencePack"):
        validate_graph_revision(
            graph,
            topology,
            propagation_rules(),
            evidence_packs=PropagationEvidenceResolution(packs=(evidence_pack("E1"),)),
        )


def test_confirmed_graph_rejects_unreviewed_long_edge() -> None:
    edge = propagation_edge(path_length=3)
    topology = topology_snapshot(
        nodes=(node("pump"), node("manifold")),
        interfaces=(interface("pump", "manifold"),),
    )
    with pytest.raises(
        FmeaDomainError,
        match="authoritative human confirmation is unavailable until the propagation review service",
    ):
        validate_graph_revision(
            graph_revision(edges=(edge,), status=PropagationStatus.CONFIRMED),
            topology,
            propagation_rules(),
        )


def test_graph_revision_is_frozen_slotted_and_keeps_declared_field_order() -> None:
    assert hasattr(PropagationGraphRevision, "__slots__")
    assert tuple(field.name for field in fields(PropagationGraphRevision)) == (
        "graph_revision_id",
        "workspace_id",
        "analysis_id",
        "analysis_record_version",
        "topology_snapshot_id",
        "topology_hash",
        "evidence_pack_ids",
        "domain_pack_id",
        "domain_pack_version",
        "rule_pack_id",
        "rule_pack_version",
        "status",
        "assistance_suggestion_ids",
        "nodes",
        "edges",
        "paths",
        "unresolved_issue_codes",
        "parent_graph_revision_id",
        "record_version",
        "created_at",
    )
    with pytest.raises(FrozenInstanceError):
        graph_revision(edges=()).status = PropagationStatus.CONFIRMED
