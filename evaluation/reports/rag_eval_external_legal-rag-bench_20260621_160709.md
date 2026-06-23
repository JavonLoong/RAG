# RAG Evaluation Report

- Run: `external_legal-rag-bench`
- Gate status: `pass`
- Total questions: 5

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 5 |
| retrieval.question_recall_at_k | 1.0 |
| retrieval.keyword_recall_at_k | 1.0 |
| retrieval.average_keyword_coverage | 1.0 |
| retrieval.passage_id_recall_at_k | 1.0 |
| retrieval.passage_id_expected_count | 5 |
| retrieval.passage_id_hit_count | 5 |
| retrieval.full_evidence_coverage_rate | 1.0 |
| retrieval.no_result_rate | 0.0 |
| retrieval.average_retrieved_count_at_k | 10.0 |
| evidence.expected_keyword_total | 60 |
| evidence.retrieved_keyword_hit_total | 60 |
| evidence.evidence_keyword_hit_rate | 1.0 |
| evidence.question_with_any_evidence_rate | 1.0 |
| evidence.question_with_full_evidence_rate | 1.0 |
| citation.evaluated_questions | 5 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 1.0 |
| citation.average_citation_keyword_coverage | 1.0 |
| answer.evaluated_questions | 5 |
| answer.answer_contains_evidence_rate | 1.0 |
| answer.answer_completeness_avg | 1.0 |
| answer.complete_answer_rate | 1.0 |
| hallucination_risk.low_count | 5 |
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
| legal-2 | Harry is serving as a juror in a burglary trial. He is also a professional locksmith. During the proceedings, Harry is shown a lock which, in his expert view, is too damaged to have been lockpicked in the manner described in court. Why might Harry's expert knowledge of lockpicking be irrelevant when assessing the physical evidence? | 1.0 | 1.0 | False | low |
| legal-3 | Isaac is on trial for statutory murder of an emergency worker. You are his barrister. Should you notify the jury that, according to the Crimes Act 1958, the standard sentence for this offence is 30 years imprisonment? | 1.0 | 1.0 | False | low |
| legal-4 | Should jurors be excused if they have encountered news stories about the accused prior to the trial commencing? | 1.0 | 1.0 | False | low |
| legal-5 | Frank and Joe are jurors in an arson trial. Over the weekend, Joe finds photos of the accused holding a petrol canister and texts them to Frank. Having received this new information, what should Frank do? | 1.0 | 1.0 | False | low |
