"""Behavioral tests for the QueryService-to-FMEA evidence adapter."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from core_domain.fmea.errors import FmeaDomainError
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
from fmea_infrastructure.evidence_provider import QueryServiceEvidenceProvider


@dataclass
class RecordingQueryPort:
    response: QueryResponse
    calls: list[QueryRequest] = field(default_factory=list)

    def query(self, request: QueryRequest) -> QueryResponse:
        self.calls.append(request)
        return self.response


@dataclass
class RecordingFmeaRepository:
    saved_packs: list[EvidencePack] = field(default_factory=list)

    @property
    def save_pack_calls(self) -> int:
        return len(self.saved_packs)

    def save_evidence_pack(self, pack: EvidencePack, *, actor_id: str, actor_type: ActorType) -> EvidencePack:
        self.saved_packs.append(pack)
        return pack

    def get_evidence_pack(self, pack_id: str) -> EvidencePack | None:
        return next((pack for pack in self.saved_packs if pack.pack_id == pack_id), None)


def _query_response() -> QueryResponse:
    return QueryResponse(
        request_id="request-1",
        trace_id="trace-1",
        status=QueryStatus.OK,
        mode=ModeDecision(requested=QueryMode.AUTO, used=QueryMode.AUTO, reason="evidence"),
        answer=AnswerPayload(text="", finish_reason="stop"),
        citations=[
            Citation(
                id="T1",
                type=CitationType.TEXT,
                source=SourceRef(document_id="doc-1", file="manual.pdf", page=12, chunk_id="chunk-1"),
                quote="fuel pressure is monitored",
                metadata={"document_version": "doc-v1"},
            ),
            Citation(
                id="G1",
                type=CitationType.GRAPH,
                source=SourceRef(document_id="doc-2"),
                triple={"subject": "fuel", "predicate": "feeds", "object": "combustor"},
                quote="fuel feeds combustor",
                metadata={"document_version": "graph-v1"},
            ),
            Citation(
                id="C1",
                type=CitationType.COMMUNITY,
                quote="fuel system community",
                metadata={"title": "Fuel system"},
            ),
        ],
        retrieval=RetrievalSummary(text_hits=1, graph_hits=1, community_hits=1),
        usage=UsageMetrics(latency_ms=1.0),
    )


def _response(citations: list[Citation], warnings: list[WarningItem] | None = None) -> QueryResponse:
    response = _query_response()
    return response.model_copy(update={"citations": citations, "warnings": warnings or []})


def _request(
    fixture_versions: VersionSet,
    *,
    profile: EvidenceSelectionProfile = EvidenceSelectionProfile.COMBINED,
    evidence_types: tuple[CitationType, ...] = (),
) -> EvidenceRequest:
    return EvidenceRequest(
        workspace_id="ws-1",
        analysis_id="analysis-1",
        query="fuel pressure to combustor",
        versions=fixture_versions,
        acl_scope=("engineering",),
        evidence_profile=profile,
        evidence_types=evidence_types,
    )


def _provider(
    response: QueryResponse,
) -> tuple[QueryServiceEvidenceProvider, RecordingQueryPort, RecordingFmeaRepository]:
    query_service = RecordingQueryPort(response)
    repository = RecordingFmeaRepository()
    provider = QueryServiceEvidenceProvider(
        query_service=query_service,
        repository=repository,
        clock=lambda: "2026-08-24T00:00:00Z",
        pack_id_factory=lambda: "pack-1",
    )
    return provider, query_service, repository


def _text_citation(
    citation_id: str = "T1",
    *,
    quote: str = "fuel pressure is monitored",
    page: int = 12,
    document_id: str = "doc-1",
    document_version: str = "doc-v1",
    metadata: dict[str, object] | None = None,
    score: float | None = 0.1,
) -> Citation:
    citation_metadata = {"document_version": document_version}
    if metadata:
        citation_metadata.update(metadata)
    return Citation(
        id=citation_id,
        type=CitationType.TEXT,
        source=SourceRef(document_id=document_id, file="manual.pdf", page=page, chunk_id="chunk-1"),
        quote=quote,
        score=score,
        metadata=citation_metadata,
    )


def _graph_citation(
    citation_id: str = "G1",
    *,
    quote: str = "fuel feeds combustor",
    metadata: dict[str, object] | None = None,
) -> Citation:
    citation_metadata = {"document_version": "graph-v1"}
    if metadata:
        citation_metadata.update(metadata)
    return Citation(
        id=citation_id,
        type=CitationType.GRAPH,
        triple={"subject": "fuel", "predicate": "feeds", "object": "combustor"},
        quote=quote,
        metadata=citation_metadata,
    )


def _community_citation(citation_id: str = "C1") -> Citation:
    return Citation(
        id=citation_id,
        type=CitationType.COMMUNITY,
        quote="fuel system community",
        metadata={"title": "Fuel system"},
    )


def test_create_snapshot_makes_one_evidence_query_and_one_pack_save(
    fixture_versions: VersionSet,
) -> None:
    query_service = RecordingQueryPort(_query_response())
    repository = RecordingFmeaRepository()
    provider = QueryServiceEvidenceProvider(
        query_service=query_service,
        repository=repository,
        clock=lambda: "2026-08-24T00:00:00Z",
        pack_id_factory=lambda: "pack-1",
    )

    snapshot = provider.create_snapshot(
        EvidenceRequest(
            workspace_id="ws-1",
            analysis_id="analysis-1",
            query="fuel pressure to combustor",
            versions=fixture_versions,
            acl_scope=("engineering",),
            evidence_profile=EvidenceSelectionProfile.COMBINED,
        )
    )

    assert len(query_service.calls) == 1
    assert query_service.calls[0].mode is QueryMode.AUTO
    assert query_service.calls[0].evidence_only is True
    assert query_service.calls[0].evidence_profile is EvidenceSelectionProfile.COMBINED
    assert query_service.calls[0].include_context is True
    assert query_service.calls[0].top_k == 20
    assert [ref.source_type for ref in snapshot.pack.refs] == [
        "rag_text",
        "graphrag_relation",
        "graphrag_community",
    ]
    assert snapshot.pack.refs[0].locator == '{"chunk_id":"chunk-1","document_id":"doc-1","file":"manual.pdf","page":12}'
    assert snapshot.pack.refs[1].locator == '{"document_id":"doc-2","edge_id":"G1","object":"combustor","predicate":"feeds","subject":"fuel"}'
    assert snapshot.pack.refs[2].locator == '{"community_id":"C1","title":"Fuel system"}'
    assert all(ref.created_at == "2026-08-24T00:00:00Z" for ref in snapshot.pack.refs)
    assert repository.save_pack_calls == 1


def test_exact_duplicate_citations_are_counted_before_deduplication(
    fixture_versions: VersionSet,
) -> None:
    citation = _text_citation()
    provider, _, _ = _provider(_response([citation, citation]))

    snapshot = provider.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY))

    assert snapshot.source_counts == (
        (CitationType.TEXT, 2),
        (CitationType.GRAPH, 0),
        (CitationType.COMMUNITY, 0),
    )
    assert len(snapshot.pack.refs) == 1
    assert snapshot.incomplete is False


def test_different_locator_version_or_source_type_creates_distinct_refs(
    fixture_versions: VersionSet,
) -> None:
    text = _text_citation()
    other_page = _text_citation(page=13)
    other_version = _text_citation(document_version="doc-v2")
    graph = _graph_citation(quote=text.quote)
    provider, _, _ = _provider(_response([text, other_page, other_version, graph]))

    snapshot = provider.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.COMBINED))

    assert len(snapshot.pack.refs) == 4
    assert len({ref.evidence_hash for ref in snapshot.pack.refs}) == 4
    assert [ref.source_type for ref in snapshot.pack.refs] == [
        "rag_text",
        "rag_text",
        "rag_text",
        "graphrag_relation",
    ]


def test_refs_and_counts_use_stable_text_graph_community_order(
    fixture_versions: VersionSet,
) -> None:
    provider, _, _ = _provider(_response([_community_citation(), _text_citation(), _graph_citation()]))

    snapshot = provider.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.COMBINED))

    assert [ref.source_type for ref in snapshot.pack.refs] == [
        "rag_text",
        "graphrag_relation",
        "graphrag_community",
    ]
    assert snapshot.source_counts == (
        (CitationType.TEXT, 1),
        (CitationType.GRAPH, 1),
        (CitationType.COMMUNITY, 1),
    )


def test_conflicting_allowlisted_identity_facts_retain_both_refs_and_warn(
    fixture_versions: VersionSet,
) -> None:
    first = _text_citation()
    conflicting = _text_citation(page=13)
    provider, _, _ = _provider(_response([first, conflicting]))

    snapshot = provider.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY))

    assert len(snapshot.pack.refs) == 2
    assert snapshot.warnings == (
        "EVIDENCE_IDENTITY_CONFLICT: citation identity has conflicting allowlisted provenance.",
    )
    assert snapshot.incomplete is True


@pytest.mark.parametrize(
    ("profile", "citations", "expected_types", "incomplete"),
    [
        (
            EvidenceSelectionProfile.RAG_ONLY,
            [_text_citation()],
            ["rag_text"],
            False,
        ),
        (
            EvidenceSelectionProfile.GRAPHRAG_ONLY,
            [_graph_citation(), _community_citation()],
            ["graphrag_relation", "graphrag_community"],
            False,
        ),
        (
            EvidenceSelectionProfile.COMBINED,
            [_text_citation()],
            ["rag_text"],
            True,
        ),
    ],
)
def test_named_profiles_use_selected_zero_source_types_for_incomplete_state(
    fixture_versions: VersionSet,
    profile: EvidenceSelectionProfile,
    citations: list[Citation],
    expected_types: list[str],
    incomplete: bool,
) -> None:
    provider, _, _ = _provider(_response(citations))

    snapshot = provider.create_snapshot(_request(fixture_versions, profile=profile))

    assert [ref.source_type for ref in snapshot.pack.refs] == expected_types
    assert snapshot.incomplete is incomplete


def test_custom_profile_preserves_requested_types_in_one_query(
    fixture_versions: VersionSet,
) -> None:
    requested = (CitationType.COMMUNITY, CitationType.TEXT)
    provider, query_service, _ = _provider(_response([_text_citation(), _community_citation()]))

    snapshot = provider.create_snapshot(
        _request(
            fixture_versions,
            profile=EvidenceSelectionProfile.CUSTOM,
            evidence_types=requested,
        )
    )

    assert query_service.calls[0].evidence_types == requested
    assert snapshot.incomplete is False


def test_auto_is_incomplete_for_query_warnings_or_empty_citations(
    fixture_versions: VersionSet,
) -> None:
    warning_response = _response(
        [_text_citation()],
        [WarningItem(code="GRAPH_RETRIEVAL_DEGRADED", message="Graph unavailable.")],
    )
    warning_provider, _, _ = _provider(warning_response)
    warning_snapshot = warning_provider.create_snapshot(
        _request(fixture_versions, profile=EvidenceSelectionProfile.AUTO)
    )

    empty_provider, _, _ = _provider(_response([]))
    empty_snapshot = empty_provider.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.AUTO))

    assert warning_snapshot.warnings == ("GRAPH_RETRIEVAL_DEGRADED: Graph unavailable.",)
    assert warning_snapshot.incomplete is True
    assert empty_snapshot.pack.refs == ()
    assert empty_snapshot.incomplete is True


def test_invalid_citation_material_is_warned_and_never_promoted(
    fixture_versions: VersionSet,
) -> None:
    invalid_text = _text_citation(quote="   ")
    invalid_graph = Citation(id="G1", type=CitationType.GRAPH, quote="relation without triple")
    provider, _, _ = _provider(_response([invalid_text, invalid_graph]))

    snapshot = provider.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.COMBINED))

    assert snapshot.pack.refs == ()
    assert snapshot.warnings == (
        "INVALID_EVIDENCE_CITATION: citation 'T1' has empty or invalid material.",
        "INVALID_EVIDENCE_CITATION: citation 'G1' has empty or invalid material.",
    )
    assert snapshot.incomplete is True


def test_only_allowlisted_fields_affect_hashes_not_score_or_arbitrary_metadata(
    fixture_versions: VersionSet,
) -> None:
    first = _text_citation(metadata={"source_trust": "reviewed", "is_primary": True, "secret": "one"}, score=0.1)
    second = _text_citation(metadata={"source_trust": "reviewed", "is_primary": True, "secret": "two"}, score=0.9)
    provider_a, _, _ = _provider(_response([first]))
    provider_b, _, _ = _provider(_response([second]))

    first_ref = provider_a.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY)).pack.refs[0]
    second_ref = provider_b.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY)).pack.refs[0]

    assert first_ref.evidence_id == second_ref.evidence_id
    assert first_ref.evidence_hash == second_ref.evidence_hash
    assert first_ref.content_hash == second_ref.content_hash
    assert first_ref.source_trust == "reviewed"
    assert first_ref.is_primary is True


def test_identical_identity_conflicting_metadata_merges_order_independently(
    fixture_versions: VersionSet,
) -> None:
    reviewed_primary = _text_citation(metadata={"source_trust": "reviewed", "is_primary": True})
    unreviewed_non_primary = _text_citation(metadata={"source_trust": "unreviewed", "is_primary": False})
    forward_provider, _, _ = _provider(_response([reviewed_primary, unreviewed_non_primary]))
    reverse_provider, _, _ = _provider(_response([unreviewed_non_primary, reviewed_primary]))

    forward_snapshot = forward_provider.create_snapshot(
        _request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY)
    )
    reverse_snapshot = reverse_provider.create_snapshot(
        _request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY)
    )

    assert forward_snapshot.pack.refs == reverse_snapshot.pack.refs
    assert forward_snapshot.warnings == reverse_snapshot.warnings == (
        "EVIDENCE_METADATA_CONFLICT: identical evidence identity has conflicting allowlisted metadata.",
    )
    ref = forward_snapshot.pack.refs[0]
    assert ref.source_trust == "conflict"
    assert ref.is_primary is False


def test_trust_only_conflict_downgrades_primary_even_when_primary_agrees(
    fixture_versions: VersionSet,
) -> None:
    reviewed_primary = _text_citation(metadata={"source_trust": "reviewed", "is_primary": True})
    unreviewed_primary = _text_citation(metadata={"source_trust": "unreviewed", "is_primary": True})
    forward_provider, _, _ = _provider(_response([reviewed_primary, unreviewed_primary]))
    reverse_provider, _, _ = _provider(_response([unreviewed_primary, reviewed_primary]))

    forward_snapshot = forward_provider.create_snapshot(
        _request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY)
    )
    reverse_snapshot = reverse_provider.create_snapshot(
        _request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY)
    )

    assert forward_snapshot.pack.refs == reverse_snapshot.pack.refs
    assert forward_snapshot.warnings == reverse_snapshot.warnings == (
        "EVIDENCE_METADATA_CONFLICT: identical evidence identity has conflicting allowlisted metadata.",
    )
    assert forward_snapshot.pack.refs[0].source_trust == "conflict"
    assert forward_snapshot.pack.refs[0].is_primary is False


def test_primary_only_conflict_downgrades_trust_even_when_trust_agrees(
    fixture_versions: VersionSet,
) -> None:
    reviewed_primary = _text_citation(metadata={"source_trust": "reviewed", "is_primary": True})
    reviewed_non_primary = _text_citation(metadata={"source_trust": "reviewed", "is_primary": False})
    forward_provider, _, _ = _provider(_response([reviewed_primary, reviewed_non_primary]))
    reverse_provider, _, _ = _provider(_response([reviewed_non_primary, reviewed_primary]))

    forward_snapshot = forward_provider.create_snapshot(
        _request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY)
    )
    reverse_snapshot = reverse_provider.create_snapshot(
        _request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY)
    )

    assert forward_snapshot.pack.refs == reverse_snapshot.pack.refs
    assert forward_snapshot.warnings == reverse_snapshot.warnings == (
        "EVIDENCE_METADATA_CONFLICT: identical evidence identity has conflicting allowlisted metadata.",
    )
    assert forward_snapshot.pack.refs[0].source_trust == "conflict"
    assert forward_snapshot.pack.refs[0].is_primary is False


def test_fallback_ids_versions_acl_and_literal_provenance_mapping(
    fixture_versions: VersionSet,
) -> None:
    text = Citation(
        id="T-fallback",
        type=CitationType.TEXT,
        source=SourceRef(file="manual.pdf"),
        quote="text evidence",
        metadata={"document_version": 42, "source_trust": "   ", "is_primary": 1, "rank": 5},
    )
    graph = Citation(
        id="G-fallback",
        type=CitationType.GRAPH,
        triple={"subject": "fuel", "predicate": "feeds", "object": "combustor"},
        quote="graph evidence",
        metadata={"document_version": None, "source_trust": None, "is_primary": False},
    )
    community = Citation(
        id="C-fallback",
        type=CitationType.COMMUNITY,
        quote="community evidence",
        metadata={"title": 123},
    )
    provider, _, _ = _provider(_response([text, graph, community]))

    snapshot = provider.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.COMBINED))

    text_ref, graph_ref, community_ref = snapshot.pack.refs
    assert text_ref.document_id == "text:ws-1:T-fallback"
    assert text_ref.document_version == "data-1"
    assert text_ref.locator == '{"file":"manual.pdf"}'
    assert text_ref.acl_scope == ("engineering",)
    assert text_ref.source_trust == "unrated"
    assert text_ref.is_primary is False
    assert graph_ref.document_id == "graph:graph-1:G-fallback"
    assert graph_ref.document_version == "graph-1"
    assert graph_ref.locator == '{"edge_id":"G-fallback","object":"combustor","predicate":"feeds","subject":"fuel"}'
    assert community_ref.document_id == "community:graph-1:C-fallback"
    assert community_ref.document_version == "graph-1"
    assert community_ref.locator == '{"community_id":"C-fallback"}'


def test_text_locator_strips_strings_and_omits_blank_source_fields(
    fixture_versions: VersionSet,
) -> None:
    citation = Citation(
        id="T-whitespace",
        type=CitationType.TEXT,
        source=SourceRef(
            document_id="  doc-1  ",
            file="   ",
            page="  12  ",
            chunk_id="  chunk-1  ",
        ),
        quote="text evidence",
    )
    provider, _, _ = _provider(_response([citation]))

    ref = provider.create_snapshot(
        _request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY)
    ).pack.refs[0]

    assert ref.document_id == "doc-1"
    assert ref.locator == '{"chunk_id":"chunk-1","document_id":"doc-1","page":"12"}'


def test_read_refs_preserves_requested_order_and_does_not_query(
    fixture_versions: VersionSet,
) -> None:
    provider, query_service, repository = _provider(_response([_text_citation(), _graph_citation()]))
    snapshot = provider.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.COMBINED))
    requested_ids = (snapshot.pack.refs[1].evidence_id, snapshot.pack.refs[0].evidence_id)

    refs = provider.read_refs(snapshot.pack, requested_ids)

    assert tuple(ref.evidence_id for ref in refs) == requested_ids
    assert len(query_service.calls) == 1
    assert repository.save_pack_calls == 1
    with pytest.raises(FmeaDomainError, match="evidence ID missing"):
        provider.read_refs(snapshot.pack, ("missing",))


def test_load_pack_reads_once_rejects_missing_and_workspace_mismatch(
    fixture_versions: VersionSet,
) -> None:
    provider, query_service, repository = _provider(_response([_text_citation()]))
    snapshot = provider.create_snapshot(_request(fixture_versions, profile=EvidenceSelectionProfile.RAG_ONLY))

    assert provider.load_pack("ws-1", "pack-1") is snapshot.pack
    assert len(query_service.calls) == 1
    assert repository.save_pack_calls == 1
    with pytest.raises(FmeaDomainError, match="was not found"):
        provider.load_pack("ws-1", "missing")
    with pytest.raises(FmeaDomainError, match="does not match"):
        provider.load_pack("other-workspace", "pack-1")
