from __future__ import annotations

from typing import Any

from evaluation import RAGEvaluationCase
from scripts.run_full_external_benchmark_gemini_evaluation import GeneratedAnswerRag, run_cases_with_cache


class _FakeRetriever:
    def query(self, question: str) -> dict[str, Any]:
        return {
            "retrieval_results": [
                {
                    "text": "Basal cell carcinoma is a type of skin cancer.",
                    "metadata": {"source_file": "medical.txt"},
                }
            ],
            "citations": [{"source": "medical.txt", "text": "Basal cell carcinoma is a type of skin cancer."}],
        }


class _RecordingLLM:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def generate(self, prompt: str, **kwargs: Any) -> str:
        self.kwargs = kwargs
        return "Basal cell carcinoma. [1]"


def test_generated_answer_rag_passes_configured_generation_settings() -> None:
    llm = _RecordingLLM()
    rag = GeneratedAnswerRag(
        retriever=_FakeRetriever(),
        llm=llm,
        top_k=1,
        temperature=0.7,
        max_output_tokens=131072,
    )

    output = rag.query("What is a common skin cancer?")

    assert output["answer"] == "Basal cell carcinoma. [1]"
    assert llm.kwargs["temperature"] == 0.7
    assert llm.kwargs["max_tokens"] == 131072


class _CaseRag:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, question: str) -> dict[str, Any]:
        self.queries.append(question)
        return {
            "answer": f"answer for {question}",
            "retrieval_results": [{"text": question}],
            "citations": [{"source": "fake", "text": question}],
        }


def test_run_cases_with_cache_stops_after_max_new_cases(tmp_path) -> None:
    cases = [
        RAGEvaluationCase(id="c1", question="q1", expected_evidence_keywords=["q1"]),
        RAGEvaluationCase(id="c2", question="q2", expected_evidence_keywords=["q2"]),
        RAGEvaluationCase(id="c3", question="q3", expected_evidence_keywords=["q3"]),
    ]
    rag = _CaseRag()

    outputs, complete = run_cases_with_cache(
        cases,
        rag=rag,
        output_path=tmp_path / "outputs.jsonl",
        resume=False,
        continue_on_error=False,
        max_new_cases=2,
    )

    assert complete is False
    assert [output["id"] for output in outputs] == ["c1", "c2"]
    assert rag.queries == ["q1", "q2"]
