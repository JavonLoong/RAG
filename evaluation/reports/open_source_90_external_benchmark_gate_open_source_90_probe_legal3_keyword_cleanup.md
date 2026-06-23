# Open Source 90 External Benchmark Gate

- Profile: `open_source_90`
- Gate status: `fail`
- Overall score: 82.78 / 100
- Total cases: 3
- Source run: `open_source_90_probe_legal3_keyword_cleanup`

## Benchmark Scores

| Benchmark | Cases | Score | Keyword recall | No result rate | Gate |
| --- | ---: | ---: | ---: | ---: | --- |
| legal-rag-bench | 3 | 82.78 | 0.944444 | 0.0 | pass |

## Failures

| Scope | Metric | Actual | Rule | Threshold |
| --- | --- | ---: | --- | ---: |
| aggregate | overall_score_100 | 82.78 | >= | 90.0 |
| legal-rag-bench | score_100 | 82.78 | >= | 90.0 |

## Interpretation

This gate is the external benchmark counterpart to the local `quality:90` smoke gate. A pass here is required before claiming market-level 90% quality.
