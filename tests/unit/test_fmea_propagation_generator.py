from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace

import pytest

from core_domain.fmea.domain_pack import DomainPackManifest
from core_domain.fmea.propagation import PropagationRulePack, TopologySnapshot
from core_domain.fmea.states import (
    ClaimStatus,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.structured_generation import (
    GenerationRunStatus,
    GenerationStage,
    StructuredModelResponse,
)
from fmea_application.assistance_contracts import AssistanceKind
from fmea_application.propagation_service import PropagationCandidateInterface, PropagationModelRequest
from fmea_infrastructure.propagation_generator import (
    PropagationGenerationError,
)
from fmea_infrastructure.propagation_generator import (
    PropagationSuggestionGenerator as ConcretePropagationSuggestionGenerator,
)


@dataclass(frozen=True)
class _Candidate:
    candidate_id: str
    payload: object


class _Pipeline:
    def __init__(self, payload, *, status=GenerationRunStatus.SUCCEEDED, repair_count=0):
        self.payload = payload
        self.status = status
        self.repair_count = repair_count
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "GenerationResult",
            (),
            {
                "status": self.status,
                "repair_count": self.repair_count,
                "batch": type(
                    "Batch",
                    (),
                    {
                        "template_id": "fmea-propagation-hypothesis",
                        "template_version": "1.0.0",
                        "evidence_pack_id": kwargs["evidence_pack"].pack_id,
                        "candidates": (_Candidate("candidate-1", self.payload),),
                    },
                )(),
                "traces": (
                    type(
                        "Trace",
                        (),
                        {
                            "stage": GenerationStage.REPAIR if self.repair_count else GenerationStage.CRITIC,
                            "model_id": "deepseek-v4-pro",
                            "prompt_hash": "b" * 64,
                            "response_hash": "a" * 64,
                        },
                    )(),
                ),
                "trace_id": "trace-generator-1",
            },
        )()


def _request() -> PropagationModelRequest:
    from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
    from core_domain.fmea.value_objects import EvidencePack

    analysis = FmeaAnalysis(
        analysis_id="analysis-1",
        project_id="project-1",
        analysis_type="fuel_system",
        lifecycle_stage="draft",
        scope="scope",
        system_boundary="boundary",
        exclusions=(),
        equipment_configuration="config",
        control_software_version="control",
        fuel_type="natural_gas",
        operating_modes=("steady_state",),
        assumptions=(),
        limitations=(),
        unanalysed_parts=(),
        versions=_versions(),
        owner_actor_id="analyst-1",
        reviewer_actor_ids=(),
        approver_actor_id=None,
        approved_at=None,
        parent_revision_id=None,
        current_revision_id="revision-1",
    )
    row = FmeaRow(
        row_id="row-1",
        analysis_id="analysis-1",
        evidence_pack_id="pack-1",
        item_id="fuel_pump",
        function_id="pump",
        failure_mode="low pressure",
        causes=(),
        mechanisms=(),
        effects=(),
        symptoms=(),
        controls=(),
        barriers=(),
        actions=(),
        risk_assessment=None,
        field_evidence=(),
        field_support=(),
        claim_status=ClaimStatus.KNOWN,
        review_status=ReviewStatus.ACCEPTED,
        publication_status=PublicationStatus.UNPUBLISHED,
    )
    pack = EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=_versions(),
        refs=(_ref(),),
        created_at="2026-08-28T00:00:00Z",
        expires_at=None,
    )
    domain_pack = DomainPackManifest(
        pack_id="fuel-combustion",
        version="1.0.0",
        content_hash="c" * 64,
        compatible_schema_ids=("graphrag.fmea.v1",),
        analysis_types=("fuel_system",),
        template_identities=(("fmea-propagation-hypothesis", "1.0.0"),),
        scoring_rule_identities=(),
        propagation_rule_identities=(("fuel-propagation", "1.0.0"),),
        extension_fields=(),
    )
    rule_pack = PropagationRulePack(
        rule_pack_id="fuel-propagation",
        version="1.0.0",
        applicable_analysis_types=("fuel_system",),
        relation_types=("propagation",),
        interface_variables=("fuel_pressure",),
        units=("kPa",),
        directions=("fuel_to_combustion",),
    )
    return PropagationModelRequest(
        run_id="run-1",
        analysis=analysis,
        source_rows=(row,),
        evidence_pack=pack,
        topology=TopologySnapshot("topology-1", "ws-1", "analysis-1", "d" * 64, (), ()),
        domain_pack=domain_pack,
        rule_pack=rule_pack,
        candidate_interfaces=(
            type(
                "CandidateInterface",
                (),
                {
                    "interface_id": "i-1",
                    "source_node_id": "fuel_pump",
                    "target_node_id": "fuel_filter",
                    "interface_variable": "fuel_pressure",
                    "unit": "kPa",
                    "direction": "fuel_to_combustion",
                    "operating_modes": ("steady_state",),
                    "path_length": 1,
                },
            )(),
        ),
        candidate_endpoint_ids=("fuel_filter", "fuel_pump"),
        candidate_evidence_ids=("ev-1",),
        allowed_relation_types=("propagation",),
        max_depth=2,
        max_edges=40,
    )


def _versions():
    from core_domain.fmea.states import FMEA_SCHEMA_ID
    from core_domain.fmea.value_objects import VersionSet

    return VersionSet(
        schema_id=FMEA_SCHEMA_ID,
        data_version="data-1",
        graph_version="graph-1",
        evidence_pack_version="evidence-1",
        profile_version="profile-1",
        template_version="template-1",
        scoring_version="score-1",
        prompt_version="prompt-1",
        model_version="model-1",
        input_snapshot_hash="e" * 64,
    )


def _ref():
    from core_domain.fmea.value_objects import EvidenceRef

    return EvidenceRef(
        evidence_id="ev-1",
        workspace_id="ws-1",
        document_id="doc-1",
        document_version="v1",
        content_hash="f" * 64,
        locator="page:1",
        quote="pressure is low",
        normalized_quote="pressure is low",
        evidence_hash="1" * 64,
        acl_scope=("engineering",),
        source_type="primary_document",
        source_trust="reviewed",
        is_primary=True,
        created_at="2026-08-28T00:00:00Z",
        expires_at=None,
    )


def _edge(**overrides):
    edge = {
        "interface_id": "i-1",
        "source_entity_id": "fuel_pump",
        "target_entity_id": "fuel_filter",
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
    edge.update(overrides)
    return edge


def test_generator_returns_immutable_propagation_suggestion() -> None:
    request = _request()
    generator = ConcretePropagationSuggestionGenerator(_Pipeline({"edges": [_edge()]}))

    suggestion = generator.generate(request)

    assert suggestion.kind is AssistanceKind.PROPAGATION_HYPOTHESIS
    assert suggestion.applied is False
    assert suggestion.payload[0]["target_entity_id"] == "fuel_filter"
    assert suggestion.evidence_ids == ("ev-1",)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("target_entity_id", "invented_turbine", "FMEA_PROPAGATION_ENDPOINT_INVALID"),
        ("evidence_ids", ["invented-evidence"], "FMEA_PROPAGATION_EVIDENCE_INVALID"),
        ("relation_type", "invented_relation", "FMEA_PROPAGATION_RELATION_INVALID"),
        ("path_length", 3, "FMEA_PROPAGATION_DEPTH_INVALID"),
    ],
)
def test_generator_rejects_values_outside_the_server_bound_request(field, value, code) -> None:
    request = _request()
    generator = ConcretePropagationSuggestionGenerator(_Pipeline({"edges": [_edge(**{field: value})]}))

    with pytest.raises(PropagationGenerationError) as captured:
        generator.generate(request)

    assert captured.value.code == code


def test_generator_rejects_depth_two_candidate_labeled_as_depth_one() -> None:
    request = replace(
        _request(),
        candidate_interfaces=(
            PropagationCandidateInterface(
                interface_id="i-2",
                source_node_id="fuel_filter",
                target_node_id="fuel_manifold",
                interface_variable="fuel_pressure",
                unit="kPa",
                direction="fuel_to_combustion",
                operating_modes=("steady_state",),
                path_length=2,
            ),
        ),
        candidate_endpoint_ids=("fuel_filter", "fuel_manifold", "fuel_pump"),
    )
    generator = ConcretePropagationSuggestionGenerator(
        _Pipeline({
            "edges": [
                _edge(
                    interface_id="i-2",
                    source_entity_id="fuel_filter",
                    target_entity_id="fuel_manifold",
                    path_length=1,
                )
            ]
        })
    )

    with pytest.raises(PropagationGenerationError) as captured:
        generator.generate(request)

    assert captured.value.code == "FMEA_PROPAGATION_ENDPOINT_INVALID"


def test_generator_rejects_interface_substitution_even_when_endpoints_are_allowed() -> None:
    request = _request()
    generator = ConcretePropagationSuggestionGenerator(
        _Pipeline({
            "edges": [
                _edge(
                    interface_id="i-1",
                    source_entity_id="fuel_pump",
                    target_entity_id="fuel_pump",
                )
            ]
        })
    )

    with pytest.raises(PropagationGenerationError) as captured:
        generator.generate(request)

    assert captured.value.code == "FMEA_PROPAGATION_ENDPOINT_INVALID"


def test_generator_orders_edges_by_bound_candidate_before_building_suggestion() -> None:
    request = replace(
        _request(),
        candidate_interfaces=(
            PropagationCandidateInterface(
                interface_id="i-2",
                source_node_id="fuel_pump",
                target_node_id="fuel_filter",
                interface_variable="fuel_pressure",
                unit="kPa",
                direction="fuel_to_combustion",
                operating_modes=("steady_state",),
                path_length=1,
            ),
            PropagationCandidateInterface(
                interface_id="i-1",
                source_node_id="fuel_filter",
                target_node_id="fuel_manifold",
                interface_variable="fuel_pressure",
                unit="kPa",
                direction="fuel_to_combustion",
                operating_modes=("steady_state",),
                path_length=2,
            ),
        ),
        candidate_endpoint_ids=("fuel_filter", "fuel_manifold", "fuel_pump"),
    )
    generator = ConcretePropagationSuggestionGenerator(
        _Pipeline({
            "edges": [
                _edge(
                    interface_id="i-1",
                    source_entity_id="fuel_filter",
                    target_entity_id="fuel_manifold",
                    path_length=2,
                ),
                _edge(
                    interface_id="i-2",
                    source_entity_id="fuel_pump",
                    target_entity_id="fuel_filter",
                    path_length=1,
                ),
            ]
        })
    )

    suggestion = generator.generate(request)

    assert [edge["interface_id"] for edge in suggestion.payload] == ["i-2", "i-1"]


def test_generator_rejects_root_budget_override() -> None:
    request = _request()
    generator = ConcretePropagationSuggestionGenerator(_Pipeline({"edges": [_edge()], "max_depth": 999}))

    with pytest.raises(PropagationGenerationError) as captured:
        generator.generate(request)

    assert captured.value.code == "FMEA_PROPAGATION_BUDGET_INVALID"


def test_generator_accepts_one_repair_but_never_more_than_one() -> None:
    request = _request()
    generator = ConcretePropagationSuggestionGenerator(
        _Pipeline({"edges": [_edge()]}, status=GenerationRunStatus.NEEDS_REVIEW, repair_count=1)
    )

    suggestion = generator.generate(request)

    assert suggestion.run_id == "run-1"
    assert suggestion.trace_id == "trace-generator-1"


class _Gateway:
    def __init__(self) -> None:
        self.calls = []

    def complete(self, request, **_kwargs):
        self.calls.append(request)
        if request.stage is GenerationStage.GENERATE:
            context = re.search(r"BEGIN_RUN_CONTEXT_JSON[^\n]*\n(.*?)\nEND_RUN_CONTEXT_JSON", request.user_prompt, re.S)
            assert context is not None
            values = json.loads(context.group(1))
            content = json.dumps(
                {
                    "template_id": values["template_id"],
                    "template_version": values["template_version"],
                    "template_hash": values["template_hash"],
                    "evidence_pack_id": values["evidence_pack_id"],
                    "candidates": [{"candidate_id": "candidate-1", "payload": {"edges": [_edge()]}, "claims": []}],
                },
                separators=(",", ":"),
            )
        else:
            content = json.dumps({"verdict": "accept", "findings": [], "summary": "bounded"})
        return StructuredModelResponse(
            content=content,
            model_id=request.model_id,
            finish_reason="stop",
            input_tokens=1,
            output_tokens=1,
            response_hash=hashlib.sha256(content.encode()).hexdigest(),
            http_attempts=1,
        )


def test_generator_uses_offline_flash_then_pro_critic_pipeline() -> None:
    gateway = _Gateway()

    suggestion = ConcretePropagationSuggestionGenerator(gateway).generate(_request())

    assert [request.stage for request in gateway.calls] == [GenerationStage.GENERATE, GenerationStage.CRITIC]
    assert [request.model_id for request in gateway.calls] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert suggestion.kind is AssistanceKind.PROPAGATION_HYPOTHESIS
