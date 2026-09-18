# RAG Evaluation Report

- Run: `external_ragbench-hotpotqa-validation`
- Gate status: `fail`
- Total questions: 25

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 25 |
| retrieval.question_recall_at_k | 0.8 |
| retrieval.keyword_recall_at_k | 0.67 |
| retrieval.average_keyword_coverage | 0.67 |
| retrieval.full_evidence_coverage_rate | 0.24 |
| retrieval.no_result_rate | 0.2 |
| retrieval.average_retrieved_count_at_k | 4.0 |
| evidence.expected_keyword_total | 300 |
| evidence.retrieved_keyword_hit_total | 201 |
| evidence.evidence_keyword_hit_rate | 0.67 |
| evidence.question_with_any_evidence_rate | 0.8 |
| evidence.question_with_full_evidence_rate | 0.24 |
| citation.evaluated_questions | 20 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.8375 |
| citation.average_citation_keyword_coverage | 0.8375 |
| answer.evaluated_questions | 20 |
| answer.answer_contains_evidence_rate | 1.0 |
| answer.answer_completeness_avg | 0.8375 |
| answer.complete_answer_rate | 0.3 |
| hallucination_risk.low_count | 18 |
| hallucination_risk.medium_count | 2 |
| hallucination_risk.high_count | 0 |
| hallucination_risk.not_applicable_count | 5 |
| hallucination_risk.high_risk_rate | 0.0 |
| hallucination_risk.medium_or_high_risk_rate | 0.1 |

## Gate Failures

| Metric | Actual | Rule | Threshold |
| --- | ---: | --- | ---: |
| retrieval.no_result_rate | 0.2 | <= | 0.05 |

## Retrieval Default Policy

| Setting | Recommendation |
| --- | --- |
| hybrid_rrf | True |
| metadata_filters | explicit_and_auto_source_filters |
| graph_retriever | enable_when_graph_db_path_and_graph_quality_pass |
| query_rewrite | keep_optional |
| reranker | none |
| no_answer_gate | enable_with_calibrated_threshold |
| no_answer_min_results | 1 |

Triggered by metrics: `retrieval.no_result_rate`.

## Failure Cases

| ID | Question | Retrieval Coverage | Missing Citation | Risk |
| --- | --- | ---: | --- | --- |
| ragbench-hotpotqa-validation-5ab3bd7d55429969a97a819f | Which team featured in both the 2012 and 2011 Cops del Rey Finals ? | 0.0 | False | not_applicable |
| ragbench-hotpotqa-validation-5a8d7b1755429941ae14dfc6 | What is the 2010 population of the city 2.1 miles southwest of Marietta Air Force Station? | 0.0 | False | not_applicable |
| ragbench-hotpotqa-validation-5a74547755429979e2882900 | the head football coach at the University of Houston from 2007 to 2011, is the current team coach of which football team ? | 0.0 | False | not_applicable |
| ragbench-hotpotqa-validation-5a809b575542996402f6a59c | What former nose tackle announced ESPN College Football Friday Primetime in 2017? | 0.0 | False | not_applicable |
| ragbench-hotpotqa-validation-5a78dc4d55429970f5fffdb6 | Which band has more members, Muzzle or Primus? | 0.416667 | False | medium |
| ragbench-hotpotqa-validation-5a8f9cdb554299458435d69c | which persons private jet called Trump Force One which is built by Boeing Commercial Airplanes and is the manufacturer's largest single aisle passenger aircraft that is produced from 1981 to 2004? | 0.0 | False | not_applicable |
| ragbench-hotpotqa-validation-5addffff5542992200553bdd | How many Academy Awards did the film, in which Jimmy Bryant provided the singing voice for the character Tony, win ? | 0.5 | False | medium |

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| ragbench-hotpotqa-validation-5ab3bd7d55429969a97a819f | Which team featured in both the 2012 and 2011 Cops del Rey Finals ? | 0.0 | None | False | not_applicable |
| ragbench-hotpotqa-validation-5ae1fd995542997283cd2313 | Is It Just Me? was a single by the English rock band from what Suffolk city? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5a79d2fe5542994f819ef0c3 | Who was born first, Aleksandr Ivanovsky or Arthur Lubin? | 0.666667 | 0.666667 | False | low |
| ragbench-hotpotqa-validation-5a72814f5542994cef4bc2eb | The American Astronomical Society presents an award named after what New Zealand astronomer? | 0.916667 | 0.916667 | False | low |
| ragbench-hotpotqa-validation-5a8d7b1755429941ae14dfc6 | What is the 2010 population of the city 2.1 miles southwest of Marietta Air Force Station? | 0.0 | None | False | not_applicable |
| ragbench-hotpotqa-validation-5a74547755429979e2882900 | the head football coach at the University of Houston from 2007 to 2011, is the current team coach of which football team ? | 0.0 | None | False | not_applicable |
| ragbench-hotpotqa-validation-5a8205b755429926c1cdadee | The Wright Model B was an early pusher biplane designed by what inventors and aviation pioneers who are credited with building the world's first successful airplane? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5a7e6df35542997cc2c47544 | What was the other name of the textile mill on which The Mill was based on? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5a721bbc55429971e9dc9279 | Which Grammy Nominated album was created by a band whose members include John Bowman? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5ab930655542991b5579f12a | Are both Dziga Vertov and Roger Donaldson are involved in the film industry? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5ae3c1515542992f92d8236a | Which magazine was founded first Science News or High Times ? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5ac3def75542997ea680c95f | Where was the Danger Mouse produced U2 album exclusively released? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5ab47d765542991751b4d78f | Who designed the hotel that held the IFBB professional bodybuilding competition in September 1991? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5a809b575542996402f6a59c | What former nose tackle announced ESPN College Football Friday Primetime in 2017? | 0.0 | None | False | not_applicable |
| ragbench-hotpotqa-validation-5a7a0a2d5542990783324e06 | The Dressing Point massacre occurred 2 years after which important document was passed in Mexican Texas? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5a7a5ea15542994f819ef1c7 | Who born earlier, Lewis Terman or  G. Stanley Hall? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5a78dc4d55429970f5fffdb6 | Which band has more members, Muzzle or Primus? | 0.416667 | 0.416667 | False | medium |
| ragbench-hotpotqa-validation-5a8f9cdb554299458435d69c | which persons private jet called Trump Force One which is built by Boeing Commercial Airplanes and is the manufacturer's largest single aisle passenger aircraft that is produced from 1981 to 2004? | 0.0 | None | False | not_applicable |
| ragbench-hotpotqa-validation-5a78a7025542990784727710 | Who is older, Anne Noe or Jean-Marie Pfaff? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5aba926f55429901930fa83e | Which Formula One World Champion had a teammate named Richie Ginther? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5ae40b2b55429970de88d8b3 | In between  Polytechnic University of the Philippines and California Polytechnic State University which was founded as a vocational high school? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5abffc0d5542990832d3a1e2 | What instrument of war was only used by the President of the United States who was born in Lamar, Missouri? | 0.916667 | 0.916667 | False | low |
| ragbench-hotpotqa-validation-5ae2952a5542994d89d5b42b | What is the birth date of the person Richard Callaghan coached to Olympic, World, and national titles? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5a7fa48c5542994857a7679a | In addition to Syosset Central, Half Hollow Hills Central, and the school district that has Henry L. Grishman as its superintendent, what other school district is near Hauppauge Union Free School District? | 0.916667 | 0.916667 | False | low |
| ragbench-hotpotqa-validation-5addffff5542992200553bdd | How many Academy Awards did the film, in which Jimmy Bryant provided the singing voice for the character Tony, win ? | 0.5 | 0.5 | False | medium |
