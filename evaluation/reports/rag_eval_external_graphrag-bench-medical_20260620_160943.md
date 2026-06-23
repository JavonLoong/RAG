# RAG Evaluation Report

- Run: `external_graphrag-bench-medical`
- Gate status: `fail`
- Total questions: 25

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 25 |
| retrieval.question_recall_at_k | 0.96 |
| retrieval.keyword_recall_at_k | 0.405498 |
| retrieval.average_keyword_coverage | 0.406563 |
| retrieval.full_evidence_coverage_rate | 0.04 |
| retrieval.no_result_rate | 0.0 |
| retrieval.average_retrieved_count_at_k | 5.0 |
| evidence.expected_keyword_total | 291 |
| evidence.retrieved_keyword_hit_total | 118 |
| evidence.evidence_keyword_hit_rate | 0.405498 |
| evidence.question_with_any_evidence_rate | 0.96 |
| evidence.question_with_full_evidence_rate | 0.04 |
| citation.evaluated_questions | 25 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.405498 |
| citation.average_citation_keyword_coverage | 0.406563 |
| answer.evaluated_questions | 25 |
| answer.answer_contains_evidence_rate | 0.92 |
| answer.answer_completeness_avg | 0.399896 |
| answer.complete_answer_rate | 0.04 |
| hallucination_risk.low_count | 4 |
| hallucination_risk.medium_count | 19 |
| hallucination_risk.high_count | 2 |
| hallucination_risk.not_applicable_count | 0 |
| hallucination_risk.high_risk_rate | 0.08 |
| hallucination_risk.medium_or_high_risk_rate | 0.84 |

## Gate Failures

| Metric | Actual | Rule | Threshold |
| --- | ---: | --- | ---: |
| retrieval.keyword_recall_at_k | 0.405498 | >= | 0.6 |
| answer.answer_completeness_avg | 0.399896 | >= | 0.6 |
| hallucination_risk.medium_or_high_risk_rate | 0.84 | <= | 0.5 |

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
| graphrag-medical-Medical-a8bad1cf | From which cell type does basal cell carcinoma arise? | 0.583333 | False | medium |
| graphrag-medical-Medical-422500d5 | Which anatomical locations are most commonly affected by basal cell carcinoma? | 0.416667 | False | medium |
| graphrag-medical-Medical-6d2a190d | What is the primary risk factor for basal cell carcinoma? | 0.333333 | False | medium |
| graphrag-medical-Medical-5ad931db | How does fair skin affect the risk of developing BCC? | 0.333333 | False | medium |
| graphrag-medical-Medical-6b0f8bc4 | Does older age influence the risk of basal cell carcinoma? | 0.142857 | False | medium |
| graphrag-medical-Medical-75c9949b | How does family history impact the risk of basal cell carcinoma? | 0.333333 | False | medium |
| graphrag-medical-Medical-ec091b24 | Is immune suppression a risk factor for BCC? | 0.5 | False | medium |
| graphrag-medical-Medical-8d39da2e | What are common symptoms of basal cell carcinoma? | 0.083333 | False | medium |
| graphrag-medical-Medical-88c0b2ba | Which diagnostic methods are used for BCC? | 0.083333 | False | high |
| graphrag-medical-Medical-ec7d8801 | When might radiation therapy be used in BCC? | 0.583333 | False | medium |
| graphrag-medical-Medical-9797af69 | What is recurrence in the context of BCC? | 0.0 | False | high |
| graphrag-medical-Medical-6884d3fa | What does follow-up for BCC typically include? | 0.166667 | False | medium |
| graphrag-medical-Medical-97abee55 | What anatomical layer do basal cells belong to? | 0.545455 | False | medium |
| graphrag-medical-Medical-28d1e2d7 | Is sun exposure a risk factor for BCC? | 0.5 | False | medium |
| graphrag-medical-Medical-4cf524cb | Do tanning beds increase the risk of BCC? | 0.416667 | False | medium |
| graphrag-medical-Medical-df1408f4 | What hair and eye colors are associated with increased BCC risk? | 0.083333 | False | medium |
| graphrag-medical-Medical-17ae12cd | Can a history of radiation therapy increase BCC risk? | 0.583333 | False | medium |
| graphrag-medical-Medical-965ad8a8 | What is a common presentation of BCC on the skin? | 0.166667 | False | medium |
| graphrag-medical-Medical-5175a85e | What is the role of biopsy in BCC diagnosis? | 0.416667 | False | medium |
| graphrag-medical-Medical-0429f83c | What is included in the management of BCC recurrence? | 0.166667 | False | medium |
| graphrag-medical-Medical-152bec6a | What is the recommended frequency for full skin exams in BCC follow-up? | 0.166667 | False | medium |

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| graphrag-medical-Medical-73586ddc | What is the most common type of skin cancer? | 1.0 | 1.0 | False | low |
| graphrag-medical-Medical-a8bad1cf | From which cell type does basal cell carcinoma arise? | 0.583333 | 0.583333 | False | medium |
| graphrag-medical-Medical-422500d5 | Which anatomical locations are most commonly affected by basal cell carcinoma? | 0.416667 | 0.416667 | False | medium |
| graphrag-medical-Medical-6d2a190d | What is the primary risk factor for basal cell carcinoma? | 0.333333 | 0.333333 | False | medium |
| graphrag-medical-Medical-5ad931db | How does fair skin affect the risk of developing BCC? | 0.333333 | 0.333333 | False | medium |
| graphrag-medical-Medical-6b0f8bc4 | Does older age influence the risk of basal cell carcinoma? | 0.142857 | 0.142857 | False | medium |
| graphrag-medical-Medical-75c9949b | How does family history impact the risk of basal cell carcinoma? | 0.333333 | 0.333333 | False | medium |
| graphrag-medical-Medical-ec091b24 | Is immune suppression a risk factor for BCC? | 0.5 | 0.5 | False | medium |
| graphrag-medical-Medical-8d39da2e | What are common symptoms of basal cell carcinoma? | 0.083333 | 0.083333 | False | medium |
| graphrag-medical-Medical-88c0b2ba | Which diagnostic methods are used for BCC? | 0.083333 | 0.0 | False | high |
| graphrag-medical-Medical-a8ee8ba1 | What is the most common treatment for basal cell carcinoma? | 0.909091 | 0.909091 | False | low |
| graphrag-medical-Medical-ec7d8801 | When might radiation therapy be used in BCC? | 0.583333 | 0.583333 | False | medium |
| graphrag-medical-Medical-9797af69 | What is recurrence in the context of BCC? | 0.0 | 0.0 | False | high |
| graphrag-medical-Medical-6884d3fa | What does follow-up for BCC typically include? | 0.166667 | 0.166667 | False | medium |
| graphrag-medical-Medical-fc6d1c33 | Which skin cancer subtype arises from basal cells? | 0.75 | 0.75 | False | low |
| graphrag-medical-Medical-97abee55 | What anatomical layer do basal cells belong to? | 0.545455 | 0.545455 | False | medium |
| graphrag-medical-Medical-28d1e2d7 | Is sun exposure a risk factor for BCC? | 0.5 | 0.5 | False | medium |
| graphrag-medical-Medical-4cf524cb | Do tanning beds increase the risk of BCC? | 0.416667 | 0.416667 | False | medium |
| graphrag-medical-Medical-df1408f4 | What hair and eye colors are associated with increased BCC risk? | 0.083333 | 0.083333 | False | medium |
| graphrag-medical-Medical-17ae12cd | Can a history of radiation therapy increase BCC risk? | 0.583333 | 0.583333 | False | medium |
| graphrag-medical-Medical-965ad8a8 | What is a common presentation of BCC on the skin? | 0.166667 | 0.166667 | False | medium |
| graphrag-medical-Medical-5175a85e | What is the role of biopsy in BCC diagnosis? | 0.416667 | 0.333333 | False | medium |
| graphrag-medical-Medical-5f2cb8a5 | Which systemic therapy may be considered for BCC? | 0.9 | 0.9 | False | low |
| graphrag-medical-Medical-0429f83c | What is included in the management of BCC recurrence? | 0.166667 | 0.166667 | False | medium |
| graphrag-medical-Medical-152bec6a | What is the recommended frequency for full skin exams in BCC follow-up? | 0.166667 | 0.166667 | False | medium |
