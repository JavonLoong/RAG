from __future__ import annotations

from kg_pipeline.community_summary import summarize_communities
from storage_layer.graph_store import GraphEdgeRecord, GraphStore


class FakeSummaryLLM:
    def generate(self, prompt: str) -> str:
        return (
            '{"title": "Compressor fouling maintenance", '
            '"summary": "Compressor fouling raises outlet temperature. Offline wash mitigates fouling."}'
        )


def test_summarize_communities_stores_sentence_level_evidence_bindings(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.sqlite")
    store.import_edges(
        [
            GraphEdgeRecord(
                triple_id="t1",
                subject="Compressor",
                predicate="HAS_RISK",
                object_name="Fouling",
                evidence="Compressor fouling raises outlet temperature.",
                confidence=0.92,
            ),
            GraphEdgeRecord(
                triple_id="t2",
                subject="Fouling",
                predicate="MITIGATED_BY",
                object_name="Offline Wash",
                evidence="Offline compressor wash mitigates fouling.",
                confidence=0.88,
            ),
        ]
    )
    store.store_communities(
        [
            {"community_id": "C1", "node_name": "Compressor"},
            {"community_id": "C1", "node_name": "Fouling"},
            {"community_id": "C1", "node_name": "Offline Wash"},
        ]
    )

    result = summarize_communities(store, FakeSummaryLLM(), min_community_size=1)

    assert result.communities_processed == 1
    export = store.export_graph()
    metadata = export["community_summaries"][0]["metadata"]
    assert metadata["evidence_triple_ids"] == ["t1", "t2"]
    assert [item["sentence_index"] for item in metadata["sentence_evidence"]] == [0, 1]
    assert metadata["sentence_evidence"][0]["evidence_triple_ids"]
    assert metadata["sentence_evidence"][1]["evidence_triple_ids"]


def test_summarize_communities_stores_sentence_source_evidence_spans(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.sqlite")
    store.import_edges(
        [
            GraphEdgeRecord(
                triple_id="t1",
                subject="Compressor",
                predicate="HAS_RISK",
                object_name="Fouling",
                evidence="Compressor fouling raises outlet temperature.",
                confidence=0.92,
                source_file="manual.pdf",
                source_page="12",
                source_chunk_id="chunk-12-a",
            ),
            GraphEdgeRecord(
                triple_id="t2",
                subject="Fouling",
                predicate="MITIGATED_BY",
                object_name="Offline Wash",
                evidence="Offline compressor wash mitigates fouling.",
                confidence=0.88,
                source_file="manual.pdf",
                source_page="13",
                source_chunk_id="chunk-13-b",
            ),
        ]
    )
    store.store_communities(
        [
            {"community_id": "C1", "node_name": "Compressor"},
            {"community_id": "C1", "node_name": "Fouling"},
            {"community_id": "C1", "node_name": "Offline Wash"},
        ]
    )

    summarize_communities(store, FakeSummaryLLM(), min_community_size=1)

    export = store.export_graph()
    bindings = export["community_summaries"][0]["metadata"]["sentence_evidence"]
    first_source = bindings[0]["source_evidence"][0]
    second_source = bindings[1]["source_evidence"][0]
    assert first_source == {
        "triple_id": "t1",
        "text": "Compressor fouling raises outlet temperature.",
        "source_file": "manual.pdf",
        "source_page": "12",
        "source_chunk_id": "chunk-12-a",
    }
    assert second_source == {
        "triple_id": "t2",
        "text": "Offline compressor wash mitigates fouling.",
        "source_file": "manual.pdf",
        "source_page": "13",
        "source_chunk_id": "chunk-13-b",
    }


def test_get_community_summaries_returns_source_evidence_metadata(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.sqlite")
    store.import_edges(
        [
            GraphEdgeRecord(
                triple_id="t1",
                subject="Compressor",
                predicate="HAS_RISK",
                object_name="Fouling",
                evidence="Compressor fouling raises outlet temperature.",
                confidence=0.92,
                source_file="manual.pdf",
                source_page="12",
            )
        ]
    )
    store.store_communities(
        [
            {"community_id": "C1", "node_name": "Compressor"},
            {"community_id": "C1", "node_name": "Fouling"},
        ]
    )
    store.store_community_summaries(
        [
            {
                "community_id": "C1",
                "title": "Compressor fouling maintenance",
                "summary": "Compressor fouling raises outlet temperature.",
                "entity_count": 2,
                "edge_count": 1,
                "metadata": {
                    "evidence_triple_ids": ["t1"],
                    "sentence_evidence": [
                        {
                            "sentence_index": 0,
                            "evidence_triple_ids": ["t1"],
                            "source_evidence": [
                                {
                                    "triple_id": "t1",
                                    "text": "Compressor fouling raises outlet temperature.",
                                    "source_file": "manual.pdf",
                                    "source_page": "12",
                                }
                            ],
                        }
                    ],
                },
            }
        ]
    )

    summaries = store.get_community_summaries()

    assert summaries[0]["metadata"]["sentence_evidence"][0]["source_evidence"][0] == {
        "triple_id": "t1",
        "text": "Compressor fouling raises outlet temperature.",
        "source_file": "manual.pdf",
        "source_page": "12",
    }
