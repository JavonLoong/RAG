# External RAG Benchmark Evaluation

- Run: `open_source_90_probe_legal3_keyword_cleanup`
- Score type: `retrieval_first_score`
- Overall score: **82.78 / 100** (usable)
- Total cases: 3
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| legal-rag-bench | 3 | 82.78 | usable | pass | 0.944444 | 0.333333 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_legal-rag-bench_20260621_145108.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
