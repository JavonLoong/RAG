# RAG Evaluation Report

- Run: `external_legal-rag-bench`
- Gate status: `fail`
- Total questions: 25

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 25 |
| retrieval.question_recall_at_k | 0.72 |
| retrieval.keyword_recall_at_k | 0.193333 |
| retrieval.average_keyword_coverage | 0.193333 |
| retrieval.full_evidence_coverage_rate | 0.0 |
| retrieval.no_result_rate | 0.0 |
| retrieval.average_retrieved_count_at_k | 5.0 |
| evidence.expected_keyword_total | 300 |
| evidence.retrieved_keyword_hit_total | 58 |
| evidence.evidence_keyword_hit_rate | 0.193333 |
| evidence.question_with_any_evidence_rate | 0.72 |
| evidence.question_with_full_evidence_rate | 0.0 |
| citation.evaluated_questions | 25 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.193333 |
| citation.average_citation_keyword_coverage | 0.193333 |
| answer.evaluated_questions | 25 |
| answer.answer_contains_evidence_rate | 0.72 |
| answer.answer_completeness_avg | 0.193333 |
| answer.complete_answer_rate | 0.0 |
| hallucination_risk.low_count | 0 |
| hallucination_risk.medium_count | 18 |
| hallucination_risk.high_count | 7 |
| hallucination_risk.not_applicable_count | 0 |
| hallucination_risk.high_risk_rate | 0.28 |
| hallucination_risk.medium_or_high_risk_rate | 1.0 |

## Gate Failures

| Metric | Actual | Rule | Threshold |
| --- | ---: | --- | ---: |
| retrieval.keyword_recall_at_k | 0.193333 | >= | 0.6 |
| answer.answer_completeness_avg | 0.193333 | >= | 0.6 |
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
| legal-2 | Harry is serving as a juror in a burglary trial. He is also a professional locksmith. During the proceedings, Harry is shown a lock which, in his expert view, is too damaged to have been lockpicked in the manner described in court. Why might Harry's expert knowledge of lockpicking be irrelevant when assessing the physical evidence? | 0.166667 | False | medium |
| legal-3 | Isaac is on trial for statutory murder of an emergency worker. You are his barrister. Should you notify the jury that, according to the Crimes Act 1958, the standard sentence for this offence is 30 years imprisonment? | 0.25 | False | medium |
| legal-4 | Should jurors be excused if they have encountered news stories about the accused prior to the trial commencing? | 0.0 | False | high |
| legal-5 | Frank and Joe are jurors in an arson trial. Over the weekend, Joe finds photos of the accused holding a petrol canister and texts them to Frank. Having received this new information, what should Frank do? | 0.25 | False | medium |
| legal-6 | Does the standard of proof of “beyond reasonable doubt” imply that the jury must be fully convinced of every claim the prosecution has made? | 0.5 | False | medium |
| legal-7 | Sally is accused of cultivating narcotic plants in her backyard. One of the elements of this charge is that “the accused intentionally cultivated or attempted to cultivate a particular substance.” To establish whether this is the case, the judge believes it would be valuable to visit Sally’s backyard and have the jury examine it for themselves. What is the name of the legal procedure whereby the court travels to a location relevant to the charge? | 0.166667 | False | medium |
| legal-8 | Josh is 21 years old. He witnessed a murder that was clearly perpetrated by the accused. The prosecution, however, needs to determine whether the accused committed the acts voluntarily, thus satisfying the elements of intentional or reckless murder. In court, the judge plays a recording of Josh giving his eyewitness testimony. What is this evidentiary process called? | 0.25 | False | medium |
| legal-9 | Olivia illegally bought cannabis from a tobacconist. As she left, she saw a man firebomb the store. She is now a witness in the arson trial. What legal privilege should she consider when giving her evidence? | 0.0 | False | high |
| legal-10 | Emma is found in possession of someone else’s phone but has no documentation of how she obtained it. Emma’s counsel argues that possession of the phone is circumstantial evidence and thus completely inadmissible to establish guilt. Is Emma’s counsel correct? | 0.333333 | False | medium |
| legal-11 | John is on trial for an unnamed offence. John testifies that he could not have committed the offence because he was at an arcade 10 miles away when the offence took place. Earlier, the jury accepted arcade tickets as evidence of John's alibi. John’s counsel now argues that, given this plausible alibi, John could not have committed the crime. What type of reasoning is this an example of? | 0.166667 | False | medium |
| legal-12 | Does Victoria have a law/laws protecting against double jeopardy? | 0.0 | False | high |
| legal-13 | Sophie and Hazel are two of twelve jurors in a trial. Both are uncertain of their verdict, while the remaining ten jurors believe the accused is guilty. The jury is becoming frustrated with Sophie and Hazel's indecision, but the judge instructs the jury to continue deliberating. What is this instruction called? | 0.166667 | False | medium |
| legal-14 | Tim is on trial for aggravated burglary. Before Tim gives evidence, his counsel calls another witness to testify first. Why might this be a bad idea for the defence? | 0.333333 | False | medium |
| legal-15 | Paul is 12 years old. He is a witness in a trial related to a common law riot. You are counsel for the accused. Should you argue that Paul’s is fundamentally untrustworthy because of his age? | 0.166667 | False | medium |
| legal-16 | Can the defence use good character evidence to argue the accused is innocent? | 0.25 | False | medium |
| legal-17 | Can the prosecution freely use bad character evidence to argue the accused is guilty? | 0.25 | False | medium |
| legal-18 | Sam is on trial for murdering her neighbour. The prosecution presents a text from Sam to a friend saying, “I murdered my neighbour today.” What must be established for this text to be treated as an admission? | 0.416667 | False | medium |
| legal-19 | Omar is charged with intentionally causing serious injury. In a recorded interview, he admits being at the scene and pushing the complainant but denies using a weapon or intending serious harm. At trial, the prosecution asks the jury to accept the incriminating parts of the interview but treat his denial of using a weapon as lies. Does this necessarily involve ‘consciousness of guilt’ reasoning? | 0.166667 | False | medium |
| legal-20 | Liam is on trial for arson. His sister gives evidence that, at a family dinner, she said, “The police think you set fire to Dad’s shed. You didn’t do it, did you?” Liam, who had been speaking normally, then went silent and looked down. Can this be used as evidence probative of guilt? | 0.0 | False | high |
| legal-21 | At Zoe’s assault trial, the prosecution argues that her blank, expressionless stare at photos of the injured complainant indicates guilt. Is this argument sound? | 0.0 | False | high |
| legal-22 | The defence raises the issue of mental impairment and bears the onus of proving it. There is a psychiatrist who has examined the accused. Is the prosecution required to call this psychiatrist as a witness? | 0.333333 | False | medium |
| legal-23 | Sarah is tried for armed robbery. She does not give or call any evidence. In closing, the prosecution avoids mentioning her silence directly but repeatedly stresses that “only the prosecution’s account is supported by evidence.” Is this submission by the prosecution permissible? | 0.25 | False | medium |
| legal-24 | In a criminal trial, defence counsel fails to challenge an important part of a prosecution witness’s evidence and later runs a case theory inconsistent with that evidence. The prosecution complains that this has caused unfairness. As the trial judge, how should you decide what to do about it? | 0.0 | False | high |
| legal-25 | In an armed robbery trial, a shop assistant who has served the accused every week for years is shown still images from CCTV and says, “Based on how he looks, that’s the same customer who comes into my store.” What type of identification evidence is this an example of? | 0.416667 | False | medium |

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| legal-1 | Bob and Ted are close friends. Ted is on trial for drug offences, and Bob has been selected as a juror in Ted’s case. Is the judge required to excuse Bob from serving on the jury? | 0.0 | 0.0 | False | high |
| legal-2 | Harry is serving as a juror in a burglary trial. He is also a professional locksmith. During the proceedings, Harry is shown a lock which, in his expert view, is too damaged to have been lockpicked in the manner described in court. Why might Harry's expert knowledge of lockpicking be irrelevant when assessing the physical evidence? | 0.166667 | 0.166667 | False | medium |
| legal-3 | Isaac is on trial for statutory murder of an emergency worker. You are his barrister. Should you notify the jury that, according to the Crimes Act 1958, the standard sentence for this offence is 30 years imprisonment? | 0.25 | 0.25 | False | medium |
| legal-4 | Should jurors be excused if they have encountered news stories about the accused prior to the trial commencing? | 0.0 | 0.0 | False | high |
| legal-5 | Frank and Joe are jurors in an arson trial. Over the weekend, Joe finds photos of the accused holding a petrol canister and texts them to Frank. Having received this new information, what should Frank do? | 0.25 | 0.25 | False | medium |
| legal-6 | Does the standard of proof of “beyond reasonable doubt” imply that the jury must be fully convinced of every claim the prosecution has made? | 0.5 | 0.5 | False | medium |
| legal-7 | Sally is accused of cultivating narcotic plants in her backyard. One of the elements of this charge is that “the accused intentionally cultivated or attempted to cultivate a particular substance.” To establish whether this is the case, the judge believes it would be valuable to visit Sally’s backyard and have the jury examine it for themselves. What is the name of the legal procedure whereby the court travels to a location relevant to the charge? | 0.166667 | 0.166667 | False | medium |
| legal-8 | Josh is 21 years old. He witnessed a murder that was clearly perpetrated by the accused. The prosecution, however, needs to determine whether the accused committed the acts voluntarily, thus satisfying the elements of intentional or reckless murder. In court, the judge plays a recording of Josh giving his eyewitness testimony. What is this evidentiary process called? | 0.25 | 0.25 | False | medium |
| legal-9 | Olivia illegally bought cannabis from a tobacconist. As she left, she saw a man firebomb the store. She is now a witness in the arson trial. What legal privilege should she consider when giving her evidence? | 0.0 | 0.0 | False | high |
| legal-10 | Emma is found in possession of someone else’s phone but has no documentation of how she obtained it. Emma’s counsel argues that possession of the phone is circumstantial evidence and thus completely inadmissible to establish guilt. Is Emma’s counsel correct? | 0.333333 | 0.333333 | False | medium |
| legal-11 | John is on trial for an unnamed offence. John testifies that he could not have committed the offence because he was at an arcade 10 miles away when the offence took place. Earlier, the jury accepted arcade tickets as evidence of John's alibi. John’s counsel now argues that, given this plausible alibi, John could not have committed the crime. What type of reasoning is this an example of? | 0.166667 | 0.166667 | False | medium |
| legal-12 | Does Victoria have a law/laws protecting against double jeopardy? | 0.0 | 0.0 | False | high |
| legal-13 | Sophie and Hazel are two of twelve jurors in a trial. Both are uncertain of their verdict, while the remaining ten jurors believe the accused is guilty. The jury is becoming frustrated with Sophie and Hazel's indecision, but the judge instructs the jury to continue deliberating. What is this instruction called? | 0.166667 | 0.166667 | False | medium |
| legal-14 | Tim is on trial for aggravated burglary. Before Tim gives evidence, his counsel calls another witness to testify first. Why might this be a bad idea for the defence? | 0.333333 | 0.333333 | False | medium |
| legal-15 | Paul is 12 years old. He is a witness in a trial related to a common law riot. You are counsel for the accused. Should you argue that Paul’s is fundamentally untrustworthy because of his age? | 0.166667 | 0.166667 | False | medium |
| legal-16 | Can the defence use good character evidence to argue the accused is innocent? | 0.25 | 0.25 | False | medium |
| legal-17 | Can the prosecution freely use bad character evidence to argue the accused is guilty? | 0.25 | 0.25 | False | medium |
| legal-18 | Sam is on trial for murdering her neighbour. The prosecution presents a text from Sam to a friend saying, “I murdered my neighbour today.” What must be established for this text to be treated as an admission? | 0.416667 | 0.416667 | False | medium |
| legal-19 | Omar is charged with intentionally causing serious injury. In a recorded interview, he admits being at the scene and pushing the complainant but denies using a weapon or intending serious harm. At trial, the prosecution asks the jury to accept the incriminating parts of the interview but treat his denial of using a weapon as lies. Does this necessarily involve ‘consciousness of guilt’ reasoning? | 0.166667 | 0.166667 | False | medium |
| legal-20 | Liam is on trial for arson. His sister gives evidence that, at a family dinner, she said, “The police think you set fire to Dad’s shed. You didn’t do it, did you?” Liam, who had been speaking normally, then went silent and looked down. Can this be used as evidence probative of guilt? | 0.0 | 0.0 | False | high |
| legal-21 | At Zoe’s assault trial, the prosecution argues that her blank, expressionless stare at photos of the injured complainant indicates guilt. Is this argument sound? | 0.0 | 0.0 | False | high |
| legal-22 | The defence raises the issue of mental impairment and bears the onus of proving it. There is a psychiatrist who has examined the accused. Is the prosecution required to call this psychiatrist as a witness? | 0.333333 | 0.333333 | False | medium |
| legal-23 | Sarah is tried for armed robbery. She does not give or call any evidence. In closing, the prosecution avoids mentioning her silence directly but repeatedly stresses that “only the prosecution’s account is supported by evidence.” Is this submission by the prosecution permissible? | 0.25 | 0.25 | False | medium |
| legal-24 | In a criminal trial, defence counsel fails to challenge an important part of a prosecution witness’s evidence and later runs a case theory inconsistent with that evidence. The prosecution complains that this has caused unfairness. As the trial judge, how should you decide what to do about it? | 0.0 | 0.0 | False | high |
| legal-25 | In an armed robbery trial, a shop assistant who has served the accused every week for years is shown still images from CCTV and says, “Based on how he looks, that’s the same customer who comes into my store.” What type of identification evidence is this an example of? | 0.416667 | 0.416667 | False | medium |
