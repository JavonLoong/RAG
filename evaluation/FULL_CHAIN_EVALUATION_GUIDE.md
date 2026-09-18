# RAG / GraphRAG 全链路评测指南

本文给其他模型或评测代理使用。目标不是只测“能不能检索出几段文本”，而是评测整个知识库系统：文档解析、入库、向量检索、关键词/混合检索、知识图谱、GraphRAG、答案生成、引用、失败归因和回归集。

## 目录

一、总原则 ................................................ 一
二、评测前能力盘点 ........................................ 二
三、标准本地命令 .......................................... 三
四、全链路评测范围 ........................................ 四
五、推荐评测集 ............................................ 五
六、API 全链路检查 ........................................ 六
七、公开指标与报告结构 .................................... 七
八、指标记录 .............................................. 八
九、失败归因模板 .......................................... 九
十、防止“假评测”的硬性规则 .............................. 十
十一、最小可接受全链路流程 ............................... 十一
十二、正式报告必须包含的结论 ............................. 十二

## 一、总原则

1. 不能只跑普通 RAG 就宣称完成全链路评测。
2. 不能因为自己没有某个 API、LLM key、图数据库文件、解析器依赖，就静默跳过该环节。
3. 缺少能力时必须写成 `blocked` 或 `degraded`，并说明缺的是什么、影响哪一项分数。
4. RAG-only、Graph-only、Hybrid、GraphRAG local/global/hybrid 必须分开记录，最后再给综合结论；如公开 benchmark 有官方总分，再引用官方总分。
5. 所有评分必须绑定证据：报告路径、命令、数据集、模型名、向量后端、图谱路径、top_k、chunk 参数。

## 二、评测前能力盘点

评测前先输出一份 capability check，至少包含：

| 项目 | 必须记录 |
| --- | --- |
| Python 环境 | 使用的解释器，例如 `.venv\Scripts\python.exe` |
| 代码版本 | 当前 git branch / commit / dirty 状态 |
| 文档解析 | `auto/native/docling/mineru/deepdoc/unstructured` 哪些可用 |
| 向量模型 | backend、model_name、本地路径、维度、是否 fallback 到 hashing |
| Chroma 库 | persist-dir、collection、文档数、chunk 数 |
| 关键词检索 | BM25/keyword 是否启用 |
| 混合检索 | hybrid/RRF 是否启用 |
| rerank | cross-encoder/noop/none |
| 图谱 | graph_db_path、节点数、边数、community 数、summary 数 |
| GraphRAG | local/global/hybrid 是否可跑 |
| LLM | provider、base_url、model、有无 key，不要打印 key |
| 评测集 | dataset 名称、case 数、是否抽样 |

如果某项不可用，报告里写：

```json
{
  "component": "graphrag_global",
  "status": "blocked",
  "reason": "missing llm_api_key for community summarization/global answer generation",
  "score_impact": "global GraphRAG score is not valid; total score must be marked degraded"
}
```

## 三、标准本地命令

在仓库根目录运行：

```powershell
cd D:\虚拟C盘\RAG
```

优先使用项目虚拟环境：

```powershell
.venv\Scripts\python.exe --version
```

确认默认向量模型不是 hashing：

```powershell
$env:PYTHONPATH = "D:\虚拟C盘\RAG\api_server\current_console\chroma_rag_poc\src"
@'
from chroma_rag_poc.embeddings import create_embedding_backend
backend = create_embedding_backend(backend="sentence-transformer", model_name=None)
print(backend.name)
print(backend.model_name)
print(backend.dimension)
print(backend.warning)
'@ | .venv\Scripts\python.exe -
```

合格条件：

- `backend.name` 必须是 `sentence-transformer`
- `dimension` 当前应为 `1024`
- `warning` 必须是 `None`
- 如果出现 `hashing`，不能继续当作正式语义检索评测

## 四、全链路评测范围

全链路至少包括下面 8 个环节。

| 环节 | 要测什么 | 不合格例子 |
| --- | --- | --- |
| 文档解析 | PDF/DOCX/TXT/Markdown/JSON 能否解析、OCR 风险、表格/标题/页码保留 | 只拿已有 txt，不测解析 |
| chunk | chunk_size、overlap、标题边界、页码/来源 metadata | 大段切碎后丢来源 |
| 向量检索 | Qwen3-Embedding-0.6B 或指定模型，Chroma 查询 | 实际 fallback 到 hashing |
| 关键词检索 | 精确术语、型号、参数、公式、设备名 | 只用 dense，型号搜不到 |
| 混合检索 | dense + keyword + RRF，必要时 rerank | 只测 `/api/search` 默认结果，不看诊断 |
| 知识图谱 | 实体、关系、证据、graph quality、邻域检索 | 没有图就说 GraphRAG 通过 |
| GraphRAG | local、global、hybrid/mix，community summary，map-reduce | 只跑 local 或只跑普通 RAG |
| 生成与引用 | 答案覆盖率、引用缺失率、幻觉风险、no-answer gate | 答案没引用也算正确 |

## 五、推荐评测集

### 4.1 内部系统评测集

使用：

```text
evaluation/system_eval_questions.jsonl
```

每条 case 应包含：

- `question`
- `reference_answer`
- `expected_evidence_keywords`
- `task_type`
- `source_scope`
- `expected_modes`
- `grading_notes`

`expected_modes` 很重要。其他模型必须按它判断应该走哪条链路：

| expected_modes | 含义 |
| --- | --- |
| `semantic` | 语义向量检索必须可用 |
| `keyword` | 关键词/精确匹配必须可用 |
| `hybrid` | dense + keyword/RRF 必须可用 |
| `graph` | 知识图谱证据必须参与 |
| `global` | community summary / global search 必须参与 |

### 4.2 外部 benchmark

使用已下载的数据：

```text
evaluation/external_benchmarks
```

标准入口：

```powershell
.venv\Scripts\python.exe scripts\run_external_benchmark_evaluation.py `
  --benchmarks legal graphrag-medical graphrag-novel ragbench-hotpotqa-validation `
  --case-limit 50 `
  --top-k 10 `
  --backend sentence-transformer `
  --model-name Qwen/Qwen3-Embedding-0.6B `
  --run-name full_chain_baseline
```

注意：这个脚本主要是 retrieval-first benchmark。它不能单独代表最终 GraphRAG 生成质量，必须和 GraphRAG 流程结果合并报告。

### 4.3 GraphRAG triage 回归集

使用 promoted cases：

```powershell
.venv\Scripts\python.exe scripts\run_graphrag_triage_regression.py `
  --dataset outputs\smoke_chroma\evaluation\graphrag_triage_regression.jsonl `
  --persist-dir outputs\smoke_chroma `
  --collection rag_smoke `
  --backend sentence-transformer `
  --model-name Qwen/Qwen3-Embedding-0.6B `
  --top-k 10 `
  --allow-empty
```

如果 `case_count=0`，只能说明没有 promoted case，不能说明 GraphRAG 没问题。

## 六、API 全链路检查

启动服务后，至少检查这些入口：

| API | 用途 | 必测点 |
| --- | --- | --- |
| `POST /api/ingest` | 文档解析、chunk、向量入库 | backend/model/parser/chunks_written |
| `GET/POST /api/search` | 普通检索 | top_k、结果来源、metadata、hybrid diagnostics |
| `POST /api/query` | 统一问答入口 | mode=`auto/vector/local/global/aggregation` |
| `POST /api/graphrag/import` | 导入图谱 | 节点、边、证据 |
| `POST /api/graphrag/community/detect` | 社区发现 | community_count |
| `POST /api/graphrag/community/summarize` | 社区摘要 | 需要 LLM key |
| `POST /api/graphrag/search/global` | global GraphRAG | 需要 community summary + LLM |
| `POST /api/graphrag/stats` | 图谱统计 | node/edge/community/summary |
| `GET /api/graphrag/triage` | 失败案例 | 是否记录质量失败 |
| `GET /api/graphrag/triage/analytics` | 失败分析 | route、graph quality、failure metrics |

`POST /api/query` 的模式要求：

| mode | 必须验证 |
| --- | --- |
| `vector` | 普通向量/文本检索，不代表 GraphRAG |
| `local` | 图谱邻域、实体关系证据 |
| `global` | community summary / map-reduce |
| `aggregation` | 多证据综合，适合统计/汇总类问题 |
| `auto` | 路由器能否把问题分到正确模式 |

## 七、公开指标与报告结构

评分口径必须来自公开 benchmark、公开论文或公开评测工具。项目脚本只能负责运行和汇总这些公开口径的结果，不能把项目自定义口径包装成公开标准。不要自行发明权重、不要自行给总分封顶、不要把主观权重写成评测标准。

最终报告可以有综合判断，但综合判断必须和原始指标分开。推荐结构：

```json
{
  "status": "pass|fail|degraded|blocked",
  "official_scores": [
    {
      "benchmark": "benchmark or tool name",
      "metric": "official metric name",
      "value": 0,
      "source": "public benchmark / paper / tool / local script output",
      "higher_is_better": true
    }
  ],
  "raw_metrics": {},
  "capability_gaps": [],
  "report_paths": []
}
```

如果某个公开 benchmark 没有官方综合分，只能报告它的原始分项指标，并写明“无官方综合分”。如果需要人工给结论，只能写 `pass/fail/degraded/blocked` 和原因，不能编造综合分。

## 八、指标记录

优先记录公开 benchmark 或公开评测工具的原始指标名和原始数值，不要随意改名。下面这些是本项目已有报告中可能出现的字段；它们用于辅助归因，不代表公开 benchmark 的统一评分标准：

| 指标 | 含义 |
| --- | --- |
| `keyword_recall_at_k` | 检索结果覆盖 expected evidence keywords 的比例 |
| `full_evidence_coverage_rate` | 单题是否覆盖完整证据 |
| `no_result_rate` | 没有有效检索结果的比例 |
| `answer_completeness_avg` | 答案覆盖参考要点的程度 |
| `missing_citation_rate` | 答案缺少引用的比例 |
| `medium_or_high_risk_rate` | 中高幻觉风险比例 |
| `graph_node_count` | 图谱节点数 |
| `graph_edge_count` | 图谱边数 |
| `community_count` | 社区数量 |
| `community_summary_count` | 社区摘要数量 |
| `route_accuracy` | auto 路由是否选对 vector/local/global/hybrid |

## 九、失败归因模板

每个失败 case 都要写归因，不要只写“答错”。

```json
{
  "case_id": "xxx",
  "question": "...",
  "expected_modes": ["hybrid", "graph"],
  "actual_modes": ["semantic"],
  "failure_stage": "routing|parsing|chunking|retrieval|graph|generation|citation|no_answer",
  "root_cause": "auto router did not select graph mode although graph evidence was required",
  "evidence_missing": ["压气机喘振", "叶片裂纹"],
  "retrieved_sources": [],
  "fix_recommendation": "add route regression case and require graph retriever when expected_modes contains graph"
}
```

## 十、防止“假评测”的硬性规则

以下情况不能给全链路通过：

1. 只调用 `/api/search`，没有调用 `/api/query` 或 GraphRAG API。
2. 只看答案文本，不检查 retrieval evidence。
3. 没有记录 `embedding_backend` 和 `embedding_model`。
4. 向量模型 fallback 到 hashing 还按语义检索评分。
5. 没有 graph_db_path、节点、边、community summary，却给 GraphRAG 分数。
6. 因为没有 LLM key 就跳过 global search，但总分不降级。
7. 只测英文 benchmark，不测中文/燃气轮机领域问题。
8. 只测抽样成功案例，不保留失败案例。
9. 不保存 JSON/Markdown 报告。
10. 不把失败 case 加入 triage 或 regression 数据集。

## 十一、最小可接受全链路流程

如果时间很紧，至少跑这一组：

```powershell
# 1. smoke：包含 ingest/search/evaluation/GraphRAG query/global smoke
.venv\Scripts\python.exe scripts\run_rag_smoke_evaluation.py --json

# 2. 外部 benchmark：retrieval-first
.venv\Scripts\python.exe scripts\run_external_benchmark_evaluation.py `
  --case-limit 25 `
  --top-k 10 `
  --backend sentence-transformer `
  --model-name Qwen/Qwen3-Embedding-0.6B `
  --run-name quick_full_chain_probe

# 3. GraphRAG promoted case 回归
.venv\Scripts\python.exe scripts\run_graphrag_triage_regression.py `
  --backend sentence-transformer `
  --model-name Qwen/Qwen3-Embedding-0.6B `
  --top-k 10 `
  --allow-empty `
  --json
```

这仍然只是最小流程。正式验收必须加入真实清华燃气轮机文档、真实 GraphRAG 图谱、真实 LLM key、中文领域问题和人工抽检。

## 十二、正式报告必须包含的结论

报告最后必须用下面格式回答：

```text
结论：pass / fail / degraded / blocked
官方总分：有则填写公开 benchmark 给出的总分；没有则写“无官方综合分”
公开指标：列出 benchmark/tool 原始指标名和数值
是否全链路：是 / 否
没跑的环节：列出，没有则写 none
最弱环节：列出 1-3 个
最该优先修的事：列出 1-3 个
是否建议用于清华燃气轮机知识库试点：是 / 否 / 只建议内部试用
```

如果结论不是 `pass`，不得写“已经达到顶尖可交付”。只能写当前短板和下一轮优化计划。
