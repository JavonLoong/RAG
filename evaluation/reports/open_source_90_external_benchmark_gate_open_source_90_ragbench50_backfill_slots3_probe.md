# Open Source 90 External Benchmark Gate

- Profile: `open_source_90`
- Gate status: `fail`
- Overall score: 84.51 / 100
- Total cases: 50
- Source run: `open_source_90_ragbench50_backfill_slots3_probe`

## Benchmark Scores

| Benchmark | Cases | Score | Keyword recall | Gold id recall | No result rate | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| ragbench-hotpotqa-validation | 50 | 84.51 | 0.72 | 0.886792 | 0.0 | pass |

## Failures

| Scope | Metric | Actual | Rule | Threshold |
| --- | --- | ---: | --- | ---: |
| aggregate | overall_score_100 | 84.51 | >= | 90.0 |
| ragbench-hotpotqa-validation | score_100 | 84.51 | >= | 90.0 |
| ragbench-hotpotqa-validation | retrieval.gold_id_recall_at_k | 0.886792 | >= | 0.9 |

## Interpretation

This gate is the external benchmark counterpart to the local `quality:90` smoke gate. A pass here is required before claiming market-level 90% quality.
