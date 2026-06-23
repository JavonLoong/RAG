# Full External RAG Benchmark Evaluation

- Run: `gemini_probe_1`
- Score type: `full_rag_generation_score`
- Overall score: **22.86 / 100** (poor)
- Total cases: 1
- Top K: 3
- LLM: `gemini-openai:gemini-3.5-flash`

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Answer completeness | Ref F1 | Retrieval recall | Missing citation | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| legal-rag-bench | 1 | 22.86 | poor | fail | 0.083333 | 0.197802 | 0.0 | 0.0 | D:\虚拟C盘\RAG\evaluation\reports\rag_eval_full_external_legal-rag-bench_20260620_163330.md |

## Limitations

- Generated answers are compared with gold references using deterministic keyword coverage and token F1.
- This does not use the gold answer in the answer-generation prompt.
- Token F1 can penalize correct paraphrases, so answer_completeness and retrieval metrics are reported together.
