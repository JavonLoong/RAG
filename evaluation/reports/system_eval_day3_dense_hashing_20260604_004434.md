# System Evaluation Report

- Generated at: 2026-06-04T00:44:34
- Questions: 30
- Top K: 5
- Retrieval only: True
- Matched outputs: 30
- Missing outputs: 0

## Metrics

| Group | Metric | Value |
| --- | --- | --- |
| retrieval | evaluated_questions | 30 |
| retrieval | question_recall_at_k | 0.600000 |
| retrieval | keyword_recall_at_k | 0.425000 |
| retrieval | average_keyword_coverage | 0.425000 |
| retrieval | full_evidence_coverage_rate | 0.233333 |
| retrieval | no_result_rate | 0.000000 |
| retrieval | average_retrieved_count_at_k | 5.000000 |
| evidence | expected_keyword_total | 120 |
| evidence | retrieved_keyword_hit_total | 51 |
| evidence | evidence_keyword_hit_rate | 0.425000 |
| evidence | question_with_any_evidence_rate | 0.600000 |
| evidence | question_with_full_evidence_rate | 0.233333 |
| citation | evaluated_questions | 0 |
| citation | citation_present_rate | - |
| citation | missing_citation_rate | - |
| citation | citation_keyword_hit_rate | - |
| citation | average_citation_keyword_coverage | - |
| answer | evaluated_questions | 0 |
| answer | answer_contains_evidence_rate | - |
| answer | answer_completeness_avg | - |
| answer | complete_answer_rate | - |
| hallucination_risk | low_count | 0 |
| hallucination_risk | medium_count | 0 |
| hallucination_risk | high_count | 0 |
| hallucination_risk | not_applicable_count | 30 |
| hallucination_risk | high_risk_rate | - |
| hallucination_risk | medium_or_high_risk_rate | - |

## Task Types

| Task type | Count |
| --- | --- |
| answer_quality | 2 |
| comparison | 2 |
| evaluation_method | 2 |
| kg_graph_rag | 6 |
| ocr_risk | 5 |
| standard_rag_fact | 6 |
| standard_rag_process | 5 |
| structured_data_fact | 2 |

## Cases

| ID | Type | Question | Retrieval coverage | Answer coverage | Missing citation | Risk | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| se001 | standard_rag_fact | 燃气-蒸汽联合循环为什么通常比单一燃气轮机循环效率更高？ | 0.750000 | - | - | not_applicable | 应检索到联合循环、余热利用、蒸汽轮机或能量梯级利用相关证据，不能只泛泛说效率高。 |
| se002 | standard_rag_fact | 压气机在燃气轮机中的主要作用是什么？ | 1.000000 | - | - | not_applicable | 答案应说明压气机与燃烧室、空气压力/流量之间的关系。 |
| se003 | standard_rag_fact | 燃烧室在燃气轮机热力循环中承担什么功能？ | 0.500000 | - | - | not_applicable | 应覆盖燃料燃烧、压缩空气和高温燃气，避免只写燃烧室是燃烧的地方。 |
| se004 | standard_rag_fact | 涡轮为什么能够输出机械功？ | 0.250000 | - | - | not_applicable | 应命中涡轮膨胀做功和驱动压气机/负载的证据。 |
| se005 | standard_rag_fact | 燃气轮机简单循环通常包括哪几个核心部件？ | 1.000000 | - | - | not_applicable | 应同时找回三个核心部件，漏掉任一核心部件都视为不完整。 |
| se006 | standard_rag_fact | 余热锅炉在联合循环系统中的作用是什么？ | 0.500000 | - | - | not_applicable | 应说明余热锅炉利用排气余热产生蒸汽，并能连接到蒸汽轮机。 |
| se007 | standard_rag_process | 燃气轮机启动过程为什么需要关注转速、燃油和点火条件？ | 0.750000 | - | - | not_applicable | 应覆盖启动、转速、燃油、点火之间的耦合关系。 |
| se008 | standard_rag_process | 为什么燃气轮机运行监测要同时看温度、压力和振动信号？ | 0.000000 | - | - | not_applicable | 应体现多信号联合监测，不能只列传感器名称。 |
| se009 | standard_rag_process | 燃气轮机故障诊断中，为什么需要把现象、原因和处理措施关联起来？ | 0.000000 | - | - | not_applicable | 应检索到故障现象、原因分析、处理措施或维修决策相关证据。 |
| se010 | standard_rag_process | 设备维修报告中，哪些信息最适合作为 RAG 检索的证据片段？ | 0.000000 | - | - | not_applicable | 应说明证据片段应包含事实、原因和处理结果，不应只说全文入库。 |
| se011 | comparison | 向量检索和关键词检索在动力装备资料检索中各自更适合什么问题？ | 0.750000 | - | - | not_applicable | 应明确两种检索方式的适用场景，并指出互补关系。 |
| se012 | comparison | 为什么本项目采用 Hybrid Search 而不是只用 ChromaDB 向量检索？ | 0.250000 | - | - | not_applicable | 应找回混合检索、ChromaDB、BM25/稀疏检索或召回率相关证据。 |
| se013 | standard_rag_process | Reranker 在 RAG 流程中的作用是什么？ | 0.000000 | - | - | not_applicable | 应说明 reranker 是召回后的二次排序环节，不应误解为向量数据库。 |
| se014 | answer_quality | RAG 回答为什么需要 citation 或 evidence 溯源？ | 0.000000 | - | - | not_applicable | 应覆盖引用溯源、人工核验和防幻觉。 |
| se015 | answer_quality | 如果检索结果没有覆盖标准答案中的关键证据，生成模型可能出现什么风险？ | 0.000000 | - | - | not_applicable | 应把检索覆盖不足和生成幻觉风险联系起来。 |
| se016 | ocr_risk | OCR 结果为什么不能直接当作完全准确的精校文本？ | 1.000000 | - | - | not_applicable | 应检索到 OCR 审计中关于可用但非精校、需人工核验的判断。 |
| se017 | ocr_risk | 本项目 OCR 审计中，为什么说表格、公式和图注对知识图谱抽取风险更大？ | 1.000000 | - | - | not_applicable | 应解释这些版面元素与错误关系抽取之间的风险。 |
| se018 | ocr_risk | 为什么 Label Studio JSON 不能整页直接入库到 ChromaDB？ | 0.500000 | - | - | not_applicable | 应命中 JSON 入库前检测报告中的处理建议。 |
| se019 | ocr_risk | 当前公开书籍 JSON 入库前检测报告建议使用哪一个快照，为什么？ | 1.000000 | - | - | not_applicable | 应说明连续快照关系和避免重复入库的原因。 |
| se020 | ocr_risk | Layout-aware OCR 相比普通逐行 OCR，对 RAG 入库有什么价值？ | 0.000000 | - | - | not_applicable | 应说明版面感知与 chunk/清洗/检索质量的关系。 |
| se021 | kg_graph_rag | 知识图谱 POC 中 schema 约束的作用是什么？ | 0.500000 | - | - | not_applicable | 应检索到 schema、实体/关系约束和三元组校验相关证据。 |
| se022 | kg_graph_rag | 知识图谱 POC 为什么要为每条三元组绑定 evidence？ | 0.750000 | - | - | not_applicable | 应说明 evidence 与人工评审、溯源之间的关系。 |
| se023 | kg_graph_rag | 当前 Graph construction POC 已经证明了什么？ | 0.000000 | - | - | not_applicable | 应覆盖 POC 全流程，不能夸大为完整 GraphRAG 问答已经完成。 |
| se024 | kg_graph_rag | 当前知识图谱 POC 的人工评审结果是多少？ | 0.000000 | - | - | not_applicable | 应准确命中数量，不能把 27 条和 26 条混淆。 |
| se025 | kg_graph_rag | GraphRAG 的局部搜索和全局搜索分别适合什么类型的问题？ | 1.000000 | - | - | not_applicable | 应区分实体子图/多跳和社区摘要/全局总结。 |
| se026 | kg_graph_rag | 社区检测和社区摘要在 GraphRAG 中解决什么问题？ | 1.000000 | - | - | not_applicable | 应说明社区不是前端展示，而是全局搜索的索引和摘要基础。 |
| se027 | structured_data_fact | Goldwind 解码数据质量报告中，解析后的数据规模是多少？ | 0.000000 | - | - | not_applicable | 应准确命中行列规模和 RUNDATA/parsed_data.csv。 |
| se028 | structured_data_fact | Goldwind 解码数据中，哪些列属于非数值列？ | 0.000000 | - | - | not_applicable | 应准确列出四个非数值列，不能只说有日期和版本。 |
| se029 | evaluation_method | 用这个评测集评价 RAG 系统时，context recall 应该关注什么？ | 0.000000 | - | - | not_applicable | 应区分检索覆盖和生成质量。 |
| se030 | evaluation_method | 最后汇报中，为什么要同时展示成功案例和失败案例？ | 0.250000 | - | - | not_applicable | 应体现失败分析的学术价值，不能只说展示失败会显得诚实。 |
