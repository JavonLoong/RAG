# 🔬 知识图谱抽取方案 Proposal

> **项目**: 动力装备知识库与智能体 (RAG项目)
> **撰写人**: 纪文龙
> **日期**: 2026-04-14
> **状态**: 初稿 — 待组内讨论

---

## 一、背景与需求

### 1.1 项目现状

当前 Phase 1 已完成**向量化 RAG 管线**：
- Label Studio 标注 JSON → 结构化文本提取
- 文本清洗 + 智能分块（Title 触发 + overlap）
- BGE-m3 向量化 → ChromaDB 存储
- 混合检索（语义 BM25 + RRF 融合）

### 1.2 向量 RAG 的局限性

| 问题 | 示例场景 |
|:-----|:---------|
| **多跳推理困难** | "LM2500燃气轮机的压气机喘振时应如何处理？" → 需要从"LM2500"→"压气机"→"喘振"→"处置方法"跨4段落关联 |
| **实体关系缺失** | 无法回答 "哪些设备使用了相同型号的轴承？" — 因为向量检索无法捕捉结构化关系 |
| **上下文碎片化** | 分块后的语义片段间缺乏全局联系，影响综合类问题的回答质量 |
| **精确属性查询弱** | "LM2500的额定功率是多少？" — 需要精确的属性三元组支撑 |

### 1.3 知识图谱的价值

知识图谱 (KG) 将文档中的实体和关系显式建模为图结构，能够：
- ✅ 支持多跳推理和关联查询
- ✅ 提供可解释的检索路径
- ✅ 结合向量检索实现 **GraphRAG** — 图+向量混合检索
- ✅ 可视化呈现知识结构，便于专家审核

---

## 二、候选方案概览

```
                    知识图谱抽取方案
                        │
         ┌──────────────┼──────────────┐
         │              │              │
    传统 NLP 管线    LLM 驱动抽取    GraphRAG 框架
    ┌────┼────┐     ┌───┼───┐     ┌────┼────┐
    │         │     │       │     │         │
  REBEL   DeepKE  Prompt  SFT  LightRAG  nano-
  (端到端) (浙大)  (零样本) (微调)         graphrag
```

### 2.1 方案 A：REBEL — 端到端关系抽取

| 属性 | 详情 |
|:-----|:-----|
| **来源** | Babelscape, EMNLP 2021 |
| **原理** | seq2seq 模型，直接从文本生成三元组 (Subject, Predicate, Object) |
| **模型** | `Babelscape/rebel-large` (355M params) |
| **中文支持** | ⚠️ 仅英文，中文需翻译或用 mREBEL |
| **优点** | 轻量、推理速度快、不依赖外部 API |
| **缺点** | 中文支持弱、关系类型固定、工业领域术语覆盖有限 |

### 2.2 方案 B：DeepKE — 浙大开源知识抽取工具集

| 属性 | 详情 |
|:-----|:-----|
| **来源** | 浙江大学 ZJUNLP, GitHub 4.5k+ stars |
| **原理** | 模块化框架：NER + 关系抽取 + 属性抽取 |
| **模型** | 支持 BERT/RoBERTa/UIE/LLM 多种后端 |
| **中文支持** | ⭐⭐⭐⭐⭐ 原生中文，支持自定义实体/关系 schema |
| **优点** | 灵活度高、可训练专用模型、文档齐全 |
| **缺点** | 需配置训练数据、部署较重、需要 GPU |

### 2.3 方案 C：LLM Prompt 零样本抽取

| 属性 | 详情 |
|:-----|:-----|
| **原理** | 直接使用通用 LLM（Qwen/DeepSeek）+ 精心设计的 Prompt 从文本中抽取三元组 |
| **代码量** | 极少（约100行），核心是 Prompt 工程 |
| **中文支持** | ⭐⭐⭐⭐⭐ 取决于 LLM 本身 |
| **优点** | 最快上手、零训练数据、灵活适应新领域 |
| **缺点** | 幻觉风险、推理成本（API费用）、批量处理慢、结果一致性差 |
| **示例 Prompt** | 见下方 |

```
你是一个知识图谱抽取专家。从以下动力装备技术文本中抽取所有实体和关系。

输出格式（JSON数组）：
[
  {"subject": "LM2500", "predicate": "包含部件", "object": "16级轴流式压气机"},
  {"subject": "排气温度散布度", "predicate": "阈值", "object": "≤25°C"}
]

实体类型：设备、部件、参数、故障模式、维护操作、规范标准
关系类型：包含部件、性能参数、故障原因、维护方法、适用于

文本：
{chunk_text}
```

### 2.4 方案 D：Microsoft GraphRAG

| 属性 | 详情 |
|:-----|:-----|
| **来源** | Microsoft Research, 2024, GitHub 26k+ stars |
| **论文** | "From Local to Global: A Graph RAG Approach to Query-Focused Summarization" |
| **原理** | LLM 抽取实体/关系 → 构建图 → Leiden 社区检测 → 层次化摘要 → 全局/局部检索 |
| **中文支持** | ⭐⭐⭐ 需配合中文 LLM |
| **优点** | 全局理解能力最强、社区层次摘要对综合问题效果好 |
| **缺点** | Token 消耗极高（索引阶段）、不支持增量更新需全量重建、部署复杂 |

### 2.5 方案 E：LightRAG — 轻量级 GraphRAG

| 属性 | 详情 |
|:-----|:-----|
| **来源** | 香港大学 HKUDS, 2024, arXiv:2410.05779, GitHub 22k+ stars |
| **原理** | LLM 抽取 → 知识图谱 → **双层检索**（Low-level 精确实体 + High-level 主题概念）→ 混合模式 |
| **中文支持** | ⭐⭐⭐⭐ 可配 Qwen/DeepSeek |
| **优点** | **增量更新** ← 关键优势！低 API 成本、双层检索平衡精度与广度 |
| **缺点** | 社区摘要能力弱于 MS GraphRAG |

### 2.6 方案 F：nano-graphrag — 极简 Python 实现

| 属性 | 详情 |
|:-----|:-----|
| **来源** | 开源社区, GitHub 5k+ stars |
| **原理** | MS GraphRAG 的简化版，~1100行代码，支持 Local/Global 查询 |
| **后端** | LLM: OpenAI/Ollama | 向量: nano-vectordb/FAISS/Milvus | 图: NetworkX/Neo4j |
| **优点** | 代码极简易读、可深度定制、支持本地 LLM (Ollama) |
| **缺点** | 功能简化、生产稳定性待验证 |

---

## 三、综合对比分析

### 3.1 核心维度对比

| 维度 | REBEL | DeepKE | LLM Prompt | MS GraphRAG | LightRAG | nano-graphrag |
|:-----|:------|:-------|:-----------|:------------|:---------|:-------------|
| **中文支持** | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **上手速度** | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **抽取质量** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **工业领域适应** | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **增量更新** | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| **可解释性** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **部署成本** | 低 | 中 | 极低~中 | 高 | 低~中 | 低 |
| **GPU 需求** | 中 | 高 | 无(API) | 无(API) | 无(API) | 无(API) |
| **社区活跃** | ⭐⭐ | ⭐⭐⭐ | N/A | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |

### 3.2 成本估算对比

以当前数据量（~30 chunks, ~12K字符）为基准，估算处理1000个chunk的成本：

| 方案 | 索引成本 | 查询成本/次 | 总硬件需求 |
|:-----|:---------|:-----------|:-----------|
| LLM Prompt | ~¥5-15 (API) | ~¥0.05 | 无 GPU |
| LightRAG | ~¥10-30 (API) | ~¥0.1 | 无 GPU |
| MS GraphRAG | ~¥30-100 (API) | ~¥0.2 | 无 GPU |
| DeepKE | ¥0 (本地) | ¥0 | 需 8GB+ GPU |
| nano-graphrag + Ollama | ¥0 (本地) | ¥0 | 需 16GB+ RAM |

---

## 四、推荐方案

### 4.1 推荐路线：分阶段递进

#### 🥇 第一阶段（1~2周）：LLM Prompt + Neo4j

**目标**: 快速验证知识图谱对 RAG 效果的提升

```
现有 Chunks → LLM Prompt 抽取三元组
                      ↓
              Neo4j 图数据库存储
                      ↓
         图检索 + 向量检索 = 混合 RAG
```

**选择理由**:
- 零训练数据，直接复用现有 chunks
- 1-2天即可出 PoC 结果
- 可直观对比：纯向量 RAG vs 图+向量 RAG
- 代码量极少（~200行核心逻辑）

**技术栈**:
- LLM: Qwen-turbo / DeepSeek-V3 API
- 图数据库: Neo4j Community Edition (免费)
- 图可视化: Neo4j Browser / pyvis
- 向量检索: 现有 ChromaDB (不变)

#### 🥈 第二阶段（2~4周）：LightRAG 集成

**目标**: 替换手工 Prompt 抽取为自动化 GraphRAG 管线

**选择理由**:
- 增量更新 — 新文档无需重建全图
- 双层检索 — 兼顾精确查询和概念理解
- 成本可控 — 相比 MS GraphRAG 节省 3-5x Token
- 代码质量好 — 港大团队维护，文档清晰

### 4.2 备选方案

如果 LLM API 调用受限（学校网络/预算），替代路线：

```
nano-graphrag + Ollama (本地 LLM)
-- 完全离线运行，无 API 费用
-- 需要 16GB+ 内存跑 Qwen-7B 或 DeepSeek-7B 本地模型
```

---

## 五、第一阶段 PoC 实施路线

### 5.1 架构图

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│ Label Studio │───→│  向量化存储.py │───→│  ChromaDB   │─┐
│ JSON 标注数据 │    │  解析+分块    │    │  向量检索    │ │
└─────────────┘    └──────┬───────┘    └─────────────┘ │
                          │                            │
                    ┌─────▼──────┐                     │
                    │ LLM Prompt  │                     │  ┌───────────────┐
                    │ 三元组抽取   │                     ├──→  混合 RAG 检索  │
                    └─────┬──────┘                     │  │ (图+向量融合)  │
                          │                            │  └───────────────┘
                    ┌─────▼──────┐                     │
                    │   Neo4j    │─────────────────────┘
                    │   图数据库  │
                    └────────────┘
```

### 5.2 实体/关系 Schema 设计（动力装备领域）

**实体类型**:
| 类型 | 示例 |
|:-----|:-----|
| `Equipment` 设备 | LM2500燃气轮机、MAN 9L32/44CR柴油机 |
| `Component` 部件 | 压气机、燃烧室、涡轮叶片、轴承 |
| `Parameter` 参数 | 排气温度、振动值、滑油压力 |
| `FaultMode` 故障模式 | 喘振、蠕变裂纹、热点 |
| `Procedure` 操作规程 | 启动程序、A级保养、紧急停机 |
| `Standard` 规范标准 | IMO Tier III、ISO 14224 |

**关系类型**:
| 关系 | 描述 | 示例 |
|:-----|:-----|:-----|
| `HAS_COMPONENT` | 设备包含部件 | LM2500 → 16级轴流式压气机 |
| `HAS_PARAMETER` | 参数属性 | 排气温度散布度 → ≤25°C |
| `CAUSES` | 故障因果 | 进气堵塞 → 压气机喘振 |
| `REQUIRES` | 维护需求 | A级保养 → 检查进气滤清器 |
| `APPLIES_TO` | 适用范围 | 本手册 → LM2500系列 |
| `THRESHOLD` | 阈值关系 | 轴承振动 → ≤25.4mm/s |

### 5.3 预期产出

1. **对比实验**: 针对相同问题集，对比纯向量 RAG vs 图+向量 RAG 的 Top-5 准确率
2. **图谱可视化**: Neo4j 图形化展示设备-部件-故障-参数关系网络
3. **技术报告**: 记录抽取质量、图谱规模、检索效果提升数据

---

## 六、参考资源

### 论文
1. **LightRAG**: "LightRAG: Simple and Fast Retrieval-Augmented Generation" [arXiv:2410.05779](https://arxiv.org/abs/2410.05779)
2. **Microsoft GraphRAG**: "From Local to Global: A Graph RAG Approach" [arXiv:2404.16130](https://arxiv.org/abs/2404.16130)
3. **REBEL**: "REBEL: Relation Extraction By End-to-end Language generation" [EMNLP 2021]
4. **DeepKE**: "DeepKE: A Deep Learning Based Knowledge Extraction Toolkit" [EMNLP 2022 Demo]

### GitHub 仓库
| 项目 | Stars | 链接 |
|:-----|:------|:-----|
| Microsoft GraphRAG | 26k+ | [microsoft/graphrag](https://github.com/microsoft/graphrag) |
| LightRAG | 22k+ | [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) |
| nano-graphrag | 5k+ | [gusye1234/nano-graphrag](https://github.com/gusye1234/nano-graphrag) |
| DeepKE | 4.5k+ | [zjunlp/DeepKE](https://github.com/zjunlp/DeepKE) |
| REBEL | 1k+ | [Babelscape/rebel](https://github.com/Babelscape/rebel) |

### 工业领域参考
- ISO 14224: 石油和天然气工业设备可靠性和维护数据标准
- IEC 61360: 工业自动化系统数据元素类型模型

---

## 七、讨论要点

以下问题需要组内讨论确定：

1. **LLM 选型**: 使用 Qwen / DeepSeek / 智谱 哪个 API？学校是否有免费额度？
2. **图数据库**: Neo4j Community 还是用更轻量的方案（如 NetworkX 内存图）？
3. **抽取粒度**: 是以 chunk 为单位抽取，还是以完整文档为单位？
4. **评估标准**: 如何量化对比图谱 RAG vs 纯向量 RAG 的效果？需要人工标注 ground truth 吗？
5. **分工**: 继鸿和文龙各自尝试不同方案，还是协作同一方案？
