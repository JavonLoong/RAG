"""Deterministic PRD acceptance gates for real PowerRAG delivery evidence.

Missing expert gold data is reported as ``not_evaluated``.  The evaluator never
turns smoke tests, demo fixtures, or mere record counts into a passing quality
claim.
"""
# ruff: noqa: RUF001

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.ocr_benchmark import levenshtein_distance, normalize_ocr_text

REQUIRED_OCR_CATEGORIES = {"clear", "low_quality", "table", "dual_column", "image"}
OCR_SPOTCHECK_PASS_DECISIONS = {"accepted", "passed"}
EXPERT_DECISIONS = {"accepted", "minor", "major", "rejected"}
ACCEPTANCE_RESPONSIBILITY = {
    "AC-M2-01": {
        "owner_roles": ["知识工程师", "OCR 审核人"],
        "input_files": ["ocr_coverage.json", "OCR 原页/阻断证据"],
    },
    "AC-M2-02": {
        "owner_roles": ["OCR 审核人"],
        "input_files": ["ocr_gold.jsonl", "逐字金标准原页证据"],
    },
    "AC-M3-01": {
        "owner_roles": ["领域专家", "知识工程师"],
        "input_files": ["retrieval_gold.jsonl", "问题与证据块审核记录"],
    },
    "AC-M3-02": {
        "owner_roles": ["领域专家", "知识工程师"],
        "input_files": ["retrieval_gold.jsonl", "四类边界用例证据"],
    },
    "AC-M4-01": {
        "owner_roles": ["图谱工程师", "领域专家"],
        "input_files": ["graph_gold.json", "不少于 100 条关系审核证据"],
    },
    "AC-M4-02": {
        "owner_roles": ["图谱工程师", "领域专家"],
        "input_files": ["graph_gold.json", "发布图审计与同题集证据"],
    },
    "AC-M5-01": {
        "owner_roles": ["领域专家"],
        "input_files": ["fmea_expert.jsonl", "逐项 FMEA 审核证据"],
    },
    "AC-M5-02": {
        "owner_roles": ["交付负责人"],
        "input_files": ["fmea_export_verification.json", "JSON/CSV/DOCX 对照证据"],
    },
    "AC-E2E-01": {
        "owner_roles": ["知识工程师", "领域审核人"],
        "input_files": ["e2e_signoff.json", "正式界面主闭环操作证据"],
    },
    "AC-E2E-02": {
        "owner_roles": ["知识工程师", "领域审核人"],
        "input_files": ["e2e_signoff.json", "恢复闭环操作证据"],
    },
    "TECH-15": {
        "owner_roles": ["测试负责人"],
        "input_files": ["performance.json", "参考设备原始耗时记录"],
    },
    "TECH-16": {
        "owner_roles": ["测试负责人", "界面观察人"],
        "input_files": ["large_file.json", "60 MB 实传任务与界面观察证据"],
    },
}
ACCEPTANCE_CANDIDATE_FILES = {
    "AC-M2-01": ["candidates/ocr_spotcheck_candidate.json"],
    "AC-M2-02": ["candidates/ocr_gold_candidate.jsonl"],
    "AC-M3-01": ["candidates/retrieval_gold_candidate.jsonl"],
    "AC-M3-02": ["candidates/retrieval_gold_candidate.jsonl"],
    "AC-M4-01": ["candidates/graph_gold_candidate.json"],
    "AC-M4-02": ["candidates/graph_gold_candidate.json"],
    "AC-M5-01": ["candidates/fmea_expert_candidate.jsonl"],
    "AC-M5-02": ["candidates/fmea_export_verification_candidate.json"],
    "AC-E2E-01": ["candidates/e2e_signoff_candidate.json"],
    "AC-E2E-02": ["candidates/e2e_signoff_candidate.json"],
    "TECH-15": ["candidates/performance_candidate.json"],
    "TECH-16": ["candidates/large_file_candidate.json"],
}


def evaluate_prd_acceptance(input_dir: str | Path) -> dict[str, Any]:
    root = Path(input_dir)
    gates = {
        "AC-M2-01": _evaluate_ocr_coverage(
            _read_json(root / "ocr_coverage.json"),
            evidence_root=root,
        ),
        "AC-M2-02": _evaluate_ocr_gold(
            _read_jsonl(root / "ocr_gold.jsonl"),
            evidence_root=root,
        ),
        "AC-M3-01": _evaluate_retrieval_gold(
            _read_jsonl(root / "retrieval_gold.jsonl"),
            evidence_root=root,
        ),
        "AC-M3-02": _evaluate_retrieval_edge_cases(
            _read_jsonl(root / "retrieval_gold.jsonl"),
            evidence_root=root,
        ),
        "AC-M4-01": _evaluate_graph_gold(
            _read_json(root / "graph_gold.json"),
            evidence_root=root,
        ),
        "AC-M4-02": _evaluate_graph_evidence(
            _read_json(root / "graph_gold.json"),
            evidence_root=root,
        ),
        "AC-M5-01": _evaluate_fmea_expert(
            _read_jsonl(root / "fmea_expert.jsonl"),
            evidence_root=root,
        ),
        "AC-M5-02": _evaluate_fmea_exports(
            _read_json(root / "fmea_export_verification.json"),
            evidence_root=root,
        ),
        "AC-E2E-01": _evaluate_e2e(
            _read_json(root / "e2e_signoff.json"),
            recovery=False,
            evidence_root=root,
        ),
        "AC-E2E-02": _evaluate_e2e(
            _read_json(root / "e2e_signoff.json"),
            recovery=True,
            evidence_root=root,
        ),
        "TECH-15": _evaluate_performance(
            _read_json(root / "performance.json"),
            evidence_root=root,
        ),
        "TECH-16": _evaluate_large_file(
            _read_json(root / "large_file.json"),
            evidence_root=root,
        ),
    }
    status_counts = {
        status: sum(item["status"] == status for item in gates.values())
        for status in ("passed", "failed", "not_evaluated")
    }
    return {
        "format": "powerrag-prd-acceptance-v1",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "input_dir": str(root.resolve()),
        "overall_status": "passed" if status_counts["passed"] == len(gates) else "not_accepted",
        "status_counts": status_counts,
        "gates": gates,
    }


def write_acceptance_package(input_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    input_root = Path(input_dir)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    result = evaluate_prd_acceptance(input_root)
    json_path = output_root / "acceptance.json"
    markdown_path = output_root / "acceptance.md"
    work_items_path = output_root / "work_items.json"
    handoff_path = output_root / "human_review_handoff.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_acceptance_markdown(result), encoding="utf-8")
    work_items = build_acceptance_work_items(result, input_dir=input_root)
    work_items_path.write_text(
        json.dumps(work_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    handoff_path.write_text(render_human_review_handoff(work_items), encoding="utf-8")
    input_files = [
        _file_record(path, input_root)
        for path in sorted(input_root.rglob("*"))
        if path.is_file()
    ]
    output_files = [
        _file_record(path, output_root)
        for path in (json_path, markdown_path, work_items_path, handoff_path)
    ]
    manifest = {
        "format": "powerrag-prd-acceptance-package-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "overall_status": result["overall_status"],
        "inputs": input_files,
        "outputs": output_files,
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        **result,
        "package_dir": str(output_root.resolve()),
        "manifest": manifest,
        "work_items": work_items,
    }


def build_acceptance_work_items(
    result: dict[str, Any],
    *,
    input_dir: str | Path | None = None,
) -> dict[str, Any]:
    input_root = Path(input_dir) if input_dir is not None else None
    items = []
    candidate_file_count = 0
    for gate_id, gate in result.get("gates", {}).items():
        if gate.get("status") == "passed":
            continue
        responsibility = ACCEPTANCE_RESPONSIBILITY[gate_id]
        candidate_files = []
        if input_root is not None:
            candidate_files = [
                relative
                for relative in ACCEPTANCE_CANDIDATE_FILES.get(gate_id, [])
                if (input_root / relative).is_file()
            ]
        candidate_file_count += len(candidate_files)
        item = {
            "acceptance_id": gate_id,
            "status": gate.get("status"),
            "owner_roles": responsibility["owner_roles"],
            "input_files": responsibility["input_files"],
            "required_action": gate.get("message"),
            "current_metrics": gate.get("metrics") or {},
        }
        if candidate_files:
            item["candidate_status"] = "pending_human_review"
            item["candidate_files"] = candidate_files
        items.append(item)
    return {
        "format": "powerrag-prd-acceptance-work-items-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_status": result.get("overall_status"),
        "open_item_count": len(items),
        "candidate_file_count": candidate_file_count,
        "items": items,
    }


def render_acceptance_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# PowerRAG PRD 正式验收报告",
        "",
        f"- 总体结论：**{result['overall_status']}**",
        f"- 通过：{result['status_counts']['passed']}",
        f"- 未通过：{result['status_counts']['failed']}",
        f"- 未评测：{result['status_counts']['not_evaluated']}",
        "",
        "> 未提供真实金标准或专家签字的数据一律记为“未评测”，不会用自动化测试或样例记录替代。",
        "",
        "| 验收项 | 状态 | 样本/规模 | 指标 | 结论 |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for gate_id, gate in result["gates"].items():
        lines.append(
            f"| {gate_id} | {gate['status']} | {gate.get('sample_count', 0)} | "
            f"{_markdown_cell(gate.get('metrics', {}))} | {_markdown_cell(gate.get('message', ''))} |"
        )
    lines.extend(["", "## 待补证据", ""])
    pending = [f"- {gate_id}：{gate['message']}" for gate_id, gate in result["gates"].items() if gate["status"] != "passed"]
    lines.extend(pending or ["- 无。全部验收门禁均有真实证据并通过。"])
    return "\n".join(lines) + "\n"


def render_human_review_handoff(work_items: dict[str, Any]) -> str:
    """Render one role-routed handoff packet without fabricating human decisions."""
    items = list(work_items.get("items") or [])
    role_items: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for role in item.get("owner_roles") or []:
            role_items.setdefault(str(role), []).append(item)

    lines = [
        "# PowerRAG PRD 人工验收交接包",
        "",
        f"- 正式验收状态：**{work_items.get('overall_status', 'unknown')}**",
        f"- 待处理门槛：{len(items)}",
        f"- 已挂载候选文件：{work_items.get('candidate_file_count', 0)}",
        "",
        "> 本文件只负责分派与复核导航。候选数据未经具名角色确认，不会自动写入正式证据，也不会自动通过门禁。",
        "",
        "## 角色分工",
        "",
        "| 责任角色 | 待复核门槛 | 数量 |",
        "| --- | --- | ---: |",
    ]
    for role, assigned in sorted(role_items.items()):
        gate_ids = "、".join(str(item.get("acceptance_id", "")) for item in assigned)
        lines.append(f"| {_markdown_cell(role)} | {_markdown_cell(gate_ids)} | {len(assigned)} |")
    if not role_items:
        lines.append("| 无 | 无开放门槛 | 0 |")

    lines.extend(
        [
            "",
            "## 门槛复核清单",
            "",
            "| 完成 | 门槛 | 当前状态 | 责任角色 | 正式输入 | 候选文件 | 必须完成的复核 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in items:
        roles = "、".join(str(value) for value in item.get("owner_roles") or [])
        formal_inputs = "、".join(str(value) for value in item.get("input_files") or [])
        candidates = "、".join(str(value) for value in item.get("candidate_files") or []) or "未挂载"
        lines.append(
            "| ☐ | {gate} | {status} | {roles} | {inputs} | {candidates} | {action} |".format(
                gate=_markdown_cell(item.get("acceptance_id", "")),
                status=_markdown_cell(item.get("status", "")),
                roles=_markdown_cell(roles),
                inputs=_markdown_cell(formal_inputs),
                candidates=_markdown_cell(candidates),
                action=_markdown_cell(item.get("required_action", "")),
            )
        )
    if not items:
        lines.append("| ☑ | 全部门槛 | passed | - | - | - | 无待办 |")

    lines.extend(
        [
            "",
            "## 统一执行顺序",
            "",
            "1. 在验收工作台按门槛点击“载入候选”，核对候选引用的原页、日志、截图和导出文件。",
            "2. 由表中责任角色填写真实姓名、复核时间、决定和必要的修改；不得沿用占位人名或机器自评。",
            "3. 将确认后的内容保存到对应正式输入文件；保存时保留当前 SHA-256，避免多人覆盖。",
            "4. 重新生成验收包；只有门槛状态实际变为 `passed` 才勾选本清单。",
            "5. 两名角色共同负责的门槛必须保留两份独立签名或等价审计记录。",
            "",
            "## 签署记录",
            "",
            "| 责任角色 | 姓名 | 已复核门槛 | 签署时间 | 决定/备注 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for role in sorted(role_items):
        lines.append(f"| {_markdown_cell(role)} |  |  |  |  |")
    if not role_items:
        lines.append("| 无待签角色 | - | - | - | - |")
    return "\n".join(lines) + "\n"


def _evaluate_ocr_coverage(
    payload: dict[str, Any] | None,
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    if not payload:
        return _gate("not_evaluated", "缺少 ocr_coverage.json。")

    total = _nonnegative_int(payload.get("total_pages"))
    text_or_structure_pages = _nonnegative_int(payload.get("text_or_structure_pages"))
    declared_blocked_pages = _nonnegative_int(payload.get("blocked_pages"))

    blocked_records = list(payload.get("blocked_page_records") or [])
    valid_blocked_records: dict[tuple[str, int], dict[str, Any]] = {}
    for record in blocked_records:
        if not isinstance(record, dict) or not _valid_ocr_blocked_page_record(
            record,
            evidence_root=evidence_root,
        ):
            continue
        key = (str(record["source_file"]).strip(), _nonnegative_int(record.get("page_num")))
        valid_blocked_records[key] = record
    validated_blocked_pages = len(valid_blocked_records)
    invalid_blocked_records = len(blocked_records) - validated_blocked_pages

    spotchecks = list(payload.get("spotchecks") or [])
    valid_spotchecks = [
        row
        for row in spotchecks
        if isinstance(row, dict) and _valid_ocr_spotcheck(row, evidence_root=evidence_root)
    ]
    categories = {str(row["category"]).strip() for row in valid_spotchecks}
    missing_categories = REQUIRED_OCR_CATEGORIES - categories
    invalid_spotchecks = len(spotchecks) - len(valid_spotchecks)

    accounted = text_or_structure_pages + validated_blocked_pages
    coverage = accounted / total if total else 0.0
    blocked_count_matches = declared_blocked_pages == validated_blocked_pages
    passed = (
        total > 0
        and accounted == total
        and blocked_count_matches
        and not invalid_blocked_records
        and not missing_categories
        and not invalid_spotchecks
    )
    failures: list[str] = []
    if total <= 0 or accounted != total:
        failures.append("页面覆盖必须为 100%")
    if not blocked_count_matches or invalid_blocked_records:
        failures.append("阻断页必须逐页提供失败码、重试次数、下游阻断状态和证据引用")
    if missing_categories:
        failures.append(f"缺少人工抽检类别 {sorted(missing_categories)}")
    if invalid_spotchecks:
        failures.append("人工抽检记录必须包含通过结论、审核人、审核时间和原页证据")
    return _gate(
        "passed" if passed else "failed",
        "页覆盖、页面级阻断记录与五类人工抽检均满足要求。"
        if passed
        else "；".join(failures),
        sample_count=total,
        metrics={
            "page_coverage": round(coverage, 6),
            "text_or_structure_pages": text_or_structure_pages,
            "blocked_pages_declared": declared_blocked_pages,
            "blocked_pages_validated": validated_blocked_pages,
            "invalid_blocked_page_records": invalid_blocked_records,
            "spotcheck_count": len(valid_spotchecks),
            "categories": sorted(categories),
            "missing_categories": sorted(missing_categories),
            "invalid_spotcheck_records": invalid_spotchecks,
        },
    )


def _valid_ocr_blocked_page_record(
    record: dict[str, Any],
    *,
    evidence_root: Path,
) -> bool:
    evidence_refs = record.get("evidence_refs") or []
    return bool(
        str(record.get("source_file") or "").strip()
        and _nonnegative_int(record.get("page_num")) > 0
        and str(record.get("failure_code") or "").strip()
        and str(record.get("reason") or "").strip()
        and _nonnegative_int(record.get("attempt_count")) > 0
        and record.get("downstream_publish_blocked") is True
        and isinstance(evidence_refs, list)
        and any(str(item).strip() for item in evidence_refs)
        and _evidence_refs_exist(evidence_root, evidence_refs)
    )


def _valid_ocr_spotcheck(record: dict[str, Any], *, evidence_root: Path) -> bool:
    return bool(
        str(record.get("category") or "").strip() in REQUIRED_OCR_CATEGORIES
        and str(record.get("source_file") or "").strip()
        and _nonnegative_int(record.get("page_num")) > 0
        and str(record.get("decision") or "").strip().lower() in OCR_SPOTCHECK_PASS_DECISIONS
        and str(record.get("reviewer") or "").strip()
        and str(record.get("reviewed_at") or "").strip()
        and str(record.get("evidence_ref") or "").strip()
        and _evidence_refs_exist(evidence_root, [record.get("evidence_ref")])
    )


def _evidence_refs_exist(root: Path, references: list[Any]) -> bool:
    resolved_root = root.resolve()
    for reference in references:
        relative = Path(str(reference or "").strip())
        if not str(relative) or relative.is_absolute():
            return False
        candidate = (resolved_root / relative).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            return False
        if not candidate.is_file():
            return False
    return True


def _reviewed_row(record: dict[str, Any], *, evidence_root: Path) -> bool:
    return bool(
        str(record.get("reviewer") or "").strip()
        and str(record.get("reviewed_at") or "").strip()
        and str(record.get("evidence_ref") or "").strip()
        and _evidence_refs_exist(evidence_root, [record.get("evidence_ref")])
    )


def _valid_review_block(payload: dict[str, Any], *, evidence_root: Path) -> bool:
    review = payload.get("review") or {}
    if not isinstance(review, dict):
        return False
    evidence_refs = review.get("evidence_refs") or []
    return bool(
        str(review.get("reviewer") or "").strip()
        and str(review.get("reviewed_at") or "").strip()
        and isinstance(evidence_refs, list)
        and evidence_refs
        and _evidence_refs_exist(evidence_root, evidence_refs)
    )


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _evaluate_ocr_gold(
    rows: list[dict[str, Any]],
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    candidates = [
        row
        for row in rows
        if row.get("gold_text") is not None and row.get("predicted_text") is not None
    ]
    valid = [row for row in candidates if _reviewed_row(row, evidence_root=evidence_root)]
    if not valid:
        return _gate(
            "failed" if candidates else "not_evaluated",
            "OCR 金标准必须逐页提供审核人、审核时间和包内原页证据。"
            if candidates
            else "缺少 ocr_gold.jsonl 人工逐字金标准。",
            sample_count=len(candidates),
        )
    accuracies = []
    critical_total = critical_correct = 0
    clear_count = 0
    clear_pass = True
    for row in valid:
        gold = normalize_ocr_text(str(row["gold_text"]))
        predicted = normalize_ocr_text(str(row["predicted_text"]))
        accuracy = 1.0 - (levenshtein_distance(gold, predicted) / max(len(gold), 1))
        accuracies.append(max(0.0, accuracy))
        if str(row.get("category")) == "clear":
            clear_count += 1
            clear_pass = clear_pass and accuracy >= 0.95
        for field in row.get("critical_fields") or []:
            critical_total += 1
            critical_correct += str(field.get("gold") or "") == str(field.get("predicted") or "")
    passed = clear_count > 0 and clear_pass and critical_total > 0
    return _gate(
        "passed" if passed else "failed",
        "清晰印刷体字符准确率达到 95%，关键字段已逐项核对。"
        if passed
        else "必须包含清晰页且每页字符准确率不低于 95%，并提供关键字段核对。",
        sample_count=len(valid),
        metrics={
            "mean_character_accuracy": round(sum(accuracies) / len(accuracies), 6),
            "clear_sample_count": clear_count,
            "critical_field_accuracy": round(critical_correct / critical_total, 6) if critical_total else None,
        },
    )


def _evaluate_retrieval_gold(
    rows: list[dict[str, Any]],
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    candidates = [row for row in rows if row.get("relevant_evidence_ids")]
    valid = [row for row in candidates if _reviewed_row(row, evidence_root=evidence_root)]
    if len(valid) < 10:
        return _gate(
            "not_evaluated" if not candidates else "failed",
            "需要至少 10 个带审核人、审核时间和包内证据的专家问题及相关证据块。",
            sample_count=len(valid),
            metrics={"unreviewed_or_invalid_count": len(candidates) - len(valid)},
        )
    recalls = []
    reciprocal_ranks = []
    resolvable = []
    for row in valid:
        relevant = {str(item) for item in row["relevant_evidence_ids"]}
        retrieved = [str(item) for item in row.get("retrieved_evidence_ids") or []]
        recalls.append(bool(relevant.intersection(retrieved[:5])))
        ranks = [index for index, item in enumerate(retrieved, start=1) if item in relevant]
        reciprocal_ranks.append(1 / min(ranks) if ranks else 0.0)
        resolvable.extend(bool(item.get("resolvable")) for item in row.get("citations") or [])
    recall_at_5 = sum(recalls) / len(recalls)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)
    citation_rate = sum(resolvable) / len(resolvable) if resolvable else 0.0
    passed = recall_at_5 >= 0.8 and citation_rate == 1.0
    return _gate(
        "passed" if passed else "failed",
        "Recall@5 达标且所有展示引用可解析。" if passed else "Recall@5 必须不低于 80%，引用可解析率必须为 100%。",
        sample_count=len(valid),
        metrics={"recall_at_5": round(recall_at_5, 6), "mrr": round(mrr, 6), "citation_resolvable_rate": round(citation_rate, 6)},
    )


def _evaluate_retrieval_edge_cases(
    rows: list[dict[str, Any]],
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    required = {"no_answer", "cross_model", "source_conflict", "version_rollback"}
    candidates = [row for row in rows if row.get("case_type")]
    cases = {
        str(row.get("case_type")): row
        for row in candidates
        if _reviewed_row(row, evidence_root=evidence_root)
    }
    if not cases:
        return _gate(
            "failed" if candidates else "not_evaluated",
            "四类边界用例必须提供审核人、审核时间和包内证据。"
            if candidates
            else "缺少无答案、跨型号、冲突来源和版本回滚用例。",
        )
    missing = required - set(cases)
    failures = [name for name, row in cases.items() if name in required and not bool(row.get("passed"))]
    passed = not missing and not failures
    return _gate(
        "passed" if passed else "failed",
        "四类边界问题均通过。" if passed else f"缺失 {sorted(missing)}；失败 {sorted(failures)}。",
        sample_count=len(required & set(cases)),
        metrics={"required_case_types": sorted(required)},
    )


def _evaluate_graph_gold(
    payload: dict[str, Any] | None,
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    if not payload:
        return _gate("not_evaluated", "缺少 graph_gold.json 人工关系金标准。")
    gold = {_relation_key(item) for item in payload.get("gold_relations") or []}
    predicted = {_relation_key(item) for item in payload.get("predicted_relations") or []}
    review_valid = _valid_review_block(payload, evidence_root=evidence_root)
    if len(gold) < 100:
        return _gate("failed", "人工金标准关系必须不少于 100 条。", sample_count=len(gold))
    matched = gold & predicted
    precision = len(matched) / len(predicted) if predicted else 0.0
    recall = len(matched) / len(gold)
    gold_entities = {value for item in gold for value in (item[0], item[2])}
    predicted_entities = {value for item in predicted for value in (item[0], item[2])}
    entity_match = gold_entities & predicted_entities
    entity_precision = len(entity_match) / len(predicted_entities) if predicted_entities else 0.0
    entity_recall = len(entity_match) / len(gold_entities) if gold_entities else 0.0
    passed = precision >= 0.85 and recall >= 0.70 and review_valid
    return _gate(
        "passed" if passed else "failed",
        "关系精确率、召回率和人工审核证据达到 V1 门槛。"
        if passed
        else "关系精确率需 ≥85%，召回率需 ≥70%，且必须有具名审核与包内证据。",
        sample_count=len(gold),
        metrics={
            "relation_precision": round(precision, 6),
            "relation_recall": round(recall, 6),
            "entity_precision": round(entity_precision, 6),
            "entity_recall": round(entity_recall, 6),
            "review_valid": review_valid,
        },
    )


def _evaluate_graph_evidence(
    payload: dict[str, Any] | None,
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    if not payload or "published_statements" not in payload:
        return _gate("not_evaluated", "缺少已发布图语句证据审计。")
    statements = list(payload.get("published_statements") or [])
    bound = sum(bool(item.get("evidence_bound")) for item in statements)
    violations = sum(int(item.get("blocking_violation_count") or 0) for item in statements)
    same_question = list(payload.get("same_question_comparison") or [])
    expert = all(item.get("expert_judgement") for item in same_question) if same_question else False
    review_valid = _valid_review_block(payload, evidence_root=evidence_root)
    passed = (
        bool(statements)
        and bound == len(statements)
        and violations == 0
        and bool(same_question)
        and expert
        and review_valid
    )
    return _gate(
        "passed" if passed else "failed",
        "证据绑定、违规逃逸及同题集专家判断均满足要求。"
        if passed
        else "要求 100% 证据绑定、0 个阻断违规逃逸，并完成带包内证据的同题集专家审核。",
        sample_count=len(statements),
        metrics={
            "evidence_binding_rate": round(bound / len(statements), 6) if statements else 0.0,
            "blocking_violation_escape_count": violations,
            "same_question_cases": len(same_question),
            "review_valid": review_valid,
        },
    )


def _evaluate_fmea_expert(
    rows: list[dict[str, Any]],
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    candidates = [row for row in rows if str(row.get("expert_decision")) in EXPERT_DECISIONS]
    valid = [row for row in candidates if _reviewed_row(row, evidence_root=evidence_root)]
    if not valid:
        return _gate(
            "failed" if candidates else "not_evaluated",
            "FMEA 专家结论必须逐项提供审核人、审核时间和包内证据。"
            if candidates
            else "缺少 fmea_expert.jsonl 领域专家逐项结论。",
            sample_count=len(candidates),
        )
    nonempty = evidence_bound = 0
    score_violations = 0
    for row in valid:
        fields = dict(row.get("fields") or {})
        evidence = dict(row.get("field_evidence") or {})
        for name, value in fields.items():
            if value not in (None, ""):
                nonempty += 1
                evidence_bound += bool(evidence.get(name))
        score_violations += any(row.get(name) not in (None, "") for name in ("severity", "occurrence", "detection", "rpn"))
    major_or_rejected = sum(str(row["expert_decision"]) in {"major", "rejected"} for row in valid)
    evidence_rate = evidence_bound / nonempty if nonempty else 1.0
    revision_rate = major_or_rejected / len(valid)
    passed = evidence_rate == 1.0 and revision_rate <= 0.2 and score_violations == 0
    return _gate(
        "passed" if passed else "failed",
        "专业字段证据、专家修订率和评分空值满足要求。" if passed else "非空字段证据需 100%，重大修改+拒绝需 ≤20%，未批准评分必须为空。",
        sample_count=len(valid),
        metrics={"field_evidence_rate": round(evidence_rate, 6), "major_or_rejected_rate": round(revision_rate, 6), "score_policy_violation_count": score_violations},
    )


def _evaluate_fmea_exports(
    payload: dict[str, Any] | None,
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    if not payload:
        return _gate("not_evaluated", "缺少 fmea_export_verification.json。")
    row_count = _nonnegative_int(payload.get("row_count") or payload.get("json_rows"))
    json_rows = _nonnegative_int(payload.get("json_rows") or row_count)
    csv_rows = _nonnegative_int(payload.get("csv_rows"))
    docx_rows = _nonnegative_int(payload.get("docx_rows"))
    format_rows_match = row_count > 0 and row_count == json_rows == csv_rows == docx_rows
    review_valid = _valid_review_block(payload, evidence_root=evidence_root)
    passed = (
        format_rows_match
        and bool(payload.get("consistent"))
        and bool(payload.get("docx_verified"))
        and bool(payload.get("lineage_consistent"))
        and review_valid
    )
    return _gate(
        "passed" if passed else "failed",
        "JSON、CSV、正式模板与血缘一致，且具备人工核对证据。"
        if passed
        else "JSON、CSV、DOCX 行数与字段必须一致，DOCX 回读、完整血缘和带证据人工核对必须同时通过。",
        sample_count=row_count,
        metrics={
            "consistent": bool(payload.get("consistent")),
            "json_rows": json_rows,
            "csv_rows": csv_rows,
            "docx_rows": docx_rows,
            "docx_verified": bool(payload.get("docx_verified")),
            "format_rows_match": format_rows_match,
            "lineage_consistent": bool(payload.get("lineage_consistent")),
            "review_valid": review_valid,
        },
    )


def _evaluate_e2e(
    payload: dict[str, Any] | None,
    *,
    recovery: bool,
    evidence_root: Path,
) -> dict[str, Any]:
    gate = "恢复闭环" if recovery else "角色化界面闭环"
    if not payload:
        return _gate("not_evaluated", f"缺少 e2e_signoff.json {gate}签字。")
    if recovery:
        required = {"index_rebuild", "graph_resync", "document_rollback", "project_restore"}
    else:
        required = {"create_project", "intake", "resolve_issue", "publish_document", "publish_graph", "publish_fmea", "export", "feedback"}
    operations = {str(key) for key, value in dict(payload.get("operations") or {}).items() if bool(value)}
    roles = {str(payload.get("knowledge_engineer") or ""), str(payload.get("domain_reviewer") or "")} - {""}
    signatures = {str(item) for item in payload.get("signatures") or [] if str(item)}
    evidence_refs = payload.get("evidence_refs") or []
    signed = bool(payload.get("signed_at")) and roles <= signatures
    evidence_valid = bool(
        isinstance(evidence_refs, list)
        and evidence_refs
        and _evidence_refs_exist(evidence_root, evidence_refs)
    )
    passed = (
        required <= operations
        and len(roles) == 2
        and signed
        and evidence_valid
        and bool(payload.get("ui_only"))
    )
    return _gate(
        "passed" if passed else "failed",
        f"{gate}已由两个不同角色在正式界面完成并签字。"
        if passed
        else f"{gate}必须由两个不同角色仅通过正式界面完成，双方签字并附包内操作证据。",
        sample_count=len(required & operations),
        metrics={
            "required_operations": sorted(required),
            "completed_operations": sorted(required & operations),
            "distinct_roles": len(roles),
            "ui_only": bool(payload.get("ui_only")),
            "signatures_valid": signed,
            "evidence_valid": evidence_valid,
        },
    )


def _evaluate_performance(
    payload: dict[str, Any] | None,
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    if not payload:
        return _gate("not_evaluated", "缺少约定 Windows 参考设备上的 performance.json。")
    metrics = {
        "retrieval_p95_seconds": _p95(payload.get("retrieval_seconds") or []),
        "graph_path_p95_seconds": _p95(payload.get("graph_path_seconds") or []),
        "preview_p95_seconds": _p95(payload.get("preview_seconds") or []),
    }
    sample_count = min(
        len(payload.get("retrieval_seconds") or []),
        len(payload.get("graph_path_seconds") or []),
        len(payload.get("preview_seconds") or []),
    )
    review_valid = _valid_review_block(payload, evidence_root=evidence_root)
    baseline = (
        bool(payload.get("windows_reference_device"))
        and _nonnegative_int(payload.get("pilot_document_count")) >= 14
        and bool(payload.get("embedding_model"))
        and sample_count >= 3
        and review_valid
    )
    passed = (
        baseline
        and metrics["retrieval_p95_seconds"] < 2
        and metrics["graph_path_p95_seconds"] < 2
        and metrics["preview_p95_seconds"] < 3
    )
    metrics["review_valid"] = review_valid
    return _gate(
        "passed" if passed else "failed",
        "P95 与参考基线满足 TECH-15。"
        if passed
        else "需在约定设备、14 本资料和固定嵌入模型上至少实测 3 次，附原始证据并满足 2s/2s/3s P95。",
        sample_count=sample_count,
        metrics=metrics,
    )


def _evaluate_large_file(
    payload: dict[str, Any] | None,
    *,
    evidence_root: Path,
) -> dict[str, Any]:
    if not payload:
        return _gate("not_evaluated", "缺少 large_file.json 60 MB 实传记录。")
    source_sha256 = str(payload.get("source_sha256") or "").strip().lower()
    review_valid = _valid_review_block(payload, evidence_root=evidence_root)
    identity_valid = bool(
        str(payload.get("task_id") or "").strip()
        and len(source_sha256) == 64
        and all(char in "0123456789abcdef" for char in source_sha256)
    )
    passed = (
        float(payload.get("file_size_mb") or 0) >= 60
        and bool(payload.get("asynchronous"))
        and bool(payload.get("progress_visible"))
        and not bool(payload.get("browser_frozen"))
        and not bool(payload.get("request_timed_out"))
        and identity_valid
        and review_valid
    )
    metrics = {
        key: payload.get(key)
        for key in (
            "file_size_mb",
            "asynchronous",
            "progress_visible",
            "browser_frozen",
            "request_timed_out",
        )
    }
    metrics.update({"identity_valid": identity_valid, "review_valid": review_valid})
    return _gate(
        "passed" if passed else "failed",
        "60 MB 资料异步处理且界面无卡死/超时。"
        if passed
        else "必须提供任务 ID、源文件 SHA、包内观察证据，并验证 60 MB 实传、异步进度、浏览器不卡死且请求不超时。",
        sample_count=1,
        metrics=metrics,
    )


def _gate(status: str, message: str, *, sample_count: int = 0, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": status, "message": message, "sample_count": sample_count, "metrics": metrics or {}}


def _relation_key(item: Any) -> tuple[str, str, str]:
    if isinstance(item, dict):
        return (str(item.get("subject") or "").strip(), str(item.get("predicate") or "").strip().upper(), str(item.get("object") or item.get("object_name") or "").strip())
    values = list(item or [])
    return tuple(str(values[index]).strip() if index < len(values) else "" for index in range(3))  # type: ignore[return-value]


def _p95(values: list[Any]) -> float:
    numeric = sorted(float(item) for item in values)
    if not numeric:
        return float("inf")
    return numeric[max(0, min(len(numeric) - 1, int(0.95 * len(numeric) + 0.999999) - 1))]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, dict) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {"path": path.relative_to(root).as_posix(), "byte_size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}


def _markdown_cell(value: Any) -> str:
    return str(json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value).replace("|", "\\|").replace("\n", " ")
