# External RAG Benchmark Evaluation

- Run: `initial_50_top10`
- Score type: `retrieval_first_score`
- Overall score: **39.05 / 100** (poor)
- Total cases: 200
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| legal-rag-bench | 50 | 23.18 | poor | fail | 0.188333 | 0.0 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_legal-rag-bench_20260620_161156.md |
| graphrag-bench-medical | 50 | 48.05 | poor | fail | 0.520646 | 0.08 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_graphrag-bench-medical_20260620_161209.md |
| graphrag-bench-novel | 50 | 27.32 | poor | fail | 0.244505 | 0.02 | 0.02 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_graphrag-bench-novel_20260620_161305.md |
| ragbench-hotpotqa-validation | 50 | 57.63 | weak | fail | 0.643333 | 0.24 | 0.22 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_ragbench-hotpotqa-validation_20260620_161310.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
