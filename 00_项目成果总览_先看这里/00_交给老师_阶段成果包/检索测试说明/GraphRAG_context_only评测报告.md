# System Evaluation Report

- Generated at: 2026-05-21T12:50:28
- Questions: 1
- Top K: 3
- Retrieval only: True
- Matched outputs: 1
- Missing outputs: 0

## Metrics

| Group | Metric | Value |
| --- | --- | --- |
| retrieval | evaluated_questions | 1 |
| retrieval | question_recall_at_k | 0.000000 |
| retrieval | keyword_recall_at_k | 0.000000 |
| retrieval | average_keyword_coverage | 0.000000 |
| retrieval | full_evidence_coverage_rate | 0.000000 |
| retrieval | no_result_rate | 0.000000 |
| retrieval | average_retrieved_count_at_k | 3.000000 |
| evidence | expected_keyword_total | 2 |
| evidence | retrieved_keyword_hit_total | 0 |
| evidence | evidence_keyword_hit_rate | 0.000000 |
| evidence | question_with_any_evidence_rate | 0.000000 |
| evidence | question_with_full_evidence_rate | 0.000000 |
| citation | evaluated_questions | 0 |
| citation | citation_present_rate | - |
| citation | missing_citation_rate | - |
| citation | citation_keyword_hit_rate | - |
| citation | average_citation_keyword_coverage | - |
| answer | evaluated_questions | 0 |
| answer | answer_contains_evidence_rate | - |
| answer | answer_completeness_avg | - |
| answer | complete_answer_rate | - |
| hallucination_risk | low_count | 0 |
| hallucination_risk | medium_count | 0 |
| hallucination_risk | high_count | 0 |
| hallucination_risk | not_applicable_count | 1 |
| hallucination_risk | high_risk_rate | - |
| hallucination_risk | medium_or_high_risk_rate | - |

## Task Types

| Task type | Count |
| --- | --- |
| graphrag_context_probe | 1 |

## Cases

| ID | Type | Question | Retrieval coverage | Answer coverage | Missing citation | Risk | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| graphrag_probe_001 | graphrag_context_probe | combustor efficiency | 0.000000 | - | - | not_applicable | Integration probe for GraphRAG context-only output; not a final quality benchmark. |
