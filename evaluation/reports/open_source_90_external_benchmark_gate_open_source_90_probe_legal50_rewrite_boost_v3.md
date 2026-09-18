# Open Source 90 External Benchmark Gate

- Profile: `open_source_90`
- Gate status: `fail`
- Overall score: 78.8 / 100
- Total cases: 50
- Source run: `open_source_90_probe_legal50_rewrite_boost_v3`

## Benchmark Scores

| Benchmark | Cases | Score | Keyword recall | No result rate | Gate |
| --- | ---: | ---: | ---: | ---: | --- |
| legal-rag-bench | 50 | 78.8 | 0.88 | 0.0 | pass |

## Failures

| Scope | Metric | Actual | Rule | Threshold |
| --- | --- | ---: | --- | ---: |
| aggregate | overall_score_100 | 78.8 | >= | 90.0 |
| legal-rag-bench | score_100 | 78.8 | >= | 90.0 |
| legal-rag-bench | retrieval.keyword_recall_at_k | 0.88 | >= | 0.9 |

## Interpretation

This gate is the external benchmark counterpart to the local `quality:90` smoke gate. A pass here is required before claiming market-level 90% quality.
