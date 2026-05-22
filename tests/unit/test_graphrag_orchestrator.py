from __future__ import annotations

import sqlite3

import pytest

from rag_orchestrator.adapters import SQLiteGraphRetriever
from rag_orchestrator.graphrag_qa import GraphRagConfigurationError, GraphRagQAOrchestrator


class FakeTextRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, top_k: int) -> list[dict[str, object]]:
        self.calls.append((query, top_k))
        return [
            {
                "id": "chunk-1",
                "text": "Compressor washing lowers outlet temperature after fouling.",
                "source": "manual.pdf",
                "score": 0.91,
                "metadata": {"page": 12, "section": "compressor maintenance"},
            }
        ]


class FakeGraphRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, top_k: int) -> list[dict[str, object]]:
        self.calls.append((query, top_k))
        return [
            {
                "id": "rel-1",
                "subject": "compressor fouling",
                "predicate": "RESOLVED_BY",
                "object": "offline compressor wash",
                "evidence": "The fault graph links fouling to offline washing as a corrective action.",
                "source": "kg.sqlite",
                "confidence": 0.87,
            }
        ]


class FakeLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, **_: object) -> str:
        self.prompts.append(prompt)
        return "Use compressor washing evidence [T1] together with the graph relation [G1]."


class ExplodingLLM:
    def generate(self, prompt: str, **_: object) -> str:
        raise AssertionError(f"LLM should not be called in context-only mode: {prompt}")  # noqa: TRY003


def test_answer_builds_context_from_text_and_graph_and_preserves_citations() -> None:
    text_retriever = FakeTextRetriever()
    graph_retriever = FakeGraphRetriever()
    llm = FakeLLM()
    orchestrator = GraphRagQAOrchestrator(
        text_retriever=text_retriever,
        graph_retriever=graph_retriever,
        llm=llm,
    )

    result = orchestrator.answer("How should compressor fouling be handled?", top_k=2)

    assert text_retriever.calls == [("How should compressor fouling be handled?", 2)]
    assert graph_retriever.calls == [("How should compressor fouling be handled?", 2)]
    assert result.answer == "Use compressor washing evidence [T1] together with the graph relation [G1]."
    assert "## Text retrieval evidence" in result.context
    assert "[T1] manual.pdf" in result.context
    assert "Compressor washing lowers outlet temperature" in result.context
    assert "## Graph retrieval evidence" in result.context
    assert "[G1] compressor fouling --RESOLVED_BY--> offline compressor wash" in result.context
    assert "The fault graph links fouling" in result.context
    assert len(llm.prompts) == 1
    assert "How should compressor fouling be handled?" in llm.prompts[0]
    assert result.citations[0]["id"] == "T1"
    assert result.citations[0]["source_type"] == "text"
    assert result.citations[0]["metadata"] == {"page": 12, "section": "compressor maintenance"}
    assert result.citations[1]["id"] == "G1"
    assert result.citations[1]["source_type"] == "graph"
    assert result.evidence == result.citations


def test_context_only_returns_retrieval_context_without_calling_llm() -> None:
    orchestrator = GraphRagQAOrchestrator(
        text_retriever=FakeTextRetriever(),
        graph_retriever=FakeGraphRetriever(),
        llm=ExplodingLLM(),
    )

    result = orchestrator.answer("Show context only.", top_k=1, context_only=True)

    assert result.answer is None
    assert result.context_only is True
    assert "## Text retrieval evidence" in result.context
    assert "## Graph retrieval evidence" in result.context


def test_missing_llm_raises_clear_error_for_real_answer_generation() -> None:
    orchestrator = GraphRagQAOrchestrator(
        text_retriever=FakeTextRetriever(),
        graph_retriever=FakeGraphRetriever(),
        llm=None,
    )

    with pytest.raises(GraphRagConfigurationError, match="LLM.*required.*context_only"):
        orchestrator.answer("Generate an answer.", top_k=1)


def test_sqlite_graph_retriever_reads_local_graph_store_schema(tmp_path) -> None:
    sqlite_path = tmp_path / "graph_store.sqlite"
    with sqlite3.connect(sqlite_path) as connection:
        connection.executescript(
            """
            CREATE TABLE nodes (id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT);
            CREATE TABLE edges (
                id INTEGER PRIMARY KEY,
                triple_id TEXT NOT NULL,
                subject_node_id INTEGER NOT NULL,
                object_node_id INTEGER NOT NULL,
                predicate TEXT NOT NULL,
                confidence REAL,
                source_file TEXT,
                source_page TEXT,
                source_chunk_id TEXT
            );
            CREATE TABLE evidence (
                id INTEGER PRIMARY KEY,
                edge_id INTEGER NOT NULL,
                triple_id TEXT NOT NULL,
                text TEXT NOT NULL,
                source_file TEXT,
                source_page TEXT,
                source_chunk_id TEXT
            );
            INSERT INTO nodes (id, name, type) VALUES (1, '燃烧室', 'Component');
            INSERT INTO nodes (id, name, type) VALUES (2, '燃烧不稳定', 'Problem');
            INSERT INTO edges (
                id, triple_id, subject_node_id, object_node_id, predicate, confidence, source_file, source_page
            ) VALUES (1, 't1', 1, 2, 'HAS_PROBLEM', 0.9, 'book.pdf', '12');
            INSERT INTO evidence (edge_id, triple_id, text, source_file, source_page)
            VALUES (1, 't1', '燃烧室可能出现燃烧不稳定问题。', 'book.pdf', '12');
            """
        )

    hits = SQLiteGraphRetriever(sqlite_path).search("燃烧室 问题", top_k=1)

    assert hits[0]["subject"] == "燃烧室"
    assert hits[0]["predicate"] == "HAS_PROBLEM"
    assert hits[0]["object"] == "燃烧不稳定"
    assert "燃烧不稳定" in hits[0]["evidence"]
    assert hits[0]["source"] == "book.pdf"
