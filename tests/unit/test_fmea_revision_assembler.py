from __future__ import annotations

from dataclasses import replace
from inspect import signature

import pytest
from fmea_governance_fixtures import make_assemble_request, make_governance_inputs

from core_domain.fmea.entities import FmeaRow
from core_domain.fmea.states import ReviewStatus


def _implementation():
    try:
        from fmea_application.revision_assembler import RevisionAssembler
    except ModuleNotFoundError as exc:
        pytest.fail(f"Task 2 production implementation is missing: {exc}")
    return RevisionAssembler


def _row(fixture_row: FmeaRow, row_id: str) -> FmeaRow:
    return replace(fixture_row, row_id=row_id, review_status=ReviewStatus.ACCEPTED)


def _inputs(*, rows: tuple[FmeaRow, ...] = (), **overrides: object) -> dict[str, object]:
    values: dict[str, object] = make_governance_inputs(
        workspace_id="ws-1",
        analysis_id="analysis-1",
        rows=rows,
        evidence_packs=(),
        domain_pack={
            "pack_id": "generic-domain",
            "version": "1.0.0",
            "content_hash": "a" * 64,
        },
        version_identities=(
            ("generic-template", "1.0.0", "b" * 64),
            ("generic-scoring", "1.0.0", "c" * 64),
        ),
        requested_profile="combined",
        resolved_profile="combined",
        evidence_types=("graph", "text"),
    )
    values.update(overrides)
    return values


def test_revision_assembler_is_order_independent(fixture_row: FmeaRow):
    assembler = _implementation()()
    first = assembler.assemble(
        make_assemble_request(),
        _inputs(rows=(_row(fixture_row, "row-b"), _row(fixture_row, "row-a"))),
    )
    second = assembler.assemble(
        make_assemble_request(),
        _inputs(rows=(_row(fixture_row, "row-a"), _row(fixture_row, "row-b"))),
    )
    assert first.revision_hash == second.revision_hash


def test_revision_assembler_constructor_has_no_retrieval_dependency():
    RevisionAssembler = _implementation()
    assert set(signature(RevisionAssembler).parameters) <= {"self", "clock", "id_factory"}


def test_assembler_preserves_retrieval_provenance_without_retrieval_dependency():
    RevisionAssembler = _implementation()
    inputs = _inputs(
        requested_profile="graphrag_only",
        resolved_profile="graphrag_only",
        evidence_types=("graph", "community"),
    )
    revision = RevisionAssembler().assemble(make_assemble_request(), inputs)
    assert revision.retrieval_provenance.resolved_profile == "graphrag_only"
    assert revision.retrieval_provenance.evidence_types == ("community", "graph")


def test_assembler_rejects_mixed_workspace_records(fixture_row: FmeaRow):
    RevisionAssembler = _implementation()
    foreign_row = replace(_row(fixture_row, "row-foreign"), analysis_id="analysis-2")
    with pytest.raises(ValueError, match="analysis"):
        RevisionAssembler().assemble(make_assemble_request(), _inputs(rows=(foreign_row,)))


def test_assembler_does_not_accept_client_resource_overrides():
    RevisionAssembler = _implementation()
    with pytest.raises(TypeError):
        RevisionAssembler().assemble(
            make_assemble_request(),
            _inputs(domain_pack_id="client-selected-pack"),
        )
