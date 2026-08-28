from __future__ import annotations

import pytest

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
)
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PropagationStatus,
    PublicationStatus,
    ReviewStatus,
)
from fmea_application.propagation_service import (
    ConfirmPropagationCommand,
    PropagationDecisionAction,
    PropagationEdgeDecision,
    PropagationError,
    PropagationReviewResult,
    PropagationReviewService,
)
from fmea_application.review_contracts import ActorContext


def _topology() -> TopologySnapshot:
    return TopologySnapshot(
        topology_snapshot_id="topology-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        topology_hash="sha256:" + "1" * 64,
        nodes=(
            TopologyNode("pump", "equipment", ("steady",)),
            TopologyNode("filter", "equipment", ("steady",)),
            TopologyNode("flame", "equipment", ("steady",)),
        ),
        interfaces=(
            TopologyInterface("interface-1", "pump", "filter", "fuel_pressure", "kPa", "forward", ("steady",)),
            TopologyInterface("interface-2", "filter", "flame", "fuel_pressure", "kPa", "forward", ("steady",)),
        ),
    )


def _rule_pack() -> PropagationRulePack:
    return PropagationRulePack(
        rule_pack_id="fuel-propagation",
        version="1.0.0",
        applicable_analysis_types=("fuel_system",),
        relation_types=("propagation",),
        interface_variables=("fuel_pressure",),
        units=("kPa",),
        directions=("forward",),
    )


def _edge(
    edge_id: str, source: str, target: str, *, path_length: int = 1, risk_priority: str = "normal"
) -> PropagationEdge:
    return PropagationEdge(
        edge_id=edge_id,
        analysis_id="analysis-1",
        source_entity_id=source,
        target_entity_id=target,
        relation_type="propagation",
        interface_variable="fuel_pressure",
        unit="kPa",
        direction="forward",
        threshold="<250",
        operating_modes=("steady",),
        delay_ms=1,
        response_time_ms=2,
        fault_tolerance_time_ms=3,
        barrier_ids=(),
        evidence_pack_id="pack-1",
        evidence_ids=("ev-1",),
        evidence_support=EvidenceSupportStatus.SUPPORTED,
        claim_status=ClaimStatus.KNOWN,
        review_status=ReviewStatus.SUGGESTED,
        publication_status=PublicationStatus.UNPUBLISHED,
        path_length=path_length,
        is_cyclic=False,
        is_unprocessed=False,
        is_external=False,
        is_terminal=False,
        risk_priority=risk_priority,
    )


def _graph(
    *, status: PropagationStatus = PropagationStatus.PROPOSED, edges: tuple[PropagationEdge, ...] | None = None
) -> PropagationGraphRevision:
    selected = edges or (_edge("edge-1", "pump", "filter"), _edge("edge-2", "filter", "flame"))
    paths = tuple(
        PropagationPath(
            path_id=f"path-{edge.edge_id}",
            analysis_id="analysis-1",
            source_entity_id=edge.source_entity_id,
            target_entity_id=edge.target_entity_id,
            edges=(edge,),
            path_length=1,
            is_cyclic=False,
            requires_human_review=False,
        )
        for edge in selected
    )
    return PropagationGraphRevision(
        graph_revision_id="graph-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        analysis_record_version=1,
        topology_snapshot_id="topology-1",
        topology_hash="sha256:" + "1" * 64,
        evidence_pack_ids=("pack-1",),
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        rule_pack_id="fuel-propagation",
        rule_pack_version="1.0.0",
        status=status,
        assistance_suggestion_ids=("suggestion-1",),
        nodes=_topology().nodes,
        edges=selected,
        paths=paths,
        unresolved_issue_codes=(),
        parent_graph_revision_id=None,
        record_version=1,
        created_at="2026-08-28T00:00:00Z",
    )


class _Registry:
    def __init__(self, rule_pack: PropagationRulePack) -> None:
        self.rule_pack = rule_pack

    def get(self, rule_pack_id: str, version: str) -> PropagationRulePack:
        assert (rule_pack_id, version) == (self.rule_pack.rule_pack_id, self.rule_pack.version)
        return self.rule_pack


class _Repository:
    def __init__(self, graph: PropagationGraphRevision, pack) -> None:
        self.graph = graph
        self.pack = pack
        self.review_prepared = None
        self.invalidation_prepared = None

    def get_graph(self, graph_revision_id: str, workspace_id: str):
        if graph_revision_id == self.graph.graph_revision_id and workspace_id == self.graph.workspace_id:
            return self.graph
        return None

    def get_current_graph(self, analysis_id: str, workspace_id: str):
        if analysis_id == self.graph.analysis_id and workspace_id == self.graph.workspace_id:
            return self.graph
        return None

    def get_topology_snapshot(self, topology_snapshot_id: str, workspace_id: str):
        return _topology() if topology_snapshot_id == "topology-1" and workspace_id == "ws-1" else None

    def get_evidence_pack(self, pack_id: str, workspace_id: str):
        return self.pack if pack_id == self.pack.pack_id and workspace_id == self.pack.workspace_id else None

    def commit_graph_review(self, prepared):
        self.review_prepared = prepared
        return PropagationReviewResult(
            graph=prepared.graph,
            decision_id=prepared.decision_id,
            audit_event_id=prepared.audit.event_id,
            outbox_event_id=prepared.outbox.event_id,
        )

    def invalidate(self, prepared):
        self.invalidation_prepared = prepared
        return prepared.graph


def _service(repository: _Repository) -> PropagationReviewService:
    return PropagationReviewService(
        repository,
        assistance_repository=object(),
        topology_port=object(),
        domain_pack_registry=object(),
        propagation_rule_registry=_Registry(_rule_pack()),
        generator=object(),
    )


def _reviewer() -> ActorContext:
    return ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"propagation_reviewer"}), "ws-1")


def _command(*, decisions: tuple[PropagationEdgeDecision, ...] | None = None, acknowledgements: tuple[str, ...] = ()):
    return ConfirmPropagationCommand(
        graph_revision_id="graph-1",
        expected_graph_record_version=1,
        edge_decisions=decisions
        or (
            PropagationEdgeDecision("edge-1", PropagationDecisionAction.ACCEPT, "accepted"),
            PropagationEdgeDecision("edge-2", PropagationDecisionAction.REJECT, "rejected"),
        ),
        acknowledgements=acknowledgements,
        idempotency_key="00000000-0000-4000-8000-000000000401",
    )


def test_confirm_graph_creates_confirmed_child_from_exact_edge_decisions(fixture_pack) -> None:
    repository = _Repository(_graph(), fixture_pack)
    result = _service(repository).confirm_graph(_command(), _reviewer())

    assert result.graph.status is PropagationStatus.CONFIRMED
    assert result.graph.parent_graph_revision_id == "graph-1"
    assert result.graph.record_version == 2
    assert [edge.edge_id for edge in result.graph.edges] == ["edge-1"]
    assert repository.review_prepared is not None
    assert repository.review_prepared.graph.status is PropagationStatus.CONFIRMED


def test_confirm_graph_requires_one_decision_for_every_edge(fixture_pack) -> None:
    repository = _Repository(_graph(), fixture_pack)
    command = _command(decisions=(PropagationEdgeDecision("edge-1", PropagationDecisionAction.ACCEPT, "accepted"),))

    with pytest.raises(PropagationError, match="every graph edge") as captured:
        _service(repository).confirm_graph(command, _reviewer())

    assert captured.value.code == "FMEA_PROPAGATION_REVIEW_INCOMPLETE"
    assert repository.review_prepared is None


def test_confirm_graph_requires_human_propagation_reviewer(fixture_pack) -> None:
    repository = _Repository(_graph(), fixture_pack)
    actor = ActorContext("analyst-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1")

    with pytest.raises(PropagationError) as captured:
        _service(repository).confirm_graph(_command(), actor)

    assert captured.value.code == "FMEA_PROPAGATION_REVIEW_FORBIDDEN"


def test_confirm_graph_does_not_weaken_generic_confirmed_graph_validator(fixture_pack) -> None:
    repository = _Repository(_graph(), fixture_pack)
    result = _service(repository).confirm_graph(_command(), _reviewer())

    with pytest.raises(Exception, match="authoritative human confirmation"):
        validate_graph_revision(result.graph, _topology(), _rule_pack(), PropagationEvidenceResolution(()))


def test_invalidate_if_stale_creates_additive_invalidated_child(fixture_pack) -> None:
    parent = _graph(status=PropagationStatus.CONFIRMED)
    repository = _Repository(parent, fixture_pack)
    service = _service(repository)

    result = service.invalidate_if_stale(
        "analysis-1", "sha256:" + "2" * 64, ActorContext("system", ActorType.SYSTEM, frozenset(), "ws-1")
    )

    assert result is not None
    assert result.status is PropagationStatus.INVALIDATED
    assert result.parent_graph_revision_id == parent.graph_revision_id
    assert result.graph_revision_id != parent.graph_revision_id
    assert repository.invalidation_prepared is not None


def test_invalidate_if_stale_does_not_cross_workspace(fixture_pack) -> None:
    repository = _Repository(_graph(status=PropagationStatus.CONFIRMED), fixture_pack)

    result = _service(repository).invalidate_if_stale(
        "analysis-1", "sha256:" + "2" * 64, ActorContext("system", ActorType.SYSTEM, frozenset(), "other-workspace")
    )

    assert result is None
