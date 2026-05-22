# LLM_Context

更新时间：2026-05-22

主线：普通 RAG 负责“chunk 检索 + LLM 回答”；KG / GraphRAG 先做 construction，把实体、关系、evidence 结构化，再接图检索与回答。

已完成：14 本资料入 ChromaDB；4 本 OCR 质量较放心资料跑通 KG construction，产出 240 条 evidence-bound 三元组、102 节点图谱、SVG、graph.json、SQLite 图存储和 Neo4j Cypher。前端保留黑蓝控制台，新增“KG流程”页展示 OCR→chunk→schema→实体→关系→三元组→evidence→图谱文件。

边界：当前 KG 抽取主要是 schema 约束 + 代码规则；LLM 已可接入问答，下一步是让 LLM 按同 schema 抽取并和规则/人工审核对比。
