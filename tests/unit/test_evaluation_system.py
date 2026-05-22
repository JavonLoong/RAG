from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_system_evaluation import evaluate_records, write_reports


def test_evaluate_records_computes_system_metrics() -> None:
    dataset = [
        {
            "id": "se001",
            "question": "联合循环为什么效率高？",
            "expected_evidence_keywords": ["联合循环", "能量梯级利用", "60%"],
            "task_type": "ordinary_rag",
            "source_scope": "manuals",
            "grading_notes": "答案应说明能量梯级利用和接近60%的效率。",
        },
        {
            "id": "se002",
            "question": "OCR 表格识别有什么风险？",
            "expected_evidence_keywords": ["OCR", "表格", "误识别"],
            "task_type": "ocr_risk",
            "source_scope": "ocr_outputs",
            "grading_notes": "答案应指出表格单元格和数字可能误识别。",
        },
    ]
    outputs = [
        {
            "id": "se001",
            "answer": "联合循环通过能量梯级利用把热功转换效率提高到接近60%。",
            "citations": [{"source": "combined-cycle.pdf", "text": "联合循环 能量梯级利用 接近60%"}],
            "retrieval_results": [
                {"rank": 1, "text": "燃气-蒸汽联合循环进行能量梯级利用，效率接近60%。"}
            ],
        },
        {
            "id": "se002",
            "answer": "OCR 表格可能出现误识别，尤其是数字和单元格边界。",
            "retrieval_results": [
                {"rank": 1, "text": "OCR 输出中表格、页眉页脚和数字存在误识别风险。"}
            ],
        },
    ]

    payload = evaluate_records(dataset, outputs, top_k=3)

    assert payload["summary"]["total_questions"] == 2
    assert payload["metrics"]["retrieval"]["question_recall_at_k"] == 1.0
    assert payload["metrics"]["retrieval"]["keyword_recall_at_k"] == 1.0
    assert payload["metrics"]["answer"]["answer_contains_evidence_rate"] == 1.0
    assert payload["metrics"]["answer"]["answer_completeness_avg"] == 1.0
    assert payload["metrics"]["citation"]["missing_citation_rate"] == 0.5
    assert payload["results"][1]["missing_citation"] is True
    assert payload["results"][1]["hallucination_risk"] == "medium"


def test_evaluate_records_supports_retrieval_only_inputs() -> None:
    dataset = [
        {
            "id": "se003",
            "question": "图谱路径应如何命中实体关系？",
            "expected_evidence_keywords": ["实体", "关系", "路径"],
            "task_type": "kg_graph_rag",
            "source_scope": ["kg_triples", "graph_index"],
            "grading_notes": "检索结果应覆盖实体、关系和路径。",
        }
    ]
    outputs = [
        {
            "id": "se003",
            "hits": [
                {"rank": 1, "content": "GraphRAG 返回实体-关系路径作为证据。"},
                {"rank": 2, "content": "普通向量片段。"},
            ],
        }
    ]

    payload = evaluate_records(dataset, outputs, top_k=1, retrieval_only=True)

    assert payload["metrics"]["retrieval"]["question_recall_at_k"] == 1.0
    assert payload["metrics"]["retrieval"]["keyword_recall_at_k"] == 1.0
    assert payload["metrics"]["answer"]["evaluated_questions"] == 0
    assert payload["metrics"]["answer"]["answer_contains_evidence_rate"] is None
    assert payload["metrics"]["citation"]["missing_citation_rate"] is None
    assert payload["results"][0]["answer_evidence_keywords"] == []


def test_write_reports_creates_json_and_markdown(tmp_path: Path) -> None:
    payload = evaluate_records(
        [
            {
                "id": "se004",
                "question": "跨文档答案需要什么证据？",
                "expected_evidence_keywords": ["文档A", "文档B"],
                "task_type": "cross_document",
                "source_scope": "two manuals",
                "grading_notes": "答案应同时覆盖两个来源。",
            }
        ],
        [
            {
                "id": "se004",
                "answer": "需要同时引用文档A和文档B。",
                "citations": ["doc-a.pdf#p1", "doc-b.pdf#p2"],
                "retrieval_results": [
                    {"rank": 1, "text": "文档A说明材料限制。"},
                    {"rank": 2, "text": "文档B说明运行条件。"},
                ],
            }
        ],
        top_k=2,
    )

    paths = write_reports(
        payload,
        tmp_path,
        run_name="unit",
        generated_at=datetime(2026, 5, 21, 9, 30, 0),
    )

    assert paths["json"].name == "system_eval_unit_20260521_093000.json"
    assert paths["md"].name == "system_eval_unit_20260521_093000.md"
    report_json = json.loads(paths["json"].read_text(encoding="utf-8"))
    report_md = paths["md"].read_text(encoding="utf-8")
    assert report_json["summary"]["total_questions"] == 1
    assert "# System Evaluation Report" in report_md
    assert "question_recall_at_k" in report_md
    assert "跨文档答案需要什么证据？" in report_md
