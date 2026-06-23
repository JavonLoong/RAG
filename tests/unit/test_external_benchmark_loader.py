from __future__ import annotations

import json
from pathlib import Path

from evaluation.external_benchmark_loader import (
    build_graphrag_bench_suite,
    build_legal_rag_bench_suite,
    build_ragbench_suite,
)


def test_build_legal_rag_bench_suite_maps_passages_and_answers(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    root.mkdir()
    (root / "corpus.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "p1",
                        "title": "Jury directions",
                        "text": "A judge may excuse a juror if impartiality is not possible.",
                    }
                ),
                json.dumps(
                    {
                        "id": "p2",
                        "title": "Sentencing",
                        "text": "This passage is unrelated.",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "qa.jsonl").write_text(
        json.dumps(
            {
                "id": 7,
                "question": "Must the judge excuse Bob?",
                "answer": "No. The court may excuse a juror if impartiality is not possible.",
                "relevant_passage_id": "p1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    suite = build_legal_rag_bench_suite(root, case_limit=1)

    assert suite.name == "legal-rag-bench"
    assert len(suite.payloads) == 1
    assert b"PASSAGE_ID: p1" in suite.payloads[0][1]
    assert len(suite.cases) == 1
    case = suite.cases[0]
    assert case.id == "legal-7"
    assert case.question == "Must the judge excuse Bob?"
    assert case.reference_answer.startswith("No.")
    assert "p1" in case.expected_evidence_keywords
    assert any("impartiality" in keyword.lower() for keyword in case.expected_evidence_keywords)


def test_legal_keyword_extraction_filters_section_number_noise(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    root.mkdir()
    (root / "corpus.jsonl").write_text(
        json.dumps(
            {
                "id": "1.2-c2-s2",
                "title": "1.2 Excusing Jurors",
                "text": "1. After providing the jury panel with this information, the court may excuse jurors.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "qa.jsonl").write_text(
        json.dumps(
            {
                "id": 1,
                "question": "Must the judge excuse Bob?",
                "answer": "The court may excuse jurors after providing information.",
                "relevant_passage_id": "1.2-c2-s2",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    suite = build_legal_rag_bench_suite(root, case_limit=1)
    keywords = suite.cases[0].expected_evidence_keywords

    assert "1.2-c2-s2" in keywords
    assert "Excusing Jurors" in keywords
    assert "providing" in keywords
    assert "1 2" not in keywords
    assert "Jurors 1" not in keywords
    assert "1 After" not in keywords


def test_legal_keyword_extraction_filters_multi_level_heading_numbers(tmp_path: Path) -> None:
    root = tmp_path / "legal"
    root.mkdir()
    (root / "corpus.jsonl").write_text(
        json.dumps(
            {
                "id": "4.13.2-c4-s2",
                "title": "4.13.2 Jury Directions",
                "text": "The jury's role is determining whether a person is a possible contributor to the forensic sample.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "qa.jsonl").write_text(
        json.dumps(
            {
                "id": 31,
                "question": "What DNA direction is needed?",
                "answer": "The judge should direct the jury about determining possible contributors.",
                "relevant_passage_id": "4.13.2-c4-s2",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    suite = build_legal_rag_bench_suite(root, case_limit=1)
    keywords = suite.cases[0].expected_evidence_keywords

    assert "Jury Directions" in keywords
    assert "13 Jury Directions" not in keywords
    assert "13 Jury" not in keywords


def test_build_graphrag_bench_suite_uses_evidence_keywords(tmp_path: Path) -> None:
    root = tmp_path / "graphrag"
    (root / "Datasets" / "Corpus").mkdir(parents=True)
    (root / "Datasets" / "Questions").mkdir(parents=True)
    (root / "Datasets" / "Corpus" / "medical.json").write_text(
        json.dumps(
            [
                {
                    "corpus_name": "Medical",
                    "context": "Basal cell carcinoma is the most common type of skin cancer.",
                }
            ]
        ),
        encoding="utf-8",
    )
    (root / "Datasets" / "Questions" / "medical_questions.json").write_text(
        json.dumps(
            [
                {
                    "id": "m1",
                    "source": "Medical",
                    "question": "What is the most common type of skin cancer?",
                    "answer": "Basal cell carcinoma.",
                    "question_type": "Fact Retrieval",
                    "evidence": ["Basal cell carcinoma is the most common type of skin cancer."],
                }
            ]
        ),
        encoding="utf-8",
    )

    suite = build_graphrag_bench_suite(root, domain="medical", case_limit=1)

    assert suite.name == "graphrag-bench-medical"
    assert len(suite.payloads) == 1
    assert suite.payloads[0][0] == "graphrag-bench-medical-Medical.txt"
    case = suite.cases[0]
    assert case.id == "graphrag-medical-m1"
    assert case.task_type == "Fact Retrieval"
    assert "Basal cell carcinoma" in case.expected_evidence_keywords
    assert "skin cancer" in case.expected_evidence_keywords


def test_build_ragbench_suite_maps_supporting_sentences(tmp_path: Path) -> None:
    root = tmp_path / "ragbench"
    hotpotqa = root / "hotpotqa"
    hotpotqa.mkdir(parents=True)
    row = {
        "id": "r1",
        "question": "Which team appeared in both finals?",
        "documents": ["Doc 0 text.", "Doc 1 text."],
        "response": "Barcelona appeared in both finals.",
        "documents_sentences": [
            [["0a", "Barcelona played the 2012 final."], ["0b", "Other text."]],
            [["1a", "Barcelona played the 2011 final."]],
        ],
        "all_relevant_sentence_keys": ["0a", "1a"],
        "relevance_score": 1.0,
        "utilization_score": 1.0,
        "completeness_score": 1.0,
    }
    (hotpotqa / "validation-00000-of-00001.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    suite = build_ragbench_suite(root, dataset="hotpotqa", split="validation", case_limit=1)

    assert suite.name == "ragbench-hotpotqa-validation"
    assert len(suite.payloads) == 1
    assert b"SENTENCE_ID: 0a" in suite.payloads[0][1]
    assert b"SENTENCE_ID: 1a" in suite.payloads[0][1]
    case = suite.cases[0]
    assert case.id == "ragbench-hotpotqa-validation-r1"
    assert case.source_scope == "ragbench-hotpotqa-validation-r1.txt"
    assert case.reference_answer == "Barcelona appeared in both finals."
    assert "Barcelona" in case.expected_evidence_keywords
    assert "2012 final" in case.expected_evidence_keywords
    assert "2011 final" in case.expected_evidence_keywords
    assert "support sentence ids: 0a, 1a" in case.grading_notes
