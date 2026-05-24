# RAG项目技术架构与背景资料梳理

### 一、目前采用的技术架构情况

咱们的项目整体采用了 **标准RAG + GraphRAG (知识图谱检索增强)** 双线并行的模块化架构设计。为了方便后续做实验评测、支持顶刊级别的指标量化，工程上做了深度的模块解耦。

**核心技术栈：**
- **后端框架**：Python 3.11+, FastAPI (提供 REST API), Uvicorn (ASGI 异步服务器), Pydantic (数据校验与引擎建模)
- **核心模型库**：Sentence-Transformers, Transformers, Torch
- **检索与存储引擎**：
  - **向量检索**：ChromaDB 
  - **稀疏/关键词检索**：Jieba + Rank-BM25
  - **图数据库**：Neo4j (用于 GraphRAG 的实体关系与社区存储)
- **文档解析**：PyPDF, python-docx 配合自研 Layout-aware OCR 策略
- **前端应用**：目前在 `frontend_app/current_console` 沉淀了原生前端实验控制台
- **基础设施与开发工具**（基于工程配置全量罗列）：
  - **基础运行依赖**：Numpy (科学计算), Requests (网络请求), python-dotenv (环境配置), orjson / python-multipart (高效序列化与表单解析), tqdm (进度监控)
  - **代码质量与测试**：Ruff (极速 Linter & Formatter), Mypy (静态类型检查), Pytest + pytest-cov (自动化测试与覆盖率), Pre-commit (Git提交拦截检查)
  - **项目文档与构建**：MkDocs + Material (自动化文档站生成), tox-uv / hatchling (依赖管理与打包构建)

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

---

### 三、普通 RAG 核心数据与查询流程 (Standard RAG Workflow)

为了更清晰地说明系统的运转过程，我们将技术架构拆分为“普通 RAG”和“知识图谱(KG)”两条主线。以下是普通 RAG 的运作机制：

```mermaid
graph TD
    %% 离线数据构建流程
    subgraph offline["离线数据构建流程 (Offline Pipeline)"]
        A[原始文档 PDF/Word] --> B[Layout-aware OCR 解析]
        B --> C[文本清洗与多层级 Chunking]
        C -->|向量化分支| D[Embedding 模型]
        D --> E[(ChromaDB 向量库)]
        C -->|倒排索引| F[(BM25 稀疏索引)]
    end

    %% 在线检索问答流程
    subgraph online["在线检索问答流程 (Online Pipeline)"]
        Q[用户 Query] --> R[意图识别与 Query 改写]
        R -->|向量召回| E
        R -->|关键词召回| F
        E --> S[多路召回结果]
        F --> S
        S --> T[融合去重与 Reranker 重排]
        T --> U[Top-K 高质量证据]
        U --> V[上下文组装 Prompt]
        Q -.-> V
        V --> W[LLM 生成与幻觉校验]
        W --> X[带 Citation 溯源的最终回答]
    end
```

**1. 离线数据构建流程 (Offline Data Pipeline)**
*   **文档解析**：输入各类格式文档 (PDF, Word 等)，通过自研的 Layout-aware OCR 策略进行精准解析，保留版面结构信息。
*   **分块处理**：对解析后的文本进行清洗，并执行多层级切分 (Hierarchical Chunking)。
*   **向量化入库**：将文本块通过 Embedding 模型向量化，存入 ChromaDB，同时建立倒排索引以支持 BM25 稀疏检索。

**2. 在线检索问答流程 (Online RAG Pipeline)**
*   **意图识别与改写**：接收用户的 Query，通过小模型或规则进行意图识别，并在必要时对 Query 进行扩展或改写。
*   **多路召回**：从 ChromaDB 召回语义相似的文本块，从 BM25 召回关键词匹配的文本块。
*   **融合重排 (Reranking)**：将多路召回的结果进行去重融合，通过 Reranker 模型对证据片段进行重新打分排序，筛选出最相关的 Top-K 证据。
*   **生成与溯源**：将用户的 Query 与精选的 Top-K 证据组装成 Prompt 交给 LLM 生成最终回答，并附带引用 (Citation) 的溯源信息，同时通过内置的校验机制拦截潜在幻觉。

---

### 四、知识图谱与 GraphRAG 核心流程 (KG & GraphRAG Workflow)

知识图谱线（GraphRAG）是独立于普通 RAG 的另一条重型数据管线，主要用于处理需要全局宏观视野、跨文档实体关系推理的复杂问题：

```mermaid
graph TD
    %% 离线数据构建流程
    subgraph offline["离线图谱构建流程 (Offline Pipeline)"]
        A[原始文档 PDF/Word] --> B[Layout-aware OCR 解析]
        B --> C[文本清洗与多层级 Chunking]
        C -->|图谱化分支| G[LLM 实体/关系抽取]
        G --> H[归一化处理]
        H --> I[(Neo4j 图数据库)]
        I --> J[图谱社区发现]
        J --> K[生成社区摘要]
        K --> I
    end

    %% 在线检索问答流程
    subgraph online["在线图谱检索流程 (Online Pipeline)"]
        Q[用户 Query] --> R[意图识别与 Query 改写]
        R -->|实体子图/摘要召回| I
        I --> S[图谱召回结果]
        S --> T[上下文融合与重排]
        T --> U[全局/局部高质量证据]
        U --> V[上下文组装 Prompt]
        Q -.-> V
        V --> W[LLM 生成与幻觉校验]
        W --> X[带 Citation 溯源的最终回答]
    end
```

**1. 离线图谱构建流程 (Offline KG Pipeline)**
*   **文档解析与切分**：与普通 RAG 共享底层解析逻辑，通过 OCR 和文本清洗获得干净的 Chunk 数据。
*   **知识抽取与入库**：将文本块输入大模型（LLM），抽取其中的“实体”、“关系”和“断言”三元组，经过人工校验或自动归一化处理后，将结构化数据存入 Neo4j 图数据库。
*   **图谱高级挖掘**：在图数据库中执行图谱社区发现 (Community Detection) 算法，识别局部聚集的网络结构，并利用大模型生成“社区摘要”，反向存入图库，用于支撑宏观总结性问题的回答。

**2. 在线图谱检索流程 (Online GraphRAG Pipeline)**
*   **意图识别与节点映射**：接收用户 Query，提取 Query 中的关键实体，并将其映射到图数据库中的具体节点。
*   **图谱结构召回**：根据问题类型，进行不同维度的图检索。例如针对局部问题，通过实体跳数扩展（N-hop）召回关联子图；针对宏观总结性问题，直接召回相关的图谱社区摘要。
*   **生成与溯源**：将召回的结构化三元组知识或社区摘要拼装为高信息密度的上下文，组装 Prompt 送入大模型，最终生成包含图谱级全局视野的专业回答。
