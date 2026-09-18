# RAG Evaluation Report

- Run: `external_graphrag-bench-novel`
- Gate status: `fail`
- Total questions: 25

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 25 |
| retrieval.question_recall_at_k | 0.52 |
| retrieval.keyword_recall_at_k | 0.166667 |
| retrieval.average_keyword_coverage | 0.134603 |
| retrieval.full_evidence_coverage_rate | 0.0 |
| retrieval.no_result_rate | 0.04 |
| retrieval.average_retrieved_count_at_k | 4.8 |
| evidence.expected_keyword_total | 216 |
| evidence.retrieved_keyword_hit_total | 36 |
| evidence.evidence_keyword_hit_rate | 0.166667 |
| evidence.question_with_any_evidence_rate | 0.52 |
| evidence.question_with_full_evidence_rate | 0.0 |
| citation.evaluated_questions | 24 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.173077 |
| citation.average_citation_keyword_coverage | 0.140212 |
| answer.evaluated_questions | 24 |
| answer.answer_contains_evidence_rate | 0.541667 |
| answer.answer_completeness_avg | 0.140212 |
| answer.complete_answer_rate | 0.0 |
| hallucination_risk.low_count | 1 |
| hallucination_risk.medium_count | 12 |
| hallucination_risk.high_count | 11 |
| hallucination_risk.not_applicable_count | 1 |
| hallucination_risk.high_risk_rate | 0.458333 |
| hallucination_risk.medium_or_high_risk_rate | 0.958333 |

## Gate Failures

| Metric | Actual | Rule | Threshold |
| --- | ---: | --- | ---: |
| retrieval.keyword_recall_at_k | 0.166667 | >= | 0.6 |
| answer.answer_completeness_avg | 0.140212 | >= | 0.6 |
| hallucination_risk.medium_or_high_risk_rate | 0.958333 | <= | 0.5 |

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
| graphrag-novel-Novel-73586ddc | In the narrative of 'An Unsentimental Journey through Cornwall', which plant known scientifically as Erica vagans is also referred to by another common name, and what is that name? | 0.166667 | False | medium |
| graphrag-novel-Novel-74440a6a | Within the account of the royal visit to St. Michael's Mount in Cornwall, who is identified as the person who married Princess Frederica of Hanover? | 0.0 | False | high |
| graphrag-novel-Novel-f80cbf85 | According to the narrative's discussion of historic sites, in which region of France is Mont St. Michel located? | 0.125 | False | medium |
| graphrag-novel-Novel-b3c430ef | In the historical account relating to St. Michael's Mount, which individual is said to have caused himself to be bled to death there? | 0.0 | False | high |
| graphrag-novel-Novel-304b0354 | Within the Cornish legends described in the narrative, who was the figure doomed to empty Dozmare Pool as a punishment? | 0.0 | False | high |
| graphrag-novel-Novel-e05d0922 | According to the description of Kynance Cove in Cornwall, which specific feature is included as a part of Kynance Cove? | 0.25 | False | medium |
| graphrag-novel-Novel-dba48e64 | In the account of the travelers' visit to Kynance Cove, what natural landmarks are mentioned as being located near or within Kynance Cove, such as Asparagus Island, Gull Rock, and Bellows? | 0.25 | False | medium |
| graphrag-novel-Novel-ea3d4859 | During the travelers' exploration of the Cornish coastline in the narrative, what notable geographical feature is located near Housel Cove? | 0.111111 | False | medium |
| graphrag-novel-Novel-ba894e2c | In the retelling of the Arthurian legend within the novel, who is the character credited with producing King Arthur? | 0.0 | False | high |
| graphrag-novel-Novel-42f1975a | According to the narrative's summary of Arthurian history, who was proclaimed king after the death of Uther Pendragon? | 0.583333 | False | medium |
| graphrag-novel-Novel-419cadfe | Within the summary of Arthurian legend provided in the narrative, with whom did King Arthur engage in battle? | 0.142857 | False | medium |
| graphrag-novel-Novel-9e7500a0 | In the context of the Arthurian story as recounted in the narrative, which character fell in love with Ygrayne, leading to significant events in the legend? | 0.125 | False | medium |
| graphrag-novel-Novel-bffd01c2 | In the novel's retelling of the end of King Arthur's story, who was the knight entrusted to throw the sword Excalibur into the mere? | 0.0 | False | not_applicable |
| graphrag-novel-Novel-ef451592 | Aside from Penolver, what other prominent feature is described as being near Housel Cove in the narrative? | 0.111111 | False | medium |
| graphrag-novel-Novel-eab59fae | According to the journey described in the narrative, in which county of England is the town of Marazion located? | 0.0 | False | high |
| graphrag-novel-Novel-61cf41ee | During the journey through Cornwall, who is identified as the driver responsible for transporting the main party by carriage? | 0.0 | False | high |
| graphrag-novel-Novel-09d21113 | In the account of the road journey after passing through Penzance, to which location did Charles travel with the carriage? | 0.416667 | False | medium |
| graphrag-novel-Novel-1b7a0e02 | During the first evening at The Lizard, what did Charles call out excitedly upon seeing the lights, as described in the narrative? | 0.0 | False | high |
| graphrag-novel-Novel-752ca0c2 | In the context of the story's visit to Mullion, which individual did Mary Mundy express her admiration for? | 0.0 | False | high |
| graphrag-novel-Novel-4ae5ec38 | Within the travel narrative, in which English county is Whitesand Bay described as being located? | 0.0 | False | high |
| graphrag-novel-Novel-563587c2 | On the occasion of their outing described in the narrative, to which destination did the carriage ultimately travel? | 0.333333 | False | medium |
| graphrag-novel-Novel-6aaabde4 | Within the story's depiction of the Old Inn at Mullion, who is credited with writing a poem about Mary Mundy? | 0.083333 | False | medium |
| graphrag-novel-Novel-2e9466a9 | According to the journey through coastal villages described in the book, where is the fishing village of Cadgwith located? | 0.0 | False | high |
| graphrag-novel-Novel-d2746bf8 | During the visit to Mullion, who was mentioned as being considered the best ghost-layer in England? | 0.0 | False | high |

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| graphrag-novel-Novel-73586ddc | In the narrative of 'An Unsentimental Journey through Cornwall', which plant known scientifically as Erica vagans is also referred to by another common name, and what is that name? | 0.166667 | 0.166667 | False | medium |
| graphrag-novel-Novel-74440a6a | Within the account of the royal visit to St. Michael's Mount in Cornwall, who is identified as the person who married Princess Frederica of Hanover? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-f80cbf85 | According to the narrative's discussion of historic sites, in which region of France is Mont St. Michel located? | 0.125 | 0.125 | False | medium |
| graphrag-novel-Novel-b3c430ef | In the historical account relating to St. Michael's Mount, which individual is said to have caused himself to be bled to death there? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-304b0354 | Within the Cornish legends described in the narrative, who was the figure doomed to empty Dozmare Pool as a punishment? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-b1a95144 | In reference to the royal visit to St. Michael's Mount described in the narrative, to which princess did the Queen show motherly kindness during her stay? | 0.666667 | 0.666667 | False | low |
| graphrag-novel-Novel-e05d0922 | According to the description of Kynance Cove in Cornwall, which specific feature is included as a part of Kynance Cove? | 0.25 | 0.25 | False | medium |
| graphrag-novel-Novel-dba48e64 | In the account of the travelers' visit to Kynance Cove, what natural landmarks are mentioned as being located near or within Kynance Cove, such as Asparagus Island, Gull Rock, and Bellows? | 0.25 | 0.25 | False | medium |
| graphrag-novel-Novel-ea3d4859 | During the travelers' exploration of the Cornish coastline in the narrative, what notable geographical feature is located near Housel Cove? | 0.111111 | 0.111111 | False | medium |
| graphrag-novel-Novel-ba894e2c | In the retelling of the Arthurian legend within the novel, who is the character credited with producing King Arthur? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-42f1975a | According to the narrative's summary of Arthurian history, who was proclaimed king after the death of Uther Pendragon? | 0.583333 | 0.583333 | False | medium |
| graphrag-novel-Novel-419cadfe | Within the summary of Arthurian legend provided in the narrative, with whom did King Arthur engage in battle? | 0.142857 | 0.142857 | False | medium |
| graphrag-novel-Novel-9e7500a0 | In the context of the Arthurian story as recounted in the narrative, which character fell in love with Ygrayne, leading to significant events in the legend? | 0.125 | 0.125 | False | medium |
| graphrag-novel-Novel-bffd01c2 | In the novel's retelling of the end of King Arthur's story, who was the knight entrusted to throw the sword Excalibur into the mere? | 0.0 | None | False | not_applicable |
| graphrag-novel-Novel-ef451592 | Aside from Penolver, what other prominent feature is described as being near Housel Cove in the narrative? | 0.111111 | 0.111111 | False | medium |
| graphrag-novel-Novel-eab59fae | According to the journey described in the narrative, in which county of England is the town of Marazion located? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-61cf41ee | During the journey through Cornwall, who is identified as the driver responsible for transporting the main party by carriage? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-09d21113 | In the account of the road journey after passing through Penzance, to which location did Charles travel with the carriage? | 0.416667 | 0.416667 | False | medium |
| graphrag-novel-Novel-1b7a0e02 | During the first evening at The Lizard, what did Charles call out excitedly upon seeing the lights, as described in the narrative? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-752ca0c2 | In the context of the story's visit to Mullion, which individual did Mary Mundy express her admiration for? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-4ae5ec38 | Within the travel narrative, in which English county is Whitesand Bay described as being located? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-563587c2 | On the occasion of their outing described in the narrative, to which destination did the carriage ultimately travel? | 0.333333 | 0.333333 | False | medium |
| graphrag-novel-Novel-6aaabde4 | Within the story's depiction of the Old Inn at Mullion, who is credited with writing a poem about Mary Mundy? | 0.083333 | 0.083333 | False | medium |
| graphrag-novel-Novel-2e9466a9 | According to the journey through coastal villages described in the book, where is the fishing village of Cadgwith located? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-d2746bf8 | During the visit to Mullion, who was mentioned as being considered the best ghost-layer in England? | 0.0 | 0.0 | False | high |
