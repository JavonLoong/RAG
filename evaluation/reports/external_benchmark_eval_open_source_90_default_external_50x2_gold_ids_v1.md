# External RAG Benchmark Evaluation

- Run: `open_source_90_default_external_50x2_gold_ids_v1`
- Score type: `retrieval_first_score`
- Overall score: **87.33 / 100** (strong)
- Total cases: 100
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Gold id recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| legal-rag-bench | 50 | 96.68 | strong | pass | 0.908333 | 1.0 | 0.52 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_legal-rag-bench_20260621_162630.md |
| ragbench-hotpotqa-validation | 50 | 77.99 | usable | pass | 0.691667 | 0.805031 | 0.14 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_ragbench-hotpotqa-validation_20260621_162642.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
