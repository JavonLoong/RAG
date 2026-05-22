from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CORE_TRIPLE_KEYS = {
    "id",
    "triple_id",
    "subject",
    "subject_type",
    "predicate",
    "relation",
    "object",
    "object_type",
    "target",
    "target_type",
    "evidence",
    "confidence",
    "source_file",
    "source_page",
    "source_pages",
    "source_chunk_id",
}


@dataclass(frozen=True)
class GraphEdgeRecord:
    triple_id: str
    subject: str
    predicate: str
    object_name: str
    subject_type: str | None = None
    object_type: str | None = None
    evidence: str | None = None
    confidence: float | None = None
    source_file: str | None = None
    source_page: str | None = None
    source_chunk_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class GraphStore:
    """Small SQLite-backed graph store for local KG experiments."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self, reset: bool = False) -> None:
        if reset and self.db_path.exists():
            self.db_path.unlink()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    triple_id TEXT NOT NULL UNIQUE,
                    subject_node_id INTEGER NOT NULL REFERENCES nodes(id),
                    object_node_id INTEGER NOT NULL REFERENCES nodes(id),
                    predicate TEXT NOT NULL,
                    confidence REAL,
                    source_file TEXT,
                    source_page TEXT,
                    source_chunk_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    edge_id INTEGER NOT NULL REFERENCES edges(id) ON DELETE CASCADE,
                    triple_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source_file TEXT,
                    source_page TEXT,
                    source_chunk_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
                CREATE INDEX IF NOT EXISTS idx_edges_predicate ON edges(predicate);
                CREATE INDEX IF NOT EXISTS idx_edges_subject ON edges(subject_node_id);
                CREATE INDEX IF NOT EXISTS idx_edges_object ON edges(object_node_id);
                CREATE INDEX IF NOT EXISTS idx_evidence_triple ON evidence(triple_id);
                CREATE INDEX IF NOT EXISTS idx_evidence_text ON evidence(text);
                """
            )

    def import_edges(self, edges: list[GraphEdgeRecord], reset: bool = True) -> dict[str, Any]:
        self.initialize(reset=reset)
        with self._connect() as connection:
            for edge in edges:
                subject_id = self._upsert_node(connection, edge.subject, edge.subject_type)
                object_id = self._upsert_node(connection, edge.object_name, edge.object_type)
                cursor = connection.execute(
                    """
                    INSERT INTO edges (
                        triple_id,
                        subject_node_id,
                        object_node_id,
                        predicate,
                        confidence,
                        source_file,
                        source_page,
                        source_chunk_id,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge.triple_id,
                        subject_id,
                        object_id,
                        edge.predicate,
                        edge.confidence,
                        edge.source_file,
                        edge.source_page,
                        edge.source_chunk_id,
                        _json_dumps(edge.metadata),
                    ),
                )
                if edge.evidence:
                    connection.execute(
                        """
                        INSERT INTO evidence (
                            edge_id,
                            triple_id,
                            text,
                            source_file,
                            source_page,
                            source_chunk_id,
                            metadata_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            cursor.lastrowid,
                            edge.triple_id,
                            edge.evidence,
                            edge.source_file,
                            edge.source_page,
                            edge.source_chunk_id,
                            _json_dumps(edge.metadata),
                        ),
                    )
            connection.commit()
        return self.summary()

    def neighbors(self, entity_name: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    e.triple_id,
                    s.name AS subject,
                    s.type AS subject_type,
                    o.name AS object,
                    o.type AS object_type,
                    e.predicate,
                    e.confidence,
                    e.source_file,
                    e.source_page,
                    e.source_chunk_id,
                    CASE WHEN s.name = ? THEN o.name ELSE s.name END AS neighbor_name,
                    CASE WHEN s.name = ? THEN o.type ELSE s.type END AS neighbor_type,
                    CASE WHEN s.name = ? THEN 'outgoing' ELSE 'incoming' END AS direction
                FROM edges e
                JOIN nodes s ON s.id = e.subject_node_id
                JOIN nodes o ON o.id = e.object_node_id
                WHERE s.name = ? OR o.name = ?
                ORDER BY e.predicate, neighbor_name, e.triple_id
                LIMIT ?
                """,
                (entity_name, entity_name, entity_name, entity_name, entity_name, limit),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def edges_by_relation(self, predicate: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    e.triple_id,
                    s.name AS subject,
                    s.type AS subject_type,
                    o.name AS object,
                    o.type AS object_type,
                    e.predicate,
                    e.confidence,
                    e.source_file,
                    e.source_page,
                    e.source_chunk_id
                FROM edges e
                JOIN nodes s ON s.id = e.subject_node_id
                JOIN nodes o ON o.id = e.object_node_id
                WHERE e.predicate = ?
                ORDER BY e.triple_id
                LIMIT ?
                """,
                (predicate, limit),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def search_evidence(self, keyword: str, limit: int = 50) -> list[dict[str, Any]]:
        pattern = f"%{keyword.lower()}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    ev.triple_id,
                    ev.text AS evidence,
                    ev.source_file,
                    ev.source_page,
                    ev.source_chunk_id,
                    s.name AS subject,
                    o.name AS object,
                    e.predicate,
                    e.confidence
                FROM evidence ev
                JOIN edges e ON e.id = ev.edge_id
                JOIN nodes s ON s.id = e.subject_node_id
                JOIN nodes o ON o.id = e.object_node_id
                WHERE lower(ev.text) LIKE ?
                ORDER BY ev.triple_id
                LIMIT ?
                """,
                (pattern, limit),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        with self._connect() as connection:
            node_count = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edge_count = connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            evidence_count = connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            relation_counts = {
                row["predicate"]: row["count"]
                for row in connection.execute(
                    "SELECT predicate, COUNT(*) AS count FROM edges GROUP BY predicate ORDER BY predicate"
                ).fetchall()
            }
            entity_type_counts = {
                row["type"]: row["count"]
                for row in connection.execute(
                    """
                    SELECT COALESCE(type, 'Unknown') AS type, COUNT(*) AS count
                    FROM nodes
                    GROUP BY COALESCE(type, 'Unknown')
                    ORDER BY type
                    """
                ).fetchall()
            }
        return {
            "sqlite_path": str(self.db_path),
            "node_count": node_count,
            "edge_count": edge_count,
            "evidence_count": evidence_count,
            "relation_counts": relation_counts,
            "entity_type_counts": entity_type_counts,
        }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _upsert_node(connection: sqlite3.Connection, name: str, entity_type: str | None) -> int:
        connection.execute(
            "INSERT OR IGNORE INTO nodes (name, type) VALUES (?, ?)",
            (name, entity_type),
        )
        if entity_type:
            connection.execute(
                "UPDATE nodes SET type = COALESCE(type, ?) WHERE name = ?",
                (entity_type, name),
            )
        row = connection.execute("SELECT id FROM nodes WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise ValueError(f"Failed to create graph node: {name}")
        return int(row["id"])


def import_kg_file(
    input_path: str | Path,
    sqlite_path: str | Path,
    cypher_path: str | Path | None = None,
) -> dict[str, Any]:
    source_path = Path(input_path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    edges = normalize_kg_payload(payload)

    store = GraphStore(sqlite_path)
    summary = store.import_edges(edges, reset=True)
    summary["source_input"] = str(source_path)

    if cypher_path is not None:
        write_neo4j_cypher(edges, cypher_path)
        summary["cypher_path"] = str(Path(cypher_path))
        summary["neo4j_status"] = "cypher_file_generated_not_executed"
    else:
        summary["cypher_path"] = None
        summary["neo4j_status"] = "not_requested"

    return summary


def normalize_kg_payload(payload: Any) -> list[GraphEdgeRecord]:
    if isinstance(payload, list):
        return _normalize_triples(payload)
    if not isinstance(payload, dict):
        raise ValueError("KG input must be a JSON object or list.")
    if isinstance(payload.get("triples"), list):
        return _normalize_triples(payload["triples"])
    if isinstance(payload.get("links"), list):
        return _normalize_graph_links(payload)
    raise ValueError("KG input must contain either 'triples' or 'links'.")


def write_neo4j_cypher(edges: list[GraphEdgeRecord], cypher_path: str | Path) -> None:
    target_path = Path(cypher_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "// Generated by storage_layer.graph_store.",
        "// This file is not proof that Neo4j is running; execute it with cypher-shell or Neo4j Browser when Neo4j is available.",
        "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (n:Entity) REQUIRE n.name IS UNIQUE;",
        "",
    ]

    for edge in edges:
        rel_type = _sanitize_relationship_type(edge.predicate)
        lines.extend(
            [
                f"MERGE (s:Entity {{name: {_cypher_value(edge.subject)}}})",
                f"MERGE (o:Entity {{name: {_cypher_value(edge.object_name)}}})",
            ]
        )
        if edge.subject_type:
            lines.append(f"SET s.type = coalesce(s.type, {_cypher_value(edge.subject_type)})")
        if edge.object_type:
            lines.append(f"SET o.type = coalesce(o.type, {_cypher_value(edge.object_type)})")

        rel_props = {
            "predicate": edge.predicate,
            "evidence": edge.evidence,
            "confidence": edge.confidence,
            "source_file": edge.source_file,
            "source_page": edge.source_page,
            "source_chunk_id": edge.source_chunk_id,
            "metadata_json": _json_dumps(edge.metadata) if edge.metadata else None,
        }
        lines.extend(
            [
                f"MERGE (s)-[r:{rel_type} {{triple_id: {_cypher_value(edge.triple_id)}}}]->(o)",
                f"SET r += {_cypher_map(rel_props)};",
                "",
            ]
        )

    target_path.write_text("\n".join(lines), encoding="utf-8")


def _normalize_triples(triples: list[dict[str, Any]]) -> list[GraphEdgeRecord]:
    edges: list[GraphEdgeRecord] = []
    for index, triple in enumerate(triples, start=1):
        subject = _required_text(triple, "subject")
        object_name = _coerce_text(triple.get("object") or triple.get("target"))
        predicate = _coerce_text(triple.get("predicate") or triple.get("relation"))
        if not object_name or not predicate:
            raise ValueError(f"Triple #{index} must include object/target and predicate/relation.")

        triple_id = _coerce_text(triple.get("id") or triple.get("triple_id")) or f"TRIPLE-{index:04d}"
        edges.append(
            GraphEdgeRecord(
                triple_id=triple_id,
                subject=subject,
                predicate=predicate,
                object_name=object_name,
                subject_type=_coerce_text(triple.get("subject_type")),
                object_type=_coerce_text(triple.get("object_type") or triple.get("target_type")),
                evidence=_coerce_text(triple.get("evidence")),
                confidence=_coerce_float(triple.get("confidence")),
                source_file=_coerce_text(triple.get("source_file")),
                source_page=_coerce_source_page(triple),
                source_chunk_id=_coerce_text(triple.get("source_chunk_id")),
                metadata=_metadata_without_core(triple),
            )
        )
    return edges


def _normalize_graph_links(payload: dict[str, Any]) -> list[GraphEdgeRecord]:
    nodes = payload.get("nodes") or []
    node_by_id = {_coerce_text(node.get("id")): node for node in nodes if _coerce_text(node.get("id"))}
    edges: list[GraphEdgeRecord] = []
    for index, link in enumerate(payload["links"], start=1):
        source_id = _required_text(link, "source")
        target_id = _required_text(link, "target")
        source_node = node_by_id.get(source_id, {})
        target_node = node_by_id.get(target_id, {})
        subject = _coerce_text(source_node.get("label") or source_node.get("name") or source_id)
        object_name = _coerce_text(target_node.get("label") or target_node.get("name") or target_id)
        predicate = _coerce_text(link.get("predicate") or link.get("relation") or link.get("type"))
        if not subject or not object_name or not predicate:
            raise ValueError(f"Graph link #{index} must include source, target, and predicate.")
        triple_id = _coerce_text(link.get("triple_id") or link.get("id")) or f"LINK-{index:04d}"
        edges.append(
            GraphEdgeRecord(
                triple_id=triple_id,
                subject=subject,
                predicate=predicate,
                object_name=object_name,
                subject_type=_coerce_text(link.get("subject_type") or source_node.get("type")),
                object_type=_coerce_text(link.get("object_type") or target_node.get("type")),
                evidence=_coerce_text(link.get("evidence")),
                confidence=_coerce_float(link.get("confidence")),
                source_file=_coerce_text(link.get("source_file")),
                source_page=_coerce_source_page(link),
                source_chunk_id=_coerce_text(link.get("source_chunk_id")),
                metadata=_metadata_without_core(link),
            )
        )
    return edges


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = _coerce_text(payload.get(key))
    if not value:
        raise ValueError(f"Missing required KG field: {key}")
    return value


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, int | float | bool):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_source_page(payload: dict[str, Any]) -> str | None:
    if "source_page" in payload:
        return _coerce_text(payload.get("source_page"))
    if "source_pages" in payload:
        return _coerce_text(payload.get("source_pages"))
    return None


def _metadata_without_core(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in CORE_TRIPLE_KEYS}


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _sanitize_relationship_type(predicate: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]", "_", predicate.upper())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        return "RELATED_TO"
    if normalized[0].isdigit():
        return f"REL_{normalized}"
    return normalized


def _cypher_map(payload: dict[str, Any]) -> str:
    parts = [f"{key}: {_cypher_value(value)}" for key, value in payload.items() if value not in (None, "")]
    return "{" + ", ".join(parts) + "}"


def _cypher_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return json.dumps(value)
    return json.dumps(str(value), ensure_ascii=False)


def relation_counts(edges: list[GraphEdgeRecord]) -> dict[str, int]:
    return dict(Counter(edge.predicate for edge in edges))
