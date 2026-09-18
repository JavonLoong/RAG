# External RAG Benchmark Evaluation

- Run: `open_source_90_ragbench50_prefilter_v1`
- Score type: `retrieval_first_score`
- Overall score: **83.53 / 100** (usable)
- Total cases: 50
- Top K: 10

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Keyword recall | Gold id recall | Full coverage | No result rate | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| ragbench-hotpotqa-validation | 50 | 83.53 | usable | pass | 0.716667 | 0.874214 | 0.16 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_external_ragbench-hotpotqa-validation_20260621_163902.md |

## Limitations

- This run uses retrieved context as the answer, so it measures parsing, chunking, indexing, and retrieval first.
- It is not yet a full LLM generation quality score.
- Microsoft GraphRAG open-question datasets are not included in the numeric score because they do not ship ordinary gold answers.
