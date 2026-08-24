from __future__ import annotations

from dataclasses import replace

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.states import ActorType, ClaimStatus, PublicationStatus, ReviewStatus
from fmea_application.services import FmeaService


class MemoryRepository:
    def __init__(self) -> None:
        self.analyses = {}
        self.packs = {}
        self.rows = {}
        self.edges = {}
        self.calls: list[str] = []

    def initialize(self) -> None:
        self.calls.append("initialize")

    def save_analysis(self, analysis, *, actor_id, actor_type, expected_record_version=None):
        self.calls.append("save_analysis")
        self.analyses[analysis.analysis_id] = analysis
        return analysis

    def get_analysis(self, analysis_id):
        return self.analyses.get(analysis_id)

    def save_evidence_pack(self, pack, *, actor_id, actor_type):
        self.calls.append("save_pack")
        self.packs[pack.pack_id] = pack
        return pack

    def get_evidence_pack(self, pack_id):
        return self.packs.get(pack_id)

    def save_row(self, row, *, actor_id, actor_type, expected_record_version=None):
        self.calls.append("save_row")
        self.rows[row.row_id] = row
        return row

    def get_row(self, row_id):
        return self.rows.get(row_id)

    def save_propagation_edge(self, edge, *, actor_id, actor_type, expected_record_version=None):
        self.calls.append("save_edge")
        self.edges[edge.edge_id] = edge
        return edge

    def get_propagation_edge(self, edge_id):
        return self.edges.get(edge_id)

    def append_audit_event(self, **event):
        self.calls.append("append_audit_event")
        return "audit-1"


def test_service_exposes_only_the_requested_persistence_entries() -> None:
    public_methods = {name for name in dir(FmeaService) if not name.startswith("_")}

    assert public_methods == {
        "create_analysis",
        "register_evidence_pack",
        "save_row",
        "save_propagation_edge",
        "persist_candidate_bundle",
    }


def test_service_delegates_direct_persistence_methods(
    fixture_analysis, fixture_pack, fixture_row, fixture_edge
) -> None:
    repository = MemoryRepository()
    service = FmeaService(repository)

    assert service.create_analysis(fixture_analysis, actor_id="runner", actor_type=ActorType.SYSTEM) == fixture_analysis
    assert service.register_evidence_pack(fixture_pack, actor_id="runner", actor_type=ActorType.SYSTEM) == fixture_pack
    assert service.save_row(fixture_row, actor_id="runner", actor_type=ActorType.SYSTEM) == fixture_row
    assert service.save_propagation_edge(fixture_edge, actor_id="runner", actor_type=ActorType.SYSTEM) == fixture_edge
    assert repository.calls == ["save_analysis", "save_pack", "save_row", "save_edge"]


def test_candidate_bundle_saves_pack_before_candidates_in_input_order(
    fixture_analysis, fixture_pack, fixture_row, fixture_edge
) -> None:
    repository = MemoryRepository()
    service = FmeaService(repository)
    second_row = replace(fixture_row, row_id="row-2")
    second_edge = replace(fixture_edge, edge_id="edge-2", path_length=3)

    result_rows, result_edges = service.persist_candidate_bundle(
        analysis=fixture_analysis,
        evidence_pack=fixture_pack,
        rows=(fixture_row, second_row),
        edges=(fixture_edge, second_edge),
        actor_id="runner",
        actor_type=ActorType.SYSTEM,
    )

    assert repository.calls == ["save_pack", "save_row", "save_row", "save_edge", "save_edge"]
    assert tuple(repository.rows) == (result_rows[0].row_id, result_rows[1].row_id)
    assert tuple(repository.edges) == (result_edges[0].edge_id, result_edges[1].edge_id)


def test_candidate_bundle_marks_rows_suggested_and_unpublished(
    fixture_analysis, fixture_pack, fixture_row, fixture_edge
) -> None:
    repository = MemoryRepository()
    service = FmeaService(repository)
    source_row = replace(
        fixture_row,
        review_status=ReviewStatus.DRAFT,
        publication_status=PublicationStatus.PUBLISHED,
    )

    result_rows, result_edges = service.persist_candidate_bundle(
        analysis=fixture_analysis,
        evidence_pack=fixture_pack,
        rows=(source_row,),
        edges=(fixture_edge,),
        actor_id="runner",
        actor_type=ActorType.SYSTEM,
    )

    assert result_rows[0].review_status is ReviewStatus.SUGGESTED
    assert result_rows[0].publication_status is PublicationStatus.UNPUBLISHED
    assert result_edges[0].review_status is ReviewStatus.SUGGESTED
    assert result_edges[0].publication_status is PublicationStatus.UNPUBLISHED
    assert source_row.review_status is ReviewStatus.DRAFT
    assert source_row.publication_status is PublicationStatus.PUBLISHED
    assert repository.rows[result_rows[0].row_id] == result_rows[0]


def test_candidate_bundle_routes_long_or_unsafe_edges_to_review(
    fixture_analysis, fixture_pack, fixture_edge
) -> None:
    repository = MemoryRepository()
    service = FmeaService(repository)
    long_edge = replace(fixture_edge, edge_id="edge-long", path_length=3)
    unknown_edge = replace(fixture_edge, edge_id="edge-unknown", claim_status=ClaimStatus.UNKNOWN)

    _, result_edges = service.persist_candidate_bundle(
        analysis=fixture_analysis,
        evidence_pack=fixture_pack,
        rows=(),
        edges=(long_edge, unknown_edge),
        actor_id="runner",
        actor_type=ActorType.SYSTEM,
    )

    assert all(edge.review_status is ReviewStatus.IN_REVIEW for edge in result_edges)
    assert all(edge.publication_status is PublicationStatus.UNPUBLISHED for edge in result_edges)


@pytest.mark.parametrize("invalid_kind", ("row_analysis", "edge_analysis", "row_pack", "edge_pack"))
def test_candidate_bundle_rejects_wrong_analysis_or_pack_before_writing(
    fixture_analysis, fixture_pack, fixture_row, fixture_edge, invalid_kind
) -> None:
    repository = MemoryRepository()
    service = FmeaService(repository)
    rows = (fixture_row,)
    edges = (fixture_edge,)
    if invalid_kind == "row_analysis":
        rows = (replace(fixture_row, analysis_id="other-analysis"),)
    elif invalid_kind == "edge_analysis":
        edges = (replace(fixture_edge, analysis_id="other-analysis"),)
    elif invalid_kind == "row_pack":
        rows = (replace(fixture_row, evidence_pack_id="other-pack"),)
    else:
        edges = (replace(fixture_edge, evidence_pack_id="other-pack"),)

    with pytest.raises(FmeaDomainError):
        service.persist_candidate_bundle(
            analysis=fixture_analysis,
            evidence_pack=fixture_pack,
            rows=rows,
            edges=edges,
            actor_id="runner",
            actor_type=ActorType.SYSTEM,
        )

    assert repository.calls == []


@pytest.mark.parametrize("invalid_kind", ("row_evidence", "edge_evidence"))
def test_candidate_bundle_rejects_missing_evidence_before_writing(
    fixture_analysis, fixture_pack, fixture_row, fixture_edge, invalid_kind
) -> None:
    repository = MemoryRepository()
    service = FmeaService(repository)
    rows = (replace(fixture_row, field_evidence=(("failure_mode", ("missing-id",)),)),)
    edges = (fixture_edge,)
    if invalid_kind == "edge_evidence":
        rows = (fixture_row,)
        edges = (replace(fixture_edge, evidence_ids=("missing-id",)),)

    with pytest.raises(FmeaDomainError, match="evidence ID"):
        service.persist_candidate_bundle(
            analysis=fixture_analysis,
            evidence_pack=fixture_pack,
            rows=rows,
            edges=edges,
            actor_id="runner",
            actor_type=ActorType.SYSTEM,
        )

    assert repository.calls == []


def test_candidate_bundle_validates_every_candidate_before_first_write(
    fixture_analysis, fixture_pack, fixture_row, fixture_edge
) -> None:
    repository = MemoryRepository()
    service = FmeaService(repository)
    invalid_row = replace(fixture_row, row_id="row-invalid", evidence_pack_id="other-pack")

    with pytest.raises(FmeaDomainError, match="EvidencePack"):
        service.persist_candidate_bundle(
            analysis=fixture_analysis,
            evidence_pack=fixture_pack,
            rows=(fixture_row, invalid_row),
            edges=(fixture_edge,),
            actor_id="runner",
            actor_type=ActorType.SYSTEM,
        )

    assert repository.calls == []
