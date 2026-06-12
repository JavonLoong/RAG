# Codex Core Bug Report

## 检查范围

- `api_server/current_console/server.py`
  - 该文件是 FastAPI 启动入口，实际路由由 `chroma_rag_poc.api.create_app()` 注册。
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py`
  - 检查了上传、上传清单、日志读取、处理入库、搜索、统计、导出等主路由。
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_graphrag.py`
  - 检查了 GraphRAG 社区检测、摘要、全局搜索、图统计、社区列表路由。
- 关联数据流模块：
  - `pipeline.py`
  - `parsing.py`
  - `chunking.py`
  - `text_utils.py`
  - `storage_layer/graph_store.py`

## 发现并修复的问题

### 1. 上传 `relative_path` 可绕过最终文件名类型校验

问题：

- `/api/upload` 原先只校验 `UploadFile.filename` 的扩展名。
- 调用方可以传入支持类型的 `filename`，再通过 `relative_path` 生成不支持的最终保存名。
- 结果是接口返回上传成功，但文件后续不会被 `_supported_upload_paths()` 纳入可处理清单，形成清单状态与实际可处理文件不一致。

修复：

- 在保存前同时校验原始 `source_name` 和最终 `stored_name`。
- `source_kind` 改为基于最终保存名计算，保证 manifest 与实际处理路径一致。

### 2. GET `/api/search` 未限制 `top_k`

问题：

- POST `/api/search` 通过 Pydantic 限制 `top_k` 为 `1..20`。
- GET `/api/search` 没有同等限制，空库时甚至会用异常大的 `top_k` 返回 200，数据存在时可能触发无效或昂贵查询。

修复：

- 增加 `_validate_top_k()`。
- GET 搜索在进入集合解析和查询前校验 `top_k`。

### 3. GraphRAG 路由直接信任请求里的本地数据库路径

问题：

- GraphRAG 路由接受 `graph_db_path` 后直接传给 `GraphStore`。
- 请求可指定运行目录外的本地 SQLite 文件；在 `GraphStore.initialize(reset=False)` 下会打开并初始化该文件。
- 这会造成不必要的本地文件访问面，并且在 Windows 下可能留下 SQLite 文件锁。

修复：

- 增加 `_resolve_graph_db_path()`。
- 只允许 `.db` / `.sqlite` / `.sqlite3` 文件。
- 只允许路径位于仓库根目录或当前 app 的 runtime 根目录、persist/upload 目录范围内。
- 在进入 `GraphStore` 前统一处理空路径、越界路径、不存在文件和目录路径。

## 新增测试

- `test_api_upload_rejects_unsupported_relative_path_extension`
- `test_api_search_get_rejects_out_of_range_top_k`
- `test_graphrag_routes_reject_graph_db_outside_runtime_roots`

## 验证结果

- `uv run python -m pytest api_server/current_console/chroma_rag_poc/tests/test_pipeline.py -q`
  - 15 passed
- `uv run python -m pytest tests/unit/test_graph_store.py tests/unit/test_community_detection.py tests/unit/test_global_search.py tests/unit/test_graphrag_orchestrator.py tests/unit/test_model_adapters_llm.py -q`
  - 19 passed

## 备注

- `server.py` 本身没有直接声明 API 路由；它的路由行为来自 `create_app()` 及其挂载的 GraphRAG router。
- 本次仅修改与当前 API 路由检查直接相关的文件，未处理仓库中已有的无关工作区变更。
