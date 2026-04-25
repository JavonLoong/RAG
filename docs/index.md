# Power Equipment RAG Research System

这份文档对应重新整理后的 RAG/GraphRAG 顶刊工程工作区。

## 当前仓库定位

仓库现在按核心能力拆分，而不是按“临时代码/应用/脚本”混放：

1. `api_server/`：当前可运行 RAG 控制台后端与服务接口。
2. `frontend_app/`：当前控制台前端与后续可视化应用。
3. `data_pipeline/`：文件解析、清洗、切分、数据集和早期原型。
4. `storage_layer/`：运行数据、向量库、后续图数据库和实验结果存储。
5. `observability/`：日志、trace、错误归因和性能监控。
6. `evaluation/`、`experiments/`、`paper_assets/`：面向顶刊论文的评测、实验和论文资产。

## 推荐入口

日常开发、组会演示、界面联调优先使用：

- `api_server/current_console/`
- `frontend_app/current_console/`
- `storage_layer/runtime/current_console/`

当前控制台包含：

- FastAPI 后端
- 前端控制台
- Chroma 入库与检索
- 文件处理 operation log
- benchmark 与统计接口

## 工程蓝图

完整目录蓝图见：

- `docs/rag_full_engineering_blueprint.md`

## 根仓原型包

`data_pipeline/prototype/power_rag_pipeline/` 保留了一条更轻量的早期原型实现，用于记录：

- Label Studio JSON 解析
- 文本清洗
- 分块
- 向量化
- 混合检索

它不是当前主应用入口，但适合作为最小实验基线。

## 归档区

`archive/legacy-code/` 存放历史实验与旧材料，默认不作为当前主线维护目标。
