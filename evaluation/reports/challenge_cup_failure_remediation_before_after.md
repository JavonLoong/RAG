# Failure Remediation Before/After

- report_type: `challenge_cup_failure_remediation_before_after`
- status: `remediation_card_ablation_ready_no_live_retriever_claim`
- analyzed_question_count: `40`
- before avg hybrid coverage: `0.371667`
- after avg effective coverage: `0.84125`
- before zero coverage: `11`
- after zero coverage: `0`

## Boundary

This is a remediation-card ablation over the fixed Day4 failure set. It proves which failures can be closed or bounded by explicit glossary, fact-card, structured-fact, and keyword-guardrail evidence; it is not a live retriever upgrade, not an online LLM answer win-rate, provides no award guarantee, and does not replace real expert feedback or real timed rehearsal evidence.

## Category Closure

| Category | Cases | Status | Avg after coverage |
| --- | ---: | --- | ---: |
| corpus_gap_or_query_gap | 1 | `closed_by_remediation_card` | 1.000000 |
| evaluation_concept_gap | 13 | `closed_by_remediation_card` | 1.000000 |
| exact_number_fact | 3 | `closed_by_remediation_card` | 1.000000 |
| hybrid_dilution | 17 | `bounded_by_keyword_guardrail` | 0.626471 |
| partial_ranking_gap | 2 | `closed_by_remediation_card` | 1.000000 |
| structured_fact_routing | 2 | `closed_by_remediation_card` | 1.000000 |
| terminology_alias_gap | 2 | `closed_by_remediation_card` | 1.000000 |

## Critical Cases

| Case | Status |
| --- | --- |
| se013 | `closed_or_bounded` |
| se024 | `closed_or_bounded` |
| se027 | `closed_or_bounded` |
| se028 | `closed_or_bounded` |

## Remediation Cards

- `evaluation_metric_glossary`: Defines context recall, citation coverage, hallucination risk, failure analysis, and benchmark boundaries.
- `kg_poc_fact_card`: Pins KG POC counts: 27 candidates, 26 correct, 1 discuss, 0 wrong, plus boundary claims.
- `goldwind_structured_fact_card`: Pins Goldwind decoded data facts: RUNDATA, parsed_data.csv, 12098 rows, 190 columns, and non-numeric fields.
- `reranker_alias_card`: Maps Reranker to 重排, 二次排序, Cross-Encoder, 精排, candidate evidence ordering, and Top-K context quality.
- `keyword_guardrail_policy`: For weak deterministic dense hashing, choose keyword-weighted fallback when keyword coverage beats hybrid RRF.
- `source_scope_routing_card`: Routes evaluation, demo fallback, KG POC, and source_scope questions to compact project evidence instead of long OCR chunks.

## Verification Commands

- `python scripts/build_challenge_cup_failure_remediation_before_after.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`
