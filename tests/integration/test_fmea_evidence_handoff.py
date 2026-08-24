"""Executable handoff proof from query citations to FMEA candidates."""

from __future__ import annotations

import inspect
import subprocess
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import pytest

import fmea_infrastructure.evidence_provider as evidence_provider_module
from core_domain.fmea.states import ActorType
from core_domain.fmea.value_objects import EvidencePack, VersionSet
from core_domain.query_contracts import (
    AnswerPayload,
    Citation,
    CitationType,
    EvidenceSelectionProfile,
    ModeDecision,
    QueryMode,
    QueryRequest,
    QueryResponse,
    QueryStatus,
    RetrievalSummary,
    SourceRef,
    UsageMetrics,
    WarningItem,
)
from fmea_application.ports import EvidenceRequest
from fmea_application.services import FmeaService
from fmea_infrastructure.evidence_provider import QueryServiceEvidenceProvider


@dataclass
class FakeQueryService:
    response: QueryResponse
    requests: list[QueryRequest] = field(default_factory=list)

    def query(self, request: QueryRequest) -> QueryResponse:
        self.requests.append(request)
        return self.response


@dataclass
class MemoryRepository:
    packs: dict[str, EvidencePack] = field(default_factory=dict)
    rows: dict[str, object] = field(default_factory=dict)
    pack_save_calls: list[str] = field(default_factory=list)

    def save_evidence_pack(self, pack, *, actor_id, actor_type):
        self.pack_save_calls.append(pack.pack_id)
        self.packs[pack.pack_id] = pack
        return pack

    def get_evidence_pack(self, pack_id):
        return self.packs.get(pack_id)

    def save_row(self, row, *, actor_id, actor_type, expected_record_version=None):
        self.rows[row.row_id] = row
        return row

    def save_propagation_edge(self, edge, *, actor_id, actor_type, expected_record_version=None):
        raise AssertionError


def _text() -> Citation:
    return Citation(
        id="T1",
        type=CitationType.TEXT,
        source=SourceRef(document_id="manual-1", file="fuel-manual.pdf", page=12, chunk_id="chunk-12"),
        quote="Low fuel pressure can destabilize the flame.",
        metadata={"document_version": "manual-v1", "source_trust": "reviewed", "is_primary": True},
    )


def _graph() -> Citation:
    return Citation(
        id="G1",
        type=CitationType.GRAPH,
        source=SourceRef(document_id="graph-source-1"),
        triple={"subject": "fuel_filter", "predicate": "feeds", "object": "combustor"},
        quote="The fuel filter feeds the combustor.",
        metadata={"document_version": "graph-v1"},
    )


def _community() -> Citation:
    return Citation(
        id="C1",
        type=CitationType.COMMUNITY,
        quote="Fuel delivery faults can propagate to combustion stability.",
        metadata={"title": "Fuel and combustion coupling"},
    )


def _response(citations: tuple[Citation, ...], warnings: tuple[WarningItem, ...] = ()) -> QueryResponse:
    return QueryResponse(
        request_id="query-1",
        trace_id="trace-1",
        status=QueryStatus.PARTIAL if warnings else QueryStatus.OK,
        mode=ModeDecision(requested=QueryMode.AUTO, used=QueryMode.AUTO, reason="evidence profile"),
        answer=AnswerPayload(text="", finish_reason="stop"),
        citations=list(citations),
        retrieval=RetrievalSummary(
            text_hits=sum(item.type is CitationType.TEXT for item in citations),
            graph_hits=sum(item.type is CitationType.GRAPH for item in citations),
            community_hits=sum(item.type is CitationType.COMMUNITY for item in citations),
        ),
        usage=UsageMetrics(latency_ms=1.0),
        warnings=list(warnings),
    )


@pytest.mark.parametrize(
    ("profile", "evidence_types", "citations", "warnings", "expected_sources", "incomplete"),
    [
        (EvidenceSelectionProfile.RAG_ONLY, (), (_text(),), (), ("rag_text",), False),
        (
            EvidenceSelectionProfile.GRAPHRAG_LOCAL_ONLY,
            (),
            (_graph(),),
            (),
            ("graphrag_relation",),
            False,
        ),
        (
            EvidenceSelectionProfile.GRAPHRAG_GLOBAL_ONLY,
            (),
            (_community(),),
            (),
            ("graphrag_community",),
            False,
        ),
        (
            EvidenceSelectionProfile.GRAPHRAG_ONLY,
            (),
            (_graph(), _community()),
            (),
            ("graphrag_relation", "graphrag_community"),
            False,
        ),
        (
            EvidenceSelectionProfile.COMBINED,
            (),
            (_text(), _graph(), _community()),
            (),
            ("rag_text", "graphrag_relation", "graphrag_community"),
            False,
        ),
        (
            EvidenceSelectionProfile.COMBINED,
            (),
            (_text(),),
            (WarningItem(code="GRAPH_RETRIEVAL_DEGRADED", message="Graph sources are unavailable."),),
            ("rag_text",),
            True,
        ),
        (
            EvidenceSelectionProfile.CUSTOM,
            (CitationType.TEXT, CitationType.COMMUNITY),
            (_text(), _community()),
            (),
            ("rag_text", "graphrag_community"),
            False,
        ),
    ],
)
def test_query_evidence_snapshot_hands_one_pack_to_fmea_candidates(
    fixture_versions: VersionSet,
    fixture_analysis,
    fixture_row,
    profile: EvidenceSelectionProfile,
    evidence_types: tuple[CitationType, ...],
    citations: tuple[Citation, ...],
    warnings: tuple[WarningItem, ...],
    expected_sources: tuple[str, ...],
    incomplete: bool,
) -> None:
    query_service = FakeQueryService(_response(citations, warnings))
    repository = MemoryRepository()
    provider = QueryServiceEvidenceProvider(
        query_service,
        repository,
        clock=lambda: "2026-08-24T00:00:00Z",
        pack_id_factory=lambda: "pack-handoff",
    )
    request = EvidenceRequest(
        workspace_id="ws-1",
        analysis_id=fixture_analysis.analysis_id,
        query="燃料压力下降如何影响燃烧稳定性?",
        versions=fixture_versions,
        acl_scope=("engineering",),
        evidence_profile=profile,
        evidence_types=evidence_types,
    )

    snapshot = provider.create_snapshot(request)
    evidence_ids = tuple(ref.evidence_id for ref in snapshot.pack.refs)
    candidate = replace(
        fixture_row,
        row_id=f"row-{profile.value}",
        evidence_pack_id=snapshot.pack.pack_id,
        field_evidence=(("failure_mode", evidence_ids),),
    )
    saved_rows, _ = FmeaService(repository).persist_candidate_bundle(
        fixture_analysis,
        snapshot.pack,
        (candidate,),
        (),
        actor_id="fmea-test",
        actor_type=ActorType.SYSTEM,
    )

    assert len(query_service.requests) == 1
    assert query_service.requests[0].evidence_profile is profile
    assert query_service.requests[0].evidence_types == evidence_types
    assert tuple(ref.source_type for ref in snapshot.pack.refs) == expected_sources
    assert snapshot.incomplete is incomplete
    assert len(repository.packs) == 1
    candidate_ids = {item for _, ids in saved_rows[0].field_evidence for item in ids}
    assert candidate_ids == set(evidence_ids)
    for evidence_id in candidate_ids:
        containing_packs = [pack for pack in repository.packs.values() if pack.ref_by_id(evidence_id)]
        assert containing_packs == [snapshot.pack]


def test_handoff_keeps_query_and_storage_implementations_replaceable(fixture_versions: VersionSet) -> None:
    assert FakeQueryService.__mro__ == (FakeQueryService, object)

    forbidden_backends = ("chroma", "neo4j", "graphstore")
    concrete_types = {
        name.lower()
        for name, value in vars(evidence_provider_module).items()
        if inspect.isclass(value) and value.__module__ == evidence_provider_module.__name__
    }
    assert not any(token in name for token in forbidden_backends for name in concrete_types)

    repository = MemoryRepository()
    provider = QueryServiceEvidenceProvider(
        FakeQueryService(_response((_text(),))),
        repository,
        clock=lambda: "2026-08-24T00:00:00Z",
        pack_id_factory=lambda: "pack-boundary",
    )
    snapshot = provider.create_snapshot(
        EvidenceRequest(
            workspace_id="ws-1",
            analysis_id="analysis-1",
            query="fuel pressure",
            versions=fixture_versions,
            acl_scope=("engineering",),
            evidence_profile=EvidenceSelectionProfile.RAG_ONLY,
        )
    )
    serialized_ref = asdict(snapshot.pack.refs[0])
    assert {"score", "rank", "metadata", "prompt"}.isdisjoint(serialized_ref)


def test_query_contract_import_does_not_pull_fmea_packages() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    script = (
        "import sys; import core_domain.query_contracts; "
        "print(any(name == 'fmea_application' or name.startswith('fmea_application.') "
        "or name == 'fmea_infrastructure' or name.startswith('fmea_infrastructure.') "
        "for name in sys.modules))"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"
