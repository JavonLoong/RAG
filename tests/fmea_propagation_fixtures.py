from __future__ import annotations

from dataclasses import replace

import pytest

from core_domain.fmea.propagation import (
    PropagationEdge,
    PropagationGraphRevision,
    PropagationPath,
    PropagationRulePack,
    TopologyInterface,
    TopologyNode,
    TopologySnapshot,
)
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PropagationStatus,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.fmea.value_objects import EvidencePack
from fmea_application.propagation_service import (
    ConfirmPropagationCommand,
    PropagationDecisionAction,
    PropagationEdgeDecision,
    PropagationReviewResult,
    PropagationReviewService,
)
from fmea_application.review_contracts import ActorContext
from fmea_infrastructure.propagation_repository_sqlite import SqlitePropagationRepository


def _topology(workspace_id: str) -> TopologySnapshot:
    return TopologySnapshot(
        topology_snapshot_id="topology-1",
        workspace_id=workspace_id,
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


def _edge(edge_id: str, source: str, target: str) -> PropagationEdge:
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
        path_length=1,
        is_cyclic=False,
        is_unprocessed=False,
        is_external=False,
        is_terminal=False,
        risk_priority="normal",
    )


def _graph(workspace_id: str) -> PropagationGraphRevision:
    topology = _topology(workspace_id)
    edges = (_edge("edge-1", "pump", "filter"), _edge("edge-2", "filter", "flame"))
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
        for edge in edges
    )
    return PropagationGraphRevision(
        graph_revision_id="graph-1",
        workspace_id=workspace_id,
        analysis_id="analysis-1",
        analysis_record_version=1,
        topology_snapshot_id=topology.topology_snapshot_id,
        topology_hash=topology.topology_hash,
        evidence_pack_ids=("pack-1",),
        domain_pack_id="fuel-combustion",
        domain_pack_version="1.0.0",
        rule_pack_id="fuel-propagation",
        rule_pack_version="1.0.0",
        status=PropagationStatus.PROPOSED,
        assistance_suggestion_ids=("suggestion-1",),
        nodes=topology.nodes,
        edges=edges,
        paths=paths,
        unresolved_issue_codes=(),
        parent_graph_revision_id=None,
        record_version=1,
        created_at="2026-08-28T00:00:00Z",
    )


def _foreign_pack(pack: EvidencePack, workspace_id: str) -> EvidencePack:
    refs = tuple(replace(ref, workspace_id=workspace_id) for ref in pack.refs)
    return EvidencePack.build(
        pack_id=pack.pack_id,
        workspace_id=workspace_id,
        acl_scope=pack.acl_scope,
        versions=pack.versions,
        refs=refs,
        created_at=pack.created_at,
        expires_at=pack.expires_at,
        parent_pack_refs=pack.parent_pack_refs,
        lineage_reason=pack.lineage_reason,
        lineage_schema_version=pack.lineage_schema_version,
    )


class _CaptureRepository:
    def __init__(self, parent: PropagationGraphRevision, topology: TopologySnapshot, pack: EvidencePack) -> None:
        self.parent = parent
        self.topology = topology
        self.pack = pack
        self.prepared = None

    def get_graph_revision(self, graph_revision_id: str, workspace_id: str):
        if graph_revision_id == self.parent.graph_revision_id and workspace_id == self.parent.workspace_id:
            return self.parent
        return None

    def get_topology_snapshot(self, topology_snapshot_id: str, workspace_id: str):
        if topology_snapshot_id == self.topology.topology_snapshot_id and workspace_id == self.topology.workspace_id:
            return self.topology
        return None

    def get_evidence_pack(self, pack_id: str, workspace_id: str):
        if pack_id == self.pack.pack_id and workspace_id == self.pack.workspace_id:
            return self.pack
        return None

    def get_graph_source_row_ids(self, graph_revision_id: str, workspace_id: str):
        if graph_revision_id == self.parent.graph_revision_id and workspace_id == self.parent.workspace_id:
            return ("row-1",) if workspace_id == "ws-1" else ("row-foreign",)
        return ()

    def replay_graph_review(self, scope, payload_hash):
        return None

    def commit_graph_review(self, prepared):
        self.prepared = prepared
        return PropagationReviewResult(
            graph=prepared.graph,
            decision_id=prepared.decision_id,
            audit_event_id=prepared.audit.event_id,
            outbox_event_id=prepared.outbox.event_id,
        )


@pytest.fixture
def repository(tmp_path, fixture_review_bundle, fixture_system_actor) -> SqlitePropagationRepository:
    repository = SqlitePropagationRepository(tmp_path / "fmea.sqlite3")
    repository.initialize()
    repository.save_review_candidate_bundle(fixture_review_bundle, fixture_system_actor)
    return repository


@pytest.fixture
def prepared_graph_confirmation(repository, fixture_pack):
    def build(
        *,
        repository: SqlitePropagationRepository | None = None,
        edge_actions: tuple[tuple[str, str], ...] = (("edge-1", "accept"), ("edge-2", "reject")),
        idempotency_key: str = "00000000-0000-4000-8000-000000000401",
        reason: str = "accepted by propagation reviewer",
        workspace_id: str = "ws-1",
    ):
        target = repository or build.repository
        parent = _graph(workspace_id)
        topology = _topology(workspace_id)
        pack = fixture_pack if workspace_id == "ws-1" else _foreign_pack(fixture_pack, workspace_id)
        if workspace_id == "ws-1" and target.get_graph_revision(parent.graph_revision_id, workspace_id) is None:
            connection = target._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                target._insert_topology(connection, topology)
                target._insert_graph(connection, parent, ("row-1",))
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()
        capture = _CaptureRepository(parent, topology, pack)
        actor = ActorContext(
            "reviewer-1" if workspace_id == "ws-1" else "reviewer-foreign",
            ActorType.HUMAN,
            frozenset({"propagation_reviewer"}),
            workspace_id,
        )
        command = ConfirmPropagationCommand(
            graph_revision_id=parent.graph_revision_id,
            expected_graph_record_version=parent.record_version,
            edge_decisions=tuple(
                PropagationEdgeDecision(edge_id, PropagationDecisionAction(action), reason)
                for edge_id, action in edge_actions
            ),
            acknowledgements=(),
            idempotency_key=idempotency_key,
        )
        service = PropagationReviewService(
            capture,
            assistance_repository=object(),
            topology_port=object(),
            domain_pack_registry=object(),
            propagation_rule_registry=type("Registry", (), {"get": lambda _self, _id, _version: _rule_pack()})(),
            generator=object(),
            clock=lambda: "2026-08-28T00:00:01Z",
        )
        service.confirm_graph(command, actor)
        assert capture.prepared is not None
        return capture.prepared

    build.repository = repository
    return build


__all__ = ["prepared_graph_confirmation", "repository"]
