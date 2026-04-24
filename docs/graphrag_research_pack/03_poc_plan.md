# GraphRAG POC 建议

## 目标

用一个小数据集验证 GraphRAG 是否比普通 RAG 更适合我们的场景。

## 数据

建议先选 10 到 30 篇文档，最好满足：

- 文档之间有共同实体或主题。
- 有跨文档关系，比如同一设备、同一公司、同一事件、同一问题。
- 能设计出普通 RAG 不容易完整回答的问题。

## 对比方案

做两个 baseline：

1. 普通 RAG：chunk + embedding + vector search + LLM。
2. GraphRAG：entity/relation extraction + graph/community summary + graph/vector hybrid query。

## 测试问题

问题要覆盖三类：

1. 局部事实：某个文档里提到了什么？
2. 多跳关系：A 和 B 之间通过哪些实体或事件关联？
3. 全局归纳：这批文档主要讨论了哪些主题、风险或趋势？

## 评估指标

- 答案完整性：是否覆盖问题的多个方面。
- 引用准确性：是否能回到原文来源。
- 关系可信度：实体和关系是否真实来自文本。
- 成本：建图 token 成本、查询 token 成本。
- 延迟：索引时间和查询时间。
- 维护成本：新增文档后是否容易更新。

## 建议路线

第一阶段：用 Microsoft GraphRAG 跑通官方流程，重点看输出的 entities、relationships、community reports。

第二阶段：用 Neo4j GraphRAG 或 LangChain + Neo4j 把图落库，观察图结构是否可查、可视化、可解释。

第三阶段：根据结果决定是否继续做完整系统。如果复杂问题提升不明显，就回到 hybrid RAG；如果提升明显，再投入 schema、实体归一和评估。

