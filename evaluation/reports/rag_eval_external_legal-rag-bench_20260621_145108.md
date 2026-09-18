# RAG Evaluation Report

- Run: `external_legal-rag-bench`
- Gate status: `pass`
- Total questions: 3

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 3 |
| retrieval.question_recall_at_k | 1.0 |
| retrieval.keyword_recall_at_k | 0.944444 |
| retrieval.average_keyword_coverage | 0.944445 |
| retrieval.full_evidence_coverage_rate | 0.333333 |
| retrieval.no_result_rate | 0.0 |
| retrieval.average_retrieved_count_at_k | 10.0 |
| evidence.expected_keyword_total | 36 |
| evidence.retrieved_keyword_hit_total | 34 |
| evidence.evidence_keyword_hit_rate | 0.944444 |
| evidence.question_with_any_evidence_rate | 1.0 |
| evidence.question_with_full_evidence_rate | 0.333333 |
| citation.evaluated_questions | 3 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.944444 |
| citation.average_citation_keyword_coverage | 0.944445 |
| answer.evaluated_questions | 3 |
| answer.answer_contains_evidence_rate | 1.0 |
| answer.answer_completeness_avg | 0.944445 |
| answer.complete_answer_rate | 0.333333 |
| hallucination_risk.low_count | 3 |
| hallucination_risk.medium_count | 0 |
| hallucination_risk.high_count | 0 |
| hallucination_risk.not_applicable_count | 0 |
| hallucination_risk.high_risk_rate | 0.0 |
| hallucination_risk.medium_or_high_risk_rate | 0.0 |

## Gate Failures

No gate failures.

## Retrieval Default Policy

| Setting | Recommendation |
| --- | --- |
| hybrid_rrf | True |
| metadata_filters | explicit_and_auto_source_filters |
| graph_retriever | enable_when_graph_db_path_and_graph_quality_pass |
| query_rewrite | keep_optional |
| reranker | none |
| no_answer_gate | keep_optional |

Triggered by metrics: `none`.

## Failure Cases

No failure cases.

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| legal-1 | Bob and Ted are close friends. Ted is on trial for drug offences, and Bob has been selected as a juror in Ted’s case. Is the judge required to excuse Bob from serving on the jury? | 1.0 | 1.0 | False | low |
| legal-2 | Harry is serving as a juror in a burglary trial. He is also a professional locksmith. During the proceedings, Harry is shown a lock which, in his expert view, is too damaged to have been lockpicked in the manner described in court. Why might Harry's expert knowledge of lockpicking be irrelevant when assessing the physical evidence? | 0.916667 | 0.916667 | False | low |
| legal-3 | Isaac is on trial for statutory murder of an emergency worker. You are his barrister. Should you notify the jury that, according to the Crimes Act 1958, the standard sentence for this offence is 30 years imprisonment? | 0.916667 | 0.916667 | False | low |
