# 📦 纪文龙 — RAG Pipeline v2.0（合并优化版）

> **项目名称**: 动力装备知识库与智能体  
> **负责人**: 刘超老师  
> **个人方向**: 向量化存储 + 混合检索 + 前端管理  
> **最后更新**: 2026-04-14  
> **版本**: v2.0 合并优化版

---

## 🆕 v2.0 重大更新

### 架构升级：单文件 → 模块化包

```
v1.0: 向量化存储.py (732行全部逻辑)
  ↓ 吸收项目2优点重构
v2.0: chroma_rag_poc/ (8个独立模块)
      ├── schemas.py      数据结构
      ├── text_utils.py   文本工具（Unicode规范化/哈希/token估算）
      ├── parsing.py      解析（自动格式检测 + Label Studio/通用JSON）
      ├── cleaning.py     清洗（OCR碎片短文本合并）
      ├── chunking.py     分块（Title触发 + 多级断点）
      ├── embeddings.py   向量化（BGE-m3 + hashing降级）
      ├── retrieval.py    混合检索（语义+BM25+RRF融合）
      ├── rag.py          RAG端到端问答
      ├── pipeline.py     流程编排
      ├── benchmark.py    性能基准测试
      ├── api.py          FastAPI后端（Pydantic校验）
      └── __main__.py     CLI入口
```

### 合并了两个版本的最优特性

| 来源 | 吸收的功能 |
|:-----|:-----------|
| 项目2 | 模块化架构、文本规范化、自动JSON检测、内容去重、多级断点分块、hashing降级、ChromaDB资源管理、关闭telemetry、Pydantic校验、单元测试 |
| 项目1 | Title触发分块、短文本合并、BM25+语义混合检索、RRF融合排序、RAG问答、暗色前端面板、数据质量报告、批量目录解析 |

---

## 🧭 项目背景（两分钟读懂）

### 我们在做什么？

```
用户提问："燃气轮机压气机喘振时怎么处理？"
    ↓
系统从技术手册中检索最相关的段落（语义+关键词混合检索）
    ↓
（未来）大模型基于检索内容生成专业回答
```

### 数据流全景

```
PDF 技术手册
     ↓ （Label Studio 标注）
JSON 标注文件                    ← 原始数据格式
     ↓ （parsing.py 解析 + 自动格式检测）
结构化文本块 (Title/Para/List)    ← Step 1: 解析 + 去重
     ↓ （cleaning.py 短文本合并）
干净文本块                       ← Step 1.5: 清洗
     ↓ （chunking.py Title触发 + 多级断点）
Chunks                          ← Step 2: 智能分块
     ↓ （embeddings.py BGE-m3）
1024维向量                      ← Step 3: 向量化
     ↓ （pipeline.py → ChromaDB）
向量数据库                       ← 持久化存储
     ↓ （retrieval.py 语义+BM25+RRF混合检索）
检索结果                         ← Step 4: 混合检索
     ↓ （rag.py → 未来接大模型API）
自然语言回答                     ← Step 5: 生成
```

---

## 🚀 快速上手

### 方式一：直接运行（推荐）

```bash
# 启动管理面板
python app_server.py
# 浏览器打开 http://localhost:8000
```

### 方式二：模块化方式

```bash
cd chroma_rag_poc

# 安装为包
pip install -e .

# 启动服务
python -m chroma_rag_poc serve

# 入库数据
python -m chroma_rag_poc ingest --dir "../../03_数据/标注数据"

# 检索测试
python -m chroma_rag_poc search --query "燃气轮机故障诊断"

# 性能测试
python -m chroma_rag_poc benchmark

# 完整演示
python -m chroma_rag_poc demo --json-dir "../../03_数据/标注数据"
```

### 管理面板功能

- 📤 拖拽上传 JSON 文件
- ⚡ 一键处理（解析→清洗→分块→向量化→存储）
- 📊 实时查看 ChromaDB 统计
- 🔍 语义检索测试
- 📐 集合详情与来源追踪

---

## 📁 文件说明

### 核心代码（chroma_rag_poc/）

| 模块 | 说明 | 来源 |
|:-----|:-----|:-----|
| `schemas.py` | 数据结构 (TextBlock/SourceRecord/ChunkRecord) | 合并 |
| `text_utils.py` | Unicode规范化/SHA256哈希/token估算 | 项目2 |
| `parsing.py` | JSON解析 + 自动格式检测 + 去重 + 批量 | 合并 |
| `cleaning.py` | OCR碎片短文本合并 | 项目1 |
| `chunking.py` | Title触发 + 多级断点分块 | 合并 |
| `embeddings.py` | BGE-m3 + hashing降级 | 合并 |
| `retrieval.py` | BM25+语义混合检索 + RRF融合 | 项目1 |
| `rag.py` | 端到端RAG问答 | 项目1 |
| `pipeline.py` | ChromaDB管理/入库/查询/统计/质量报告 | 合并 |
| `api.py` | FastAPI后端 + Pydantic校验 | 合并 |
| `benchmark.py` | 合成数据性能基准测试 | 项目2 |
| `__main__.py` | CLI入口 (serve/ingest/search/benchmark/demo) | 合并 |

### 兼容入口

| 文件 | 说明 |
|:-----|:-----|
| `向量化存储.py` | 向后兼容入口（代理到新模块） |
| `app_server.py` | 向后兼容服务入口 |

### 测试

| 文件 | 说明 |
|:-----|:-----|
| `tests/test_pipeline.py` | 完整单元测试（7个测试用例） |

---

## 📊 技术指标

| 指标 | 数值 |
|:-----|:-----|
| 向量维度 | 1024 (BGE-m3) |
| 分块大小 | 500字符 (可配置) |
| 重叠大小 | 50字符 (可配置) |
| 检索方式 | 语义+BM25混合 (RRF融合) |
| 数据库 | ChromaDB (cosine距离) |

---

## 🗺️ 下一步计划

- [ ] 接入大模型API (DeepSeek/Qwen) — RAG真问答
- [ ] 知识图谱抽取 — Prompt+Schema / DeepKE / LightRAG
- [ ] GPU环境部署 — 解决向量化速度瓶颈
- [ ] 更多标注数据 — 上线真实文档
