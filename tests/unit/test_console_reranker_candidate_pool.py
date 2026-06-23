from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POC_SRC = REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(POC_SRC) not in sys.path:
    sys.path.insert(0, str(POC_SRC))

from chroma_rag_poc.pipeline import (
    _ChromaCollectionRetriever,
    _TemplateQueryRewriter,
    _SEARCH_RERANKER_CACHE,
    _backfill_source_local_neighbors,
    _build_search_reranker,
    _candidate_pool_size,
    _default_search_reranker,
    _expand_source_local_neighbors,
    _rerank_candidate_pool_size,
)
from retrieval_engine import DocumentChunk, RetrievalResult


def test_cross_encoder_reranker_expands_candidate_pool() -> None:
    assert _rerank_candidate_pool_size(top_k=5, reranker="cross_encoder") == 50


def test_no_reranker_keeps_candidate_pool_at_top_k() -> None:
    assert _rerank_candidate_pool_size(top_k=5, reranker=None) == 5
    assert _rerank_candidate_pool_size(top_k=5, reranker="none") == 5


def test_default_retrieval_candidate_pool_is_wide_enough_for_sparse_long_tail() -> None:
    assert _candidate_pool_size(top_k=10) >= 150


def test_chroma_retriever_pushes_metadata_filter_into_query_where() -> None:
    class FakeCollection:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def query(self, **kwargs: object) -> dict[str, object]:
            self.calls.append(kwargs)
            return {
                "ids": [["target"]],
                "documents": [["target evidence"]],
                "metadatas": [[{"source_file": "target.txt", "chunk_id": "target"}]],
                "distances": [[0.1]],
            }

    collection = FakeCollection()
    retriever = _ChromaCollectionRetriever(collection)

    results = retriever.retrieve(
        "target",
        top_k=5,
        filters={"field": "meta.source_file", "operator": "==", "value": "target.txt"},
    )

    assert collection.calls[0]["where"] == {"source_file": "target.txt"}
    assert [result.chunk_id for result in results] == ["target"]


def test_source_local_neighbor_expansion_adds_adjacent_sentence_candidates() -> None:
    class FakeCollection:
        def get(self, **kwargs: object) -> dict[str, object]:
            return {
                "ids": ["0a", "0b", "1a"],
                "documents": [
                    "SENTENCE_ID: 0a\nAnchor sentence.",
                    "SENTENCE_ID: 0b\nBridge sentence.",
                    "SENTENCE_ID: 1a\nOther passage sentence.",
                ],
                "metadatas": [
                    {"source_file": "case.txt", "sentence_id": "0a", "chunk_id": "0a"},
                    {"source_file": "case.txt", "sentence_id": "0b", "chunk_id": "0b"},
                    {"source_file": "case.txt", "sentence_id": "1a", "chunk_id": "1a"},
                ],
            }

    anchor = RetrievalResult(
        chunk=DocumentChunk.from_text(
            "SENTENCE_ID: 0a\nAnchor sentence.",
            metadata={"source_file": "case.txt", "sentence_id": "0a", "chunk_id": "0a"},
        ),
        score=1.0,
    )

    expanded = _expand_source_local_neighbors(
        FakeCollection(),
        [anchor],
        source_file="case.txt",
        collection_count=3,
        top_k=3,
    )

    assert [result.metadata.get("sentence_id") for result in expanded[:2]] == ["0a", "0b"]


def test_source_local_neighbor_backfill_preserves_leading_hits() -> None:
    class FakeCollection:
        def get(self, **kwargs: object) -> dict[str, object]:
            return {
                "ids": ["0a", "0b", "1a"],
                "documents": [
                    "SENTENCE_ID: 0a\nAnchor sentence.",
                    "SENTENCE_ID: 0b\nBridge sentence.",
                    "SENTENCE_ID: 1a\nOther passage sentence.",
                ],
                "metadatas": [
                    {"source_file": "case.txt", "sentence_id": "0a", "chunk_id": "0a"},
                    {"source_file": "case.txt", "sentence_id": "0b", "chunk_id": "0b"},
                    {"source_file": "case.txt", "sentence_id": "1a", "chunk_id": "1a"},
                ],
            }

    base = [
        RetrievalResult(
            chunk=DocumentChunk.from_text(
                "SENTENCE_ID: 0a\nAnchor sentence.",
                metadata={"source_file": "case.txt", "sentence_id": "0a", "chunk_id": "0a"},
            ),
            score=1.0,
        ),
        RetrievalResult(
            chunk=DocumentChunk.from_text(
                "SENTENCE_ID: 1a\nOther passage sentence.",
                metadata={"source_file": "case.txt", "sentence_id": "1a", "chunk_id": "1a"},
            ),
            score=0.9,
        ),
    ]

    expanded = _backfill_source_local_neighbors(
        FakeCollection(),
        base,
        source_file="case.txt",
        collection_count=3,
        top_k=3,
        reserved_neighbor_slots=1,
    )

    assert [result.metadata.get("sentence_id") for result in expanded] == ["0a", "1a", "0b"]


def test_default_search_reranker_can_be_forced_by_env(monkeypatch) -> None:
    monkeypatch.setenv("RAG_DEFAULT_RERANKER", "cross_encoder")

    assert _default_search_reranker() == "cross_encoder"


def test_cross_encoder_search_reranker_is_cached(monkeypatch) -> None:
    created = 0

    class FakeCrossEncoderReranker:
        def __init__(self) -> None:
            nonlocal created
            created += 1

    monkeypatch.setattr("model_adapters.reranker.CrossEncoderReranker", FakeCrossEncoderReranker)
    _SEARCH_RERANKER_CACHE.clear()

    first = _build_search_reranker("cross_encoder")
    second = _build_search_reranker("cross_encoder")

    assert first is second
    assert created == 1
    _SEARCH_RERANKER_CACHE.clear()


def test_default_search_reranker_uses_downloaded_local_model(monkeypatch) -> None:
    monkeypatch.delenv("RAG_DEFAULT_RERANKER", raising=False)
    monkeypatch.delenv("RAG_ALLOW_ONLINE_MODELS", raising=False)
    monkeypatch.delenv("RAG_RERANKER_MODEL_PATH", raising=False)

    assert _default_search_reranker() == "cross_encoder"


def test_template_query_rewriter_expands_legal_scenario_questions() -> None:
    rewriter = _TemplateQueryRewriter()

    convulsion_rewrites = rewriter.rewrite(
        "Jonah suddenly suffers an unexpected convulsion while driving."
    )
    silence_rewrites = rewriter.rewrite(
        "Frank stays silent when asked about the car by someone who is not a government authority."
    )
    dna_rewrites = rewriter.rewrite(
        "Police took mitochondrial DNA and Y-STR samples from full siblings."
    )

    assert any("involuntary muscular movements" in item for item in convulsion_rewrites)
    assert any("right to silence" in item for item in silence_rewrites)
    assert any("dna evidence jury directions" in item for item in dna_rewrites)


def test_template_query_rewriter_expands_legal_long_tail_scenarios() -> None:
    rewriter = _TemplateQueryRewriter()

    alibi_rewrites = rewriter.rewrite(
        "Alex had dinner with friends across town at that exact time and the jury thinks there is a real chance it is true."
    )
    dna_rewrites = rewriter.rewrite(
        "Nuclear DNA, mitochondrial DNA and Y-STR testing link full siblings to a forensic sample."
    )
    silence_rewrites = rewriter.rewrite("Is the right to silence based solely on common law?")
    conspiracy_rewrites = rewriter.rewrite(
        "The other parties to a Commonwealth conspiracy have already been acquitted."
    )
    party_pill_rewrites = rewriter.rewrite(
        "They agreed to sell a harmless party pill that was in fact a controlled drug."
    )
    perseverance_rewrites = rewriter.rewrite(
        "Two jurors are uncertain of their verdict and the judge tells the jury to continue deliberating."
    )
    admission_rewrites = rewriter.rewrite("A text says I murdered my neighbour. What is required to use it as an admission?")
    identification_rewrites = rewriter.rewrite(
        "A shop assistant who served the accused every week identifies him from still images."
    )
    selective_silence_rewrites = rewriter.rewrite(
        "He gives his name and age but says no comment to other questions."
    )
    accused_presence_rewrites = rewriter.rewrite(
        "At a loud Christmas party he stays silent when asked whether that is his car."
    )

    assert any("directions about alibi evidence" in item for item in alibi_rewrites)
    assert any("possible contributor to the forensic sample" in item for item in dna_rewrites)
    assert any("no adverse inference may be drawn" in item for item in silence_rewrites)
    assert any("criminal code conspiracy acquitted inconsistent" in item for item in conspiracy_rewrites)
    assert any("accused mental state agreement" in item for item in party_pill_rewrites)
    assert any("perseverance" in item for item in perseverance_rewrites)
    assert any("using an admission" in item for item in admission_rewrites)
    assert any("identification evidence" in item for item in identification_rewrites)
    assert any("answered some questions" in item for item in selective_silence_rewrites)
    assert any("accused presence" in item for item in accused_presence_rewrites)
