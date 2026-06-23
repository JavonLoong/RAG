# Open Source 90 External Benchmark Gate

- Profile: `open_source_90`
- Gate status: `fail`
- Overall score: 85.34 / 100
- Total cases: 50
- Source run: `open_source_90_ragbench50_backfill_s2_b1_a2_probe`

## Benchmark Scores

| Benchmark | Cases | Score | Keyword recall | Gold id recall | No result rate | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| ragbench-hotpotqa-validation | 50 | 85.34 | 0.708333 | 0.899371 | 0.0 | pass |

## Failures

| Scope | Metric | Actual | Rule | Threshold |
| --- | --- | ---: | --- | ---: |
| aggregate | overall_score_100 | 85.34 | >= | 90.0 |
| ragbench-hotpotqa-validation | score_100 | 85.34 | >= | 90.0 |
| ragbench-hotpotqa-validation | retrieval.gold_id_recall_at_k | 0.899371 | >= | 0.9 |

## Interpretation

This gate is the external benchmark counterpart to the local `quality:90` smoke gate. A pass here is required before claiming market-level 90% quality.
