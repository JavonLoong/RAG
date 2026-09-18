# Open Source 90 External Benchmark Gate

- Profile: `open_source_90`
- Gate status: `fail`
- Overall score: 90.79 / 100
- Total cases: 10
- Source run: `open_source_90_default_external_probe_gold_ids_v3`

## Benchmark Scores

| Benchmark | Cases | Score | Keyword recall | Gold id recall | No result rate | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| legal-rag-bench | 5 | 100.0 | 1.0 | 1.0 | 0.0 | pass |
| ragbench-hotpotqa-validation | 5 | 81.58 | 0.616667 | 1.0 | 0.0 | pass |

## Failures

| Scope | Metric | Actual | Rule | Threshold |
| --- | --- | ---: | --- | ---: |
| ragbench-hotpotqa-validation | score_100 | 81.58 | >= | 90.0 |
| ragbench-hotpotqa-validation | retrieval.keyword_recall_at_k | 0.616667 | >= | 0.9 |

## Interpretation

This gate is the external benchmark counterpart to the local `quality:90` smoke gate. A pass here is required before claiming market-level 90% quality.
