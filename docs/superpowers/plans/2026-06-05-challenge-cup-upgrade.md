# Challenge Cup Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first complete challenge-cup-ready project package for the power-equipment trusted GraphRAG system, including review-facing documents, a 60-question evaluation set, reproducibility notes, and verification commands.

**Architecture:** Keep the existing RAG/GraphRAG codebase stable and add a high-level `docs/challenge_cup/` entrypoint that aggregates current evidence from `docs/project_deliverables/`, `evaluation/reports/`, and existing scripts. Add small deterministic scripts and unit tests only where they make the package reproducible.

**Tech Stack:** Python 3.11+, pytest, JSONL, Markdown, existing `scripts/run_day3_retrieval_baselines.py`, existing `scripts/analyze_day4_failure_cases.py`, existing `evaluation/system_eval_questions.jsonl`.

---

## File Structure

Create:

- `docs/challenge_cup/README_先看这里.md`: reviewer entrypoint and reading order.
- `docs/challenge_cup/00_项目一页纸.md`: one-page positioning, contribution, evidence, and demo route.
- `docs/challenge_cup/01_挑战杯项目书.md`: project proposal narrative for challenge-cup review.
- `docs/challenge_cup/02_技术白皮书.md`: architecture, data flow, GraphRAG design, evaluation, and safety boundary.
- `docs/challenge_cup/03_实验评测报告.md`: current baseline results and planned extended evaluation structure.
- `docs/challenge_cup/04_系统演示脚本.md`: live and offline demo script.
- `docs/challenge_cup/05_答辩问答手册.md`: high-risk Q&A.
- `docs/challenge_cup/06_结项验收清单.md`: requirement-to-evidence checklist.
- `docs/challenge_cup/reproducibility/runbook.md`: commands to rerun tests and reports.
- `docs/challenge_cup/reproducibility/dataset_manifest.md`: dataset/evidence inventory.
- `docs/challenge_cup/reproducibility/command_log.md`: commands executed during package generation.
- `scripts/extend_challenge_cup_eval_questions.py`: deterministic extension from 30 to 60 questions.
- `scripts/build_challenge_cup_package.py`: deterministic Markdown package builder.
- `tests/unit/test_challenge_cup_package.py`: validates generated package and extended dataset schema.

Modify:

- `evaluation/system_eval_questions.jsonl`: expand to 60 records with required fields.
- `README.md`: add a short pointer to `docs/challenge_cup/README_先看这里.md`.

Use existing evidence:

- `docs/project_deliverables/03_普通RAG数据库_14本资料/数据库构建结果_人话版.md`
- `docs/project_deliverables/05_知识图谱POC_三元组和人工判断/人工判断小结.md`
- `docs/project_deliverables/06_汇报材料_发群和组会/RAG课程汇报_最终交付包/README_先看这里.md`
- `evaluation/reports/day3_retrieval_baseline_comparison_20260604_004434.md`
- `evaluation/reports/day4_failure_analysis_20260604_012258.md`

## Task 1: Add Package Builder Test

**Files:**

- Create: `tests/unit/test_challenge_cup_package.py`
- Create later: `scripts/build_challenge_cup_package.py`
- Create later: `scripts/extend_challenge_cup_eval_questions.py`

- [ ] **Step 1: Write the failing package and dataset tests**

Create `tests/unit/test_challenge_cup_package.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"
PACKAGE_DIR = REPO_ROOT / "docs" / "challenge_cup"


REQUIRED_DATASET_FIELDS = {
    "id",
    "question",
    "reference_answer",
    "expected_evidence_keywords",
    "task_type",
    "source_scope",
    "expected_modes",
    "grading_notes",
}


REQUIRED_PACKAGE_FILES = [
    "README_先看这里.md",
    "00_项目一页纸.md",
    "01_挑战杯项目书.md",
    "02_技术白皮书.md",
    "03_实验评测报告.md",
    "04_系统演示脚本.md",
    "05_答辩问答手册.md",
    "06_结项验收清单.md",
    "reproducibility/runbook.md",
    "reproducibility/dataset_manifest.md",
    "reproducibility/command_log.md",
]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_challenge_cup_eval_dataset_has_60_schema_complete_records() -> None:
    rows = read_jsonl(DATASET)
    assert len(rows) == 60
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    for row in rows:
        assert REQUIRED_DATASET_FIELDS <= set(row)
        assert isinstance(row["expected_evidence_keywords"], list)
        assert row["expected_evidence_keywords"]
        assert isinstance(row["expected_modes"], list)
        assert row["expected_modes"]


def test_build_challenge_cup_package_outputs_required_files() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_challenge_cup_package.py"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert "docs/challenge_cup" in result.stdout
    for relative in REQUIRED_PACKAGE_FILES:
        path = PACKAGE_DIR / relative
        assert path.exists(), relative
        text = path.read_text(encoding="utf-8")
        forbidden = ("TO" + "DO", "T" + "BD")
        assert not any(marker in text for marker in forbidden)
    one_page = (PACKAGE_DIR / "00_项目一页纸.md").read_text(encoding="utf-8")
    assert "9080" in one_page
    assert "27" in one_page
    assert "GraphRAG" in one_page
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_challenge_cup_package.py -q
```

Expected: FAIL because `evaluation/system_eval_questions.jsonl` currently has 30 records and `scripts/build_challenge_cup_package.py` does not exist.

## Task 2: Extend Evaluation Dataset to 60 Questions

**Files:**

- Create: `scripts/extend_challenge_cup_eval_questions.py`
- Modify: `evaluation/system_eval_questions.jsonl`
- Test: `tests/unit/test_challenge_cup_package.py`

- [ ] **Step 1: Create the deterministic extension script**

Create `scripts/extend_challenge_cup_eval_questions.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"


ADDITIONAL_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "cc031",
        "question": "为什么动力装备知识库需要同时保留 OCR 质量审计和 RAG 检索评测？",
        "reference_answer": "OCR 质量决定可检索文本是否可靠，RAG 检索评测决定系统是否能从文本中找到证据。两者合在一起才能说明系统不是只完成了入库，而是能把扫描资料转成可追溯知识服务。",
        "expected_evidence_keywords": ["OCR", "质量审计", "RAG", "检索评测", "证据"],
        "task_type": "challenge_cup_positioning",
        "source_scope": "challenge_cup_synthesis",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应能说明 OCR 与检索评测分别解决数据可靠性和系统有效性问题。",
    },
    {
        "id": "cc032",
        "question": "本项目为什么不能只说自己是一个普通问答页面？",
        "reference_answer": "项目包含资料处理、OCR 审计、ChromaDB 入库、知识图谱 POC、人工 evidence 评审、检索 baseline、失败归因和演示脚本。普通问答页面无法体现这些可复现工程链路和评测证据。",
        "expected_evidence_keywords": ["OCR", "ChromaDB", "知识图谱", "人工评审", "baseline", "失败归因"],
        "task_type": "challenge_cup_positioning",
        "source_scope": "project_deliverables_and_evaluation_notes",
        "expected_modes": ["keyword", "hybrid_rrf", "graphrag_context"],
        "grading_notes": "回答需要突出工程闭环，不应只描述前端问答。",
    },
    {
        "id": "cc033",
        "question": "GraphRAG 在动力装备资料中适合解决哪一类普通 RAG 不稳定的问题？",
        "reference_answer": "GraphRAG 更适合处理跨文档、跨实体、跨部件的关系型或归纳型问题，例如故障现象与可能原因、部件与参数、处理措施与证据之间的关联。普通 RAG 对单段事实检索更直接，但跨资料组织关系时容易漏掉结构。",
        "expected_evidence_keywords": ["GraphRAG", "跨文档", "实体", "关系", "故障", "证据"],
        "task_type": "kg_graph_rag",
        "source_scope": "graphrag_design_docs",
        "expected_modes": ["graphrag_context", "graphrag_global"],
        "grading_notes": "必须说明 GraphRAG 的适用场景，而不是宣称所有问题都优于普通 RAG。",
    },
    {
        "id": "cc034",
        "question": "为什么三元组必须绑定 evidence 才能用于可信问答？",
        "reference_answer": "三元组如果没有 evidence，就无法判断实体、关系和方向是否被原文支持，也无法在回答中追溯来源。绑定 evidence 后，评审者可以检查关系是否来自文本而不是模型臆测。",
        "expected_evidence_keywords": ["三元组", "evidence", "实体", "关系", "来源", "臆测"],
        "task_type": "kg_graph_rag",
        "source_scope": "kg_poc_outputs",
        "expected_modes": ["keyword", "graphrag_context"],
        "grading_notes": "应强调证据绑定是可信性和人工评审的前提。",
    },
    {
        "id": "cc035",
        "question": "当前知识图谱 POC 的人工评审结果能证明什么，不能证明什么？",
        "reference_answer": "它能证明候选三元组生成、evidence 绑定、人工判断和导出的闭环已经跑通，27 条候选中 26 条正确、1 条待讨论、0 条错误。它不能证明完整商业级 GraphRAG 问答系统或大规模自动抽取已经完全验证。",
        "expected_evidence_keywords": ["27", "26", "1", "0", "人工评审", "不能证明"],
        "task_type": "structured_data_fact",
        "source_scope": "kg_poc_outputs",
        "expected_modes": ["keyword", "graphrag_context"],
        "grading_notes": "必须同时说清楚能证明和不能过度声称的边界。",
    },
    {
        "id": "cc036",
        "question": "为什么 9080 个 chunk 的普通 RAG 库只是起点，不是最终质量证明？",
        "reference_answer": "9080 个 chunk 证明资料可以被清洗、切分、向量化并持久化入库，但检索质量还取决于 embedding、chunk 粒度、reranker、source scope 和评测集。当前 hashing embedding 适合证明流程，不能代表最终语义检索能力。",
        "expected_evidence_keywords": ["9080", "chunk", "embedding", "reranker", "评测", "hashing"],
        "task_type": "standard_rag_fact",
        "source_scope": "rag_build_summary",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应区分入库规模证明和质量证明。",
    },
    {
        "id": "cc037",
        "question": "挑战杯答辩中如何解释本项目的创新点？",
        "reference_answer": "创新点应表述为面向动力装备资料的可信知识工程闭环：扫描资料 OCR 审计、证据绑定知识图谱、RAG/GraphRAG 同题评测、失败归因和可追溯回答，而不是简单说接入了大模型。",
        "expected_evidence_keywords": ["动力装备", "可信", "OCR", "知识图谱", "同题评测", "失败归因"],
        "task_type": "challenge_cup_positioning",
        "source_scope": "challenge_cup_synthesis",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "回答不能把创新点简化为使用 LLM。",
    },
    {
        "id": "cc038",
        "question": "为什么项目需要保留失败案例分析？",
        "reference_answer": "失败案例分析能说明系统不是只挑成功样例展示，而是在用评测驱动改进。它能把术语别名、结构化事实、弱 embedding、chunk 排序等问题转化成下一轮工程任务。",
        "expected_evidence_keywords": ["失败案例", "评测驱动", "术语别名", "结构化事实", "embedding", "排序"],
        "task_type": "evaluation_method",
        "source_scope": "evaluation_framework",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应强调失败案例是科研和工程严谨性的证据。",
    },
    {
        "id": "cc039",
        "question": "动力装备故障诊断类问题为什么需要同时返回可能原因和检查证据？",
        "reference_answer": "故障诊断不能只给结论，必须说明相关现象、可能原因、应检查的部件或参数，以及这些内容来自哪些资料。这样才能避免模型直接替代工程师决策，并把系统定位为证据型辅助工具。",
        "expected_evidence_keywords": ["故障诊断", "可能原因", "检查", "部件", "参数", "证据"],
        "task_type": "fault_reasoning",
        "source_scope": "fault_reports_and_maintenance_documents",
        "expected_modes": ["hybrid_rrf", "graphrag_context"],
        "grading_notes": "回答应保持辅助定位，不应直接下维修决策。",
    },
    {
        "id": "cc040",
        "question": "燃气轮机运行监测中温度、压力和振动信号为什么常被放在一起分析？",
        "reference_answer": "温度、压力和振动分别反映热力状态、流动或压缩状态以及机械状态。联合分析可以帮助判断异常是否来自燃烧、压气、轴承、传感器或工况变化，而单一信号容易造成误判。",
        "expected_evidence_keywords": ["温度", "压力", "振动", "热力", "机械", "误判"],
        "task_type": "fault_reasoning",
        "source_scope": "public_books_operation_and_fault_reports",
        "expected_modes": ["keyword", "hybrid_rrf", "graphrag_context"],
        "grading_notes": "应体现多参数联合分析的运维价值。",
    },
    {
        "id": "cc041",
        "question": "燃烧室相关问题为什么适合用图谱表达部件、现象和影响之间的关系？",
        "reference_answer": "燃烧室问题往往涉及燃料、空气、温度场、压力损失、火焰稳定性、排放和下游涡轮影响。图谱可以把部件、现象、参数和影响关系显式连接，便于跨段落组织证据。",
        "expected_evidence_keywords": ["燃烧室", "燃料", "空气", "温度场", "压力损失", "关系"],
        "task_type": "kg_graph_rag",
        "source_scope": "public_books_gas_turbine_and_combined_cycle",
        "expected_modes": ["graphrag_context", "graphrag_global"],
        "grading_notes": "应说明图谱表达多实体关系的优势。",
    },
    {
        "id": "cc042",
        "question": "为什么挑战杯项目书要把应用价值和技术指标同时写清楚？",
        "reference_answer": "应用价值说明项目解决什么真实问题，技术指标说明系统完成到什么程度。只有二者同时存在，评委才能判断项目既不是空泛应用口号，也不是脱离场景的技术堆砌。",
        "expected_evidence_keywords": ["应用价值", "技术指标", "真实问题", "完成程度", "评委"],
        "task_type": "challenge_cup_positioning",
        "source_scope": "challenge_cup_synthesis",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应把评审视角讲清楚。",
    },
    {
        "id": "cc043",
        "question": "如果 GraphRAG 没有在所有题上超过 keyword baseline，应该如何解释？",
        "reference_answer": "应解释为不同方法适合不同问题。keyword 对明确术语和数字事实很强，GraphRAG 更适合跨实体关系和全局归纳。项目应报告分类型结果，而不是声称 GraphRAG 对所有问题都更好。",
        "expected_evidence_keywords": ["keyword", "GraphRAG", "术语", "数字事实", "跨实体", "分类型"],
        "task_type": "evaluation_method",
        "source_scope": "evaluation_framework",
        "expected_modes": ["keyword", "graphrag_global"],
        "grading_notes": "必须体现方法适用边界。",
    },
    {
        "id": "cc044",
        "question": "为什么本项目需要一页式成果总览？",
        "reference_answer": "一页式成果总览能让评委快速看到问题、方法、数据规模、核心指标、演示路径和材料入口。它解决的是材料很多但入口分散的问题。",
        "expected_evidence_keywords": ["一页式", "问题", "方法", "数据规模", "指标", "入口"],
        "task_type": "challenge_cup_positioning",
        "source_scope": "challenge_cup_synthesis",
        "expected_modes": ["keyword"],
        "grading_notes": "应解释成果总览的评审沟通价值。",
    },
    {
        "id": "cc045",
        "question": "如何证明本项目不是只做了资料搬运？",
        "reference_answer": "需要展示从资料输入到 OCR 审计、chunk 入库、检索评测、知识图谱 evidence 评审、失败归因和演示脚本的完整链路。资料搬运只停留在收集文件，本项目强调可检索、可评测和可追溯。",
        "expected_evidence_keywords": ["OCR", "chunk", "检索评测", "evidence", "失败归因", "可追溯"],
        "task_type": "challenge_cup_positioning",
        "source_scope": "project_deliverables_and_evaluation_notes",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "回答要明确区分资料收集和知识工程。",
    },
    {
        "id": "cc046",
        "question": "为什么技术白皮书中必须写清楚数据流？",
        "reference_answer": "数据流说明原始资料如何经过 OCR、清洗、chunk、索引、图谱构建、检索、生成和评测。没有数据流，评委无法判断系统是否端到端跑通，也无法定位每个模块的贡献。",
        "expected_evidence_keywords": ["数据流", "OCR", "chunk", "索引", "图谱构建", "评测"],
        "task_type": "challenge_cup_positioning",
        "source_scope": "rag_system_design_docs",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "回答应体现端到端可复现性。",
    },
    {
        "id": "cc047",
        "question": "为什么要在答辩中主动说明系统不替代工程师决策？",
        "reference_answer": "动力装备运维属于高风险场景。系统应提供证据型辅助，包括可能原因、检查项和资料来源，而不是直接替代工程师做维修决策。主动说明边界能降低幻觉和安全质疑。",
        "expected_evidence_keywords": ["不替代", "工程师", "高风险", "证据型辅助", "维修决策", "安全"],
        "task_type": "answer_quality",
        "source_scope": "challenge_cup_synthesis",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应强调高风险应用边界。",
    },
    {
        "id": "cc048",
        "question": "GraphRAG global 更适合回答什么类型的问题？",
        "reference_answer": "GraphRAG global 更适合跨文档、跨社区的全局归纳问题，例如总结资料中燃烧室问题主要类别、运维知识结构或故障模式分布。它不一定适合查单个精确数字。",
        "expected_evidence_keywords": ["global", "跨文档", "社区", "全局归纳", "故障模式", "精确数字"],
        "task_type": "kg_graph_rag",
        "source_scope": "graphrag_design_docs",
        "expected_modes": ["graphrag_global"],
        "grading_notes": "应明确 global search 的问题类型。",
    },
    {
        "id": "cc049",
        "question": "为什么 source_scope 对评测和检索都重要？",
        "reference_answer": "source_scope 能标记问题期望证据来自哪类资料，帮助评测时判断是否检索到正确来源，也能在检索时进行过滤或加权，减少无关材料稀释 Top-K。",
        "expected_evidence_keywords": ["source_scope", "证据", "评测", "过滤", "加权", "Top-K"],
        "task_type": "evaluation_method",
        "source_scope": "evaluation_framework",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应同时说明评测和检索两侧价值。",
    },
    {
        "id": "cc050",
        "question": "为什么要记录每个实验的命令和报告路径？",
        "reference_answer": "记录命令和报告路径可以保证结果可复现、可审计。评委或后续开发者能知道某个指标来自哪个脚本、哪个数据集和哪个输出文件。",
        "expected_evidence_keywords": ["命令", "报告路径", "可复现", "可审计", "脚本", "数据集"],
        "task_type": "evaluation_method",
        "source_scope": "challenge_cup_synthesis",
        "expected_modes": ["keyword"],
        "grading_notes": "应体现 reproducibility 的科研价值。",
    },
    {
        "id": "cc051",
        "question": "如果现场后端服务启动失败，演示应该如何继续？",
        "reference_answer": "应切换到离线备用线：打开一页式成果总览、知识图谱审核页面、SVG、评测报告和答辩问答手册，用固定证据包说明系统链路，而不是现场排查环境。",
        "expected_evidence_keywords": ["离线备用", "一页式", "知识图谱", "SVG", "评测报告", "答辩"],
        "task_type": "demo_reliability",
        "source_scope": "project_deliverables_and_evaluation_notes",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应强调答辩现场优先保证叙事连续性。",
    },
    {
        "id": "cc052",
        "question": "为什么项目材料中要保留不能过度声称的清单？",
        "reference_answer": "不能过度声称的清单能保证学术表述严谨，避免把 POC 说成生产系统、把 30 或 60 题评测说成最终论文 benchmark、把证据辅助说成自动维修决策。",
        "expected_evidence_keywords": ["过度声称", "严谨", "POC", "生产系统", "benchmark", "自动维修"],
        "task_type": "answer_quality",
        "source_scope": "challenge_cup_synthesis",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应强调学术规范和答辩风险控制。",
    },
    {
        "id": "cc053",
        "question": "为什么 hybrid 检索可能被弱 dense_hashing 稀释？",
        "reference_answer": "当 dense_hashing 的语义质量较弱时，它返回的候选可能与问题相关性不高。RRF 融合后这些候选会占用排名位置，导致原本 keyword 能命中的强词面证据被挤出 Top-K。",
        "expected_evidence_keywords": ["hybrid", "dense_hashing", "RRF", "keyword", "Top-K", "稀释"],
        "task_type": "evaluation_method",
        "source_scope": "evaluation_framework",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应解释 Day4 failure analysis 中 hybrid_dilution 的含义。",
    },
    {
        "id": "cc054",
        "question": "为什么真实 embedding 和 reranker 是下一阶段质量提升重点？",
        "reference_answer": "真实 embedding 能提升语义召回，reranker 能在候选结果中做更精细排序。当前 hashing embedding 主要用于离线可复现实验，不能代表最终语义质量。",
        "expected_evidence_keywords": ["embedding", "reranker", "语义召回", "排序", "hashing", "质量"],
        "task_type": "standard_rag_process",
        "source_scope": "rag_system_design_docs",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应区分可复现 baseline 和质量增强方向。",
    },
    {
        "id": "cc055",
        "question": "为什么 OCR 两栏排版会影响 RAG 入库质量？",
        "reference_answer": "两栏排版如果被逐行错误拼接，会打乱句子顺序和段落结构，导致 chunk 中语义断裂。检索时即使命中关键词，也可能无法提供完整证据。",
        "expected_evidence_keywords": ["OCR", "两栏", "逐行", "句子顺序", "chunk", "证据"],
        "task_type": "ocr_risk",
        "source_scope": "ocr_quality_reports",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应说明 OCR 版面风险如何传递到 RAG。",
    },
    {
        "id": "cc056",
        "question": "为什么知识图谱关系类型不能全部写成 related_to？",
        "reference_answer": "全部写成 related_to 会丢失组成、原因、症状、处理措施、参数指示等语义差异，图谱检索无法利用关系类型进行推理或过滤。关系类型需要少而准。",
        "expected_evidence_keywords": ["related_to", "关系类型", "原因", "症状", "处理措施", "过滤"],
        "task_type": "kg_graph_rag",
        "source_scope": "kg_poc_outputs",
        "expected_modes": ["graphrag_context"],
        "grading_notes": "应强调 schema 粒度控制。",
    },
    {
        "id": "cc057",
        "question": "为什么结项验收清单要把主张映射到证据文件？",
        "reference_answer": "验收清单把每个主张映射到具体文件、脚本、报告或演示证据，可以让评审快速核验项目完成度，避免材料散落造成可信度下降。",
        "expected_evidence_keywords": ["验收清单", "主张", "证据文件", "脚本", "报告", "完成度"],
        "task_type": "challenge_cup_positioning",
        "source_scope": "challenge_cup_synthesis",
        "expected_modes": ["keyword"],
        "grading_notes": "应体现 checklist 的评审组织价值。",
    },
    {
        "id": "cc058",
        "question": "为什么本项目适合用可复现实验而不是只用主观展示来证明效果？",
        "reference_answer": "主观展示容易只挑成功案例，可复现实验能固定问题集、方法、指标和报告路径，让不同策略在同一条件下比较，并暴露失败原因。",
        "expected_evidence_keywords": ["可复现", "问题集", "方法", "指标", "报告", "失败原因"],
        "task_type": "evaluation_method",
        "source_scope": "evaluation_framework",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应说明可复现实验比 demo 更有证明力。",
    },
    {
        "id": "cc059",
        "question": "项目冲击特等奖时最应该避免哪三类表述风险？",
        "reference_answer": "应避免把 POC 说成完整生产系统，把有限评测说成最终论文 benchmark，把证据型辅助说成自动替代工程师维修决策。这三类表述都会削弱学术严谨性。",
        "expected_evidence_keywords": ["POC", "生产系统", "benchmark", "证据型辅助", "工程师", "严谨"],
        "task_type": "answer_quality",
        "source_scope": "challenge_cup_synthesis",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "回答应列出三类风险并解释原因。",
    },
    {
        "id": "cc060",
        "question": "第一轮挑战杯升级完成后，项目应该达到什么状态？",
        "reference_answer": "第一轮完成后应有统一的 challenge_cup 成果入口、60 题评测集、项目书、技术白皮书、实验评测报告、演示脚本、答辩问答手册、结项验收清单和可复现 runbook，并能通过测试和本地控制台验证基本健康度。",
        "expected_evidence_keywords": ["challenge_cup", "60", "项目书", "白皮书", "实验评测报告", "runbook"],
        "task_type": "challenge_cup_positioning",
        "source_scope": "challenge_cup_synthesis",
        "expected_modes": ["keyword", "hybrid_rrf"],
        "grading_notes": "应总结第一轮可交付状态。",
    },
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records).rstrip() + "\n",
        encoding="utf-8",
    )


def normalize_existing(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item.setdefault("expected_modes", ["keyword", "hybrid_rrf"])
        normalized.append(item)
    return normalized


def main() -> int:
    current = normalize_existing(read_jsonl(DATASET))
    by_id = {str(item["id"]): item for item in current}
    for item in ADDITIONAL_QUESTIONS:
        by_id[item["id"]] = item
    ordered = [by_id[item["id"]] for item in current]
    existing_ids = {item["id"] for item in ordered}
    ordered.extend(item for item in ADDITIONAL_QUESTIONS if item["id"] not in existing_ids)
    if len(ordered) != 60:
        raise RuntimeError(f"Expected 60 questions after extension, got {len(ordered)}")
    write_jsonl(DATASET, ordered)
    print(f"Wrote {len(ordered)} questions to {DATASET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the extension script**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/extend_challenge_cup_eval_questions.py
```

Expected: prints `Wrote 60 questions to D:\虚拟C盘\RAG\evaluation\system_eval_questions.jsonl`.

- [ ] **Step 3: Run the dataset part of the test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_challenge_cup_package.py::test_challenge_cup_eval_dataset_has_60_schema_complete_records -q
```

Expected: PASS.

- [ ] **Step 4: Commit dataset extension**

Run:

```powershell
git add evaluation/system_eval_questions.jsonl scripts/extend_challenge_cup_eval_questions.py tests/unit/test_challenge_cup_package.py
git commit -m "test: define challenge cup evaluation dataset"
```

Expected: commit succeeds with only these files staged.

## Task 3: Build Challenge Cup Documentation Package

**Files:**

- Create: `scripts/build_challenge_cup_package.py`
- Create generated docs under `docs/challenge_cup/`
- Test: `tests/unit/test_challenge_cup_package.py`

- [ ] **Step 1: Create the package builder script**

Create `scripts/build_challenge_cup_package.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "docs" / "challenge_cup"
REPRO = OUT / "reproducibility"
REPORTS = REPO_ROOT / "evaluation" / "reports"
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"


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


def md_link(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def build_context() -> dict[str, Any]:
    return {
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "question_count": count_jsonl(DATASET),
        "day3": latest("day3_retrieval_baseline_comparison_*.md"),
        "day4": latest("day4_failure_analysis_*.md"),
        "rag_db": REPO_ROOT / "docs" / "project_deliverables" / "03_普通RAG数据库_14本资料" / "数据库构建结果_人话版.md",
        "kg_review": REPO_ROOT / "docs" / "project_deliverables" / "05_知识图谱POC_三元组和人工判断" / "人工判断小结.md",
        "course_pack": REPO_ROOT / "docs" / "project_deliverables" / "06_汇报材料_发群和组会" / "RAG课程汇报_最终交付包" / "README_先看这里.md",
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
8. `reproducibility/runbook.md`

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

当前已完成资料处理、普通 RAG 数据库、知识图谱 POC、30 题 baseline、失败分析和课程汇报包。第一轮挑战杯升级将评测集扩展到 60 题，并建立统一成果入口。
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
    day3 = ctx["day3"]
    day4 = ctx["day4"]
    day3_ref = md_link(day3) if day3 else "未找到 Day3 报告"
    day4_ref = md_link(day4) if day4 else "未找到 Day4 报告"
    return f"""# 实验评测报告

## 评测集

当前系统评测集包含 {ctx["question_count"]} 题，覆盖普通 RAG、OCR 风险、GraphRAG/知识图谱、结构化事实、评测方法和挑战杯答辩口径。

## 已有 baseline

Day3 已比较 keyword、dense_hashing 和 hybrid_rrf 三种离线检索策略。报告位置：`{day3_ref}`。

## 失败归因

Day4 已将弱命中和失败案例归类为术语别名、结构化事实、hybrid 稀释、排序差距和评测概念缺口等问题。报告位置：`{day4_ref}`。

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
"""


def build_dataset_manifest(ctx: dict[str, Any]) -> str:
    return f"""# 数据集与证据清单

- 系统评测集：`evaluation/system_eval_questions.jsonl`，{ctx["question_count"]} 题。
- 普通 RAG 数据库说明：`{md_link(ctx["rag_db"])}`。
- 知识图谱人工评审：`{md_link(ctx["kg_review"])}`。
- Day3 baseline：`{md_link(ctx["day3"]) if ctx["day3"] else "未找到"}`。
- Day4 失败分析：`{md_link(ctx["day4"]) if ctx["day4"] else "未找到"}`。
- 课程最终交付包：`{md_link(ctx["course_pack"])}`。
"""


def build_command_log(ctx: dict[str, Any]) -> str:
    return f"""# 命令记录

生成时间：{ctx["now"]}

已记录的推荐命令见 `runbook.md`。本文件用于后续追加真实执行输出和报告路径。
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
    write(REPRO / "runbook.md", build_runbook(ctx))
    write(REPRO / "dataset_manifest.md", build_dataset_manifest(ctx))
    write(REPRO / "command_log.md", build_command_log(ctx))
    manifest = {
        "generated_at": ctx["now"],
        "output_dir": md_link(OUT),
        "question_count": ctx["question_count"],
    }
    write(OUT / "package_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"Wrote docs/challenge_cup with {ctx['question_count']} evaluation questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the package builder**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_package.py
```

Expected: prints `Wrote docs/challenge_cup with 60 evaluation questions`.

- [ ] **Step 3: Run the package test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_challenge_cup_package.py::test_build_challenge_cup_package_outputs_required_files -q
```

Expected: PASS.

- [ ] **Step 4: Commit documentation package**

Run:

```powershell
git add scripts/build_challenge_cup_package.py docs/challenge_cup tests/unit/test_challenge_cup_package.py
git commit -m "docs: add challenge cup deliverable package"
```

Expected: commit succeeds with only package files staged.

## Task 4: Add Challenge Cup Entry Link to Root README

**Files:**

- Modify: `README.md`
- Test: manual grep

- [ ] **Step 1: Add a concise entry section near the top of `README.md`**

Insert after the opening project description:

```markdown
## 挑战杯 / 结项评审入口

挑战杯与结项材料入口见 [`docs/challenge_cup/README_先看这里.md`](docs/challenge_cup/README_先看这里.md)。该目录把项目一页纸、挑战杯项目书、技术白皮书、实验评测报告、系统演示脚本、答辩问答手册和结项验收清单集中到一个评审入口。
```

- [ ] **Step 2: Verify the README contains the entry**

Run:

```powershell
rg "docs/challenge_cup/README_先看这里.md|挑战杯 / 结项评审入口" README.md
```

Expected: both patterns appear.

- [ ] **Step 3: Commit README entry**

Run:

```powershell
git add README.md
git commit -m "docs: link challenge cup review entry"
```

Expected: commit succeeds with only `README.md` staged.

## Task 5: Regenerate Baseline Reports on the 60-Question Set

**Files:**

- Modify generated outputs under `evaluation/reports/`
- Modify generated summaries under `docs/project_deliverables/06_汇报材料_发群和组会/`
- Modify generated docs under `docs/challenge_cup/`

- [ ] **Step 1: Run Day3 baseline**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/run_day3_retrieval_baselines.py --dataset evaluation/system_eval_questions.jsonl --top-k 5
```

Expected:

- Prints `Corpus chunks: ...`
- Writes `evaluation/reports/day3_retrieval_baseline_comparison_<timestamp>.md`
- Writes `evaluation/reports/day3_retrieval_baseline_comparison_<timestamp>.json`

- [ ] **Step 2: Run Day4 failure analysis**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/analyze_day4_failure_cases.py
```

Expected:

- Prints `Wrote JSON report: ...`
- Prints `Wrote Markdown report: ...`
- Prints `Analyzed cases: ...`

- [ ] **Step 3: Rebuild challenge cup package so report links point to latest outputs**

Run:

```powershell
.\.venv\Scripts\python.exe scripts/build_challenge_cup_package.py
```

Expected: `docs/challenge_cup/03_实验评测报告.md` references latest Day3 and Day4 reports.

- [ ] **Step 4: Run package test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_challenge_cup_package.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit regenerated reports**

Run:

```powershell
git add evaluation/reports docs/project_deliverables/06_汇报材料_发群和组会 docs/challenge_cup
git commit -m "docs: refresh challenge cup evaluation reports"
```

Expected: commit succeeds with generated reports and docs only.

## Task 6: Full Verification

**Files:**

- No new files unless test logs are manually copied into `docs/challenge_cup/reproducibility/command_log.md`.

- [ ] **Step 1: Run unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```

Expected: all unit tests pass, including `test_challenge_cup_package.py`.

- [ ] **Step 2: Run console backend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest api_server/current_console/chroma_rag_poc/tests -q
```

Expected: all console backend tests pass.

- [ ] **Step 3: Inspect final status without reverting unrelated changes**

Run:

```powershell
git status --short --branch
```

Expected: challenge-cup commits are cleanly recorded. Pre-existing unrelated modified/deleted/untracked files may still appear and must not be reverted.

- [ ] **Step 4: Final completion note for this implementation phase**

Record in final response:

- Design spec path and commit.
- Implementation plan path.
- Challenge cup package path.
- Tests run and results.
- Remaining high-award work: GraphRAG local/global same-question report, real embedding/reranker experiment, polished PPT, and live browser verification.

## Self-Review

Spec coverage:

- `docs/challenge_cup/` deliverables are covered by Tasks 3 and 4.
- 60-question dataset is covered by Task 2.
- Existing baseline reuse and regenerated reports are covered by Task 5.
- Engineering stability and verification are covered by Task 6.
- Scope exclusions from the design spec are respected: no frontend rewrite, no production auth system, no cloud deployment, no production Neo4j claim, no model training.

Placeholder scan:

- This plan uses no unresolved placeholder markers or deferred-detail steps.
- Each script-creation step includes complete code.
- Each verification step includes exact commands and expected outcomes.

Type consistency:

- Dataset field names match `REQUIRED_DATASET_FIELDS`.
- Script paths match the file structure.
- Generated package filenames match the test's `REQUIRED_PACKAGE_FILES`.
