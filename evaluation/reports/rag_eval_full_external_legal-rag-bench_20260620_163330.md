# RAG Evaluation Report

- Run: `full_external_legal-rag-bench`
- Gate status: `fail`
- Total questions: 1

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 1 |
| retrieval.question_recall_at_k | 0.0 |
| retrieval.keyword_recall_at_k | 0.0 |
| retrieval.average_keyword_coverage | 0.0 |
| retrieval.full_evidence_coverage_rate | 0.0 |
| retrieval.no_result_rate | 0.0 |
| retrieval.average_retrieved_count_at_k | 3.0 |
| evidence.expected_keyword_total | 12 |
| evidence.retrieved_keyword_hit_total | 0 |
| evidence.evidence_keyword_hit_rate | 0.0 |
| evidence.question_with_any_evidence_rate | 0.0 |
| evidence.question_with_full_evidence_rate | 0.0 |
| citation.evaluated_questions | 1 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.0 |
| citation.average_citation_keyword_coverage | 0.0 |
| answer.evaluated_questions | 1 |
| answer.answer_contains_evidence_rate | 1.0 |
| answer.answer_completeness_avg | 0.083333 |
| answer.complete_answer_rate | 0.0 |
| hallucination_risk.low_count | 0 |
| hallucination_risk.medium_count | 0 |
| hallucination_risk.high_count | 1 |
| hallucination_risk.not_applicable_count | 0 |
| hallucination_risk.high_risk_rate | 1.0 |
| hallucination_risk.medium_or_high_risk_rate | 1.0 |
| reference_match.evaluated_questions | 1 |
| reference_match.exact_match_rate | 0.0 |
| reference_match.average_token_f1 | 0.197802 |

## Gate Failures

| Metric | Actual | Rule | Threshold |
| --- | ---: | --- | ---: |
| retrieval.keyword_recall_at_k | 0.0 | >= | 0.6 |
| answer.answer_completeness_avg | 0.083333 | >= | 0.6 |
| hallucination_risk.medium_or_high_risk_rate | 1.0 | <= | 0.5 |

## Retrieval Default Policy

| Setting | Recommendation |
| --- | --- |
| hybrid_rrf | True |
| metadata_filters | explicit_and_auto_source_filters |
| graph_retriever | enable_when_graph_db_path_and_graph_quality_pass |
| query_rewrite | enable_by_default |
| reranker | cross_encoder |
| no_answer_gate | enable_with_calibrated_threshold |
| no_answer_min_score | calibrate_from_validation_set |

Triggered by metrics: `retrieval.keyword_recall_at_k, answer.answer_completeness_avg, hallucination_risk.medium_or_high_risk_rate`.

## Failure Cases

| ID | Question | Retrieval Coverage | Missing Citation | Risk |
| --- | --- | ---: | --- | --- |
| legal-1 | Bob and Ted are close friends. Ted is on trial for drug offences, and Bob has been selected as a juror in Ted’s case. Is the judge required to excuse Bob from serving on the jury? | 0.0 | False | high |

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| legal-1 | Bob and Ted are close friends. Ted is on trial for drug offences, and Bob has been selected as a juror in Ted’s case. Is the judge required to excuse Bob from serving on the jury? | 0.0 | 0.083333 | False | high |
