from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from build_defense_rehearsal_scorecard import (
    OUTPUT_JSON as DEFENSE_REHEARSAL_SCORECARD_JSON,
    OUTPUT_MD as DEFENSE_REHEARSAL_SCORECARD_MD,
    build_payload as build_defense_scorecard_payload,
    write_outputs as write_defense_scorecard_outputs,
)
from build_defense_rehearsal_result_packet import (
    OUTPUT_JSON as DEFENSE_REHEARSAL_RESULT_PACKET_JSON,
    OUTPUT_MD as DEFENSE_REHEARSAL_RESULT_PACKET_MD,
    build_payload as build_defense_result_payload,
    write_outputs as write_defense_result_outputs,
)
from build_expert_feedback_request_packet import (
    OUTPUT_JSON as EXPERT_FEEDBACK_REQUEST_PACKET_JSON,
    OUTPUT_MD as EXPERT_FEEDBACK_REQUEST_PACKET_MD,
    build_payload as build_expert_request_payload,
    write_outputs as write_expert_request_outputs,
)
from build_graphrag_answer_benchmark import (
    OUTPUT_JSON as GRAPH_ANSWER_BENCHMARK_JSON,
    OUTPUT_MD as GRAPH_ANSWER_BENCHMARK_MD,
    build_payload as build_graph_answer_benchmark_payload,
    write_markdown as write_graph_answer_benchmark_markdown,
)
from build_graphrag_gap_remediation_plan import (
    OUTPUT_JSON as GRAPH_GAP_REMEDIATION_JSON,
    OUTPUT_MD as GRAPH_GAP_REMEDIATION_MD,
    build_payload as build_graph_gap_remediation_payload,
    write_markdown as write_graph_gap_remediation_markdown,
)
from build_challenge_cup_defense_deck import (
    FINAL_PPTX as DEFENSE_DECK_PPTX,
    SPEAKER_NOTES as DEFENSE_DECK_NOTES,
    build_outputs as build_defense_deck_outputs,
)
from build_challenge_cup_hard_evidence_ledger import (
    EXPERT_README as HARD_EVIDENCE_EXPERT_README,
    OUTPUT_JSON as HARD_EVIDENCE_LEDGER_JSON,
    OUTPUT_MD as HARD_EVIDENCE_LEDGER_MD,
    REHEARSAL_README as HARD_EVIDENCE_REHEARSAL_README,
    ROOT_README as HARD_EVIDENCE_README,
    write_outputs as write_hard_evidence_ledger_outputs,
)
from build_challenge_cup_official_rubric_alignment import (
    OUTPUT_JSON as OFFICIAL_RUBRIC_ALIGNMENT_JSON,
    OUTPUT_MD as OFFICIAL_RUBRIC_ALIGNMENT_MD,
    write_outputs as write_official_rubric_alignment_outputs,
)
from check_challenge_cup_goal_completion import write_report as write_goal_completion_report


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "docs" / "challenge_cup"
REPRO = OUT / "reproducibility"
REPORTS = REPO_ROOT / "evaluation" / "reports"
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
ACCEPTANCE_CHECKLIST = OUT / "06_结项验收清单.md"
CLAIM_MATRIX = OUT / "07_评审主张证据矩阵.md"
AWARD_SELF_EVAL = OUT / "08_特等奖评审自评表.md"
EXPERT_REVIEW_INDEX = OUT / "09_专家快速审阅索引.md"
DEFENSE_REHEARSAL_CARD = OUT / "10_答辩攻防与彩排卡.md"
APPLICATION_VALIDATION_DOC = OUT / "11_应用场景与专家验证.md"
EXPERT_FEEDBACK_PROTOCOL = OUT / "12_专家反馈采集与整改闭环.md"
GRAPH_REPORT = REPORTS / "challenge_cup_graphrag_same_question_report.md"
GRAPH_REPORT_JSON = REPORTS / "challenge_cup_graphrag_same_question_report.json"
GRAPH_CONTEXT_DEMO_MD = REPORTS / "challenge_cup_graphrag_context_demo.md"
GRAPH_CONTEXT_DEMO_JSON = REPORTS / "challenge_cup_graphrag_context_demo.json"
GRAPH_MANUAL_EVIDENCE_SUPPLEMENT = REPRO / "graphrag_manual_evidence_supplement.csv"
LIVE_SMOKE_REPORT = REPRO / "live_demo_smoke_report.md"
BROWSER_SMOKE_REPORT = REPRO / "browser_demo_smoke_report.md"
BROWSER_SMOKE_JSON = REPRO / "browser_demo_smoke_report.json"
READINESS_GATE_REPORT = REPRO / "readiness_gate_report.md"
GOAL_COMPLETION_REPORT = REPRO / "goal_completion_report.md"
EVIDENCE_HASHES = REPRO / "evidence_hashes.json"
EVAL_COVERAGE_PROFILE = REPRO / "evaluation_coverage_profile.json"
SUBMISSION_ARCHIVE = REPRO / "challenge_cup_submission_package.zip"
SUBMISSION_ARCHIVE_MANIFEST = REPRO / "challenge_cup_submission_archive_manifest.json"
APPLICATION_VALIDATION_REPORT = REPRO / "application_validation_report.md"
EXPERT_FEEDBACK_FORM = REPRO / "expert_feedback_form.md"
BROWSER_SCREENSHOT_DIR = REPRO / "browser_screenshots"
BROWSER_SCREENSHOTS = [
    BROWSER_SCREENSHOT_DIR / "desktop_overview.png",
    BROWSER_SCREENSHOT_DIR / "desktop_search_results.png",
    BROWSER_SCREENSHOT_DIR / "desktop_kg_artifacts.png",
    BROWSER_SCREENSHOT_DIR / "mobile_overview.png",
]
EVAL_COVERAGE_MINIMUMS = {
    "task_types": 10,
    "source_scopes": 15,
    "graphrag_questions": 10,
}
ARCHIVE_TIMESTAMP = (2026, 6, 5, 21, 6, 0)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_submission_archive_inputs(evidence_files: list[str]) -> list[str]:
    excluded = {
        md_link(SUBMISSION_ARCHIVE),
        md_link(SUBMISSION_ARCHIVE_MANIFEST),
        md_link(READINESS_GATE_REPORT),
    }
    required = set(evidence_files)
    required.difference_update(excluded)
    required.update(
        {
            md_link(OUT / "package_manifest.json"),
            md_link(EVIDENCE_HASHES),
            md_link(EVAL_COVERAGE_PROFILE),
            md_link(REPRO / "dataset_manifest.md"),
            md_link(REPRO / "runbook.md"),
            md_link(REPRO / "command_log.md"),
        }
    )
    for path in OUT.rglob("*"):
        if not path.is_file():
            continue
        relative = md_link(path)
        if (
            relative in excluded
            or (path.name.startswith(f"{SUBMISSION_ARCHIVE.name}.") and path.name.endswith(".tmp"))
        ):
            continue
        required.add(relative)

    missing = sorted(relative for relative in required if not (REPO_ROOT / relative).is_file())
    empty = sorted(relative for relative in required if (REPO_ROOT / relative).is_file() and (REPO_ROOT / relative).stat().st_size == 0)
    if missing or empty:
        raise FileNotFoundError(f"submission archive inputs invalid: missing={missing}, empty={empty}")
    return sorted(required)


def write_submission_archive(ctx: dict[str, Any], included_files: list[str]) -> None:
    SUBMISSION_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    temp_archive = SUBMISSION_ARCHIVE.with_name(f"{SUBMISSION_ARCHIVE.name}.{os.getpid()}.tmp")
    if temp_archive.exists():
        temp_archive.unlink()
    with zipfile.ZipFile(temp_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in included_files:
            info = zipfile.ZipInfo(relative, date_time=ARCHIVE_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            archive.writestr(info, (REPO_ROOT / relative).read_bytes())
    temp_archive.replace(SUBMISSION_ARCHIVE)
    manifest = {
        "generated_at": ctx["now"],
        "archive_path": md_link(SUBMISSION_ARCHIVE),
        "algorithm": "sha256",
        "bytes": SUBMISSION_ARCHIVE.stat().st_size,
        "sha256": sha256_file(SUBMISSION_ARCHIVE),
        "file_count": len(included_files),
        "included_files": included_files,
        "excluded_files": [md_link(READINESS_GATE_REPORT), md_link(SUBMISSION_ARCHIVE), md_link(SUBMISSION_ARCHIVE_MANIFEST)],
    }
    write(SUBMISSION_ARCHIVE_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))


def read(path: Path, limit: int = 1600) -> str:
    if not path.exists():
        return f"文件未找到：{path}"
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text if len(text) <= limit else text[:limit].rstrip() + "\n..."


def count_jsonl(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_evaluation_coverage_profile(ctx: dict[str, Any]) -> dict[str, Any]:
    rows = read_jsonl(DATASET)
    task_type_counts = Counter(str(row["task_type"]) for row in rows)
    source_scope_counts = Counter(str(row["source_scope"]) for row in rows)
    expected_mode_counts: Counter[str] = Counter()
    questions_with_graphrag_modes = 0
    for row in rows:
        modes = [str(mode) for mode in row.get("expected_modes", [])]
        expected_mode_counts.update(modes)
        if any(mode.startswith("graphrag_") for mode in modes):
            questions_with_graphrag_modes += 1
    return {
        "generated_at": ctx["now"],
        "generated_from": md_link(DATASET),
        "question_count": len(rows),
        "task_type_counts": dict(sorted(task_type_counts.items())),
        "source_scope_counts": dict(sorted(source_scope_counts.items())),
        "expected_mode_counts": dict(sorted(expected_mode_counts.items())),
        "questions_with_graphrag_modes": questions_with_graphrag_modes,
        "minimums": dict(EVAL_COVERAGE_MINIMUMS),
    }


def latest(pattern: str) -> Path | None:
    candidates = sorted(REPORTS.glob(pattern))
    return candidates[-1] if candidates else None


def generated_at_from_reports(*paths: Path | None) -> str:
    stamps: list[str] = []
    for path in paths:
        if path is None:
            continue
        match = re.search(r"(\d{8})_(\d{6})", path.name)
        if match:
            stamps.append(match.group(1) + match.group(2))
    if not stamps:
        return "1970-01-01 00:00"
    stamp = max(stamps)
    return datetime.strptime(stamp, "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M")


def md_link(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def optional_md_link(path: Path | None) -> str:
    return md_link(path) if path is not None else "暂无对应报告，运行 runbook 中的评测命令后生成"


def browser_validation_context() -> dict[str, Any]:
    fallback = {
        "query": "燃气轮机异常振动诊断流程",
        "search_meta": "集合 gas_turbine_ocr_demo_snapshot · 延迟 42.10 ms · 结果 5 · 后端 public-demo",
        "screenshot": md_link(BROWSER_SCREENSHOTS[1]),
    }
    if not BROWSER_SMOKE_JSON.exists():
        return fallback
    payload = json.loads(BROWSER_SMOKE_JSON.read_text(encoding="utf-8"))
    browser = payload.get("browser", {})
    screenshots = browser.get("screenshots", {})
    return {
        "query": browser.get("query") or fallback["query"],
        "search_meta": browser.get("search_meta") or fallback["search_meta"],
        "screenshot": screenshots.get("desktop_search_results") or fallback["screenshot"],
    }


def build_context() -> dict[str, Any]:
    day3 = latest("day3_retrieval_baseline_comparison_*.md")
    day4 = latest("day4_failure_analysis_*.md")
    return {
        "now": generated_at_from_reports(day3, day4),
        "question_count": count_jsonl(DATASET),
        "day3": day3,
        "day4": day4,
        "graph_report": GRAPH_REPORT if GRAPH_REPORT.exists() else None,
        "graph_report_json": GRAPH_REPORT_JSON if GRAPH_REPORT_JSON.exists() else None,
        "graph_context_demo_md": GRAPH_CONTEXT_DEMO_MD if GRAPH_CONTEXT_DEMO_MD.exists() else None,
        "graph_context_demo_json": GRAPH_CONTEXT_DEMO_JSON if GRAPH_CONTEXT_DEMO_JSON.exists() else None,
        "graph_answer_benchmark_md": GRAPH_ANSWER_BENCHMARK_MD,
        "graph_answer_benchmark_json": GRAPH_ANSWER_BENCHMARK_JSON,
        "graph_gap_remediation_md": GRAPH_GAP_REMEDIATION_MD,
        "graph_gap_remediation_json": GRAPH_GAP_REMEDIATION_JSON,
        "validation": browser_validation_context(),
        "rag_db": REPO_ROOT
        / "docs"
        / "project_deliverables"
        / "03_普通RAG数据库_14本资料"
        / "数据库构建结果_人话版.md",
        "kg_review": REPO_ROOT
        / "docs"
        / "project_deliverables"
        / "05_知识图谱POC_三元组和人工判断"
        / "人工判断小结.md",
        "course_pack": REPO_ROOT
        / "docs"
        / "project_deliverables"
        / "06_汇报材料_发群和组会"
        / "RAG课程汇报_最终交付包"
        / "README_先看这里.md",
    }


def build_readme(ctx: dict[str, Any]) -> str:
    return f"""# 挑战杯项目成果入口

生成时间：{ctx["now"]}

本目录是“知燃知维：面向动力装备运维知识的可信 GraphRAG 系统”的结项与挑战杯评审入口。先看本页，再按顺序阅读项目一页纸、项目书、技术白皮书、实验评测报告、演示脚本和答辩问答手册。

## 推荐阅读顺序

1. `00_项目一页纸.md`
2. `01_挑战杯项目书.md`
3. `02_技术白皮书.md`
4. `03_实验评测报告.md`
5. `04_系统演示脚本.md`
6. `05_答辩问答手册.md`
7. `06_结项验收清单.md`
8. `07_评审主张证据矩阵.md`
9. `08_特等奖评审自评表.md`
10. `09_专家快速审阅索引.md`
11. `10_答辩攻防与彩排卡.md`
12. `11_应用场景与专家验证.md`
13. `12_专家反馈采集与整改闭环.md`
14. `defense_deck/challenge_cup_defense_deck.pptx`
15. `defense_deck/challenge_cup_defense_speaker_notes.md`
16. `reproducibility/application_validation_report.md`
17. `reproducibility/expert_feedback_form.md`
18. `reproducibility/runbook.md`
19. `reproducibility/dataset_manifest.md`
20. `reproducibility/readiness_gate_report.md`
21. `reproducibility/goal_completion_report.md`
22. `reproducibility/defense_rehearsal_scorecard.md`
23. `reproducibility/defense_rehearsal_result_packet.md`
24. `reproducibility/expert_feedback_request_packet.md`
25. `reproducibility/official_rubric_alignment.md`
26. `reproducibility/hard_evidence_ledger.md`
27. `reproducibility/challenge_cup_submission_archive_manifest.json`
28. `reproducibility/challenge_cup_submission_package.zip`

## 当前核心数字

- 普通 RAG 数据库：9080 个 chunk。
- 系统评测集：{ctx["question_count"]} 题。
- 知识图谱 POC：27 条候选三元组，26 条正确，1 条待讨论，0 条明确错误。
- 已有课程交付包：PPT、讲稿、评测说明、失败分析、演示脚本、备用证据包和答辩口径。
"""


def build_one_page(ctx: dict[str, Any]) -> str:
    return """# 项目一页纸

## 项目名称

知燃知维：面向动力装备运维知识的可信 GraphRAG 系统

## 一句话定位

本项目把动力装备扫描资料、课程资料和问答 JSON 转化为可检索、可评测、可追溯的 RAG / GraphRAG 知识系统，用证据绑定和失败归因降低专业问答中的幻觉风险。

## 真实问题

动力装备资料具有扫描件多、专业术语密集、部件和故障关系复杂的特点。普通关键词检索难以稳定回答“现象、原因、检查项、处理措施和证据来源”之间的关系型问题。

## 核心贡献

1. 数据链路：OCR 审计、文本清洗、chunk 入库和 ChromaDB 持久化。
2. 知识链路：实体关系三元组、evidence 绑定、人工评审和图谱展示。
3. 评测链路：60 题系统评测集、baseline 对比、失败案例归因。
4. 演示链路：本地控制台主线和离线备用证据包。

## 核心数字

- 9080 个普通 RAG chunk。
- 60 道系统评测题。
- 27 条 POC 三元组，其中 26 条正确、1 条待讨论、0 条明确错误。

## 边界声明

系统提供证据型辅助，不替代工程师做真实运维决策；GraphRAG 用于增强跨文档和跨实体证据组织，不声称在所有问题上必然优于普通 RAG。
"""


def build_project_book(ctx: dict[str, Any]) -> str:
    return """# 挑战杯项目书

## 项目背景

燃气轮机和动力装备资料包含大量部件、参数、故障、工况和处理措施信息。传统资料检索依赖人工翻阅，普通问答系统又容易缺少来源说明。本项目面向这一问题，构建可信 GraphRAG 系统，让专业知识回答具备证据、关系和评测支撑。

## 技术路线

系统采用“资料处理 -> 普通 RAG -> 知识图谱构建 -> GraphRAG 检索 -> 证据约束回答 -> 自动评测”的路线。普通 RAG 负责单段证据召回，GraphRAG 负责部件、故障、参数和处理措施之间的关系组织，评测脚本负责比较不同策略的表现。

## 创新点

1. 面向动力装备资料的 OCR 到 RAG 到 GraphRAG 全链路工程。
2. evidence-bound 三元组和人工评审闭环，避免无证据知识图谱。
3. 以评测集和失败归因驱动改进，不只展示成功样例。
4. 明确高风险场景边界，将系统定位为证据型辅助。

## 应用价值

项目可用于课程知识整理、动力装备资料学习、运维知识检索和故障分析证据准备。它把分散资料转化为可检索和可审计知识资产。

## 完成情况

当前已完成资料处理、普通 RAG 数据库、知识图谱 POC、60 题 baseline、失败分析、GraphRAG 同题子集和课程汇报包，并建立统一成果入口。
"""


def build_whitepaper(ctx: dict[str, Any]) -> str:
    return """# 技术白皮书

## 架构概览

系统由数据管线、检索引擎、知识图谱构建、RAG 编排、评测体系、控制台和挑战杯成果包组成。核心原则是所有回答都尽量回到原文证据、图谱关系或评测报告。

## 数据流

原始资料和 OCR 文本进入清洗与 chunk 阶段，写入普通 RAG 索引；知识图谱管线从 chunk 中抽取实体和关系，并绑定 evidence；检索阶段同时比较 keyword、dense hashing、hybrid RRF 和 GraphRAG 相关模式；评测阶段输出 recall、关键词覆盖率、证据覆盖和失败原因。

## GraphRAG 增量

GraphRAG 的价值不是画图，而是把部件、故障、参数和措施之间的关系显式化。局部图检索用于围绕实体查找关系证据，全局社区摘要用于跨文档归纳类问题。

## 安全边界

系统不输出无证据维修决策。若证据不足，回答应说明不足；若关系仍需人工判断，系统应保留待讨论状态。
"""


def build_eval_report(ctx: dict[str, Any]) -> str:
    day3_ref = optional_md_link(ctx["day3"])
    day4_ref = optional_md_link(ctx["day4"])
    graph_ref = optional_md_link(ctx["graph_report"])
    graph_context_ref = optional_md_link(ctx["graph_context_demo_md"])
    graph_answer_ref = optional_md_link(ctx["graph_answer_benchmark_md"])
    graph_gap_ref = optional_md_link(ctx["graph_gap_remediation_md"])
    graph_supplement_ref = md_link(GRAPH_MANUAL_EVIDENCE_SUPPLEMENT)
    return f"""# 实验评测报告

## 评测集

当前系统评测集包含 {ctx["question_count"]} 题，覆盖普通 RAG、OCR 风险、GraphRAG/知识图谱、结构化事实、评测方法和挑战杯答辩口径。

## 已有 baseline

Day3 已比较 keyword、dense_hashing 和 hybrid_rrf 三种离线检索策略。报告位置：`{day3_ref}`。

## 失败归因

Day4 已将弱命中和失败案例归类为术语别名、结构化事实、hybrid 稀释、排序差距和评测概念缺口等问题。报告位置：`{day4_ref}`。

## GraphRAG 同题子集

已从 60 题评测集中筛出显式标注 `graphrag_context` / `graphrag_global` 的同题子集，并对这些题的 keyword、dense_hashing、hybrid_rrf baseline 覆盖率做了对照。报告位置：`{graph_ref}`。

## GraphRAG context-only demo

已将 supported 同题案例生成 context-only GraphRAG QA 快照，固定展示文本检索证据和 triples.csv 图谱关系证据。报告位置：`{graph_context_ref}`。该 demo 不生成 LLM 答案，不作为完整在线 answer benchmark。

## GraphRAG answer benchmark

已将 10 道 GraphRAG 同题生成答案级覆盖对照，固定比较文本 baseline 参考关键词覆盖率与 triples.csv 图谱证据覆盖率；当前本地证据覆盖已关闭固定子集 partial/missing 缺口。报告位置：`{graph_answer_ref}`。该 benchmark 是 deterministic offline reference keyword coverage，不生成在线 LLM 答案，不宣称 GraphRAG 全面优于 baseline。

## GraphRAG 补证整改计划

已将 answer benchmark 暴露出的 partial/missing 案例转成可审计补证闭环。报告位置：`{graph_gap_ref}`。manual evidence supplement：`{graph_supplement_ref}` 已关闭 P0 missing 和 cc056 relation schema partial 缺口。该闭环只证明固定 GraphRAG 子集的本地证据覆盖，不宣称在线 LLM answer win-rate、外部专家验证或 GraphRAG 全面优于 baseline。

## 结论

当前项目能证明评测链路存在并可复跑，也能展示 GraphRAG context-only 证据编排、答案级覆盖对照和补证整改计划。挑战杯版本后续可继续补充真实 LLM answer 生成、embedding/reranker 复测和更大规模 benchmark。

## 关键证据摘录

### 普通 RAG 数据库

{read(ctx["rag_db"], 1200)}

### 知识图谱人工评审

{read(ctx["kg_review"], 1200)}
"""


def build_demo_script(ctx: dict[str, Any]) -> str:
    validation = ctx["validation"]
    return f"""# 系统演示脚本

## 主线演示

1. 打开 `docs/challenge_cup/00_项目一页纸.md`，用 30 秒说明问题、方法和核心数字。
2. 启动控制台：`cd api_server/current_console; python server.py`，打开 `http://localhost:8000`。
3. 固定场景演示：在检索框输入“{validation["query"]}”，展示 `docs/challenge_cup/reproducibility/browser_demo_smoke_report.json` 中记录的 `{validation["search_meta"]}`。
4. 按顺序讲清 5 条证据：`demo-maint-thresholds-076` 给出监测阈值，`demo-structure-fault-130` 解释异常振动机理，`demo-gt07-fault-021` 给出 GT-07 现象，`demo-gt07-repair-022` 给出进气滤网和压气机叶片处理结果，`demo-gt07-manual-023` 给出温度传感器校验等处置建议。
5. 主动说明边界：系统提供证据整理和来源追溯，必须由工程师结合现场工况人工确认，不替代最终维修决策。
6. 打开 `docs/challenge_cup/reproducibility/application_validation_report.md` 和 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`，证明固定场景不是口头承诺。
7. 打开 `docs/challenge_cup/03_实验评测报告.md`，说明 baseline 和失败归因。

## 备用演示

如果服务未启动，直接打开 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`、`docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`、`docs/challenge_cup/reproducibility/application_validation_report.md`、知识图谱审核页面、SVG、实验评测报告和答辩问答手册。现场不排查环境，把时间用于解释证据链。
"""


def build_qa(ctx: dict[str, Any]) -> str:
    return """# 答辩问答手册

## 为什么需要 GraphRAG？

普通 RAG 擅长查单段证据，GraphRAG 擅长组织跨实体和跨文档关系。本项目把 GraphRAG 用在部件、故障、参数和措施之间的关系证据上。

## 是否能替代工程师？

不能。系统定位是证据型辅助，提供可能原因、检查项和来源，不做最终维修决策。

## 为什么能冲击高奖？

项目不是单一页面，而是完整知识工程闭环：真实资料、OCR 审计、RAG 入库、图谱 evidence、评测、失败归因和可演示系统。

## 如果 GraphRAG 没有全面超过 keyword 怎么办？

按问题类型解释。keyword 对明确术语和数字事实很强，GraphRAG 对跨实体关系和全局归纳更有价值。

## 数据和表述有什么边界？

不声称生产级运维闭环，不声称所有三元组都已大规模自动验证，不声称当前评测集是最终论文 benchmark。
"""


def build_checklist(ctx: dict[str, Any]) -> str:
    return """# 结项验收清单

本清单用于结项老师或挑战杯评委快速判断项目是否具备“可提交、可复核、可答辩”的交付状态。验收口径是：先证明成果包完整和证据可追溯，再讨论创新性和奖项竞争力。

## 结项验收口径

- 可提交范围：挑战杯材料包、终审答辩 PPT/讲稿、可复现实验评测、固定应用场景、浏览器演示证据、专家反馈采集协议。
- 验收方式：按本页逐项打开证据，运行 readiness gate，并用固定 GT-07 场景复核证据链。
- 通过标准：材料路径存在、核心结论有证据、演示有离线备份、边界不夸大。

## 可提交材料

| 材料 | 路径 | 验收要点 | 状态 |
| --- | --- | --- | --- |
| 包清单 | `docs/challenge_cup/package_manifest.json` | 记录证据文件和评测题数，便于判断提交范围。 | 已固化 |
| 证据清单 | `docs/challenge_cup/reproducibility/dataset_manifest.md` | 汇总数据、报告、截图、KG artifact 和课程交付入口。 | 已固化 |
| 可复现门禁 | `docs/challenge_cup/reproducibility/readiness_gate_report.md` | 证明材料、manifest、哈希、浏览器 smoke 和应用案例均可复核。 | 已固化 |
| 终审答辩 PPT | `docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx` | 10 页终审答辩 deck，覆盖问题、方法、GT-07、GraphRAG、归档、边界和下一步。 | 已固化 |
| 终审答辩讲稿 | `docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md` | 90 秒开场、三分钟演示、杀手问题和边界口径。 | 已固化 |
| 演示证据 | `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` | 证明页面、搜索交互、KG artifact 和移动端基本可用。 | 已固化 |
| 应用验证 | `docs/challenge_cup/reproducibility/application_validation_report.md` | 用固定燃气轮机异常振动场景展示证据链和边界。 | 已固化 |
| 专家反馈表 | `docs/challenge_cup/reproducibility/expert_feedback_form.md` | 收集真实签字、邮件或会议纪要，不伪造外部背书。 | 待真实反馈归档 |

## 验收步骤

1. 打开 `docs/challenge_cup/README_先看这里.md`，确认评审阅读顺序。
2. 打开 `docs/challenge_cup/07_评审主张证据矩阵.md`，逐条核对主张、证据、命令和边界。
3. 打开 `docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx` 和讲稿，检查终审答辩主线。
4. 运行 `python scripts/build_challenge_cup_package.py` 重新生成材料包。
5. 运行 `python scripts/check_challenge_cup_readiness.py` 生成 `docs/challenge_cup/reproducibility/readiness_gate_report.md`。
6. 打开 `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png`，复核固定搜索结果。

## 现场演示与离线备份

| 场景 | 首选动作 | 备用动作 |
| --- | --- | --- |
| 后端和前端均可用 | 按 `docs/challenge_cup/04_系统演示脚本.md` 现场演示固定查询。 | 用 browser smoke 报告解释已验证的交互路径。 |
| 现场网络或后端不可用 | 不现场排环境。 | 打开 `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`、截图和 KG artifact 继续答辩。 |
| 评委追问真实应用价值 | 展示 `docs/challenge_cup/11_应用场景与专家验证.md`。 | 说明真实生产决策仍需人工确认。 |

## 未完成项与边界

| 项目 | 当前处理 | 不得夸大 |
| --- | --- | --- |
| 真实外部反馈 | 已有采集协议和表单，等待签字、邮件或会议纪要归档。 | 不宣称已经获得专家认可。 |
| 生产级运维上线 | 当前证明课程资料知识化和可复核演示。 | 不宣称替代工程师决策或已进入生产系统。 |
| 大规模 benchmark | 当前是 60 题挑战杯评测集和 GraphRAG 子集。 | 不宣称达到公开论文级大规模评测。 |

## 验收结论

当前材料包达到“可提交结项 / 可进入挑战杯评审”的状态：材料入口清楚，证据链可追溯，机器门禁可复核，演示有离线备份。下一阶段的提分项是归档真实专家反馈、强化现场彩排和扩展更大规模评测。
"""


def build_claim_evidence_matrix(ctx: dict[str, Any]) -> str:
    day3_ref = optional_md_link(ctx["day3"])
    day4_ref = optional_md_link(ctx["day4"])
    graph_ref = optional_md_link(ctx["graph_report"])
    return f"""# 评审主张证据矩阵

本矩阵把挑战杯答辩中的高水平主张逐条绑定到可核验材料、复现命令和边界说明，避免把项目包装成只有演示页面的普通 RAG 工具。

| 评审维度 | 可答辩主张 | 直接证据 | 复现 / 验证命令 | 边界说明 |
| --- | --- | --- | --- | --- |
| 创新性 | 项目不是单纯问答页面，而是面向动力装备知识的 evidence-bound RAG / GraphRAG 工程闭环。 | `docs/challenge_cup/02_技术白皮书.md`; `{graph_ref}`; `docs/project_deliverables/06_四本书KG工具跑通演示/kg_evidence_viewer.html` | `python scripts/build_graphrag_challenge_report.py` | GraphRAG 用于关系证据组织，不声称在所有问题上必然优于普通 RAG。 |
| 工程闭环 | 已形成资料处理、OCR、chunk 入库、检索、KG POC、演示、验收的端到端链路。 | `docs/challenge_cup/06_结项验收清单.md`; `docs/challenge_cup/reproducibility/dataset_manifest.md`; `docs/project_deliverables/03_普通RAG数据库_14本资料/数据库构建结果_人话版.md` | `python scripts/build_challenge_cup_package.py` | 当前交付强调可结项与可答辩，不等同于生产级运维系统上线。 |
| 科学评测 | 评测不是只挑成功案例，而是包含 60 题评测集、baseline、失败归因、GraphRAG 同题子集和补证闭环；固定 GraphRAG 子集当前本地证据缺口已关闭。 | `evaluation/system_eval_questions.jsonl`; `{day3_ref}`; `{day4_ref}`; `{graph_ref}`; `evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md` | `python scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5`; `python scripts/analyze_day4_failure_cases.py`; `python scripts/build_graphrag_gap_remediation_plan.py` | 评测集是当前阶段的课程 / 挑战杯评测集；本地证据覆盖不等于在线 LLM 胜率或外部专家验证。 |
| 可复现 | 评委可以按 runbook 复现包生成、live smoke、browser smoke 和 readiness gate。 | `docs/challenge_cup/reproducibility/runbook.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` | `python scripts/check_challenge_cup_readiness.py`; `node scripts/run_challenge_cup_browser_demo_smoke.mjs` | Browser smoke 证明本地演示与关键资源可用，不替代生产压测。 |
| 应用验证 | 项目已把“燃气轮机异常振动诊断”固化为可复核应用案例，能展示阈值、机理、现象、检修措施和复机结果的证据链。 | `docs/challenge_cup/11_应用场景与专家验证.md`; `docs/challenge_cup/reproducibility/application_validation_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.json`; `docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png` | `python scripts/build_challenge_cup_package.py`; `python scripts/check_challenge_cup_readiness.py` | 当前是公开演示快照和角色化审查，不伪造外部生产签字；高风险维修仍需人工确认。 |
| 专家反馈闭环 | 项目已准备好可发送给老师或行业专家的反馈采集表、评分维度、签字或邮件证据归档规则和整改闭环。 | `docs/challenge_cup/12_专家反馈采集与整改闭环.md`; `docs/challenge_cup/reproducibility/expert_feedback_form.md`; `docs/challenge_cup/reproducibility/application_validation_report.md` | `python scripts/check_challenge_cup_readiness.py` | 未收到真实反馈前不得宣称已通过专家验证；反馈必须按签字、邮件或会议纪要归档。 |
| 应用边界 | 系统定位为证据型辅助和知识资产整理，不替代工程师做最终运维决策。 | `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/00_项目一页纸.md`; `docs/challenge_cup/03_实验评测报告.md` | `python scripts/check_challenge_cup_readiness.py` | 对高风险维修决策保留人工确认和证据不足提示。 |
"""


def build_award_self_eval(ctx: dict[str, Any]) -> str:
    return """# 特等奖评审自评表

本表按清华公开报道中出现的评审维度进行自检：评委会关注作品的学术价值或实用性、创新性、作品完成情况和现场答辩表现；清华制度文件也强调实用性、创新性和学术价值。特等奖不超过6件，可空缺，因此本表只用于倒逼整改，不承诺获奖结果。完整官方口径与证据绑定见 `docs/challenge_cup/reproducibility/official_rubric_alignment.md`。

## 参考口径

- 清华大学第37届“挑战杯”校级终审报道：评委从作品的学术价值或实用性、创新性、作品完成情况和现场答辩表现等方面评分；特等奖候选作品经公开答辩和综合评定产生。链接：https://www.tsinghua.edu.cn/info/1181/35383.htm
- 《清华大学课外创新人才培养体系制度文件汇编》：评审应充分考虑作品的实用性、创新性和学术价值；特等奖不超过6件，可空缺。链接：https://qiyuan.tsinghua.edu.cn/intro/2018/11024/%E6%94%AF%E6%92%91%E6%9D%90%E6%96%993-%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E8%AF%BE%E5%A4%96%E5%88%9B%E6%96%B0%E4%BA%BA%E6%89%8D%E5%9F%B9%E5%85%BB%E4%BD%93%E7%B3%BB%E5%88%B6%E5%BA%A6%E6%96%87%E4%BB%B6%E6%B1%87%E7%BC%96.pdf

| 评审维度 | 当前自评 | 已有证据 | 仍需现场强调 | 风险控制 |
| --- | --- | --- | --- | --- |
| 学术价值或实用性 | A- | `docs/challenge_cup/07_评审主张证据矩阵.md`; `docs/challenge_cup/03_实验评测报告.md`; `evaluation/system_eval_questions.jsonl` | 把动力装备运维知识的真实痛点讲清楚，强调证据型辅助而非泛问答。 | 避免把课程数据包装成生产级运维闭环。 |
| 创新性 | A- | `docs/challenge_cup/02_技术白皮书.md`; `evaluation/reports/challenge_cup_graphrag_same_question_report.md`; `docs/project_deliverables/06_四本书KG工具跑通演示/kg_evidence_viewer.html` | 强调 evidence-bound KG、失败归因和 GraphRAG 同题子集，而不是只说用了 RAG。 | 明确 GraphRAG 不保证所有问题都超过普通 RAG。 |
| 作品完成情况 | A | `docs/challenge_cup/reproducibility/readiness_gate_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/runbook.md` | 现场先跑 readiness gate，再展示浏览器截图和 KG artifact。 | 如果 live backend 异常，按离线证据包继续答辩。 |
| 现场答辩表现 | A- | `docs/challenge_cup/04_系统演示脚本.md`; `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md`; `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`; `docs/challenge_cup/reproducibility/command_log.md` | 3分钟内讲清“问题-方法-证据-边界”，把失败案例变成科学性而不是扣分点。 | 结果归档包已经准备好；真实彩排完成前不得宣称已完成现场演练。 |
| 特等奖不超过6件 | 目标状态 | `docs/challenge_cup/07_评审主张证据矩阵.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` | 用“可复现证据链 + 严谨边界 + 工程闭环”争取进入特等奖讨论。 | 不把奖项概率写成承诺；持续补强演示稳定性和答辩节奏。 |
"""


def build_expert_review_index(ctx: dict[str, Any]) -> str:
    return """# 专家快速审阅索引

本索引用于让评委、结项验收老师或答辩委员在 3-5 分钟内定位项目证据。它不是新的主张材料，而是把已有项目书、评测、演示和门禁证据组织成可复核路径。

## 三分钟审阅路径

1. 先看项目定位：`docs/challenge_cup/00_项目一页纸.md`。
2. 再看特等奖口径：`docs/challenge_cup/08_特等奖评审自评表.md`。
3. 复核主张证据：`docs/challenge_cup/07_评审主张证据矩阵.md`。
4. 查看应用验证案例：`docs/challenge_cup/11_应用场景与专家验证.md`。
5. 查看可复现状态：`docs/challenge_cup/reproducibility/readiness_gate_report.md`。
6. 如果现场演示受限，查看浏览器证据：`docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`。

## 特等奖主张

| 主张 | 快速证据 | 复核方式 |
| --- | --- | --- |
| 项目不是普通问答页，而是可结项的 RAG / GraphRAG 知识工程闭环 | `docs/challenge_cup/01_挑战杯项目书.md`; `docs/challenge_cup/02_技术白皮书.md`; `docs/challenge_cup/06_结项验收清单.md` | 阅读项目书的技术路线和验收清单 |
| 评测不是只挑成功样例，而是有 60 题评测集、baseline、失败归因和 GraphRAG 同题子集 | `evaluation/system_eval_questions.jsonl`; `docs/challenge_cup/03_实验评测报告.md`; `evaluation/reports/challenge_cup_graphrag_same_question_report.md` | 运行评测命令或检查评测报告 |
| 演示不是口头承诺，而是有 live smoke、browser smoke、截图和 KG artifact 证据 | `docs/challenge_cup/reproducibility/live_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png` | 运行 smoke 或打开截图 |
| 应用价值不是泛泛而谈，而是有异常振动诊断固定案例、record id 和边界说明 | `docs/challenge_cup/11_应用场景与专家验证.md`; `docs/challenge_cup/reproducibility/application_validation_report.md` | 复核 GT-07 证据链和人工确认边界 |
| 申报边界清楚，不把课程资料系统夸大成生产级运维系统 | `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/08_特等奖评审自评表.md` | 检查答辩边界和风险控制 |

## 一键复核命令

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_package.py
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```

## 风险边界

- 当前 readiness gate 证明成果包、证据链接、评测集、smoke 报告和浏览器截图可复核；它不证明最终奖项结果。
- 当前系统定位为证据型辅助和知识资产整理；不替代工程师做真实运维决策。
- 如果现场后端启动失败，按 `docs/challenge_cup/04_系统演示脚本.md` 切换到离线证据包和浏览器截图继续答辩。
"""


def build_defense_rehearsal_card(ctx: dict[str, Any]) -> str:
    return """# 答辩攻防与彩排卡

本卡用于把“现场答辩表现”从临场发挥变成可训练、可复核、可切换的流程。彩排时按本卡计时，现场时按本卡选择主线和证据。

## 90秒开场

1. 15 秒：说明真实问题，动力装备资料分散、扫描件多、术语密集，普通检索难以解释部件、故障、参数和措施之间的关系。
2. 25 秒：说明方法，项目把 OCR、普通 RAG、evidence-bound 知识图谱、GraphRAG 检索和自动评测连成闭环。
3. 25 秒：说明完成度，评测集、baseline、失败归因、浏览器 smoke、KG artifact 和 readiness gate 均已留证。
4. 25 秒：说明边界，系统是证据型辅助和知识资产整理，不替代工程师做真实运维决策。

## 三分钟演示节奏

| 时间 | 动作 | 证据锚点 |
| --- | --- | --- |
| 0:00-0:30 | 打开一页纸，讲问题、方法和核心数字 | `docs/challenge_cup/00_项目一页纸.md` |
| 0:30-1:20 | 展示检索或离线截图，证明系统不是静态材料 | `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` |
| 1:20-2:10 | 打开 KG artifact 或证据矩阵，证明 GraphRAG 价值在关系证据组织 | `docs/challenge_cup/07_评审主张证据矩阵.md` |
| 2:10-2:40 | 展示 readiness gate，证明可复核而非口头承诺 | `docs/challenge_cup/reproducibility/readiness_gate_report.md` |
| 2:40-3:00 | 主动讲边界和下一步，避免被动防守 | `docs/challenge_cup/08_特等奖评审自评表.md` |

## 杀手问题

| 追问 | 推荐回答 | 立即引用 |
| --- | --- | --- |
| 你们和普通 RAG 的本质差异是什么？ | 普通 RAG 解决片段召回，项目额外把部件、故障、参数和措施关系显式化，并要求 KG 三元组绑定 evidence。 | `docs/challenge_cup/02_技术白皮书.md`; `docs/challenge_cup/07_评审主张证据矩阵.md` |
| GraphRAG 是否全面优于 keyword / hybrid？ | 不做绝对化结论。它在跨实体关系和全局归纳问题上更有价值，评测报告保留 baseline 和失败归因。 | `docs/challenge_cup/03_实验评测报告.md`; `evaluation/reports/challenge_cup_graphrag_same_question_report.md` |
| 数据是否足以支撑生产级运维？ | 当前支撑结项、课程资料知识化和可复核演示，不宣称生产级闭环；高风险运维决策必须人工确认。 | `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/08_特等奖评审自评表.md` |
| 现场服务挂了怎么办？ | 不现场排环境，切到离线证据包：browser smoke、截图、KG artifact、readiness gate 和专家审阅索引。 | `docs/challenge_cup/04_系统演示脚本.md`; `docs/challenge_cup/09_专家快速审阅索引.md` |
| 为什么能冲击特等奖？ | 不是靠页面包装，而是靠真实资料处理、知识工程闭环、科学评测、失败归因、可复现门禁和清晰边界。 | `docs/challenge_cup/08_特等奖评审自评表.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` |

## 不可夸大边界

- 不说“已经替代工程师”。
- 不说“GraphRAG 对所有问题都更强”。
- 不说“当前数据已经覆盖真实生产全场景”。
- 不把 readiness gate 说成获奖保证；它只证明交付包和演示证据可复核。

## 彩排通过标准

- 90秒开场不超时，且必须讲到问题、方法、完成度和边界。
- 三分钟演示节奏完整跑完，现场失败时能在 20 秒内切换到离线证据包。
- 每个杀手问题至少能在 30 秒内给出一句结论和一个证据锚点。
- 彩排后复核 `docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md`，确认没有把 readiness gate 说成获奖保证。
- 彩排计时结果只写入 `docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md`，真实记录完成前不得提前宣称通过。
- 彩排结束后运行：

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
```
"""


def build_application_validation_doc(ctx: dict[str, Any]) -> str:
    validation = ctx["validation"]
    return f"""# 应用场景与专家验证

本材料把项目的“实用性”从概念描述压实为可复核的固定应用场景。当前版本使用现有公开演示快照和角色化审查，不伪造外部生产签字；正式参赛前可把本页作为老师、行业专家或实验室同学反馈的记录表继续补签。

## 固定应用场景

| 场景 | 人工原流程 | 系统辅助后流程 | 验证角色 | 量化收益 | 证据 |
| --- | --- | --- | --- | --- | --- |
| 燃气轮机异常振动诊断证据整理 | 人工在手册、故障样例、维护理论材料中分别查阈值、故障机理、案例现象、检修措施和复机结果，容易漏掉来源记录。 | 输入“{validation["query"]}”，系统在演示集合中返回阈值、机理、GT-07 现象、停机检查、处理建议五类证据，并保留 record id。 | 课程项目评审、动力装备资料审阅者、答辩评委 | `{validation["search_meta"]}`；从 2,655 个向量片段、约 1,185,989 tokens 中一次返回 5 条证据，形成“阈值判断 -> 故障机理 -> 案例现象 -> 检修措施 -> 复机结果”的审计链。 | `docs/challenge_cup/reproducibility/application_validation_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.json`; `{validation["screenshot"]}` |
| 挑战杯现场答辩复核 | 评委需要在有限时间内确认项目是否只是静态展示。 | 先看本页，再打开固定案例报告和 browser smoke 截图，快速核验问题、证据、边界和复现命令。 | 答辩评委、指导教师 | 3-5 分钟内可定位应用场景、证据来源和边界声明，降低口头陈述不可复核风险。 | `docs/challenge_cup/07_评审主张证据矩阵.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` |

## 边界声明

- 本项目是证据型辅助，不替代工程师做最终运维或维修决策。
- 当前验证使用公开演示快照和 4 本 OCR 质量较稳定的燃气轮机材料，不代表覆盖真实生产全场景。
- Browser smoke 证明本地演示与关键资源可用，不等同于生产压测或上线验收。
- 不声称 RAG / GraphRAG 对所有问题都优于人工或其他检索方法；高风险维修必须人工确认。

## 下一步专家反馈采集

1. 让指导教师或行业背景同学按固定场景独立复核一次，记录其是否能在 5 分钟内找到关键证据。
2. 将反馈分为“证据链完整”“术语解释清楚”“边界是否严谨”“仍需补充数据”四项。
3. 若获得真实签字或邮件反馈，将扫描件或摘要加入 `docs/challenge_cup/reproducibility/application_validation_report.md`，并重新运行 readiness gate。
"""


def build_application_validation_report(ctx: dict[str, Any]) -> str:
    validation = ctx["validation"]
    return f"""# 应用验证报告

## 固定案例

- 案例名称：燃气轮机异常振动诊断证据链。
- 输入问题：{validation["query"]}。
- 演示集合：gas_turbine_ocr_demo_snapshot。
- 检索结果：{validation["search_meta"]}。
- 复核入口：`docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`；`docs/challenge_cup/reproducibility/browser_demo_smoke_report.json`；`{validation["screenshot"]}`。

## 证据链

| 步骤 | record | 证据作用 | 人工判断 |
| --- | --- | --- | --- |
| 阈值判断 | `demo-maint-thresholds-076` | 给出排气温度散布度、轴承振动、滑油金属颗粒、压气机效率衰减等关键监测阈值。 | 作为异常振动和早期故障诊断线索，不能单独构成停机决策。 |
| 故障机理 | `demo-structure-fault-130` | 说明结构强度故障与不正常振动、停机风险之间的关系。 | 用于解释为什么振动异常需要结合机械损伤风险审查。 |
| 案例现象 | `demo-gt07-fault-021` | GT-07 升负荷至 75% 后，压气机出口温度从 430°C 升至 485°C，振动传感器 VIB-CMP-01 到 7.2 mm/s，并触发“压气机出口温度偏高”报警。 | 现象层证据，提示压气机出口温度偏高和振动异常需要联合分析。 |
| 检修结果 | `demo-gt07-repair-022` | 停机检查发现进气滤网压差偏高、滤网局部堵塞、压气机前三级叶片积灰；清理进气滤网、安排压气机叶片离线清洗并复位温度传感器后，温度回落至 438°C，振动值降至 3.1 mm/s。 | 形成“原因 -> 措施 -> 复机结果”的闭环证据。 |
| 处置建议 | `demo-gt07-manual-023` | 给出压气机出口温度偏高的常见原因：进气阻力增大、压气机叶片污染和温度传感器漂移；建议检查进气滤网、清洗压气机叶片、校验温度传感器。 | 可作为检修清单草案，必须由工程师结合现场工况人工确认。 |

## 半量化收益

- 系统在演示快照中从 2,655 个向量片段、约 1,185,989 tokens 中返回 5 条证据结果，检索延迟为 42.10 ms。
- 人工原流程需要分别查找阈值、故障机理、案例现象、检修结果和处置建议；系统辅助后把这五类证据组织到同一页结果中。
- 对结项和挑战杯答辩的价值是：评委可以沿 record id 复核证据链，避免只听“系统能诊断”的口头承诺。

## 边界结论

本案例证明系统能辅助完成异常振动诊断的证据整理和来源追溯，但不证明它可以替代工程师做最终维修决策。GT-07 案例中的进气滤网、压气机叶片和温度传感器判断仍必须结合真实现场数据、设备规程和人工确认。
"""


def build_expert_feedback_protocol(ctx: dict[str, Any]) -> str:
    return """# 专家反馈采集与整改闭环

本页用于把外部意见采集变成可审计流程。当前反馈采集状态为：待真实反馈归档。未收到真实签字、邮件或会议纪要前，不伪造外部意见，不宣称项目已经通过专家验证。

## 反馈采集状态

| 项目 | 当前状态 | 归档规则 |
| --- | --- | --- |
| 指导教师反馈 | 待真实反馈归档 | 使用 `docs/challenge_cup/reproducibility/expert_feedback_form.md`，附签字页、邮件截图或会议纪要。 |
| 行业或实验室同学反馈 | 待真实反馈归档 | 记录单位或角色、联系方式、评审日期、评审问题和整改建议。 |
| 固定应用场景复核 | 已准备固定材料 | 复核 `docs/challenge_cup/reproducibility/application_validation_report.md` 与固定查询证据链。 |
| readiness 复核 | 已有机器门禁 | 反馈归档后重新运行 `docs/challenge_cup/reproducibility/readiness_gate_report.md` 对应命令。 |

## 专家反馈采集表

- 表单入口：`docs/challenge_cup/reproducibility/expert_feedback_form.md`。
- 评审对象：项目一页纸、固定场景演示、应用验证报告、readiness gate、浏览器截图。
- 核心问题：实用性是否成立、证据链是否可信、边界是否严谨、哪些材料仍需补充。

## 整改闭环

| 步骤 | 动作 | 可审计证据 |
| --- | --- | --- |
| 1 | 发出反馈表和固定场景材料 | 邮件、聊天记录或会议邀请截图。 |
| 2 | 收到反馈后摘录关键意见 | 签字页、邮件回复、会议纪要或反馈表原件。 |
| 3 | 将意见拆成整改项 | 在本页追加“意见-整改-证据”表。 |
| 4 | 完成整改后重跑 gate | `python scripts/build_challenge_cup_package.py`；`python scripts/check_challenge_cup_readiness.py`。 |

## 诚信边界

- 不伪造外部意见，不把内部自评写成专家背书。
- 不把“已准备采集协议”说成“已获得专家认可”。
- 真实反馈如果提出否定意见，必须保留并进入整改闭环。
"""


def build_expert_feedback_form(ctx: dict[str, Any]) -> str:
    return """# 专家反馈采集表

## 评审人信息

- 评审人姓名：
- 单位或角色：
- 联系方式：
- 评审日期：
- 签字或邮件证据：

## 评审材料

| 材料 | 路径 | 复核要点 |
| --- | --- | --- |
| 项目一页纸 | `docs/challenge_cup/00_项目一页纸.md` | 问题、方法、数字和边界是否清楚。 |
| 固定场景演示 | `docs/challenge_cup/04_系统演示脚本.md` | 是否能按 3 分钟节奏讲清证据链。 |
| 应用验证报告 | `docs/challenge_cup/reproducibility/application_validation_report.md` | `燃气轮机异常振动诊断流程` 是否能支撑应用价值。 |
| 浏览器证据 | `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md` | 5 条记录是否可复核，含 `demo-gt07-repair-022`。 |
| readiness gate | `docs/challenge_cup/reproducibility/readiness_gate_report.md` | 机器门禁是否证明包完整性和边界。 |

## 评分表

| 维度 | 评分 | 证据或意见 |
| --- | --- | --- |
| 实用性 |  |  |
| 创新性 |  |  |
| 工程完成度 |  |  |
| 评测可信度 |  |  |
| 答辩可讲清程度 |  |  |

## 整改建议

| 问题 | 严重度 | 建议 | 需补证据 |
| --- | --- | --- | --- |
|  |  |  |  |

## 归档路径

反馈原件、签字页、邮件截图或会议纪要应归档到挑战杯证据包，并在 `docs/challenge_cup/12_专家反馈采集与整改闭环.md` 追加整改记录。未归档真实证据前，不得宣称已经获得专家认可。
"""


def build_runbook(ctx: dict[str, Any]) -> str:
    return """# 可复现运行手册

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q
.\.venv\Scripts\python.exe -m pytest api_server/current_console/chroma_rag_poc/tests -q
```

## 扩展评测集

```powershell
.\.venv\Scripts\python.exe scripts/extend_challenge_cup_eval_questions.py
```

## 运行现场演示烟测

```powershell
.\.venv\Scripts\python.exe scripts/run_challenge_cup_live_demo_smoke.py
node scripts/run_challenge_cup_browser_demo_smoke.mjs
```

## 重新生成 Day3 baseline

```powershell
.\.venv\Scripts\python.exe scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5
```

## 重新生成 Day4 失败分析

```powershell
.\.venv\Scripts\python.exe scripts/analyze_day4_failure_cases.py
```

## 重新生成挑战杯成果包

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_package.py
```

## 刷新终审答辩 PPT

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_defense_deck.py --force
```

## 刷新官方评审口径对齐表

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_official_rubric_alignment.py
```

## 归档真实硬证据

收到真实专家反馈附件后运行：

```powershell
.\.venv\Scripts\python.exe scripts/record_challenge_cup_hard_evidence.py expert_feedback --id advisor-a --source <真实专家反馈附件路径> --evidence-type email_reply --reviewer-identity advisor-a --role-or-org advisor --review-date 2026-06-06 --review-dimension 实用性 --review-dimension 创新性 --review-dimension 边界严谨性 --remediation-issue 演示节奏 --remediation-action 压缩开场
```

完成真实计时彩排后，首选用测得秒数生成观察员记录并归档：

```powershell
.\.venv\Scripts\python.exe scripts/run_challenge_cup_timed_rehearsal.py --id rehearsal-1 --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal
```

如果已有真实计时截图、录屏或观察员笔记附件，也可以直接归档：

```powershell
.\.venv\Scripts\python.exe scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <真实计时记录附件路径> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29
```

## 刷新硬证据台账

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_hard_evidence_ledger.py
```

## 运行结项 readiness gate

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
```

## 运行总目标完成门禁

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_goal_completion.py
```

当前缺少真实专家反馈和真实计时彩排时，该门禁应返回 fail；这不是包生成失败，而是防止把 package readiness 误写成总目标已完成。
"""


def build_hard_evidence_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## 硬证据台账",
            "",
            f"- 硬证据台账：`{md_link(HARD_EVIDENCE_LEDGER_MD)}`",
            f"- 硬证据 JSON：`{md_link(HARD_EVIDENCE_LEDGER_JSON)}`",
            f"- 硬证据归档入口：`{md_link(HARD_EVIDENCE_README)}`",
            f"- 真实专家反馈归档入口：`{md_link(HARD_EVIDENCE_EXPERT_README)}`",
            f"- 真实计时彩排归档入口：`{md_link(HARD_EVIDENCE_REHEARSAL_README)}`",
        ]
    )


def build_official_rubric_dataset_manifest_section() -> str:
    return "\n".join(
        [
            "",
            "## 官方评审口径对齐",
            "",
            f"- 官方评审口径对齐表：`{md_link(OFFICIAL_RUBRIC_ALIGNMENT_MD)}`",
            f"- 官方评审口径 JSON：`{md_link(OFFICIAL_RUBRIC_ALIGNMENT_JSON)}`",
        ]
    )


def build_dataset_manifest(ctx: dict[str, Any]) -> str:
    return f"""# 数据集与证据清单

- 系统评测集：`evaluation/system_eval_questions.jsonl`，{ctx["question_count"]} 题。
- 评测覆盖画像：`{md_link(EVAL_COVERAGE_PROFILE)}`。
- 普通 RAG 数据库说明：`{md_link(ctx["rag_db"])}`。
- 知识图谱人工评审：`{md_link(ctx["kg_review"])}`。
- Day3 baseline：`{optional_md_link(ctx["day3"])}`。
- Day4 失败分析：`{optional_md_link(ctx["day4"])}`。
- GraphRAG 同题子集：`{optional_md_link(ctx["graph_report"])}`。
- GraphRAG 同题 JSON：`{optional_md_link(ctx["graph_report_json"])}`。
- GraphRAG context-only demo：`{optional_md_link(ctx["graph_context_demo_md"])}`。
- GraphRAG context-only JSON：`{optional_md_link(ctx["graph_context_demo_json"])}`。
- GraphRAG answer benchmark：`{optional_md_link(ctx["graph_answer_benchmark_md"])}`。
- GraphRAG answer benchmark JSON：`{optional_md_link(ctx["graph_answer_benchmark_json"])}`。
- GraphRAG 补证整改计划：`{optional_md_link(ctx["graph_gap_remediation_md"])}`。
- GraphRAG 补证整改 JSON：`{optional_md_link(ctx["graph_gap_remediation_json"])}`。
- GraphRAG manual evidence supplement：`{md_link(GRAPH_MANUAL_EVIDENCE_SUPPLEMENT)}`。
- 评审主张证据矩阵：`{md_link(CLAIM_MATRIX)}`。
- 特等奖评审自评表：`{md_link(AWARD_SELF_EVAL)}`。
- 专家快速审阅索引：`{md_link(EXPERT_REVIEW_INDEX)}`。
- 答辩攻防与彩排卡：`{md_link(DEFENSE_REHEARSAL_CARD)}`。
- 终审答辩 PPTX：`{md_link(DEFENSE_DECK_PPTX)}`。
- 终审答辩讲稿：`{md_link(DEFENSE_DECK_NOTES)}`。
- 答辩彩排计分卡：`{md_link(DEFENSE_REHEARSAL_SCORECARD_MD)}`。
- 答辩彩排计分 JSON：`{md_link(DEFENSE_REHEARSAL_SCORECARD_JSON)}`。
- 答辩计时彩排结果归档包：`{md_link(DEFENSE_REHEARSAL_RESULT_PACKET_MD)}`。
- 答辩计时彩排结果 JSON：`{md_link(DEFENSE_REHEARSAL_RESULT_PACKET_JSON)}`。
- 专家反馈外发包：`{md_link(EXPERT_FEEDBACK_REQUEST_PACKET_MD)}`。
- 专家反馈外发 JSON：`{md_link(EXPERT_FEEDBACK_REQUEST_PACKET_JSON)}`。
- 应用场景与专家验证：`{md_link(APPLICATION_VALIDATION_DOC)}`。
- 应用验证报告：`{md_link(APPLICATION_VALIDATION_REPORT)}`。
- 专家反馈采集与整改闭环：`{md_link(EXPERT_FEEDBACK_PROTOCOL)}`。
- 专家反馈采集表：`{md_link(EXPERT_FEEDBACK_FORM)}`。
- 现场演示烟测：`{md_link(LIVE_SMOKE_REPORT)}`。
- 真实浏览器演示烟测：`{md_link(BROWSER_SMOKE_REPORT)}`。
- 真实浏览器烟测 JSON：`{md_link(BROWSER_SMOKE_JSON)}`。
- 结项 readiness gate：`{md_link(READINESS_GATE_REPORT)}`。
- 总目标完成门禁：`{md_link(GOAL_COMPLETION_REPORT)}`。
- 证据完整性哈希：`{md_link(EVIDENCE_HASHES)}`。
- 可提交归档包：`{md_link(SUBMISSION_ARCHIVE)}`。
- 可提交归档包哈希清单：`{md_link(SUBMISSION_ARCHIVE_MANIFEST)}`。
- 浏览器验收截图：`{md_link(BROWSER_SCREENSHOT_DIR)}/`。
- 浏览器桌面总览截图：`{md_link(BROWSER_SCREENSHOTS[0])}`。
- 浏览器桌面检索截图：`{md_link(BROWSER_SCREENSHOTS[1])}`。
- 浏览器 KG 产物截图：`{md_link(BROWSER_SCREENSHOTS[2])}`。
- 浏览器移动端截图：`{md_link(BROWSER_SCREENSHOTS[3])}`。
- 课程最终交付包：`{md_link(ctx["course_pack"])}`。
"""


def build_command_log(ctx: dict[str, Any]) -> str:
    return f"""# 命令记录

生成时间：{ctx["now"]}

## 2026-06-05 本轮验证记录

```text
python scripts/extend_challenge_cup_eval_questions.py
-> Wrote 60 questions to evaluation/system_eval_questions.jsonl

python scripts/build_challenge_cup_package.py
-> Wrote docs/challenge_cup with 60 evaluation questions
-> docs/challenge_cup/defense_deck/challenge_cup_defense_deck.pptx
-> docs/challenge_cup/defense_deck/challenge_cup_defense_speaker_notes.md
-> docs/challenge_cup/11_应用场景与专家验证.md
-> docs/challenge_cup/12_专家反馈采集与整改闭环.md
-> docs/challenge_cup/reproducibility/application_validation_report.md
-> docs/challenge_cup/reproducibility/expert_feedback_form.md
-> docs/challenge_cup/reproducibility/evaluation_coverage_profile.json
-> docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip
-> docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json

python scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5
-> Corpus chunks: 6494
-> evaluation/reports/day3_retrieval_baseline_comparison_20260605_210540.md

python scripts/analyze_day4_failure_cases.py
-> evaluation/reports/day4_failure_analysis_20260605_210642.md
-> Analyzed cases: 40

python -m pytest tests/unit -q
-> 86 passed

python -m pytest api_server/current_console/chroma_rag_poc/tests -q
-> 21 passed

python scripts/run_challenge_cup_live_demo_smoke.py
-> docs/challenge_cup/reproducibility/live_demo_smoke_report.md
-> Status: pass (5/5 checks)

python -m unittest tests/unit/test_console_import_compat.py
-> OK

python -m unittest tests/unit/test_frontend_demo_mode_contract.py
-> OK

python -m unittest api_server/current_console/chroma_rag_poc/tests/test_pipeline.py -k test_frontend_libs_and_assets_are_served_from_root_paths
-> OK

python -m unittest api_server/current_console/chroma_rag_poc/tests/test_pipeline.py -k test_deliverable_assets_are_served_from_stable_root_path
-> OK

python scripts/build_graphrag_context_demo.py
-> evaluation/reports/challenge_cup_graphrag_context_demo.md
-> evaluation/reports/challenge_cup_graphrag_context_demo.json

python scripts/build_graphrag_answer_benchmark.py
-> evaluation/reports/challenge_cup_graphrag_answer_benchmark.md
-> evaluation/reports/challenge_cup_graphrag_answer_benchmark.json

python scripts/build_graphrag_gap_remediation_plan.py
-> evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.md
-> evaluation/reports/challenge_cup_graphrag_gap_remediation_plan.json

python scripts/build_defense_rehearsal_scorecard.py
-> docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.md
-> docs/challenge_cup/reproducibility/defense_rehearsal_scorecard.json

python scripts/build_defense_rehearsal_result_packet.py
-> docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.md
-> docs/challenge_cup/reproducibility/defense_rehearsal_result_packet.json

python scripts/build_expert_feedback_request_packet.py
-> docs/challenge_cup/reproducibility/expert_feedback_request_packet.md
-> docs/challenge_cup/reproducibility/expert_feedback_request_packet.json

python scripts/build_challenge_cup_official_rubric_alignment.py
-> docs/challenge_cup/reproducibility/official_rubric_alignment.md
-> docs/challenge_cup/reproducibility/official_rubric_alignment.json

python scripts/build_challenge_cup_hard_evidence_ledger.py
-> docs/challenge_cup/reproducibility/hard_evidence_ledger.md
-> docs/challenge_cup/reproducibility/hard_evidence_ledger.json

node scripts/run_challenge_cup_browser_demo_smoke.mjs
-> docs/challenge_cup/reproducibility/browser_demo_smoke_report.md
-> docs/challenge_cup/reproducibility/browser_demo_smoke_report.json
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_overview.png
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png
-> docs/challenge_cup/reproducibility/browser_screenshots/mobile_overview.png
-> Status: pass (13/13 checks)

python scripts/check_challenge_cup_readiness.py
-> docs/challenge_cup/reproducibility/readiness_gate_report.md
-> Status: pass (30/30 gates)

python scripts/check_challenge_cup_goal_completion.py
-> docs/challenge_cup/reproducibility/goal_completion_report.md
-> Status: fail (awaiting real expert feedback and timed rehearsal)
```

推荐复现命令见 `runbook.md`。重新运行后，以新的终端输出和报告时间戳为准。
"""


def main() -> int:
    ctx = build_context()
    write(OUT / "README_先看这里.md", build_readme(ctx))
    write(OUT / "00_项目一页纸.md", build_one_page(ctx))
    write(OUT / "01_挑战杯项目书.md", build_project_book(ctx))
    write(OUT / "02_技术白皮书.md", build_whitepaper(ctx))
    write(OUT / "03_实验评测报告.md", build_eval_report(ctx))
    write(OUT / "04_系统演示脚本.md", build_demo_script(ctx))
    write(OUT / "05_答辩问答手册.md", build_qa(ctx))
    write(ACCEPTANCE_CHECKLIST, build_checklist(ctx))
    write(CLAIM_MATRIX, build_claim_evidence_matrix(ctx))
    write(AWARD_SELF_EVAL, build_award_self_eval(ctx))
    write(EXPERT_REVIEW_INDEX, build_expert_review_index(ctx))
    write(DEFENSE_REHEARSAL_CARD, build_defense_rehearsal_card(ctx))
    write(APPLICATION_VALIDATION_DOC, build_application_validation_doc(ctx))
    write(EXPERT_FEEDBACK_PROTOCOL, build_expert_feedback_protocol(ctx))
    write(APPLICATION_VALIDATION_REPORT, build_application_validation_report(ctx))
    write(EXPERT_FEEDBACK_FORM, build_expert_feedback_form(ctx))
    write_defense_scorecard_outputs(build_defense_scorecard_payload())
    write_defense_result_outputs(build_defense_result_payload())
    write_expert_request_outputs(build_expert_request_payload())
    write_official_rubric_alignment_outputs()
    hard_evidence_payload = write_hard_evidence_ledger_outputs()
    graph_answer_payload = build_graph_answer_benchmark_payload()
    write(GRAPH_ANSWER_BENCHMARK_JSON, json.dumps(graph_answer_payload, ensure_ascii=False, indent=2))
    write_graph_answer_benchmark_markdown(GRAPH_ANSWER_BENCHMARK_MD, graph_answer_payload)
    graph_gap_payload = build_graph_gap_remediation_payload()
    write(GRAPH_GAP_REMEDIATION_JSON, json.dumps(graph_gap_payload, ensure_ascii=False, indent=2))
    write_graph_gap_remediation_markdown(GRAPH_GAP_REMEDIATION_MD, graph_gap_payload)
    write(REPRO / "runbook.md", build_runbook(ctx))
    write(
        REPRO / "dataset_manifest.md",
        build_dataset_manifest(ctx) + build_official_rubric_dataset_manifest_section() + build_hard_evidence_dataset_manifest_section(),
    )
    write(EVAL_COVERAGE_PROFILE, json.dumps(build_evaluation_coverage_profile(ctx), ensure_ascii=False, indent=2))
    write(REPRO / "command_log.md", build_command_log(ctx))
    build_defense_deck_outputs()
    write_goal_completion_report(REPO_ROOT)
    evidence_files = [
        md_link(DATASET),
        md_link(DEFENSE_DECK_PPTX),
        md_link(DEFENSE_DECK_NOTES),
        md_link(ACCEPTANCE_CHECKLIST),
        md_link(CLAIM_MATRIX),
        md_link(AWARD_SELF_EVAL),
        md_link(EXPERT_REVIEW_INDEX),
        md_link(DEFENSE_REHEARSAL_CARD),
        md_link(DEFENSE_REHEARSAL_SCORECARD_MD),
        md_link(DEFENSE_REHEARSAL_SCORECARD_JSON),
        md_link(DEFENSE_REHEARSAL_RESULT_PACKET_MD),
        md_link(DEFENSE_REHEARSAL_RESULT_PACKET_JSON),
        md_link(EXPERT_FEEDBACK_REQUEST_PACKET_MD),
        md_link(EXPERT_FEEDBACK_REQUEST_PACKET_JSON),
        md_link(OFFICIAL_RUBRIC_ALIGNMENT_MD),
        md_link(OFFICIAL_RUBRIC_ALIGNMENT_JSON),
        md_link(HARD_EVIDENCE_LEDGER_MD),
        md_link(HARD_EVIDENCE_LEDGER_JSON),
        md_link(HARD_EVIDENCE_README),
        md_link(HARD_EVIDENCE_EXPERT_README),
        md_link(HARD_EVIDENCE_REHEARSAL_README),
        *hard_evidence_payload.get("raw_evidence_files", []),
        md_link(APPLICATION_VALIDATION_DOC),
        md_link(EXPERT_FEEDBACK_PROTOCOL),
        md_link(APPLICATION_VALIDATION_REPORT),
        md_link(EXPERT_FEEDBACK_FORM),
        md_link(GRAPH_MANUAL_EVIDENCE_SUPPLEMENT),
        md_link(LIVE_SMOKE_REPORT),
        md_link(BROWSER_SMOKE_REPORT),
        md_link(BROWSER_SMOKE_JSON),
        md_link(READINESS_GATE_REPORT),
        md_link(GOAL_COMPLETION_REPORT),
        *(md_link(path) for path in BROWSER_SCREENSHOTS),
        *(
            md_link(path)
            for path in (
                ctx["day3"],
                ctx["day4"],
                ctx["graph_report"],
                ctx["graph_report_json"],
                ctx["graph_context_demo_md"],
                ctx["graph_context_demo_json"],
                GRAPH_ANSWER_BENCHMARK_MD,
                GRAPH_ANSWER_BENCHMARK_JSON,
                GRAPH_GAP_REMEDIATION_MD,
                GRAPH_GAP_REMEDIATION_JSON,
            )
            if path is not None
        ),
    ]
    manifest = {
        "generated_at": ctx["now"],
        "output_dir": md_link(OUT),
        "question_count": ctx["question_count"],
        "evaluation_coverage_profile": md_link(EVAL_COVERAGE_PROFILE),
        "evidence_files": evidence_files,
        "integrity_manifest": md_link(EVIDENCE_HASHES),
        "submission_archive": md_link(SUBMISSION_ARCHIVE),
        "submission_archive_manifest": md_link(SUBMISSION_ARCHIVE_MANIFEST),
    }
    write(OUT / "package_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    excluded_self_reports = [md_link(READINESS_GATE_REPORT)]
    hash_payload = {
        "algorithm": "sha256",
        "generated_at": ctx["now"],
        "excluded_self_reports": excluded_self_reports,
        "files": [
            {
                "path": relative,
                "bytes": (REPO_ROOT / relative).stat().st_size,
                "sha256": sha256_file(REPO_ROOT / relative),
            }
            for relative in sorted(path for path in evidence_files if path not in excluded_self_reports)
        ],
    }
    write(EVIDENCE_HASHES, json.dumps(hash_payload, ensure_ascii=False, indent=2))
    archive_inputs = build_submission_archive_inputs(evidence_files)
    write_submission_archive(ctx, archive_inputs)
    print(f"Wrote docs/challenge_cup with {ctx['question_count']} evaluation questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
