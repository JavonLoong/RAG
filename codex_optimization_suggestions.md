# RAG 控制台 API 路由逻辑优化建议

## 检查范围

本次重点检查 `api_server/current_console/server.py` 的后端入口与实际 API 路由注册链路。结论是：`server.py` 本身不直接声明业务路由，它负责路径注入、运行目录选择和调用 `chroma_rag_poc.api.create_app()`；真实路由主要集中在：

- `api_server/current_console/server.py`
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py`
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_graphrag.py`
- 关联调用：`pipeline.py`、`retrieval.py`、`engine_bridge.py`、`retrieval_engine/*`、`rag_orchestrator/*`

当前导出的 API 路由包括：

| 方法 | 路径 | 处理函数 |
| --- | --- | --- |
| GET | `/` | `index` |
| GET | `/api/health` | `health` |
| POST | `/api/upload` | `upload_file` |
| GET | `/api/uploads` | `list_uploads` |
| DELETE | `/api/uploads/{filename}` | `delete_upload` |
| POST | `/api/uploads/delete` | `delete_uploads` |
| GET | `/api/logs` | `list_logs` |
| GET | `/api/logs/{filename}` | `read_log` |
| POST | `/api/process` | `process_files` |
| POST | `/api/ingest` | `ingest` |
| POST | `/api/public-books-json/ingest` | `ingest_public_books_json` |
| GET | `/api/stats` | `stats` |
| GET | `/api/search` | `search_get` |
| POST | `/api/search` | `search_post` |
| POST | `/api/benchmark` | `benchmark` |
| DELETE | `/api/collections/{name}` | `delete_collection` |
| GET | `/api/export` | `export_all` |
| GET | `/api/chroma/export` | `export_chroma_db` |
| GET | `/api/export/{collection_name}` | `export_collection` |
| POST | `/api/graphrag/community/detect` | `detect_communities` |
| POST | `/api/graphrag/community/summarize` | `summarize_communities` |
| POST | `/api/graphrag/search/global` | `global_search` |
| POST | `/api/graphrag/stats` | `graph_stats` |
| GET | `/api/graphrag/communities` | `list_communities` |

## 总体判断

当前 API 已经具备一个本地 RAG 控制台的完整闭环：上传、处理、入库、统计、搜索、导出、日志和 GraphRAG 基础能力。但它仍然更像“单机控制台后端”，不是可水平扩展的服务化 API。最大优化空间集中在四点：

1. `api.py` 仍是 1000 行以上的路由、校验、文件状态、Chroma 操作混合模块，服务边界不清晰。
2. 多个长耗时接口在 `async def` 中执行同步 CPU/IO 工作，容易阻塞 FastAPI 事件循环。
3. 检索层实际 API 仍主要调用简单 Chroma 语义检索，项目中已有 Hybrid/BM25/Reranker/GraphRAG 抽象没有完整接入路由。
4. 本地文件读写、导出、删除、日志和 GraphRAG DB 路径已经做了一些防护，但整体缺少认证、任务队列、并发状态一致性和资源配额。

## P0：需要优先处理的路由与安全边界

### 1. 避免 `create_app()` 的导入期副作用

现状：

- `server.py` 导入 `create_app` 后，又在 `server.py` 中创建自己的 `app`。
- 但 `api.py` 文件底部也执行了 `app = create_app()`。
- 这意味着运行 `server.py` 时，`api.py` 会先用默认目录创建一次 app，再由 `server.py` 用当前控制台目录创建第二次 app。

建议：

- 删除或隔离 `api.py` 底部的模块级 `app = create_app()`，改成 `chroma_rag_poc.__main__` 或 ASGI 专用入口显式创建。
- 如果仍需 `uvicorn chroma_rag_poc.api:app`，建议增加 `create_default_app()` 并避免导入时创建目录、挂载前端、吞掉路由导入异常。

收益：

- 减少启动副作用。
- 避免测试、CLI、脚本导入 API 模块时意外创建 runtime 目录。
- 让 `server.py` 成为唯一控制台入口，路由逻辑更可预测。

### 2. 前端目录选择不应在导入期硬失败

现状：

- `FRONTEND_DIR = next(...)` 在 `api.py` 顶层执行。
- 如果三个候选前端目录都不存在，导入 `api.py` 会直接抛 `StopIteration`，`index()` 中的 404 分支实际没有机会执行。

建议：

- 改为 `FRONTEND_DIR: Path | None`。
- 在 `create_app()` 内根据实际存在情况决定是否挂载 `/static`。
- `/` 路由在没有前端时返回明确 404 和候选路径诊断。

### 3. 给所有破坏性和本地文件读取接口加认证/授权

现状：

- `server.py` 使用 `uvicorn.run(... host="0.0.0.0", port=8000)`。
- `create_app()` 配置 `allow_origins=["*"]`。
- 删除上传、删除集合、导出数据库、读取日志、指定本地 JSON 目录入库、GraphRAG DB 操作等接口没有统一认证。

高风险接口：

- `DELETE /api/uploads/{filename}`
- `POST /api/uploads/delete`
- `DELETE /api/collections/{name}`
- `GET /api/export`
- `GET /api/export/{collection_name}`
- `GET /api/logs/{filename}`
- `POST /api/public-books-json/ingest`
- `/api/graphrag/*`

建议：

- 本地控制台模式默认绑定 `127.0.0.1`，只有显式配置才绑定 `0.0.0.0`。
- 增加最小 API token 或本地 session 保护。
- CORS 默认只允许控制台前端 origin。
- 对读本地路径、导出、删除类接口增加权限分组。

### 4. 收紧 `/api/public-books-json/ingest` 的本地路径读取范围

现状：

- 该接口接受请求体里的 `input_dir`，只检查路径是否存在。
- 与 GraphRAG DB 路径相比，它缺少 allowed roots 校验。

建议：

- 复用 GraphRAG 的 allowed roots 思路，只允许读取仓库数据目录、上传目录、runtime 目录或显式白名单目录。
- 返回错误时不要暴露过多本地绝对路径。
- 把路径型任务改为“服务端预登记数据源 ID”，前端只传 ID。

## P1：架构设计与扩展性

### 1. 拆分 `api.py` 的单体路由模块

建议拆成以下 router/service 结构：

```text
chroma_rag_poc/
  api_app.py              # create_app, middleware, lifecycle
  routes/
    health.py
    frontend.py
    uploads.py
    ingest.py
    search.py
    stats.py
    export.py
    logs.py
    benchmark.py
    graphrag.py
  services/
    upload_manifest.py
    ingest_service.py
    search_service.py
    chroma_service.py
    export_service.py
    job_service.py
  security/
    paths.py
    auth.py
    limits.py
```

关键点：

- router 只处理 HTTP 参数、状态码和响应模型。
- service 负责业务编排。
- storage/client 适配器负责 Chroma、GraphStore、文件系统。
- schema 单独管理 request/response model，便于 OpenAPI 合约测试。

### 2. 统一 GET/POST 搜索语义

现状：

- `GET /api/search` 在 collection 为空时自动选择第一个非空集合。
- `POST /api/search` 默认固定 `power_equipment`。
- 两者行为不一致，容易造成前端与脚本调用结果不同。

建议：

- 提取 `SearchService.resolve_collection()`。
- 明确 collection 为空时的策略：默认集合、最新集合、全部集合聚合、或返回 400。
- 响应中固定返回 `resolved_collection` 和 `collection_resolution_strategy`。

### 3. GraphRAG 不应只暴露“指定 db_path 的工具接口”

现状：

- GraphRAG 路由以 `graph_db_path` 为核心参数。
- 它更像调试工具，而不是当前 RAG 控制台的一等能力。
- 上传/入库 pipeline 与图谱抽取、图更新、社区检测、社区摘要、全局搜索之间还没有形成端到端任务链。

建议：

- 增加图谱数据源注册：collection -> graph index。
- 增加 `/api/graphrag/build`、`/api/graphrag/jobs/{id}`、`/api/graphrag/search/local`、`/api/graphrag/search/hybrid`。
- 让前端和 API 使用 `graph_id` 或 `collection`，不要直接传本地 SQLite 路径。
- 建立向量 chunk ID、实体、关系、社区摘要之间的稳定引用。

## P1：性能与高并发优化

### 1. 长耗时接口改为后台任务模型

当前长耗时接口：

- `/api/process`
- `/api/ingest`
- `/api/public-books-json/ingest`
- `/api/benchmark`
- `/api/graphrag/community/detect`
- `/api/graphrag/community/summarize`
- `/api/graphrag/search/global`
- `/api/export`

问题：

- 路由是 `async def`，但内部大量使用同步文件读写、Chroma 操作、模型加载、社区检测、LLM 调用。
- 这些任务会占用 worker，影响健康检查、日志读取、搜索等轻量接口。

建议：

- 引入轻量 job abstraction：`queued/running/succeeded/failed/cancelled`。
- 本地单机可先用 SQLite + ThreadPool/ProcessPool；之后再替换为 Celery/RQ/Arq。
- API 返回 `job_id`，前端轮询或 SSE 订阅进度。
- 日志与 job_id 绑定，替代散落的 log_file 查询。

### 2. 上传、处理、导出避免整文件进内存

现状：

- `/api/upload` 使用 `await file.read()` 一次性读入内存。
- `/api/process` 对选中文件 `read_bytes()` 后组装 payload 列表。
- `/api/export` 用 `io.BytesIO()` 在内存中构造整个 ChromaDB zip。

建议：

- 上传时使用分块 streaming 到临时文件，再原子 rename。
- 设置单文件大小、批量文件数量、总请求体大小限制。
- 入库处理改为文件迭代器或 job worker 读取，避免 API 层聚合全部 bytes。
- 导出写入临时 zip 文件或流式生成，并对超大库返回后台导出任务。

### 3. Chroma client 生命周期集中管理

现状：

- 每次 stats/search/delete/export 都创建 `PersistentClient`。
- 多处调用私有方法 `_system.stop()` 和 `clear_system_cache()`。

建议：

- 封装 `ChromaService`，统一 client 创建、关闭、重试、并发锁和 telemetry 配置。
- 对只读查询增加短生命周期缓存：集合列表、集合 count、存储大小。
- 对写操作引入 collection-level lock，避免 upload/process/delete/export 并发冲突。

### 4. 上传 manifest 改为事务型状态表

现状：

- 上传清单是 `.upload-manifest.json`。
- 多个请求同时上传、删除、处理时，读-改-写 JSON 文件存在丢更新风险。

建议：

- 用 SQLite 保存 upload manifest、job、log、collection 状态。
- 每个文件状态记录 `uploaded/processing/processed/failed/deleted`。
- 文件处理结果与 Chroma upsert 在业务上形成可恢复事务：失败可重试，重复处理可幂等。

## P1：检索准确度与 GraphRAG 策略

### 1. 将已有 Hybrid/Reranker 接入 API 搜索主路径

现状：

- `api.py` 的 `/api/search` 调用 `pipeline.query_collection()`，主要是 Chroma 语义检索。
- 项目里已有 `chroma_rag_poc/retrieval.py` 的 BM25 + RRF，也有 `retrieval_engine/hybrid.py` 和 `model_adapters/reranker.py`，但当前 API 搜索主路径没有使用它们。
- `engine_bridge.py` 已经提供根级检索组件桥接，但目前未被路由调用。

建议：

- 新增搜索模式：`semantic`、`keyword`、`hybrid`、`hybrid_rerank`、`graphrag_local`、`graphrag_global`。
- 默认使用 hybrid：向量召回 + BM25 召回 + RRF 合并。
- 对 top 50 candidates 使用 `BAAI/bge-reranker-v2-m3` 或可配置 reranker 重排。
- 搜索响应返回 component scores，便于调试召回来源。

### 2. 建立评测集驱动的检索调参

建议围绕已有 `evaluation/*` 做接口化：

- 增加 `/api/evaluation/run` 后台任务。
- 维护固定问题集、期望答案、引用片段或实体关系。
- 指标覆盖 recall@k、MRR、nDCG、answer faithfulness、citation coverage。
- 每次调整 chunk、embedding、BM25、reranker、GraphRAG 策略都跑基准。

### 3. GraphRAG 全局搜索需要社区筛选和局部回退

现状：

- `GlobalSearchOrchestrator` 对社区摘要执行 map-reduce，但路由只传 `max_communities`。
- 社区摘要选择策略较粗，缺少基于 query 的社区预筛选。

建议：

- 给社区摘要建立向量索引，先检索相关社区，再进入 map-reduce。
- 支持 DRIFT 风格：全局社区摘要回答 + 局部实体邻域补证。
- 将回答中的实体、关系、社区、原文 chunk 串起来，返回可追溯 citations。
- 对社区摘要做版本化，图谱更新后只增量刷新受影响社区。

### 4. 入库阶段补强结构化元数据

建议：

- chunk metadata 中统一保留 `doc_id/source_file/page/section/block_type/entity_ids/graph_node_ids`。
- PDF/OCR 文档保留页码、标题层级和表格边界。
- 支持按文件、页码、章节、设备型号、时间范围过滤检索。
- 对中文技术文档增加术语词典、型号正则、同义词扩展。

## P2：工程化最佳实践

### 1. 建立 OpenAPI 合约和路由存在性测试

建议：

- 测试 `create_app()` 的完整 route table，防止 GraphRAG router 被静默跳过。
- 保存 OpenAPI snapshot，接口变更时显式 review。
- 覆盖 GET/POST search 行为一致性、错误状态码、响应字段稳定性。

### 2. 修正测试发现路径

现状：

- 根目录 `pyproject.toml` 的 pytest `testpaths` 不包含 `api_server/current_console/chroma_rag_poc/tests`。
- 这会导致只在根目录跑 `pytest` 时漏掉控制台 API 测试。

建议：

- 将控制台测试纳入根测试路径，或在 CI 中增加专门 job。
- 区分 unit、api、integration、performance 标记，避免慢测试影响快速回归。

### 3. 统一错误响应格式

现状：

- 多处直接把异常字符串拼进 HTTP detail。
- 不同接口 400/500 使用不一致。

建议：

```json
{
  "error": {
    "code": "SEARCH_COLLECTION_NOT_FOUND",
    "message": "集合不存在或为空",
    "request_id": "...",
    "log_file": "..."
  }
}
```

同时：

- 内部异常和本地路径只写日志，不直接暴露给前端。
- 给用户错误、系统错误、依赖错误、权限错误分层。

### 4. 让 GraphRAG 路由也接入统一观测

现状：

- 主 API 多数使用 `OperationLogger`。
- GraphRAG 路由没有统一 log_file、阶段日志、耗时统计和 request_id。

建议：

- 所有路由加 request_id middleware。
- GraphRAG 检测、摘要、全局搜索增加阶段日志：open_graph、detect、summarize、map、reduce。
- 暴露 Prometheus 风格指标：请求耗时、任务耗时、检索 top_k、LLM token、错误类型。

## 建议实施路线

### 第 1 阶段：路由安全与启动确定性

- 移除 `api.py` 的导入期 `app = create_app()` 副作用。
- 修复 `FRONTEND_DIR` 导入期硬失败。
- 默认绑定 localhost，并增加最小 API token。
- 给 `/api/public-books-json/ingest` 加 allowed roots。
- 增加 route table 和 OpenAPI snapshot 测试。

### 第 2 阶段：API 模块化与任务化

- 拆分 `api.py` routers/services/schemas。
- 引入 SQLite job store。
- 将 process/ingest/export/benchmark/GraphRAG summary 转为后台任务。
- upload manifest 迁移到 SQLite。

### 第 3 阶段：检索质量升级

- `/api/search` 增加 hybrid 和 rerank 模式。
- 接入 `engine_bridge.py` 和根级 `retrieval_engine`。
- 建立检索评测集和自动报告。
- GraphRAG 增加 graph_id、build job、local/global/hybrid search。

### 第 4 阶段：生产化基础

- 统一认证、审计、限流、请求大小限制。
- 增加结构化日志、metrics、trace。
- 引入配置管理和环境分层：local/dev/prod。
- 对 Chroma/GraphStore/LLM 调用做连接管理、重试、超时、熔断。

## 优先级摘要

| 优先级 | 建议 | 价值 |
| --- | --- | --- |
| P0 | 移除导入期 app 创建、修复前端目录导入失败 | 启动稳定性 |
| P0 | 加认证、收紧 CORS、本地路径白名单 | 安全边界 |
| P1 | 长任务后台化 | 并发与用户体验 |
| P1 | manifest 迁移 SQLite | 状态一致性 |
| P1 | 搜索主路径接入 hybrid/reranker | 检索准确度 |
| P1 | GraphRAG 从 db_path 工具接口升级为 collection/graph_id 能力 | 可用性与扩展性 |
| P2 | 拆分 `api.py` | 可维护性 |
| P2 | OpenAPI/route snapshot 测试 | 合约稳定 |
| P2 | 统一错误响应和观测 | 运维效率 |

## 结论

`server.py` 当前作为控制台入口基本可用，但真正需要优化的是它导入的 `create_app()` 路由装配层。下一轮最值得做的是“启动副作用清理 + 安全边界收紧 + 长任务后台化 + 搜索主路径升级为 hybrid/rerank”。这四项能同时提升稳定性、安全性、并发能力和 RAG 检索质量。
