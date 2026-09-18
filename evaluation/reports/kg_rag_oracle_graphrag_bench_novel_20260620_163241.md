# KG-RAG Oracle Graph Evaluation

- Benchmark: GraphRAG-Bench Novel evidence_triple oracle graph
- Score: **7.5 / 100**
- Questions: 200
- Multi-triple questions: 98
- Graph edges: 428
- Graph quality gate: `fail`
- Graph DB: `D:\虚拟C盘\RAG\outputs\kg_rag_oracle_eval\graphrag_bench_novel_oracle.sqlite`

## Metrics

| Metric | Value |
| --- | ---: |
| evaluated_questions | 200 |
| multi_triple_questions | 98 |
| graph_edge_count | 428 |
| parse_failure_count | 0 |
| triple_hit_rate | 0.044393 |
| question_any_triple_hit_rate | 0.085 |
| complete_path_rate | 0.055 |
| entity_recall | 0.158879 |
| relation_recall | 0.074766 |

## Worst Examples

| ID | Expected | Hit | Complete | Question |
| --- | ---: | ---: | --- | --- |
| Novel-73586ddc | 1 | 0 | False | In the narrative of 'An Unsentimental Journey through Cornwall', which plant known scientifically as Erica vagans is also referred to by ano |
| Novel-74440a6a | 1 | 0 | False | Within the account of the royal visit to St. Michael's Mount in Cornwall, who is identified as the person who married Princess Frederica of  |
| Novel-f80cbf85 | 1 | 0 | False | According to the narrative's discussion of historic sites, in which region of France is Mont St. Michel located? |
| Novel-b3c430ef | 1 | 0 | False | In the historical account relating to St. Michael's Mount, which individual is said to have caused himself to be bled to death there? |
| Novel-304b0354 | 1 | 0 | False | Within the Cornish legends described in the narrative, who was the figure doomed to empty Dozmare Pool as a punishment? |
| Novel-b1a95144 | 1 | 0 | False | In reference to the royal visit to St. Michael's Mount described in the narrative, to which princess did the Queen show motherly kindness du |
| Novel-e05d0922 | 1 | 0 | False | According to the description of Kynance Cove in Cornwall, which specific feature is included as a part of Kynance Cove? |
| Novel-dba48e64 | 3 | 0 | False | In the account of the travelers' visit to Kynance Cove, what natural landmarks are mentioned as being located near or within Kynance Cove, s |
| Novel-ea3d4859 | 1 | 0 | False | During the travelers' exploration of the Cornish coastline in the narrative, what notable geographical feature is located near Housel Cove? |
| Novel-ba894e2c | 1 | 0 | False | In the retelling of the Arthurian legend within the novel, who is the character credited with producing King Arthur? |

## Limitations

- This uses benchmark-provided evidence_triple as an oracle graph, so it tests graph retrieval/path routing, not automatic KG extraction quality.
- It uses SQLiteGraphRetriever lexical entity matching and PPR-style two-hop traversal; no LLM answer generation is included.
- A second run with automatically extracted triples is required to measure real end-to-end GraphRAG construction quality.
