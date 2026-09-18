# RAG Evaluation Report

- Run: `external_graphrag-bench-novel`
- Gate status: `fail`
- Total questions: 50

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 50 |
| retrieval.question_recall_at_k | 0.66 |
| retrieval.keyword_recall_at_k | 0.244505 |
| retrieval.average_keyword_coverage | 0.221436 |
| retrieval.full_evidence_coverage_rate | 0.02 |
| retrieval.no_result_rate | 0.02 |
| retrieval.average_retrieved_count_at_k | 9.8 |
| evidence.expected_keyword_total | 364 |
| evidence.retrieved_keyword_hit_total | 89 |
| evidence.evidence_keyword_hit_rate | 0.244505 |
| evidence.question_with_any_evidence_rate | 0.66 |
| evidence.question_with_full_evidence_rate | 0.02 |
| citation.evaluated_questions | 49 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.25 |
| citation.average_citation_keyword_coverage | 0.225956 |
| answer.evaluated_questions | 49 |
| answer.answer_contains_evidence_rate | 0.673469 |
| answer.answer_completeness_avg | 0.225956 |
| answer.complete_answer_rate | 0.020408 |
| hallucination_risk.low_count | 6 |
| hallucination_risk.medium_count | 27 |
| hallucination_risk.high_count | 16 |
| hallucination_risk.not_applicable_count | 1 |
| hallucination_risk.high_risk_rate | 0.326531 |
| hallucination_risk.medium_or_high_risk_rate | 0.877551 |

## Gate Failures

| Metric | Actual | Rule | Threshold |
| --- | ---: | --- | ---: |
| retrieval.keyword_recall_at_k | 0.244505 | >= | 0.6 |
| answer.answer_completeness_avg | 0.225956 | >= | 0.6 |
| hallucination_risk.medium_or_high_risk_rate | 0.877551 | <= | 0.5 |

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
| graphrag-novel-Novel-f80cbf85 | According to the narrative's discussion of historic sites, in which region of France is Mont St. Michel located? | 0.25 | False | medium |
| graphrag-novel-Novel-b3c430ef | In the historical account relating to St. Michael's Mount, which individual is said to have caused himself to be bled to death there? | 0.083333 | False | medium |
| graphrag-novel-Novel-304b0354 | Within the Cornish legends described in the narrative, who was the figure doomed to empty Dozmare Pool as a punishment? | 0.111111 | False | medium |
| graphrag-novel-Novel-e05d0922 | According to the description of Kynance Cove in Cornwall, which specific feature is included as a part of Kynance Cove? | 0.25 | False | medium |
| graphrag-novel-Novel-ea3d4859 | During the travelers' exploration of the Cornish coastline in the narrative, what notable geographical feature is located near Housel Cove? | 0.111111 | False | medium |
| graphrag-novel-Novel-ba894e2c | In the retelling of the Arthurian legend within the novel, who is the character credited with producing King Arthur? | 0.0 | False | high |
| graphrag-novel-Novel-419cadfe | Within the summary of Arthurian legend provided in the narrative, with whom did King Arthur engage in battle? | 0.285714 | False | medium |
| graphrag-novel-Novel-9e7500a0 | In the context of the Arthurian story as recounted in the narrative, which character fell in love with Ygrayne, leading to significant events in the legend? | 0.125 | False | medium |
| graphrag-novel-Novel-bffd01c2 | In the novel's retelling of the end of King Arthur's story, who was the knight entrusted to throw the sword Excalibur into the mere? | 0.0 | False | not_applicable |
| graphrag-novel-Novel-ef451592 | Aside from Penolver, what other prominent feature is described as being near Housel Cove in the narrative? | 0.222222 | False | medium |
| graphrag-novel-Novel-eab59fae | According to the journey described in the narrative, in which county of England is the town of Marazion located? | 0.0 | False | high |
| graphrag-novel-Novel-61cf41ee | During the journey through Cornwall, who is identified as the driver responsible for transporting the main party by carriage? | 0.0 | False | high |
| graphrag-novel-Novel-09d21113 | In the account of the road journey after passing through Penzance, to which location did Charles travel with the carriage? | 0.5 | False | medium |
| graphrag-novel-Novel-1b7a0e02 | During the first evening at The Lizard, what did Charles call out excitedly upon seeing the lights, as described in the narrative? | 0.0 | False | high |
| graphrag-novel-Novel-752ca0c2 | In the context of the story's visit to Mullion, which individual did Mary Mundy express her admiration for? | 0.0 | False | high |
| graphrag-novel-Novel-4ae5ec38 | Within the travel narrative, in which English county is Whitesand Bay described as being located? | 0.0 | False | high |
| graphrag-novel-Novel-563587c2 | On the occasion of their outing described in the narrative, to which destination did the carriage ultimately travel? | 0.333333 | False | medium |
| graphrag-novel-Novel-6aaabde4 | Within the story's depiction of the Old Inn at Mullion, who is credited with writing a poem about Mary Mundy? | 0.083333 | False | medium |
| graphrag-novel-Novel-2e9466a9 | According to the journey through coastal villages described in the book, where is the fishing village of Cadgwith located? | 0.0 | False | high |
| graphrag-novel-Novel-d2746bf8 | During the visit to Mullion, who was mentioned as being considered the best ghost-layer in England? | 0.142857 | False | medium |
| graphrag-novel-Novel-75f181e8 | During the travelers' excursions from The Lizard, to which beach did Charles offer to drive the party for sightseeing and bathing? | 0.0 | False | high |
| graphrag-novel-Novel-de0767ce | In the narrative's account of tea at the Old Inn, what specialty did Mary Mundy prepare for her guests? | 0.1 | False | medium |
| graphrag-novel-Novel-d5c10dcf | In the context of the Cornish journey, where is The Lizard, the southernmost point described in the narrative, located? | 0.0 | False | high |
| graphrag-novel-Novel-85c57bc9 | In which Cornish village did Thomas Flavel serve as a reverend gentleman, as mentioned during the visit to the old church? | 0.428571 | False | medium |
| graphrag-novel-Novel-4196794d | During the boating excursion described in the narrative, where did the young members of the party go after leaving the shore? | 0.166667 | False | medium |
| graphrag-novel-Novel-51e5f06f | After the sea-cave excursion near Church Cove, at what location was Charles waiting for the travelers' return? | 0.2 | False | medium |
| graphrag-novel-Novel-e1aa3f36 | In the retelling of the Arthurian legend within the narrative, what was the relationship between Merlin and Uther Pendragon regarding counsel or advice? | 0.125 | False | medium |
| graphrag-novel-Novel-83b8a631 | According to the narrative's account of Cornish coastal fauna, to which region is the sand-eel described as being peculiar? | 0.4 | False | medium |
| graphrag-novel-Novel-2c702150 | Within the depiction of religious communities in the narrative, in which English county is the Methodist sect noted as being present? | 0.25 | False | medium |
| graphrag-novel-Novel-5bae1c96 | In the legends recounted in the narrative, who was condemned to the endless task of emptying Dozmare Pool? | 0.0 | False | high |
| graphrag-novel-Novel-a5c06d63 | Within the travelers' account of their route through Cornwall, in which county is Land's End, the furthest western point described in the story, located? | 0.2 | False | medium |
| graphrag-novel-Novel-4de99f79 | According to the Cornish folklore referenced in the narrative, where did the legendary figure Tregeagle have his dwelling? | 0.0 | False | high |
| graphrag-novel-Novel-ebb0af4d | In the journey along the Cornish coastline, what notable location is described as being near Housel Cove? | 0.285714 | False | medium |
| graphrag-novel-Novel-8217a825 | According to the narrative's description of coastal towns, near which location is the town of Falmouth situated? | 0.142857 | False | medium |
| graphrag-novel-Novel-64042235 | During the traveler's route through Cornwall in the story, who is identified as having passed through the town of Penzance? | 0.375 | False | medium |
| graphrag-novel-Novel-b4100b78 | Within the discussion of poetry in the narrative, who is credited with moralising the poem 'Maud'? | 0.0 | False | high |
| graphrag-novel-Novel-d2bac092 | In the geographical descriptions in the story, where is Whitesand Bay stated to be located? | 0.0 | False | high |
| graphrag-novel-Novel-e416a392 | Within the description of regional resources in the narrative, where is slate identified as being found? | 0.333333 | False | medium |
| graphrag-novel-Novel-7d087b64 | From which prominent location was Roughtor visible, as experienced by the travelers during their visit to Cornwall? | 0.0 | False | high |
| graphrag-novel-Novel-1af03c49 | According to the narrative, which coastal destination does Cornwall include among its notable features? | 0.0 | False | high |
| graphrag-novel-Novel-0dd6c56f | In the context of hotel accommodations described in the narrative, where is the Falmouth Hotel located? | 0.333333 | False | medium |
| graphrag-novel-Novel-322bb52d | According to the narrator's reflections in 'An Unsentimental Journey through Cornwall', how is King Arthur associated with the Land of Lyonesse, and what is said about his journey there? | 0.4 | False | medium |

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| graphrag-novel-Novel-73586ddc | In the narrative of 'An Unsentimental Journey through Cornwall', which plant known scientifically as Erica vagans is also referred to by another common name, and what is that name? | 0.166667 | 0.166667 | False | medium |
| graphrag-novel-Novel-74440a6a | Within the account of the royal visit to St. Michael's Mount in Cornwall, who is identified as the person who married Princess Frederica of Hanover? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-f80cbf85 | According to the narrative's discussion of historic sites, in which region of France is Mont St. Michel located? | 0.25 | 0.25 | False | medium |
| graphrag-novel-Novel-b3c430ef | In the historical account relating to St. Michael's Mount, which individual is said to have caused himself to be bled to death there? | 0.083333 | 0.083333 | False | medium |
| graphrag-novel-Novel-304b0354 | Within the Cornish legends described in the narrative, who was the figure doomed to empty Dozmare Pool as a punishment? | 0.111111 | 0.111111 | False | medium |
| graphrag-novel-Novel-b1a95144 | In reference to the royal visit to St. Michael's Mount described in the narrative, to which princess did the Queen show motherly kindness during her stay? | 0.666667 | 0.666667 | False | low |
| graphrag-novel-Novel-e05d0922 | According to the description of Kynance Cove in Cornwall, which specific feature is included as a part of Kynance Cove? | 0.25 | 0.25 | False | medium |
| graphrag-novel-Novel-dba48e64 | In the account of the travelers' visit to Kynance Cove, what natural landmarks are mentioned as being located near or within Kynance Cove, such as Asparagus Island, Gull Rock, and Bellows? | 0.75 | 0.75 | False | low |
| graphrag-novel-Novel-ea3d4859 | During the travelers' exploration of the Cornish coastline in the narrative, what notable geographical feature is located near Housel Cove? | 0.111111 | 0.111111 | False | medium |
| graphrag-novel-Novel-ba894e2c | In the retelling of the Arthurian legend within the novel, who is the character credited with producing King Arthur? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-42f1975a | According to the narrative's summary of Arthurian history, who was proclaimed king after the death of Uther Pendragon? | 0.666667 | 0.666667 | False | low |
| graphrag-novel-Novel-419cadfe | Within the summary of Arthurian legend provided in the narrative, with whom did King Arthur engage in battle? | 0.285714 | 0.285714 | False | medium |
| graphrag-novel-Novel-9e7500a0 | In the context of the Arthurian story as recounted in the narrative, which character fell in love with Ygrayne, leading to significant events in the legend? | 0.125 | 0.125 | False | medium |
| graphrag-novel-Novel-bffd01c2 | In the novel's retelling of the end of King Arthur's story, who was the knight entrusted to throw the sword Excalibur into the mere? | 0.0 | None | False | not_applicable |
| graphrag-novel-Novel-ef451592 | Aside from Penolver, what other prominent feature is described as being near Housel Cove in the narrative? | 0.222222 | 0.222222 | False | medium |
| graphrag-novel-Novel-eab59fae | According to the journey described in the narrative, in which county of England is the town of Marazion located? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-61cf41ee | During the journey through Cornwall, who is identified as the driver responsible for transporting the main party by carriage? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-09d21113 | In the account of the road journey after passing through Penzance, to which location did Charles travel with the carriage? | 0.5 | 0.5 | False | medium |
| graphrag-novel-Novel-1b7a0e02 | During the first evening at The Lizard, what did Charles call out excitedly upon seeing the lights, as described in the narrative? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-752ca0c2 | In the context of the story's visit to Mullion, which individual did Mary Mundy express her admiration for? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-4ae5ec38 | Within the travel narrative, in which English county is Whitesand Bay described as being located? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-563587c2 | On the occasion of their outing described in the narrative, to which destination did the carriage ultimately travel? | 0.333333 | 0.333333 | False | medium |
| graphrag-novel-Novel-6aaabde4 | Within the story's depiction of the Old Inn at Mullion, who is credited with writing a poem about Mary Mundy? | 0.083333 | 0.083333 | False | medium |
| graphrag-novel-Novel-2e9466a9 | According to the journey through coastal villages described in the book, where is the fishing village of Cadgwith located? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-d2746bf8 | During the visit to Mullion, who was mentioned as being considered the best ghost-layer in England? | 0.142857 | 0.142857 | False | medium |
| graphrag-novel-Novel-75f181e8 | During the travelers' excursions from The Lizard, to which beach did Charles offer to drive the party for sightseeing and bathing? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-de0767ce | In the narrative's account of tea at the Old Inn, what specialty did Mary Mundy prepare for her guests? | 0.1 | 0.1 | False | medium |
| graphrag-novel-Novel-d5c10dcf | In the context of the Cornish journey, where is The Lizard, the southernmost point described in the narrative, located? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-85c57bc9 | In which Cornish village did Thomas Flavel serve as a reverend gentleman, as mentioned during the visit to the old church? | 0.428571 | 0.428571 | False | medium |
| graphrag-novel-Novel-4196794d | During the boating excursion described in the narrative, where did the young members of the party go after leaving the shore? | 0.166667 | 0.166667 | False | medium |
| graphrag-novel-Novel-51e5f06f | After the sea-cave excursion near Church Cove, at what location was Charles waiting for the travelers' return? | 0.2 | 0.2 | False | medium |
| graphrag-novel-Novel-e1aa3f36 | In the retelling of the Arthurian legend within the narrative, what was the relationship between Merlin and Uther Pendragon regarding counsel or advice? | 0.125 | 0.125 | False | medium |
| graphrag-novel-Novel-83b8a631 | According to the narrative's account of Cornish coastal fauna, to which region is the sand-eel described as being peculiar? | 0.4 | 0.4 | False | medium |
| graphrag-novel-Novel-2c702150 | Within the depiction of religious communities in the narrative, in which English county is the Methodist sect noted as being present? | 0.25 | 0.25 | False | medium |
| graphrag-novel-Novel-5bae1c96 | In the legends recounted in the narrative, who was condemned to the endless task of emptying Dozmare Pool? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-a5c06d63 | Within the travelers' account of their route through Cornwall, in which county is Land's End, the furthest western point described in the story, located? | 0.2 | 0.2 | False | medium |
| graphrag-novel-Novel-4de99f79 | According to the Cornish folklore referenced in the narrative, where did the legendary figure Tregeagle have his dwelling? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-ebb0af4d | In the journey along the Cornish coastline, what notable location is described as being near Housel Cove? | 0.285714 | 0.285714 | False | medium |
| graphrag-novel-Novel-8217a825 | According to the narrative's description of coastal towns, near which location is the town of Falmouth situated? | 0.142857 | 0.142857 | False | medium |
| graphrag-novel-Novel-64042235 | During the traveler's route through Cornwall in the story, who is identified as having passed through the town of Penzance? | 0.375 | 0.375 | False | medium |
| graphrag-novel-Novel-b4100b78 | Within the discussion of poetry in the narrative, who is credited with moralising the poem 'Maud'? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-d2bac092 | In the geographical descriptions in the story, where is Whitesand Bay stated to be located? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-eae5175c | According to the narrative's overview of the region, what natural feature is described as being part of Cornwall? | 1.0 | 1.0 | False | low |
| graphrag-novel-Novel-e416a392 | Within the description of regional resources in the narrative, where is slate identified as being found? | 0.333333 | 0.333333 | False | medium |
| graphrag-novel-Novel-7d087b64 | From which prominent location was Roughtor visible, as experienced by the travelers during their visit to Cornwall? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-1af03c49 | According to the narrative, which coastal destination does Cornwall include among its notable features? | 0.0 | 0.0 | False | high |
| graphrag-novel-Novel-2d5348fe | In the travelers' exploration of historic sites, where is TINTAGEL, the legendary birthplace of King Arthur, located? | 0.666667 | 0.666667 | False | low |
| graphrag-novel-Novel-0dd6c56f | In the context of hotel accommodations described in the narrative, where is the Falmouth Hotel located? | 0.333333 | 0.333333 | False | medium |
| graphrag-novel-Novel-8ff5dd5a | Within the context of Arthurian legend as discussed by the narrator in 'An Unsentimental Journey through Cornwall', what is the relationship between King Arthur and Sir Launcelot, and how is Sir Launcelot described in relation to King Arthur and the Knights of the Round Table? | 0.916667 | 0.916667 | False | low |
| graphrag-novel-Novel-322bb52d | According to the narrator's reflections in 'An Unsentimental Journey through Cornwall', how is King Arthur associated with the Land of Lyonesse, and what is said about his journey there? | 0.4 | 0.4 | False | medium |
