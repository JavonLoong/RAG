# External RAG Benchmark Evaluation

- Run: `passage_boundary_legal_10_top10_v3`
- Score type: `retrieval_first_score`
- Overall score: **54.92 / 100** (weak)
- Total cases: 10
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| legal-rag-bench | 10 | 54.92 | weak | pass | 0.641667 | 0.0 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_legal-rag-bench_20260620_165154.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
