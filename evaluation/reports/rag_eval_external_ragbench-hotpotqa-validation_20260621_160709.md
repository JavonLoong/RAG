# RAG Evaluation Report

- Run: `external_ragbench-hotpotqa-validation`
- Gate status: `pass`
- Total questions: 5

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 5 |
| retrieval.question_recall_at_k | 1.0 |
| retrieval.keyword_recall_at_k | 0.616667 |
| retrieval.average_keyword_coverage | 0.616667 |
| retrieval.passage_id_recall_at_k | None |
| retrieval.passage_id_expected_count | 0 |
| retrieval.passage_id_hit_count | 0 |
| retrieval.full_evidence_coverage_rate | 0.0 |
| retrieval.no_result_rate | 0.0 |
| retrieval.average_retrieved_count_at_k | 10.0 |
| evidence.expected_keyword_total | 60 |
| evidence.retrieved_keyword_hit_total | 37 |
| evidence.evidence_keyword_hit_rate | 0.616667 |
| evidence.question_with_any_evidence_rate | 1.0 |
| evidence.question_with_full_evidence_rate | 0.0 |
| citation.evaluated_questions | 5 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.616667 |
| citation.average_citation_keyword_coverage | 0.616667 |
| answer.evaluated_questions | 5 |
| answer.answer_contains_evidence_rate | 1.0 |
| answer.answer_completeness_avg | 0.616667 |
| answer.complete_answer_rate | 0.0 |
| hallucination_risk.low_count | 3 |
| hallucination_risk.medium_count | 2 |
| hallucination_risk.high_count | 0 |
| hallucination_risk.not_applicable_count | 0 |
| hallucination_risk.high_risk_rate | 0.0 |
| hallucination_risk.medium_or_high_risk_rate | 0.4 |

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

| ID | Question | Retrieval Coverage | Missing Citation | Risk |
| --- | --- | ---: | --- | --- |
| ragbench-hotpotqa-validation-5ab3bd7d55429969a97a819f | Which team featured in both the 2012 and 2011 Cops del Rey Finals ? | 0.5 | False | medium |
| ragbench-hotpotqa-validation-5a79d2fe5542994f819ef0c3 | Who was born first, Aleksandr Ivanovsky or Arthur Lubin? | 0.5 | False | medium |

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| ragbench-hotpotqa-validation-5ab3bd7d55429969a97a819f | Which team featured in both the 2012 and 2011 Cops del Rey Finals ? | 0.5 | 0.5 | False | medium |
| ragbench-hotpotqa-validation-5ae1fd995542997283cd2313 | Is It Just Me? was a single by the English rock band from what Suffolk city? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5a79d2fe5542994f819ef0c3 | Who was born first, Aleksandr Ivanovsky or Arthur Lubin? | 0.5 | 0.5 | False | medium |
| ragbench-hotpotqa-validation-5a72814f5542994cef4bc2eb | The American Astronomical Society presents an award named after what New Zealand astronomer? | 0.666667 | 0.666667 | False | low |
| ragbench-hotpotqa-validation-5a8d7b1755429941ae14dfc6 | What is the 2010 population of the city 2.1 miles southwest of Marietta Air Force Station? | 0.666667 | 0.666667 | False | low |
