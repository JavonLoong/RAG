# External RAG Benchmark Evaluation

- Run: `open_source_90_ragbench50_neighbors_a1_b2_c3_probe`
- Score type: `retrieval_first_score`
- Overall score: **83.94 / 100** (usable)
- Total cases: 50
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Gold id recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| ragbench-hotpotqa-validation | 50 | 83.94 | usable | pass | 0.71 | 0.880503 | 0.16 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_ragbench-hotpotqa-validation_20260621_164744.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
