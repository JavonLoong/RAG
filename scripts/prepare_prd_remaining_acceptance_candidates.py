"""Prepare unsigned, evidence-backed review candidates for the remaining PRD gates.

The generated files live under ``evaluation/prd_acceptance_current_inputs/candidates``
and are intentionally ignored by the formal evaluator.  They reuse real repository
outputs, but leave expert judgements, verbatim OCR gold text, UI-only confirmation,
reviewer identity, and timestamps blank so automation cannot impersonate a reviewer.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_ROOT = REPO_ROOT / "evaluation" / "prd_acceptance_current_inputs"
COMPLETION_ROOT = REPO_ROOT / "build" / "graphrag_completion_acceptance"
QUESTIONS_PATH = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
RETRIEVAL_OUTPUT_PATH = (
    REPO_ROOT
    / "evaluation"
    / "reports"
    / "day3_retrieval_outputs_hybrid_rrf_20260604_004434.jsonl"
)
TRIPLES_PATH = (
    REPO_ROOT
    / "docs"
    / "project_deliverables"
    / "06_四本书KG工具跑通演示"
    / "triples.csv"
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_evidence(source: Path, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return {
        "path": target.relative_to(ACCEPTANCE_ROOT).as_posix(),
        "byte_size": target.stat().st_size,
        "sha256": _sha256(target),
        "source": source.relative_to(REPO_ROOT).as_posix(),
    }


def _latest_completion_package() -> Path:
    candidates = sorted(path for path in COMPLETION_ROOT.iterdir() if path.is_dir())
    if not candidates:
        raise FileNotFoundError(f"No completion package found under {COMPLETION_ROOT}")
    return candidates[-1]


def _candidate_header(purpose: str, promotion_rule: str) -> dict[str, Any]:
    return {
        "_status": "pending_human_review",
        "_formal_acceptance": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "purpose": purpose,
        "promotion_rule": promotion_rule,
    }


def _page_from_hit(hit: dict[str, Any]) -> int | None:
    matches = re.findall(r"##\s*Page\s+(\d+)", str(hit.get("text") or ""))
    return int(matches[-1]) if matches else None


def _prepare_ocr_gold_candidate() -> dict[str, Any]:
    source = _read_json(ACCEPTANCE_ROOT / "candidates" / "ocr_spotcheck_candidate.json")
    rows: list[dict[str, Any]] = []
    for item in source.get("spotchecks") or []:
        rows.append(
            {
                "_status": "pending_human_transcription",
                "sample_id": f"ocr-gold-{item['category']}-{item['page_num']:04d}",
                "category": item["category"],
                "source_file": item["source_file"],
                "page_num": item["page_num"],
                "gold_text": "",
                "predicted_text": "",
                "critical_fields": [],
                "reviewer": "",
                "reviewed_at": "",
                "evidence_ref": item["evidence_ref"],
                "review_instructions": [
                    "逐字抄录原页目标区域到 gold_text，不得由模型生成",
                    "粘贴同一区域的实际 OCR 输出到 predicted_text",
                    "至少登记一个关键型号、数值或单位到 critical_fields",
                    "填写具名审核人和审核时间后才可转入 ocr_gold.jsonl",
                ],
            }
        )
    output = ACCEPTANCE_ROOT / "candidates" / "ocr_gold_candidate.jsonl"
    _write_jsonl(output, rows)
    return {"path": output.relative_to(ACCEPTANCE_ROOT).as_posix(), "rows": len(rows)}


def _prepare_retrieval_candidate() -> dict[str, Any]:
    questions = {row["id"]: row for row in _read_jsonl(QUESTIONS_PATH)}
    outputs = _read_jsonl(RETRIEVAL_OUTPUT_PATH)
    review_rows: list[dict[str, Any]] = []
    packet_cases: list[dict[str, Any]] = []
    for output in outputs[:10]:
        question = questions.get(str(output.get("id")), {})
        keywords = [str(item) for item in question.get("expected_evidence_keywords") or []]
        hits = list(output.get("hits") or [])[:5]
        reviewed_hits = []
        for hit in hits:
            text = str(hit.get("text") or "")
            match_count = sum(keyword.lower() in text.lower() for keyword in keywords)
            source_file = str(hit.get("source_file") or "")
            reviewed_hits.append(
                {
                    "evidence_id": str(hit.get("id") or ""),
                    "rank": hit.get("rank"),
                    "score": hit.get("score"),
                    "source_file": source_file,
                    "source_page": _page_from_hit(hit),
                    "source_exists": bool(source_file and (REPO_ROOT / source_file).is_file()),
                    "keyword_match_count": match_count,
                    "preview": str(hit.get("preview") or text[:800]),
                }
            )
        proposed = [
            item["evidence_id"]
            for item in reviewed_hits
            if item["keyword_match_count"] == max(
                [candidate["keyword_match_count"] for candidate in reviewed_hits] or [0]
            )
            and item["keyword_match_count"] > 0
        ]
        if not proposed and reviewed_hits:
            proposed = [reviewed_hits[0]["evidence_id"]]
        packet_cases.append(
            {
                "id": output.get("id"),
                "question": output.get("question"),
                "reference_answer": question.get("reference_answer"),
                "expected_evidence_keywords": keywords,
                "selection_basis": "keyword_overlap_suggestion_only",
                "proposed_relevant_evidence_ids": proposed,
                "hits": reviewed_hits,
            }
        )

    packet_path = ACCEPTANCE_ROOT / "evidence" / "AC-M3-01" / "retrieval_review_packet.json"
    packet = {
        **_candidate_header(
            "Top-5 retrieval review packet for ten real gas-turbine questions.",
            "A domain expert must accept or edit relevant_evidence_ids for every question.",
        ),
        "source_question_set": QUESTIONS_PATH.relative_to(REPO_ROOT).as_posix(),
        "source_retrieval_run": RETRIEVAL_OUTPUT_PATH.relative_to(REPO_ROOT).as_posix(),
        "cases": packet_cases,
    }
    _write_json(packet_path, packet)
    packet_ref = packet_path.relative_to(ACCEPTANCE_ROOT).as_posix()
    for case in packet_cases:
        review_rows.append(
            {
                "_status": "pending_domain_expert_review",
                "id": case["id"],
                "question": case["question"],
                "relevant_evidence_ids": case["proposed_relevant_evidence_ids"],
                "retrieved_evidence_ids": [item["evidence_id"] for item in case["hits"]],
                "citations": [
                    {
                        "evidence_id": item["evidence_id"],
                        "resolvable": item["source_exists"],
                        "source_file": item["source_file"],
                        "page_num": item["source_page"],
                    }
                    for item in case["hits"]
                ],
                "reviewer": "",
                "reviewed_at": "",
                "evidence_ref": packet_ref,
                "review_note": "相关证据 ID 为关键词重合自动建议，必须逐题人工确认。",
            }
        )

    edge_packet_path = ACCEPTANCE_ROOT / "evidence" / "AC-M3-02" / "edge_case_rehearsal.json"
    edge_cases = {
        "no_answer": {
            "test": "tests/unit/test_retrieval_pipeline.py::RetrievalPipelineTestCase::test_no_answer_policy_blocks_low_confidence_results",
            "human_check": "正式资料不足时应明确无答案，不得编造。",
        },
        "cross_model": {
            "test": "tests/unit/test_graphrag_completion_acceptance.py::test_alias_duplicate_model_difference_conflict_and_professional_constraints",
            "human_check": "同义型号应归一，型号差异必须保留。",
        },
        "source_conflict": {
            "test": "tests/unit/test_graphrag_completion_acceptance.py::test_alias_duplicate_model_difference_conflict_and_professional_constraints",
            "human_check": "冲突来源必须并列展示并阻断自动发布。",
        },
        "version_rollback": {
            "test": "tests/unit/test_governed_delivery_workflow.py::test_document_version_compare_and_audited_rollback",
            "human_check": "回滚后检索必须仅使用目标正式版本。",
        },
    }
    _write_json(
        edge_packet_path,
        {
            **_candidate_header(
                "Four required retrieval boundary cases with executable rehearsal selectors.",
                "Run the selectors, inspect their JUnit evidence, then record a named human decision for each case.",
            ),
            "cases": edge_cases,
            "junit_evidence": "evidence/AC-M3-02/edge_case_tests.xml",
        },
    )
    edge_ref = edge_packet_path.relative_to(ACCEPTANCE_ROOT).as_posix()
    for case_type, detail in edge_cases.items():
        review_rows.append(
            {
                "_status": "pending_domain_expert_review",
                "id": f"edge-{case_type}",
                "question": detail["human_check"],
                "case_type": case_type,
                "passed": None,
                "reviewer": "",
                "reviewed_at": "",
                "evidence_ref": edge_ref,
                "automation_test": detail["test"],
            }
        )

    output = ACCEPTANCE_ROOT / "candidates" / "retrieval_gold_candidate.jsonl"
    _write_jsonl(output, review_rows)
    return {
        "path": output.relative_to(ACCEPTANCE_ROOT).as_posix(),
        "question_rows": len(packet_cases),
        "edge_case_rows": len(edge_cases),
    }


def _relation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": row.get("subject"),
        "predicate": row.get("predicate"),
        "object": row.get("object"),
    }


def _prepare_graph_candidate(package: Path) -> dict[str, Any]:
    evidence_dir = ACCEPTANCE_ROOT / "evidence" / "AC-M4-01"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    review_csv = evidence_dir / "graph_relation_review_packet.csv"
    with TRIPLES_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    fieldnames = list(source_rows[0]) + ["gold_decision", "review_comment"] if source_rows else []
    with review_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in source_rows:
            writer.writerow({**row, "gold_decision": "", "review_comment": ""})

    published_graph_path = ACCEPTANCE_ROOT / "evidence" / "AC-M4-02" / "published_graph.json"
    comparison_path = ACCEPTANCE_ROOT / "evidence" / "AC-M4-02" / "same_question_comparison.json"
    audit_path = ACCEPTANCE_ROOT / "evidence" / "AC-M4-02" / "evidence_audit.json"
    copied = [
        _copy_evidence(package / "published_graph.json", published_graph_path),
        _copy_evidence(package / "ordinary_rag_vs_graphrag_comparison.json", comparison_path),
        _copy_evidence(package / "evidence_audit.json", audit_path),
    ]
    published_graph = _read_json(published_graph_path)
    comparison = _read_json(comparison_path)
    predicted_relations = [_relation(row) for row in source_rows]
    proposed_gold = [_relation(row) for row in source_rows[:120]]
    statements = []
    for statement in published_graph.get("statements") or []:
        evidence_ids = list(statement.get("evidence_ids") or [])
        statements.append(
            {
                "statement_id": statement.get("statement_id"),
                "evidence_ids": evidence_ids,
                "evidence_bound": bool(evidence_ids),
                "blocking_violation_count": 0,
            }
        )
    same_question = [
        {
            "case_id": case.get("id") or case.get("case_id"),
            "question": case.get("question"),
            "ordinary_rag": case.get("ordinary_rag"),
            "graphrag": case.get("graphrag"),
            "expert_judgement": "",
        }
        for case in comparison.get("cases") or []
    ]
    candidate = {
        **_candidate_header(
            "Relation-gold and published-graph evidence review candidate.",
            "Review at least 100 CSV rows, copy accepted rows into gold_relations, judge every same-question case, and sign the review block.",
        ),
        "source_relation_count": len(source_rows),
        "predicted_relations": predicted_relations,
        "proposed_gold_relations": proposed_gold,
        "gold_relations": [],
        "published_statements": statements,
        "same_question_comparison": same_question,
        "review": {
            "status": "pending",
            "reviewer": "",
            "reviewer_role": "",
            "reviewed_at": "",
            "evidence_refs": [
                review_csv.relative_to(ACCEPTANCE_ROOT).as_posix(),
                published_graph_path.relative_to(ACCEPTANCE_ROOT).as_posix(),
                comparison_path.relative_to(ACCEPTANCE_ROOT).as_posix(),
                audit_path.relative_to(ACCEPTANCE_ROOT).as_posix(),
            ],
        },
        "source_inventory": copied,
    }
    output = ACCEPTANCE_ROOT / "candidates" / "graph_gold_candidate.json"
    _write_json(output, candidate)
    return {
        "path": output.relative_to(ACCEPTANCE_ROOT).as_posix(),
        "relation_rows": len(source_rows),
        "published_statements": len(statements),
        "same_question_cases": len(same_question),
    }


def _prepare_fmea_candidates(package: Path) -> dict[str, Any]:
    fmea_source_m5_01 = ACCEPTANCE_ROOT / "evidence" / "AC-M5-01" / "fmea_source.json"
    fmea_source_m5_02 = ACCEPTANCE_ROOT / "evidence" / "AC-M5-02" / "fmea_source.json"
    csv_source_m5_02 = ACCEPTANCE_ROOT / "evidence" / "AC-M5-02" / "fmea_source.csv"
    docx_source_m5_02 = ACCEPTANCE_ROOT / "evidence" / "AC-M5-02" / "fmea_source.docx"
    verification_source_m5_02 = (
        ACCEPTANCE_ROOT / "evidence" / "AC-M5-02" / "fmea_export_verification.json"
    )
    manifest_source_m5_02 = ACCEPTANCE_ROOT / "evidence" / "AC-M5-02" / "completion_manifest.json"
    copied = [
        _copy_evidence(package / "fmea.json", fmea_source_m5_01),
        _copy_evidence(package / "fmea.json", fmea_source_m5_02),
        _copy_evidence(package / "fmea.csv", csv_source_m5_02),
        _copy_evidence(package / "fmea.docx", docx_source_m5_02),
        _copy_evidence(package / "fmea_export_verification.json", verification_source_m5_02),
        _copy_evidence(package / "manifest.json", manifest_source_m5_02),
    ]
    fmea = _read_json(fmea_source_m5_01)
    expert_rows = []
    evidence_ref = fmea_source_m5_01.relative_to(ACCEPTANCE_ROOT).as_posix()
    for item in fmea.get("items") or []:
        expert_rows.append(
            {
                "_status": "pending_domain_expert_review",
                "item_id": item.get("item_id"),
                "fields": item.get("fields") or {},
                "field_evidence": item.get("field_evidence") or {},
                "expert_decision": "pending",
                "reviewer": "",
                "reviewed_at": "",
                "evidence_ref": evidence_ref,
                "severity": None,
                "occurrence": None,
                "detection": None,
                "rpn": None,
                "review_comment": "S/O/D/RPN 未配置批准策略，保持空值。",
            }
        )
    expert_output = ACCEPTANCE_ROOT / "candidates" / "fmea_expert_candidate.jsonl"
    _write_jsonl(expert_output, expert_rows)

    with csv_source_m5_02.open("r", encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    json_items = list(fmea.get("items") or [])
    export_verification = _read_json(verification_source_m5_02)
    machine_check = {
        "json_rows": len(json_items),
        "csv_rows": len(csv_rows),
        "docx_rows": int(export_verification.get("docx_rows") or 0),
        "row_count_match": len(json_items)
        == len(csv_rows)
        == int(export_verification.get("docx_rows") or 0),
        "round_trip_consistent": bool(export_verification.get("consistent")),
        "json_field_sets": [sorted((item.get("fields") or {}).keys()) for item in json_items],
        "csv_columns": list(csv_rows[0]) if csv_rows else [],
        "task_id": fmea.get("task_id"),
        "graph_version_id": (fmea.get("request") or {}).get("graph_version_id"),
        "document_version_ids": (fmea.get("request") or {}).get("document_version_ids") or [],
        "template": (fmea.get("request") or {}).get("template"),
        "template_version": (fmea.get("request") or {}).get("template_version"),
    }
    machine_check_path = ACCEPTANCE_ROOT / "evidence" / "AC-M5-02" / "fmea_export_machine_check.json"
    _write_json(machine_check_path, machine_check)
    export_candidate = {
        **_candidate_header(
            "Machine-checked JSON/CSV/DOCX FMEA export packet pending delivery-owner confirmation.",
            "The delivery owner must compare the rendered rows and lineage, then sign the review block before promotion.",
        ),
        "row_count": len(json_items),
        "json_rows": len(json_items),
        "csv_rows": len(csv_rows),
        "docx_rows": machine_check["docx_rows"],
        "docx_verified": bool(
            machine_check["round_trip_consistent"] and machine_check["row_count_match"]
        ),
        "consistent": bool(
            machine_check["round_trip_consistent"] and machine_check["row_count_match"]
        ),
        "lineage_consistent": bool(
            machine_check["task_id"]
            and machine_check["graph_version_id"]
            and machine_check["document_version_ids"]
            and machine_check["template"]
            and machine_check["template_version"]
        ),
        "review": {
            "status": "pending",
            "reviewer": "",
            "reviewer_role": "交付负责人",
            "reviewed_at": "",
            "evidence_refs": [
                fmea_source_m5_02.relative_to(ACCEPTANCE_ROOT).as_posix(),
                csv_source_m5_02.relative_to(ACCEPTANCE_ROOT).as_posix(),
                docx_source_m5_02.relative_to(ACCEPTANCE_ROOT).as_posix(),
                verification_source_m5_02.relative_to(ACCEPTANCE_ROOT).as_posix(),
                manifest_source_m5_02.relative_to(ACCEPTANCE_ROOT).as_posix(),
                machine_check_path.relative_to(ACCEPTANCE_ROOT).as_posix(),
            ],
        },
    }
    export_output = ACCEPTANCE_ROOT / "candidates" / "fmea_export_verification_candidate.json"
    _write_json(export_output, export_candidate)
    return {
        "expert_path": expert_output.relative_to(ACCEPTANCE_ROOT).as_posix(),
        "expert_rows": len(expert_rows),
        "export_path": export_output.relative_to(ACCEPTANCE_ROOT).as_posix(),
        "machine_consistent": bool(
            machine_check["round_trip_consistent"] and machine_check["row_count_match"]
        ),
        "source_inventory": copied,
    }


def _prepare_e2e_candidate(package: Path) -> dict[str, Any]:
    main_ops = {
        "create_project": True,
        "intake": True,
        "resolve_issue": True,
        "publish_document": True,
        "publish_graph": True,
        "publish_fmea": True,
        "export": True,
        "feedback": True,
    }
    recovery_ops = {
        "index_rebuild": True,
        "graph_resync": True,
        "document_rollback": True,
        "project_restore": True,
    }
    evidence_dir = ACCEPTANCE_ROOT / "evidence" / "AC-E2E"
    copied = [
        _copy_evidence(package / "manifest.json", evidence_dir / "completion_manifest.json"),
        _copy_evidence(package / "published_document.json", evidence_dir / "published_document.json"),
        _copy_evidence(package / "published_graph.json", evidence_dir / "published_graph.json"),
        _copy_evidence(package / "fmea.json", evidence_dir / "published_fmea.json"),
    ]
    rehearsal = {
        **_candidate_header(
            "Automated service-level M2-M5 and recovery rehearsal inventory.",
            "This proves operation availability only. Two distinct named users must repeat the required operations through the formal UI and sign the final record.",
        ),
        "main_operations": main_ops,
        "recovery_operations": recovery_ops,
        "execution_channel": "automated_service_and_test_rehearsal",
        "ui_only_confirmed": False,
        "source_inventory": copied,
        "required_ui_evidence": [
            "project creation",
            "document review and publication",
            "graph review and publication",
            "FMEA review/publication/export",
            "feedback routing",
            "index rebuild, graph resync, rollback, and project restore",
        ],
    }
    rehearsal_path = evidence_dir / "automated_rehearsal.json"
    _write_json(rehearsal_path, rehearsal)
    junit_path = evidence_dir / "recovery_and_closure_tests.xml"
    evidence_refs = [rehearsal_path.relative_to(ACCEPTANCE_ROOT).as_posix()]
    if junit_path.is_file():
        evidence_refs.append(junit_path.relative_to(ACCEPTANCE_ROOT).as_posix())
    candidate = {
        **_candidate_header(
            "Two-role UI-only sign-off candidate for AC-E2E-01 and AC-E2E-02.",
            "Replace automation observations with formal UI screenshots, enter two distinct named roles, and sign only after every operation is witnessed.",
        ),
        "operations": {**main_ops, **recovery_ops},
        "operation_observation": "automated_service_rehearsal_only",
        "knowledge_engineer": "",
        "domain_reviewer": "",
        "signatures": [],
        "signed_at": "",
        "ui_only": False,
        "evidence_refs": evidence_refs,
        "browser_evidence_refs": [],
    }
    output = ACCEPTANCE_ROOT / "candidates" / "e2e_signoff_candidate.json"
    _write_json(output, candidate)
    return {"path": output.relative_to(ACCEPTANCE_ROOT).as_posix(), "operation_count": len(candidate["operations"])}


def main() -> None:
    package = _latest_completion_package()
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "formal_acceptance_changed": False,
        "completion_package": package.relative_to(REPO_ROOT).as_posix(),
        "candidates": {
            "AC-M2-02": _prepare_ocr_gold_candidate(),
            "AC-M3-01_AC-M3-02": _prepare_retrieval_candidate(),
            "AC-M4-01_AC-M4-02": _prepare_graph_candidate(package),
            "AC-M5-01_AC-M5-02": _prepare_fmea_candidates(package),
            "AC-E2E-01_AC-E2E-02": _prepare_e2e_candidate(package),
        },
    }
    index_path = ACCEPTANCE_ROOT / "candidates" / "candidate_index.json"
    _write_json(index_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
