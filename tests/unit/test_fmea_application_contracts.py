"""Contract tests for the FMEA application handoff boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from inspect import signature
from typing import Literal, get_type_hints

import pytest

from core_domain.fmea import contracts, entities, propagation, scoring, states, value_objects
from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.propagation import PropagationEdge
from core_domain.fmea.states import ActorType
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from fmea_application.ports import (
    EvidenceProvider,
    EvidenceRequest,
    EvidenceSnapshot,
    FmeaRepository,
    PropagationEvidenceProvider,
    PropagationRequest,
)


def test_evidence_request_defaults_to_combined_sources(fixture_versions: VersionSet) -> None:
    request = EvidenceRequest(
        workspace_id="ws-1",
        analysis_id="analysis-1",
        query="fuel pressure",
        versions=fixture_versions,
        acl_scope=("engineering",),
    )

    assert request.evidence_profile is EvidenceSelectionProfile.COMBINED
    assert request.evidence_types == ()
    assert request.max_hits == 20
    with pytest.raises(FrozenInstanceError):
        request.query = "changed"


def test_evidence_request_normalizes_tuple_fields(fixture_versions: VersionSet) -> None:
    request = EvidenceRequest(
        "ws-1",
        "analysis-1",
        "fuel pressure",
        fixture_versions,
        ["engineering"],
        evidence_profile=EvidenceSelectionProfile.CUSTOM,
        evidence_types=[CitationType.TEXT],
    )

    assert request.acl_scope == ("engineering",)
    assert request.evidence_types == (CitationType.TEXT,)


def test_evidence_snapshot_separates_pack_from_run_audit(fixture_pack: EvidencePack) -> None:
    snapshot = EvidenceSnapshot(
        pack=fixture_pack,
        profile=EvidenceSelectionProfile.COMBINED,
        source_counts=[(CitationType.TEXT, 1), (CitationType.GRAPH, 0)],
        warnings=["GRAPH_RETRIEVAL_DEGRADED: graph unavailable"],
        incomplete=True,
    )

    assert tuple(field.name for field in fields(EvidenceSnapshot)) == (
        "pack",
        "profile",
        "source_counts",
        "warnings",
        "incomplete",
    )
    assert snapshot.source_counts == ((CitationType.TEXT, 1), (CitationType.GRAPH, 0))
    assert snapshot.warnings == ("GRAPH_RETRIEVAL_DEGRADED: graph unavailable",)
    assert "score" not in get_type_hints(type(snapshot))
    with pytest.raises(FrozenInstanceError):
        snapshot.incomplete = False


@pytest.mark.parametrize("max_hits", (0, -1, 101))
def test_evidence_request_rejects_invalid_hit_limits(
    fixture_versions: VersionSet, max_hits: int
) -> None:
    with pytest.raises(ValueError, match="max_hits"):
        EvidenceRequest(
            "ws-1",
            "analysis-1",
            "fuel pressure",
            fixture_versions,
            ("engineering",),
            max_hits=max_hits,
        )


def test_custom_evidence_profile_requires_non_empty_unique_types(fixture_versions: VersionSet) -> None:
    with pytest.raises(ValueError, match="custom evidence profile"):
        EvidenceRequest(
            "ws-1",
            "analysis-1",
            "fuel pressure",
            fixture_versions,
            ("engineering",),
            evidence_profile=EvidenceSelectionProfile.CUSTOM,
        )

    with pytest.raises(ValueError, match="must not contain duplicates"):
        EvidenceRequest(
            "ws-1",
            "analysis-1",
            "fuel pressure",
            fixture_versions,
            ("engineering",),
            evidence_profile=EvidenceSelectionProfile.CUSTOM,
            evidence_types=(CitationType.TEXT, CitationType.TEXT),
        )


@pytest.mark.parametrize(
    "profile",
    tuple(profile for profile in EvidenceSelectionProfile if profile is not EvidenceSelectionProfile.CUSTOM),
)
def test_non_custom_evidence_profiles_reject_explicit_types(
    fixture_versions: VersionSet, profile: EvidenceSelectionProfile
) -> None:
    with pytest.raises(ValueError, match="custom evidence profile"):
        EvidenceRequest(
            "ws-1",
            "analysis-1",
            "fuel pressure",
            fixture_versions,
            ("engineering",),
            evidence_profile=profile,
            evidence_types=(CitationType.TEXT,),
        )


def test_propagation_request_uses_phase_two_defaults_and_tuple_source_ids(
    fixture_analysis: FmeaAnalysis, fixture_pack: EvidencePack
) -> None:
    request = PropagationRequest(
        analysis=fixture_analysis,
        evidence_pack=fixture_pack,
        source_row_ids=["row-1", "row-2"],
        target_system="combustion",
    )

    assert request.source_row_ids == ("row-1", "row-2")
    assert request.target_system == "combustion"
    assert request.max_hops == 2
    assert request.max_edges == 40
    assert get_type_hints(PropagationRequest)["target_system"] == Literal["fuel", "combustion"]


def test_evidence_provider_keeps_propagation_separate() -> None:
    assert tuple(
        name for name, member in EvidenceProvider.__dict__.items() if not name.startswith("_") and callable(member)
    ) == ("create_snapshot", "read_refs", "load_pack")
    assert not hasattr(EvidenceProvider, "find_propagation_edges")
    assert tuple(
        name
        for name, member in PropagationEvidenceProvider.__dict__.items()
        if not name.startswith("_") and callable(member)
    ) == ("find_propagation_edges",)

    assert tuple(signature(EvidenceProvider.create_snapshot).parameters) == ("self", "request")
    assert get_type_hints(EvidenceProvider.create_snapshot) == {
        "request": EvidenceRequest,
        "return": EvidenceSnapshot,
    }
    assert tuple(signature(EvidenceProvider.read_refs).parameters) == ("self", "pack", "evidence_ids")
    assert get_type_hints(EvidenceProvider.read_refs) == {
        "pack": EvidencePack,
        "evidence_ids": tuple[str, ...],
        "return": tuple[EvidenceRef, ...],
    }
    assert tuple(signature(EvidenceProvider.load_pack).parameters) == ("self", "workspace_id", "pack_id")
    assert get_type_hints(EvidenceProvider.load_pack) == {
        "workspace_id": str,
        "pack_id": str,
        "return": EvidencePack,
    }
    assert tuple(signature(PropagationEvidenceProvider.find_propagation_edges).parameters) == (
        "self",
        "request",
    )
    assert get_type_hints(PropagationEvidenceProvider.find_propagation_edges) == {
        "request": PropagationRequest,
        "return": tuple[PropagationEdge, ...],
    }


def test_fmea_repository_exposes_exact_foundation_methods() -> None:
    expected_parameters = {
        "initialize": ("self",),
        "save_analysis": ("self", "analysis", "actor_id", "actor_type", "expected_record_version"),
        "get_analysis": ("self", "analysis_id"),
        "save_evidence_pack": ("self", "pack", "actor_id", "actor_type"),
        "get_evidence_pack": ("self", "pack_id"),
        "save_row": ("self", "row", "actor_id", "actor_type", "expected_record_version"),
        "get_row": ("self", "row_id"),
        "save_propagation_edge": ("self", "edge", "actor_id", "actor_type", "expected_record_version"),
        "get_propagation_edge": ("self", "edge_id"),
        "append_audit_event": (
            "self",
            "actor_id",
            "actor_type",
            "command",
            "aggregate_type",
            "aggregate_id",
            "before_hash",
            "after_hash",
            "reason",
            "versions",
        ),
    }
    actual_methods = {
        name for name, member in FmeaRepository.__dict__.items() if not name.startswith("_") and callable(member)
    }

    assert actual_methods == set(expected_parameters)
    for name, parameters in expected_parameters.items():
        assert tuple(signature(getattr(FmeaRepository, name)).parameters) == parameters

    assert get_type_hints(FmeaRepository.save_analysis) == {
        "analysis": FmeaAnalysis,
        "actor_id": str,
        "actor_type": ActorType,
        "expected_record_version": int | None,
        "return": FmeaAnalysis,
    }
    assert get_type_hints(FmeaRepository.save_evidence_pack) == {
        "pack": EvidencePack,
        "actor_id": str,
        "actor_type": ActorType,
        "return": EvidencePack,
    }
    assert get_type_hints(FmeaRepository.save_row) == {
        "row": FmeaRow,
        "actor_id": str,
        "actor_type": ActorType,
        "expected_record_version": int | None,
        "return": FmeaRow,
    }
    assert get_type_hints(FmeaRepository.save_propagation_edge) == {
        "edge": PropagationEdge,
        "actor_id": str,
        "actor_type": ActorType,
        "expected_record_version": int | None,
        "return": PropagationEdge,
    }
    assert get_type_hints(FmeaRepository.append_audit_event) == {
        "actor_id": str,
        "actor_type": ActorType,
        "command": str,
        "aggregate_type": str,
        "aggregate_id": str,
        "before_hash": str | None,
        "after_hash": str | None,
        "reason": str,
        "versions": VersionSet,
        "return": str,
    }


def test_fmea_contracts_reexport_exact_domain_identities() -> None:
    assert contracts.__all__ == [
        "ActorType",
        "ClaimStatus",
        "EvidencePack",
        "EvidenceRef",
        "EvidenceSupportStatus",
        "FmeaAnalysis",
        "FmeaRow",
        "PropagationEdge",
        "PublicationStatus",
        "ReviewStatus",
        "RiskAssessment",
        "RunStatus",
        "ScoringRulePack",
        "VersionSet",
    ]

    source_modules = {
        "ActorType": states,
        "ClaimStatus": states,
        "EvidencePack": value_objects,
        "EvidenceRef": value_objects,
        "EvidenceSupportStatus": states,
        "FmeaAnalysis": entities,
        "FmeaRow": entities,
        "PropagationEdge": propagation,
        "PublicationStatus": states,
        "ReviewStatus": states,
        "RiskAssessment": scoring,
        "RunStatus": states,
        "ScoringRulePack": scoring,
        "VersionSet": value_objects,
    }

    for name, source_module in source_modules.items():
        assert getattr(contracts, name) is getattr(source_module, name)
