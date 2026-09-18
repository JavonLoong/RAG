# Full External RAG Benchmark Evaluation

- Run: `gemini_full_20260620_1640`
- Score type: `full_rag_generation_score`
- Overall score: ** / 100** (partial)
- Total cases: 2062
- Completed cases: 100
- Top K: 10
- LLM: `gemini-openai:gemini-3.5-flash`

## Benchmark Scores

| Benchmark | Cases | Score | Band | Gate | Answer completeness | Ref F1 | Retrieval recall | Missing citation | Report |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| graphrag-bench-medical | 2062 | None | partial | partial |  |  |  |  |  |

## Limitations

- Generated answers are compared with gold references using deterministic keyword coverage and token F1.
- This does not use the gold answer in the answer-generation prompt.
- Token F1 can penalize correct paraphrases, so answer_completeness and retrieval metrics are reported together.
