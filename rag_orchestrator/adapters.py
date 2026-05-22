from __future__ import annotations

import os
import re
import shlex
import sqlite3
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .graphrag_qa import GraphRagConfigurationError

CHROMADB_MISSING_ERROR = "chromadb is required for --chroma-path retrieval. Install project dependencies first."
NO_CHROMA_COLLECTIONS_ERROR = "No Chroma collections were found at the given path."
NO_GRAPH_TABLE_ERROR = "No graph-like SQLite table found. Expected columns such as subject/predicate/object."
EMPTY_LLM_COMMAND_ERROR = "LLM command is empty."
EMPTY_LLM_ANSWER_ERROR = "LLM command returned an empty answer."
GRAPH_STORE_EDGE_JOIN = "__graph_store_edge_join__"


class ChromaTextRetriever:
    """Small Chroma adapter used by the demo CLI."""

    def __init__(
        self,
        chroma_path: str | Path,
        *,
        collection_name: str | None = None,
        embedding_function: Any | None = None,
    ) -> None:
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:
            raise GraphRagConfigurationError(CHROMADB_MISSING_ERROR) from exc

        path = Path(chroma_path)
        if path.name == "chroma.sqlite3":
            path = path.parent
        if not path.exists():
            raise FileNotFoundError(f"Chroma path does not exist: {path}")  # noqa: TRY003

        self.client = chromadb.PersistentClient(
            path=str(path),
            settings=Settings(anonymized_telemetry=False, is_persistent=True),
        )
        self.collection = self._get_collection(collection_name)
        self.embedding_function = embedding_function or _default_hashing_embedding(self.collection)

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        include = ["documents", "metadatas", "distances"]
        if self.embedding_function is not None:
            vector = _embed_query(self.embedding_function, query)
            result = self.collection.query(query_embeddings=[vector], n_results=top_k, include=include)
        else:
            result = self.collection.query(query_texts=[query], n_results=top_k, include=include)
        return _flatten_chroma_result(result)

    def _get_collection(self, collection_name: str | None) -> Any:
        if collection_name:
            return self.client.get_collection(collection_name)
        collections = self.client.list_collections()
        names = [getattr(collection, "name", str(collection)) for collection in collections]
        if not names:
            raise GraphRagConfigurationError(NO_CHROMA_COLLECTIONS_ERROR)
        if len(names) > 1:
            joined = ", ".join(names)
            message = f"Multiple Chroma collections found ({joined}); pass --collection explicitly."
            raise GraphRagConfigurationError(message)
        return self.client.get_collection(names[0])


class SQLiteGraphRetriever:
    """Generic graph retriever for SQLite tables containing triples or edges."""

    SUBJECT_COLUMNS = ("subject", "head", "source_node", "from_node", "src")
    PREDICATE_COLUMNS = ("predicate", "relation", "relationship", "edge_type", "label")
    OBJECT_COLUMNS = ("object", "tail", "target_node", "to_node", "dst", "target")
    EVIDENCE_COLUMNS = ("evidence", "evidence_text", "text", "description", "content", "chunk_text")
    SOURCE_COLUMNS = ("source_file", "evidence_doc", "document", "doc_id", "source_path")
    SCORE_COLUMNS = ("confidence", "score", "weight")
    ID_COLUMNS = ("id", "edge_id", "triple_id")

    def __init__(self, sqlite_path: str | Path, *, table_name: str | None = None, max_scan_rows: int = 5000) -> None:
        self.sqlite_path = Path(sqlite_path)
        if not self.sqlite_path.exists():
            message = f"Graph store SQLite path does not exist: {self.sqlite_path}"
            raise FileNotFoundError(message)
        self.table_name = table_name
        self.max_scan_rows = max_scan_rows

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        terms = _query_terms(query)
        with sqlite3.connect(self.sqlite_path) as connection:
            connection.row_factory = sqlite3.Row
            table_name, columns = self._resolve_table(connection)
            if table_name == GRAPH_STORE_EDGE_JOIN:
                rows = self._load_joined_graph_store_rows(connection)
            else:
                quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
                sql = (
                    f"SELECT {quoted_columns} FROM {_quote_identifier(table_name)} "  # noqa: S608
                    f"LIMIT {int(self.max_scan_rows)}"
                )
                rows = [dict(row) for row in connection.execute(sql)]

        ranked = []
        for row in rows:
            rank_score = _row_match_score(row, terms)
            if rank_score > 0:
                ranked.append((rank_score, _row_numeric_score(row, self.SCORE_COLUMNS), row))
        if not ranked:
            ranked = [(0, _row_numeric_score(row, self.SCORE_COLUMNS), row) for row in rows]
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [self._normalize_row(row) for _, _, row in ranked[:top_k]]

    def _resolve_table(self, connection: sqlite3.Connection) -> tuple[str, list[str]]:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        if self.table_name in {None, "edges"} and {"nodes", "edges"}.issubset(set(tables)):
            edge_columns = _table_columns(connection, "edges")
            if {"subject_node_id", "object_node_id", "predicate"}.issubset({column.lower() for column in edge_columns}):
                return GRAPH_STORE_EDGE_JOIN, []
        if self.table_name:
            if self.table_name not in tables:
                message = f"Graph table not found in SQLite store: {self.table_name}"
                raise GraphRagConfigurationError(message)
            columns = _table_columns(connection, self.table_name)
            return self.table_name, columns
        preferred = [table for table in ("triples", "relationships", "edges", "graph_edges", "facts") if table in tables]
        for table in [*preferred, *tables]:
            columns = _table_columns(connection, table)
            if _has_any(columns, self.SUBJECT_COLUMNS) and _has_any(columns, self.OBJECT_COLUMNS):
                return table, columns
        raise GraphRagConfigurationError(NO_GRAPH_TABLE_ERROR)

    def _load_joined_graph_store_rows(self, connection: sqlite3.Connection) -> list[dict[str, Any]]:
        sql = """
            SELECT
                e.id AS id,
                e.triple_id AS triple_id,
                s.name AS subject,
                e.predicate AS predicate,
                o.name AS object,
                ev.text AS evidence,
                COALESCE(ev.source_file, e.source_file) AS source_file,
                COALESCE(ev.source_page, e.source_page) AS source_page,
                COALESCE(ev.source_chunk_id, e.source_chunk_id) AS source_chunk_id,
                e.confidence AS confidence
            FROM edges e
            JOIN nodes s ON s.id = e.subject_node_id
            JOIN nodes o ON o.id = e.object_node_id
            LEFT JOIN evidence ev ON ev.edge_id = e.id
            LIMIT ?
        """
        return [dict(row) for row in connection.execute(sql, (int(self.max_scan_rows),))]

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _first_present(row, self.ID_COLUMNS),
            "subject": _first_present(row, self.SUBJECT_COLUMNS),
            "predicate": _first_present(row, self.PREDICATE_COLUMNS),
            "object": _first_present(row, self.OBJECT_COLUMNS),
            "evidence": _first_present(row, self.EVIDENCE_COLUMNS),
            "source": _first_present(row, self.SOURCE_COLUMNS),
            "confidence": _first_present(row, self.SCORE_COLUMNS),
            "metadata": {
                key: value
                for key, value in row.items()
                if key
                not in {
                    *self.ID_COLUMNS,
                    *self.SUBJECT_COLUMNS,
                    *self.PREDICATE_COLUMNS,
                    *self.OBJECT_COLUMNS,
                    *self.EVIDENCE_COLUMNS,
                    *self.SOURCE_COLUMNS,
                    *self.SCORE_COLUMNS,
                }
            },
        }


@dataclass(slots=True)
class CommandLLM:
    """LLM adapter that sends the prompt to a configured local command via stdin."""

    command: str | Sequence[str]
    timeout_seconds: int = 120

    def generate(self, prompt: str, **_: Any) -> str:
        if isinstance(self.command, str):
            command = shlex.split(self.command, posix=os.name != "nt")
        else:
            command = list(self.command)
        if not command:
            raise GraphRagConfigurationError(EMPTY_LLM_COMMAND_ERROR)
        completed = subprocess.run(  # noqa: S603 - the command is an explicit user-supplied LLM adapter.
            command,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            message = f"LLM command failed with exit code {completed.returncode}: {stderr}"
            raise RuntimeError(message)
        answer = completed.stdout.strip()
        if not answer:
            raise RuntimeError(EMPTY_LLM_ANSWER_ERROR)
        return answer


def _default_hashing_embedding(collection: Any) -> Any | None:
    try:
        from chroma_rag_poc.embeddings import HashingEmbeddingFunction
    except ImportError:
        return None
    metadata = getattr(collection, "metadata", None) or {}
    dimension = int(metadata.get("embedding_dimension") or metadata.get("dimension") or 384)
    return HashingEmbeddingFunction(dimension=dimension)


def _embed_query(embedding_function: Any, query: str) -> list[float]:
    embed_query = getattr(embedding_function, "embed_query", None)
    vector = embed_query(query) if callable(embed_query) else embedding_function([query])[0]
    if vector and isinstance(vector[0], list):
        return vector[0]
    return vector


def _flatten_chroma_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = _first_row(result.get("ids"))
    documents = _first_row(result.get("documents"))
    metadatas = _first_row(result.get("metadatas"))
    distances = _first_row(result.get("distances"))
    hits = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        hits.append(
            {
                "id": ids[index] if index < len(ids) else None,
                "text": document,
                "metadata": metadata,
                "source": metadata.get("source_file") or metadata.get("source"),
                "distance": distances[index] if index < len(distances) else None,
            }
        )
    return hits


def _first_row(value: Any) -> list[Any]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    if isinstance(value, list):
        return value
    return []


def _query_terms(query: str) -> list[str]:
    terms = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query) if len(term) >= 2]
    compact_query = query.strip().lower()
    if compact_query and compact_query not in terms and len(compact_query) <= 80:
        terms.append(compact_query)
    return terms or [compact_query]


def _row_match_score(row: dict[str, Any], terms: list[str]) -> int:
    haystack = " ".join(str(value).lower() for value in row.values() if value is not None)
    return sum(1 for term in terms if term and term in haystack)


def _row_numeric_score(row: dict[str, Any], names: Sequence[str]) -> float:
    value = _first_present(row, names)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    return [row[1] for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")]


def _has_any(columns: Sequence[str], candidates: Sequence[str]) -> bool:
    column_set = {column.lower() for column in columns}
    return any(candidate in column_set for candidate in candidates)


def _first_present(row: dict[str, Any], names: Sequence[str]) -> Any:
    lower_to_key = {key.lower(): key for key in row}
    for name in names:
        key = lower_to_key.get(name)
        if key is not None and row[key] is not None:
            return row[key]
    return None


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
