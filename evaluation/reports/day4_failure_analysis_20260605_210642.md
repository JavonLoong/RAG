# Day 4 Failure Case Analysis

- Generated at: 2026-06-05T21:06:42
- Day 3 comparison: `D:\虚拟C盘\RAG\evaluation\reports\day3_retrieval_baseline_comparison_20260605_210540.json`
- Analyzed cases: 40

## Category Counts

| Category | Count |
| --- | ---: |
| corpus_gap_or_query_gap | 1 |
| evaluation_concept_gap | 13 |
| exact_number_fact | 3 |
| hybrid_dilution | 17 |
| partial_ranking_gap | 2 |
| structured_fact_routing | 2 |
| terminology_alias_gap | 2 |

## Method Snapshot

| Method | Question recall@K | Avg keyword coverage | Strong | Weak | Missed |
| --- | ---: | ---: | ---: | ---: | ---: |
| keyword | 0.833333 | 0.563056 | 25 | 25 | 10 |
| dense_hashing | 0.583333 | 0.299722 | 12 | 23 | 25 |
| hybrid_rrf | 0.816667 | 0.519722 | 24 | 25 | 11 |

## Cases

| ID | Type | Coverage keyword/dense/hybrid | Category | Reason | Action |
| --- | --- | --- | --- | --- | --- |
| cc032 | challenge_cup_positioning | 0.333333/0.166667/0.166667 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc033 | kg_graph_rag | 0.666667/0.0/0.5 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc036 | standard_rag_fact | 0.5/0.5/0.666667 | exact_number_fact | 问题要求精确数字事实，但当前 chunk 和排序没有把 POC 数量结论排进 Top-K。 | 为项目成果总览、POC 运行报告建立短 chunk 或事实卡片，专门承载 27/26/1/0 这类汇报数字。 |
| cc037 | challenge_cup_positioning | 0.5/0.333333/0.5 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc038 | evaluation_method | 0.0/0.0/0.0 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| cc042 | challenge_cup_positioning | 0.4/0.0/0.2 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc043 | evaluation_method | 0.0/0.166667/0.166667 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| cc044 | challenge_cup_positioning | 0.333333/0.0/0.166667 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc045 | challenge_cup_positioning | 0.5/0.166667/0.5 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc046 | challenge_cup_positioning | 0.666667/0.166667/0.666667 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc047 | answer_quality | 0.166667/0.166667/0.333333 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| cc048 | kg_graph_rag | 0.5/0.166667/0.333333 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc049 | evaluation_method | 0.666667/0.0/0.333333 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| cc050 | evaluation_method | 0.166667/0.0/0.333333 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| cc051 | demo_reliability | 0.0/0.0/0.0 | corpus_gap_or_query_gap | 三种方法都没有命中预期关键词，可能是语料范围、题目问法或评测关键词与材料表达不一致。 | 回看原文证据，补同义词、补短摘要，或把该题标为需要 GraphRAG/结构化索引的问题。 |
| cc052 | answer_quality | 0.0/0.0/0.0 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| cc053 | evaluation_method | 0.333333/0.0/0.0 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| cc054 | standard_rag_process | 0.5/0.333333/0.5 | terminology_alias_gap | 题目使用 Reranker 英文术语，但材料中更常出现“重排、二次排序、Cross-Encoder”等中文或别名。 | 增加查询改写/同义词扩展：Reranker -> 重排、二次排序、Cross-Encoder、精排。 |
| cc055 | ocr_risk | 0.666667/0.166667/0.666667 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc056 | kg_graph_rag | 0.333333/0.166667/0.166667 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc057 | challenge_cup_positioning | 0.5/0.0/0.333333 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| cc058 | evaluation_method | 0.166667/0.166667/0.5 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| cc059 | answer_quality | 0.0/0.0/0.0 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| cc060 | challenge_cup_positioning | 0.666667/0.0/0.833333 | exact_number_fact | 问题要求精确数字事实，但当前 chunk 和排序没有把 POC 数量结论排进 Top-K。 | 为项目成果总览、POC 运行报告建立短 chunk 或事实卡片，专门承载 27/26/1/0 这类汇报数字。 |
| se003 | standard_rag_fact | 0.5/0.5/0.5 | partial_ranking_gap | 有方法能部分命中，但 Top-K 内证据不完整，主要是排序和 chunk 粒度问题。 | 调小关键报告 chunk、增加 reranker，并做按 source_scope 的候选过滤或加权。 |
| se008 | standard_rag_process | 1.0/0.0/1.0 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| se009 | standard_rag_process | 1.0/0.0/0.25 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| se010 | standard_rag_process | 0.25/0.0/0.0 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| se013 | standard_rag_process | 0.0/0.0/0.75 | terminology_alias_gap | 题目使用 Reranker 英文术语，但材料中更常出现“重排、二次排序、Cross-Encoder”等中文或别名。 | 增加查询改写/同义词扩展：Reranker -> 重排、二次排序、Cross-Encoder、精排。 |
| se014 | answer_quality | 1.0/0.0/1.0 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| se015 | answer_quality | 0.0/0.0/0.0 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| se020 | ocr_risk | 1.0/0.0/0.75 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| se021 | kg_graph_rag | 0.5/0.5/0.5 | partial_ranking_gap | 有方法能部分命中，但 Top-K 内证据不完整，主要是排序和 chunk 粒度问题。 | 调小关键报告 chunk、增加 reranker，并做按 source_scope 的候选过滤或加权。 |
| se023 | kg_graph_rag | 1.0/0.0/0.75 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| se024 | kg_graph_rag | 0.0/0.0/0.0 | exact_number_fact | 问题要求精确数字事实，但当前 chunk 和排序没有把 POC 数量结论排进 Top-K。 | 为项目成果总览、POC 运行报告建立短 chunk 或事实卡片，专门承载 27/26/1/0 这类汇报数字。 |
| se025 | kg_graph_rag | 1.0/0.0/1.0 | hybrid_dilution | 关键词 baseline 更强，Hybrid RRF 被弱 dense_hashing 结果稀释，导致部分强词面证据排名下降。 | 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。 |
| se027 | structured_data_fact | 0.0/0.0/0.0 | structured_fact_routing | 结构化事实没有被专门路由到数据质量报告或字段清单，普通文本 chunk 对精确字段名/数值召回不足。 | 给 Goldwind/SCADA 类问题建立结构化摘要索引，保留 key-value、字段名、行列规模和报告路径。 |
| se028 | structured_data_fact | 0.0/0.0/0.0 | structured_fact_routing | 结构化事实没有被专门路由到数据质量报告或字段清单，普通文本 chunk 对精确字段名/数值召回不足。 | 给 Goldwind/SCADA 类问题建立结构化摘要索引，保留 key-value、字段名、行列规模和报告路径。 |
| se029 | evaluation_method | 0.25/0.0/0.0 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| se030 | evaluation_method | 0.5/0.25/0.5 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |

## Top Hit Diagnostics

### cc032 本项目为什么不能只说自己是一个普通问答页面？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\04_e6a13e82eb6f\document.txt | ocr_text_cleaned | 分。又 AE Ro所以又有 ”由于气体此热是温度的复杂而 十分SHARE AK CEPR )与 “BRRRK”\| CEILAAR TY LA HERRRARK\| Eo ERR Tt KARAM KAMP AK o MAM ASHE: 为: a=efrosa 。 SCO ed CRI ia Fee Colts me CO) Rt re ee ab Pa a ... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\03_8262abdfa4ad\document.txt | ocr_text_cleaned | 角度。 ## Page 125 106炮气江轮发动机燃烧【第3 HE) 大多数早期关于射流混合的研究工作是在加形的管道上进行的，主要是为了模拟单 AE AAC TIL.REE A,ESM J sO AT ERE ait,FE NG TN AR Ae OY ETE,A AO TE A,3h Aa 87§1993 SE LILES EEA ET MAL 4.8... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\10_e461d0cc931e\document.txt | ocr_text_cleaned | 液力变扭器的作用是;保证燃气轮机在开始旋转的瞬间,就能由起动柴 M那么,为什么不能把起动柴油机的输出轴与起动离 eet na em BUA ALA Lt IPA PR A A Me asmasymaeoesmuse RDU,就能发出很大扭矩。因为柴油机所能发出的功率 \|BUH自持转于(或扭矩)与单位时间内吸入到气缸中去的空气量有密 速后,人们才能向它增加喷... |

### cc033 GraphRAG 在动力装备资料中适合解决哪一类普通 RAG 不稳定的问题？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | README.md | project_overview | # Power Equipment RAG Research System 这是围绕"动力装备知识库 / RAG / GraphRAG / 顶刊实验"重新整理后的工程工作区。 当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `fro... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\13_4e83a06514eb\document.txt | ocr_text_cleaned | 5.128 datReKI OTE SCR! 5.6.2.7计及非定常效应的气动设计 提定常是溪通道内流动的本质特征。传统的涡轮设计体系大多基于定常人 南于狐住了流动的主要特征可以设计册较高性能的时轮机械。然而随着先进航 空发动机涡轮部件气动负苘的进一步提高,部件结构越来越紧尖,各叶片排之癌的 厘定党相互作用也更加突出,油轮内流动图有的非定党性已不能忽略,... |
| hybrid_rrf | README.md | project_overview | # Power Equipment RAG Research System 这是围绕"动力装备知识库 / RAG / GraphRAG / 顶刊实验"重新整理后的工程工作区。 当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `fro... |

### cc036 为什么 9080 个 chunk 的普通 RAG 库只是起点，不是最终质量证明？

- Category: `exact_number_fact`
- Action: 为项目成果总览、POC 运行报告建立短 chunk 或事实卡片，专门承载 27/26/1/0 这类汇报数字。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | ，同时通过内置的校验机制拦截潜在幻觉。 --- ### 四、知识图谱与 GraphRAG 核心流程 (KG & GraphRAG Workflow) 知识图谱线（GraphRAG）是独立于普通 RAG 的另一条重型数据管线，主要用于处理需要全局宏观视野、跨文档实体关系推理的复杂问题： ```mermaid graph TD %% 离线数据构建流程 subg... |
| dense_hashing | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | 向量检索“见树不见林”的痛点。 3. **GraphRAG 编排层 (`rag_orchestrator/graph`)**：执行 Map-Reduce 风格的复杂图谱推理组装流。负责将高密度的结构化子图信息与海量社区摘要，在上下文中进行规约与逻辑拼接，驱动大模型进行全局视角的跨文档深度推理。 #### C. 双引擎公共基座 (Shared Infrast... |
| hybrid_rrf | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | 向量检索“见树不见林”的痛点。 3. **GraphRAG 编排层 (`rag_orchestrator/graph`)**：执行 Map-Reduce 风格的复杂图谱推理组装流。负责将高密度的结构化子图信息与海量社区摘要，在上下文中进行规约与逻辑拼接，驱动大模型进行全局视角的跨文档深度推理。 #### C. 双引擎公共基座 (Shared Infrast... |

### cc037 挑战杯答辩中如何解释本项目的创新点？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | README.md | project_overview | # Power Equipment RAG Research System 这是围绕"动力装备知识库 / RAG / GraphRAG / 顶刊实验"重新整理后的工程工作区。 当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `fro... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\04_e6a13e82eb6f\document.txt | ocr_text_cleaned | 93)0 5 1200-187 2601 1200\|o 2493 0-2669(0 272a\c 2782/¢,s2010-189 2624 2200 Jo-zs22 0.+2691\|0-2746.0-2767]0-52790-1910-264 11300 je asaa/0-2722/0-2265\|0:2799\|0-9357)266 2400\|2544\|... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | 64 se aL ICR FEL, 在商业上CE公司的T64也很成功。在其则世35年之后，术因的 工厂仍在生产T64。它为CE公司的林四分部奠定了至实的批生产基础， 共计生产了3215各T64 AR AOA, 7700涡轴发动机的设计和研制 GE AS AE T64的下一个发动机型号一T700，在美国飞机站气议 轮必动机历史上古据了非常重要的地位。T700... |

### cc038 为什么项目需要保留失败案例分析？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | 发动机按美国空军合同研制。除了为适应级生空气起动系统再对传动向 轮箱进行改进，为适度交流发电机包而对进口出轮箱进行改进，以及为 28伏点火系统提供保护措施之外。与为尖军制造的J79-CE-8 He 动机相同。J79-GE-15于1962年3月首次运行于同年10月通过 150小时的MQT。并在1963年2月开始生产型发动机交付。1963年5 人 ## Pag... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\13_4e83a06514eb\document.txt | ocr_text_cleaned | E,流通的机截面积油气流方向是逐沉减小的;另一部分是 侧切部分ABC 加四 m2 abe CARA We PR EAT BU 5 A AH A AURORE,See MN A AR 69“UC EOE. SSPE RAHM。与实际平均出气角ay ARLES A 动时,气体攻性将会对气流角产生一定的影响。至于在高超声加流动中,由空气动 力学知识可知,气体的儿... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\07_b1a5f133347e\document.txt | ocr_text_cleaned | SCRE 1 eC FL RO OL A A LPAI ZEEMAN EIS»UN AAA EA, 油汪油箱。经测济油箱的排气口排出。节流孔10 ALAN ROU ES OA I.HET 中，如果辕围环境空气比较肚，那么，节流孔9可能被廊扒，从而其通流而积增大。这将会引起去钠承 的密封宰气的流量和压力的变化，而使密封效果变差。这种情况应该引起运行人员的注意... |

### cc042 为什么挑战杯项目书要把应用价值和技术指标同时写清楚？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | README.md | project_overview | # Power Equipment RAG Research System 这是围绕"动力装备知识库 / RAG / GraphRAG / 顶刊实验"重新整理后的工程工作区。 当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `fro... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\02_f83c2147c643\document.txt | ocr_text_cleaned | 压力从末站出口压力(一般为5.3~5.9 MPa)调整至满 足燃气轮机的使用要求(=38 M7O1F燃气轮机要求天然气人口压力为3.4 MPa 1.59%),监 控器作为紧急调压器,在调压阅失效时起后备压力调节作用。当调压器故障时,其阀门全开， 此时调压器下游压力升高,监控器监测到调压器下游压力升高后,自动投入运行;如果监控器 也发生故障,监控器阀门全关,... |
| hybrid_rrf | README.md | project_overview | # Power Equipment RAG Research System 这是围绕"动力装备知识库 / RAG / GraphRAG / 顶刊实验"重新整理后的工程工作区。 当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `fro... |

### cc043 如果 GraphRAG 没有在所有题上超过 keyword baseline，应该如何解释？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | 性错误，应该如何? e,相加 式中:si一一发光火焰总的辐射系数; 2,一一发光火焰中气相的辐射系数; 2一一发兴火焰中炭粒子的辐射系数。 €,=0.539, a,=0.4526。 对吸收系数，类似于方程(12-38)，也可写出 1990~2000K得出一个-em HH 7,=2000K,2010K aah,取这两者的平均 值即为bio»同样定bco,:随... |
| dense_hashing | data_pipeline\reports\ocr_night_corrected_quality_audit_20260518.md | data_pipeline_reports | # 夜间总检矫正版 OCR 交付前质量审计 ## 总判断 这批 OCR 已经完成工程层面的全量处理，可以作为 RAG 检索候选文本；但它仍不是精校文本。 - 运行完整性：高，所有目标页都处理完，脚本层面没有报错。 - 文字识别：整体可用，但封面、目录、表格、公式、页眉页脚仍可能有识别噪声。 - 句段关系：新版 layout-aware 输出已经比旧版更好，... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | CI wea 锦材料公司的产品锦儿钛合金80的可用性，在随后的涡轮闹气发动机 发展的历史中证明烛常重要。在所有后续动力喷气公司的设计中，狗儿 钴合金80取代了雷克其78。动力喷气公司也帮助罗孚和BTH公司解决 制造问题。惠特尔提出了一个新蜂的滑轮叶片制造角决方案。他委泊两 个从革斯特的联合制竺公司来的工程师制得办叶片专用设备。 1941 4 12月23日，... |

### cc044 为什么本项目需要一页式成果总览？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | 发动机按美国空军合同研制。除了为适应级生空气起动系统再对传动向 轮箱进行改进，为适度交流发电机包而对进口出轮箱进行改进，以及为 28伏点火系统提供保护措施之外。与为尖军制造的J79-CE-8 He 动机相同。J79-GE-15于1962年3月首次运行于同年10月通过 150小时的MQT。并在1963年2月开始生产型发动机交付。1963年5 人 ## Pag... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\13_4e83a06514eb\document.txt | ocr_text_cleaned | “等价叶栅”的失速攻角修正值,进而得到其失速攻角。确定叶栅失速攻 FA im后,根据攻角;与失速攻角is的比值,便可以通过图5.6确定其在非设计点 Ainley和Mathieson认为在不考虑叶尖间隙的情况下,涡轮端区流动主要取决 于端壁边界层的发展等。他们结合大量的实验数据分析,给出二次流引起的阻力系 50°:40 sie sic (a)(b) o>=X... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | 发动机按美国空军合同研制。除了为适应级生空气起动系统再对传动向 轮箱进行改进，为适度交流发电机包而对进口出轮箱进行改进，以及为 28伏点火系统提供保护措施之外。与为尖军制造的J79-CE-8 He 动机相同。J79-GE-15于1962年3月首次运行于同年10月通过 150小时的MQT。并在1963年2月开始生产型发动机交付。1963年5 人 ## Pag... |

### cc045 如何证明本项目不是只做了资料搬运？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\06_汇报材料_发群和组会\组会展示要点.md | kg_poc_outputs | - 输入来源：Label Studio 导出的 OCR / bbox / transcription JSON。 - 文档内容：船舶燃气轮机控制与健康管理课程知识体系构建论文。 - OCR 文本块：246 个。 - chunk：14 个。 - schema：10 类实体，15 类关系。 - 候选三元组：27 条。 - schema 校验通过：27 条。 -... |
| dense_hashing | README.md | project_overview | igs/ # 全局配置中心（JSON/环境变量） ├─ core_domain/ # 领域语义与共享数据结构 ├─ data_pipeline/ # 数据导入、解析、清洗、切分与数据集 ├─ kg_pipeline/ # 知识图谱构建、社区检测与摘要 │ ├─ community_detection.py # Leiden 社区检测 │ ├─ commun... |
| hybrid_rrf | README.md | project_overview | igs/ # 全局配置中心（JSON/环境变量） ├─ core_domain/ # 领域语义与共享数据结构 ├─ data_pipeline/ # 数据导入、解析、清洗、切分与数据集 ├─ kg_pipeline/ # 知识图谱构建、社区检测与摘要 │ ├─ community_detection.py # Leiden 社区检测 │ ├─ commun... |

### cc046 为什么技术白皮书中必须写清楚数据流？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | README.md | project_overview | # Power Equipment RAG Research System 这是围绕"动力装备知识库 / RAG / GraphRAG / 顶刊实验"重新整理后的工程工作区。 当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `fro... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\13_4e83a06514eb\document.txt | ocr_text_cleaned | “等价叶栅”的失速攻角修正值,进而得到其失速攻角。确定叶栅失速攻 FA im后,根据攻角;与失速攻角is的比值,便可以通过图5.6确定其在非设计点 Ainley和Mathieson认为在不考虑叶尖间隙的情况下,涡轮端区流动主要取决 于端壁边界层的发展等。他们结合大量的实验数据分析,给出二次流引起的阻力系 50°:40 sie sic (a)(b) o>=X... |
| hybrid_rrf | TECH_STACK.md | project_overview | 心数据流向与跨模块调用约束 ### 4.1 数据构建流与图谱流 1. 用户上传文件 -> `data_pipeline/file_ingestion` 2. 调用 `parsers` 解析为文本 -> 执行 `cleaning` 和 `chunking` -> 分块写入 `document_store` / `vector_store`。 3. 从已切分的... |

### cc047 为什么要在答辩中主动说明系统不替代工程师决策？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | 纸。后来又有人进一步的研究'”'，进一步证实的确烟粒子在没到达测 烟仪器设备之前，在取样管线内有相当数量黏留在取样管的内壁上。他导出一个经验方 程，表示从取样管线出来的颗粒与进入取样管线的颗粒之比wm与其他参数，如取样管 线长度、取样管内径、取样管内样气流速的关系 n/n,=exp[—(1.05 x 1O“V+2.27 x103)ZZACDTY)](15-... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\11_f9ae274e182b\document.txt | ocr_text_cleaned | 1 ile a A Oe eet AAUFERITR. BREEAM 2 ROA LA ARK A tae 人RNAS Ae A8*CHCULIIB COREL J EMEC OA ALAR COMO). A 的压力可失对机组的性能亦有一定的影响,但比进气损失的影响要小一些。通党 认为排气损失增加136,功率下降4.7,执丁增加.5%,因此降低排气系统的压... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\10_e461d0cc931e\document.txt | ocr_text_cleaned | Page 232 (3)能保证机组良好的起动过程,点火可靠,不超温,不喘振,热应力小。按事先编好 的程序及时点火,暖机,控制喷油量,及时开大或关小压气机的可转导叶,打开或关闭压气 BLA AT. (4)具有一套可靠的保护和报警系统。这些保护大致有:机组的超速保护,机组的超 温保护,机组的振动保护`机组的熄火保护,机组的调节系统故障保护。此外还有润滑油压 过... |

### cc048 GraphRAG global 更适合回答什么类型的问题？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | 向量检索“见树不见林”的痛点。 3. **GraphRAG 编排层 (`rag_orchestrator/graph`)**：执行 Map-Reduce 风格的复杂图谱推理组装流。负责将高密度的结构化子图信息与海量社区摘要，在上下文中进行规约与逻辑拼接，驱动大模型进行全局视角的跨文档深度推理。 #### C. 双引擎公共基座 (Shared Infrast... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\08_530bf8fe4384\document.txt | ocr_text_cleaned | r.Conventional Steam Power Plants and Their Potential Siemens Guest Lecture,Chi- aa Oct,1996, ## Page 320 —S428 36 ABB Power Generation,GT26 Advanced Cycle System.‘The Innovative ... |
| hybrid_rrf | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | （LLM），抽取其中的“实体”、“关系”和“断言”三元组，经过人工校验或自动归一化处理后，将结构化数据存入 Neo4j 图数据库。 * **图谱高级挖掘**：在图数据库中执行图谱社区发现 (Community Detection) 算法，识别局部聚集的网络结构，并利用大模型生成“社区摘要”，反向存入图库，用于支撑宏观总结性问题的回答。 **2. 在线图谱检... |

### cc049 为什么 source_scope 对评测和检索都重要？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | evaluation\README.md | evaluation_framework | # evaluation 评测层。用于检索指标、答案指标、图谱指标、人工评估、消融实验和显著性检验。 ## 当前评测集 - `system_eval_questions.jsonl`：30 题小型系统评测集，覆盖普通 RAG、OCR 风险、GraphRAG/知识图谱、结构化数据和评测方法。 - `scripts/run_system_evaluation.... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\05_42b658350682\document.txt | ocr_text_cleaned | 22C 5069 2344 13820 1035 15.76 581 D.[alFA RE RLO.83°、 Q额定工况用天然气作燃料，额定功率是在透平联轴器处测得，不计进排气损失。 * 38 ## Page 43 (续) MAS)EF排气 额定功率热耗率\|转速 克鲁克勒-洪鲍尔特-杜茨公司(Kioeckner Humboldt Deutz)工业燃气轮机分... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\02_f83c2147c643\document.txt | ocr_text_cleaned | IN Tsay 3 min。从转速达到点火转速开始计时,持续3 min,计时 完毕后自动停止。在高盘期间应进行以下一些工作: 回当转速达到点火转速时,开始记录盘车时间,以确定高航冷却时间是否与设定值相符。 加监测下列参数在正常范围以内:轮盘间阶温度,燃烧器上下缸金属温差,透平上下缸金 属温关,轴振动,轴承回油温度,轴承金属温度.润滑油供油压力和温度.SFC... |

### cc050 为什么要记录每个实验的命令和报告路径？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | 纸。后来又有人进一步的研究'”'，进一步证实的确烟粒子在没到达测 烟仪器设备之前，在取样管线内有相当数量黏留在取样管的内壁上。他导出一个经验方 程，表示从取样管线出来的颗粒与进入取样管线的颗粒之比wm与其他参数，如取样管 线长度、取样管内径、取样管内样气流速的关系 n/n,=exp[—(1.05 x 1O“V+2.27 x103)ZZACDTY)](15-... |
| dense_hashing | data_pipeline\reports\public_books_json_audit_20260522.md | public_books_json_audit_reports | 0186-0238_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun_Huan_Zhuang_Zhi__Shang__1.pdf \| 18 \| 18 \| 893 \| 420 \| 244 \| 177 \| \| 0186-0238_Ran_Qi_Lun_Ji_Yu_Ran_Qi_-Zheng_Qi_Lian_He_Xun... |
| hybrid_rrf | TECH_STACK.md | project_overview | 评估和统计显著性分析。 ├─ experiments/ # 实验编排层：负责顶刊实验脚本、配置矩阵、批量运行和结果归档。 ├─ paper_assets/ # 论文资产层：负责自动生成论文图表、表格、案例、附录和复现实验说明。 ├─ api_server/ # 服务接口层：对外提供上传、处理、检索、问答、评测、日志查询等 API。 ├─ frontend_... |

### cc051 如果现场后端服务启动失败，演示应该如何继续？

- Category: `corpus_gap_or_query_gap`
- Action: 回看原文证据，补同义词、补短摘要，或把该题标为需要 GraphRAG/结构化索引的问题。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\07_b1a5f133347e\document.txt | ocr_text_cleaned | 汽轮机上+发电机的GDP 195000kgf mm ak eat, 150+ /—50r/min 0到清政转速的启动时间230上/一1os eect 550-+/—50r/min means 1800~2000e/min eat EA 805 清吹至点火的下降时间Nos PL Oe. ‘ershayALI 10-96, aba AER ILI 10-97,... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\10_e461d0cc931e\document.txt | ocr_text_cleaned | 温度不 同而热膨胀不一致时,端面齿处两轮盘之间能相互滑动,减少了相互间的作用力。端面具 与中心拉杆相配合使用时,转子的装拆甚为方便,但端面齿精度要求高,加工较难,故在压 气机中较少应用。而在透平转子中,各轮盘之间的温度差别一般比压气机的大,端面齿处 \| b c FA8.19中心拉杆转子 an MELT be骑颖径回销杀式co SRT BT [用用 由了0n... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\07_b1a5f133347e\document.txt | ocr_text_cleaned | 汽轮机上+发电机的GDP 195000kgf mm ak eat, 150+ /—50r/min 0到清政转速的启动时间230上/一1os eect 550-+/—50r/min means 1800~2000e/min eat EA 805 清吹至点火的下降时间Nos PL Oe. ‘ershayALI 10-96, aba AER ILI 10-97,... |

### cc052 为什么项目材料中要保留不能过度声称的清单？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\02_f83c2147c643\document.txt | ocr_text_cleaned | 防止新空气进入燃气轮机票壳内重新引燃火焰。 在进入燃气轮机间检查设备状况之前,应当确认单壳内温度合适,将消防系统切换至检修 ” 状态或者停运思壳消防。进和燃气轮机棱壳的工作人员应当根据实际情况采取必要且适当 的保护措施后才能进入。例如,身穿隔热服,穿哉消防呼吸器,全开单这风机通风,在单壳间 门口或其他便利位置准备好灭火器,等等。 一般而言,燃气轮机蛙壳内火... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\03_8262abdfa4ad\document.txt | ocr_text_cleaned | 文献 [1]Goodger,E.M.,‘Transport Fuels Technology,Landfall Press,Norwich,UK,2000. [2]Goodger,E.M.,Aerospace Fuels,Landfall Press,Norwich,UK,2007. [3]Edwards,J.T,“Liquid Fuels and Pro... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\10_e461d0cc931e\document.txt | ocr_text_cleaned | 液力变扭器的作用是;保证燃气轮机在开始旋转的瞬间,就能由起动柴 M那么,为什么不能把起动柴油机的输出轴与起动离 eet na em BUA ALA Lt IPA PR A A Me asmasymaeoesmuse RDU,就能发出很大扭矩。因为柴油机所能发出的功率 \|BUH自持转于(或扭矩)与单位时间内吸入到气缸中去的空气量有密 速后,人们才能向它增加喷... |

### cc053 为什么 hybrid 检索可能被弱 dense_hashing 稀释？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\07_b1a5f133347e\document.txt | ocr_text_cleaned | SCRE 1 eC FL RO OL A A LPAI ZEEMAN EIS»UN AAA EA, 油汪油箱。经测济油箱的排气口排出。节流孔10 ALAN ROU ES OA I.HET 中，如果辕围环境空气比较肚，那么，节流孔9可能被廊扒，从而其通流而积增大。这将会引起去钠承 的密封宰气的流量和压力的变化，而使密封效果变差。这种情况应该引起运行人员的注意... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\08_530bf8fe4384\document.txt | ocr_text_cleaned | 的保养方法 当联合循环电厂在机组停备用\| ，应对余热钢妨采取的防认措施。这些措施可以根据个坊备用时 间的长短，合理地选用 《1保持压力法。余热锅炉停运后，关闭各汽水阁门，利用钢护的残余压力，防止空气潮人锅简和 管入内，同时控制水的pH值在%.8一10.4之间，使其保持一定的碱度。这种方法扣作简单、方便- 但常会由于系统的严密性差，无法长期维持压力。一般来说... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\08_530bf8fe4384\document.txt | ocr_text_cleaned | 的保养方法 当联合循环电厂在机组停备用\| ，应对余热钢妨采取的防认措施。这些措施可以根据个坊备用时 间的长短，合理地选用 《1保持压力法。余热锅炉停运后，关闭各汽水阁门，利用钢护的残余压力，防止空气潮人锅简和 管入内，同时控制水的pH值在%.8一10.4之间，使其保持一定的碱度。这种方法扣作简单、方便- 但常会由于系统的严密性差，无法长期维持压力。一般来说... |

### cc054 为什么真实 embedding 和 reranker 是下一阶段质量提升重点？

- Category: `terminology_alias_gap`
- Action: 增加查询改写/同义词扩展：Reranker -> 重排、二次排序、Cross-Encoder、精排。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | 向量检索“见树不见林”的痛点。 3. **GraphRAG 编排层 (`rag_orchestrator/graph`)**：执行 Map-Reduce 风格的复杂图谱推理组装流。负责将高密度的结构化子图信息与海量社区摘要，在上下文中进行规约与逻辑拼接，驱动大模型进行全局视角的跨文档深度推理。 #### C. 双引擎公共基座 (Shared Infrast... |
| dense_hashing | data_pipeline\reports\ocr_layout_aware_summary.md | data_pipeline_reports | 4 \| 0 \| `D:\虚拟C盘\RAG\data_pipeline\ocr_layout_aware_tesseract\tsinghua_gas_turbine_books\12_703d154d523b\document.txt` \| \| 航空燃气轮机涡轮气体动力学：流动机理及气动设计=TURBINE AERODYNAMICS FOR AERO-EN... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | 9-22所示)。构成了JHPTET计划的\| 核心。这些项目验证术来多用途皮半机、特种飞机、运输机、先进直天 机、有航导弹上应用的新技术。ATECG计划内1963年开始实施，JTAGC 计划愉1987年开始实施，1988年随着THPTET计划的启动，JTAGC计划 并人HPTET计划。根据未来20年关键军用准进系统的发展震要。这些 计划验证的技术可转移到所有... |

### cc055 为什么 OCR 两栏排版会影响 RAG 入库质量？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\reports\ocr_quality_audit.md | ocr_quality_reports | # OCR 可靠性审计 ## 总判断 这批 OCR 可以作为普通 RAG 的“检索候选文本”，但不能当作完全无误的精校文本。 - 运行完整性：高。13 本都跑完了，脚本层面没有报错。 - 文字识别：整体可用，但不能保证零错。封面、目录、表格、公式、页眉页脚最容易出错。 - 句段关系：中等。OCR 保留的是页面上的视觉行顺序，不等于真正的语义段落结构。 ##... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\08_530bf8fe4384\document.txt | ocr_text_cleaned | Py 0.2778 0.2163 0.2875 0.2198 0.2970 0.2234 \|十二 28.0 0.3220 0.2705 0.3417 0.2740\|0.3512 0.2776 =十十 39.2 0.4120 0.3505 0.4217 0.3540 0.4312 0.3576 44.8 0.4519 0.3904 0.4616 0.3939... |
| hybrid_rrf | data_pipeline\reports\ocr_layout_risk_audit.md | data_pipeline_reports | # OCR 两栏版面风险审计 ## 结论 你的担心是成立的：如果 PDF 是左右两栏，普通 OCR 文本可能把阅读顺序搞错。 现有全量 OCR 结果只保存了文字行，没有保存坐标框；因此旧结果不能可靠恢复“左栏先读完，再读右栏”的真实顺序。 这份报告重新抽样跑了一遍带坐标的 OCR，用来估计两栏风险。 ## 抽样结果 - 抽样页数：13 - 疑似两栏页：1 ... |

### cc056 为什么知识图谱关系类型不能全部写成 related_to？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | kg_pipeline\poc\README.md | kg_poc_outputs | # 最小知识图谱 POC 本目录是会议要求的最小 graph construction 样例，主题是燃气轮机/设备故障文本。 重要说明： - 当前版本是 `rule-based/manual baseline`。 - 没有调用 LLM。 - 没有跑通 Microsoft GraphRAG、Neo4j 或 LlamaIndex/LangChain。 - 目标... |
| dense_hashing | kg_pipeline\poc\graph_demo.html | kg_poc_outputs | n); } .badge.needs_discussion { background: var(--gold); } .badge.reject { background: var(--red); } .hidden { display: none; } @media (max-width: 1080px) { .layout, .text-grid { ... |
| hybrid_rrf | kg_pipeline\poc\graph_demo.html | kg_poc_outputs | ria-label="关系筛选"> <button class="filter active" type="button" data-filter="all">全部</button> <button class="filter" type="button" data-filter="pass">通过</button> <button class="filt... |

### cc057 为什么结项验收清单要把主张映射到证据文件？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | README.md | project_overview | # Power Equipment RAG Research System 这是围绕"动力装备知识库 / RAG / GraphRAG / 顶刊实验"重新整理后的工程工作区。 当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `fro... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\10_e461d0cc931e\document.txt | ocr_text_cleaned | ,故共用了36台燃气轮机压 缩机组,单机容量25MW,总计900MW.。该两套装置注气量400一600亿ms/a,可回收轻烃 700~1000 Fj t/a. 轻烃 和\|\|2二二二二二二远'二二一一一-注气井 Sa系上二二二二一-起一一一一一一-3 统广一一一一一二二二二一一 轻烃一一一一一一一了了 图14.13天然气回注装置 气举采油类似于注气,是将分离... |
| hybrid_rrf | data_pipeline\reports\ocr_night_corrected_delivery_acceptance_20260518.md | data_pipeline_reports | # OCR 交付前验收报告 - 生成时间：`2026-05-18T01:35:00` - OCR 根目录：`D:\虚拟C盘\RAG\data_pipeline\ocr_layout_aware_tesseract_night_corrected\tsinghua_gas_turbine_books` ## 结论 可以交付为“带风险标注的 OCR 文本成果”... |

### cc058 为什么本项目适合用可复现实验而不是只用主观展示来证明效果？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | TECH_STACK.md | project_overview | # 顶刊目标 RAG/GraphRAG 项目技术栈与工程架构白皮书 本文件全面记录了本项目所依赖的所有技术栈，并明确区分了“第三方开源/商业技术”与“完全自研的架构体系”。同时，作为系统的全景技术档案，本文详细收录了本项目的底层工程蓝图、模块调度数据流向、LLM 运行上下文以及可观测性追踪体系的所有核心细节。本项目是一个面向顶刊论文级别、高度工程化、可复现... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | 率降低而需要的功率 增大。这时压力很低，并没有足够的激发能量来造成高频周次的钱劳损伤。在相当低的 转速下，高压压气机应该退出旋转失速。在燃烧室点火时，以及在点火之后，有旋转失 速是不能接受的。在旋转失速情况下，由于压气机效率低，要保持转子加速，就要求非 常商的油轮进口温度。 ## Page 263 248 sense pean (2)Mugabe,oo)a... |
| hybrid_rrf | TECH_STACK.md | project_overview | # 顶刊目标 RAG/GraphRAG 项目技术栈与工程架构白皮书 本文件全面记录了本项目所依赖的所有技术栈，并明确区分了“第三方开源/商业技术”与“完全自研的架构体系”。同时，作为系统的全景技术档案，本文详细收录了本项目的底层工程蓝图、模块调度数据流向、LLM 运行上下文以及可观测性追踪体系的所有核心细节。本项目是一个面向顶刊论文级别、高度工程化、可复现... |

### cc059 项目冲击特等奖时最应该避免哪三类表述风险？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | -主空气模，采用LPP，但放流强度有限 而且由非旋流和旋流组合 ## Page 476 第16章“预混代烧中的回火461 Se CE SA 第三，如参考文献[146】中所建议的，要避免预混模中可能出现的台阶型，不要 用扩张型出口，不要在放流器下游加燃油喷射杆，不要有流动分配板，也不要用燃油首 向团射等。这些情况如图16-11所示，这些都已经证明，有实际意义... |
| dense_hashing | data_pipeline\reports\public_books_json_audit_20260522.md | public_books_json_audit_reports | 3628 \| 15 \| True \| \| project-1-at-2026-05-19-03-05-578140b7.json \| 48.47 \| 3643 \| 15 \| True \| \| project-1-at-2026-05-19-04-14-ef170eef.json \| 49.04 \| 3654 \| 11 \| True \| \| project-... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | -主空气模，采用LPP，但放流强度有限 而且由非旋流和旋流组合 ## Page 476 第16章“预混代烧中的回火461 Se CE SA 第三，如参考文献[146】中所建议的，要避免预混模中可能出现的台阶型，不要 用扩张型出口，不要在放流器下游加燃油喷射杆，不要有流动分配板，也不要用燃油首 向团射等。这些情况如图16-11所示，这些都已经证明，有实际意义... |

### cc060 第一轮挑战杯升级完成后，项目应该达到什么状态？

- Category: `exact_number_fact`
- Action: 为项目成果总览、POC 运行报告建立短 chunk 或事实卡片，专门承载 27/26/1/0 这类汇报数字。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | README.md | project_overview | # Power Equipment RAG Research System 这是围绕"动力装备知识库 / RAG / GraphRAG / 顶刊实验"重新整理后的工程工作区。 当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `fro... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\03_8262abdfa4ad\document.txt | ocr_text_cleaned | CR-2392 1974. /25]Walker,R.E.,and Kors,D.L.,“Multiple Jet Study,”Final Report,NASA CR 121217,1973. \|26]Srinivasan,R.,Berenfeld,A.,and Mongia,H.C.,“Dilution Jet Mixing Program Phas... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | EZA LARA 1108洲 际间炸机竞争，该飞机彼命名为XB-70天尔基蛙，动力选用J93- =1的发展型3-GE-3 SAAN CAE a 12月，国防部长指示航空研究与开发司令部和空军装备司信 oo ## Page 423 B suemmesmenen ‘mB~70 MEA AL Re,IER NE HP SAC联队的 时间。1958年1 JY,RR... |

### se003 燃烧室在燃气轮机热力循环中承担什么功能？

- Category: `partial_ranking_gap`
- Action: 调小关键报告 chunk、增加 reranker，并做按 source_scope 的候选过滤或加权。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\09_949722474f48\document.txt | ocr_text_cleaned | 传热学在其发展进程中者是采用了理论 分析与实验相结合的方法。科学实验是推动这些学科发展的重要力量,通过实验,可以验 证理论的正确性,通过实验,可以发现新的现象,促进了理论分析的发展.随着计算机和计 算理论的发展,数值分析也已经成为这些学科研究发展的重要方面. 我们强调实验实践的重要性,在学习和工作中,一定要牢记实践是检验真理的惟一 标准。特别是对从事工程工... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\09_949722474f48\document.txt | ocr_text_cleaned | 传热学在其发展进程中者是采用了理论 分析与实验相结合的方法。科学实验是推动这些学科发展的重要力量,通过实验,可以验 证理论的正确性,通过实验,可以发现新的现象,促进了理论分析的发展.随着计算机和计 算理论的发展,数值分析也已经成为这些学科研究发展的重要方面. 我们强调实验实践的重要性,在学习和工作中,一定要牢记实践是检验真理的惟一 标准。特别是对从事工程工... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\09_949722474f48\document.txt | ocr_text_cleaned | 传热学在其发展进程中者是采用了理论 分析与实验相结合的方法。科学实验是推动这些学科发展的重要力量,通过实验,可以验 证理论的正确性,通过实验,可以发现新的现象,促进了理论分析的发展.随着计算机和计 算理论的发展,数值分析也已经成为这些学科研究发展的重要方面. 我们强调实验实践的重要性,在学习和工作中,一定要牢记实践是检验真理的惟一 标准。特别是对从事工程工... |

### se008 为什么燃气轮机运行监测要同时看温度、压力和振动信号？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\07_b1a5f133347e\document.txt | ocr_text_cleaned | 烟气轮机、风机等设备，开展了转子在线运行监测与故障诊浙机理及治理措施领域的工 作,取得了显著的经济效益 振动问题是回转机械运行中最主要的问题，拔动信号包含了丰富的机机运行状态信息并易于在线条 集和诊断。振动分析方法是最主要的故障诊断方法，可对故障类型作分析判断。对直气轮机的故障监测 与诊断对象主要是回转机械的核心部件转子及组件，如轴颈的振动及支撑轴承，还有... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\10_e461d0cc931e\document.txt | ocr_text_cleaned | ATT A oS,FT a Pd i RS ss FB BY JE 工况,其重载工况和轻载工况可参照上面叙述过的自行分析,超扭和超速限制线也不画， 同样可自行分析。 (1)COGOG。这类舰艇都采用双桨推进,巡航时两台巡航机运行,高速航行时改为两 台加力机运行,情况与前述的单桨推进相似,只是这时每侧的螺旋桨各负担总推进功率的 一半。图7.90中的oa'a线... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\11_f9ae274e182b\document.txt | ocr_text_cleaned | 可能有多方面的反映,对振动信号进行频 谱分析,找到振动产生的根本原因.才能有效地排出振动故障。频谱分析和故障厚 因的对应关系,可以根据前人的研究2,利用所建立的频谱特征和故障原因的关 系图表进行排障。对于振动不良但未引起跳机的故障模式,如果故障发生在燃机 当中.可以在定期停机检查中对燃机进行检查和维修,如果故障发生在其他附件如 联轴器.此轮箱或发电机中,则... |

### se009 燃气轮机故障诊断中，为什么需要把现象、原因和处理措施关联起来？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\11_f9ae274e182b\document.txt | ocr_text_cleaned | sions.1948,20(1):61—74. [L41]来五星,轩建平,史铁林,等.Wigner-Ville时频分布研究及其在齿轮故障诊断中的应用 CU.振动工程学报,2003,16(2):247-250, [42]程发研,汤宝平,刘文艺.一种抑制维格纳分布交叉项的方法及在故障诊断中应用[站 中国机械工程,2008,19(14):1727-1731. L... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\02_f83c2147c643\document.txt | ocr_text_cleaned | 多燃用重油和轻油,相对于气体顽料机组,液体燃料机组需增设液体燃料分配装置和和雾化空 气系统等;双燃料机组既可燃用气体燃料,也可燃用液体燃料。 另外,燃气轮机按照结构特点还可分为轻型和重型两类。轻型的结构紧次而轻,体积小、 装机快,启动快,所用材料一般较好,主要用于航室,其质量功率比一般低于0.2 kg/kW,航空 燃气轮机经适当改进后加装动力透平,所派生出... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\11_f9ae274e182b\document.txt | ocr_text_cleaned | y\|涡轮通过能力\| FE oe经济性 “neh\|明显增加\| RETR REE)三\|\|后时\| P 降低 叶片受\|ee cae ey ag:\|浊轮出功降低,排气温\| 外来物\|RRR ea a ot ese\|已\| 3 [MIE]忆 损伤\|性降低 \|高温透平排气\|引起成生产区的安全安全性\| alae vewpaene\|涡轮出功降低,全厂热\|经济性 woe mI L... |

### se010 设备维修报告中，哪些信息最适合作为 RAG 检索的证据片段？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | 别与 Query 改写] R -->\|向量召回\| E R -->\|关键词召回\| F E --> S[多路召回结果] F --> S S --> T[融合去重与 Reranker 重排] T --> U[Top-K 高质量证据] U --> V[上下文组装 Prompt] Q -.-> V V --> W[LLM 生成与幻觉校验] W --> X[带 Cit... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\13_4e83a06514eb\document.txt | ocr_text_cleaned | 冲击作用,这种交变载荷会导致转子叶片前缘 产生高周疲劳失效。 由于径流涡轮具有如上所说的结构简单以及在小流量下仍可获得较高效率等 优点,因此,它不仅在柴油机汽油机的废气涡轮增压器上和小功率燃气轮机装置上 获得广泛应用,并且大量被用来作为制冷及低温装置上的膨胀机。在能源的综合利 用方面,径流涡轮作为回收能量的设备也得到了应用,如烟气涡轮膨胀机,有机工质 的涡... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\11_f9ae274e182b\document.txt | ocr_text_cleaned | 应用分析[].科学技术与工程,2007， 7(15):3881-3885. [24]余杰.周浩,黄春光.以可靠性为中心的检修策略品].高电压技术,2005,31(6); 090 ## Page 108 BABS BRI RCM的相关分析方法及工具 27-28. [25]Ade.DAT SEE oy AE CRCMD在电力系统中的应用研究LD].杭州:浙江大... |

### se013 Reranker 在 RAG 流程中的作用是什么？

- Category: `terminology_alias_gap`
- Action: 增加查询改写/同义词扩展：Reranker -> 重排、二次排序、Cross-Encoder、精排。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\02_f83c2147c643\document.txt | ocr_text_cleaned | 检 查经TCA加热后的天然气温度是否满足燃气轮机的要求,如果温度低于低限设定值,将触发 低速RUNBACK,此时应观察风气轮机控制系统是可动作正常,若不正常可手动三负荷。在此 期间,应采取各种有效措施(如尽快恢复海水奈\水浴炉正常)尽量提高天然气温度。 5.22.8系统维护及保养 系统维护保养包括双级过滤器的切换及涉芯的更换、水浴炉维护及其他定期维护保养-... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | AL) 的目的是为广大读者提供一个全面了解世界航室发动宙发展历 Ki TAA RRMA GRR ARTI ah BAR HA fo 作原理有更科学、系统的认识，对国外航空发动机的产品发展 经验、组织管理方法和技术发展路线有更深记的理解，对航空 发动机发展对国防建设和国民经济发展的重要性有更充分的重 视，以唤起广大读者对航空改动机事业的关注和热爱，并积极 投... |
| hybrid_rrf | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | raphRAG Survey: Retrieval-Augmented Generation with Graphs》**：全面梳理了当前 RAG 系统结合图技术的常见模块划分，帮我们避坑了业界的不同技术路线挑战。 2. **工程落地实操参考** - **《Neo4j GraphRAG Python Documentation》**：重型方案参考。重点看了... |

### se014 RAG 回答为什么需要 citation 或 evidence 溯源？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | 别与 Query 改写] R -->\|向量召回\| E R -->\|关键词召回\| F E --> S[多路召回结果] F --> S S --> T[融合去重与 Reranker 重排] T --> U[Top-K 高质量证据] U --> V[上下文组装 Prompt] Q -.-> V V --> W[LLM 生成与幻觉校验] W --> X[带 Cit... |
| dense_hashing | data_pipeline\reports\public_books_json_audit_20260522.md | public_books_json_audit_reports | -at-2026-05-19-08-10-28b5dbce.json \| 54.31 \| 3753 \| 11 \| True \| \| project-1-at-2026-05-20-02-57-883eb4bc.json \| 55.3 \| 3771 \| 18 \| True \| \| project-1-at-2026-05-20-03-14-bfd5082b.... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | 何 散布，(2)看是否有回流区来稳定火焰。有一个回流区存在是肯定的。其位置始于x= 16mm，轴向止于x~40mm，这位置合适。如果回流区出现非常早，就紧贴在副模出口， 甚至局部回缩。这并不对挂住炎有利。因为总的说，这地方还没有多少燃伐，回流回来 的热机气温度并不高，起不了稳定火焰的作用;MRI,MEE MTR CMB EEA ST, 也没多少稳住火烙的作... |

### se015 如果检索结果没有覆盖标准答案中的关键证据，生成模型可能出现什么风险？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | TECH_STACK.md | project_overview | al_engine`) * **多路召回与重排机制 (Hybrid Retriever & Reranker)**：自研集成层，将 Dense (向量语义)、Sparse (BM25 词法) 和 Graph (图谱邻域) 三路检索结果进行评分归一化、去重和融合互补。 * **上下文智能打包器 (Context Packer)**：自研 token 预算控制... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\07_b1a5f133347e\document.txt | ocr_text_cleaned | [ae[aver\|mea[aes[amar[ame piece\|ame mm we[ame\|ane[ieee\|imo\|aoe[we\|ace BRIAN,WD[neko ow\|ow\|on\|Lo\|r\|ie\|an\|ow Bete ot[at[oe[oe\|oe\|oe\|oe\|a ES screws(\|20m\|100\|oo\|im\|100\|10m\|am\|am\|m0 at... |
| hybrid_rrf | TECH_STACK.md | project_overview | 三、 全局工程蓝图与物理目录架构 (Detailed Blueprint) 以下为系统十二层核心模块的详细职责划分与包结构： ```text rag_research_system/ ├─ configs/ # 全局配置中心：统一管理实验、模型、数据、日志、部署参数。 ├─ core_domain/ # 领域语义层：定义知识单元、实体、关系、文档、问题、证... |

### se020 Layout-aware OCR 相比普通逐行 OCR，对 RAG 入库有什么价值？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | ，同时通过内置的校验机制拦截潜在幻觉。 --- ### 四、知识图谱与 GraphRAG 核心流程 (KG & GraphRAG Workflow) 知识图谱线（GraphRAG）是独立于普通 RAG 的另一条重型数据管线，主要用于处理需要全局宏观视野、跨文档实体关系推理的复杂问题： ```mermaid graph TD %% 离线数据构建流程 subg... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | 172kg/(ms),如果几何特征K=0.3，Ap=1378kPa，这时速度系数Ky只有 244。所以如果只简单地用[2人2】当作中吕度，关了4信。 在通常情况下，喷路的几何特征万记是未知的。我们知道喷委锥角26与喷嘴几何 特性密切有关，在无和液体上它们是一一对应的关系，如图6-10所示。该图中示出对 无黏液体的理论计算以及试验值，要说明，这个试验值只适用... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | Re,=WDp,/p,(5-35) Me=了AL六十Yi,Ar(5-36) 了，Y,,. pr=\|—+=(5-37) aT,DFT nh,-2np(+)In(1+B,)(1+0.3Ref,°Pr?®)(5-38) ## Page 146 第5章Me ih RR加 这是经党用的计算运 动中的液滴节发速率的方程式。 5.7等效蒸发常数 在所有关于奖油液注东发计... |

### se021 知识图谱 POC 中 schema 约束的作用是什么？

- Category: `partial_ranking_gap`
- Action: 调小关键报告 chunk、增加 reranker，并做按 source_scope 的候选过滤或加权。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | *RAG 编排层 (`rag_orchestrator`)**：基于 Advanced RAG 调度策略。集成前置的查询理解与改写 (Query Rewriting) 以对齐知识库语义，通过动态组装上下文 (In-Context Assembly) 配合严格 Prompt 工程，强制大模型生成带有准确引用 (Citation) 的溯源回答，建立防幻觉屏障。... |
| dense_hashing | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | *RAG 编排层 (`rag_orchestrator`)**：基于 Advanced RAG 调度策略。集成前置的查询理解与改写 (Query Rewriting) 以对齐知识库语义，通过动态组装上下文 (In-Context Assembly) 配合严格 Prompt 工程，强制大模型生成带有准确引用 (Citation) 的溯源回答，建立防幻觉屏障。... |
| hybrid_rrf | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | *RAG 编排层 (`rag_orchestrator`)**：基于 Advanced RAG 调度策略。集成前置的查询理解与改写 (Query Rewriting) 以对齐知识库语义，通过动态组装上下文 (In-Context Assembly) 配合严格 Prompt 工程，强制大模型生成带有准确引用 (Citation) 的溯源回答，建立防幻觉屏障。... |

### se023 当前 Graph construction POC 已经证明了什么？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\06_汇报材料_发群和组会\组会展示要点.md | kg_poc_outputs | # 本次组会展示清单：Label Studio JSON -> Graph Construction POC ## 一句话结论 这次已经补出一个可操作的 Graph construction POC 工作台：使用之前的 Label Studio 导出 JSON 作为输入，完成 `JSON -> OCR 文本块 -> chunk -> schema -> 候... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | 足长时间待机的低耗油率。首要任务是降低发 动机成本，人允许整个武器系统满足总费用目标。该原理在1971年以 “设计成本”的形式并被固化。史蒂芬.本张伯伦(Stephen J.Chamberlin), TF34/T58/764项目部门的总经理，对GE公司如何应用这个概念进行了 说明。它的令述提供了一个特别好的例子，即一个航空发动机的制造者 如何把他的设计重点... |
| hybrid_rrf | docs\project_deliverables\06_汇报材料_发群和组会\组会展示要点.md | kg_poc_outputs | # 本次组会展示清单：Label Studio JSON -> Graph Construction POC ## 一句话结论 这次已经补出一个可操作的 Graph construction POC 工作台：使用之前的 Label Studio 导出 JSON 作为输入，完成 `JSON -> OCR 文本块 -> chunk -> schema -> 候... |

### se024 当前知识图谱 POC 的人工评审结果是多少？

- Category: `exact_number_fact`
- Action: 为项目成果总览、POC 运行报告建立短 chunk 或事实卡片，专门承载 27/26/1/0 这类汇报数字。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\06_汇报材料_发群和组会\组会展示要点.md | kg_poc_outputs | - 输入来源：Label Studio 导出的 OCR / bbox / transcription JSON。 - 文档内容：船舶燃气轮机控制与健康管理课程知识体系构建论文。 - OCR 文本块：246 个。 - chunk：14 个。 - schema：10 类实体，15 类关系。 - 候选三元组：27 条。 - schema 校验通过：27 条。 -... |
| dense_hashing | docs\project_deliverables\06_汇报材料_发群和组会\组会展示要点.md | kg_poc_outputs | - 输入来源：Label Studio 导出的 OCR / bbox / transcription JSON。 - 文档内容：船舶燃气轮机控制与健康管理课程知识体系构建论文。 - OCR 文本块：246 个。 - chunk：14 个。 - schema：10 类实体，15 类关系。 - 候选三元组：27 条。 - schema 校验通过：27 条。 -... |
| hybrid_rrf | docs\project_deliverables\06_汇报材料_发群和组会\组会展示要点.md | kg_poc_outputs | - 输入来源：Label Studio 导出的 OCR / bbox / transcription JSON。 - 文档内容：船舶燃气轮机控制与健康管理课程知识体系构建论文。 - OCR 文本块：246 个。 - chunk：14 个。 - schema：10 类实体，15 类关系。 - 候选三元组：27 条。 - schema 校验通过：27 条。 -... |

### se025 GraphRAG 的局部搜索和全局搜索分别适合什么类型的问题？

- Category: `hybrid_dilution`
- Action: 在当前 hashing embedding 阶段提高 keyword 权重，等换成真实 embedding 后再重新调 Hybrid。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | README.md | project_overview | igs/ # 全局配置中心（JSON/环境变量） ├─ core_domain/ # 领域语义与共享数据结构 ├─ data_pipeline/ # 数据导入、解析、清洗、切分与数据集 ├─ kg_pipeline/ # 知识图谱构建、社区检测与摘要 │ ├─ community_detection.py # Leiden 社区检测 │ ├─ commun... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\09_949722474f48\document.txt | ocr_text_cleaned | 力损失Ap,”. KERMA 数分别为 和_—Ap, 压力保持系数分别为 由上述可得 进一步得 71 by pal®~ pa/®,— PP2Pe 8:18) 4 ©为诸压力保持系数的乘积,是总的压力保持系数。于是 tr= On (3.17) AR, AP RARE ar<r OF aD, FE OAH AY LE A RP ee. 3.13和图3. 14是... |
| hybrid_rrf | README.md | project_overview | # Power Equipment RAG Research System 这是围绕"动力装备知识库 / RAG / GraphRAG / 顶刊实验"重新整理后的工程工作区。 当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `fro... |

### se027 Goldwind 解码数据质量报告中，解析后的数据规模是多少？

- Category: `structured_fact_routing`
- Action: 给 Goldwind/SCADA 类问题建立结构化摘要索引，保留 key-value、字段名、行列规模和报告路径。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | docs\project_deliverables\RAG技术架构与背景资料梳理.md | rag_system_design_docs | 别与 Query 改写] R -->\|向量召回\| E R -->\|关键词召回\| F E --> S[多路召回结果] F --> S S --> T[融合去重与 Reranker 重排] T --> U[Top-K 高质量证据] U --> V[上下文组装 Prompt] Q -.-> V V --> W[LLM 生成与幻觉校验] W --> X[带 Cit... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\07_b1a5f133347e\document.txt | ocr_text_cleaned | 分子扩散外，主要靠气流流团的不 规则运动来完成。这种运动的尺度和强度都远大于分子运动，因此消流中的质量和热量传递要比层流中 激烈得多。相应地，在其他条件相同时，汕流中的火焰传播速度ST也大于层流火焰传播速度Su。此 外，汕流火焰锋面通常不像层流火焰那样平整，而是形成不规则的波浪和裙皱，从而在相同的空间内扩 大了火焰的有效面积A。由式〈5-21)可知，这两个... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | 少的颗粒是从火焰简壁上积谈或燃油喷嘴积谈然后掉落下来而 产生的。这样一般来说，影响粒子尺寸及分布的有: (1)火焰简壁及喷嘴积炭有多严重，这是大颗粒炭粒子的来源，人例如，天然气不 会生成沉积在喷嘴表面的痰粒子; (2)燃料的化学组成，分子结构，人例如，烷烃与芳香烃不同，芳香烃中又有多少 是多环芳香烃; (3)燃烧室的油气比及工况的影响。 8 DMPS数据 ... |

### se028 Goldwind 解码数据中，哪些列属于非数值列？

- Category: `structured_fact_routing`
- Action: 给 Goldwind/SCADA 类问题建立结构化摘要索引，保留 key-value、字段名、行列规模和报告路径。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | (PHaosal) d—0.370—0.270 ci 0.683 0.143 第12章燃烧室传热与冷却347 Pio Poor+Pino Ey,o=exp(g,+gu+htanh3w)(12-10) tre 2 ee as(12-11) 1+q(Pus) 0.119(py,o5,.)°(12-12) u=(T-625)/625(12-13) ## Page... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\11_f9ae274e182b\document.txt | ocr_text_cleaned | 在产品第一次使用之前)或者故障发生在生产.打包或者运输过程中。在后续指数 分布和Weibull分布的讨论中将更多地关注位置参数的概念,因为寿命分布最常 使用的是位置参数。 2.2.2 HSIN HT GRRE o>OR 常用的寿命分布类型主要有对数正态分布`.Weibull分布、正态分布、指数分 布,而机械产品的疲劳寿命通常服从于对数正态分布或Weibul... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\11_f9ae274e182b\document.txt | ocr_text_cleaned | 可以将任意一个复杂信和号分解为若干个IMF之和,然后分别对每个 IMF进行Hilbert变换后得到信和号的瞬时幅值和瞬时频率,就可以得到信和号的 Hilbert谱。Hilbert-Huang变换是一种具有自适应能力的新的时频分析方法,它 能够根据信号的局部时变特征自适应地进行时频分解,避免了人为因素的影响,同 时克服了传统傅里叶变换中用无意义的谐波分量来表... |

### se029 用这个评测集评价 RAG 系统时，context recall 应该关注什么？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | evaluation\README.md | evaluation_framework | # evaluation 评测层。用于检索指标、答案指标、图谱指标、人工评估、消融实验和显著性检验。 ## 当前评测集 - `system_eval_questions.jsonl`：30 题小型系统评测集，覆盖普通 RAG、OCR 风险、GraphRAG/知识图谱、结构化数据和评测方法。 - `scripts/run_system_evaluation.... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | h,Mette AAS ONE A CREAR TREAT 机没计)MORCATAA.HOF 1939 SEAL TED AULA AM (9,ARR SHR C—O EARLIER TIS 中，MTSE A,BA MAA«HEI(Vladimie Pavlee- ka),SAA RIE CLR DALES SANE,SAT DAS 司，估认为讲斯罗普这个... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\11_f9ae274e182b\document.txt | ocr_text_cleaned | 度模糊数越接近于1时,则重要性越高;反之,重要性越低。从而每 一评价属性都存在一个合适的评价模糊数,将其写成矩阵的形式即得评价项目模 糊评价矩阵,即 式中,为待评价功能属性数;zz为每一个评价属性的评价内容数(见表4-15),假 设系统的可靠性项目的评价内容数为6,维修性项目的评价内容数为3,可监测性 项目的评价内容数为4,经济性项目的评价内容数为4;方为... |

### se030 最后汇报中，为什么要同时展示成功案例和失败案例？

- Category: `evaluation_concept_gap`
- Action: 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。

| Method | Source | Scope | Top preview |
| --- | --- | --- | --- |
| keyword | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\12_703d154d523b\document.txt | ocr_text_cleaned | 动机研制与制造能力的整 合，许多桔索资料的半失，接触关键当事人和相关材料的不再 可能。本书手稿中的主体部分是一手及二手研究资料的结合， 包括一些个人的访谈以及一些口束历史。我们尽可能的去验证 这些回忆的真实性，但是仍然有一些情况可能与事实有出入- 我们希望我们的工作能为后人描奈引玉，促进这方面历史研究 的进一步发展。 当你回顾喷气发动机过去60年的发展历史... |
| dense_hashing | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\08_530bf8fe4384\document.txt | ocr_text_cleaned | 通信协议软件等组成. 1过程处理站 DCS系统中，控制站作为一个完整的计算机，它的主要1/0设备为现场的输入、输出处理设备以 及过程给入/输出〈PI/O)，包括信号变换与信号调理，A/D、D/A转换。控制站是整个DCS的基础， 它的可靠性和安全竹最为重要，死机和控制失灵的现象是绝对不允许的，而且袍余、掉电保护、搞二 抗、构成防爆系统等方面都应很有效和可靠，... |
| hybrid_rrf | data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt | ocr_text_cleaned | 纸。后来又有人进一步的研究'”'，进一步证实的确烟粒子在没到达测 烟仪器设备之前，在取样管线内有相当数量黏留在取样管的内壁上。他导出一个经验方 程，表示从取样管线出来的颗粒与进入取样管线的颗粒之比wm与其他参数，如取样管 线长度、取样管内径、取样管内样气流速的关系 n/n,=exp[—(1.05 x 1O“V+2.27 x103)ZZACDTY)](15-... |
