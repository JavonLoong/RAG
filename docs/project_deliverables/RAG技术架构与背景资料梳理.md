# RAG项目技术架构与背景资料梳理

### 一、目前采用的技术架构情况

咱们的项目整体采用了 **标准RAG + GraphRAG (知识图谱检索增强)** 双线并行的模块化架构设计。为了方便后续做实验评测、支持顶刊级别的指标量化，工程上做了深度的模块解耦。

**核心技术栈：**
- **后端框架**：Python 3.11+, FastAPI (提供 REST API)
- **核心模型库**：Sentence-Transformers, Transformers, Torch
- **检索与存储引擎**：
  - **向量检索**：ChromaDB 
  - **稀疏/关键词检索**：Jieba + Rank-BM25
  - **图数据库**：Neo4j (用于 GraphRAG 的实体关系与社区存储)
- **文档解析**：PyPDF, python-docx 配合自研 Layout-aware OCR 策略
- **前端应用**：目前在 `frontend_app/current_console` 沉淀了实验控制台

**系统核心分层设计（与代码目录强映射）：**
1. **数据管线层 (`data_pipeline`)**：负责各类文档的解析、OCR 高精度识别、数据清洗、多层级切分 (Chunking)，统一数据资产。
2. **知识图谱层 (`kg_pipeline`)**：GraphRAG 的核心引擎，负责调用大模型提取文本中的实体、关系和断言，处理归一化，并进行图谱社区发现 (Community Detection) 和摘要生成。
3. **检索引擎层 (`retrieval_engine`)**：负责多路召回引擎。支持 Dense (向量)、Sparse (关键词)、Graph (图检索) 三路召回，以及混合融合检索，最后通过 Reranker 输出高质量证据。
4. **RAG 编排层 (`rag_orchestrator`)**：全链路大模型调度。包含问题意图识别、上下文组装、答案生成、引用(Citation)溯源，以及针对幻觉的校验机制。
5. **模型适配层 (`model_adapters`)**：底座模型网关。统一封装了不同底座的 LLM、Embedding 和 Reranker 模型调用，自带 Token 成本和延迟追踪。
6. **评测实验层 (`evaluation` / `experiments`)**：包含自动化评测指标（如召回覆盖率、生成忠实度）和大规模消融实验矩阵。

---

### 二、前期看过的架构资料与背景文献

前期做架构调研时，主要吃透了下面四份核心资料（原文件都在仓库的 `docs/GraphRAG阅读材料/` 目录下）：

1. **理论基石与痛点解决**
   - **微软官方论文《From Local to Global: A Graph RAG Approach to Query-Focused Summarization》**：这篇是核心指导。重点借鉴了它为什么适合跨文档、如何利用局部特征解决全局宏观总结类（Global）的问题。
   - **综述《GraphRAG Survey: Retrieval-Augmented Generation with Graphs》**：全面梳理了当前 RAG 系统结合图技术的常见模块划分，帮我们避坑了业界的不同技术路线挑战。

2. **工程落地实操参考**
   - **《Neo4j GraphRAG Python Documentation》**：重型方案参考。重点看了如果要上企业级图数据库，文本、实体、关系、Embedding 是怎么协同落库的。
   - **《LlamaIndex Property Graph Index Documentation》**：轻型方案参考。借鉴了如果不部署重型 Neo4j，在 Python RAG 工程里快速搭建基于属性图（Property Graph）检索的折中方案。
