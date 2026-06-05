from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DELIVERABLE_DIR = REPO_ROOT / "docs" / "project_deliverables" / "06_汇报材料_发群和组会"
REPORT_DIR = REPO_ROOT / "evaluation" / "reports"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest(pattern: str) -> Path:
    matches = sorted(REPORT_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"No report matched {pattern}")
    return matches[0]


def count_jsonl(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def as_rel(path: Path | str) -> str:
    raw = Path(path)
    try:
        return str(raw.relative_to(REPO_ROOT))
    except ValueError:
        return str(raw)


def fmt_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def retrieval_summary(report: dict[str, Any]) -> dict[str, Any]:
    retrieval = report["metrics"]["retrieval"]
    results = report["results"]
    strong = 0
    weak = 0
    missed = 0
    for item in results:
        coverage = item.get("retrieval_keyword_coverage") or 0.0
        if coverage >= 0.75:
            strong += 1
        elif coverage > 0:
            weak += 1
        else:
            missed += 1
    return {
        "question_recall_at_k": retrieval["question_recall_at_k"],
        "avg_keyword_coverage": retrieval["average_keyword_coverage"],
        "strong": strong,
        "weak": weak,
        "missed": missed,
    }


def method_rows(reports: dict[str, dict[str, Any]]) -> list[str]:
    rows = [
        "| 方法 | question recall@K | avg keyword coverage | strong | weak | missed |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in ("keyword", "dense_hashing", "hybrid_rrf"):
        data = retrieval_summary(reports[name])
        rows.append(
            "| "
            + " | ".join(
                [
                    name,
                    fmt_metric(data["question_recall_at_k"]),
                    fmt_metric(data["avg_keyword_coverage"]),
                    str(data["strong"]),
                    str(data["weak"]),
                    str(data["missed"]),
                ]
            )
            + " |"
        )
    return rows


def build_context() -> dict[str, Any]:
    day3 = {
        "keyword": read_json(latest("system_eval_day3_keyword_*.json")),
        "dense_hashing": read_json(latest("system_eval_day3_dense_hashing_*.json")),
        "hybrid_rrf": read_json(latest("system_eval_day3_hybrid_rrf_*.json")),
    }
    day4_path = latest("day4_failure_analysis_*.json")
    day4 = read_json(day4_path)
    manifest = read_json(DELIVERABLE_DIR / "artifact-build-manifest.json")
    questions_path = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "question_count": count_jsonl(questions_path),
        "day3": day3,
        "day3_comparison_md": latest("day3_retrieval_baseline_comparison_*.md"),
        "day4_path": day4_path,
        "day4_analysis_md": latest("day4_failure_analysis_*.md"),
        "day4": day4,
        "manifest": manifest,
        "questions_path": questions_path,
    }


def write_demo_script(ctx: dict[str, Any]) -> Path:
    path = DELIVERABLE_DIR / "第六天现场演示脚本.md"
    keyword = retrieval_summary(ctx["day3"]["keyword"])
    hybrid = retrieval_summary(ctx["day3"]["hybrid_rrf"])
    contact_sheet = ctx["manifest"].get("contactSheet", "")
    lines = [
        "# 第六天现场演示脚本",
        "",
        f"生成时间：{ctx['generated_at']}",
        "",
        "## 演示目标",
        "",
        "现场只证明三件事：资料已经进入工程链路、检索质量可以被量化、失败案例能反向指导下一轮优化。不要把当前系统说成完整商业级 GraphRAG，也不要承诺真实 LLM 答案已经稳定。",
        "",
        "## 5 分钟主线",
        "",
        "1. 打开 PPT：`docs/project_deliverables/06_汇报材料_发群和组会/RAG课程汇报_第五天材料.pptx`。",
        f"2. 第 1 页先报数字：14 本资料、13 本 OCR、{ctx['question_count']} 题评测集、6494 个离线评测 chunk。",
        "3. 第 3-4 页讲链路：PDF/OCR/JSON 进入普通 RAG 与 KG/GraphRAG 两条线。",
        "4. 第 5 页讲评测集：不是随机问答，而是覆盖事实、流程、OCR 风险、GraphRAG、结构化数据和评测方法。",
        f"5. 第 6 页讲 baseline：keyword question recall@K={keyword['question_recall_at_k']:.3f}，hybrid_rrf question recall@K={hybrid['question_recall_at_k']:.3f}。",
        "6. 第 7-8 页讲失败案例：弱项不是隐藏起来，而是按失败类型归因，形成优化任务。",
        "7. 第 9 页演示现场路线：先展示评测报告，再展示一个成功案例、一个失败案例，最后打开 Graph POC 证据页面。",
        "8. 第 10 页收束：最后一周重点是可汇报质量，不是临时堆功能。",
        "",
        "## 现场打开顺序",
        "",
        "| 顺序 | 打开什么 | 讲什么 | 失败时怎么切换 |",
        "| ---: | --- | --- | --- |",
        "| 1 | PPTX | 汇报总线和核心指标 | 用 `第五天PPT讲稿.md` 逐页讲 |",
        f"| 2 | `{as_rel(ctx['day3_comparison_md'])}` | 三种检索 baseline 的量化对比 | 用 PPT 第 6 页截图讲 |",
        f"| 3 | `{as_rel(ctx['day4_analysis_md'])}` | 弱/失败案例的归因 | 用 `第四天失败案例分析.md` 讲 |",
        "| 4 | `docs/project_deliverables/05_知识图谱POC_三元组和人工判断/三元组审核页面.html` | evidence 与人工评审闭环 | 用 `docs/project_deliverables/05_知识图谱POC_三元组和人工判断/知识图谱图片.svg` 或 PPT 第 9 页讲 |",
        "| 5 | `api_server/current_console/start_local.bat` | 本地控制台入口 | 若服务没起，说明已准备静态前端与离线材料 |",
        "",
        "## 可直接念的开场",
        "",
        f"我这次不是只做一个能问答的页面，而是把动力装备资料接进 Python 工程链路，做到了资料导入、OCR 清洗、RAG 检索、知识图谱 POC、{ctx['question_count']} 题评测和失败案例分析。当前最有价值的结果不是模型回答多漂亮，而是系统可以被复现、被评测、被解释。",
        "",
        "## 可直接念的结尾",
        "",
        f"目前 keyword baseline 在专业术语场景下表现最好，说明这批资料的检索瓶颈不只是大模型，而是术语、证据片段和排序策略。下一步我会把失败案例转成 source scope、embedding/reranker 和结构化事实路由三类优化任务，再用同一套 {ctx['question_count']} 题评测集复测。",
        "",
        "## 预览图",
        "",
        f"- PPT contact sheet：`{contact_sheet}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_evidence_pack(ctx: dict[str, Any]) -> Path:
    path = DELIVERABLE_DIR / "第六天演示备用证据包.md"
    rows = method_rows(ctx["day3"])
    day4_counts = ctx["day4"]["category_counts"]
    failure_rows = [
        "| 类别 | 数量 | 现场解释 |",
        "| --- | ---: | --- |",
    ]
    explanations = {
        "evaluation_concept_gap": "评测概念在语料中覆盖不足，需要补项目文档或解释性材料。",
        "hybrid_dilution": "混合检索并非必然更好，融合后可能稀释强关键词命中。",
        "structured_fact_routing": "精确数量和结构化事实需要专门路由，不适合只靠普通文本召回。",
        "partial_ranking_gap": "证据存在但排序靠后，需要 reranker 或更细 chunk。",
        "terminology_alias_gap": "术语别名没有统一，需补同义词和领域词表。",
        "exact_number_fact": "数字事实必须保留来源和精确匹配策略。",
    }
    for key, value in day4_counts.items():
        failure_rows.append(f"| {key} | {value} | {explanations.get(key, '作为下一轮优化任务处理。')} |")

    lines = [
        "# 第六天演示备用证据包",
        "",
        f"生成时间：{ctx['generated_at']}",
        "",
        "## A. 核心证据文件",
        "",
        "| 用途 | 文件 | 说明 |",
        "| --- | --- | --- |",
        f"| {ctx['question_count']} 题评测集 | `{as_rel(ctx['questions_path'])}` | 当前共 {ctx['question_count']} 题，覆盖事实、流程、OCR、GraphRAG 和评测方法 |",
        f"| baseline 对比 | `{as_rel(ctx['day3_comparison_md'])}` | 三种检索策略的统一评测结果 |",
        f"| 失败案例 JSON | `{as_rel(ctx['day4_path'])}` | 失败分类和案例归因的机器可读结果 |",
        "| 失败案例说明 | `docs/project_deliverables/06_汇报材料_发群和组会/第四天失败案例分析.md` | 给汇报用的人话版本 |",
        "| PPTX | `docs/project_deliverables/06_汇报材料_发群和组会/RAG课程汇报_第五天材料.pptx` | 10 页可编辑汇报稿 |",
        "| PPT 讲稿 | `docs/project_deliverables/06_汇报材料_发群和组会/第五天PPT讲稿.md` | 逐页讲述口径 |",
        "",
        "## B. baseline 指标",
        "",
        *rows,
        "",
        "现场解释：keyword 暂时最好，说明专业资料里显式术语、字段名、报告词很关键；dense_hashing 是离线确定性 baseline，不代表最终 embedding 上限；hybrid_rrf 没有超过 keyword，说明融合策略还需要结合 reranker 和查询类型路由。",
        "",
        "## C. 失败归因",
        "",
        *failure_rows,
        "",
        f"现场解释：这 {len(ctx['day4'].get('cases', []))} 个弱/失败案例不是项目失败，而是评测系统暴露出的下一轮优化入口。学术汇报里要把失败案例作为 evidence，而不是回避。",
        "",
        "## D. 本地演示命令",
        "",
        "```powershell",
        "cd \"D:\\虚拟C盘\\RAG\\api_server\\current_console\"",
        "$env:PYTHONPATH=\"$PWD\\chroma_rag_poc\\src\"",
        "python server.py",
        "```",
        "",
        "启动后访问：`http://localhost:8000`。如果端口占用或依赖缺失，改用 PPT、评测报告和 HTML/SVG 静态证据讲完整链路。",
        "",
        "## E. 不能说过头的话",
        "",
        "- 不说完整 GraphRAG 已经最终完成。",
        "- 不说 Neo4j 已经实际跑通，因为当前主要是 SQLite 图存储和 Neo4j Cypher 文件。",
        "- 不说真实 LLM 答案已经稳定，因为没有把 `OPENAI_API_KEY` 作为现场依赖。",
        f"- 不说 {ctx['question_count']} 题评测代表最终论文级 benchmark，只说它是课程项目阶段的可复现评测集。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_qa_checklist(ctx: dict[str, Any]) -> Path:
    path = DELIVERABLE_DIR / "第六天答辩口径与检查清单.md"
    slide_count = ctx["manifest"].get("slideCount", "unknown")
    ppt_size = ctx["manifest"].get("outputBytes", "unknown")
    lines = [
        "# 第六天答辩口径与检查清单",
        "",
        f"生成时间：{ctx['generated_at']}",
        "",
        "## 答辩高频问题",
        "",
        "### 1. 你这个和普通聊天机器人有什么区别？",
        "",
        "它不是直接把问题丢给模型，而是先做资料处理、OCR、chunk、检索、证据召回和评测。回答是否可靠，要看检索证据是否覆盖标准答案关键词。",
        "",
        "### 2. 为什么 keyword 比 dense_hashing 好？",
        "",
        "因为当前资料是燃气轮机、维修报告和知识图谱 POC 这类强术语文本，显式关键词很重要。dense_hashing 只是离线可复现的 dense-style baseline，不代表接入正式 embedding 后的最终效果。",
        "",
        "### 3. hybrid 为什么没有显著超过 keyword？",
        "",
        "混合检索不是简单相加就一定更好。当前失败分析里有 `hybrid_dilution`，说明融合后可能把关键词强命中的证据排低，后续需要按问题类型路由和 reranker。",
        "",
        "### 4. GraphRAG 做到什么程度？",
        "",
        "当前已经有 KG construction、schema、三元组、evidence、人工评审、SQLite 图存储和 context-only 编排。还不能说完整 GraphRAG 最终问答系统已经完成。",
        "",
        "### 5. 这个项目的学术性在哪里？",
        "",
        f"学术性不在页面好看，而在问题定义、可复现数据链路、baseline 对比、失败案例归因和边界说明。当前汇报已经有 {ctx['question_count']} 题评测集、三类 baseline 和失败分类。",
        "",
        "### 6. 最后还要优化什么？",
        "",
        f"优先做三件事：扩大 source scope，替换正式 embedding 或 reranker，给精确数字和结构化事实加路由。每项优化都用同一套 {ctx['question_count']} 题评测复测。",
        "",
        "## 上台前 10 分钟检查",
        "",
        "- PPTX 能打开。",
        f"- PPTX 页数是 {slide_count} 页，文件大小约 {ppt_size} bytes。",
        "- `第五天PPT讲稿.md` 能打开，必要时可以照稿讲。",
        f"- `{as_rel(ctx['day3_comparison_md'])}` 能打开。",
        f"- `{as_rel(ctx['day4_analysis_md'])}` 或 `第四天失败案例分析.md` 能打开。",
        "- Graph POC 的 HTML/SVG 能打开；如果不能打开，用 PPT 第 9 页讲。",
        "- 如果本地服务无法启动，不现场排查环境，把演示切到离线证据包。",
        "",
        "## 现场时间控制",
        "",
        "| 时长 | 内容 | 目标 |",
        "| ---: | --- | --- |",
        "| 30 秒 | 一句话介绍项目 | 让老师知道不是普通 demo |",
        "| 90 秒 | 数据链路和系统架构 | 证明工程闭环 |",
        f"| 90 秒 | {ctx['question_count']} 题评测和 baseline | 证明可评测 |",
        "| 60 秒 | 失败案例分析 | 证明知道系统边界 |",
        "| 60 秒 | Graph POC / evidence | 证明 GraphRAG 方向有实物 |",
        "| 30 秒 | 后续优化 | 收束到可执行计划 |",
        "",
        "## 最稳妥的一句话",
        "",
        "这个项目当前最重要的价值是：把动力装备资料从原始 PDF/OCR 推进到了可检索、可评测、可解释、可继续优化的 RAG/GraphRAG 工程链路。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    DELIVERABLE_DIR.mkdir(parents=True, exist_ok=True)
    ctx = build_context()
    outputs = [
        write_demo_script(ctx),
        write_evidence_pack(ctx),
        write_qa_checklist(ctx),
    ]
    manifest = {
        "generated_at": ctx["generated_at"],
        "outputs": [str(path) for path in outputs],
        "question_count": ctx["question_count"],
        "ppt_slide_count": ctx["manifest"].get("slideCount"),
        "ppt_output_bytes": ctx["manifest"].get("outputBytes"),
        "day4_case_count": len(ctx["day4"].get("cases", [])),
    }
    manifest_path = DELIVERABLE_DIR / "第六天演示包_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
