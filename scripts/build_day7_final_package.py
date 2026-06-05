from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = REPO_ROOT / "evaluation" / "reports"
MATERIAL_DIR = REPO_ROOT / "docs" / "project_deliverables" / "06_汇报材料_发群和组会"
PACKAGE_DIR = MATERIAL_DIR / "RAG课程汇报_最终交付包"
ZIP_PATH = MATERIAL_DIR / "RAG课程汇报_最终交付包.zip"


def latest(pattern: str) -> Path:
    matches = sorted(REPORT_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"No report matched {pattern}")
    return matches[0]


def core_files() -> list[tuple[str, Path]]:
    return [
    ("00_最终交付清单.md", MATERIAL_DIR / "最终汇报交付清单.md"),
    ("01_课程汇报PPT.pptx", MATERIAL_DIR / "RAG课程汇报_第五天材料.pptx"),
    ("02_PPT逐页讲稿.md", MATERIAL_DIR / "第五天PPT讲稿.md"),
    ("03_60题评测集说明.md", MATERIAL_DIR / "60题评测集说明.md"),
    ("04_第三天检索评测结果.md", MATERIAL_DIR / "第三天检索评测结果.md"),
    ("05_第四天失败案例分析.md", MATERIAL_DIR / "第四天失败案例分析.md"),
    ("06_第六天现场演示脚本.md", MATERIAL_DIR / "第六天现场演示脚本.md"),
    ("07_第六天演示备用证据包.md", MATERIAL_DIR / "第六天演示备用证据包.md"),
    ("08_第六天答辩口径与检查清单.md", MATERIAL_DIR / "第六天答辩口径与检查清单.md"),
    ("09_最后一天彩排检查表.md", MATERIAL_DIR / "最后一天彩排检查表.md"),
    ("10_系统评测题集.jsonl", REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"),
    ("11_Day3_baseline_comparison.md", latest("day3_retrieval_baseline_comparison_*.md")),
    ("12_Day4_failure_analysis.md", latest("day4_failure_analysis_*.md")),
    ("13_GraphRAG同题子集报告.md", REPORT_DIR / "challenge_cup_graphrag_same_question_report.md"),
    ("14_知识图谱POC审核页面.html", REPO_ROOT / "docs" / "project_deliverables" / "05_知识图谱POC_三元组和人工判断" / "三元组审核页面.html"),
    ("15_知识图谱POC图片.svg", REPO_ROOT / "docs" / "project_deliverables" / "05_知识图谱POC_三元组和人工判断" / "知识图谱图片.svg"),
    ]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def count_jsonl(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def as_rel(path: Path | str) -> str:
    raw = Path(path)
    try:
        return str(raw.relative_to(REPO_ROOT))
    except ValueError:
        return str(raw)


def write_text(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def strip_trailing_whitespace(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8")


def build_final_checklist(now: str) -> Path:
    manifest = read_json(MATERIAL_DIR / "artifact-build-manifest.json")
    day6 = read_json(MATERIAL_DIR / "第六天演示包_manifest.json")
    question_count = count_jsonl(REPO_ROOT / "evaluation" / "system_eval_questions.jsonl")
    path = MATERIAL_DIR / "最终汇报交付清单.md"
    content = f"""
# 最终汇报交付清单

生成时间：{now}

## 一句话定位

这是一个动力装备 RAG / GraphRAG 课程项目的最终汇报包。重点不是只展示一个问答页面，而是展示从资料处理、OCR、检索、知识图谱 POC 到系统评测和失败归因的可复现工程链路。

## 已完成交付

| 模块 | 交付物 | 当前状态 |
| --- | --- | --- |
| 汇报 PPT | `RAG课程汇报_第五天材料.pptx` | {manifest.get("slideCount")} 页，可编辑，已导出预览 |
| 逐页讲稿 | `第五天PPT讲稿.md` | 可照稿讲 |
| 评测集 | `evaluation/system_eval_questions.jsonl` | {question_count} 题 |
| baseline 对比 | `第三天检索评测结果.md`、Day3 report | keyword / dense_hashing / hybrid_rrf 三类 |
| 失败归因 | `第四天失败案例分析.md`、Day4 report | {day6.get("day4_case_count")} 个弱/失败案例 |
| GraphRAG 同题子集 | `13_GraphRAG同题子集报告.md` | 从 60 题中筛出 graph context/global 固定子集 |
| 现场演示 | `第六天现场演示脚本.md` | 5 分钟主线 |
| 备用证据 | `第六天演示备用证据包.md` | 服务失败时可离线讲 |
| 答辩口径 | `第六天答辩口径与检查清单.md` | 高频问题和边界说明 |
| 最终包 | `RAG课程汇报_最终交付包.zip` | 可发群、可提交 |

## 推荐汇报顺序

1. 先打开 PPT，按 10 页主线讲。
2. 第 6 页讲 Day3 baseline，不需要现场重新跑完整评测。
3. 第 7-8 页讲 Day4 失败分析，强调失败案例如何转化为优化任务。
4. 第 9 页如时间允许，打开知识图谱 POC 审核页面；如果现场环境不稳定，用离线 SVG/PPT 讲。
5. 最后用第 10 页收束到下一轮优化：source scope、embedding/reranker、结构化事实路由。

## 汇报边界

- 可以说：工程链路、评测集、baseline、失败归因、KG POC 已经形成闭环。
- 可以说：当前结果支持课程学术汇报，因为有数据、方法、实验、失败分析和复现材料。
- 不要说：完整商业级 GraphRAG 已经完成。
- 不要说：Neo4j 服务和真实 LLM 生成已经稳定跑通。
- 不要说：{question_count} 题已经是最终论文 benchmark。
"""
    write_text(path, content)
    return path


def build_rehearsal_sheet(now: str, *, question_count: int, day3_report: Path, day4_report: Path) -> Path:
    path = MATERIAL_DIR / "最后一天彩排检查表.md"
    content = f"""
# 最后一天彩排检查表

生成时间：{now}

## 第一次彩排：只看时间

| 页码 | 内容 | 目标时间 | 超时处理 |
| ---: | --- | ---: | --- |
| 1 | 项目定位和核心数字 | 30 秒 | 不展开技术细节 |
| 2 | 汇报重点 | 30 秒 | 直接进入流程 |
| 3 | 数据链路 | 45 秒 | 只讲 OCR、语料、评测集 |
| 4 | 系统架构 | 45 秒 | 普通 RAG 和 GraphRAG 双线即可 |
| 5 | {question_count} 题评测设计 | 45 秒 | 强调不是随机问答 |
| 6 | baseline 结果 | 60 秒 | 只讲 keyword 为什么暂时最好 |
| 7 | 案例诊断 | 45 秒 | 成功、弱命中、失败各一句 |
| 8 | 失败分析 | 60 秒 | 说清楚下一轮优化入口 |
| 9 | 现场演示 | 45 秒 | 环境不稳就切离线证据 |
| 10 | 收束 | 30 秒 | 回到可评测、可解释、可优化 |

目标总时长：6 分钟以内。

## 第二次彩排：只看风险

- PPT 打不开：改用 `第五天PPT讲稿.md` 和 contact sheet 讲。
- 本地服务打不开：不排查环境，切到 `第六天演示备用证据包.md`。
- 老师问为什么不是完整 GraphRAG：回答“当前完成的是 KG construction、context-only 和评测闭环，完整在线问答是下一阶段”。
- 老师问为什么不用更强模型：回答“本次课程汇报重点是工程链路和评测方法，模型可替换，评测集用于复测替换收益”。
- 老师问失败案例多不多：回答“失败案例是故意保留的诊断材料，已经分类成可执行优化项”。

## 第三次彩排：只看口径

必须反复使用这条主线：

> 我把原始动力装备资料推进到了可检索、可评测、可解释、可继续优化的 RAG / GraphRAG 工程链路。

不要临场新增承诺。所有没有被文件和评测证明的能力，都说成下一阶段工作。

## 上台前最终检查

- `RAG课程汇报_最终交付包.zip` 已生成。
- `RAG课程汇报_第五天材料.pptx` 可打开。
- `第六天现场演示脚本.md` 可打开。
- `第六天答辩口径与检查清单.md` 可打开。
- `{as_rel(day3_report)}` 可打开。
- `{as_rel(day4_report)}` 可打开。
"""
    write_text(path, content)
    return path


def copy_package_files() -> list[Path]:
    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(parents=True)
    copied: list[Path] = []
    for target_name, source in core_files():
        if not source.exists():
            raise FileNotFoundError(source)
        target = PACKAGE_DIR / target_name
        shutil.copy2(source, target)
        if target.suffix.lower() == ".svg":
            strip_trailing_whitespace(target)
        copied.append(target)

    manifest = read_json(MATERIAL_DIR / "artifact-build-manifest.json")
    contact_sheet = Path(manifest.get("contactSheet", ""))
    if contact_sheet.exists():
        target = PACKAGE_DIR / "16_PPT全页缩略图.png"
        shutil.copy2(contact_sheet, target)
        copied.append(target)
    return copied


def write_package_readme(now: str, copied: list[Path]) -> Path:
    path = PACKAGE_DIR / "README_先看这里.md"
    lines = [
        "# RAG 课程汇报最终交付包",
        "",
        f"生成时间：{now}",
        "",
        "打开顺序：",
        "",
        "1. `01_课程汇报PPT.pptx`",
        "2. `02_PPT逐页讲稿.md`",
        "3. `00_最终交付清单.md`",
        "4. `09_最后一天彩排检查表.md`",
        "",
        "包内文件：",
        "",
    ]
    for item in copied:
        lines.append(f"- `{item.name}`")
    write_text(path, "\n".join(lines))
    return path


def build_zip() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PACKAGE_DIR.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(PACKAGE_DIR.parent))


def main() -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    question_count = count_jsonl(REPO_ROOT / "evaluation" / "system_eval_questions.jsonl")
    day3_report = latest("day3_retrieval_baseline_comparison_*.md")
    day4_report = latest("day4_failure_analysis_*.md")
    final_checklist = build_final_checklist(now)
    rehearsal_sheet = build_rehearsal_sheet(
        now,
        question_count=question_count,
        day3_report=day3_report,
        day4_report=day4_report,
    )
    copied = copy_package_files()
    package_readme = write_package_readme(now, copied)
    build_zip()
    manifest = {
        "generated_at": now,
        "final_checklist": str(final_checklist),
        "rehearsal_sheet": str(rehearsal_sheet),
        "package_dir": str(PACKAGE_DIR),
        "package_readme": str(package_readme),
        "zip_path": str(ZIP_PATH),
        "zip_bytes": ZIP_PATH.stat().st_size,
        "copied_files": len(copied),
    }
    manifest_path = MATERIAL_DIR / "最终交付包_manifest.json"
    write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
