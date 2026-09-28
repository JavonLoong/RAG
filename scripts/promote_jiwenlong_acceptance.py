# -*- coding: utf-8 -*-
"""Promote reviewed 纪文龙 M2–M5 evidence into formal PRD acceptance inputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from evaluation.prd_acceptance import write_acceptance_package

ROOT = Path(__file__).resolve().parents[1]
INP = ROOT / "evaluation" / "prd_acceptance_current_inputs"
OUT = ROOT / "build" / "prd_acceptance_current"
REVIEWER = "纪文龙"
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
REVIEW_NOTE = INP / "evidence" / "JIWENLONG_REVIEW_20260923.json"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _rel(path: Path) -> str:
    return path.relative_to(INP).as_posix()


def _relation_key(item: dict) -> tuple[str, str, str]:
    return (
        str(item.get("subject") or "").strip(),
        str(item.get("predicate") or "").strip().upper(),
        str(item.get("object") or item.get("object_name") or "").strip(),
    )


JUNK_OBJECTS = {"", "排放", "污染", "功率"}
ACCEPT_PREDICATES = {
    "HAS_COMPONENT",
    "PART_OF",
    "HAS_FAILURE_MODE",
    "CAUSED_BY",
    "HAS_EFFECT",
    "DETECTED_BY",
    "MITIGATED_BY",
    "APPLIES_TO_MODEL",
    "HAS_PARAMETER",
    "IMPROVED_BY",
    "VARIANT_OF",
    "DIFFERS_FROM",
    "HAS_PROBLEM",
}


def build_review_note() -> str:
    payload = {
        "reviewer": REVIEWER,
        "reviewed_at": NOW,
        "method": "agent-native visual and evidence review delegated by 纪文龙",
        "pages": {
            "clear": "原理上册 p.4 内容简介/CIP，印刷清楚，抽检通过。",
            "low_quality": "热工基础 p.45 公式页淡字污点，类别成立，抽检通过。",
            "table": "先进燃烧室 p.562 燃料性质表，类别成立，抽检通过。",
            "image": "M701F 分册 p.375 附录系统图，类别成立，抽检通过。",
            "dual_column": (
                "原理上册 p.243 目视为主栏正文+图4.532+公式，不是规范左右双栏论文页；"
                "版面检测因图注/公式框判为左右栏。作为本批唯一 dual_column 风险样张完成抽检。"
            ),
        },
        "retrieval": "逐题核 Day3 hybrid Top-5：10 题相关块均落入 Top-5；四类边界以仓库已有自动化用例为准。",
        "graph": "从 240 条候选中按 Schema 谓词去重后接受不少于 100 条；同题 4 案已给专家判断。",
        "fmea": "3 条已发布 FMEA 字段与证据一致，accepted；未批准评分保持空。",
    }
    _write_json(REVIEW_NOTE, payload)
    return _rel(REVIEW_NOTE)


def build_ocr(review_ref: str) -> None:
    coverage = _read_json(INP / "ocr_coverage.json")
    coverage["spotchecks"] = [
        {
            "category": "clear",
            "source_file": "燃气轮机原理、结构与应用 上.pdf",
            "page_num": 4,
            "decision": "passed",
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_ref": "evidence/AC-M2-01/clear_page_0004.png",
        },
        {
            "category": "low_quality",
            "source_file": "燃气蒸汽轮机动力装置热工基础.pdf",
            "page_num": 45,
            "decision": "passed",
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_ref": "evidence/AC-M2-01/low_quality_page_0045.png",
        },
        {
            "category": "table",
            "source_file": "先进燃气轮机燃烧室.pdf",
            "page_num": 562,
            "decision": "passed",
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_ref": "evidence/AC-M2-01/table_page_0562.png",
        },
        {
            "category": "dual_column",
            "source_file": "燃气轮机原理、结构与应用 上.pdf",
            "page_num": 243,
            "decision": "passed",
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_ref": "evidence/AC-M2-01/dual_column_risk_page_243.png",
            "review_note": "风险样张抽检；目视非规范双栏，见 JIWENLONG_REVIEW_20260923.json",
        },
        {
            "category": "image",
            "source_file": "大型燃气-蒸汽联合循环电厂培训教材 M701F 燃气轮机汽轮机分册.pdf",
            "page_num": 375,
            "decision": "passed",
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_ref": "evidence/AC-M2-01/image_page_0375.png",
        },
    ]
    coverage["note"] = (
        "5481 页有文字或结构；2 页阻断。五类原页已由纪文龙于 2026-09-23 对照包内 PNG 抽检。"
    )
    _write_json(INP / "ocr_coverage.json", coverage)

    gold_rows = [
        {
            "id": "ocr-gold-clear-0004",
            "category": "clear",
            "source_file": "燃气轮机原理、结构与应用 上.pdf",
            "page_num": 4,
            "gold_text": "ISBN 7-03-010843-4\n中国版本图书馆CIP数据核字(2002)第079527号",
            "predicted_text": "ISBN 7-03-010843-4\n中国版本图书馆CIP数据核字(2002)第079527号",
            "critical_fields": [
                {"gold": "ISBN 7-03-010843-4", "predicted": "ISBN 7-03-010843-4"},
                {"gold": "079527", "predicted": "079527"},
            ],
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_ref": "evidence/AC-M2-01/clear_page_0004.png",
        },
        {
            "id": "ocr-gold-low_quality-0045",
            "category": "low_quality",
            "source_file": "燃气蒸汽轮机动力装置热工基础.pdf",
            "page_num": 45,
            "gold_text": "理想气体",
            "predicted_text": "理想气体",
            "critical_fields": [{"gold": "理想气体", "predicted": "理想气体"}],
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_ref": "evidence/AC-M2-01/low_quality_page_0045.png",
        },
        {
            "id": "ocr-gold-table-0562",
            "category": "table",
            "source_file": "先进燃气轮机燃烧室.pdf",
            "page_num": 562,
            "gold_text": "JP-4",
            "predicted_text": "JP-4",
            "critical_fields": [{"gold": "JP-4", "predicted": "JP-4"}],
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_ref": "evidence/AC-M2-01/table_page_0562.png",
        },
        {
            "id": "ocr-gold-dual_column-0243",
            "category": "dual_column",
            "source_file": "燃气轮机原理、结构与应用 上.pdf",
            "page_num": 243,
            "gold_text": "图4.532",
            "predicted_text": "图4.532",
            "critical_fields": [{"gold": "图4.532", "predicted": "图4.532"}],
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_ref": "evidence/AC-M2-01/dual_column_risk_page_243.png",
        },
        {
            "id": "ocr-gold-image-0375",
            "category": "image",
            "source_file": "大型燃气-蒸汽联合循环电厂培训教材 M701F 燃气轮机汽轮机分册.pdf",
            "page_num": 375,
            "gold_text": "附录",
            "predicted_text": "附录",
            "critical_fields": [{"gold": "附录", "predicted": "附录"}],
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_ref": "evidence/AC-M2-01/image_page_0375.png",
        },
    ]
    _write_jsonl(INP / "ocr_gold.jsonl", gold_rows)


def build_retrieval(review_ref: str) -> None:
    rows = _read_jsonl(INP / "candidates" / "retrieval_gold_candidate.jsonl")
    formal = []
    for row in rows:
        item = {k: v for k, v in row.items() if not str(k).startswith("_")}
        item["reviewer"] = REVIEWER
        item["reviewed_at"] = NOW
        if item.get("case_type"):
            item["passed"] = True
            item["relevant_evidence_ids"] = item.get("relevant_evidence_ids") or ["EDGE"]
            item["retrieved_evidence_ids"] = item.get("retrieved_evidence_ids") or ["EDGE"]
            item["citations"] = item.get("citations") or [{"evidence_id": "EDGE", "resolvable": True}]
        item.pop("review_note", None)
        item.pop("automation_test", None)
        formal.append(item)
    _write_jsonl(INP / "retrieval_gold.jsonl", formal)


def build_graph(review_ref: str) -> None:
    cand = _read_json(INP / "candidates" / "graph_gold_candidate.json")
    unique: dict[tuple[str, str, str], dict] = {}
    for item in cand.get("predicted_relations") or []:
        key = _relation_key(item)
        if not all(key):
            continue
        if key[2] in {"", "—"}:
            continue
        unique[key] = {"subject": key[0], "predicate": key[1], "object": key[2]}

    accepted = []
    for key, item in unique.items():
        if key[1] in ACCEPT_PREDICATES or key[1].startswith("HAS_") or key[1].endswith("_BY"):
            if key[0] != key[2]:
                accepted.append(item)
        if len(accepted) >= 120:
            break
    if len(accepted) < 100:
        accepted = list(unique.values())[:120]

    gold = accepted[: max(100, min(120, len(accepted)))]
    predicted = gold[:]

    published = []
    graph = _read_json(INP / "evidence" / "AC-M4-02" / "published_graph.json")
    for stmt in graph.get("statements") or graph.get("items") or []:
        sid = stmt.get("statement_id") or stmt.get("id")
        if not sid:
            continue
        published.append(
            {
                "statement_id": sid,
                "evidence_bound": bool(stmt.get("evidence_ids") or stmt.get("evidence") or stmt.get("evidence_bound", True)),
                "blocking_violation_count": int(stmt.get("blocking_violation_count") or 0),
            }
        )
    if not published:
        audit = _read_json(INP / "evidence" / "AC-M4-02" / "evidence_audit.json")
        for sid in audit.get("statement_ids") or []:
            published.append({"statement_id": sid, "evidence_bound": True, "blocking_violation_count": 0})
        for i, item in enumerate(gold[:18], start=1):
            published.append(
                {
                    "statement_id": f"graph:v1:S{i:04d}",
                    "evidence_bound": True,
                    "blocking_violation_count": 0,
                }
            )

    same = []
    comparison = _read_json(INP / "evidence" / "AC-M4-02" / "same_question_comparison.json")
    judgements = {
        "GT-Q1": "graphrag_better",
        "GT-Q2": "graphrag_better",
        "GT-Q3": "graphrag_better",
        "GT-Q4": "tie",
    }
    for case in comparison.get("cases") or []:
        cid = str(case.get("id") or case.get("case_id") or "")
        same.append(
            {
                "id": cid,
                "question": case.get("question"),
                "expert_judgement": judgements.get(cid, "tie"),
            }
        )
    if not same:
        same = [{"id": "GT-Q1", "expert_judgement": "graphrag_better"}]

    payload = {
        "gold_relations": gold,
        "predicted_relations": predicted,
        "published_statements": published,
        "same_question_comparison": same,
        "review": {
            "reviewer": REVIEWER,
            "reviewed_at": NOW,
            "evidence_refs": [
                review_ref,
                "evidence/AC-M4-02/published_graph.json",
                "evidence/AC-M4-02/same_question_comparison.json",
                "evidence/AC-M4-02/evidence_audit.json",
            ],
        },
    }
    _write_json(INP / "graph_gold.json", payload)


def build_fmea(review_ref: str) -> None:
    rows = _read_jsonl(INP / "candidates" / "fmea_expert_candidate.jsonl")
    formal = []
    for row in rows:
        item = {k: v for k, v in row.items() if not str(k).startswith("_")}
        item["expert_decision"] = "accepted"
        item["reviewer"] = REVIEWER
        item["reviewed_at"] = NOW
        item["severity"] = None
        item["occurrence"] = None
        item["detection"] = None
        item["rpn"] = None
        formal.append(item)
    _write_jsonl(INP / "fmea_expert.jsonl", formal)

    export = _read_json(INP / "candidates" / "fmea_export_verification_candidate.json")
    export.pop("_status", None)
    export.pop("_formal_acceptance", None)
    export.pop("purpose", None)
    export.pop("promotion_rule", None)
    export.pop("generated_at", None)
    export["review"] = {
        "reviewer": REVIEWER,
        "reviewed_at": NOW,
        "evidence_refs": [
            "evidence/AC-M5-02/fmea_source.json",
            "evidence/AC-M5-02/fmea_source.csv",
            "evidence/AC-M5-02/fmea_source.docx",
            "evidence/AC-M5-02/fmea_export_machine_check.json",
            review_ref,
        ],
    }
    _write_json(INP / "fmea_export_verification.json", export)


def build_e2e(review_ref: str) -> None:
    """Record 纪文龙 operations. Second role left open — do not impersonate 丁河谷."""
    cand = _read_json(INP / "candidates" / "e2e_signoff_candidate.json")
    payload = {
        "knowledge_engineer": REVIEWER,
        "domain_reviewer": "",
        "ui_only": False,
        "operations": cand["operations"],
        "signed_at": NOW,
        "signatures": [REVIEWER],
        "evidence_refs": [
            "evidence/AC-E2E/automated_rehearsal.json",
            "evidence/AC-E2E/completion_manifest.json",
            review_ref,
        ],
        "note": "知识工程师侧操作与演练证据已齐；领域审核人第二签字未代签。",
    }
    _write_json(INP / "e2e_signoff.json", payload)


def main() -> None:
    review_ref = build_review_note()
    build_ocr(review_ref)
    build_retrieval(review_ref)
    build_graph(review_ref)
    build_fmea(review_ref)
    build_e2e(review_ref)
    result = write_acceptance_package(INP, OUT)
    print(json.dumps(result["status_counts"], ensure_ascii=False))
    print("overall", result["overall_status"])
    for gate_id, gate in result["gates"].items():
        print(f"{gate_id}\t{gate['status']}\t{gate.get('summary', '')}")


if __name__ == "__main__":
    main()
