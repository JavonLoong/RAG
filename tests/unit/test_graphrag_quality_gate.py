from __future__ import annotations

from rag_orchestrator import evaluate_graph_quality as exported_evaluate_graph_quality
from rag_orchestrator.graph_quality import GraphQualityThresholds, evaluate_graph_quality
from storage_layer.graph_store import GraphEdgeRecord, GraphStore


def test_graph_quality_gate_is_exported_from_rag_orchestrator() -> None:
    assert exported_evaluate_graph_quality is evaluate_graph_quality


def test_graph_quality_gate_passes_evidence_bound_graph(tmp_path) -> None:
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
    store.store_community_summaries(
        [
                {
                    "community_id": "C1",
                    "title": "Compressor fouling maintenance",
                    "summary": "Compressor fouling is mitigated by offline wash.",
                    "entity_count": 3,
                    "edge_count": 2,
                    "metadata": {
                        "evidence_triple_ids": ["t1", "t2"],
                        "sentence_evidence": [
                            {
                                "sentence_index": 0,
                                "evidence_triple_ids": ["t1", "t2"],
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

    report = evaluate_graph_quality(store)

    assert report.gate_status == "pass"
    assert report.metrics["evidence_coverage"] == 1.0
    assert report.metrics["community_summary_coverage"] == 1.0
    assert report.metrics["summary_evidence_coverage"] == 1.0
    assert report.metrics["summary_sentence_evidence_coverage"] == 1.0
    assert report.metrics["summary_sentence_source_coverage"] == 1.0
    assert report.to_dict()["quality_gate"]["status"] == "pass"


def test_graph_quality_gate_ignores_evidence_covered_isolated_noise_nodes(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.sqlite")
    store.import_edges(
        [
            GraphEdgeRecord(
                triple_id="t1",
                subject="Chat corpus",
                predicate="HAS_TOPIC",
                object_name="Rental discussion",
                evidence="The corpus contains private chat records discussing rental housing.",
                confidence=0.92,
                source_file="wechat_private_chunks_rag.json",
                source_chunk_id="chunk-1",
            ),
        ]
    )
    store.upsert_nodes([{"name": "qlogo", "type": "metadata_noise"}])
    store.store_communities(
        [
            {"community_id": "C1", "node_name": "Chat corpus"},
            {"community_id": "C1", "node_name": "Rental discussion"},
            {"community_id": "C1", "node_name": "qlogo"},
        ]
    )
    store.store_community_summaries(
        [
            {
                "community_id": "C1",
                "title": "Private chat corpus overview",
                "summary": "The community summarizes private chat records discussing rental housing.",
                "entity_count": 3,
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
                                    "text": "The corpus contains private chat records discussing rental housing.",
                                    "source_file": "wechat_private_chunks_rag.json",
                                    "source_chunk_id": "chunk-1",
                                }
                            ],
                        }
                    ],
                },
            }
        ]
    )

    report = evaluate_graph_quality(store)

    assert report.gate_status == "pass"
    assert report.metrics["node_count"] == 3
    assert report.metrics["quality_node_count"] == 2
    assert report.metrics["ignored_isolated_node_count"] == 1
    assert report.metrics["isolated_node_count"] == 0
    assert report.metrics["isolated_node_rate"] == 0.0
    assert report.details["isolated_nodes"] == []
    assert report.details["ignored_isolated_noise_nodes"] == ["qlogo"]


def test_graph_quality_gate_requires_sentence_level_summary_evidence(tmp_path) -> None:
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
    store.store_community_summaries(
        [
            {
                "community_id": "C1",
                "title": "Compressor fouling maintenance",
                "summary": "Compressor fouling raises temperature. Offline wash mitigates fouling.",
                "entity_count": 3,
                "edge_count": 2,
                "metadata": {"evidence_triple_ids": ["t1", "t2"]},
            }
        ]
    )

    report = evaluate_graph_quality(store)

    assert report.gate_status == "fail"
    assert report.metrics["summary_sentence_evidence_coverage"] == 0.0
    assert any(failure["metric"] == "summary_sentence_evidence_coverage" for failure in report.gate_failures)
    assert report.details["summaries_with_unbound_sentences"] == ["C1"]


def test_graph_quality_gate_requires_sentence_source_spans(tmp_path) -> None:
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
    store.store_community_summaries(
        [
            {
                "community_id": "C1",
                "title": "Compressor fouling maintenance",
                "summary": "Compressor fouling raises temperature. Offline wash mitigates fouling.",
                "entity_count": 3,
                "edge_count": 2,
                "metadata": {
                    "evidence_triple_ids": ["t1", "t2"],
                    "sentence_evidence": [
                        {"sentence_index": 0, "evidence_triple_ids": ["t1"]},
                        {"sentence_index": 1, "evidence_triple_ids": ["t2"]},
                    ],
                },
            }
        ]
    )

    report = evaluate_graph_quality(store)

    assert report.gate_status == "fail"
    assert report.metrics["summary_sentence_evidence_coverage"] == 1.0
    assert report.metrics["summary_sentence_source_coverage"] == 0.0
    assert any(failure["metric"] == "summary_sentence_source_coverage" for failure in report.gate_failures)
    assert report.details["summaries_with_missing_sentence_sources"] == ["C1"]


def test_graph_quality_gate_flags_unsafe_graph_for_graphrag(tmp_path) -> None:
    store = GraphStore(tmp_path / "graph.sqlite")
    store.import_edges(
        [
            GraphEdgeRecord(
                triple_id="t1",
                subject="Combustor",
                predicate="HAS_PROBLEM",
                object_name="Instability",
                evidence="Combustor instability evidence.",
                confidence=0.9,
            ),
            GraphEdgeRecord(
                triple_id="t2",
                subject="Instability",
                predicate="CAUSES",
                object_name="Noise",
                evidence=None,
                confidence=0.31,
            ),
        ]
    )
    store.upsert_nodes([{"name": "Detached Sensor", "type": "Sensor"}])
    store.store_communities(
        [
            {"community_id": "C1", "node_name": "Combustor"},
            {"community_id": "C1", "node_name": "Instability"},
        ]
    )

    report = evaluate_graph_quality(
        store,
        thresholds=GraphQualityThresholds(
            min_evidence_coverage=1.0,
            min_edge_confidence=0.7,
            max_isolated_node_rate=0.0,
            min_community_assignment_coverage=1.0,
            min_community_summary_coverage=1.0,
            min_summary_evidence_coverage=1.0,
        ),
    )

    assert report.gate_status == "fail"
    failure_metrics = {failure["metric"] for failure in report.gate_failures}
    assert "evidence_coverage" in failure_metrics
    assert "low_confidence_edge_rate" in failure_metrics
    assert "isolated_node_rate" in failure_metrics
    assert "community_assignment_coverage" in failure_metrics
    assert "community_summary_coverage" in failure_metrics
    assert report.metrics["missing_evidence_edge_count"] == 1
    assert report.details["missing_evidence_edges"] == ["t2"]
    assert "Detached Sensor" in report.details["isolated_nodes"]
