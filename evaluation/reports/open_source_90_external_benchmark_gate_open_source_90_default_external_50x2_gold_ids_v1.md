# Open Source 90 External Benchmark Gate

- Profile: `open_source_90`
- Gate status: `fail`
- Overall score: 87.33 / 100
- Total cases: 100
- Source run: `open_source_90_default_external_50x2_gold_ids_v1`

## Benchmark Scores

| Benchmark | Cases | Score | Keyword recall | Gold id recall | No result rate | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| legal-rag-bench | 50 | 96.68 | 0.908333 | 1.0 | 0.0 | pass |
| ragbench-hotpotqa-validation | 50 | 77.99 | 0.691667 | 0.805031 | 0.0 | pass |

## Failures

| Scope | Metric | Actual | Rule | Threshold |
| --- | --- | ---: | --- | ---: |
| aggregate | overall_score_100 | 87.33 | >= | 90.0 |
| ragbench-hotpotqa-validation | score_100 | 77.99 | >= | 90.0 |
| ragbench-hotpotqa-validation | retrieval.gold_id_recall_at_k | 0.805031 | >= | 0.9 |

## Interpretation

This gate is the external benchmark counterpart to the local `quality:90` smoke gate. A pass here is required before claiming market-level 90% quality.
