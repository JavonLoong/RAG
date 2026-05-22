# Repository Layout

## Top-level layout

```text
.
├─ configs/
├─ core_domain/
├─ data_pipeline/
│  ├─ prototype/
│  └─ datasets/
├─ kg_pipeline/
├─ retrieval_engine/
├─ rag_orchestrator/
├─ model_adapters/
├─ storage_layer/
│  └─ runtime/
├─ observability/
├─ evaluation/
├─ experiments/
├─ paper_assets/
├─ api_server/
│  └─ current_console/
├─ frontend_app/
│  └─ current_console/
├─ scripts/
├─ tests/
├─ docs/
└─ archive/
```

## What each area is for

### `api_server/`

放服务接口层。当前主应用位于 `api_server/current_console/`。

### `frontend_app/`

放前端应用层。当前控制台页面位于 `frontend_app/current_console/`，后端会优先从这里挂载静态页面。

### `storage_layer/`

放存储抽象与运行数据。当前控制台运行数据迁移到 `storage_layer/runtime/current_console/`。

### `data_pipeline/`

放数据导入、解析、清洗、切分和数据集。早期 `power_rag_pipeline` 原型迁移到 `data_pipeline/prototype/`。

### `kg_pipeline/`

放知识图谱抽取、归一、构建、社区检测和图谱摘要。

### `retrieval_engine/`

放 dense、sparse、graph、hybrid retrieval 与 rerank。

### `rag_orchestrator/`

放 query plan、prompt 构造、答案生成、引用管理和答案验证。

### `model_adapters/`

放 LLM、Embedding、Reranker、抽取模型、成本追踪和重试策略。

### `observability/`

放结构化日志、运行 trace、性能监控、错误归因和审计能力。

### `evaluation/`

放评测数据、指标、人工评估、消融实验和显著性检验。

### `experiments/`

放顶刊实验脚本、配置矩阵、规模实验和错误分析。

### `paper_assets/`

放论文图表、案例、附录、演示材料和复现实验说明。

### `scripts/`

放工程脚本，例如数据准备、服务启动、评测运行和烟测。

### `tests/`

放单元、集成、回归、性能测试。

### `docs/`

放架构文档、会议分析、调研手册、实验协议和复现文档。

### `archive/`

放历史代码和旧实验，默认不作为当前主线开发入口。

## Notes

- 原 `apps/jiwenlong-rag-console/` 已迁移到 `api_server/current_console/`。
- 原 `src/power_rag_pipeline/` 已迁移到 `data_pipeline/prototype/power_rag_pipeline/`。
- 原 `goldwind_decoded/` 已迁移到 `data_pipeline/datasets/goldwind_decoded/`。
- 原 `source.pptx` 已迁移到 `paper_assets/presentations/source.pptx`。
