# 顶刊目标 RAG/GraphRAG 工程架构与文件目录蓝图

> 目标：把当前 RAG 控制台继续推进为一套可复现实验、可观测运行、可扩展 GraphRAG 能力、可支撑顶刊论文的方法工程系统。
> 设计原则：模块高内聚、接口清晰、日志可追踪、实验可复现、评测可量化、论文图表可自动生成。

## 目录总览

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

---

## configs/：全局配置中心

统一管理不同运行环境、不同实验方案、不同模型组合和不同数据集配置，避免参数散落在代码中。

```text
configs/
├─ base.yaml
├─ local.yaml
├─ production.yaml
├─ model_registry.yaml
├─ dataset_registry.yaml
├─ retrieval_profiles.yaml
├─ graphrag_profiles.yaml
├─ evaluation_profiles.yaml
└─ logging.yaml
```

- `base.yaml`：定义系统默认配置，如默认 chunk 大小、默认 embedding 后端、默认集合名、日志目录、缓存目录等基础参数。
- `local.yaml`：定义本地开发配置，如本地 Chroma 路径、本地 Neo4j 地址、本地模型路径和小规模测试数据路径。
- `production.yaml`：定义正式运行配置，如服务端口、持久化路径、并发限制、文件大小限制、日志保留策略和安全开关。
- `model_registry.yaml`：登记所有可用模型，包括 LLM、Embedding、Reranker、实体抽取模型；字段应包含模型名、维度、上下文窗口、调用方式和成本估计。
- `dataset_registry.yaml`：登记实验数据集，包括原始文件目录、标准答案文件、任务类型、领域标签、版本号和数据许可说明。
- `retrieval_profiles.yaml`：定义不同检索方案，如 dense-only、bm25-only、hybrid、graph-neighbor、community-summary 等。
- `graphrag_profiles.yaml`：定义 GraphRAG 构图方案，如实体类型、关系类型、抽取 prompt、图社区算法、摘要策略和图数据库后端。
- `evaluation_profiles.yaml`：定义评测配置，如指标集合、top-k 范围、评测模型、人工标注协议和显著性检验方式。
- `logging.yaml`：定义日志格式、日志级别、operation log 文件名规则、敏感字段脱敏规则和保留天数。

---

## core_domain/：领域语义层

这一层是整个系统的数据“语法书”，定义所有模块共享的数据结构，避免每个模块各自发明字段。

```text
core_domain/
├─ __init__.py
├─ documents.py
├─ chunks.py
├─ knowledge_units.py
├─ graph_schema.py
├─ queries.py
├─ evidence.py
├─ answers.py
├─ metrics.py
└─ errors.py
```

- `documents.py`：封装 `SourceDocument`、`ParsedPage`、`DocumentMetadata` 等类，描述原始文档、页码、来源路径、文件类型、版本和导入时间。
- `chunks.py`：封装 `TextChunk`、`ChunkMetadata`、`ChunkSpan` 等类，描述切分后的文本片段、字符范围、token 估计、所属文档和清洗状态。
- `knowledge_units.py`：封装 `EntityMention`、`CanonicalEntity`、`RelationMention`、`Claim` 等类，表达从文本中抽取出的实体、关系和可验证断言。
- `graph_schema.py`：封装 `EntityType`、`RelationType`、`GraphNode`、`GraphEdge`、`Community` 等数据结构，定义知识图谱的节点、边、类型系统和社区结构。
- `queries.py`：封装 `UserQuery`、`QueryIntent`、`QueryPlan`、`QueryConstraint` 等类，描述用户问题、问题意图、检索计划和过滤约束。
- `evidence.py`：封装 `EvidenceItem`、`EvidenceBundle`、`Citation` 等类，描述答案引用的文本证据、图谱证据、分数、来源和可追溯路径。
- `answers.py`：封装 `GeneratedAnswer`、`AnswerSection`、`AnswerDiagnostics` 等类，表达最终答案、分段结构、引用、置信度和生成诊断信息。
- `metrics.py`：封装 `RetrievalMetricResult`、`AnswerMetricResult`、`ExperimentSummary` 等类，统一表示评测指标和实验汇总结果。
- `errors.py`：定义 `ParsingError`、`EmbeddingError`、`GraphBuildError`、`RetrievalError`、`GenerationError` 等业务异常类型，用于精确归因。

---

## data_pipeline/：数据管线层

负责把 PDF、DOCX、TXT、Markdown、CSV 等文件变成可检索、可构图、可评测的结构化文本资产。

```text
data_pipeline/
├─ __init__.py
├─ file_ingestion.py
├─ parsers/
│  ├─ __init__.py
│  ├─ base_parser.py
│  ├─ pdf_parser.py
│  ├─ docx_parser.py
│  ├─ text_parser.py
│  ├─ markdown_parser.py
│  ├─ table_parser.py
│  └─ parser_registry.py
├─ cleaning.py
├─ chunking.py
├─ deduplication.py
├─ quality_checks.py
├─ dataset_versioning.py
└─ pipeline_runner.py
```

- `file_ingestion.py`：封装 `FileIngestionService`，负责上传文件校验、文件名规范化、文件大小统计、hash 计算、保存路径生成和导入 manifest 更新。
- `parsers/base_parser.py`：定义 `BaseParser` 抽象类，规定 `parse(bytes, metadata) -> list[ParsedPage]` 接口，所有具体解析器必须实现。
- `parsers/pdf_parser.py`：封装 `PdfParser`，负责 PDF 文本提取、页码保留、表格/标题识别接口预留和解析失败的细粒度异常抛出。
- `parsers/docx_parser.py`：封装 `DocxParser`，负责 Word 段落、标题、表格、列表结构的提取，并保留原始段落顺序。
- `parsers/text_parser.py`：封装 `TextParser`，负责 TXT、日志类文本、编码探测、异常字符替换和行级结构保留。
- `parsers/markdown_parser.py`：封装 `MarkdownParser`，负责标题层级、代码块、表格、列表和普通段落的解析。
- `parsers/table_parser.py`：封装 `CsvTsvParser`，负责 CSV/TSV 表格读取、列名规范化、行记录转文本和表格元数据保留。
- `parsers/parser_registry.py`：封装 `ParserRegistry`，根据文件扩展名和 MIME 类型选择对应 parser，避免业务代码直接写 if-else。
- `cleaning.py`：封装 `TextCleaner`、`BlockMerger`，负责去除乱码、页眉页脚、重复空白、过短碎片合并和领域词保护。
- `chunking.py`：封装 `Chunker`、`HierarchicalChunker`，负责按标题、段落、句子和 token 预算生成 chunk，并保留 chunk 到原文的 span 映射。
- `deduplication.py`：封装 `DocumentDeduplicator` 和 `ChunkDeduplicator`，负责基于 hash、simhash 或 embedding 相似度去重。
- `quality_checks.py`：封装 `DataQualityChecker`，输出空文档、超大文档、异常编码、短块比例、重复比例、token 估计等质量报告。
- `dataset_versioning.py`：封装 `DatasetVersionManager`，根据文件 hash 和配置 hash 生成数据集版本，保证论文实验可复现。
- `pipeline_runner.py`：封装 `DataPipelineRunner`，串联 ingestion、parse、clean、chunk、quality check，并向 observability 写入阶段日志。

---

## kg_pipeline/：知识图谱构建层

负责从文本中抽取实体关系，构建可查询、可解释、可评测的知识图谱，是 GraphRAG 的核心增量能力。

```text
kg_pipeline/
├─ __init__.py
├─ schema_design.py
├─ extraction/
│  ├─ __init__.py
│  ├─ entity_extractor.py
│  ├─ relation_extractor.py
│  ├─ claim_extractor.py
│  ├─ prompt_templates.py
│  └─ extraction_runner.py
├─ normalization/
│  ├─ __init__.py
│  ├─ entity_linker.py
│  ├─ relation_normalizer.py
│  └─ conflict_resolver.py
├─ graph_builder.py
├─ community_detection.py
├─ graph_summarizer.py
├─ graph_quality.py
└─ graph_exporter.py
```

- `schema_design.py`：定义领域实体类型、关系类型、属性字段和约束规则，例如设备、部件、故障、原因、工况、检测指标等。
- `extraction/entity_extractor.py`：封装 `EntityExtractor`，调用 LLM 或信息抽取模型从 chunk 中识别实体 mention，并输出实体类型和置信度。
- `extraction/relation_extractor.py`：封装 `RelationExtractor`，从同一 chunk 或跨 chunk 上下文中抽取实体间关系，如“导致”“属于”“监测”“缓解”。
- `extraction/claim_extractor.py`：封装 `ClaimExtractor`，抽取可作为答案证据的自然语言断言，并绑定来源 chunk 与实体。
- `extraction/prompt_templates.py`：保存实体抽取、关系抽取、断言抽取、反思校验的 prompt 模板；模板必须版本化以支持论文复现。
- `extraction/extraction_runner.py`：封装 `ExtractionRunner`，批量调度抽取任务、控制并发、记录 token 成本、处理模型失败和重试。
- `normalization/entity_linker.py`：封装 `EntityLinker`，把不同写法的实体 mention 聚合为规范实体，例如“燃机”和“燃气轮机”的归一。
- `normalization/relation_normalizer.py`：封装 `RelationNormalizer`，把自由文本关系映射到 schema 中定义的标准关系类型。
- `normalization/conflict_resolver.py`：封装 `ConflictResolver`，处理冲突实体类型、矛盾关系、多来源证据合并和置信度更新。
- `graph_builder.py`：封装 `KnowledgeGraphBuilder`，把实体、关系、claim 和 chunk 引用合成为 `GraphNode`、`GraphEdge`，并写入图存储。
- `community_detection.py`：封装 `GraphCommunityDetector`，实现 Louvain、Leiden 或 Neo4j GDS 社区发现，为 Microsoft GraphRAG 式全局摘要服务。
- `graph_summarizer.py`：封装 `CommunitySummarizer` 和 `NodeNeighborhoodSummarizer`，生成社区摘要、实体邻域摘要和图谱层级摘要。
- `graph_quality.py`：封装 `GraphQualityChecker`，统计孤立节点、关系密度、重复实体、低置信边、幻觉关系和图谱覆盖率。
- `graph_exporter.py`：封装 `GraphExporter`，导出 Neo4j Cypher、GraphML、JSONL、论文图可视化数据和前端图谱视图数据。

---

## retrieval_engine/：检索引擎层

负责把用户问题转成多路召回和可解释证据，包括普通 RAG、GraphRAG 和混合检索。

```text
retrieval_engine/
├─ __init__.py
├─ query_analysis.py
├─ dense_retriever.py
├─ sparse_retriever.py
├─ graph_retriever.py
├─ hybrid_retriever.py
├─ reranker.py
├─ context_packer.py
├─ retrieval_diagnostics.py
└─ retrieval_service.py
```

- `query_analysis.py`：封装 `QueryAnalyzer`，识别查询意图、实体约束、时间/设备/故障类型过滤条件，并生成 `QueryPlan`。
- `dense_retriever.py`：封装 `DenseRetriever`，调用 embedding 模型和向量数据库进行 top-k 语义召回。
- `sparse_retriever.py`：封装 `SparseRetriever`，实现 BM25、关键词匹配、领域术语扩展和精确短语召回。
- `graph_retriever.py`：封装 `GraphRetriever`，基于实体链接、邻域扩展、路径搜索、社区摘要召回图谱证据。
- `hybrid_retriever.py`：封装 `HybridRetriever`，融合 dense、sparse、graph 三路召回，处理分数归一、去重和证据互补。
- `reranker.py`：封装 `Reranker`，使用 cross-encoder、LLM judge 或规则分数对候选证据重排序。
- `context_packer.py`：封装 `ContextPacker`，在 token 预算内选择最有价值证据，按来源、主题、实体关系组织上下文。
- `retrieval_diagnostics.py`：封装 `RetrievalDiagnostics`，记录每路召回数量、耗时、分数分布、被丢弃证据和最终上下文组成。
- `retrieval_service.py`：封装 `RetrievalService`，对外提供统一 `retrieve(UserQuery) -> EvidenceBundle` 接口。

---

## rag_orchestrator/：RAG 编排层

负责把检索证据转成可引用、可校验、可解释的最终答案。

```text
rag_orchestrator/
├─ __init__.py
├─ prompt_builder.py
├─ answer_generator.py
├─ citation_manager.py
├─ hallucination_guard.py
├─ answer_verifier.py
├─ answer_postprocessor.py
└─ rag_service.py
```

- `prompt_builder.py`：封装 `PromptBuilder`，根据问题类型、证据包、回答风格和引用要求生成 LLM 输入 prompt。
- `answer_generator.py`：封装 `AnswerGenerator`，调用 LLM 生成答案，并记录输入 token、输出 token、模型名、耗时和失败原因。
- `citation_manager.py`：封装 `CitationManager`，把答案中的句子绑定到 `EvidenceItem`，生成可点击引用和原文回溯信息。
- `hallucination_guard.py`：封装 `HallucinationGuard`，检查答案中是否出现无证据支持的实体、数值、因果关系和过度推断。
- `answer_verifier.py`：封装 `AnswerVerifier`，使用规则或 LLM judge 对答案完整性、引用准确性、事实一致性进行验证。
- `answer_postprocessor.py`：封装 `AnswerPostprocessor`，负责答案结构化、中文术语统一、表格生成、摘要压缩和错误提示格式化。
- `rag_service.py`：封装 `RagService`，串联 query analysis、retrieval、generation、verification，提供最终问答接口。

---

## model_adapters/：模型适配层

把不同模型的调用细节隔离起来，让业务层只关心“我要 embedding / rerank / generate / extract”。

```text
model_adapters/
├─ __init__.py
├─ base.py
├─ llm_client.py
├─ embedding_client.py
├─ reranker_client.py
├─ extraction_client.py
├─ token_counter.py
├─ cost_tracker.py
└─ retry_policy.py
```

- `base.py`：定义 `BaseModelClient`、`ModelResponse`、`ModelUsage` 等通用接口和返回结构。
- `llm_client.py`：封装 `LLMClient`，统一调用 OpenAI、本地 vLLM、Ollama 或其他云模型，支持流式和非流式输出。
- `embedding_client.py`：封装 `EmbeddingClient`，统一文本向量化接口，处理批量大小、维度校验、缓存和模型切换。
- `reranker_client.py`：封装 `RerankerClient`，统一 reranker 调用，输入 query 和候选文本，输出重排序分数。
- `extraction_client.py`：封装 `ExtractionModelClient`，服务实体关系抽取任务，支持结构化 JSON 输出和 schema 校验。
- `token_counter.py`：封装 `TokenCounter`，估算或精确计算不同模型的 token 数，支撑成本和上下文预算控制。
- `cost_tracker.py`：封装 `CostTracker`，记录每次模型调用的 token、价格、耗时和失败率，用于实验成本分析。
- `retry_policy.py`：封装 `RetryPolicy`，定义超时、限流、指数退避、最大重试次数和不可重试错误类型。

---

## storage_layer/：存储抽象层

统一封装向量库、图数据库、文件仓库、缓存和实验结果，避免业务层直接依赖具体数据库。

```text
storage_layer/
├─ __init__.py
├─ vector_store.py
├─ graph_store.py
├─ document_store.py
├─ cache_store.py
├─ experiment_store.py
├─ manifest_store.py
└─ migrations/
   ├─ 001_initial_schema.cypher
   ├─ 002_add_claim_nodes.cypher
   └─ 003_add_community_summary.cypher
```

- `vector_store.py`：封装 `VectorStore` 接口和 `ChromaVectorStore` 实现，负责 collection 创建、upsert、query、delete、stats。
- `graph_store.py`：封装 `GraphStore` 接口和 `Neo4jGraphStore` 实现，负责节点边写入、路径查询、邻域查询、社区查询和索引创建。
- `document_store.py`：封装 `DocumentStore`，负责原始文件、解析文本、chunk JSONL、质量报告和版本化数据资产的保存。
- `cache_store.py`：封装 `CacheStore`，缓存 embedding、LLM 抽取结果、社区摘要和检索中间结果，减少重复计算。
- `experiment_store.py`：封装 `ExperimentStore`，保存实验配置、运行记录、指标结果、失败日志和生成的论文表格。
- `manifest_store.py`：封装 `ManifestStore`，统一管理上传文件、处理状态、日志文件、数据版本和入库状态。
- `migrations/001_initial_schema.cypher`：定义 Neo4j 初始节点、关系、约束和索引。
- `migrations/002_add_claim_nodes.cypher`：新增 claim 节点及 claim 到 chunk/entity 的连接关系。
- `migrations/003_add_community_summary.cypher`：新增社区摘要节点、层级关系和摘要索引。

---

## observability/：可观测性层

负责让系统出错时知道错在哪里、慢在哪里、成本花在哪里。

```text
observability/
├─ __init__.py
├─ operation_logger.py
├─ tracing.py
├─ performance_monitor.py
├─ error_classifier.py
├─ audit_log.py
├─ log_reader.py
└─ dashboards.py
```

- `operation_logger.py`：封装 `OperationLogger` 和 `OperationStage`，按一次上传、处理、检索、评测生成独立 `.log` 文件。
- `tracing.py`：封装 `TraceContext`，在 API、pipeline、model、storage 之间传递 trace_id、run_id 和 request_id。
- `performance_monitor.py`：封装 `PerformanceMonitor`，统计 CPU 时间、wall time、文件大小、token 数、批量写入耗时和检索延迟。
- `error_classifier.py`：封装 `ErrorClassifier`，把异常归因为文件过大、格式不规范、解析失败、模型失败、向量库失败、图数据库失败等类别。
- `audit_log.py`：封装 `AuditLogger`，记录用户上传、删除、处理、导出、实验运行等关键操作。
- `log_reader.py`：封装 `LogReader`，提供安全读取日志摘要、过滤敏感字段和按 run_id 查询日志的能力。
- `dashboards.py`：封装后端统计聚合函数，为前端提供处理成功率、失败原因分布、平均耗时、token 成本等面板数据。

---

## evaluation/：评测层

负责用顶刊标准证明方法有效，而不是只展示 demo。

```text
evaluation/
├─ __init__.py
├─ dataset_builder.py
├─ ground_truth.py
├─ retrieval_metrics.py
├─ answer_metrics.py
├─ graph_metrics.py
├─ human_eval.py
├─ ablation.py
├─ significance_tests.py
└─ evaluation_runner.py
```

- `dataset_builder.py`：封装 `EvaluationDatasetBuilder`，从领域文档构造 query、标准答案、相关证据、实体关系标注。
- `ground_truth.py`：封装 `GroundTruthLoader`，读取人工标注、专家答案、黄金证据和图谱标准边。
- `retrieval_metrics.py`：实现 Recall@k、Precision@k、MRR、nDCG、Evidence Coverage、Graph Evidence Hit Rate 等指标。
- `answer_metrics.py`：实现答案完整性、引用准确性、faithfulness、answer relevance、LLM-as-judge 评分和人工评分聚合。
- `graph_metrics.py`：实现实体抽取 F1、关系抽取 F1、图连通性、社区模块度、图谱覆盖率、低置信边比例等指标。
- `human_eval.py`：封装 `HumanEvaluationProtocol`，定义专家打分表、双人标注一致性、冲突仲裁和导出格式。
- `ablation.py`：封装 `AblationStudyRunner`，自动运行无图谱、无 rerank、无社区摘要、不同 chunk 策略等消融实验。
- `significance_tests.py`：实现 t-test、Wilcoxon、bootstrap 置信区间等统计检验，支撑论文结论。
- `evaluation_runner.py`：封装 `EvaluationRunner`，按配置批量运行评测，写入 `ExperimentStore` 并生成报告。

---

## experiments/：实验编排层

负责把论文中的所有实验变成可以一键复跑的工程流程。

```text
experiments/
├─ __init__.py
├─ run_baselines.py
├─ run_graphrag_variants.py
├─ run_ablation_studies.py
├─ run_scalability_tests.py
├─ run_error_analysis.py
├─ configs/
│  ├─ exp_baseline.yaml
│  ├─ exp_graphrag.yaml
│  ├─ exp_ablation.yaml
│  └─ exp_scalability.yaml
└─ results/
   └─ README.md
```

- `run_baselines.py`：运行普通 RAG、BM25、dense-only、hybrid-only 等基线方法。
- `run_graphrag_variants.py`：运行 Microsoft GraphRAG 风格、Neo4j GraphRAG 风格、LlamaIndex/LangChain 快速集成风格等变体。
- `run_ablation_studies.py`：运行不同模块去除实验，量化实体关系、社区摘要、图检索、rerank 的贡献。
- `run_scalability_tests.py`：测试 10、100、1000、10000 文档规模下的构建耗时、检索延迟、存储占用和成本。
- `run_error_analysis.py`：收集失败案例，按解析失败、召回失败、图谱错误、生成幻觉、引用错误分类。
- `configs/exp_baseline.yaml`：定义基线实验矩阵，包括数据集、检索器、模型和 top-k。
- `configs/exp_graphrag.yaml`：定义 GraphRAG 实验矩阵，包括图构建策略、社区算法和图检索深度。
- `configs/exp_ablation.yaml`：定义消融实验矩阵，明确每次关闭哪些模块。
- `configs/exp_scalability.yaml`：定义可扩展性实验矩阵，包括文件规模、并发、模型批大小和数据库配置。
- `results/README.md`：说明实验结果目录结构，哪些文件可提交论文附录，哪些文件只是临时产物。

---

## paper_assets/：论文资产层

把实验结果自动转成论文图表和附录材料，减少手动整理错误。

```text
paper_assets/
├─ figures/
│  ├─ architecture_diagram.py
│  ├─ pipeline_flow.py
│  ├─ graph_visualization.py
│  └─ performance_plots.py
├─ tables/
│  ├─ main_results_table.py
│  ├─ ablation_table.py
│  ├─ error_analysis_table.py
│  └─ cost_table.py
├─ case_studies/
│  ├─ select_cases.py
│  ├─ format_case_study.py
│  └─ evidence_trace_exporter.py
└─ reproducibility/
   ├─ environment.md
   ├─ dataset_card.md
   ├─ model_card.md
   └─ experiment_protocol.md
```

- `figures/architecture_diagram.py`：根据模块定义生成系统架构图，输出 SVG/PNG/PDF。
- `figures/pipeline_flow.py`：生成数据处理、图谱构建、检索生成的流程图。
- `figures/graph_visualization.py`：从图数据库采样子图，生成论文中的知识图谱示例图。
- `figures/performance_plots.py`：读取实验结果，生成延迟、成本、规模扩展、指标对比曲线。
- `tables/main_results_table.py`：生成主实验结果表，包括各方法在多个指标上的平均值和显著性标记。
- `tables/ablation_table.py`：生成消融实验表，展示每个模块对指标的贡献。
- `tables/error_analysis_table.py`：生成错误分析表，统计不同失败类型的占比和代表案例。
- `tables/cost_table.py`：生成构图成本、查询成本、token 成本和存储成本表。
- `case_studies/select_cases.py`：按成功、失败、复杂多跳、图谱收益明显等标签筛选代表案例。
- `case_studies/format_case_study.py`：把案例整理成论文可读格式，包括问题、答案、证据、图路径和分析。
- `case_studies/evidence_trace_exporter.py`：导出答案到原文 chunk、实体、关系、社区摘要的完整证据链。
- `reproducibility/environment.md`：记录 Python、数据库、模型、硬件、依赖版本。
- `reproducibility/dataset_card.md`：记录数据来源、规模、字段、许可、隐私处理和标注协议。
- `reproducibility/model_card.md`：记录使用模型、版本、参数、推理设置和成本。
- `reproducibility/experiment_protocol.md`：记录实验步骤、随机种子、配置文件、评测指标和复现实验命令。

---

## api_server/：服务接口层

把核心能力以稳定 API 暴露给前端、实验脚本和外部调用者。

```text
api_server/
├─ __init__.py
├─ app.py
├─ routes/
│  ├─ __init__.py
│  ├─ health.py
│  ├─ uploads.py
│  ├─ processing.py
│  ├─ search.py
│  ├─ rag.py
│  ├─ graph.py
│  ├─ evaluation.py
│  └─ logs.py
├─ schemas/
│  ├─ requests.py
│  └─ responses.py
├─ dependencies.py
├─ error_handlers.py
└─ security.py
```

- `app.py`：创建 FastAPI 应用，挂载路由、中间件、CORS、静态资源和生命周期钩子。
- `routes/health.py`：提供健康检查、版本信息、依赖状态和模型可用性检查接口。
- `routes/uploads.py`：提供文件上传、上传列表、删除、manifest 查询和上传日志入口。
- `routes/processing.py`：提供数据处理、批量入库、重新处理、处理状态查询和处理结果摘要接口。
- `routes/search.py`：提供向量检索、混合检索、图检索、检索诊断接口。
- `routes/rag.py`：提供完整问答、流式回答、引用查看、答案验证和反馈接口。
- `routes/graph.py`：提供实体查询、关系查询、邻域查询、社区摘要、图谱可视化数据接口。
- `routes/evaluation.py`：提供评测任务创建、运行状态、指标结果、实验对比接口。
- `routes/logs.py`：提供同源受控的日志列表、日志摘要、单次 operation log 读取接口。
- `schemas/requests.py`：定义上传、处理、检索、问答、评测相关请求体 Pydantic 模型。
- `schemas/responses.py`：定义统一响应结构、错误结构、分页结构和日志引用结构。
- `dependencies.py`：封装依赖注入，如配置、存储连接、服务实例、logger、trace context。
- `error_handlers.py`：统一处理业务异常和系统异常，保证错误响应包含简洁信息和 `log_file`。
- `security.py`：封装同源校验、文件名校验、路径校验、日志访问控制和敏感字段脱敏。

---

## frontend_app/：前端应用层

提供一个面向实验和工程调试的控制台，而不是单纯 demo 页面。

```text
frontend_app/
├─ package.json
├─ src/
│  ├─ main.ts
│  ├─ api/
│  │  ├─ client.ts
│  │  ├─ uploads.ts
│  │  ├─ search.ts
│  │  ├─ graph.ts
│  │  └─ evaluation.ts
│  ├─ components/
│  │  ├─ UploadPanel.tsx
│  │  ├─ ProcessingSummary.tsx
│  │  ├─ SearchWorkbench.tsx
│  │  ├─ GraphViewer.tsx
│  │  ├─ EvidencePanel.tsx
│  │  ├─ EvaluationDashboard.tsx
│  │  └─ LogViewer.tsx
│  ├─ state/
│  │  ├─ uploadStore.ts
│  │  ├─ retrievalStore.ts
│  │  └─ experimentStore.ts
│  └─ styles/
│     ├─ tokens.css
│     └─ layout.css
└─ README.md
```

- `package.json`：声明前端依赖、构建脚本、测试脚本和代码格式化脚本。
- `src/main.ts`：前端入口，初始化路由、全局状态、主题和 API client。
- `src/api/client.ts`：封装 fetch/axios 客户端，统一错误处理、超时处理和 `log_file` 展示策略。
- `src/api/uploads.ts`：封装上传、删除、列表、处理接口调用。
- `src/api/search.ts`：封装普通检索、混合检索、GraphRAG 检索和问答接口。
- `src/api/graph.ts`：封装实体、关系、邻域、社区、图谱可视化接口。
- `src/api/evaluation.ts`：封装评测任务、指标结果、实验对比和论文图表数据接口。
- `src/components/UploadPanel.tsx`：文件上传与待处理队列组件，显示文件状态、大小、类型和最近日志入口。
- `src/components/ProcessingSummary.tsx`：处理结果摘要组件，显示成功/失败数量、chunk 数、耗时、错误摘要和日志入口。
- `src/components/SearchWorkbench.tsx`：检索与问答工作台，支持选择检索策略、top-k、显示答案与引用。
- `src/components/GraphViewer.tsx`：知识图谱可视化组件，显示实体节点、关系边、社区和证据路径。
- `src/components/EvidencePanel.tsx`：证据面板，展示文本证据、图证据、分数、来源和引用链。
- `src/components/EvaluationDashboard.tsx`：评测面板，展示指标曲线、实验对比、消融结果和错误分析。
- `src/components/LogViewer.tsx`：日志查看组件，只展示同源安全日志和脱敏摘要，避免把复杂日志塞进主流程。
- `src/state/uploadStore.ts`：维护上传文件、处理状态、选中文件和最近操作日志状态。
- `src/state/retrievalStore.ts`：维护检索参数、检索结果、答案、证据和诊断信息。
- `src/state/experimentStore.ts`：维护实验运行、指标、图表和评测任务状态。
- `src/styles/tokens.css`：定义颜色、字体、间距、阴影、状态色等设计 token。
- `src/styles/layout.css`：定义页面布局、面板、表格、图谱区域和响应式规则。
- `README.md`：说明前端启动、构建、环境变量和与 API 的交互方式。

---

## scripts/：工程脚本层

把常用工程操作变成命令，避免手工步骤不可复现。

```text
scripts/
├─ dev_server.py
├─ prepare_dataset.py
├─ build_index.py
├─ build_graph.py
├─ run_eval.py
├─ export_paper_assets.py
├─ migrate_neo4j.py
├─ clean_artifacts.py
└─ smoke_test.py
```

- `dev_server.py`：启动本地 API、前端和必要存储服务，并打印访问地址和日志目录。
- `prepare_dataset.py`：按配置导入原始文件，生成数据版本、质量报告和样例统计。
- `build_index.py`：批量解析、清洗、切分、embedding 并写入向量库。
- `build_graph.py`：批量抽取实体关系、归一化、构图、社区检测并写入图数据库。
- `run_eval.py`：按实验配置运行评测，并把指标写入 `ExperimentStore`。
- `export_paper_assets.py`：读取实验结果，生成论文图表、案例和附录材料。
- `migrate_neo4j.py`：执行 Cypher migration，创建图数据库约束、索引和 schema。
- `clean_artifacts.py`：清理缓存、临时日志、测试数据库和过期实验产物。
- `smoke_test.py`：快速验证上传、处理、检索、问答、日志读取是否正常。

---

## tests/：测试层

保证系统改动不会破坏论文实验和工程稳定性。

```text
tests/
├─ unit/
│  ├─ test_parsers.py
│  ├─ test_chunking.py
│  ├─ test_graph_schema.py
│  ├─ test_embedding_adapters.py
│  └─ test_metrics.py
├─ integration/
│  ├─ test_data_pipeline.py
│  ├─ test_kg_pipeline.py
│  ├─ test_retrieval_engine.py
│  ├─ test_rag_orchestrator.py
│  └─ test_api_server.py
├─ regression/
│  ├─ test_known_bad_files.py
│  ├─ test_large_files.py
│  ├─ test_log_observability.py
│  └─ test_chroma_compatibility.py
├─ performance/
│  ├─ test_indexing_speed.py
│  ├─ test_query_latency.py
│  └─ test_graph_build_scalability.py
└─ fixtures/
   ├─ sample_docs/
   ├─ sample_graphs/
   └─ sample_eval_sets/
```

- `unit/test_parsers.py`：测试各种文件解析器对正常文件、空文件、异常编码文件和格式损坏文件的处理。
- `unit/test_chunking.py`：测试 chunk 大小、overlap、标题边界、span 映射和短文本合并。
- `unit/test_graph_schema.py`：测试实体类型、关系类型、节点边结构和 schema 校验。
- `unit/test_embedding_adapters.py`：测试 embedding 维度、批量输入、单条查询输入、未知 backend 报错和缓存行为。
- `unit/test_metrics.py`：测试 Recall@k、nDCG、F1、faithfulness 等指标计算正确性。
- `integration/test_data_pipeline.py`：测试从文件上传到 chunk 生成的完整流程。
- `integration/test_kg_pipeline.py`：测试实体抽取、关系抽取、归一化、构图和图质量报告。
- `integration/test_retrieval_engine.py`：测试 dense、sparse、graph、hybrid、rerank 的组合检索结果。
- `integration/test_rag_orchestrator.py`：测试检索、prompt、生成、引用、验证的完整链路。
- `integration/test_api_server.py`：测试 API 上传、处理、检索、问答、日志接口和错误响应。
- `regression/test_known_bad_files.py`：保存历史失败文件样本，防止同类解析问题复发。
- `regression/test_large_files.py`：测试大文件、长文本、百万 token 文档的超时、日志和质量报告。
- `regression/test_log_observability.py`：测试失败时是否生成 `log_file`，日志是否包含阶段、错误类型和 traceback。
- `regression/test_chroma_compatibility.py`：测试 ChromaDB 版本升级下 embedding function 接口兼容性。
- `performance/test_indexing_speed.py`：测试不同规模下的数据处理和向量入库速度。
- `performance/test_query_latency.py`：测试不同 top-k、不同检索策略下的查询延迟。
- `performance/test_graph_build_scalability.py`：测试实体数量、边数量、社区检测规模扩展能力。
- `fixtures/sample_docs/`：保存小型测试文档。
- `fixtures/sample_graphs/`：保存小型图谱样本。
- `fixtures/sample_eval_sets/`：保存小型评测集样本。

---

## docs/：文档层

面向开发、实验、论文和复现的知识库。

```text
docs/
├─ architecture.md
├─ data_spec.md
├─ graph_schema.md
├─ api_reference.md
├─ evaluation_protocol.md
├─ experiment_plan.md
├─ observability_plan.md
├─ paper_outline.md
└─ troubleshooting.md
```

- `architecture.md`：解释系统总体架构、模块职责、关键设计取舍和扩展点。
- `data_spec.md`：定义原始文件、解析结果、chunk、metadata、manifest 的字段规范。
- `graph_schema.md`：定义实体类型、关系类型、图谱约束、示例和变更记录。
- `api_reference.md`：记录上传、处理、检索、问答、图谱、评测、日志接口。
- `evaluation_protocol.md`：记录评测数据构造、指标定义、人工评估流程和统计检验方法。
- `experiment_plan.md`：记录论文实验矩阵、基线方法、消融实验、规模实验和预期图表。
- `observability_plan.md`：记录可观测性改造、日志字段、错误分类、日志访问和排查流程。
- `paper_outline.md`：记录顶刊论文结构、创新点、实验设计、图表清单和写作进度。
- `troubleshooting.md`：记录常见故障，如文件解析失败、CPU 过高、Chroma 锁、Neo4j 连接失败、模型超时等。

---

## 模块依赖与数据流向

### 1. 数据构建流

```text
api_server/uploads
  → data_pipeline/file_ingestion
  → data_pipeline/parsers
  → data_pipeline/cleaning
  → data_pipeline/chunking
  → storage_layer/document_store
  → storage_layer/vector_store
  → observability/operation_logger
```

用户上传文件后，API 调用数据管线完成解析、清洗和分块；chunk 写入文档存储和向量库；每个阶段都向 observability 写入日志。

### 2. 知识图谱构建流

```text
storage_layer/document_store
  → kg_pipeline/extraction
  → kg_pipeline/normalization
  → kg_pipeline/graph_builder
  → storage_layer/graph_store
  → kg_pipeline/community_detection
  → kg_pipeline/graph_summarizer
```

图谱构建从已经清洗和切分的 chunk 出发，先抽取实体关系，再做归一化和冲突消解，最后写入图数据库并生成社区摘要。

### 3. 检索问答流

```text
api_server/search or api_server/rag
  → retrieval_engine/query_analysis
  → retrieval_engine/dense_retriever
  → retrieval_engine/sparse_retriever
  → retrieval_engine/graph_retriever
  → retrieval_engine/hybrid_retriever
  → retrieval_engine/context_packer
  → rag_orchestrator/answer_generator
  → rag_orchestrator/citation_manager
  → rag_orchestrator/answer_verifier
```

用户提问后，系统先分析问题，再多路召回文本和图谱证据；RAG 编排层把证据组织进 prompt，生成带引用的答案，并进行幻觉检查。

### 4. 实验评测流

```text
experiments/*
  → evaluation/evaluation_runner
  → retrieval_engine/*
  → rag_orchestrator/*
  → evaluation/*_metrics
  → storage_layer/experiment_store
  → paper_assets/*
```

实验脚本按配置批量运行不同方法，评测层计算指标，结果写入实验存储，最后由 paper_assets 自动生成论文图表和案例。

### 5. 横向依赖规则

- `core_domain/` 被所有业务模块依赖，但不依赖任何业务模块。
- `configs/` 被所有模块读取，但不包含业务逻辑。
- `model_adapters/` 只封装模型调用，不直接决定业务流程。
- `storage_layer/` 只封装存储细节，不直接做解析、抽取或生成。
- `observability/` 被所有运行链路调用，但不反向调用业务模块。
- `evaluation/` 和 `experiments/` 可以调用主系统能力，但主系统在线服务不依赖实验脚本。
- `paper_assets/` 只读取实验结果和图谱样本，不参与线上问答链路。

---

## 推荐优先落地顺序

1. 先稳定 `core_domain/`、`configs/`、`observability/`，否则后续模块会字段混乱、错误不可追。
2. 再完善 `data_pipeline/` 和 `storage_layer/`，保证数据可重复构建。
3. 然后做 `retrieval_engine/` 和 `rag_orchestrator/`，形成普通 RAG 强基线。
4. 再推进 `kg_pipeline/`，把 GraphRAG 作为方法创新主体。
5. 同步建设 `evaluation/` 和 `experiments/`，让每个方法改动都能量化。
6. 最后用 `paper_assets/` 把实验结果自动转成论文图表和案例。
