# External RAG Benchmark Evaluation

- Run: `open_source_90_probe_legal50_passage_score_v6`
- Score type: `retrieval_first_score`
- Overall score: **93.47 / 100** (strong)
- Total cases: 50
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |
| legal-rag-bench | 50 | 93.47 | strong | pass | 0.908333 | 0.52 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_legal-rag-bench_20260621_160102.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
