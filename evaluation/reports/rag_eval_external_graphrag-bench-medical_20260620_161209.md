# RAG Evaluation Report

- Run: `external_graphrag-bench-medical`
- Gate status: `fail`
- Total questions: 50

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 50 |
| retrieval.question_recall_at_k | 0.96 |
| retrieval.keyword_recall_at_k | 0.520646 |
| retrieval.average_keyword_coverage | 0.533117 |
| retrieval.full_evidence_coverage_rate | 0.08 |
| retrieval.no_result_rate | 0.0 |
| retrieval.average_retrieved_count_at_k | 10.0 |
| evidence.expected_keyword_total | 557 |
| evidence.retrieved_keyword_hit_total | 290 |
| evidence.evidence_keyword_hit_rate | 0.520646 |
| evidence.question_with_any_evidence_rate | 0.96 |
| evidence.question_with_full_evidence_rate | 0.08 |
| citation.evaluated_questions | 50 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.520646 |
| citation.average_citation_keyword_coverage | 0.533117 |
| answer.evaluated_questions | 50 |
| answer.answer_contains_evidence_rate | 0.96 |
| answer.answer_completeness_avg | 0.52645 |
| answer.complete_answer_rate | 0.08 |
| hallucination_risk.low_count | 20 |
| hallucination_risk.medium_count | 28 |
| hallucination_risk.high_count | 2 |
| hallucination_risk.not_applicable_count | 0 |
| hallucination_risk.high_risk_rate | 0.04 |
| hallucination_risk.medium_or_high_risk_rate | 0.6 |

## Gate Failures

| Metric | Actual | Rule | Threshold |
| --- | ---: | --- | ---: |
| retrieval.keyword_recall_at_k | 0.520646 | >= | 0.6 |
| answer.answer_completeness_avg | 0.52645 | >= | 0.6 |
| hallucination_risk.medium_or_high_risk_rate | 0.6 | <= | 0.5 |

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
| graphrag-medical-Medical-422500d5 | Which anatomical locations are most commonly affected by basal cell carcinoma? | 0.5 | False | medium |
| graphrag-medical-Medical-5ad931db | How does fair skin affect the risk of developing BCC? | 0.583333 | False | medium |
| graphrag-medical-Medical-6b0f8bc4 | Does older age influence the risk of basal cell carcinoma? | 0.285714 | False | medium |
| graphrag-medical-Medical-ec091b24 | Is immune suppression a risk factor for BCC? | 0.583333 | False | medium |
| graphrag-medical-Medical-8d39da2e | What are common symptoms of basal cell carcinoma? | 0.166667 | False | medium |
| graphrag-medical-Medical-88c0b2ba | Which diagnostic methods are used for BCC? | 0.166667 | False | medium |
| graphrag-medical-Medical-9797af69 | What is recurrence in the context of BCC? | 0.083333 | False | medium |
| graphrag-medical-Medical-6884d3fa | What does follow-up for BCC typically include? | 0.416667 | False | medium |
| graphrag-medical-Medical-4cf524cb | Do tanning beds increase the risk of BCC? | 0.416667 | False | medium |
| graphrag-medical-Medical-df1408f4 | What hair and eye colors are associated with increased BCC risk? | 0.083333 | False | medium |
| graphrag-medical-Medical-17ae12cd | Can a history of radiation therapy increase BCC risk? | 0.583333 | False | medium |
| graphrag-medical-Medical-965ad8a8 | What is a common presentation of BCC on the skin? | 0.166667 | False | medium |
| graphrag-medical-Medical-5175a85e | What is the role of biopsy in BCC diagnosis? | 0.416667 | False | medium |
| graphrag-medical-Medical-0429f83c | What is included in the management of BCC recurrence? | 0.333333 | False | medium |
| graphrag-medical-Medical-152bec6a | What is the recommended frequency for full skin exams in BCC follow-up? | 0.5 | False | medium |
| graphrag-medical-Medical-e3923e5f | Can BCC spread to lymph nodes? | 0.416667 | False | medium |
| graphrag-medical-Medical-b6dc1118 | What is the relationship between organ transplant and BCC risk? | 0.444444 | False | medium |
| graphrag-medical-Medical-ba2c8007 | Is autoimmune disease associated with increased BCC risk? | 0.555556 | False | medium |
| graphrag-medical-Medical-5c30dd24 | What is the role of imaging in BCC diagnosis? | 0.5 | False | medium |
| graphrag-medical-Medical-8622e4cc | Can BCC occur anywhere on the body? | 0.166667 | False | medium |
| graphrag-medical-Medical-941c0004 | Which anatomical locations are most commonly affected by BCC? | 0.0 | False | high |
| graphrag-medical-Medical-acec9fa2 | How does fair skin affect the risk of basal cell carcinoma? | 0.5 | False | medium |
| graphrag-medical-Medical-7c81f966 | Does older age influence the risk of BCC? | 0.428571 | False | medium |
| graphrag-medical-Medical-89de49a4 | What are common symptoms of basal cell carcinoma? | 0.166667 | False | medium |
| graphrag-medical-Medical-624c452d | What diagnostic methods are used for BCC? | 0.166667 | False | medium |
| graphrag-medical-Medical-cb249d9b | What does recurrence mean in the context of BCC? | 0.0 | False | high |
| graphrag-medical-Medical-e506aa4e | What is recommended for follow-up after BCC treatment? | 0.333333 | False | medium |
| graphrag-medical-Medical-0047c320 | Does having red or blond hair increase the risk of BCC? | 0.25 | False | medium |
| graphrag-medical-Medical-ca377f8d | Is light eye color associated with increased risk of BCC? | 0.333333 | False | medium |

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| graphrag-medical-Medical-73586ddc | What is the most common type of skin cancer? | 1.0 | 1.0 | False | low |
| graphrag-medical-Medical-a8bad1cf | From which cell type does basal cell carcinoma arise? | 0.583333 | 0.583333 | False | medium |
| graphrag-medical-Medical-422500d5 | Which anatomical locations are most commonly affected by basal cell carcinoma? | 0.5 | 0.5 | False | medium |
| graphrag-medical-Medical-6d2a190d | What is the primary risk factor for basal cell carcinoma? | 0.666667 | 0.666667 | False | low |
| graphrag-medical-Medical-5ad931db | How does fair skin affect the risk of developing BCC? | 0.583333 | 0.583333 | False | medium |
| graphrag-medical-Medical-6b0f8bc4 | Does older age influence the risk of basal cell carcinoma? | 0.285714 | 0.285714 | False | medium |
| graphrag-medical-Medical-75c9949b | How does family history impact the risk of basal cell carcinoma? | 0.75 | 0.75 | False | low |
| graphrag-medical-Medical-ec091b24 | Is immune suppression a risk factor for BCC? | 0.583333 | 0.583333 | False | medium |
| graphrag-medical-Medical-8d39da2e | What are common symptoms of basal cell carcinoma? | 0.166667 | 0.166667 | False | medium |
| graphrag-medical-Medical-88c0b2ba | Which diagnostic methods are used for BCC? | 0.166667 | 0.083333 | False | medium |
| graphrag-medical-Medical-a8ee8ba1 | What is the most common treatment for basal cell carcinoma? | 1.0 | 1.0 | False | low |
| graphrag-medical-Medical-ec7d8801 | When might radiation therapy be used in BCC? | 0.75 | 0.75 | False | low |
| graphrag-medical-Medical-9797af69 | What is recurrence in the context of BCC? | 0.083333 | 0.083333 | False | medium |
| graphrag-medical-Medical-6884d3fa | What does follow-up for BCC typically include? | 0.416667 | 0.416667 | False | medium |
| graphrag-medical-Medical-fc6d1c33 | Which skin cancer subtype arises from basal cells? | 0.833333 | 0.833333 | False | low |
| graphrag-medical-Medical-97abee55 | What anatomical layer do basal cells belong to? | 0.727273 | 0.727273 | False | low |
| graphrag-medical-Medical-28d1e2d7 | Is sun exposure a risk factor for BCC? | 0.833333 | 0.833333 | False | low |
| graphrag-medical-Medical-4cf524cb | Do tanning beds increase the risk of BCC? | 0.416667 | 0.416667 | False | medium |
| graphrag-medical-Medical-df1408f4 | What hair and eye colors are associated with increased BCC risk? | 0.083333 | 0.083333 | False | medium |
| graphrag-medical-Medical-17ae12cd | Can a history of radiation therapy increase BCC risk? | 0.583333 | 0.583333 | False | medium |
| graphrag-medical-Medical-965ad8a8 | What is a common presentation of BCC on the skin? | 0.166667 | 0.166667 | False | medium |
| graphrag-medical-Medical-5175a85e | What is the role of biopsy in BCC diagnosis? | 0.416667 | 0.333333 | False | medium |
| graphrag-medical-Medical-5f2cb8a5 | Which systemic therapy may be considered for BCC? | 0.9 | 0.9 | False | low |
| graphrag-medical-Medical-0429f83c | What is included in the management of BCC recurrence? | 0.333333 | 0.333333 | False | medium |
| graphrag-medical-Medical-152bec6a | What is the recommended frequency for full skin exams in BCC follow-up? | 0.5 | 0.5 | False | medium |
| graphrag-medical-Medical-e3923e5f | Can BCC spread to lymph nodes? | 0.416667 | 0.416667 | False | medium |
| graphrag-medical-Medical-0c2f999d | What is a brown or glossy black bump with rolled border a symptom of? | 0.916667 | 0.916667 | False | low |
| graphrag-medical-Medical-b6dc1118 | What is the relationship between organ transplant and BCC risk? | 0.444444 | 0.444444 | False | medium |
| graphrag-medical-Medical-ba2c8007 | Is autoimmune disease associated with increased BCC risk? | 0.555556 | 0.555556 | False | medium |
| graphrag-medical-Medical-5c30dd24 | What is the role of imaging in BCC diagnosis? | 0.5 | 0.416667 | False | medium |
| graphrag-medical-Medical-8622e4cc | Can BCC occur anywhere on the body? | 0.166667 | 0.166667 | False | medium |
| graphrag-medical-Medical-b0b58bf2 | What is the most common type of skin cancer? | 1.0 | 1.0 | False | low |
| graphrag-medical-Medical-90704d0a | From which cells does basal cell carcinoma arise? | 0.6 | 0.6 | False | low |
| graphrag-medical-Medical-941c0004 | Which anatomical locations are most commonly affected by BCC? | 0.0 | 0.0 | False | high |
| graphrag-medical-Medical-4bb300c3 | What is the primary risk factor for developing basal cell carcinoma? | 0.75 | 0.75 | False | low |
| graphrag-medical-Medical-acec9fa2 | How does fair skin affect the risk of basal cell carcinoma? | 0.5 | 0.5 | False | medium |
| graphrag-medical-Medical-7c81f966 | Does older age influence the risk of BCC? | 0.428571 | 0.428571 | False | medium |
| graphrag-medical-Medical-f6b5155a | Does a family history of skin cancer affect the risk of BCC? | 0.75 | 0.75 | False | low |
| graphrag-medical-Medical-4061f8c4 | Is immune suppression a risk factor for basal cell carcinoma? | 0.833333 | 0.833333 | False | low |
| graphrag-medical-Medical-89de49a4 | What are common symptoms of basal cell carcinoma? | 0.166667 | 0.166667 | False | medium |
| graphrag-medical-Medical-624c452d | What diagnostic methods are used for BCC? | 0.166667 | 0.083333 | False | medium |
| graphrag-medical-Medical-4aab8ef7 | What is the most common treatment for basal cell carcinoma? | 1.0 | 1.0 | False | low |
| graphrag-medical-Medical-bc412bb6 | When might radiation therapy or systemic therapy be used for BCC? | 0.9 | 0.9 | False | low |
| graphrag-medical-Medical-cb249d9b | What does recurrence mean in the context of BCC? | 0.0 | 0.0 | False | high |
| graphrag-medical-Medical-e506aa4e | What is recommended for follow-up after BCC treatment? | 0.333333 | 0.333333 | False | medium |
| graphrag-medical-Medical-14cee623 | Which cell type is affected in basal cell carcinoma? | 0.6 | 0.6 | False | low |
| graphrag-medical-Medical-ae28e711 | Is sun exposure a risk factor for BCC? | 0.857143 | 0.857143 | False | low |
| graphrag-medical-Medical-2bef6940 | Are tanning beds considered a risk factor for BCC? | 0.857143 | 0.857143 | False | low |
| graphrag-medical-Medical-0047c320 | Does having red or blond hair increase the risk of BCC? | 0.25 | 0.25 | False | medium |
| graphrag-medical-Medical-ca377f8d | Is light eye color associated with increased risk of BCC? | 0.333333 | 0.333333 | False | medium |
