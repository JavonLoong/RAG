# External RAG Benchmark Evaluation

- Run: `passage_boundary_legal_50_top10_v4`
- Score type: `retrieval_first_score`
- Overall score: **33.33 / 100** (poor)
- Total cases: 50
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| legal-rag-bench | 50 | 33.33 | poor | fail | 0.333333 | 0.0 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_legal-rag-bench_20260620_165630.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
