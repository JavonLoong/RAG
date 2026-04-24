# GraphRAG 调研阅读包

这个文件夹把 GraphRAG 调研需要看的资料分成三类：

- `00_tonight_talk_track.md`：今晚交流直接照着讲。
- `01_graphrag_research_brief.md`：GraphRAG 核心概念和技术路线。
- `02_tool_comparison.md`：典型工具对比，方便回答“我们该试哪个”。
- `03_poc_plan.md`：后续做小 demo 的方案。
- `04_source_links.md`：所有来源链接和本地文件对应关系。
- `papers/`：论文和白皮书 PDF。
- `official_docs/`：官方文档、项目 README、工具网页快照。

## 最短阅读顺序

如果只有 20 分钟：

1. 看 `00_tonight_talk_track.md`
2. 看 `01_graphrag_research_brief.md` 的“核心结论”
3. 看 `02_tool_comparison.md` 的表格

如果有 1 小时：

1. 看 `papers/2404.16130_microsoft_graphrag_from_local_to_global.pdf` 的 Abstract 和方法部分
2. 看 `official_docs/microsoft_graphrag_README.md`
3. 看 `official_docs/neo4j_kg_builder_user_guide.html`
4. 看 `03_poc_plan.md`

如果要后续真正做 demo：

1. 先试 Microsoft GraphRAG，理解完整 indexing/query 流程。
2. 再试 Neo4j GraphRAG，把实体、关系、chunk 存到图数据库。
3. 如果时间不够，用 LlamaIndex 或 LangChain 做轻量验证。

## 我的建议

今晚不要把重点放在“GraphRAG 一定比 RAG 强”上，而是说清楚边界：

GraphRAG 适合多文档、多跳关系、全局主题归纳、实体关系追踪；如果只是单文档事实问答，普通 RAG 或 hybrid RAG 往往更简单、更便宜。

