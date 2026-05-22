# Run Records

运行记录用于把后端处理过程从“前端显示成功/失败”推进到“可复盘的工程证据”。每次 PDF 抽取、建库、检索、KG 抽取或评测任务，都应该写一份结构化 `run_record*.json`，并保留同一次运行的 `.log` 文件。

## 标准字段

每条记录遵循 `observability/run_record_schema.json`：

| 字段 | 说明 |
| --- | --- |
| `run_id` | 唯一运行编号，建议格式为 `<task_type>-YYYYMMDD-HHMMSS`。 |
| `task_type` | `pdf_extraction`、`chroma_build`、`retrieval`、`kg_extraction`、`evaluation`、`api_process`、`mixed` 或 `unknown`。 |
| `started_at` / `finished_at` | ISO 8601 时间。任务中断时 `finished_at` 可为 `null`。 |
| `duration_seconds` | 端到端耗时，单位秒；缺失时为 `null`，不要随意填 0。 |
| `status` | `success`、`failure`、`partial`、`running` 或 `unknown`。 |
| `input_paths` / `output_paths` | 本次读取和写出的文件、目录、索引库或报告路径。 |
| `metrics` | 任务指标对象。允许扩展，但指标名应稳定。 |
| `errors` | 失败、异常、格式错误、关键阶段跳过等明确记录。 |
| `log_path` | 对应 `.log` 文件路径。 |
| `notes` | 人类可读说明，包括缺口和人工判断。 |

## 各任务建议指标

### PDF 抽取：`pdf_extraction`

建议写入：

| 指标 | 含义 |
| --- | --- |
| `pdf_file_count` | 本次处理 PDF 数量。 |
| `pages_total` | PDF 总页数。 |
| `pages_scanned` | 实际扫描/抽样页数。 |
| `pages_with_text` | 能直接抽出文字的页数。 |
| `extractable_chars` | 直接抽取的字符数。 |
| `ocr_queue_count` | 判定需要 OCR 的 PDF 或页数量。 |
| `ocr_completed_count` | OCR 已完成数量。 |
| `ocr_failed_count` | OCR 失败数量。 |
| `avg_chars_per_page` | 平均每页可抽取字符数。 |

失败要记录：文件无法打开、加密 PDF、页解析异常、OCR 引擎不可用、输出文本为空但未进入 OCR 队列等。

### Chroma 入库：`chroma_build`

建议写入：

| 指标 | 含义 |
| --- | --- |
| `source_document_count` | 原始文档数量。 |
| `chunk_count` | 分块数量。 |
| `embedding_count` | 生成 embedding 数量。 |
| `chroma_upsert_batches` | upsert 批次数。 |
| `chroma_upserted_count` | upsert 文档条数。 |
| `chroma_collection_count` | collection 数量。 |
| `chroma_total_document_count` | Chroma 中最终文档条数。 |
| `chroma_storage_bytes` | 持久化目录大小。 |
| `failed_chunk_count` | 分块、embedding 或入库失败数量。 |

失败要记录：embedding 模型加载失败、批量写入异常、collection 重名冲突、入库条数与预期不一致、持久化目录不可写等。

### 检索：`retrieval`

建议写入：

| 指标 | 含义 |
| --- | --- |
| `query_count` | 查询数量。 |
| `top_k` | 每次查询返回候选数量。 |
| `retrieved_count` | 实际返回结果数。 |
| `hit_count` | 命中人工标注答案或目标证据的数量。 |
| `hit_rate` | `hit_count / query_count`。 |
| `recall_at_k` | Recall@k。 |
| `precision_at_k` | Precision@k。 |
| `mrr` | Mean Reciprocal Rank。 |
| `avg_latency_ms` | 平均检索耗时。 |
| `empty_result_count` | 空结果查询数量。 |

失败要记录：collection 不存在、向量维度不匹配、查询超时、空结果、top-k 少于预期、证据路径缺失等。

### KG 抽取：`kg_extraction`

建议写入：

| 指标 | 含义 |
| --- | --- |
| `source_chunk_count` | 输入 chunk 数量。 |
| `candidate_triple_count` | 候选三元组数量。 |
| `validated_triple_count` | 通过校验的三元组数量。 |
| `rejected_triple_count` | 人工或规则拒绝的三元组数量。 |
| `entity_count` | 实体数量。 |
| `relation_count` | 关系类型数量。 |
| `evidence_coverage` | 带证据三元组比例。 |
| `manual_review_count` | 人工复核数量。 |
| `llm_call_count` | LLM 调用次数。 |
| `llm_failed_call_count` | LLM 调用失败次数。 |

失败要记录：schema 不匹配、证据缺失、JSON 解析失败、LLM 输出不合法、重复三元组过多、人工复核未完成等。

## 日志与汇总

`scripts/summarize_run_records.py` 会扫描：

- `observability/logs/**/*.log`
- `observability/logs/**/run_record*.json`
- `observability/run_record*.json`

输出：

- `observability/reports/run_records_summary.json`
- `observability/reports/run_records_summary.md`

如果日志缺少结构化字段，脚本只汇总能确定的信息，并在 `gaps` 或 `notes` 中明确说明缺口；如果日志读取失败或 JSON 行格式错误，脚本会把错误写入汇总，不会静默吞掉。
