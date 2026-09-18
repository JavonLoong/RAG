from __future__ import annotations

import json
from pathlib import Path

from evaluation import EvaluationThresholds, RAGEvaluationCase, RAGEvaluationHarness
from scripts.run_system_evaluation import evaluate_records


class FakeRagSystem:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def query(self, question: str) -> dict:
        self.questions.append(question)
        if "combined cycle" in question.lower():
            return {
                "answer": "Combined cycle improves efficiency through waste heat recovery.",
                "citations": [{"source": "manual.pdf", "text": "combined cycle waste heat recovery efficiency"}],
                "retrieval_results": [
                    {
                        "rank": 1,
                        "text": "combined cycle uses waste heat recovery to improve efficiency",
                        "source_file": "manual.pdf",
                    }
                ],
            }
        return {
            "answer": "The model gives a confident but unsupported answer.",
            "citations": [],
            "retrieval_results": [{"rank": 1, "text": "unrelated compressor maintenance note"}],
        }


class FakeCaseAwareRagSystem:
    def __init__(self) -> None:
        self.source_scopes: list[str] = []

    def query_case(self, case: dict) -> dict:
        self.source_scopes.append(str(case.get("source_scope") or ""))
        return {
            "answer": "scoped evidence",
            "citations": [],
            "retrieval_results": [{"text": "scoped evidence"}],
        }


def test_rag_evaluation_harness_runs_live_queries_and_applies_quality_gate() -> None:
    cases = [
        RAGEvaluationCase(
            id="q1",
            question="How does combined cycle improve efficiency?",
            reference_answer="Combined cycle uses waste heat recovery to improve efficiency.",
            expected_evidence_keywords=["combined cycle", "waste heat", "efficiency"],
            task_type="ordinary_rag",
            source_scope="manuals",
            grading_notes="Must retrieve the waste heat recovery evidence.",
        ),
        RAGEvaluationCase(
            id="q2",
            question="Which material limit is required?",
            reference_answer="The answer must cite the material limit evidence.",
            expected_evidence_keywords=["material limit", "temperature", "citation"],
            task_type="citation_quality",
            source_scope="manuals",
            grading_notes="Unsupported answers should be surfaced as failures.",
        ),
    ]

    harness = RAGEvaluationHarness(
        FakeRagSystem(),
        thresholds=EvaluationThresholds(
            min_keyword_recall_at_k=0.8,
            min_answer_completeness=0.8,
            max_missing_citation_rate=0.0,
            max_medium_or_high_risk_rate=0.0,
        ),
        top_k=3,
    )

    report = harness.run(cases, run_name="unit")

    assert report.gate_status == "fail"
    assert report.payload["summary"]["total_questions"] == 2
    assert report.payload["metrics"]["retrieval"]["keyword_recall_at_k"] == 0.5
    assert report.payload["metrics"]["citation"]["missing_citation_rate"] == 0.5
    assert {failure["id"] for failure in report.failure_cases} == {"q2"}
    assert any(failure["metric"] == "retrieval.keyword_recall_at_k" for failure in report.gate_failures)
    report_payload = report.to_dict()
    assert report_payload["evaluation_gate"]["status"] == "fail"
    policy = report_payload["retrieval_default_policy"]
    assert policy["recommended_defaults"]["hybrid_rrf"] is True
    assert policy["recommended_defaults"]["query_rewrite"] == "enable_by_default"
    assert policy["recommended_defaults"]["reranker"] == "cross_encoder"
    assert policy["recommended_defaults"]["no_answer_gate"] == "enable_with_calibrated_threshold"
    assert "retrieval.keyword_recall_at_k" in policy["triggered_by_metrics"]


def test_rag_evaluation_harness_prefers_case_aware_query_method() -> None:
    rag = FakeCaseAwareRagSystem()
    harness = RAGEvaluationHarness(rag, thresholds=EvaluationThresholds(min_keyword_recall_at_k=1.0))

    harness.run(
        [
            RAGEvaluationCase(
                id="scoped",
                question="Question with scoped corpus?",
                expected_evidence_keywords=["scoped evidence"],
                task_type="ragbench_hotpotqa",
                source_scope="ragbench-hotpotqa-validation-scoped.txt",
                grading_notes="RAGBench support sentence ids: 0a",
            )
        ]
    )

    assert rag.source_scopes == ["ragbench-hotpotqa-validation-scoped.txt"]


def test_rag_evaluation_harness_exports_machine_and_reader_reports(tmp_path: Path) -> None:
    harness = RAGEvaluationHarness(
        lambda question: {
            "answer": "Combined cycle uses waste heat recovery.",
            "citations": ["manual.pdf#p1"],
            "retrieval_results": [{"text": "combined cycle waste heat recovery"}],
        },
        thresholds=EvaluationThresholds(min_keyword_recall_at_k=1.0),
    )

    report = harness.run(
        [
            RAGEvaluationCase(
                id="q1",
                question="How does combined cycle work?",
                reference_answer="Combined cycle uses waste heat recovery.",
                expected_evidence_keywords=["combined cycle", "waste heat"],
                task_type="ordinary_rag",
                source_scope="manuals",
                grading_notes="Should cite the manual.",
            )
        ],
        run_name="unit",
    )
    paths = report.save(tmp_path)

    assert paths["json"].exists()
    assert paths["md"].exists()
    saved = json.loads(paths["json"].read_text(encoding="utf-8"))
    markdown = paths["md"].read_text(encoding="utf-8")
    assert saved["evaluation_gate"]["status"] == "pass"
    assert saved["retrieval_default_policy"]["recommended_defaults"]["query_rewrite"] == "keep_optional"
    assert "# RAG Evaluation Report" in markdown
    assert "Retrieval Default Policy" in markdown
    assert "keyword_recall_at_k" in markdown
    assert "q1" in markdown


def test_evaluation_reports_passage_id_recall_when_gold_passage_is_declared() -> None:
    payload = evaluate_records(
        [
            {
                "id": "legal-1",
                "question": "What direction is needed?",
                "expected_evidence_keywords": ["4.13.2-c4-s2", "Jury Directions"],
                "task_type": "legal_rag_qa",
                "source_scope": "legal",
                "grading_notes": "Relevant passage id: 4.13.2-c4-s2",
            }
        ],
        [
            {
                "id": "legal-1",
                "answer": "PASSAGE_ID: 4.13.2-c4-s2\nTITLE: Jury Directions",
                "retrieval_results": [
                    {
                        "text": "PASSAGE_ID: 4.13.2-c4-s2\nTITLE: Jury Directions",
                        "metadata": {"passage_id": "4.13.2-c4-s2"},
                    }
                ],
            }
        ],
        top_k=1,
        retrieval_only=True,
    )

    assert payload["metrics"]["retrieval"]["passage_id_recall_at_k"] == 1.0
    assert payload["results"][0]["expected_passage_id"] == "4.13.2-c4-s2"
    assert payload["results"][0]["retrieval_passage_id_hit"] is True


def test_evaluation_reports_gold_sentence_id_recall_for_ragbench_notes() -> None:
    payload = evaluate_records(
        [
            {
                "id": "ragbench-1",
                "question": "Which team appeared in both finals?",
                "expected_evidence_keywords": ["Barcelona", "2012", "2011"],
                "task_type": "ragbench_hotpotqa",
                "source_scope": "ragbench",
                "grading_notes": "RAGBench support sentence ids: 0a, 1a; support labels: relevance=1.0",
            }
        ],
        [
            {
                "id": "ragbench-1",
                "answer": "SENTENCE_ID: 0a\nBarcelona played the 2012 final.",
                "retrieval_results": [{"text": "SENTENCE_ID: 0a\nBarcelona played the 2012 final."}],
            }
        ],
        top_k=1,
        retrieval_only=True,
    )

    assert payload["metrics"]["retrieval"]["gold_id_recall_at_k"] == 0.5
    assert payload["metrics"]["retrieval"]["gold_id_expected_count"] == 2
    assert payload["metrics"]["retrieval"]["gold_id_hit_count"] == 1
    assert payload["results"][0]["expected_source_ids"] == ["0a", "1a"]
    assert payload["results"][0]["retrieval_source_id_hits"] == ["0a"]
