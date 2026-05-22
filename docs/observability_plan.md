# RAG 控制台可观测性修复计划

更新时间：2026-04-25

## 目标

把会议中提到的“文件处理慢、CPU 高、前端错误过于简单、后端缺少可定位日志”的问题先落到工程修复上。

前端保持简洁状态；详细排查信息写入后端 `.log` 文件，便于区分文件过大、解析异常、入库异常、检索异常和接口超时。

## 当前进度

- [x] 新增 per-operation `.log` 机制，覆盖上传、读取、解析、清洗、分块、向量入库、统计等阶段。
- [x] `/api/upload` 返回 `log_file`，并写入上传 manifest。
- [x] `/api/process` 返回 `log_file`，失败时把错误和日志文件名写回 manifest。
- [x] `/api/ingest` 返回 `log_file`，并把即时入库保存的文件名与日志关联。
- [x] 新增 `/api/logs` 和 `/api/logs/{filename}` 用于查看日志列表和单个日志。
- [x] 前端只展示简洁摘要和“详细日志”入口。
- [x] 修复自定义 hashing embedding 与新版 ChromaDB 的 `name()` / `embed_query()` 兼容问题。
- [x] 回归测试通过：最终 `10 passed in 72.94s`。

## 子 Agent 调度

- [x] gpt-5.5 xhigh 实现复核：worker `019dc0c1-b4fb-7361-8378-9c5b1627c12d` 已完成；已补日志 close 幂等、日志/上传路径校验、未知 backend 显式报错、ingest 失败写回日志、本地模式隐藏日志链接及对应测试。
- [x] gpt-5.4 xhigh 审核复核：explorer `019dc0c2-4e69-7590-bcb7-239cd8135327` 已完成；发现 `embed_query` 字符串输入、`log_path` 暴露、stats/search 未接入日志、失败分支测试不足。
- [x] 主调度整合结论并纠偏：已完成。

## 主调度纠偏项

- [x] 让 `HashingEmbeddingFunction.embed_query()` 同时兼容 Chroma 实际传入的批量 list 和文档建议的单条 str。
- [x] API 响应不再返回服务端绝对 `log_path`，只返回 `log_file`；日志接口增加同源访问保护。
- [x] 给 `/api/stats`、`/api/search` GET、`/api/search` POST 接入 operation log。
- [x] 补充对应失败/边界测试并复跑：`10 passed in 72.94s`。

## 约束

- 子 agent 不得调用孙 agent。
- 不打断已派出的子 agent。
- 不回滚用户或其他任务已有改动。
- 不滥用兜底：能明确失败原因时写清楚原因，不用宽泛 fallback 掩盖真实错误。
