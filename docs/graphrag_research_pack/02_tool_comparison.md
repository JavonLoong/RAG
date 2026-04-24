# GraphRAG / 知识图谱抽取工具对比

| 工具 | 适合做什么 | 优点 | 风险或缺点 | 建议 |
| --- | --- | --- | --- | --- |
| Microsoft GraphRAG | 学完整 GraphRAG 流程 | indexing/query/community report/global search 流程完整 | 建图成本高，prompt tuning 重要 | 首选调研对象 |
| Neo4j GraphRAG | 落地图数据库 | 能把 Document、Chunk、Entity、Relationship 存进 Neo4j，方便图查询 | 需要理解 Neo4j、Cypher、图 schema | 首选落地对象 |
| LlamaIndex PropertyGraphIndex | 快速做 Python POC | 和 LlamaIndex ingestion/query 体系结合好 | 复杂图谱治理能力有限 | 适合快速试验 |
| LangChain LLMGraphTransformer + Neo4j | 接入已有 LangChain 项目 | 集成灵活，可生成图文档并写 Neo4j | experimental 组件较多，质量取决于 prompt 和模型 | 适合项目已有 LangChain 时使用 |
| LightRAG | 轻量、快速 RAG 变体 | 强调速度和简单部署 | 和 Microsoft GraphRAG 思路不同，需单独评估 | 作为扩展调研 |
| Graphiti | 动态/时间感知知识图谱 | 适合 agent memory 和会变化的数据 | 不专注普通文档问答，工程复杂度更高 | 作为高级方向 |
| Stanford CoreNLP OpenIE | 传统三元组抽取 | 不依赖 LLM，速度快 | 语义质量和领域适配有限 | 可作 baseline |
| spaCy | NER、依存句法、规则抽取 | 工程稳定、可训练、可加规则 | 不是完整 GraphRAG 框架 | 适合做实体预处理 |
| REBEL | 关系抽取模型 | 端到端抽取关系三元组 | 英文更合适，领域迁移需评估 | 可作为 LLM 抽取的对照 |
| Diffbot | 商业知识图谱/网页抽取 | Web 数据结构化能力强 | 商业服务，成本和数据隐私要考虑 | 了解思路即可 |

## 推荐优先级

1. Microsoft GraphRAG：先理解标准 GraphRAG 为什么这么设计。
2. Neo4j GraphRAG：再看怎么把图谱落进图数据库。
3. LlamaIndex / LangChain：最后看怎么快速集成。
4. spaCy / OpenIE / REBEL：作为“知识图谱抽取工具”的补充，不是完整 GraphRAG。

