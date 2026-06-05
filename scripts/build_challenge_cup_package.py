from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "docs" / "challenge_cup"
REPRO = OUT / "reproducibility"
REPORTS = REPO_ROOT / "evaluation" / "reports"
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
CLAIM_MATRIX = OUT / "07_评审主张证据矩阵.md"
AWARD_SELF_EVAL = OUT / "08_特等奖评审自评表.md"
GRAPH_REPORT = REPORTS / "challenge_cup_graphrag_same_question_report.md"
LIVE_SMOKE_REPORT = REPRO / "live_demo_smoke_report.md"
BROWSER_SMOKE_REPORT = REPRO / "browser_demo_smoke_report.md"
BROWSER_SMOKE_JSON = REPRO / "browser_demo_smoke_report.json"
READINESS_GATE_REPORT = REPRO / "readiness_gate_report.md"
BROWSER_SCREENSHOT_DIR = REPRO / "browser_screenshots"
BROWSER_SCREENSHOTS = [
    BROWSER_SCREENSHOT_DIR / "desktop_overview.png",
    BROWSER_SCREENSHOT_DIR / "desktop_search_results.png",
    BROWSER_SCREENSHOT_DIR / "desktop_kg_artifacts.png",
    BROWSER_SCREENSHOT_DIR / "mobile_overview.png",
]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def read(path: Path, limit: int = 1600) -> str:
    if not path.exists():
        return f"文件未找到：{path}"
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text if len(text) <= limit else text[:limit].rstrip() + "\n..."


def count_jsonl(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


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


def build_context() -> dict[str, Any]:
    day3 = latest("day3_retrieval_baseline_comparison_*.md")
    day4 = latest("day4_failure_analysis_*.md")
    return {
        "now": generated_at_from_reports(day3, day4),
        "question_count": count_jsonl(DATASET),
        "day3": day3,
        "day4": day4,
        "graph_report": GRAPH_REPORT if GRAPH_REPORT.exists() else None,
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
10. `reproducibility/runbook.md`
11. `reproducibility/dataset_manifest.md`
12. `reproducibility/readiness_gate_report.md`

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
    return f"""# 实验评测报告

## 评测集

当前系统评测集包含 {ctx["question_count"]} 题，覆盖普通 RAG、OCR 风险、GraphRAG/知识图谱、结构化事实、评测方法和挑战杯答辩口径。

## 已有 baseline

Day3 已比较 keyword、dense_hashing 和 hybrid_rrf 三种离线检索策略。报告位置：`{day3_ref}`。

## 失败归因

Day4 已将弱命中和失败案例归类为术语别名、结构化事实、hybrid 稀释、排序差距和评测概念缺口等问题。报告位置：`{day4_ref}`。

## GraphRAG 同题子集

已从 60 题评测集中筛出显式标注 `graphrag_context` / `graphrag_global` 的同题子集，并对这些题的 keyword、dense_hashing、hybrid_rrf baseline 覆盖率做了对照。报告位置：`{graph_ref}`。

## 结论

当前项目能证明评测链路存在并可复跑。挑战杯版本需要继续补充 GraphRAG context/global 的同题对比，并在真实 embedding/reranker 条件允许时复测。

## 关键证据摘录

### 普通 RAG 数据库

{read(ctx["rag_db"], 1200)}

### 知识图谱人工评审

{read(ctx["kg_review"], 1200)}
"""


def build_demo_script(ctx: dict[str, Any]) -> str:
    return """# 系统演示脚本

## 主线演示

1. 打开 `docs/challenge_cup/00_项目一页纸.md`，用 30 秒说明问题、方法和核心数字。
2. 启动控制台：`cd api_server/current_console; python server.py`，打开 `http://localhost:8000`。
3. 展示普通 RAG 检索问题：“燃烧室在燃气轮机热力循环中承担什么功能？”
4. 展示 GraphRAG 证据问题：“为什么三元组必须绑定 evidence 才能用于可信问答？”
5. 打开 `docs/challenge_cup/03_实验评测报告.md`，说明 baseline 和失败归因。

## 备用演示

如果服务未启动，直接打开知识图谱审核页面、SVG、实验评测报告和答辩问答手册。现场不排查环境，把时间用于解释证据链。
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

| 主张 | 证据文件 | 状态 |
| --- | --- | --- |
| 资料处理链路完整 | `docs/project_deliverables/02_OCR结果_13本扫描PDF/`、`docs/project_deliverables/03_普通RAG数据库_14本资料/数据库构建结果_人话版.md` | 已有 |
| 普通 RAG 可入库检索 | `docs/project_deliverables/03_普通RAG数据库_14本资料/数据库构建结果_人话版.md` | 已有 |
| 知识图谱不是空图 | `docs/project_deliverables/05_知识图谱POC_三元组和人工判断/人工判断小结.md` | 已有 |
| RAG 能被评测 | `evaluation/system_eval_questions.jsonl`、`evaluation/reports/` | 已有并扩展 |
| 演示有主线和备用线 | `docs/challenge_cup/04_系统演示脚本.md` | 已有 |
| 答辩边界严谨 | `docs/challenge_cup/05_答辩问答手册.md` | 已有 |
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
| 科学评测 | 评测不是只挑成功案例，而是包含 60 题评测集、baseline、失败归因和 GraphRAG 同题子集。 | `evaluation/system_eval_questions.jsonl`; `{day3_ref}`; `{day4_ref}`; `{graph_ref}` | `python scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5`; `python scripts/analyze_day4_failure_cases.py` | 评测集是当前阶段的课程 / 挑战杯评测集，后续可扩展为更大 benchmark。 |
| 可复现 | 评委可以按 runbook 复现包生成、live smoke、browser smoke 和 readiness gate。 | `docs/challenge_cup/reproducibility/runbook.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` | `python scripts/check_challenge_cup_readiness.py`; `node scripts/run_challenge_cup_browser_demo_smoke.mjs` | Browser smoke 证明本地演示与关键资源可用，不替代生产压测。 |
| 应用边界 | 系统定位为证据型辅助和知识资产整理，不替代工程师做最终运维决策。 | `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/00_项目一页纸.md`; `docs/challenge_cup/03_实验评测报告.md` | `python scripts/check_challenge_cup_readiness.py` | 对高风险维修决策保留人工确认和证据不足提示。 |
"""


def build_award_self_eval(ctx: dict[str, Any]) -> str:
    return """# 特等奖评审自评表

本表按清华公开报道中出现的评审维度进行自检：评委会关注作品的学术价值或实用性、创新性、作品完成情况和现场答辩表现；清华制度文件也强调实用性、创新性和学术价值。特等奖不超过6件，可空缺，因此本表只用于倒逼整改，不承诺获奖结果。

## 参考口径

- 清华大学第37届“挑战杯”校级终审报道：评委从作品的学术价值或实用性、创新性、作品完成情况和现场答辩表现等方面评分；特等奖候选作品经公开答辩和综合评定产生。链接：https://www.tsinghua.edu.cn/info/1181/35383.htm
- 《清华大学课外创新人才培养体系制度文件汇编》：评审应充分考虑作品的实用性、创新性和学术价值；特等奖不超过6件，可空缺。链接：https://qiyuan.tsinghua.edu.cn/intro/2018/11024/%E6%94%AF%E6%92%91%E6%9D%90%E6%96%993-%E6%B8%85%E5%8D%8E%E5%A4%A7%E5%AD%A6%E8%AF%BE%E5%A4%96%E5%88%9B%E6%96%B0%E4%BA%BA%E6%89%8D%E5%9F%B9%E5%85%BB%E4%BD%93%E7%B3%BB%E5%88%B6%E5%BA%A6%E6%96%87%E4%BB%B6%E6%B1%87%E7%BC%96.pdf

| 评审维度 | 当前自评 | 已有证据 | 仍需现场强调 | 风险控制 |
| --- | --- | --- | --- | --- |
| 学术价值或实用性 | A- | `docs/challenge_cup/07_评审主张证据矩阵.md`; `docs/challenge_cup/03_实验评测报告.md`; `evaluation/system_eval_questions.jsonl` | 把动力装备运维知识的真实痛点讲清楚，强调证据型辅助而非泛问答。 | 避免把课程数据包装成生产级运维闭环。 |
| 创新性 | A- | `docs/challenge_cup/02_技术白皮书.md`; `evaluation/reports/challenge_cup_graphrag_same_question_report.md`; `docs/project_deliverables/06_四本书KG工具跑通演示/kg_evidence_viewer.html` | 强调 evidence-bound KG、失败归因和 GraphRAG 同题子集，而不是只说用了 RAG。 | 明确 GraphRAG 不保证所有问题都超过普通 RAG。 |
| 作品完成情况 | A | `docs/challenge_cup/reproducibility/readiness_gate_report.md`; `docs/challenge_cup/reproducibility/browser_demo_smoke_report.md`; `docs/challenge_cup/reproducibility/runbook.md` | 现场先跑 readiness gate，再展示浏览器截图和 KG artifact。 | 如果 live backend 异常，按离线证据包继续答辩。 |
| 现场答辩表现 | B+ | `docs/challenge_cup/04_系统演示脚本.md`; `docs/challenge_cup/05_答辩问答手册.md`; `docs/challenge_cup/reproducibility/command_log.md` | 3分钟内讲清“问题-方法-证据-边界”，把失败案例变成科学性而不是扣分点。 | 需要继续做限时 rehearsal，避免被问到生产部署和真实运维责任时失焦。 |
| 特等奖不超过6件 | 目标状态 | `docs/challenge_cup/07_评审主张证据矩阵.md`; `docs/challenge_cup/reproducibility/readiness_gate_report.md` | 用“可复现证据链 + 严谨边界 + 工程闭环”争取进入特等奖讨论。 | 不把奖项概率写成承诺；持续补强演示稳定性和答辩节奏。 |
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

## 运行结项 readiness gate

```powershell
.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py
```
"""


def build_dataset_manifest(ctx: dict[str, Any]) -> str:
    return f"""# 数据集与证据清单

- 系统评测集：`evaluation/system_eval_questions.jsonl`，{ctx["question_count"]} 题。
- 普通 RAG 数据库说明：`{md_link(ctx["rag_db"])}`。
- 知识图谱人工评审：`{md_link(ctx["kg_review"])}`。
- Day3 baseline：`{optional_md_link(ctx["day3"])}`。
- Day4 失败分析：`{optional_md_link(ctx["day4"])}`。
- GraphRAG 同题子集：`{optional_md_link(ctx["graph_report"])}`。
- 评审主张证据矩阵：`{md_link(CLAIM_MATRIX)}`。
- 特等奖评审自评表：`{md_link(AWARD_SELF_EVAL)}`。
- 现场演示烟测：`{md_link(LIVE_SMOKE_REPORT)}`。
- 真实浏览器演示烟测：`{md_link(BROWSER_SMOKE_REPORT)}`。
- 真实浏览器烟测 JSON：`{md_link(BROWSER_SMOKE_JSON)}`。
- 结项 readiness gate：`{md_link(READINESS_GATE_REPORT)}`。
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

node scripts/run_challenge_cup_browser_demo_smoke.mjs
-> docs/challenge_cup/reproducibility/browser_demo_smoke_report.md
-> docs/challenge_cup/reproducibility/browser_demo_smoke_report.json
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_overview.png
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_search_results.png
-> docs/challenge_cup/reproducibility/browser_screenshots/desktop_kg_artifacts.png
-> docs/challenge_cup/reproducibility/browser_screenshots/mobile_overview.png
-> Status: pass (12/12 checks)

python scripts/check_challenge_cup_readiness.py
-> docs/challenge_cup/reproducibility/readiness_gate_report.md
-> Status: pass (8/8 gates)
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
    write(OUT / "06_结项验收清单.md", build_checklist(ctx))
    write(CLAIM_MATRIX, build_claim_evidence_matrix(ctx))
    write(AWARD_SELF_EVAL, build_award_self_eval(ctx))
    write(REPRO / "runbook.md", build_runbook(ctx))
    write(REPRO / "dataset_manifest.md", build_dataset_manifest(ctx))
    write(REPRO / "command_log.md", build_command_log(ctx))
    manifest = {
        "generated_at": ctx["now"],
        "output_dir": md_link(OUT),
        "question_count": ctx["question_count"],
        "evidence_files": [
            md_link(DATASET),
            md_link(CLAIM_MATRIX),
            md_link(AWARD_SELF_EVAL),
            md_link(LIVE_SMOKE_REPORT),
            md_link(BROWSER_SMOKE_REPORT),
            md_link(BROWSER_SMOKE_JSON),
            md_link(READINESS_GATE_REPORT),
            *(md_link(path) for path in BROWSER_SCREENSHOTS),
            *(md_link(path) for path in (ctx["day3"], ctx["day4"], ctx["graph_report"]) if path is not None),
        ],
    }
    write(OUT / "package_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"Wrote docs/challenge_cup with {ctx['question_count']} evaluation questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
