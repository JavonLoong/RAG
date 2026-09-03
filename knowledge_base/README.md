# knowledge_base

M3 的规范资料库实现：不可变修订、人工审核、发布快照、证据切片、关键词/向量/RRF 混合检索、基础 RAG 引用、版本比较、作废、回滚和带校验 manifest 的备份恢复。

跨组稳定契约见 `docs/interface/m3-module-interfaces-v1.md`；完整运行手册见 `docs/张泽跃_M3_M6_交付说明.md`。

- M2→M3：`power-rag.m2-document.v1` 审核资料 JSON，通过 `M2HandoffService` 接收。
- M3→M4：`power-rag.m3-snapshot.v1` 已发布快照，通过 `KnowledgeBaseStore.export_snapshot()` 导出。
- M3→M5：仓库统一 `BaseRetriever`，由 `KnowledgeBaseRetriever` 实现，M5 不读取 M3 数据库表。
