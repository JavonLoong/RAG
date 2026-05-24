# LLM_Context

更新时间：2026-05-24

主线：普通 RAG 负责“chunk 检索 + LLM 基于证据回答”；KG / GraphRAG 先做 construction，把实体、关系、evidence 结构化，再接图检索与问答。

已完成：老师云盘 JSON 已下载并检测。按最新要求，27 个 JSON 已全部逐个入库，每个 JSON 一个独立 ChromaDB collection，避免互相覆盖；总计 69906 个 chunk。另保留最新快照单独入库包：2472 条记录、2952 个 chunk。

工程约定：JSON 原文件不进 GitHub。Windows 下 ChromaDB 不放中文路径，默认运行目录为 `%LOCALAPPDATA%\PowerRAG\current_console`。
