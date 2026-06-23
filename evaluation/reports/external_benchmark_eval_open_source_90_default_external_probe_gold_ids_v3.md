# External RAG Benchmark Evaluation

- Run: `open_source_90_default_external_probe_gold_ids_v3`
- Score type: `retrieval_first_score`
- Overall score: **90.79 / 100** (strong)
- Total cases: 10
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Gold id recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| legal-rag-bench | 5 | 100.0 | strong | pass | 1.0 | 1.0 | 1.0 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_legal-rag-bench_20260621_161543.md |
| ragbench-hotpotqa-validation | 5 | 81.58 | usable | pass | 0.616667 | 1.0 | 0.0 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_ragbench-hotpotqa-validation_20260621_161544.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
