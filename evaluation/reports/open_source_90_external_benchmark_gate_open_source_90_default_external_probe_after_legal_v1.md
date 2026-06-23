# Open Source 90 External Benchmark Gate

- Profile: `open_source_90`
- Gate status: `fail`
- Overall score: 81.21 / 100
- Total cases: 10
- Source run: `open_source_90_default_external_probe_after_legal_v1`

## Benchmark Scores

| Benchmark | Cases | Score | Keyword recall | Passage recall | No result rate | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| legal-rag-bench | 5 | 100.0 | 1.0 | 1.0 | 0.0 | pass |
| ragbench-hotpotqa-validation | 5 | 62.42 | 0.616667 |  | 0.0 | pass |

## Failures

| Scope | Metric | Actual | Rule | Threshold |
| --- | --- | ---: | --- | ---: |
| aggregate | overall_score_100 | 81.21 | >= | 90.0 |
| ragbench-hotpotqa-validation | score_100 | 62.42 | >= | 90.0 |
| ragbench-hotpotqa-validation | retrieval.keyword_recall_at_k | 0.616667 | >= | 0.9 |

## Interpretation

This gate is the external benchmark counterpart to the local `quality:90` smoke gate. A pass here is required before claiming market-level 90% quality.
