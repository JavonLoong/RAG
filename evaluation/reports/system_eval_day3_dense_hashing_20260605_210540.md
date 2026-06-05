# System Evaluation Report

- Generated at: 2026-06-05T21:05:40
- Questions: 60
- Top K: 5
- Retrieval only: True
- Matched outputs: 60
- Missing outputs: 0

## Metrics

| Group | Metric | Value |
| --- | --- | --- |
| retrieval | evaluated_questions | 60 |
| retrieval | question_recall_at_k | 0.583333 |
| retrieval | keyword_recall_at_k | 0.281879 |
| retrieval | average_keyword_coverage | 0.299722 |
| retrieval | full_evidence_coverage_rate | 0.116667 |
| retrieval | no_result_rate | 0.000000 |
| retrieval | average_retrieved_count_at_k | 5.000000 |
| evidence | expected_keyword_total | 298 |
| evidence | retrieved_keyword_hit_total | 84 |
| evidence | evidence_keyword_hit_rate | 0.281879 |
| evidence | question_with_any_evidence_rate | 0.583333 |
| evidence | question_with_full_evidence_rate | 0.116667 |
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
| hallucination_risk | not_applicable_count | 60 |
| hallucination_risk | high_risk_rate | - |
| hallucination_risk | medium_or_high_risk_rate | - |

## Task Types

| Task type | Count |
| --- | --- |
| answer_quality | 5 |
| challenge_cup_positioning | 9 |
| comparison | 2 |
| demo_reliability | 1 |
| evaluation_method | 8 |
| fault_reasoning | 2 |
| kg_graph_rag | 11 |
| ocr_risk | 6 |
| standard_rag_fact | 7 |
| standard_rag_process | 6 |
| structured_data_fact | 3 |

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
| se025 | kg_graph_rag | GraphRAG 的局部搜索和全局搜索分别适合什么类型的问题？ | 0.000000 | - | - | not_applicable | 应区分实体子图/多跳和社区摘要/全局总结。 |
| se026 | kg_graph_rag | 社区检测和社区摘要在 GraphRAG 中解决什么问题？ | 1.000000 | - | - | not_applicable | 应说明社区不是前端展示，而是全局搜索的索引和摘要基础。 |
| se027 | structured_data_fact | Goldwind 解码数据质量报告中，解析后的数据规模是多少？ | 0.000000 | - | - | not_applicable | 应准确命中行列规模和 RUNDATA/parsed_data.csv。 |
| se028 | structured_data_fact | Goldwind 解码数据中，哪些列属于非数值列？ | 0.000000 | - | - | not_applicable | 应准确列出四个非数值列，不能只说有日期和版本。 |
| se029 | evaluation_method | 用这个评测集评价 RAG 系统时，context recall 应该关注什么？ | 0.000000 | - | - | not_applicable | 应区分检索覆盖和生成质量。 |
| se030 | evaluation_method | 最后汇报中，为什么要同时展示成功案例和失败案例？ | 0.250000 | - | - | not_applicable | 应体现失败分析的学术价值，不能只说展示失败会显得诚实。 |
| cc031 | challenge_cup_positioning | 为什么动力装备知识库需要同时保留 OCR 质量审计和 RAG 检索评测？ | 0.400000 | - | - | not_applicable | 应能说明 OCR 与检索评测分别解决数据可靠性和系统有效性问题。 |
| cc032 | challenge_cup_positioning | 本项目为什么不能只说自己是一个普通问答页面？ | 0.166667 | - | - | not_applicable | 回答需要突出工程闭环，不应只描述前端问答。 |
| cc033 | kg_graph_rag | GraphRAG 在动力装备资料中适合解决哪一类普通 RAG 不稳定的问题？ | 0.000000 | - | - | not_applicable | 必须说明 GraphRAG 的适用场景，而不是宣称所有问题都优于普通 RAG。 |
| cc034 | kg_graph_rag | 为什么三元组必须绑定 evidence 才能用于可信问答？ | 0.500000 | - | - | not_applicable | 应强调证据绑定是可信性和人工评审的前提。 |
| cc035 | structured_data_fact | 当前知识图谱 POC 的人工评审结果能证明什么，不能证明什么？ | 1.000000 | - | - | not_applicable | 必须同时说清楚能证明和不能过度声称的边界。 |
| cc036 | standard_rag_fact | 为什么 9080 个 chunk 的普通 RAG 库只是起点，不是最终质量证明？ | 0.500000 | - | - | not_applicable | 应区分入库规模证明和质量证明。 |
| cc037 | challenge_cup_positioning | 挑战杯答辩中如何解释本项目的创新点？ | 0.333333 | - | - | not_applicable | 回答不能把创新点简化为使用 LLM。 |
| cc038 | evaluation_method | 为什么项目需要保留失败案例分析？ | 0.000000 | - | - | not_applicable | 应强调失败案例是科研和工程严谨性的证据。 |
| cc039 | fault_reasoning | 动力装备故障诊断类问题为什么需要同时返回可能原因和检查证据？ | 0.333333 | - | - | not_applicable | 回答应保持辅助定位，不应直接下维修决策。 |
| cc040 | fault_reasoning | 燃气轮机运行监测中温度、压力和振动信号为什么常被放在一起分析？ | 0.500000 | - | - | not_applicable | 应体现多参数联合分析的运维价值。 |
| cc041 | kg_graph_rag | 燃烧室相关问题为什么适合用图谱表达部件、现象和影响之间的关系？ | 0.833333 | - | - | not_applicable | 应说明图谱表达多实体关系的优势。 |
| cc042 | challenge_cup_positioning | 为什么挑战杯项目书要把应用价值和技术指标同时写清楚？ | 0.000000 | - | - | not_applicable | 应把评审视角讲清楚。 |
| cc043 | evaluation_method | 如果 GraphRAG 没有在所有题上超过 keyword baseline，应该如何解释？ | 0.166667 | - | - | not_applicable | 必须体现方法适用边界。 |
| cc044 | challenge_cup_positioning | 为什么本项目需要一页式成果总览？ | 0.000000 | - | - | not_applicable | 应解释成果总览的评审沟通价值。 |
| cc045 | challenge_cup_positioning | 如何证明本项目不是只做了资料搬运？ | 0.166667 | - | - | not_applicable | 回答要明确区分资料收集和知识工程。 |
| cc046 | challenge_cup_positioning | 为什么技术白皮书中必须写清楚数据流？ | 0.166667 | - | - | not_applicable | 应体现端到端可复现性。 |
| cc047 | answer_quality | 为什么要在答辩中主动说明系统不替代工程师决策？ | 0.166667 | - | - | not_applicable | 应强调高风险应用边界。 |
| cc048 | kg_graph_rag | GraphRAG global 更适合回答什么类型的问题？ | 0.166667 | - | - | not_applicable | 应明确 global search 的问题类型。 |
| cc049 | evaluation_method | 为什么 source_scope 对评测和检索都重要？ | 0.000000 | - | - | not_applicable | 应同时说明评测和检索两侧价值。 |
| cc050 | evaluation_method | 为什么要记录每个实验的命令和报告路径？ | 0.000000 | - | - | not_applicable | 应体现 reproducibility 的科研价值。 |
| cc051 | demo_reliability | 如果现场后端服务启动失败，演示应该如何继续？ | 0.000000 | - | - | not_applicable | 应强调答辩现场优先保证叙事连续性。 |
| cc052 | answer_quality | 为什么项目材料中要保留不能过度声称的清单？ | 0.000000 | - | - | not_applicable | 应强调学术规范和答辩风险控制。 |
| cc053 | evaluation_method | 为什么 hybrid 检索可能被弱 dense_hashing 稀释？ | 0.000000 | - | - | not_applicable | 应解释 Day4 failure analysis 中 hybrid_dilution 的含义。 |
| cc054 | standard_rag_process | 为什么真实 embedding 和 reranker 是下一阶段质量提升重点？ | 0.333333 | - | - | not_applicable | 应区分可复现 baseline 和质量增强方向。 |
| cc055 | ocr_risk | 为什么 OCR 两栏排版会影响 RAG 入库质量？ | 0.166667 | - | - | not_applicable | 应说明 OCR 版面风险如何传递到 RAG。 |
| cc056 | kg_graph_rag | 为什么知识图谱关系类型不能全部写成 related_to？ | 0.166667 | - | - | not_applicable | 应强调 schema 粒度控制。 |
| cc057 | challenge_cup_positioning | 为什么结项验收清单要把主张映射到证据文件？ | 0.000000 | - | - | not_applicable | 应体现 checklist 的评审组织价值。 |
| cc058 | evaluation_method | 为什么本项目适合用可复现实验而不是只用主观展示来证明效果？ | 0.166667 | - | - | not_applicable | 应说明可复现实验比 demo 更有证明力。 |
| cc059 | answer_quality | 项目冲击特等奖时最应该避免哪三类表述风险？ | 0.000000 | - | - | not_applicable | 回答应列出三类风险并解释原因。 |
| cc060 | challenge_cup_positioning | 第一轮挑战杯升级完成后，项目应该达到什么状态？ | 0.000000 | - | - | not_applicable | 应总结第一轮可交付状态。 |
