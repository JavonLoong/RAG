from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = Path(
    r"C:\Users\15410\.codex\plugins\cache\openai-primary-runtime\presentations\26.601.10930\skills\presentations"
)
REPORT_DIR = REPO_ROOT / "evaluation" / "reports"
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
OUTPUT_DIR = REPO_ROOT / "docs" / "project_deliverables" / "06_汇报材料_发群和组会"
THREAD_ID = os.environ.get("CODEX_THREAD_ID") or "manual-20260605-rag-report"
WORKSPACE = REPO_ROOT / "outputs" / THREAD_ID / "presentations" / "rag-academic-report"
SLIDES_DIR = WORKSPACE / "slides"
PREVIEW_DIR = WORKSPACE / "preview"
LAYOUT_DIR = WORKSPACE / "layout"
QA_DIR = WORKSPACE / "qa"

FINAL_PPTX = OUTPUT_DIR / "RAG课程汇报_第五天材料.pptx"
SPEAKER_NOTES = OUTPUT_DIR / "第五天PPT讲稿.md"
MATERIALS_README = OUTPUT_DIR / "第五天PPT素材说明.md"


def latest(pattern: str) -> Path:
    candidates = sorted(REPORT_DIR.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"No report found for pattern: {pattern}")
    return candidates[-1]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def count_jsonl(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def pct(value: float) -> str:
    return f"{value:.3f}"


def build_data() -> dict[str, Any]:
    day3_path = latest("day3_retrieval_baseline_comparison_*.json")
    day4_path = latest("day4_failure_analysis_*.json")
    day3 = read_json(day3_path)
    day4 = read_json(day4_path)
    summaries = {item["method"]: item for item in day3["summaries"]}
    best = max(day3["summaries"], key=lambda item: item["avg_retrieval_keyword_coverage"] or 0)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "day3_path": str(day3_path),
        "day4_path": str(day4_path),
        "question_count": count_jsonl(DATASET),
        "day3": day3,
        "day4": day4,
        "summaries": summaries,
        "best": best,
        "category_counts": day4["category_counts"],
    }


COMMON_MJS = r"""
export const C = {
  ink: "#172033",
  sub: "#566176",
  quiet: "#7A8496",
  paper: "#F7F8FA",
  line: "#D7DCE5",
  blue: "#2457A6",
  cyan: "#1897A6",
  green: "#2F7D59",
  amber: "#B7791F",
  red: "#B54747",
  navy: "#10243F",
  white: "#FFFFFF",
  paleBlue: "#EAF1FB",
  paleGreen: "#EAF6EF",
  paleAmber: "#FFF4DA",
  paleRed: "#FBEAEA",
};

export function bg(slide, ctx, color = C.paper) {
  ctx.addShape(slide, { x: 0, y: 0, w: 1280, h: 720, fill: color, line: ctx.line("#00000000", 0) });
}

export function footer(slide, ctx, n) {
  ctx.addText(slide, { text: "Power Equipment RAG · academic report",
    x: 54, y: 682, w: 520, h: 20, fontSize: 12, color: C.quiet, typeface: "Aptos",
  });
  ctx.addText(slide, { text: String(n).padStart(2, "0"),
    x: 1200, y: 680, w: 40, h: 22, fontSize: 12, color: C.quiet, align: "right", typeface: "Aptos",
  });
}

export function title(slide, ctx, kicker, claim, n) {
  ctx.addText(slide, { text: kicker.toUpperCase(),
    x: 54, y: 34, w: 360, h: 24, fontSize: 12, bold: true, color: C.cyan, typeface: "Aptos",
  });
  ctx.addText(slide, { text: claim,
    x: 54, y: 62, w: 980, h: 58, fontSize: 30, bold: true, color: C.ink, typeface: "Microsoft YaHei",
  });
  ctx.addShape(slide, { x: 54, y: 128, w: 1160, h: 1, fill: C.line, line: ctx.line("#00000000", 0) });
  footer(slide, ctx, n);
}

export function label(slide, ctx, text, x, y, w, h, opts = {}) {
  ctx.addText(slide, { text,
    x, y, w, h,
    fontSize: opts.size ?? 16,
    bold: opts.bold ?? false,
    color: opts.color ?? C.ink,
    typeface: opts.face ?? "Microsoft YaHei",
    align: opts.align ?? "left",
    valign: opts.valign ?? "top",
    insets: opts.insets ?? { left: 0, right: 0, top: 0, bottom: 0 },
  });
}

export function box(slide, ctx, x, y, w, h, fill = C.white, line = C.line) {
  return ctx.addShape(slide, { x, y, w, h, fill, line: ctx.line(line, 1) });
}

export function metric(slide, ctx, value, name, x, y, color = C.blue) {
  ctx.addText(slide, { text: value, x, y, w: 130, h: 38, fontSize: 30, bold: true, color, typeface: "Aptos Display" });
  ctx.addText(slide, { text: name, x, y: y + 42, w: 150, h: 36, fontSize: 13, color: C.sub, typeface: "Microsoft YaHei" });
}

export function bar(slide, ctx, labelText, value, max, x, y, w, color, suffix = "") {
  const display = Number.isFinite(value) && Math.abs(value) < 10
    ? String(Number(value.toFixed(3))).replace(/\.0$/, "")
    : String(value);
  label(slide, ctx, labelText, x, y - 2, 180, 24, { size: 14, color: C.sub });
  ctx.addShape(slide, { x: x + 190, y, w, h: 18, fill: "#E6EAF0", line: ctx.line("#00000000", 0) });
  ctx.addShape(slide, { x: x + 190, y, w: Math.max(4, w * value / max), h: 18, fill: color, line: ctx.line("#00000000", 0) });
  label(slide, ctx, `${display}${suffix}`, x + 200 + w, y - 3, 90, 24, { size: 14, bold: true, color });
}

export function stage(slide, ctx, index, text, x, y, w, h, fill) {
  box(slide, ctx, x, y, w, h, fill, "#C9D2DF");
  ctx.addText(slide, { text: String(index), x: x + 14, y: y + 14, w: 32, h: 30, fontSize: 18, bold: true, color: C.blue, typeface: "Aptos" });
  label(slide, ctx, text, x + 52, y + 14, w - 66, h - 24, { size: 15, bold: true, color: C.ink });
}

export function smallNote(slide, ctx, text, x, y, w, h) {
  label(slide, ctx, text, x, y, w, h, { size: 13, color: C.sub });
}
"""


def slide_module(number: int, body: str) -> str:
    return dedent(
        f"""
        import {{ C, bg, title, footer, label, box, metric, bar, stage, smallNote }} from "./common.mjs";

        export async function slide{number:02d}(presentation, ctx) {{
          const slide = presentation.slides.add();
        {body}
          return slide;
        }}
        """
    )


def slide_modules(data: dict[str, Any]) -> dict[str, str]:
    best = data["best"]
    keyword = data["summaries"]["keyword"]
    dense = data["summaries"]["dense_hashing"]
    hybrid = data["summaries"]["hybrid_rrf"]
    counts = data["category_counts"]

    category_rows = [
        ("evaluation_concept_gap", counts.get("evaluation_concept_gap", 0), "评测术语源不集中"),
        ("hybrid_dilution", counts.get("hybrid_dilution", 0), "弱 hashing 稀释排序"),
        ("structured_fact_routing", counts.get("structured_fact_routing", 0), "结构化事实未路由"),
        ("partial_ranking_gap", counts.get("partial_ranking_gap", 0), "Top-K 排序/粒度不足"),
        ("terminology_alias_gap", counts.get("terminology_alias_gap", 0), "术语别名未扩展"),
        ("exact_number_fact", counts.get("exact_number_fact", 0), "精确数字事实需短卡片"),
    ]

    return {
        "slide-01.mjs": slide_module(
            1,
            f"""
              bg(slide, ctx, C.navy);
              label(slide, ctx, "动力装备 RAG / GraphRAG 阶段汇报", 70, 86, 860, 70, {{ size: 38, bold: true, color: C.white }});
              label(slide, ctx, "从 Python 课程项目，到可评测、可复现、可解释的检索增强系统", 72, 166, 900, 42, {{ size: 20, color: "#C8D3E4" }});
              ctx.addShape(slide, {{ x: 70, y: 260, w: 1080, h: 1, fill: "#38506F", line: ctx.line("#00000000", 0) }});
              metric(slide, ctx, "14", "资料输入 PDF/JSON", 76, 302, "#76D6E2");
              metric(slide, ctx, "13", "扫描 PDF 已 OCR", 270, 302, "#A9E3BF");
              metric(slide, ctx, "60", "系统评测问题", 464, 302, "#F5C56B");
              metric(slide, ctx, "6494", "离线评测 chunks", 658, 302, "#9CC3FF");
              metric(slide, ctx, "{pct(best['question_recall_at_k'])}", "最佳 question recall@K", 872, 302, "#FFFFFF");
              label(slide, ctx, "第五天产物：架构图 · 实验表 · 成功/失败案例 · 可编辑 PPTX", 72, 595, 980, 32, {{ size: 18, color: "#DCE6F6" }});
              footer(slide, ctx, 1);
            """,
        ),
        "slide-02.mjs": slide_module(
            2,
            """
              bg(slide, ctx);
              title(slide, ctx, "Research question", "汇报重点不是“能不能问答”，而是系统是否可被评估", 2);
              label(slide, ctx, "课程作业常见风险", 76, 170, 300, 32, { size: 18, bold: true, color: C.red });
              label(slide, ctx, "只演示一个问答页面，缺少数据规模、检索证据、失败分析和复现实验。", 76, 208, 310, 92, { size: 17, color: C.ink });
              label(slide, ctx, "本项目转化目标", 476, 170, 300, 32, { size: 18, bold: true, color: C.green });
              label(slide, ctx, "把真实资料、OCR、RAG、Graph POC 与评测脚本连接成一条可解释链路。", 476, 208, 330, 92, { size: 17, color: C.ink });
              label(slide, ctx, "学术汇报标准", 876, 170, 300, 32, { size: 18, bold: true, color: C.blue });
              label(slide, ctx, "问题定义、方法设计、实验指标、成功样例、失败原因、下一步优化。", 876, 208, 320, 92, { size: 17, color: C.ink });
              stage(slide, ctx, 1, "真实资料进入系统", 104, 382, 220, 82, C.white);
              stage(slide, ctx, 2, "检索链路跑通", 386, 382, 220, 82, C.white);
              stage(slide, ctx, 3, "60 题评测集", 668, 382, 220, 82, C.white);
              stage(slide, ctx, 4, "失败案例归因", 950, 382, 220, 82, C.white);
              ctx.addShape(slide, { x: 330, y: 420, w: 48, h: 4, fill: C.cyan, line: ctx.line("#00000000", 0) });
              ctx.addShape(slide, { x: 612, y: 420, w: 48, h: 4, fill: C.cyan, line: ctx.line("#00000000", 0) });
              ctx.addShape(slide, { x: 894, y: 420, w: 48, h: 4, fill: C.cyan, line: ctx.line("#00000000", 0) });
            """,
        ),
        "slide-03.mjs": slide_module(
            3,
            """
              bg(slide, ctx);
              title(slide, ctx, "Data pipeline", "数据链路已经从资料导入扩展到评测语料", 3);
              stage(slide, ctx, 1, "14 本资料 + 问答 JSON", 70, 176, 190, 78, C.paleBlue);
              stage(slide, ctx, 2, "13 本扫描 PDF OCR", 292, 176, 190, 78, C.paleGreen);
              stage(slide, ctx, 3, "OCR 清洗与 chunk", 514, 176, 190, 78, C.paleAmber);
              stage(slide, ctx, 4, "普通 RAG / Graph POC", 736, 176, 210, 78, C.white);
              stage(slide, ctx, 5, "60 题系统评测", 978, 176, 190, 78, C.white);
              for (const x of [266, 488, 710, 952]) ctx.addShape(slide, { x, y: 214, w: 22, h: 4, fill: C.cyan, line: ctx.line("#00000000", 0) });
              label(slide, ctx, "OCR 审计证据", 92, 340, 260, 28, { size: 18, bold: true });
              metric(slide, ctx, "5483", "OCR 页数", 96, 384, C.blue);
              metric(slide, ctx, "5472", "有文字页", 272, 384, C.green);
              metric(slide, ctx, "0", "运行错误数", 448, 384, C.amber);
              label(slide, ctx, "评测语料证据", 720, 340, 260, 28, { size: 18, bold: true });
              metric(slide, ctx, "6494", "离线 chunks", 724, 384, C.blue);
              metric(slide, ctx, "60", "评测问题", 900, 384, C.green);
              metric(slide, ctx, "8", "题型分组", 1076, 384, C.amber);
              smallNote(slide, ctx, "注：当前第五天 PPT 使用本地 OCR 文本、工程报告和 Graph POC 材料构建离线评测 corpus。", 74, 594, 1040, 44);
            """,
        ),
        "slide-04.mjs": slide_module(
            4,
            """
              bg(slide, ctx);
              title(slide, ctx, "System architecture", "系统采用普通 RAG 与 GraphRAG 双线并行架构", 4);
              label(slide, ctx, "离线构建", 84, 164, 160, 26, { size: 17, bold: true, color: C.blue });
              label(slide, ctx, "在线检索", 84, 394, 160, 26, { size: 17, bold: true, color: C.green });
              box(slide, ctx, 190, 156, 980, 140, C.paleBlue, "#BFD1EA");
              label(slide, ctx, "Standard RAG", 214, 178, 180, 24, { size: 18, bold: true, color: C.blue });
              stage(slide, ctx, 1, "PDF / OCR / JSON", 220, 220, 170, 52, C.white);
              stage(slide, ctx, 2, "clean + chunk", 430, 220, 170, 52, C.white);
              stage(slide, ctx, 3, "BM25 / vector", 640, 220, 170, 52, C.white);
              stage(slide, ctx, 4, "Top-K evidence", 850, 220, 170, 52, C.white);
              box(slide, ctx, 190, 342, 980, 140, C.paleGreen, "#B9DBC7");
              label(slide, ctx, "KG / GraphRAG", 214, 364, 180, 24, { size: 18, bold: true, color: C.green });
              stage(slide, ctx, 1, "Label Studio JSON", 220, 406, 170, 52, C.white);
              stage(slide, ctx, 2, "schema triples", 430, 406, 170, 52, C.white);
              stage(slide, ctx, 3, "evidence review", 640, 406, 170, 52, C.white);
              stage(slide, ctx, 4, "community/global", 850, 406, 170, 52, C.white);
              box(slide, ctx, 266, 542, 820, 54, "#F0F3F8", "#C9D2DF");
              label(slide, ctx, "Shared infrastructure: model adapters · evaluation runner · reports · local console", 294, 558, 760, 28, { size: 17, bold: true, color: C.ink });
            """,
        ),
        "slide-05.mjs": slide_module(
            5,
            """
              bg(slide, ctx);
              title(slide, ctx, "Evaluation design", "60 题评测集覆盖事实、流程、OCR 风险和 GraphRAG", 5);
              const rows = [
                ["基础系统评测 se001-se030", 30, C.blue],
                ["挑战杯扩展 cc031-cc060", 30, C.green],
                ["GraphRAG 同题子集", 10, C.red],
                ["graph context/global 题", 10, C.cyan],
              ];
              let y = 174;
              for (const [name, value, color] of rows) {
                bar(slide, ctx, name, value, 30, 90, y, 420, color, " 题");
                y += 72;
              }
              box(slide, ctx, 760, 174, 350, 286, C.white, C.line);
              label(slide, ctx, "每题包含", 790, 204, 240, 28, { size: 20, bold: true });
              label(slide, ctx, "question · reference_answer · expected_evidence_keywords · task_type · source_scope · grading_notes", 790, 248, 280, 128, { size: 17, color: C.ink });
              label(slide, ctx, "评分口径", 790, 402, 240, 28, { size: 20, bold: true });
              label(slide, ctx, "先看检索证据覆盖，再看回答是否忠实。", 790, 442, 278, 50, { size: 17, color: C.sub });
              smallNote(slide, ctx, "这页回答老师最关心的问题：不是随便问几个问题，而是有分组、有标准答案、有证据关键词。", 88, 612, 980, 34);
            """,
        ),
        "slide-06.mjs": slide_module(
            6,
            f"""
              bg(slide, ctx);
              title(slide, ctx, "Baseline results", "专业术语场景下，keyword baseline 暂时强于 hashing 向量", 6);
              label(slide, ctx, "Question recall@K", 88, 166, 300, 26, {{ size: 19, bold: true }});
              bar(slide, ctx, "keyword", {keyword['question_recall_at_k']}, 1, 98, 218, 420, C.blue);
              bar(slide, ctx, "dense_hashing", {dense['question_recall_at_k']}, 1, 98, 276, 420, C.cyan);
              bar(slide, ctx, "hybrid_rrf", {hybrid['question_recall_at_k']}, 1, 98, 334, 420, C.green);
              label(slide, ctx, "Avg keyword coverage", 88, 438, 300, 26, {{ size: 19, bold: true }});
              bar(slide, ctx, "keyword", {keyword['avg_retrieval_keyword_coverage']}, 1, 98, 490, 420, C.blue);
              bar(slide, ctx, "dense_hashing", {dense['avg_retrieval_keyword_coverage']}, 1, 98, 548, 420, C.cyan);
              bar(slide, ctx, "hybrid_rrf", {hybrid['avg_retrieval_keyword_coverage']}, 1, 98, 606, 420, C.green);
              box(slide, ctx, 790, 202, 330, 220, C.white, C.line);
              label(slide, ctx, "汇报结论", 820, 232, 240, 28, {{ size: 20, bold: true, color: C.blue }});
              label(slide, ctx, "当前 hashing embedding 只是离线可复现 baseline，不代表最终语义检索质量。专业词汇和报告编号更依赖关键词召回。", 820, 276, 258, 118, {{ size: 17, color: C.ink }});
              metric(slide, ctx, "{keyword['strong_questions']}", "keyword 强命中题", 802, 474, C.blue);
              metric(slide, ctx, "{keyword['missed_questions']}", "keyword 未命中题", 1000, 474, C.red);
            """,
        ),
        "slide-07.mjs": slide_module(
            7,
            """
              bg(slide, ctx);
              title(slide, ctx, "Case diagnostics", "成功、弱命中和失败案例共同说明系统边界", 7);
              box(slide, ctx, 70, 170, 330, 370, C.paleGreen, "#B9DBC7");
              label(slide, ctx, "成功案例", 96, 196, 220, 28, { size: 21, bold: true, color: C.green });
              label(slide, ctx, "se001 联合循环效率\\nse002 压气机作用\\nse004 涡轮输出机械功", 96, 246, 260, 118, { size: 18, color: C.ink });
              label(slide, ctx, "说明：基础领域事实可以从 OCR 书籍中召回可用证据。", 96, 416, 260, 78, { size: 16, color: C.sub });
              box(slide, ctx, 465, 170, 330, 370, C.paleAmber, "#E6CC91");
              label(slide, ctx, "弱命中案例", 491, 196, 220, 28, { size: 21, bold: true, color: C.amber });
              label(slide, ctx, "se003 燃烧室功能\\nse010 维修报告证据片段\\nse021 schema 约束", 491, 246, 260, 118, { size: 18, color: C.ink });
              label(slide, ctx, "说明：Top-K 有相关片段，但关键词覆盖不完整，需要调 chunk 和 reranker。", 491, 416, 260, 78, { size: 16, color: C.sub });
              box(slide, ctx, 860, 170, 330, 370, C.paleRed, "#E1B7B7");
              label(slide, ctx, "失败案例", 886, 196, 220, 28, { size: 21, bold: true, color: C.red });
              label(slide, ctx, "se013 Reranker 术语\\nse024 POC 数字事实\\nse027 Goldwind 数据规模", 886, 246, 260, 118, { size: 18, color: C.ink });
              label(slide, ctx, "说明：别名、精确数字和结构化字段需要专门索引或事实卡片。", 886, 416, 260, 78, { size: 16, color: C.sub });
            """,
        ),
        "slide-08.mjs": slide_module(
            8,
            f"""
              bg(slide, ctx);
              title(slide, ctx, "Failure analysis", "{data['day4']['analyzed_question_count']} 个弱/失败案例被归为 6 类可操作优化项", 8);
              const rows = {js(category_rows)};
              let y = 174;
              for (const [cat, count, note] of rows) {{
                bar(slide, ctx, cat, count, 5, 74, y, 420, count >= 4 ? C.red : count >= 2 ? C.amber : C.blue, "");
                label(slide, ctx, note, 770, y - 2, 330, 26, {{ size: 15, color: C.sub }});
                y += 58;
              }}
              box(slide, ctx, 740, 504, 390, 94, C.white, C.line);
              label(slide, ctx, "下一步不是堆功能，而是修检索假设", 770, 526, 320, 26, {{ size: 18, bold: true, color: C.ink }});
              label(slide, ctx, "同义词扩展 · 事实卡片 · source_scope 路由 · 更好的 embedding/reranker", 770, 560, 320, 34, {{ size: 15, color: C.sub }});
            """,
        ),
        "slide-09.mjs": slide_module(
            9,
            """
              bg(slide, ctx);
              title(slide, ctx, "Live demo plan", "现场演示只走一条稳定链路，再展示 Graph POC 证据", 9);
              stage(slide, ctx, 1, "打开成果总览：说明资料规模与入口", 94, 174, 480, 66, C.white);
              stage(slide, ctx, 2, "展示 60 题评测集：说明不是随机提问", 94, 260, 480, 66, C.white);
              stage(slide, ctx, 3, "展示第三天 baseline 表：keyword / dense / hybrid", 94, 346, 480, 66, C.white);
              stage(slide, ctx, 4, "展示一个成功案例和一个失败案例", 94, 432, 480, 66, C.white);
              stage(slide, ctx, 5, "打开 Graph POC：schema / 三元组 / evidence / 人工评审", 94, 518, 480, 66, C.white);
              box(slide, ctx, 720, 190, 360, 240, C.paleBlue, "#BFD1EA");
              label(slide, ctx, "备用策略", 748, 222, 240, 28, { size: 21, bold: true, color: C.blue });
              label(slide, ctx, "如果现场系统启动不稳定，直接展示已生成的 Markdown 报告、PPT 表格和 Graph POC SVG/HTML。", 748, 272, 280, 96, { size: 18, color: C.ink });
              box(slide, ctx, 720, 468, 360, 88, C.white, C.line);
              label(slide, ctx, "演示原则：少讲技术名词，多讲证据链和评测结论。", 748, 492, 300, 38, { size: 18, bold: true, color: C.ink });
            """,
        ),
        "slide-10.mjs": slide_module(
            10,
            """
              bg(slide, ctx, "#F4F6F9");
              title(slide, ctx, "Final week plan", "剩余时间聚焦可汇报质量，而不是临时扩功能", 10);
              stage(slide, ctx, 6, "第六天：PPT 排练、截图、失败案例讲稿", 102, 190, 320, 92, C.white);
              stage(slide, ctx, 7, "第七天：现场演示检查、备用文件、时间控制", 486, 190, 320, 92, C.white);
              stage(slide, ctx, 8, "汇报后：替换真实 embedding、接入 reranker、补结构化事实路由", 870, 190, 320, 92, C.white);
              label(slide, ctx, "最终可交付", 110, 386, 240, 30, { size: 22, bold: true, color: C.blue });
              label(slide, ctx, "1. 可编辑 PPTX\\n2. 60 题评测集\\n3. baseline 对比报告\\n4. 失败案例分析\\n5. Graph POC 证据链", 112, 438, 360, 150, { size: 20, color: C.ink });
              label(slide, ctx, "核心收束", 676, 386, 240, 30, { size: 22, bold: true, color: C.green });
              label(slide, ctx, "这个项目的价值不是“会调用大模型”，而是把动力装备资料处理、检索、图谱化和评测组织成了一个可以继续研究的工程实验系统。", 676, 438, 420, 116, { size: 20, color: C.ink });
            """,
        ),
    }


def write_planning_files(data: dict[str, Any]) -> None:
    write(
        WORKSPACE / "profile-plan.txt",
        f"""
        task mode: create
        primary deck-profile: engineering-platform
        secondary gates: academic reporting, evaluation narrative
        required proof objects: architecture map, data pipeline, evaluation taxonomy, baseline chart, failure category table, demo workflow
        source requirements: use local project reports only; no external metrics
        brand constraints: no fabricated logos; use neutral technical visual system
        QA gates: claims must point to data or diagram; diagrams must preserve technical labels; rendered text must not overlap
        known missing inputs: no class template deck was provided
        """,
    )
    write(
        WORKSPACE / "source-notes.txt",
        f"""
        Sources used:
        - {data['day3_path']}
        - {data['day4_path']}
        - evaluation/system_eval_questions.jsonl
        - docs/project_deliverables/06_汇报材料_发群和组会/60题评测集说明.md
        - docs/project_deliverables/06_汇报材料_发群和组会/第三天检索评测结果.md
        - docs/project_deliverables/06_汇报材料_发群和组会/第四天失败案例分析.md

        Identity assets: none. The deck uses editable geometric proof objects only.
        """,
    )
    write(
        WORKSPACE / "claim-spine.txt",
        """
        1. The project has moved from demo to evaluated RAG system.
        2. The research question is whether retrieval evidence can be evaluated and explained.
        3. The data pipeline is large enough to support a real report, not just a toy example.
        4. The system architecture has two tracks: Standard RAG and KG/GraphRAG.
        5. The 60-question evaluation set gives a reproducible grading surface.
        6. Current baseline results show keyword retrieval is strongest under offline hashing constraints.
        7. Case diagnostics expose useful boundaries instead of hiding failures.
        8. Failure categories translate directly into optimization work.
        9. The live demo should emphasize evidence chain and POC review.
        10. The final week plan protects presentation quality and future research direction.
        """,
    )
    write(
        WORKSPACE / "contact-sheet-plan.txt",
        """
        Slide rhythm:
        1 cover with metric rail
        2 research question and evidence chain
        3 data pipeline map with metrics
        4 two-lane architecture diagram
        5 evaluation taxonomy bar proof
        6 baseline results bar proof with side conclusion
        7 success/partial/failure diagnostic comparison
        8 failure category bar proof
        9 live demo sequence with fallback rail
        10 final week plan and deliverable list
        """,
    )


def write_slide_modules(data: dict[str, Any]) -> None:
    SLIDES_DIR.mkdir(parents=True, exist_ok=True)
    write(SLIDES_DIR / "common.mjs", COMMON_MJS)
    for filename, content in slide_modules(data).items():
        write(SLIDES_DIR / filename, content)


def build_deck() -> None:
    env = os.environ.copy()
    env["HOME"] = r"C:\Users\15410"
    env["PYTHON"] = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
    command = [
        "node",
        str(SKILL_DIR / "scripts" / "build_artifact_deck.mjs"),
        "--workspace",
        str(WORKSPACE),
        "--slides-dir",
        str(SLIDES_DIR),
        "--out",
        str(FINAL_PPTX),
        "--preview-dir",
        str(PREVIEW_DIR),
        "--layout-dir",
        str(LAYOUT_DIR / "final"),
        "--contact-sheet",
        str(PREVIEW_DIR / "contact-sheet.png"),
        "--slide-count",
        "10",
    ]
    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True)


def write_speaker_notes(data: dict[str, Any]) -> None:
    best = data["best"]
    notes = f"""
    # 第五天 PPT 讲稿

    ## 1. 封面
    这次汇报的重点是：我把 Python 课程项目从一个 RAG demo，整理成了一个可评测、可复现、可解释的动力装备 RAG/GraphRAG 系统。当前有 14 本资料、13 本 OCR、60 题评测集和 6494 个离线评测 chunk。

    ## 2. 研究问题
    我不是只证明“系统能回答”，而是证明它能不能被评估。学术汇报需要讲问题定义、方法设计、实验指标、成功案例和失败原因。

    ## 3. 数据链路
    数据链路从资料输入开始，经过 OCR、清洗、chunk、普通 RAG 和 Graph POC，最后接入 60 题评测集。

    ## 4. 系统架构
    当前架构是双线：普通 RAG 负责文本检索和证据召回，GraphRAG/知识图谱线负责 schema、三元组、evidence 和人工评审。

    ## 5. 评测设计
    60 题不是随机提问，而是覆盖普通事实题、流程题、OCR 风险、GraphRAG、结构化数据和评测方法。每题都有标准答案和预期证据关键词。

    ## 6. Baseline 结果
    当前最佳 baseline 是 `{best['method']}`，question recall@K 为 {best['question_recall_at_k']:.6f}，平均关键词覆盖率为 {best['avg_retrieval_keyword_coverage']:.6f}。这说明在专业术语场景下，关键词检索仍然很强；hashing embedding 只是离线可复现 baseline。

    ## 7. 案例诊断
    成功案例说明基础领域知识可以被召回；弱命中说明 Top-K 证据不完整；失败案例说明术语别名、精确数字和结构化字段需要专门处理。

    ## 8. 失败原因
    失败不是简单的“系统不行”，而是可以归因到六类：评测概念源不集中、弱 hashing 稀释、结构化事实未路由、排序/粒度不足、术语别名缺失和精确数字事实缺失。

    ## 9. 现场演示
    演示只走一条稳定链路：成果总览、60 题评测、baseline 表、一个成功案例、一个失败案例、Graph POC evidence。

    ## 10. 收束
    最终强调：这个项目的价值不是会调用大模型，而是把动力装备资料处理、检索、图谱化和评测组织成了可以继续研究的工程实验系统。
    """
    write(SPEAKER_NOTES, dedent(notes))


def write_materials_readme(data: dict[str, Any]) -> None:
    readme = f"""
    # 第五天 PPT 素材说明

    ## 生成文件

    - PPTX：`{FINAL_PPTX}`
    - 讲稿：`{SPEAKER_NOTES}`
    - 构建 workspace：`{WORKSPACE}`
    - 预览 contact sheet：`{PREVIEW_DIR / 'contact-sheet.png'}`

    ## 数据来源

    - 第三天检索 baseline：`{data['day3_path']}`
    - 第四天失败分析：`{data['day4_path']}`
    - 60 题评测集：`evaluation/system_eval_questions.jsonl`

    ## 使用口径

    这份 PPT 适合 8-12 分钟课程汇报。建议现场只演示一条主链路，不要临时展开所有代码。
    """
    write(MATERIALS_README, dedent(readme))


def main() -> int:
    data = build_data()
    for directory in (WORKSPACE, SLIDES_DIR, PREVIEW_DIR, LAYOUT_DIR, QA_DIR, OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    write_planning_files(data)
    write_slide_modules(data)
    build_deck()
    write_speaker_notes(data)
    write_materials_readme(data)
    print(f"Wrote PPTX: {FINAL_PPTX}")
    print(f"Wrote speaker notes: {SPEAKER_NOTES}")
    print(f"Wrote materials README: {MATERIALS_README}")
    print(f"Workspace: {WORKSPACE}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
