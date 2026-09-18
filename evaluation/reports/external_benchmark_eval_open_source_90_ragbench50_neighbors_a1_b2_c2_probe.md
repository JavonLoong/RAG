# External RAG Benchmark Evaluation

- Run: `open_source_90_ragbench50_neighbors_a1_b2_c2_probe`
- Score type: `retrieval_first_score`
- Overall score: **85.4 / 100** (strong)
- Total cases: 50
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Gold id recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| ragbench-hotpotqa-validation | 50 | 85.4 | strong | pass | 0.715 | 0.899371 | 0.16 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_ragbench-hotpotqa-validation_20260621_164642.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
