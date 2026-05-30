# 顶刊目标 RAG/GraphRAG 项目技术栈与工程架构白皮书

本文件全面记录了本项目所依赖的所有技术栈，并明确区分了“第三方开源/商业技术”与“完全自研的架构体系”。同时，作为系统的全景技术档案，本文详细收录了本项目的底层工程蓝图、模块调度数据流向、LLM 运行上下文以及可观测性追踪体系的所有核心细节。本项目是一个面向顶刊论文级别、高度工程化、可复现实验的 RAG 与 GraphRAG 系统。

---

## 一、 第三方引入技术栈 (Third-Party Technologies)

### 1. 🎨 前端与可视化引擎
本项目前端主打“零构建、极速启动”，拒绝臃肿的 React/Vue 等框架。
* **核心骨架**：原生 HTML5 + Vanilla JavaScript + CSS3（玻璃拟物化设计与原生微动画）。
* **浏览器端文档解析**：**PDF.js** (PDF纯本地渲染生成 Canvas)、**PapaParse** (CSV结构化解析)、**marked.js** (Markdown 实时渲染)。
* **浏览器端端侧AI**：**ONNXRuntime-Web (WASM)**、**PaddleOCR.js (WASM)**，支持在脱离后端的情况下执行端侧 OCR。

### 2. 🧠 OCR 与文档解析底层驱动
采用多级回退机制，确保扫描件内容被 100% 提取。
* **核心本地 OCR**：**RapidOCR (ONNX Runtime)**（基于开源模型的高效本地推理引擎）。
* **对比验证 OCR**：**Tesseract-OCR**。
* **商业兜底 API**：**百度云 OCR (accurate_basic)**（仅用于复杂公式/排版的容错兜底）。
* **原生文本提取**：**PyPDF (`pypdf`)**、**python-docx**。

### 3. 💾 向量检索、图计算与大模型生态
* **向量数据库**：**ChromaDB** (`chromadb>=0.5.23`)，以 SQLite 形式本地运行，零中间件部署成本。
* **文本嵌入 (Embeddings)**：**Sentence-Transformers** + **PyTorch** (`torch`)，无缝对接 BGE 等开源表征模型。
* **词法检索引擎**：**BM25** (`rank-bm25`) + **结巴分词** (`jieba`)，用于精准术语召回。
* **图结构与运算**：**NetworkX** (`networkx`)、**Neo4j**（图数据持久化后端）、**Louvain 算法** (`python-louvain`，用于社区发现聚类)。
* **大模型交互**：`requests` / `transformers`（通过统一 HTTP 协议对接本地 Ollama 或各类云端大模型 API）。

### 4. ⚙️ 后端服务与工程化基建
* **高性能服务接口**：**FastAPI** + **Uvicorn**。
* **数据序列化**：**Orjson**（极速解析）、**Pydantic**（数据验证建模）。
* **项目与包管理**：**uv**（极速依赖管理）、**Hatchling**（PEP 621 现代构建标准）。
* **代码治理与 CI/CD**：**Ruff** (极速 Lint)、**Mypy** (静态类型)、**Pytest** (单元/集成测试)、**GitLab CI**、**MkDocs** (文档生成)。

---

## 二、 核心自研架构与算法体系 (Self-Developed Architectures)

为了达成“发顶刊、可观测、可对比消融”的目标，本项目在第三方基建之上，自主研发了庞大的中间控制层和流水线体系。以下全部为项目团队从零自研的代码模块：

### 1. 🚀 自研 OCR 调度与高并发调度层 (`data_pipeline`)
* **动态多线程 OCR 池化策略**：自研 `ThreadPoolExecutor` 并发调度器，打破 RapidOCR 的单例阻塞瓶颈。根据 CPU 核心数自动匹配（上限 12 Worker），实现 24 核机器 100% 满负荷高压吞吐。
* **文档层级切块器 (Hierarchical Chunker)**：自研分块算法，超越普通 LangChain 的无脑切块，支持按文档“标题-段落-句子”层级进行语义切分，保留严格的 Span 映射关系。
* **数据指纹与溯源机制 (Dataset Versioning)**：自研基于 Hash 的数据集去重与版本控制，确保实验复现时的语料库绝对一致。

### 2. 🕸️ 自研 GraphRAG 构图流水线 (`kg_pipeline`)
* **多跳关系与断言抽取范式**：自研全套 Prompt Template 和 `ExtractionRunner`，指导 LLM 从非结构化 chunk 中抽取实体 (Entity)、关系 (Relation) 和断言 (Claim)。
* **实体链指与冲突消解引擎 (Normalization)**：自研归一化算法，解决不同写法实体（如“燃气轮机”与“燃机”）的融合，处理知识图谱中的逻辑冲突。
* **层次化社区摘要生成器**：自研基于图谱社区发现的局部/全局摘要算法，为上层回答提供高维度的知识浓缩。

### 3. 🔍 自研混合融合检索引擎 (`retrieval_engine`)
* **多路召回与重排机制 (Hybrid Retriever & Reranker)**：自研集成层，将 Dense (向量语义)、Sparse (BM25 词法) 和 Graph (图谱邻域) 三路检索结果进行评分归一化、去重和融合互补。
* **上下文智能打包器 (Context Packer)**：自研 token 预算控制算法，在 LLM 上下文窗口限制内，精细挑选并按主题、引用来源排列最有价值的证据。

### 4. 🧠 自研 RAG 编排与幻觉守卫 (`rag_orchestrator`)
* **可追溯的引用管理器 (Citation Manager)**：自研溯源引擎，确保 LLM 生成的每一句话都映射到原始 Chunk 或图谱节点，实现 100% 来源可追踪。
* **幻觉阻断器与验证机 (Hallucination Guard)**：自研后处理模块，自动校验 LLM 输出中是否捏造了无证据支持的数值、术语或因果关系。

### 5. 🔬 自研评测与实验自动化框架 (`evaluation` & `experiments`)
* **多维指标计算系统**：自研评价体系，脱离人工评判主观性，代码级实现 Recall@k、nDCG、证据覆盖率、事实一致性 (Faithfulness) 等自动化打分。
* **全自动化消融实验脚本 (Ablation Runner)**：自研批量实验系统，一键运行“去除图谱/去除混合检索”的对比测试，自动导出可供论文直接使用的性能与成本对比图表。
* **深层可观测性埋点 (Observability)**：自研 `OperationLogger` 与 Trace 系统，追踪并统计每一次检索耗时、每一步 LLM Token 花费，实现系统级错误精准归因。

---

## 三、 全局工程蓝图与物理目录架构 (Detailed Blueprint)

以下为系统十二层核心模块的详细职责划分与包结构：

```text
rag_research_system/
├─ configs/                    # 全局配置中心：统一管理实验、模型、数据、日志、部署参数。
├─ core_domain/                # 领域语义层：定义知识单元、实体、关系、文档、问题、证据等核心数据结构。
├─ data_pipeline/              # 数据管线层：负责原始文件导入、解析、清洗、切分、版本化和质量检查。
├─ kg_pipeline/                # 知识图谱构建层：负责实体关系抽取、消歧、图谱融合、社区检测和图谱存储。
├─ retrieval_engine/           # 检索引擎层：负责向量检索、关键词检索、图检索、混合召回和重排序。
├─ rag_orchestrator/           # RAG 编排层：负责 query 理解、上下文组装、证据约束生成和答案后处理。
├─ model_adapters/             # 模型适配层：统一封装 LLM、Embedding、Reranker、抽取模型和本地/云端模型调用。
├─ storage_layer/              # 存储抽象层：统一封装 Chroma、Neo4j、文件仓库、缓存和实验结果存储。
├─ observability/              # 可观测性层：负责结构化日志、运行追踪、错误归因、性能统计和审计记录。
├─ evaluation/                 # 评测层：负责数据集构造、指标计算、消融实验、人工评估和统计显著性分析。
├─ experiments/                # 实验编排层：负责顶刊实验脚本、配置矩阵、批量运行和结果归档。
├─ paper_assets/               # 论文资产层：负责自动生成论文图表、表格、案例、附录和复现实验说明。
├─ api_server/                 # 服务接口层：对外提供上传、处理、检索、问答、评测、日志查询等 API。
├─ frontend_app/               # 前端应用层：提供实验控制台、知识图谱可视化、日志查看和结果分析界面。
├─ scripts/                    # 工程脚本层：提供启动、迁移、数据准备、批量实验、导出等命令行工具。
├─ tests/                      # 测试层：覆盖单元测试、集成测试、回归测试、性能测试和端到端测试。
└─ docs/                       # 文档层：沉淀架构说明、实验协议、数据规范、API 文档和论文计划。
```

### 3.1 核心语义层 (core_domain)
这一层是整个系统的数据“语法书”，定义所有模块共享的数据结构，避免每个模块各自发明字段。
* `documents.py`：封装 `SourceDocument`、`ParsedPage` 等类，描述原始文档信息。
* `chunks.py`：封装 `TextChunk` 等类，描述切分后的文本片段。
* `knowledge_units.py`：封装实体、关系、可验证断言 (Claim) 等。
* `graph_schema.py`：封装图谱节点、边、图社区结构。
* `queries.py` / `evidence.py` / `answers.py`：定义问题意图、检索计划、带有引用的答案证据链等结构。

### 3.2 数据管线层 (data_pipeline)
负责把 PDF、DOCX、TXT、Markdown 等文件变成可检索、可构图、可评测的结构化文本资产。
* `file_ingestion.py`：文件规范化接入与 Hash 校验。
* `parsers/pdf_parser.py`, `parsers/docx_parser.py` 等：实现具体解析器接口，保留页码和排版。
* `cleaning.py` / `chunking.py`：清洗、碎片合并、层级分块。
* `deduplication.py` / `quality_checks.py`：基于指纹的去重和质量检测（例如空文档、超大文档）。

### 3.3 知识图谱构建层 (kg_pipeline)
负责从文本中抽取实体关系，构建可查询、可解释、可评测的知识图谱，是 GraphRAG 的核心增量能力。
* `schema_design.py`：定义领域实体类型（如设备、部件、故障、工况）。
* `extraction/entity_extractor.py` & `relation_extractor.py`：调用 LLM 从 chunk 中识别实体和边。
* `normalization/entity_linker.py` & `conflict_resolver.py`：实体归一和冲突关系合并。
* `community_detection.py` & `graph_summarizer.py`：实现 Louvain 等社区发现，为全局摘要服务。

### 3.4 检索引擎层 (retrieval_engine)
负责把用户问题转成多路召回和可解释证据，包括普通 RAG、GraphRAG 和混合检索。
* `query_analysis.py`：识别查询意图和实体约束过滤条件。
* `dense_retriever.py` / `sparse_retriever.py` / `graph_retriever.py`：分别执行语义向量、BM25 和图邻域遍历。
* `hybrid_retriever.py` & `reranker.py`：多路结果去重融合及重排。
* `context_packer.py`：按来源、主题对上下文打包以适应 LLM 预算。

### 3.5 RAG 编排层 (rag_orchestrator)
负责把检索证据转成可引用、可校验、可解释的最终答案。
* `prompt_builder.py`：根据问题类型、回答风格生成 Prompt。
* `answer_generator.py`：流式生成并记录耗时成本。
* `citation_manager.py` / `hallucination_guard.py`：绑定答案句子到原文出处，校验脱离文档的幻觉。

### 3.6 实验编排层 (experiments) & 论文资产层 (paper_assets)
负责把论文中的所有实验变成可以一键复跑的流程并自动生成科研资产。
* `run_baselines.py` / `run_graphrag_variants.py` / `run_ablation_studies.py`：矩阵化管理各类对比实验与消融实验。
* `figures/architecture_diagram.py` / `performance_plots.py`：自动化脚本生成 SVG/PDF 分析图表。
* `tables/main_results_table.py`：生成主实验结果与显著性指标。

---

## 四、 核心数据流向与跨模块调用约束

### 4.1 数据构建流与图谱流
1. 用户上传文件 -> `data_pipeline/file_ingestion`
2. 调用 `parsers` 解析为文本 -> 执行 `cleaning` 和 `chunking` -> 分块写入 `document_store` / `vector_store`。
3. 从已切分的 chunk 出发 -> 调用 `kg_pipeline/extraction` 抽取实体关系。
4. 执行归一化与消歧 -> 写入图数据库 -> 运行社区发现算法产生全局摘要。

### 4.2 检索与生成流
1. 用户提问 -> `retrieval_engine/query_analysis`。
2. 同步并发请求多路 Retriever -> 执行排序和混合。
3. 把证据送入 `rag_orchestrator/context_packer` -> 拼装 Prompt -> LLM `answer_generator`。
4. 将答案绑定引用 -> 通过幻觉拦截器校验 -> 输出。

### 4.3 全局架构约束协议
- **严禁越级引用**：`core_domain/` 被所有模块依赖但不依赖任何业务逻辑；`configs/` 纯参数中心；`model_adapters/` 只做适配绝不掺杂业务；`storage_layer/` 屏蔽底层细节。
- **可观测性闭环**：所有链路必须调用 `observability/` 埋点，但日志模块绝不反向调用业务。实验评测模块 `evaluation/` 绝不能污染核心的业务服务状态。

---

## 五、 系统级 LLM 运行上下文与项目工程约定 (Context & Rules)

1. **统一双线并进逻辑**：普通 RAG 负责“Chunk检索+证据组装”；GraphRAG/KG 的核心是前置化（先执行 Construction 阶段），预先将实体、关系、Evidence 结构化，再进行在线图检索与问答。
2. **本地环境与数据集约定**：
   - 数据来源：27个已标注 JSON 数据集已经全量入库，包含 69906 个 Chunk。
   - 为了保证相互隔离避免覆盖，每个独立数据源分别生成一个独立的 ChromaDB Collection。
   - 保留的快照隔离区为 2472 条记录，2952 个 Chunk 专项分析集。
3. **环境硬性规定**：源数据 JSON 等重量级文件严格放入 `.gitignore` 不提交 Git；Windows 下的本地存储数据库路径中**严禁包含中文字符**，默认持久化映射到 `%LOCALAPPDATA%\PowerRAG\current_console` 或全英文路径下。

---

## 六、 纵深可观测性与追踪排错计划 (Observability Plan)

为了解决“文件处理慢、CPU 高、前端错误过于简单、后端缺少可定位日志”的系统级黑盒难题，本项目深入实现了工程级的错误归因系统：

### 6.1 独立的 Per-Operation 日志追踪
* **操作维度的生命周期**：新增 Per-operation `.log` 机制。用户每一次的上传、读取、解析、清洗、分块、向量入库检索和统计，都会被生成一个具备 UUID 的隔离运行日志。
* **安全穿透机制**：`/api/upload`, `/api/process`, `/api/ingest` 的响应体不再抛出绝对本地路径，而是返回受保护的 `log_file`，通过同源策略的 `/api/logs/{filename}` 被授权访问。前端屏蔽晦涩报错，保留极简摘要，仅在需要 debug 时可展开具体日志追踪树。

### 6.2 大规模/异常边缘用例追踪
* **嵌入引擎的兼容与自适应**：修正了 `HashingEmbeddingFunction.embed_query()` 对于 ChromaDB 底层批量 list 结构和单条 string 查询的双向兼容；实现对于空/异常后端的严格阻断预警。
* **无死角监控覆盖**：为 GET/POST 的 `/api/stats`, `/api/search` 等基础状态接口也接入了 Operation Log，确保任何偶发性检索延迟均能精准落位到对应的网络请求和耗时节点。
* **幂等原则**：所有异步异常处理遵循“安全 Close”原则，坚守“不滥用兜底”的铁律（当产生真实异常时，明确暴露原始堆栈而非用含糊的 Error 掩盖）。
