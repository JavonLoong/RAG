# Day 3 Retrieval Baseline Comparison

- Generated at: 2026-06-05T21:05:40
- Corpus chunks: 6494
- Chunk size / overlap: 900 / 120
- Top K: 5

## Method Summary

| Method | Questions | Matched outputs | Question recall@K | Keyword recall@K | Avg keyword coverage | Strong | Weak | Missed | Zero-hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| keyword | 60 | 60 | 0.833333 | 0.540268 | 0.563056 | 25 | 25 | 10 | 0 |
| dense_hashing | 60 | 60 | 0.583333 | 0.281879 | 0.299722 | 12 | 23 | 25 | 0 |
| hybrid_rrf | 60 | 60 | 0.816667 | 0.500000 | 0.519722 | 24 | 25 | 11 | 0 |

## Interpretation

- `keyword` is the sparse baseline. It is good at explicit terms such as equipment names, fields, and report numbers.
- `dense_hashing` is an offline deterministic dense-style baseline. It does not represent final embedding quality, but it gives a reproducible semantic-ish baseline without model downloads.
- `hybrid_rrf` fuses keyword and dense hashing with reciprocal rank fusion.
- Best Day 3 baseline by average keyword coverage: `keyword`.

## Case Picks

### Successes

| ID | Type | Question | Retrieval coverage | Notes |
| --- | --- | --- | ---: | --- |
| se001 | standard_rag_fact | 燃气-蒸汽联合循环为什么通常比单一燃气轮机循环效率更高？ | 0.750000 | 应检索到联合循环、余热利用、蒸汽轮机或能量梯级利用相关证据，不能只泛泛说效率高。 |
| se002 | standard_rag_fact | 压气机在燃气轮机中的主要作用是什么？ | 0.750000 | 答案应说明压气机与燃烧室、空气压力/流量之间的关系。 |
| se004 | standard_rag_fact | 涡轮为什么能够输出机械功？ | 1.000000 | 应命中涡轮膨胀做功和驱动压气机/负载的证据。 |

### Partial

| ID | Type | Question | Retrieval coverage | Notes |
| --- | --- | --- | ---: | --- |
| se003 | standard_rag_fact | 燃烧室在燃气轮机热力循环中承担什么功能？ | 0.500000 | 应覆盖燃料燃烧、压缩空气和高温燃气，避免只写燃烧室是燃烧的地方。 |
| se010 | standard_rag_process | 设备维修报告中，哪些信息最适合作为 RAG 检索的证据片段？ | 0.250000 | 应说明证据片段应包含事实、原因和处理结果，不应只说全文入库。 |
| se021 | kg_graph_rag | 知识图谱 POC 中 schema 约束的作用是什么？ | 0.500000 | 应检索到 schema、实体/关系约束和三元组校验相关证据。 |

### Failures

| ID | Type | Question | Retrieval coverage | Notes |
| --- | --- | --- | ---: | --- |
| se013 | standard_rag_process | Reranker 在 RAG 流程中的作用是什么？ | 0.000000 | 应说明 reranker 是召回后的二次排序环节，不应误解为向量数据库。 |
| se015 | answer_quality | 如果检索结果没有覆盖标准答案中的关键证据，生成模型可能出现什么风险？ | 0.000000 | 应把检索覆盖不足和生成幻觉风险联系起来。 |
| se024 | kg_graph_rag | 当前知识图谱 POC 的人工评审结果是多少？ | 0.000000 | 应准确命中数量，不能把 27 条和 26 条混淆。 |

## Generated Files

- keyword outputs: `D:\虚拟C盘\RAG\evaluation\reports\day3_retrieval_outputs_keyword_20260605_210540.jsonl`
- keyword report JSON: `D:\虚拟C盘\RAG\evaluation\reports\system_eval_day3_keyword_20260605_210540.json`
- keyword report Markdown: `D:\虚拟C盘\RAG\evaluation\reports\system_eval_day3_keyword_20260605_210540.md`
- dense_hashing outputs: `D:\虚拟C盘\RAG\evaluation\reports\day3_retrieval_outputs_dense_hashing_20260605_210540.jsonl`
- dense_hashing report JSON: `D:\虚拟C盘\RAG\evaluation\reports\system_eval_day3_dense_hashing_20260605_210540.json`
- dense_hashing report Markdown: `D:\虚拟C盘\RAG\evaluation\reports\system_eval_day3_dense_hashing_20260605_210540.md`
- hybrid_rrf outputs: `D:\虚拟C盘\RAG\evaluation\reports\day3_retrieval_outputs_hybrid_rrf_20260605_210540.jsonl`
- hybrid_rrf report JSON: `D:\虚拟C盘\RAG\evaluation\reports\system_eval_day3_hybrid_rrf_20260605_210540.json`
- hybrid_rrf report Markdown: `D:\虚拟C盘\RAG\evaluation\reports\system_eval_day3_hybrid_rrf_20260605_210540.md`
