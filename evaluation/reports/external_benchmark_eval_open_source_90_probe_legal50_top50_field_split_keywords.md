# External RAG Benchmark Evaluation

- Run: `open_source_90_probe_legal50_top50_field_split_keywords`
- Score type: `retrieval_first_score`
- Overall score: **61.63 / 100** (weak)
- Total cases: 50
- Top K: 50

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| legal-rag-bench | 50 | 61.63 | weak | pass | 0.663333 | 0.26 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_legal-rag-bench_20260621_150219.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
