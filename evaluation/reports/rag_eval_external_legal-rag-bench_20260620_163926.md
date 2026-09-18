# RAG Evaluation Report

- Run: `external_legal-rag-bench`
- Gate status: `fail`
- Total questions: 10

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 10 |
| retrieval.question_recall_at_k | 0.9 |
| retrieval.keyword_recall_at_k | 0.333333 |
| retrieval.average_keyword_coverage | 0.333333 |
| retrieval.full_evidence_coverage_rate | 0.0 |
| retrieval.no_result_rate | 0.0 |
| retrieval.average_retrieved_count_at_k | 10.0 |
| evidence.expected_keyword_total | 120 |
| evidence.retrieved_keyword_hit_total | 40 |
| evidence.evidence_keyword_hit_rate | 0.333333 |
| evidence.question_with_any_evidence_rate | 0.9 |
| evidence.question_with_full_evidence_rate | 0.0 |
| citation.evaluated_questions | 10 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.333333 |
| citation.average_citation_keyword_coverage | 0.333333 |
| answer.evaluated_questions | 10 |
| answer.answer_contains_evidence_rate | 0.9 |
| answer.answer_completeness_avg | 0.333333 |
| answer.complete_answer_rate | 0.0 |
| hallucination_risk.low_count | 1 |
| hallucination_risk.medium_count | 8 |
| hallucination_risk.high_count | 1 |
| hallucination_risk.not_applicable_count | 0 |
| hallucination_risk.high_risk_rate | 0.1 |
| hallucination_risk.medium_or_high_risk_rate | 0.9 |

## Gate Failures

| Metric | Actual | Rule | Threshold |
| --- | ---: | --- | ---: |
| retrieval.keyword_recall_at_k | 0.333333 | >= | 0.6 |
| answer.answer_completeness_avg | 0.333333 | >= | 0.6 |
| hallucination_risk.medium_or_high_risk_rate | 0.9 | <= | 0.5 |

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
| legal-1 | Bob and Ted are close friends. Ted is on trial for drug offences, and Bob has been selected as a juror in Ted’s case. Is the judge required to excuse Bob from serving on the jury? | 0.416667 | False | medium |
| legal-2 | Harry is serving as a juror in a burglary trial. He is also a professional locksmith. During the proceedings, Harry is shown a lock which, in his expert view, is too damaged to have been lockpicked in the manner described in court. Why might Harry's expert knowledge of lockpicking be irrelevant when assessing the physical evidence? | 0.166667 | False | medium |
| legal-3 | Isaac is on trial for statutory murder of an emergency worker. You are his barrister. Should you notify the jury that, according to the Crimes Act 1958, the standard sentence for this offence is 30 years imprisonment? | 0.25 | False | medium |
| legal-4 | Should jurors be excused if they have encountered news stories about the accused prior to the trial commencing? | 0.0 | False | high |
| legal-5 | Frank and Joe are jurors in an arson trial. Over the weekend, Joe finds photos of the accused holding a petrol canister and texts them to Frank. Having received this new information, what should Frank do? | 0.25 | False | medium |
| legal-6 | Does the standard of proof of “beyond reasonable doubt” imply that the jury must be fully convinced of every claim the prosecution has made? | 0.5 | False | medium |
| legal-7 | Sally is accused of cultivating narcotic plants in her backyard. One of the elements of this charge is that “the accused intentionally cultivated or attempted to cultivate a particular substance.” To establish whether this is the case, the judge believes it would be valuable to visit Sally’s backyard and have the jury examine it for themselves. What is the name of the legal procedure whereby the court travels to a location relevant to the charge? | 0.25 | False | medium |
| legal-8 | Josh is 21 years old. He witnessed a murder that was clearly perpetrated by the accused. The prosecution, however, needs to determine whether the accused committed the acts voluntarily, thus satisfying the elements of intentional or reckless murder. In court, the judge plays a recording of Josh giving his eyewitness testimony. What is this evidentiary process called? | 0.25 | False | medium |
| legal-9 | Olivia illegally bought cannabis from a tobacconist. As she left, she saw a man firebomb the store. She is now a witness in the arson trial. What legal privilege should she consider when giving her evidence? | 0.583333 | False | medium |

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| legal-1 | Bob and Ted are close friends. Ted is on trial for drug offences, and Bob has been selected as a juror in Ted’s case. Is the judge required to excuse Bob from serving on the jury? | 0.416667 | 0.416667 | False | medium |
| legal-2 | Harry is serving as a juror in a burglary trial. He is also a professional locksmith. During the proceedings, Harry is shown a lock which, in his expert view, is too damaged to have been lockpicked in the manner described in court. Why might Harry's expert knowledge of lockpicking be irrelevant when assessing the physical evidence? | 0.166667 | 0.166667 | False | medium |
| legal-3 | Isaac is on trial for statutory murder of an emergency worker. You are his barrister. Should you notify the jury that, according to the Crimes Act 1958, the standard sentence for this offence is 30 years imprisonment? | 0.25 | 0.25 | False | medium |
| legal-4 | Should jurors be excused if they have encountered news stories about the accused prior to the trial commencing? | 0.0 | 0.0 | False | high |
| legal-5 | Frank and Joe are jurors in an arson trial. Over the weekend, Joe finds photos of the accused holding a petrol canister and texts them to Frank. Having received this new information, what should Frank do? | 0.25 | 0.25 | False | medium |
| legal-6 | Does the standard of proof of “beyond reasonable doubt” imply that the jury must be fully convinced of every claim the prosecution has made? | 0.5 | 0.5 | False | medium |
| legal-7 | Sally is accused of cultivating narcotic plants in her backyard. One of the elements of this charge is that “the accused intentionally cultivated or attempted to cultivate a particular substance.” To establish whether this is the case, the judge believes it would be valuable to visit Sally’s backyard and have the jury examine it for themselves. What is the name of the legal procedure whereby the court travels to a location relevant to the charge? | 0.25 | 0.25 | False | medium |
| legal-8 | Josh is 21 years old. He witnessed a murder that was clearly perpetrated by the accused. The prosecution, however, needs to determine whether the accused committed the acts voluntarily, thus satisfying the elements of intentional or reckless murder. In court, the judge plays a recording of Josh giving his eyewitness testimony. What is this evidentiary process called? | 0.25 | 0.25 | False | medium |
| legal-9 | Olivia illegally bought cannabis from a tobacconist. As she left, she saw a man firebomb the store. She is now a witness in the arson trial. What legal privilege should she consider when giving her evidence? | 0.583333 | 0.583333 | False | medium |
| legal-10 | Emma is found in possession of someone else’s phone but has no documentation of how she obtained it. Emma’s counsel argues that possession of the phone is circumstantial evidence and thus completely inadmissible to establish guilt. Is Emma’s counsel correct? | 0.666667 | 0.666667 | False | low |
