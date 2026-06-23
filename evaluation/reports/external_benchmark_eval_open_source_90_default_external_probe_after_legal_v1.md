# External RAG Benchmark Evaluation

- Run: `open_source_90_default_external_probe_after_legal_v1`
- Score type: `retrieval_first_score`
- Overall score: **81.21 / 100** (usable)
- Total cases: 10
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Passage recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| legal-rag-bench | 5 | 100.0 | strong | pass | 1.0 | 1.0 | 1.0 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_legal-rag-bench_20260621_160709.md |
| ragbench-hotpotqa-validation | 5 | 62.42 | weak | pass | 0.616667 |  | 0.0 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_ragbench-hotpotqa-validation_20260621_160709.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
