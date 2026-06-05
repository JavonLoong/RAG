from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPO_ROOT / "evaluation" / "system_eval_questions.jsonl"


def q(
    qid: str,
    question: str,
    reference_answer: str,
    keywords: list[str],
    task_type: str,
    source_scope: str,
    modes: list[str],
    grading_notes: str,
) -> dict[str, Any]:
    return {
        "id": qid,
        "question": question,
        "reference_answer": reference_answer,
        "expected_evidence_keywords": keywords,
        "task_type": task_type,
        "source_scope": source_scope,
        "expected_modes": modes,
        "grading_notes": grading_notes,
    }


ADDITIONAL_QUESTIONS: list[dict[str, Any]] = [
    q(
        "cc031",
        "为什么动力装备知识库需要同时保留 OCR 质量审计和 RAG 检索评测？",
        "OCR 质量决定可检索文本是否可靠，RAG 检索评测决定系统是否能从文本中找到证据。两者合在一起才能说明系统不是只完成了入库，而是能把扫描资料转成可追溯知识服务。",
        ["OCR", "质量审计", "RAG", "检索评测", "证据"],
        "challenge_cup_positioning",
        "challenge_cup_synthesis",
        ["keyword", "hybrid_rrf"],
        "应能说明 OCR 与检索评测分别解决数据可靠性和系统有效性问题。",
    ),
    q(
        "cc032",
        "本项目为什么不能只说自己是一个普通问答页面？",
        "项目包含资料处理、OCR 审计、ChromaDB 入库、知识图谱 POC、人工 evidence 评审、检索 baseline、失败归因和演示脚本。普通问答页面无法体现这些可复现工程链路和评测证据。",
        ["OCR", "ChromaDB", "知识图谱", "人工评审", "baseline", "失败归因"],
        "challenge_cup_positioning",
        "project_deliverables_and_evaluation_notes",
        ["keyword", "hybrid_rrf", "graphrag_context"],
        "回答需要突出工程闭环，不应只描述前端问答。",
    ),
    q(
        "cc033",
        "GraphRAG 在动力装备资料中适合解决哪一类普通 RAG 不稳定的问题？",
        "GraphRAG 更适合处理跨文档、跨实体、跨部件的关系型或归纳型问题，例如故障现象与可能原因、部件与参数、处理措施与证据之间的关联。普通 RAG 对单段事实检索更直接，但跨资料组织关系时容易漏掉结构。",
        ["GraphRAG", "跨文档", "实体", "关系", "故障", "证据"],
        "kg_graph_rag",
        "graphrag_design_docs",
        ["graphrag_context", "graphrag_global"],
        "必须说明 GraphRAG 的适用场景，而不是宣称所有问题都优于普通 RAG。",
    ),
    q(
        "cc034",
        "为什么三元组必须绑定 evidence 才能用于可信问答？",
        "三元组如果没有 evidence，就无法判断实体、关系和方向是否被原文支持，也无法在回答中追溯来源。绑定 evidence 后，评审者可以检查关系是否来自文本而不是模型臆测。",
        ["三元组", "evidence", "实体", "关系", "来源", "臆测"],
        "kg_graph_rag",
        "kg_poc_outputs",
        ["keyword", "graphrag_context"],
        "应强调证据绑定是可信性和人工评审的前提。",
    ),
    q(
        "cc035",
        "当前知识图谱 POC 的人工评审结果能证明什么，不能证明什么？",
        "它能证明候选三元组生成、evidence 绑定、人工判断和导出的闭环已经跑通，27 条候选中 26 条正确、1 条待讨论、0 条错误。它不能证明完整商业级 GraphRAG 问答系统或大规模自动抽取已经完全验证。",
        ["27", "26", "1", "0", "人工评审", "不能证明"],
        "structured_data_fact",
        "kg_poc_outputs",
        ["keyword", "graphrag_context"],
        "必须同时说清楚能证明和不能过度声称的边界。",
    ),
    q(
        "cc036",
        "为什么 9080 个 chunk 的普通 RAG 库只是起点，不是最终质量证明？",
        "9080 个 chunk 证明资料可以被清洗、切分、向量化并持久化入库，但检索质量还取决于 embedding、chunk 粒度、reranker、source scope 和评测集。当前 hashing embedding 适合证明流程，不能代表最终语义检索能力。",
        ["9080", "chunk", "embedding", "reranker", "评测", "hashing"],
        "standard_rag_fact",
        "rag_build_summary",
        ["keyword", "hybrid_rrf"],
        "应区分入库规模证明和质量证明。",
    ),
    q(
        "cc037",
        "挑战杯答辩中如何解释本项目的创新点？",
        "创新点应表述为面向动力装备资料的可信知识工程闭环：扫描资料 OCR 审计、证据绑定知识图谱、RAG/GraphRAG 同题评测、失败归因和可追溯回答，而不是简单说接入了大模型。",
        ["动力装备", "可信", "OCR", "知识图谱", "同题评测", "失败归因"],
        "challenge_cup_positioning",
        "challenge_cup_synthesis",
        ["keyword", "hybrid_rrf"],
        "回答不能把创新点简化为使用 LLM。",
    ),
    q(
        "cc038",
        "为什么项目需要保留失败案例分析？",
        "失败案例分析能说明系统不是只挑成功样例展示，而是在用评测驱动改进。它能把术语别名、结构化事实、弱 embedding、chunk 排序等问题转化成下一轮工程任务。",
        ["失败案例", "评测驱动", "术语别名", "结构化事实", "embedding", "排序"],
        "evaluation_method",
        "evaluation_framework",
        ["keyword", "hybrid_rrf"],
        "应强调失败案例是科研和工程严谨性的证据。",
    ),
    q(
        "cc039",
        "动力装备故障诊断类问题为什么需要同时返回可能原因和检查证据？",
        "故障诊断不能只给结论，必须说明相关现象、可能原因、应检查的部件或参数，以及这些内容来自哪些资料。这样才能避免模型直接替代工程师决策，并把系统定位为证据型辅助工具。",
        ["故障诊断", "可能原因", "检查", "部件", "参数", "证据"],
        "fault_reasoning",
        "fault_reports_and_maintenance_documents",
        ["hybrid_rrf", "graphrag_context"],
        "回答应保持辅助定位，不应直接下维修决策。",
    ),
    q(
        "cc040",
        "燃气轮机运行监测中温度、压力和振动信号为什么常被放在一起分析？",
        "温度、压力和振动分别反映热力状态、流动或压缩状态以及机械状态。联合分析可以帮助判断异常是否来自燃烧、压气、轴承、传感器或工况变化，而单一信号容易造成误判。",
        ["温度", "压力", "振动", "热力", "机械", "误判"],
        "fault_reasoning",
        "public_books_operation_and_fault_reports",
        ["keyword", "hybrid_rrf", "graphrag_context"],
        "应体现多参数联合分析的运维价值。",
    ),
    q(
        "cc041",
        "燃烧室相关问题为什么适合用图谱表达部件、现象和影响之间的关系？",
        "燃烧室问题往往涉及燃料、空气、温度场、压力损失、火焰稳定性、排放和下游涡轮影响。图谱可以把部件、现象、参数和影响关系显式连接，便于跨段落组织证据。",
        ["燃烧室", "燃料", "空气", "温度场", "压力损失", "关系"],
        "kg_graph_rag",
        "public_books_gas_turbine_and_combined_cycle",
        ["graphrag_context", "graphrag_global"],
        "应说明图谱表达多实体关系的优势。",
    ),
    q(
        "cc042",
        "为什么挑战杯项目书要把应用价值和技术指标同时写清楚？",
        "应用价值说明项目解决什么真实问题，技术指标说明系统完成到什么程度。只有二者同时存在，评委才能判断项目既不是空泛应用口号，也不是脱离场景的技术堆砌。",
        ["应用价值", "技术指标", "真实问题", "完成程度", "评委"],
        "challenge_cup_positioning",
        "challenge_cup_synthesis",
        ["keyword", "hybrid_rrf"],
        "应把评审视角讲清楚。",
    ),
    q(
        "cc043",
        "如果 GraphRAG 没有在所有题上超过 keyword baseline，应该如何解释？",
        "应解释为不同方法适合不同问题。keyword 对明确术语和数字事实很强，GraphRAG 更适合跨实体关系和全局归纳。项目应报告分类型结果，而不是声称 GraphRAG 对所有问题都更好。",
        ["keyword", "GraphRAG", "术语", "数字事实", "跨实体", "分类型"],
        "evaluation_method",
        "evaluation_framework",
        ["keyword", "graphrag_global"],
        "必须体现方法适用边界。",
    ),
    q(
        "cc044",
        "为什么本项目需要一页式成果总览？",
        "一页式成果总览能让评委快速看到问题、方法、数据规模、核心指标、演示路径和材料入口。它解决的是材料很多但入口分散的问题。",
        ["一页式", "问题", "方法", "数据规模", "指标", "入口"],
        "challenge_cup_positioning",
        "challenge_cup_synthesis",
        ["keyword"],
        "应解释成果总览的评审沟通价值。",
    ),
    q(
        "cc045",
        "如何证明本项目不是只做了资料搬运？",
        "需要展示从资料输入到 OCR 审计、chunk 入库、检索评测、知识图谱 evidence 评审、失败归因和演示脚本的完整链路。资料搬运只停留在收集文件，本项目强调可检索、可评测和可追溯。",
        ["OCR", "chunk", "检索评测", "evidence", "失败归因", "可追溯"],
        "challenge_cup_positioning",
        "project_deliverables_and_evaluation_notes",
        ["keyword", "hybrid_rrf"],
        "回答要明确区分资料收集和知识工程。",
    ),
    q(
        "cc046",
        "为什么技术白皮书中必须写清楚数据流？",
        "数据流说明原始资料如何经过 OCR、清洗、chunk、索引、图谱构建、检索、生成和评测。没有数据流，评委无法判断系统是否端到端跑通，也无法定位每个模块的贡献。",
        ["数据流", "OCR", "chunk", "索引", "图谱构建", "评测"],
        "challenge_cup_positioning",
        "rag_system_design_docs",
        ["keyword", "hybrid_rrf"],
        "应体现端到端可复现性。",
    ),
    q(
        "cc047",
        "为什么要在答辩中主动说明系统不替代工程师决策？",
        "动力装备运维属于高风险场景。系统应提供证据型辅助，包括可能原因、检查项和资料来源，而不是直接替代工程师做维修决策。主动说明边界能降低幻觉和安全质疑。",
        ["不替代", "工程师", "高风险", "证据型辅助", "维修决策", "安全"],
        "answer_quality",
        "challenge_cup_synthesis",
        ["keyword", "hybrid_rrf"],
        "应强调高风险应用边界。",
    ),
    q(
        "cc048",
        "GraphRAG global 更适合回答什么类型的问题？",
        "GraphRAG global 更适合跨文档、跨社区的全局归纳问题，例如总结资料中燃烧室问题主要类别、运维知识结构或故障模式分布。它不一定适合查单个精确数字。",
        ["global", "跨文档", "社区", "全局归纳", "故障模式", "精确数字"],
        "kg_graph_rag",
        "graphrag_design_docs",
        ["graphrag_global"],
        "应明确 global search 的问题类型。",
    ),
    q(
        "cc049",
        "为什么 source_scope 对评测和检索都重要？",
        "source_scope 能标记问题期望证据来自哪类资料，帮助评测时判断是否检索到正确来源，也能在检索时进行过滤或加权，减少无关材料稀释 Top-K。",
        ["source_scope", "证据", "评测", "过滤", "加权", "Top-K"],
        "evaluation_method",
        "evaluation_framework",
        ["keyword", "hybrid_rrf"],
        "应同时说明评测和检索两侧价值。",
    ),
    q(
        "cc050",
        "为什么要记录每个实验的命令和报告路径？",
        "记录命令和报告路径可以保证结果可复现、可审计。评委或后续开发者能知道某个指标来自哪个脚本、哪个数据集和哪个输出文件。",
        ["命令", "报告路径", "可复现", "可审计", "脚本", "数据集"],
        "evaluation_method",
        "challenge_cup_synthesis",
        ["keyword"],
        "应体现 reproducibility 的科研价值。",
    ),
    q(
        "cc051",
        "如果现场后端服务启动失败，演示应该如何继续？",
        "应切换到离线备用线：打开一页式成果总览、知识图谱审核页面、SVG、评测报告和答辩问答手册，用固定证据包说明系统链路，而不是现场排查环境。",
        ["离线备用", "一页式", "知识图谱", "SVG", "评测报告", "答辩"],
        "demo_reliability",
        "project_deliverables_and_evaluation_notes",
        ["keyword", "hybrid_rrf"],
        "应强调答辩现场优先保证叙事连续性。",
    ),
    q(
        "cc052",
        "为什么项目材料中要保留不能过度声称的清单？",
        "不能过度声称的清单能保证学术表述严谨，避免把 POC 说成生产系统、把 30 或 60 题评测说成最终论文 benchmark、把证据辅助说成自动维修决策。",
        ["过度声称", "严谨", "POC", "生产系统", "benchmark", "自动维修"],
        "answer_quality",
        "challenge_cup_synthesis",
        ["keyword", "hybrid_rrf"],
        "应强调学术规范和答辩风险控制。",
    ),
    q(
        "cc053",
        "为什么 hybrid 检索可能被弱 dense_hashing 稀释？",
        "当 dense_hashing 的语义质量较弱时，它返回的候选可能与问题相关性不高。RRF 融合后这些候选会占用排名位置，导致原本 keyword 能命中的强词面证据被挤出 Top-K。",
        ["hybrid", "dense_hashing", "RRF", "keyword", "Top-K", "稀释"],
        "evaluation_method",
        "evaluation_framework",
        ["keyword", "hybrid_rrf"],
        "应解释 Day4 failure analysis 中 hybrid_dilution 的含义。",
    ),
    q(
        "cc054",
        "为什么真实 embedding 和 reranker 是下一阶段质量提升重点？",
        "真实 embedding 能提升语义召回，reranker 能在候选结果中做更精细排序。当前 hashing embedding 主要用于离线可复现实验，不能代表最终语义质量。",
        ["embedding", "reranker", "语义召回", "排序", "hashing", "质量"],
        "standard_rag_process",
        "rag_system_design_docs",
        ["keyword", "hybrid_rrf"],
        "应区分可复现 baseline 和质量增强方向。",
    ),
    q(
        "cc055",
        "为什么 OCR 两栏排版会影响 RAG 入库质量？",
        "两栏排版如果被逐行错误拼接，会打乱句子顺序和段落结构，导致 chunk 中语义断裂。检索时即使命中关键词，也可能无法提供完整证据。",
        ["OCR", "两栏", "逐行", "句子顺序", "chunk", "证据"],
        "ocr_risk",
        "ocr_quality_reports",
        ["keyword", "hybrid_rrf"],
        "应说明 OCR 版面风险如何传递到 RAG。",
    ),
    q(
        "cc056",
        "为什么知识图谱关系类型不能全部写成 related_to？",
        "全部写成 related_to 会丢失组成、原因、症状、处理措施、参数指示等语义差异，图谱检索无法利用关系类型进行推理或过滤。关系类型需要少而准。",
        ["related_to", "关系类型", "原因", "症状", "处理措施", "过滤"],
        "kg_graph_rag",
        "kg_poc_outputs",
        ["graphrag_context"],
        "应强调 schema 粒度控制。",
    ),
    q(
        "cc057",
        "为什么结项验收清单要把主张映射到证据文件？",
        "验收清单把每个主张映射到具体文件、脚本、报告或演示证据，可以让评审快速核验项目完成度，避免材料散落造成可信度下降。",
        ["验收清单", "主张", "证据文件", "脚本", "报告", "完成度"],
        "challenge_cup_positioning",
        "challenge_cup_synthesis",
        ["keyword"],
        "应体现 checklist 的评审组织价值。",
    ),
    q(
        "cc058",
        "为什么本项目适合用可复现实验而不是只用主观展示来证明效果？",
        "主观展示容易只挑成功案例，可复现实验能固定问题集、方法、指标和报告路径，让不同策略在同一条件下比较，并暴露失败原因。",
        ["可复现", "问题集", "方法", "指标", "报告", "失败原因"],
        "evaluation_method",
        "evaluation_framework",
        ["keyword", "hybrid_rrf"],
        "应说明可复现实验比 demo 更有证明力。",
    ),
    q(
        "cc059",
        "项目冲击特等奖时最应该避免哪三类表述风险？",
        "应避免把 POC 说成完整生产系统，把有限评测说成最终论文 benchmark，把证据型辅助说成自动替代工程师维修决策。这三类表述都会削弱学术严谨性。",
        ["POC", "生产系统", "benchmark", "证据型辅助", "工程师", "严谨"],
        "answer_quality",
        "challenge_cup_synthesis",
        ["keyword", "hybrid_rrf"],
        "回答应列出三类风险并解释原因。",
    ),
    q(
        "cc060",
        "第一轮挑战杯升级完成后，项目应该达到什么状态？",
        "第一轮完成后应有统一的 challenge_cup 成果入口、60 题评测集、项目书、技术白皮书、实验评测报告、演示脚本、答辩问答手册、结项验收清单和可复现 runbook，并能通过测试和本地控制台验证基本健康度。",
        ["challenge_cup", "60", "项目书", "白皮书", "实验评测报告", "runbook"],
        "challenge_cup_positioning",
        "challenge_cup_synthesis",
        ["keyword", "hybrid_rrf"],
        "应总结第一轮可交付状态。",
    ),
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


def extend_questions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = normalize_existing(records)
    existing_ids = {str(item["id"]) for item in ordered}
    ordered.extend(item for item in ADDITIONAL_QUESTIONS if item["id"] not in existing_ids)
    if len(ordered) != 60:
        raise RuntimeError(f"Expected 60 questions after extension, got {len(ordered)}")
    return ordered


def main() -> int:
    questions = extend_questions(read_jsonl(DATASET))
    write_jsonl(DATASET, questions)
    print(f"Wrote {len(questions)} questions to {DATASET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
