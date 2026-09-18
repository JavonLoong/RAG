from __future__ import annotations

import json
from pathlib import Path

from evaluation.prd_acceptance import (
    ACCEPTANCE_CANDIDATE_FILES,
    ACCEPTANCE_RESPONSIBILITY,
    evaluate_prd_acceptance,
    write_acceptance_package,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")


def test_missing_real_evidence_is_never_reported_as_passed(tmp_path: Path) -> None:
    result = evaluate_prd_acceptance(tmp_path)
    assert result["overall_status"] == "not_accepted"
    assert result["status_counts"] == {"passed": 0, "failed": 0, "not_evaluated": 12}
    assert all(item["status"] == "not_evaluated" for item in result["gates"].values())


def test_ocr_category_names_without_page_level_human_records_do_not_pass(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "ocr_coverage.json",
        {
            "total_pages": 2,
            "text_or_structure_pages": 1,
            "blocked_pages": 1,
            "spotcheck_categories": ["clear", "low_quality", "table", "dual_column", "image"],
        },
    )

    gate = evaluate_prd_acceptance(tmp_path)["gates"]["AC-M2-01"]

    assert gate["status"] == "failed"
    assert gate["metrics"]["page_coverage"] == 0.5
    assert gate["metrics"]["blocked_pages_validated"] == 0
    assert gate["metrics"]["categories"] == []


def test_ocr_evidence_reference_cannot_escape_acceptance_input_dir(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    _write_json(
        inputs / "ocr_coverage.json",
        {
            "total_pages": 1,
            "text_or_structure_pages": 0,
            "blocked_pages": 1,
            "blocked_page_records": [
                {
                    "source_file": "book-a.pdf",
                    "page_num": 1,
                    "failure_code": "OCR_EMPTY_AFTER_RETRIES",
                    "reason": "多策略 OCR 后仍为空。",
                    "attempt_count": 3,
                    "downstream_publish_blocked": True,
                    "evidence_refs": ["../outside.json"],
                }
            ],
        },
    )

    gate = evaluate_prd_acceptance(inputs)["gates"]["AC-M2-01"]

    assert gate["status"] == "failed"
    assert gate["metrics"]["blocked_pages_validated"] == 0
    assert gate["metrics"]["invalid_blocked_page_records"] == 1


def test_large_file_boolean_claims_without_identity_and_observation_evidence_fail(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "large_file.json",
        {
            "file_size_mb": 60,
            "asynchronous": True,
            "progress_visible": True,
            "browser_frozen": False,
            "request_timed_out": False,
        },
    )

    gate = evaluate_prd_acceptance(tmp_path)["gates"]["TECH-16"]

    assert gate["status"] == "failed"
    assert gate["metrics"]["identity_valid"] is False
    assert gate["metrics"]["review_valid"] is False


def test_fmea_export_claim_without_docx_round_trip_cannot_pass(tmp_path: Path) -> None:
    (tmp_path / "review.json").write_text("{}", encoding="utf-8")
    _write_json(
        tmp_path / "fmea_export_verification.json",
        {
            "row_count": 3,
            "json_rows": 3,
            "csv_rows": 3,
            "consistent": True,
            "lineage_consistent": True,
            "review": {
                "reviewer": "delivery-reviewer",
                "reviewed_at": "2026-09-02T00:00:00Z",
                "evidence_refs": ["review.json"],
            },
        },
    )

    gate = evaluate_prd_acceptance(tmp_path)["gates"]["AC-M5-02"]

    assert gate["status"] == "failed"
    assert gate["metrics"]["docx_verified"] is False
    assert gate["metrics"]["format_rows_match"] is False


def test_open_work_items_surface_unsigned_candidate_materials_without_passing_gates(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    candidates = inputs / "candidates"
    candidates.mkdir(parents=True)
    for filename in (
        "ocr_spotcheck_candidate.json",
        "performance_candidate.json",
        "large_file_candidate.json",
    ):
        _write_json(candidates / filename, {"_status": "pending_human_review"})

    result = write_acceptance_package(inputs, outputs)
    work_items = result["work_items"]
    by_id = {item["acceptance_id"]: item for item in work_items["items"]}

    assert result["overall_status"] == "not_accepted"
    assert work_items["candidate_file_count"] == 3
    assert by_id["AC-M2-01"]["candidate_status"] == "pending_human_review"
    assert by_id["TECH-15"]["candidate_files"] == ["candidates/performance_candidate.json"]
    assert by_id["TECH-16"]["candidate_files"] == ["candidates/large_file_candidate.json"]
    handoff = (outputs / "human_review_handoff.md").read_text(encoding="utf-8")
    assert "PowerRAG PRD 人工验收交接包" in handoff
    assert "AC-M2-01" in handoff
    assert "candidates/ocr_spotcheck_candidate.json" in handoff
    assert "OCR 审核人" in handoff


def test_every_acceptance_gate_has_a_declared_unsigned_candidate_path() -> None:
    assert set(ACCEPTANCE_CANDIDATE_FILES) == set(ACCEPTANCE_RESPONSIBILITY)
    assert all(ACCEPTANCE_CANDIDATE_FILES.values())


def test_complete_gold_and_signoff_inputs_generate_a_hashed_passing_package(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    outputs = tmp_path / "outputs"
    inputs.mkdir()
    (inputs / "blocked-evidence.json").write_text("{}", encoding="utf-8")
    (inputs / "spotcheck-evidence.png").write_bytes(b"png")
    (inputs / "review-evidence.json").write_text("{}", encoding="utf-8")
    _write_json(
        inputs / "ocr_coverage.json",
        {
            "total_pages": 100,
            "text_or_structure_pages": 98,
            "blocked_pages": 2,
            "blocked_page_records": [
                {
                    "source_file": "book-a.pdf",
                    "page_num": page_num,
                    "failure_code": "OCR_EMPTY_AFTER_RETRIES",
                    "reason": "多策略 OCR 后仍为空, 已阻止下游发布。",
                    "attempt_count": 3,
                    "downstream_publish_blocked": True,
                    "evidence_refs": ["blocked-evidence.json"],
                }
                for page_num in (99, 100)
            ],
            "spotchecks": [
                {
                    "category": category,
                    "source_file": "book-a.pdf",
                    "page_num": index,
                    "decision": "passed",
                    "reviewer": "ocr-reviewer-a",
                    "reviewed_at": "2026-09-02T00:00:00Z",
                    "evidence_ref": "spotcheck-evidence.png",
                }
                for index, category in enumerate(
                    ["clear", "low_quality", "table", "dual_column", "image"],
                    start=1,
                )
            ],
        },
    )
    _write_jsonl(
        inputs / "ocr_gold.jsonl",
        [
            {
                "id": "ocr-1",
                "category": "clear",
                "gold_text": "燃气轮机过滤器堵塞",
                "predicted_text": "燃气轮机过滤器堵塞",
                "critical_fields": [{"gold": "过滤器", "predicted": "过滤器"}],
                "reviewer": "ocr-reviewer-a",
                "reviewed_at": "2026-09-02T00:00:00Z",
                "evidence_ref": "review-evidence.json",
            }
        ],
    )
    case_types = ["no_answer", "cross_model", "source_conflict", "version_rollback"]
    retrieval_rows = [
        {
            "id": f"q-{index}",
            "case_type": case_types[index] if index < len(case_types) else "ordinary",
            "passed": True,
            "relevant_evidence_ids": [f"EV-{index}"],
            "retrieved_evidence_ids": [f"EV-{index}"],
            "citations": [{"evidence_id": f"EV-{index}", "resolvable": True}],
            "reviewer": "domain-reviewer-a",
            "reviewed_at": "2026-09-02T00:00:00Z",
            "evidence_ref": "review-evidence.json",
        }
        for index in range(10)
    ]
    _write_jsonl(inputs / "retrieval_gold.jsonl", retrieval_rows)
    relations = [
        {"subject": f"部件-{index}", "predicate": "PART_OF", "object": "燃气轮机"}
        for index in range(100)
    ]
    _write_json(
        inputs / "graph_gold.json",
        {
            "gold_relations": relations,
            "predicted_relations": relations,
            "published_statements": [
                {"statement_id": f"S-{index}", "evidence_bound": True, "blocking_violation_count": 0}
                for index in range(100)
            ],
            "same_question_comparison": [{"id": "q-1", "expert_judgement": "graphrag_better"}],
            "review": {
                "reviewer": "graph-reviewer-a",
                "reviewed_at": "2026-09-02T00:00:00Z",
                "evidence_refs": ["review-evidence.json"],
            },
        },
    )
    _write_jsonl(
        inputs / "fmea_expert.jsonl",
        [
            {
                "item_id": f"F-{index}",
                "fields": {"equipment": "燃气轮机", "failure_mode": "堵塞"},
                "field_evidence": {"equipment": ["EV-1"], "failure_mode": ["EV-2"]},
                "expert_decision": "accepted",
                "severity": None,
                "occurrence": None,
                "detection": None,
                "rpn": None,
                "reviewer": "fmea-expert-a",
                "reviewed_at": "2026-09-02T00:00:00Z",
                "evidence_ref": "review-evidence.json",
            }
            for index in range(5)
        ],
    )
    _write_json(
        inputs / "fmea_export_verification.json",
        {
            "consistent": True,
            "lineage_consistent": True,
            "row_count": 5,
            "json_rows": 5,
            "csv_rows": 5,
            "docx_rows": 5,
            "docx_verified": True,
            "review": {
                "reviewer": "delivery-reviewer-a",
                "reviewed_at": "2026-09-02T00:00:00Z",
                "evidence_refs": ["review-evidence.json"],
            },
        },
    )
    operations = dict.fromkeys(("create_project", "intake", "resolve_issue", "publish_document", "publish_graph", "publish_fmea", "export", "feedback", "index_rebuild", "graph_resync", "document_rollback", "project_restore"), True)
    _write_json(
        inputs / "e2e_signoff.json",
        {
            "knowledge_engineer": "engineer-a",
            "domain_reviewer": "expert-b",
            "ui_only": True,
            "operations": operations,
            "signed_at": "2026-09-02T00:00:00Z",
            "signatures": ["engineer-a", "expert-b"],
            "evidence_refs": ["review-evidence.json"],
        },
    )
    _write_json(
        inputs / "performance.json",
        {
            "windows_reference_device": "pilot-device-1",
            "pilot_document_count": 14,
            "embedding_model": "approved-embedding-v1",
            "retrieval_seconds": [0.4, 0.5, 0.6],
            "graph_path_seconds": [0.5, 0.7, 0.8],
            "preview_seconds": [0.8, 1.0, 1.2],
            "review": {
                "reviewer": "performance-reviewer-a",
                "reviewed_at": "2026-09-02T00:00:00Z",
                "evidence_refs": ["review-evidence.json"],
            },
        },
    )
    _write_json(
        inputs / "large_file.json",
        {
            "file_size_mb": 60,
            "asynchronous": True,
            "progress_visible": True,
            "browser_frozen": False,
            "request_timed_out": False,
            "task_id": "task-upload-60mb",
            "source_sha256": "a" * 64,
            "review": {
                "reviewer": "ui-observer-a",
                "reviewed_at": "2026-09-02T00:00:00Z",
                "evidence_refs": ["review-evidence.json"],
            },
        },
    )

    result = write_acceptance_package(inputs, outputs)
    assert result["overall_status"] == "passed"
    assert result["status_counts"] == {"passed": 12, "failed": 0, "not_evaluated": 0}
    assert (outputs / "acceptance.md").is_file()
    assert json.loads((outputs / "work_items.json").read_text(encoding="utf-8"))["open_item_count"] == 0
    assert "无待办" in (outputs / "human_review_handoff.md").read_text(encoding="utf-8")
    manifest = json.loads((outputs / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["overall_status"] == "passed"
    assert "human_review_handoff.md" in {item["path"] for item in manifest["outputs"]}
    assert all(len(item["sha256"]) == 64 for item in manifest["inputs"] + manifest["outputs"])
