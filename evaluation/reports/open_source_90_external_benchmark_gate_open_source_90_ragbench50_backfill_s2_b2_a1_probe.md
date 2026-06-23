# Open Source 90 External Benchmark Gate

- Profile: `open_source_90`
- Gate status: `fail`
- Overall score: 85.03 / 100
- Total cases: 50
- Source run: `open_source_90_ragbench50_backfill_s2_b2_a1_probe`

## Benchmark Scores

| Benchmark | Cases | Score | Keyword recall | Gold id recall | No result rate | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| ragbench-hotpotqa-validation | 50 | 85.03 | 0.725 | 0.893082 | 0.0 | pass |

## Failures

| Scope | Metric | Actual | Rule | Threshold |
| --- | --- | ---: | --- | ---: |
| aggregate | overall_score_100 | 85.03 | >= | 90.0 |
| ragbench-hotpotqa-validation | score_100 | 85.03 | >= | 90.0 |
| ragbench-hotpotqa-validation | retrieval.gold_id_recall_at_k | 0.893082 | >= | 0.9 |

## Interpretation

This gate is the external benchmark counterpart to the local `quality:90` smoke gate. A pass here is required before claiming market-level 90% quality.
