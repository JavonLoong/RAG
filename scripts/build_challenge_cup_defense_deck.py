from __future__ import annotations

import json
import os
import subprocess
import sys
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
BUNDLED_NODE = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
BUNDLED_NODE_MODULES = (
    Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "node_modules"
)
OUTPUT_DIR = REPO_ROOT / "docs" / "challenge_cup" / "defense_deck"
FINAL_PPTX = OUTPUT_DIR / "challenge_cup_defense_deck.pptx"
SPEAKER_NOTES = OUTPUT_DIR / "challenge_cup_defense_speaker_notes.md"
THREAD_ID = os.environ.get("CODEX_THREAD_ID") or "manual-20260606-challenge-cup-defense"
WORKSPACE = REPO_ROOT / "outputs" / THREAD_ID / "presentations" / "challenge-cup-defense-deck"
SLIDES_DIR = WORKSPACE / "slides"
PREVIEW_DIR = WORKSPACE / "preview"
LAYOUT_DIR = WORKSPACE / "layout"
REPORTS = REPO_ROOT / "evaluation" / "reports"
PACKAGE = REPO_ROOT / "docs" / "challenge_cup"
REPRO = PACKAGE / "reproducibility"
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def asset_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def count_jsonl(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def latest(pattern: str) -> Path | None:
    candidates = sorted(REPORTS.glob(pattern))
    return candidates[-1] if candidates else None


def readiness_summary() -> str:
    report = REPRO / "readiness_gate_report.md"
    if not report.exists():
        return "readiness gate 已配置，待本轮重新运行"
    return "readiness gate 已纳入材料、证据、归档和答辩门禁"


def build_data() -> dict[str, Any]:
    coverage = load_json(REPRO / "evaluation_coverage_profile.json")
    graph_gap = load_json(REPORTS / "challenge_cup_graphrag_gap_remediation_plan.json")
    archive_manifest = REPRO / "challenge_cup_submission_archive_manifest.json"
    archive = load_json(archive_manifest) if archive_manifest.exists() else {"file_count": 0, "bytes": 0}
    browser = load_json(REPRO / "browser_demo_smoke_report.json").get("browser", {})
    return {
        "question_count": count_jsonl(DATASET),
        "task_type_count": len(coverage.get("task_type_counts", {})),
        "source_scope_count": len(coverage.get("source_scope_counts", {})),
        "graphrag_questions": coverage.get("questions_with_graphrag_modes", 0),
        "readiness": readiness_summary(),
        "archive_file_count": archive.get("file_count", 0),
        "archive_bytes": archive.get("bytes", 0),
        "graph_remaining_tasks": graph_gap.get("remaining_task_count", 0),
        "graph_fixed_status": graph_gap.get("status", "unknown"),
        "visible_records": len(browser.get("visible_record_ids", [])),
        "browser_latency": str(browser.get("search_meta", "延迟已记录")),
        "desktop_search": asset_path(REPRO / "browser_screenshots" / "desktop_search_results.png"),
        "desktop_kg": asset_path(REPRO / "browser_screenshots" / "desktop_kg_artifacts.png"),
        "graph_report": repo_path(REPORTS / "challenge_cup_graphrag_same_question_report.md"),
        "day3": repo_path(latest("day3_retrieval_baseline_comparison_*.md") or REPORTS),
        "day4": repo_path(latest("day4_failure_analysis_*.md") or REPORTS),
    }


COMMON_MJS = r"""
export const C = {
  ink: "#152033",
  sub: "#526173",
  quiet: "#7B8798",
  paper: "#F7F8FA",
  line: "#D8DEE8",
  blue: "#2457A6",
  cyan: "#1499A5",
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

export function shape(slide, ctx, x, y, w, h, fill, line = "#00000000") {
  return ctx.addShape(slide, { x, y, w, h, fill, line: ctx.line(line, line === "#00000000" ? 0 : 1) });
}

export function text(slide, ctx, value, x, y, w, h, opts = {}) {
  ctx.addText(slide, {
    text: value,
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

export function metric(slide, ctx, item, x, y, w = 138) {
  text(slide, ctx, item.value, x, y, w, 38, { size: 29, bold: true, color: item.color ?? C.blue, face: "Aptos Display" });
  text(slide, ctx, item.label, x, y + 40, w + 10, 38, { size: 12.5, color: C.sub });
}

export function footer(slide, ctx, number) {
  text(slide, ctx, "知燃知维 · Challenge Cup defense deck", 54, 682, 520, 18, { size: 11.5, color: C.quiet, face: "Aptos" });
  text(slide, ctx, String(number).padStart(2, "0"), 1200, 680, 42, 20, { size: 11.5, color: C.quiet, align: "right", face: "Aptos" });
}

export async function renderSlide(slide, ctx, spec) {
  shape(slide, ctx, 0, 0, 1280, 720, spec.dark ? C.navy : C.paper);
  const titleColor = spec.dark ? C.white : C.ink;
  const subColor = spec.dark ? "#C9D6E7" : C.sub;
  text(slide, ctx, spec.kicker.toUpperCase(), 54, 34, 620, 22, { size: 12, bold: true, color: spec.dark ? "#76D6E2" : C.cyan, face: "Aptos" });
  text(slide, ctx, spec.title, 54, 62, 980, 64, { size: spec.titleSize ?? 29, bold: true, color: titleColor });
  text(slide, ctx, spec.subtitle ?? "", 56, 126, 1000, 32, { size: 15.5, color: subColor });
  shape(slide, ctx, 54, 164, 1160, 1, spec.dark ? "#37506E" : C.line);

  if (spec.metrics) {
    const startX = spec.metricStartX ?? 70;
    spec.metrics.forEach((item, idx) => metric(slide, ctx, item, startX + idx * 172, spec.metricY ?? 204));
  }

  if (spec.bullets) {
    let y = spec.bulletY ?? 268;
    spec.bullets.forEach((item) => {
      shape(slide, ctx, 72, y + 8, 9, 9, item.color ?? C.cyan);
      text(slide, ctx, item.text, 96, y, spec.bulletW ?? 520, 44, { size: item.size ?? 17, color: spec.dark ? C.white : C.ink, bold: item.bold ?? false });
      y += item.gap ?? 58;
    });
  }

  if (spec.cards) {
    spec.cards.forEach((card) => {
      shape(slide, ctx, card.x, card.y, card.w, card.h, card.fill ?? C.white, card.line ?? C.line);
      text(slide, ctx, card.title, card.x + 18, card.y + 16, card.w - 36, 26, { size: 18, bold: true, color: card.color ?? C.blue });
      text(slide, ctx, card.body, card.x + 18, card.y + 54, card.w - 36, card.h - 66, { size: 15.5, color: C.ink });
    });
  }

  if (spec.image) {
    shape(slide, ctx, spec.image.x - 8, spec.image.y - 8, spec.image.w + 16, spec.image.h + 16, C.white, C.line);
    await ctx.addImage(slide, {
      path: spec.image.path,
      x: spec.image.x,
      y: spec.image.y,
      w: spec.image.w,
      h: spec.image.h,
      fit: spec.image.fit ?? "contain",
      alt: spec.image.alt ?? spec.title,
    });
  }

  if (spec.callout) {
    shape(slide, ctx, spec.callout.x, spec.callout.y, spec.callout.w, spec.callout.h, spec.callout.fill ?? C.paleAmber, spec.callout.line ?? "#E0C078");
    text(slide, ctx, spec.callout.text, spec.callout.x + 18, spec.callout.y + 16, spec.callout.w - 36, spec.callout.h - 26, { size: 16.5, bold: spec.callout.bold ?? true, color: spec.callout.color ?? C.ink });
  }
  footer(slide, ctx, spec.number);
}
"""


def slide_specs(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "number": 1,
            "dark": True,
            "kicker": "Opening",
            "title": "知燃知维：面向动力装备运维知识的可信 GraphRAG 系统",
            "subtitle": "目标不是展示一个问答页，而是交付可结项、可复核、可答辩的证据型知识工程项目。",
            "metrics": [
                {"value": "60", "label": "系统评测问题", "color": "#F5C56B"},
                {"value": str(data["task_type_count"]), "label": "任务类型覆盖", "color": "#76D6E2"},
                {"value": str(data["source_scope_count"]), "label": "资料范围覆盖", "color": "#A9E3BF"},
                {"value": "Archive", "label": "manifest 记录", "color": "#FFFFFF"},
                {"value": "GT-07", "label": "固定演示场景", "color": "#F2A6A6"},
            ],
            "metricY": 242,
            "bullets": [
                {"text": "评审主线：真实资料处理 + RAG/GraphRAG + 自动评测 + 可复现门禁 + 清晰边界", "bold": True},
                {"text": "现场策略：先证明完成度，再用 GT-07 异常振动场景展示应用价值。"},
                {"text": "诚信边界：专家反馈与真实彩排未归档前，不把准备材料说成外部背书。"},
            ],
            "bulletY": 420,
            "bulletW": 980,
        },
        {
            "number": 2,
            "kicker": "Problem",
            "title": "动力装备资料难点不在问答，而在证据链能否被追溯",
            "subtitle": "扫描件、术语、部件关系和维修流程混在一起，普通检索容易回答但难以解释。",
            "cards": [
                {"x": 70, "y": 210, "w": 330, "h": 230, "title": "真实痛点", "body": "资料分散、扫描件多、术语密集；评委最关心系统是否能稳定定位证据，而不是一句流畅回答。", "fill": "#FBEAEA", "color": "#B54747"},
                {"x": 465, "y": 210, "w": 330, "h": 230, "title": "方法创新", "body": "把 OCR、chunk、RAG、知识图谱、GraphRAG 子集和人工补证串成 evidence-bound 工作流。", "fill": "#EAF1FB", "color": "#2457A6"},
                {"x": 860, "y": 210, "w": 330, "h": 230, "title": "结项价值", "body": "材料包、readiness gate、submission archive 和固定演示场景让项目能被验收，而不是只能口头展示。", "fill": "#EAF6EF", "color": "#2F7D59"},
            ],
            "callout": {"x": 140, "y": 542, "w": 980, "h": 68, "text": "一句话答辩：我们做的是“证据型辅助和知识资产整理”，不是替代工程师做高风险维修决策。"},
        },
        {
            "number": 3,
            "kicker": "Architecture",
            "title": "工程闭环覆盖资料导入、检索增强、图谱证据和评测门禁",
            "subtitle": "这页回答“项目完成度是否只是前端包装”的问题。",
            "metrics": [
                {"value": "OCR", "label": "扫描资料结构化", "color": "#2457A6"},
                {"value": "RAG", "label": "文本证据召回", "color": "#1499A5"},
                {"value": "KG", "label": "关系证据组织", "color": "#2F7D59"},
                {"value": "Gate", "label": "机器验收门禁", "color": "#B7791F"},
            ],
            "metricY": 212,
            "cards": [
                {"x": 84, "y": 365, "w": 250, "h": 120, "title": "资料层", "body": "课程资料、维修案例、JSON 问答和浏览器演示快照。"},
                {"x": 378, "y": 365, "w": 250, "h": 120, "title": "检索层", "body": "keyword / hybrid / GraphRAG context，对同题子集做证据覆盖审计。"},
                {"x": 672, "y": 365, "w": 250, "h": 120, "title": "评测层", "body": "60 题评测集、baseline、失败归因、manual evidence supplement。"},
                {"x": 966, "y": 365, "w": 250, "h": 120, "title": "交付层", "body": "README、项目书、答辩材料、归档包、readiness gate。"},
            ],
        },
        {
            "number": 4,
            "kicker": "Evaluation",
            "title": "60 题评测集把“能演示”压实为“能复核”",
            "subtitle": f"{data['task_type_count']} 类任务、{data['source_scope_count']} 类资料范围、{data['graphrag_questions']} 道 GraphRAG 标记问题。",
            "metrics": [
                {"value": "60", "label": "评测题", "color": "#2457A6"},
                {"value": str(data["task_type_count"]), "label": "task_type", "color": "#1499A5"},
                {"value": str(data["source_scope_count"]), "label": "source_scope", "color": "#2F7D59"},
                {"value": "10", "label": "GraphRAG 子集", "color": "#B7791F"},
                {"value": str(data["graph_remaining_tasks"]), "label": "剩余补证任务", "color": "#B54747"},
            ],
            "metricY": 210,
            "bullets": [
                {"text": "每题包含标准答案、证据关键词、任务类型、资料范围和评分说明。"},
                {"text": "GraphRAG 子集当前本地证据状态为 supported=10, partial=0, missing=0。"},
                {"text": "边界：本地证据覆盖不等于在线 LLM 胜率，也不等于外部专家认可。"},
            ],
            "bulletY": 390,
            "bulletW": 980,
        },
        {
            "number": 5,
            "kicker": "Scenario",
            "title": "固定应用场景：GT-07 燃气轮机异常振动诊断流程",
            "subtitle": "用真实浏览器烟测截图证明现场演示不是口头描述。",
            "image": {"path": data["desktop_search"], "x": 612, "y": 196, "w": 520, "h": 360, "fit": "contain"},
            "bullets": [
                {"text": "固定查询：燃气轮机异常振动诊断流程", "bold": True},
                {"text": f"浏览器可见记录数：{data['visible_records']}；{data['browser_latency']}"},
                {"text": "证据链覆盖阈值、叶片、滤网、传感器、检修和人工确认边界。"},
                {"text": "高风险维修仍需人工确认；系统定位为证据型辅助。"},
            ],
            "bulletY": 210,
            "bulletW": 480,
        },
        {
            "number": 6,
            "kicker": "GraphRAG proof",
            "title": "GraphRAG 价值不靠泛化承诺，而靠关系证据可视化",
            "subtitle": "答辩时只主张固定子集证据覆盖，不宣称所有问题全面优于 baseline。",
            "image": {"path": data["desktop_kg"], "x": 625, "y": 188, "w": 520, "h": 368, "fit": "contain"},
            "bullets": [
                {"text": "GraphRAG 用于部件、故障、检查项和处理措施之间的关系解释。"},
                {"text": "manual evidence supplement 已关闭 P0 missing 与 relation schema gap。"},
                {"text": f"可指向报告：{data['graph_report']}"},
            ],
            "bulletY": 220,
            "bulletW": 500,
            "callout": {"x": 78, "y": 548, "w": 495, "h": 64, "text": "关键答法：GraphRAG 是关系证据组织能力，不是“所有题都一定赢”的口号。", "fill": "#EAF6EF", "line": "#B9DBC7"},
        },
        {
            "number": 7,
            "kicker": "Submission readiness",
            "title": "结项提交不是散文件：已形成归档包、哈希和机器门禁",
            "subtitle": data["readiness"],
            "metrics": [
                {"value": str(data["archive_file_count"]), "label": "归档文件", "color": "#2457A6"},
                {"value": f"{data['archive_bytes'] // 1024}KB", "label": "zip 大小", "color": "#1499A5"},
                {"value": "SHA256", "label": "完整性校验", "color": "#2F7D59"},
                {"value": "README", "label": "评审入口", "color": "#B7791F"},
            ],
            "metricY": 220,
            "bullets": [
                {"text": "package_manifest.json 记录证据文件、评测覆盖画像和归档清单。"},
                {"text": "evidence_hashes.json 与 submission archive manifest 支撑复核。"},
                {"text": "readiness gate 覆盖材料、评测、浏览器烟测、GraphRAG、答辩和归档。"},
            ],
            "bulletY": 412,
            "bulletW": 980,
        },
        {
            "number": 8,
            "kicker": "Special prize angle",
            "title": "特等奖争取点：创新性、完成度、可复现和边界严谨同时成立",
            "subtitle": "这页用于回答“为什么不只是一个普通 RAG demo”。",
            "cards": [
                {"x": 70, "y": 210, "w": 260, "h": 230, "title": "创新性", "body": "Evidence-bound RAG + GraphRAG 子集 + 失败归因 + 补证闭环。", "fill": "#EAF1FB"},
                {"x": 360, "y": 210, "w": 260, "h": 230, "title": "完成度", "body": "项目书、白皮书、验收清单、固定演示、归档包和门禁报告齐备。", "fill": "#EAF6EF"},
                {"x": 650, "y": 210, "w": 260, "h": 230, "title": "可复现", "body": "60 题评测集、baseline、smoke、hashes、readiness gate 可重新运行。", "fill": "#FFF4DA"},
                {"x": 940, "y": 210, "w": 260, "h": 230, "title": "边界", "body": "不夸大生产替代、不伪造专家反馈、不把 gate 说成获奖保证。", "fill": "#FBEAEA", "color": "#B54747"},
            ],
            "callout": {"x": 115, "y": 536, "w": 1030, "h": 70, "text": "现场表达策略：主动展示失败案例和边界，比回避问题更能体现科学性和工程可信度。"},
        },
        {
            "number": 9,
            "kicker": "External validation",
            "title": "专家反馈与彩排是最后硬证据：已准备采集，不伪造结果",
            "subtitle": "当前状态是 ready-to-send / ready-to-record，而不是已获得专家背书。",
            "cards": [
                {"x": 86, "y": 210, "w": 500, "h": 170, "title": "专家反馈", "body": "外发包、反馈表、归档类型和整改闭环已准备；收到真实签字、邮件、会议纪要或聊天记录后再更新。", "fill": "#EAF1FB"},
                {"x": 674, "y": 210, "w": 500, "h": 170, "title": "真实彩排", "body": "90 秒开场、3 分钟演示、20 秒离线切换和杀手问题均有计分卡；真实计时完成前不宣称通过。", "fill": "#EAF6EF"},
                {"x": 86, "y": 430, "w": 500, "h": 138, "title": "必须补的外部证据", "body": "至少 1 份外部/导师反馈原件 + 1 次真实计时彩排记录 + 现场问答遗漏清单。", "fill": "#FFF4DA"},
                {"x": 674, "y": 430, "w": 500, "h": 138, "title": "补完后的动作", "body": "更新反馈闭环与彩排结果包，重新生成 package、submission archive 和 readiness gate。", "fill": "#FBEAEA", "color": "#B54747"},
            ],
        },
        {
            "number": 10,
            "kicker": "Close",
            "title": "90 秒讲清项目，3 分钟证明它能被复核",
            "subtitle": "终审答辩只保留一条主线：问题、方法、证据、边界、下一步。",
            "metrics": [
                {"value": "90s", "label": "开场定位", "color": "#2457A6"},
                {"value": "180s", "label": "固定演示", "color": "#1499A5"},
                {"value": "20s", "label": "离线切换", "color": "#2F7D59"},
                {"value": "30s", "label": "杀手问题", "color": "#B7791F"},
                {"value": "0", "label": "夸大承诺", "color": "#B54747"},
            ],
            "metricY": 220,
            "bullets": [
                {"text": "结论：项目已经从 RAG 页面升级为可结项、可审计、可答辩的知识工程系统。", "bold": True},
                {"text": "特等奖冲刺仍需真实专家反馈和真实彩排证据；这两项不能用内部材料替代。"},
                {"text": "最终动作：带着 submission archive、PPT、讲稿和 readiness report 进入现场。"},
            ],
            "bulletY": 424,
            "bulletW": 990,
        },
    ]


def write_planning_files(data: dict[str, Any]) -> None:
    write(
        WORKSPACE / "profile-plan.txt",
        """
        task mode: create
        primary deck-profile: engineering-platform
        secondary gates: academic defense, challenge-cup special-prize narrative
        required proof objects: system architecture, evaluation coverage, GT-07 browser screenshot, GraphRAG evidence screenshot, readiness/archive proof, external validation boundary
        source requirements: use local project reports and screenshots only; no fabricated external feedback
        brand authenticity constraints: no logos or fake badges; neutral technical visual system
        profile-specific QA gates: every claim has evidence; no overclaim of award, production deployment, expert approval, or live rehearsal completion
        known missing inputs: true signed expert feedback and true timed rehearsal record are not yet available
        """,
    )
    write(
        WORKSPACE / "source-notes.txt",
        f"""
        Sources used:
        - docs/challenge_cup/package_manifest.json
        - docs/challenge_cup/reproducibility/readiness_gate_report.md
        - docs/challenge_cup/reproducibility/browser_demo_smoke_report.json
        - docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png
        - docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png
        - docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json
        - evaluation/system_eval_questions.jsonl
        - {data['graph_report']}
        - {data['day3']}
        - {data['day4']}

        Identity assets: none. Screenshots are local project demo evidence, not decorative stock imagery.
        """,
    )
    write(
        WORKSPACE / "claim-spine.txt",
        """
        1. The project is a verifiable knowledge engineering system, not a generic RAG page.
        2. The data and evaluation surface are broad enough for completion review.
        3. GT-07 provides a fixed application scenario that can be shown live or offline.
        4. GraphRAG is framed as relationship evidence, not universal answer superiority.
        5. The submission archive and readiness gate make the package auditable.
        6. The special-prize argument is completion plus innovation plus rigorous boundaries.
        7. External feedback and real rehearsal evidence remain the last non-fabricable proof items.
        """,
    )


def write_slide_modules(data: dict[str, Any]) -> None:
    SLIDES_DIR.mkdir(parents=True, exist_ok=True)
    write(SLIDES_DIR / "common.mjs", COMMON_MJS)
    for spec in slide_specs(data):
        content = f"""
        import {{ renderSlide }} from "./common.mjs";

        const spec = {js(spec)};

        export async function slide{spec['number']:02d}(presentation, ctx) {{
          const slide = presentation.slides.add();
          await renderSlide(slide, ctx, spec);
          return slide;
        }}
        """
        write(SLIDES_DIR / f"slide-{spec['number']:02d}.mjs", dedent(content))


def build_deck() -> None:
    node = str(BUNDLED_NODE) if BUNDLED_NODE.exists() else "node"
    env = os.environ.copy()
    env["HOME"] = str(Path.home())
    env["PYTHON"] = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
    if BUNDLED_NODE_MODULES.exists():
        env["NODE_PATH"] = str(BUNDLED_NODE_MODULES)
    command = [
        node,
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
    notes = f"""
    # Challenge Cup Defense Speaker Notes

    ## 1. 90秒开场
    项目名称是“知燃知维：面向动力装备运维知识的可信 GraphRAG 系统”。一句话定位：我们不是做一个普通问答页面，而是把动力装备资料处理、RAG/GraphRAG、自动评测、失败归因、归档包和 readiness gate 串成一个可结项、可复核、可答辩的知识工程系统。

    ## 2. 三分钟演示主线
    先打开项目一页纸说明问题、方法和边界；再展示 GT-07 燃气轮机异常振动诊断流程；随后切到浏览器烟测截图和 KG artifact，证明演示路径已经被真实浏览器跑通过；最后展示 readiness gate 和 submission archive，说明材料不是散文件。

    ## 3. 必须讲出的数字
    评测集有 60 道题，覆盖 {data['task_type_count']} 类 task_type 和 {data['source_scope_count']} 类 source_scope；GraphRAG 标记问题有 {data['graphrag_questions']} 道；归档包文件数和 SHA256 以 manifest 为准；固定应用场景为 GT-07。

    ## 4. GraphRAG 答辩口径
    GraphRAG 在这里的价值是关系证据组织：把故障现象、部件、检查项、处理措施和复机结果串起来。不要说 GraphRAG 对所有问题都优于 baseline，也不要说本地证据覆盖等于在线 LLM 胜率。

    ## 5. GT-07 固定场景讲法
    这个场景用于证明应用价值：系统围绕“燃气轮机异常振动诊断流程”返回 5 条可见记录，覆盖阈值、叶片、滤网、传感器、检修措施和人工确认边界。高风险维修仍需工程师确认，系统只做证据型辅助。

    ## 6. readiness gate 讲法
    readiness gate 证明包内材料、manifest、hash、浏览器烟测、GraphRAG 报告、答辩材料和 submission archive 可复核。不能把 readiness gate 说成获奖保证。

    ## 7. 专家反馈与彩排边界
    专家反馈外发包和答辩彩排计分卡已经准备好，但真实签字、邮件反馈、会议纪要和真实计时彩排记录未归档前，不宣称已获得专家认可，也不宣称真实彩排已经通过。

    ## 8. 杀手问题回答模板
    问“为什么能冲击特等奖”：回答“不是靠页面包装，而是靠真实资料处理、知识工程闭环、科学评测、失败归因、可复现门禁和清晰边界”。然后落到 07 证据矩阵、08 自评表和 readiness gate。

    ## 9. 离线兜底
    如果现场服务或网络异常，20 秒内切换到 browser smoke 报告、桌面检索截图、KG artifact 截图和 submission archive。不要现场排环境。

    ## 10. 收束句
    这个项目现在已经具备结项提交状态；冲击特等奖还需要补齐真实专家反馈和真实计时彩排这两类硬证据。我们不伪造外部意见，不把内部自评写成专家背书。
    """
    write(SPEAKER_NOTES, dedent(notes))


def build_outputs(force: bool = False) -> None:
    if not force and FINAL_PPTX.exists() and SPEAKER_NOTES.exists():
        return
    for directory in (OUTPUT_DIR, WORKSPACE, SLIDES_DIR, PREVIEW_DIR, LAYOUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    data = build_data()
    write_planning_files(data)
    write_slide_modules(data)
    build_deck()
    write_speaker_notes(data)


def main() -> int:
    force = "--force" in sys.argv[1:]
    build_outputs(force=force)
    print(f"Wrote defense deck: {FINAL_PPTX.relative_to(REPO_ROOT)}")
    print(f"Wrote speaker notes: {SPEAKER_NOTES.relative_to(REPO_ROOT)}")
    print(f"Workspace: {WORKSPACE}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
