# RAG 工程目录重整报告

更新时间：2026-04-25

## 重整目标

按照 `docs/rag_full_engineering_blueprint.md` 的工程蓝图，把根目录从“应用、原型、脚本、数据混放”整理为“按核心能力划分”的顶刊工程结构。

## 已完成迁移

| 原位置 | 新位置 | 说明 |
|---|---|---|
| `apps/jiwenlong-rag-console/` | `api_server/current_console/` | 当前可运行 RAG 控制台后端与服务入口 |
| `apps/jiwenlong-rag-console/frontend/` | `frontend_app/current_console/` | 当前控制台前端 |
| `apps/jiwenlong-rag-console/data/` | `storage_layer/runtime/current_console/` | 当前控制台运行数据 |
| `apps/jiwenlong-rag-console/chroma_rag_poc/frontend/` | `frontend_app/chroma_rag_poc_legacy/` | 旧版拆分式前端静态文件 |
| `apps/jiwenlong-rag-console/chroma_rag_poc/data/` | `storage_layer/runtime/chroma_rag_poc_package/` | 旧包默认数据目录 |
| `src/power_rag_pipeline/` | `data_pipeline/prototype/power_rag_pipeline/` | 早期轻量 RAG pipeline 原型 |
| `src/algokit_example/` | `archive/legacy-code/algokit_example/` | 历史模板残留 |
| `tests/test_power_rag_pipeline.py` | `tests/unit/test_power_rag_pipeline.py` | 根仓原型单元测试 |
| `goldwind_decoded/` | `data_pipeline/datasets/goldwind_decoded/` | 解码后的实验数据 |
| `goldwind_data_task.py` | `scripts/goldwind_data_task.py` | 数据处理脚本 |
| `numpy_broadcast_matrix_answer.py` | `archive/legacy-code/numpy_broadcast_matrix_answer.py` | 非主线历史脚本 |
| `source.pptx` | `paper_assets/presentations/source.pptx` | 演示/论文资产 |

## 已修正路径

- `api_server/current_console/server.py`：运行数据改为 `storage_layer/runtime/current_console/`。
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py`：前端优先从 `frontend_app/current_console/` 挂载。
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/pipeline.py`：默认运行目录改为 `storage_layer/runtime/current_console/`。
- `api_server/current_console/scripts/*.py`：mock data、benchmark db、benchmark report 改为写入 `storage_layer/runtime/current_console/`。
- `pyproject.toml`：根仓原型包路径改为 `data_pipeline/prototype/power_rag_pipeline/`。
- `mkdocs.yml`：mkdocstrings Python 路径改为 `data_pipeline/prototype/`。
- `.gitignore`：运行数据忽略规则改为新 runtime 目录。
- `Dockerfile`：默认启动目录改为 `api_server/current_console/`。
- `README.md`、`docs/index.md`、`docs/repository-layout.md`：同步为新结构。

## 验证结果

- 根仓原型测试：`tests/unit/test_power_rag_pipeline.py`，通过 2 个测试。
- 当前控制台测试：`api_server/current_console/chroma_rag_poc/tests/test_pipeline.py`，`10 passed in 77.00s`。
- 入口导入验证：`server.app` 可导入，`/api/health` 返回 200，`/` 返回前端 HTML，运行数据目录指向 `storage_layer/runtime/current_console/`。

## 当前保留策略

- `api_server/current_console/chroma_rag_poc/` 内部包结构暂时不继续拆分，避免破坏当前可运行控制台。
- 新增的顶层能力目录先承接 README 和未来模块，后续可以逐步把 `chroma_rag_poc` 中的解析、检索、存储、可观测性代码迁移到对应能力层。
- `archive/` 保留为历史材料区，不作为主线入口。
