# RAG Evaluation Report

- Run: `external_ragbench-hotpotqa-validation`
- Gate status: `pass`
- Total questions: 50

## Metrics

| Metric | Value |
| --- | ---: |
| retrieval.evaluated_questions | 50 |
| retrieval.question_recall_at_k | 1.0 |
| retrieval.keyword_recall_at_k | 0.728333 |
| retrieval.average_keyword_coverage | 0.728333 |
| retrieval.passage_id_recall_at_k | None |
| retrieval.passage_id_expected_count | 0 |
| retrieval.passage_id_hit_count | 0 |
| retrieval.gold_id_recall_at_k | 0.962264 |
| retrieval.gold_id_expected_count | 159 |
| retrieval.gold_id_hit_count | 153 |
| retrieval.full_evidence_coverage_rate | 0.16 |
| retrieval.no_result_rate | 0.0 |
| retrieval.average_retrieved_count_at_k | 9.92 |
| evidence.expected_keyword_total | 600 |
| evidence.retrieved_keyword_hit_total | 437 |
| evidence.evidence_keyword_hit_rate | 0.728333 |
| evidence.question_with_any_evidence_rate | 1.0 |
| evidence.question_with_full_evidence_rate | 0.16 |
| citation.evaluated_questions | 50 |
| citation.citation_present_rate | 1.0 |
| citation.missing_citation_rate | 0.0 |
| citation.citation_keyword_hit_rate | 0.728333 |
| citation.average_citation_keyword_coverage | 0.728333 |
| answer.evaluated_questions | 50 |
| answer.answer_contains_evidence_rate | 1.0 |
| answer.answer_completeness_avg | 0.728333 |
| answer.complete_answer_rate | 0.16 |
| hallucination_risk.low_count | 37 |
| hallucination_risk.medium_count | 13 |
| hallucination_risk.high_count | 0 |
| hallucination_risk.not_applicable_count | 0 |
| hallucination_risk.high_risk_rate | 0.0 |
| hallucination_risk.medium_or_high_risk_rate | 0.26 |

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
| ragbench-hotpotqa-validation-5a8d7b1755429941ae14dfc6 | What is the 2010 population of the city 2.1 miles southwest of Marietta Air Force Station? | 0.583333 | False | medium |
| ragbench-hotpotqa-validation-5a7e6df35542997cc2c47544 | What was the other name of the textile mill on which The Mill was based on? | 0.583333 | False | medium |
| ragbench-hotpotqa-validation-5ab930655542991b5579f12a | Are both Dziga Vertov and Roger Donaldson are involved in the film industry? | 0.583333 | False | medium |
| ragbench-hotpotqa-validation-5ac3def75542997ea680c95f | Where was the Danger Mouse produced U2 album exclusively released? | 0.416667 | False | medium |
| ragbench-hotpotqa-validation-5a7a5ea15542994f819ef1c7 | Who born earlier, Lewis Terman or  G. Stanley Hall? | 0.583333 | False | medium |
| ragbench-hotpotqa-validation-5a78dc4d55429970f5fffdb6 | Which band has more members, Muzzle or Primus? | 0.333333 | False | medium |
| ragbench-hotpotqa-validation-5addffff5542992200553bdd | How many Academy Awards did the film, in which Jimmy Bryant provided the singing voice for the character Tony, win ? | 0.5 | False | medium |
| ragbench-hotpotqa-validation-5ae2cda55542992decbdcdb7 | What "God Gave Me You" artist wrote the song "Imagine That" for Diamond Rio? | 0.583333 | False | medium |
| ragbench-hotpotqa-validation-5ab64cfa55429953192ad2b7 | Who lived longer Ellen Glasgow or N. Scott Momaday ? | 0.416667 | False | medium |
| ragbench-hotpotqa-validation-5a8d50fb55429941ae14dfa2 | The Bodie & Benton Railway was a narrow gauge common carrier railroad in California, from the Mono Mills to a terminus in a ghost town located how many miles away from Lake Tahoe ? | 0.416667 | False | medium |
| ragbench-hotpotqa-validation-5ae547f85542990ba0bbb254 | Who was the original recording artist of the song which was chosen over If You've Got Trouble for the Beatles' "Help!" film? | 0.416667 | False | medium |

## Results

| ID | Question | Retrieval Coverage | Answer Coverage | Missing Citation | Risk |
| --- | --- | ---: | ---: | --- | --- |
| ragbench-hotpotqa-validation-5ab3bd7d55429969a97a819f | Which team featured in both the 2012 and 2011 Cops del Rey Finals ? | 0.5 | 0.5 | False | medium |
| ragbench-hotpotqa-validation-5ae1fd995542997283cd2313 | Is It Just Me? was a single by the English rock band from what Suffolk city? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5a79d2fe5542994f819ef0c3 | Who was born first, Aleksandr Ivanovsky or Arthur Lubin? | 0.5 | 0.5 | False | medium |
| ragbench-hotpotqa-validation-5a72814f5542994cef4bc2eb | The American Astronomical Society presents an award named after what New Zealand astronomer? | 0.666667 | 0.666667 | False | low |
| ragbench-hotpotqa-validation-5a8d7b1755429941ae14dfc6 | What is the 2010 population of the city 2.1 miles southwest of Marietta Air Force Station? | 0.583333 | 0.583333 | False | medium |
| ragbench-hotpotqa-validation-5a74547755429979e2882900 | the head football coach at the University of Houston from 2007 to 2011, is the current team coach of which football team ? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5a8205b755429926c1cdadee | The Wright Model B was an early pusher biplane designed by what inventors and aviation pioneers who are credited with building the world's first successful airplane? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5a7e6df35542997cc2c47544 | What was the other name of the textile mill on which The Mill was based on? | 0.583333 | 0.583333 | False | medium |
| ragbench-hotpotqa-validation-5a721bbc55429971e9dc9279 | Which Grammy Nominated album was created by a band whose members include John Bowman? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5ab930655542991b5579f12a | Are both Dziga Vertov and Roger Donaldson are involved in the film industry? | 0.583333 | 0.583333 | False | medium |
| ragbench-hotpotqa-validation-5ae3c1515542992f92d8236a | Which magazine was founded first Science News or High Times ? | 0.916667 | 0.916667 | False | low |
| ragbench-hotpotqa-validation-5ac3def75542997ea680c95f | Where was the Danger Mouse produced U2 album exclusively released? | 0.416667 | 0.416667 | False | medium |
| ragbench-hotpotqa-validation-5ab47d765542991751b4d78f | Who designed the hotel that held the IFBB professional bodybuilding competition in September 1991? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5a809b575542996402f6a59c | What former nose tackle announced ESPN College Football Friday Primetime in 2017? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5a7a0a2d5542990783324e06 | The Dressing Point massacre occurred 2 years after which important document was passed in Mexican Texas? | 0.666667 | 0.666667 | False | low |
| ragbench-hotpotqa-validation-5a7a5ea15542994f819ef1c7 | Who born earlier, Lewis Terman or  G. Stanley Hall? | 0.583333 | 0.583333 | False | medium |
| ragbench-hotpotqa-validation-5a78dc4d55429970f5fffdb6 | Which band has more members, Muzzle or Primus? | 0.333333 | 0.333333 | False | medium |
| ragbench-hotpotqa-validation-5a8f9cdb554299458435d69c | which persons private jet called Trump Force One which is built by Boeing Commercial Airplanes and is the manufacturer's largest single aisle passenger aircraft that is produced from 1981 to 2004? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5a78a7025542990784727710 | Who is older, Anne Noe or Jean-Marie Pfaff? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5aba926f55429901930fa83e | Which Formula One World Champion had a teammate named Richie Ginther? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5ae40b2b55429970de88d8b3 | In between  Polytechnic University of the Philippines and California Polytechnic State University which was founded as a vocational high school? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5abffc0d5542990832d3a1e2 | What instrument of war was only used by the President of the United States who was born in Lamar, Missouri? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5ae2952a5542994d89d5b42b | What is the birth date of the person Richard Callaghan coached to Olympic, World, and national titles? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5a7fa48c5542994857a7679a | In addition to Syosset Central, Half Hollow Hills Central, and the school district that has Henry L. Grishman as its superintendent, what other school district is near Hauppauge Union Free School District? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5addffff5542992200553bdd | How many Academy Awards did the film, in which Jimmy Bryant provided the singing voice for the character Tony, win ? | 0.5 | 0.5 | False | medium |
| ragbench-hotpotqa-validation-5ae2cda55542992decbdcdb7 | What "God Gave Me You" artist wrote the song "Imagine That" for Diamond Rio? | 0.583333 | 0.583333 | False | medium |
| ragbench-hotpotqa-validation-5ae2c8b05542992decbdcd9d | What is the birthplace of YouTube's 2016 overview featured creator Wengie? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5ab5ec0a5542997d4ad1f250 | Approximately how many locations is BJ's Wholesale Club operating in, as of early 2008? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5ae7cb575542997ec27276ea | Shinola LLC, an American luxury lifestyle band is owned and operated by Bedrock Brands a texas investment group launched by this man one of the founders of  Fossil Group | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5ab64cfa55429953192ad2b7 | Who lived longer Ellen Glasgow or N. Scott Momaday ? | 0.416667 | 0.416667 | False | medium |
| ragbench-hotpotqa-validation-5ac55ea55542993e66e82377 | Pacific Mozart Ensemble performed which German composer's Der Lindberghflug in 2002? | 0.666667 | 0.666667 | False | low |
| ragbench-hotpotqa-validation-5adbe1c5554299438c868cc4 | Was 9/11: Press for Truth released prior to Chasing Coral? | 0.666667 | 0.666667 | False | low |
| ragbench-hotpotqa-validation-5ae763aa5542995703ce8c09 | Who voices Chef Mung Daal in the American animated television series created by C. H. Greenblatt? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5ab9fe1255429939ce03dc40 | What position did the current Leader of Fine Gael hold from 2016 until 2017? | 0.666667 | 0.666667 | False | low |
| ragbench-hotpotqa-validation-5adea19a55429939a52fe919 | The infantry rifle regiment of the British Army that Talaiasi Labalaba served in was first created in what year? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5a7b47765542992d025e67d8 | What sport do The Basham Brothers and Doug Basham have in common? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5ae5ff845542996de7b71ad0 | An actress in Strange Fruit was better known for a role in CBS sitcom.  Which sitcom is this actress better known for than her role in Strange Fruit? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5adcf3e35542994ed6169c3a | Dean Mills Reservoir is on the slopes of the hill located in what town? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5a8d6d4e554299441c6b9fdb | Lost Kingdom Adventure is a dark ride located at four Legoland theme parks, including which park, which is the original Legoland park, that was opened on June 7th, 1968? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5a8d50fb55429941ae14dfa2 | The Bodie & Benton Railway was a narrow gauge common carrier railroad in California, from the Mono Mills to a terminus in a ghost town located how many miles away from Lake Tahoe ? | 0.416667 | 0.416667 | False | medium |
| ragbench-hotpotqa-validation-5a81ad9855429903bc27b9a3 | When did the 2005 Ladbrokes.com World Darts Championship begin? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5ae547f85542990ba0bbb254 | Who was the original recording artist of the song which was chosen over If You've Got Trouble for the Beatles' "Help!" film? | 0.416667 | 0.416667 | False | medium |
| ragbench-hotpotqa-validation-5a89cc99554299669944a5ae | Wiener Werkstätte Style was part of the movement that took place during what eras? | 0.666667 | 0.666667 | False | low |
| ragbench-hotpotqa-validation-5a809fe75542996402f6a5ba | The Phillips Berlina is a neo-classic car that used stretched underpinings from a car that set a new sales record for what model year? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5a7f0c4b5542993067513600 | WHICH GROUP OF PEOPLE NICKNAMED THE US ARMYS REGIMENT "BUFFALO SOLDIERS" IN WHICH THOMAS SHAW WON THE MEDAL OF HONOR DURING THE INDIAN WARS? | 0.833333 | 0.833333 | False | low |
| ragbench-hotpotqa-validation-5ae150ab55429901ffe4ae53 | How many seats does the jet airliner with which Boeing 777X was intended to compete have? | 0.75 | 0.75 | False | low |
| ragbench-hotpotqa-validation-5ae682c45542995703ce8b6f | Which Record Company reissued an Avenged Sevenfold Album that only sold 300 copies? | 0.666667 | 0.666667 | False | low |
| ragbench-hotpotqa-validation-5ab1c2bf5542997061209558 | Robin Pingeton replaced Cindy Stein as head coach of which university women's basketball team? | 0.666667 | 0.666667 | False | low |
| ragbench-hotpotqa-validation-5a80abb65542996402f6a5df | What organization affiliated with the National Collegiate Athletic Association Division were the 2012 Hawaii Warriors football team first year members of? | 1.0 | 1.0 | False | low |
| ragbench-hotpotqa-validation-5a90492655429933b8a204d8 | Garth Richardson is the son of the producer who worked for which group that evolved from The Iveys? | 0.833333 | 0.833333 | False | low |
