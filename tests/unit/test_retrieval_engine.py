import builtins
import sys
import unittest
from pathlib import Path

from retrieval_engine import (
    ChromaDatabaseError,
    ChromaRetriever,
    ChromaUnavailableError,
    DocumentChunk,
    HybridRetriever,
    KeywordRetriever,
    RetrievalResult,
)

_MISSING_CHROMADB = "No module named 'chromadb'"


class RetrievalEngineModelTests(unittest.TestCase):
    def test_document_chunk_normalizes_source_page_and_chunk_id_from_metadata(self) -> None:
        chunk = DocumentChunk.from_text(
            "compressor blade inspection notes",
            metadata={
                "source_file": "manual.pdf",
                "page_num": "12",
                "chunk_index": 3,
                "custom": "kept",
            },
        )

        self.assertEqual(chunk.source, "manual.pdf")
        self.assertEqual(chunk.page, 12)
        self.assertEqual(chunk.chunk_id, "manual.pdf:12:3")
        self.assertEqual(chunk.metadata["custom"], "kept")

    def test_retrieval_result_exposes_chunk_fields(self) -> None:
        chunk = DocumentChunk.from_text("燃气轮机维护", metadata={"source": "a.md", "page": 2, "chunk_id": "a-2"})
        result = RetrievalResult(chunk=chunk, score=0.75, retriever_name="keyword")

        self.assertEqual(result.text, "燃气轮机维护")
        self.assertEqual(result.source, "a.md")
        self.assertEqual(result.page, 2)
        self.assertEqual(result.chunk_id, "a-2")


class KeywordRetrieverTests(unittest.TestCase):
    def test_keyword_retriever_ranks_matching_chunks_and_preserves_metadata(self) -> None:
        retriever = KeywordRetriever(
            [
                DocumentChunk.from_text(
                    "燃气轮机 compressor blade inspection and compressor wash",
                    metadata={"source_file": "manual.pdf", "page_num": 10, "chunk_index": 0},
                ),
                DocumentChunk.from_text(
                    "steam turbine condenser operation",
                    metadata={"source_file": "other.pdf", "page_num": 4, "chunk_index": 1},
                ),
            ]
        )

        results = retriever.retrieve("compressor inspection", top_k=2)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "manual.pdf")
        self.assertEqual(results[0].page, 10)
        self.assertEqual(results[0].chunk_id, "manual.pdf:10:0")
        self.assertGreater(results[0].score, 0)

    def test_keyword_retriever_returns_empty_for_blank_query(self) -> None:
        retriever = KeywordRetriever([DocumentChunk.from_text("any text")])

        self.assertEqual(retriever.retrieve("   "), [])

    def test_keyword_retriever_uses_passage_and_section_metadata_as_strong_signals(self) -> None:
        exact_passage = DocumentChunk.from_text(
            "The court may excuse a juror if impartiality is doubtful.",
            metadata={
                "source_file": "legal.txt",
                "passage_id": "1.2-c2-s2",
                "section_path": "1.2 > c2 > s2",
                "passage_title": "Juror impartiality",
                "chunk_id": "exact",
            },
        )
        generic = DocumentChunk.from_text(
            "A general paragraph about jurors and trials.",
            metadata={"source_file": "legal.txt", "passage_id": "9.9-c9-s9", "chunk_id": "generic"},
        )
        retriever = KeywordRetriever([generic, exact_passage])

        results = retriever.retrieve("1.2-c2-s2 juror", top_k=2)

        self.assertEqual([result.chunk_id for result in results], ["exact", "generic"])
        self.assertGreater(results[0].score, results[1].score)

    def test_keyword_retriever_applies_metadata_filters_before_ranking(self) -> None:
        retriever = KeywordRetriever(
            [
                DocumentChunk.from_text(
                    "pump maintenance markdown source",
                    metadata={"source_file": "pump.md", "chunk_id": "md"},
                ),
                DocumentChunk.from_text(
                    "pump maintenance text source",
                    metadata={"source_file": "pump.txt", "chunk_id": "txt"},
                ),
            ]
        )

        results = retriever.retrieve(
            "pump maintenance",
            top_k=5,
            filters={"field": "meta.source_file", "operator": "==", "value": "pump.md"},
        )

        self.assertEqual([result.chunk_id for result in results], ["md"])


class FakeRetriever:
    def __init__(self, name: str, results: list[RetrievalResult]) -> None:
        self.name = name
        self.calls: list[tuple[str, int]] = []
        self.results = results

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        self.calls.append((query, top_k))
        return self.results[:top_k]


class HybridRetrieverTests(unittest.TestCase):
    def test_hybrid_retriever_merges_results_and_combines_duplicate_scores(self) -> None:
        shared = DocumentChunk.from_text("shared compressor result", metadata={"source": "a.pdf", "page": 1, "chunk_id": "a-1"})
        unique = DocumentChunk.from_text("unique turbine result", metadata={"source": "b.pdf", "page": 5, "chunk_id": "b-5"})
        first = FakeRetriever("dense", [RetrievalResult(shared, 0.6, "dense")])
        second = FakeRetriever(
            "keyword",
            [
                RetrievalResult(shared, 0.4, "keyword"),
                RetrievalResult(unique, 0.9, "keyword"),
            ],
        )
        hybrid = HybridRetriever([first, second])

        results = hybrid.retrieve("compressor", top_k=5)

        self.assertEqual(first.calls, [("compressor", 5)])
        self.assertEqual(second.calls, [("compressor", 5)])
        self.assertEqual([result.chunk_id for result in results], ["a-1", "b-5"])
        self.assertAlmostEqual(results[0].score, 1.0)
        self.assertEqual(results[0].source, "a.pdf")
        self.assertEqual(results[0].page, 1)
        self.assertEqual(results[0].retriever_name, "hybrid")

    def test_hybrid_retriever_requires_explicit_retrievers(self) -> None:
        with self.assertRaises(ValueError):
            HybridRetriever([])


class ChromaRetrieverErrorTests(unittest.TestCase):
    def test_chroma_retriever_reports_missing_database_path(self) -> None:
        missing = Path("storage_layer/runtime/does_not_exist")

        with self.assertRaisesRegex(ChromaDatabaseError, "ChromaDB path does not exist"):
            ChromaRetriever(persist_path=missing, collection_name="missing")

    def test_chroma_retriever_reports_missing_chromadb_dependency(self) -> None:
        original_import = builtins.__import__
        sys.modules.pop("chromadb", None)

        def import_without_chromadb(name: str, *args: object, **kwargs: object) -> object:
            if name == "chromadb" or name.startswith("chromadb."):
                raise ModuleNotFoundError(_MISSING_CHROMADB)
            return original_import(name, *args, **kwargs)

        try:
            builtins.__import__ = import_without_chromadb
            with self.assertRaisesRegex(ChromaUnavailableError, "chromadb is required"):
                ChromaRetriever(persist_path=Path("."), collection_name="any")
        finally:
            builtins.__import__ = original_import


if __name__ == "__main__":
    unittest.main()
