# External RAG Benchmark Evaluation

- Run: `initial_25b`
- Score type: `retrieval_first_score`
- Overall score: **35.92 / 100** (poor)
- Total cases: 100
- Top K: 5

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| legal-rag-bench | 25 | 23.53 | poor | fail | 0.193333 | 0.0 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_legal-rag-bench_20260620_160936.md |
| graphrag-bench-medical | 25 | 39.18 | poor | fail | 0.405498 | 0.04 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_graphrag-bench-medical_20260620_160943.md |
| graphrag-bench-novel | 25 | 21.27 | poor | fail | 0.166667 | 0.0 | 0.04 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_graphrag-bench-novel_20260620_161018.md |
| ragbench-hotpotqa-validation | 25 | 59.7 | weak | fail | 0.67 | 0.24 | 0.2 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_ragbench-hotpotqa-validation_20260620_161020.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
