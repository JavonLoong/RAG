# Open Source 90 External Benchmark Gate

- Profile: `open_source_90`
- Gate status: `fail`
- Overall score: 49.0 / 100
- Total cases: 50
- Source run: `open_source_90_probe_legal50_field_split_keywords`

## Benchmark Scores

| Benchmark | Cases | Score | Keyword recall | No result rate | Gate |
| --- | ---: | ---: | ---: | ---: | --- |
| legal-rag-bench | 50 | 49.0 | 0.5 | 0.0 | fail |

## Failures

| Scope | Metric | Actual | Rule | Threshold |
| --- | --- | ---: | --- | ---: |
| aggregate | overall_score_100 | 49.0 | >= | 90.0 |
| legal-rag-bench | score_100 | 49.0 | >= | 90.0 |
| legal-rag-bench | retrieval.keyword_recall_at_k | 0.5 | >= | 0.9 |

## Warnings

- legal-rag-bench harness gate_status=fail

## Interpretation

This gate is the external benchmark counterpart to the local `quality:90` smoke gate. A pass here is required before claiming market-level 90% quality.
