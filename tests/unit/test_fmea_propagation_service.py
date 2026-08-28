from __future__ import annotations

from dataclasses import replace

from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.propagation import (
    PropagationRulePack,
    TopologyInterface,
    TopologyNode,
    TopologySnapshot,
)
from core_domain.fmea.states import (
    ActorType,
    PropagationStatus,
    ReviewStatus,
    RunStatus,
)
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.propagation_service import (
    PropagationAnalysisService,
    PropagationModelRequest,
    StartPropagationCommand,
)
from fmea_application.review_contracts import ActorContext


class _Registry:
    def __init__(self, value):
        self.value = value

    def get(self, *_args):
        return self.value


class _Topology:
    def __init__(self, snapshot: TopologySnapshot) -> None:
        self.snapshot = snapshot

    def load_snapshot(self, *_args):
        return self.snapshot

    def neighbors(self, snapshot, entity_id):
        return tuple(interface for interface in snapshot.interfaces if interface.source_node_id == entity_id)


class _Repository:
    def __init__(self, analysis, row, pack) -> None:
        self.analysis = analysis
        self.row = row
        self.pack = pack
        self.saved = None

    def get_analysis(self, analysis_id):
        return self.analysis if analysis_id == self.analysis.analysis_id else None

    def get_row(self, row_id):
        return self.row if row_id == self.row.row_id else None

    def get_evidence_pack(self, pack_id):
        return self.pack if pack_id == self.pack.pack_id else None

    def save_run_and_proposal(self, prepared):
        self.saved = prepared
        return prepared.run

    def get_run(self, run_id, workspace_id):
        if self.saved and self.saved.run.run_id == run_id and self.saved.run.workspace_id == workspace_id:
            return self.saved.run
        return None

    def get_graph(self, analysis_id, workspace_id):
        if self.saved and self.saved.graph.analysis_id == analysis_id and self.saved.graph.workspace_id == workspace_id:
            return self.saved.graph
        return None


class _AssistanceRepository:
    def __init__(self) -> None:
        self.saved = []

    def save_suggestion(self, prepared):
        self.saved.append(prepared)
        return prepared.suggestion


class _Generator:
    def __init__(self, suggestion_factory) -> None:
        self.suggestion_factory = suggestion_factory
        self.requests: list[PropagationModelRequest] = []

    def generate(self, request):
        self.requests.append(request)
        return self.suggestion_factory(request)


def _domain_pack() -> DomainPackManifest:
    return DomainPackManifest(
        pack_id="fuel-combustion",
        version="1.0.0",
        content_hash="a" * 64,
        compatible_schema_ids=("graphrag.fmea.v1",),
        analysis_types=("fuel_system",),
        template_identities=(("fmea-propagation-hypothesis", "1.0.0"),),
        scoring_rule_identities=(),
        propagation_rule_identities=(("fuel-propagation", "1.0.0"),),
        extension_fields=(),
    )


def _rule_pack() -> PropagationRulePack:
    return PropagationRulePack(
        rule_pack_id="fuel-propagation",
        version="1.0.0",
        applicable_analysis_types=("fuel_system",),
        relation_types=("propagation",),
        interface_variables=("fuel_pressure",),
        units=("kPa",),
        directions=("fuel_to_combustion",),
    )


def _topology() -> TopologySnapshot:
    nodes = tuple(
        TopologyNode(node_id=node_id, node_type="equipment", operating_modes=("steady_state",))
        for node_id in (
            "fuel_pump",
            "fuel_filter",
            "fuel_manifold",
            "combustor_flame",
        )
    )
    interfaces = (
        TopologyInterface(
            "i-02", "fuel_pump", "fuel_filter", "fuel_pressure", "kPa", "fuel_to_combustion", ("steady_state",)
        ),
        TopologyInterface(
            "i-01", "fuel_filter", "fuel_manifold", "fuel_pressure", "kPa", "fuel_to_combustion", ("steady_state",)
        ),
        TopologyInterface(
            "i-03", "fuel_manifold", "combustor_flame", "fuel_pressure", "kPa", "fuel_to_combustion", ("steady_state",)
        ),
    )
    return TopologySnapshot(
        topology_snapshot_id="topology-snapshot-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        topology_hash="b" * 64,
        nodes=nodes,
        interfaces=interfaces,
    )


def _command(**overrides) -> StartPropagationCommand:
    values = {
        "analysis_id": "analysis-1",
        "expected_analysis_record_version": 1,
        "source_row_ids": ("row-1",),
        "evidence_pack_id": "pack-1",
        "topology_id": "fuel-topology",
        "topology_version": "1.0.0",
        "domain_pack_id": "fuel-combustion",
        "domain_pack_version": "1.0.0",
        "rule_pack_id": "fuel-propagation",
        "rule_pack_version": "1.0.0",
        "idempotency_key": "00000000-0000-4000-8000-000000000003",
        "max_depth": 2,
        "max_edges": 40,
    }
    values.update(overrides)
    return StartPropagationCommand(**values)


def _actor() -> ActorContext:
    return ActorContext("analyst-1", ActorType.HUMAN, frozenset({"analyst"}), "ws-1")


def _suggestion(request: PropagationModelRequest, *, target: str = "fuel_filter") -> AssistanceSuggestion:
    edge = {
        "source_entity_id": "fuel_pump",
        "target_entity_id": target,
        "relation_type": "propagation",
        "interface_variable": "fuel_pressure",
        "unit": "kPa",
        "direction": "fuel_to_combustion",
        "threshold": "<250",
        "operating_modes": ["steady_state"],
        "delay_ms": 100,
        "response_time_ms": 200,
        "fault_tolerance_time_ms": 500,
        "barrier_ids": [],
        "evidence_ids": ["ev-1"],
        "evidence_support": "supported",
        "claim_status": "known",
        "path_length": 1,
        "is_cyclic": False,
        "is_unprocessed": False,
        "is_external": False,
        "is_terminal": False,
        "risk_priority": "normal",
    }
    return AssistanceSuggestion(
        suggestion_id="suggestion-propagation-1",
        kind=AssistanceKind.PROPAGATION_HYPOTHESIS,
        workspace_id=request.evidence_pack.workspace_id,
        target_type="fmea_analysis",
        target_id=request.analysis.analysis_id,
        target_record_version=request.analysis.record_version,
        evidence_pack_ids=(request.evidence_pack.pack_id,),
        payload=(edge,),
        evidence_ids=("ev-1",),
        model_hash="c" * 64,
        prompt_hash="d" * 64,
        run_id=request.run_id,
        trace_id="trace-propagation-1",
        domain_pack_id=request.domain_pack.pack_id,
        domain_pack_version=request.domain_pack.version,
        template_id="fmea-propagation-hypothesis",
        template_version="1.0.0",
        rule_pack_id=request.rule_pack.rule_pack_id,
        rule_pack_version=request.rule_pack.version,
        created_at="2026-08-28T00:00:00Z",
    )


def _service(fixture_analysis, fixture_row, fixture_pack, *, target="fuel_filter"):
    analysis = replace(fixture_analysis, analysis_type="fuel_system")
    row = replace(
        fixture_row, analysis_id=analysis.analysis_id, item_id="fuel_pump", review_status=ReviewStatus.ACCEPTED
    )
    repository = _Repository(analysis, row, fixture_pack)
    assistance = _AssistanceRepository()
    generator = _Generator(lambda request: _suggestion(request, target=target))
    service = PropagationAnalysisService(
        repository,
        assistance_repository=assistance,
        topology_port=_Topology(_topology()),
        domain_pack_registry=_Registry(_domain_pack()),
        propagation_rule_registry=_Registry(_rule_pack()),
        generator=generator,
        clock=lambda: "2026-08-28T00:00:01Z",
    )
    return service, repository, assistance, generator


def test_service_enumerates_deterministic_two_hop_candidates_before_generation(
    fixture_analysis, fixture_row, fixture_pack
) -> None:
    service, repository, assistance, generator = _service(fixture_analysis, fixture_row, fixture_pack)

    result = service.start_analysis(_command(), _actor())

    assert result.status is RunStatus.SUCCEEDED
    assert result.error_code is None
    assert result.graph is not None
    assert result.graph.status is PropagationStatus.PROPOSED
    assert [candidate.interface_id for candidate in generator.requests[0].candidate_interfaces] == ["i-02", "i-01"]
    assert generator.requests[0].max_depth == 2
    assert result.graph.assistance_suggestion_ids == ("suggestion-propagation-1",)
    assert repository.saved is not None
    assert len(assistance.saved) == 1
    assert repository.row.review_status is ReviewStatus.ACCEPTED


def test_service_rejects_model_endpoint_outside_enumerated_candidates(
    fixture_analysis, fixture_row, fixture_pack
) -> None:
    service, repository, assistance, _ = _service(
        fixture_analysis, fixture_row, fixture_pack, target="invented_turbine"
    )

    result = service.start_analysis(_command(), _actor())

    assert result.status is RunStatus.FAILED
    assert result.error_code == "FMEA_PROPAGATION_ENDPOINT_INVALID"
    assert repository.saved is None
    assert assistance.saved == []


def test_task_three_only_proposes_and_exposes_no_confirmation_path(fixture_analysis, fixture_row, fixture_pack) -> None:
    service, _, _, _ = _service(fixture_analysis, fixture_row, fixture_pack)

    assert not hasattr(service, "confirm_graph")
