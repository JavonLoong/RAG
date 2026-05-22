import json
import sqlite3

from storage_layer.graph_store import GraphStore, import_kg_file


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_import_triples_json_to_sqlite_and_query(tmp_path):
    triples_path = tmp_path / "triples.json"
    db_path = tmp_path / "graph_store.sqlite"
    cypher_path = tmp_path / "neo4j_import.cypher"

    write_json(
        triples_path,
        {
            "summary": {"source": "unit-test"},
            "triples": [
                {
                    "id": "T-001",
                    "subject": "Gas turbine",
                    "subject_type": "Equipment",
                    "predicate": "HAS_COMPONENT",
                    "object": "Compressor",
                    "object_type": "Component",
                    "evidence": "A gas turbine includes a compressor.",
                    "source_file": "manual.pdf",
                    "source_page": 7,
                    "source_chunk_id": "chunk-7",
                    "confidence": 0.91,
                },
                {
                    "id": "T-002",
                    "subject": "Gas turbine",
                    "subject_type": "Equipment",
                    "predicate": "USES_FUEL",
                    "object": "Natural gas",
                    "object_type": "Fuel",
                    "evidence": "Gas turbines can burn natural gas.",
                    "source_file": "manual.pdf",
                    "source_page": 8,
                    "confidence": 0.87,
                },
            ],
        },
    )

    summary = import_kg_file(triples_path, db_path, cypher_path)

    assert summary["node_count"] == 3
    assert summary["edge_count"] == 2
    assert summary["evidence_count"] == 2
    assert summary["relation_counts"] == {"HAS_COMPONENT": 1, "USES_FUEL": 1}
    assert db_path.exists()
    assert cypher_path.exists()

    with sqlite3.connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {"nodes", "edges", "evidence"}.issubset(table_names)

    store = GraphStore(db_path)
    neighbors = store.neighbors("Gas turbine")
    assert [neighbor["neighbor_name"] for neighbor in neighbors] == ["Compressor", "Natural gas"]

    fuel_edges = store.edges_by_relation("USES_FUEL")
    assert fuel_edges[0]["subject"] == "Gas turbine"
    assert fuel_edges[0]["object"] == "Natural gas"

    evidence_hits = store.search_evidence("compressor")
    assert evidence_hits[0]["triple_id"] == "T-001"
    assert evidence_hits[0]["source_page"] == "7"

    cypher_text = cypher_path.read_text(encoding="utf-8")
    assert "MERGE (s:Entity {name: \"Gas turbine\"})" in cypher_text
    assert "MERGE (s)-[r:HAS_COMPONENT {triple_id: \"T-001\"}]->(o)" in cypher_text


def test_import_graph_json_links_to_sqlite(tmp_path):
    graph_path = tmp_path / "graph.json"
    db_path = tmp_path / "graph_store.sqlite"

    write_json(
        graph_path,
        {
            "nodes": [
                {"id": "A", "label": "Alpha", "type": "Concept"},
                {"id": "B", "label": "Beta", "type": "Method"},
            ],
            "links": [
                {
                    "source": "A",
                    "target": "B",
                    "predicate": "IMPROVED_BY",
                    "triple_id": "G-001",
                    "evidence": "Alpha is improved by Beta.",
                    "confidence": 0.75,
                    "source_file": "graph.pdf",
                    "source_page": 3,
                }
            ],
        },
    )

    summary = import_kg_file(graph_path, db_path)

    assert summary["node_count"] == 2
    assert summary["edge_count"] == 1

    store = GraphStore(db_path)
    neighbors = store.neighbors("Alpha")
    assert neighbors[0]["neighbor_name"] == "Beta"
    assert neighbors[0]["predicate"] == "IMPROVED_BY"
