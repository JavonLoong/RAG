# 顶刊目标 RAG/GraphRAG 项目技术栈与工程架构白皮书

本文件全面记录了本项目所依赖的所有技术栈，并**明确区分了“第三方开源/商业技术”与“完全自研的架构体系”**。本项目是一个面向顶刊论文级别、高度工程化、可复现实验的 RAG (检索增强生成) 与 GraphRAG 系统。

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

为了达成“发顶刊、可观测、可对比消融”的目标，本项目在第三方基建之上，**自主研发了庞大的中间控制层和流水线体系**。以下全部为项目团队**从零自研**的代码模块：

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
