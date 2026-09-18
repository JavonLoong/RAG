# Day 4 Failure Case Analysis

- Generated at: 2026-06-04T01:22:58
- Day 3 comparison: `D:\虚拟C盘\RAG\evaluation\reports\day3_retrieval_baseline_comparison_20260604_004434.json`
- Analyzed cases: 15

## Category Counts

| Category | Count |
| --- | ---: |
| evaluation_concept_gap | 4 |
| exact_number_fact | 1 |
| hybrid_dilution | 5 |
| partial_ranking_gap | 2 |
| structured_fact_routing | 2 |
| terminology_alias_gap | 1 |

## Method Snapshot

| Method | Question recall@K | Avg keyword coverage | Strong | Weak | Missed |
| --- | ---: | ---: | ---: | ---: | ---: |
| keyword | 0.833333 | 0.675000 | 20 | 5 | 5 |
| dense_hashing | 0.600000 | 0.425000 | 11 | 7 | 12 |
| hybrid_rrf | 0.800000 | 0.625000 | 19 | 5 | 6 |

## Cases

| ID | Type | Coverage keyword/dense/hybrid | Category | Reason | Action |
| --- | --- | --- | --- | --- | --- |
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
| se027 | structured_data_fact | 0.0/0.0/0.0 | structured_fact_routing | 结构化事实没有被专门路由到数据质量报告或字段清单，普通文本 chunk 对精确字段名/数值召回不足。 | 给 Goldwind/SCADA 类问题建立结构化摘要索引，保留 key-value、字段名、行列规模和报告路径。 |
| se028 | structured_data_fact | 0.0/0.0/0.0 | structured_fact_routing | 结构化事实没有被专门路由到数据质量报告或字段清单，普通文本 chunk 对精确字段名/数值召回不足。 | 给 Goldwind/SCADA 类问题建立结构化摘要索引，保留 key-value、字段名、行列规模和报告路径。 |
| se029 | evaluation_method | 0.25/0.0/0.0 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |
| se030 | evaluation_method | 0.5/0.25/0.5 | evaluation_concept_gap | 这是抽象评测概念题，证据分散在评测脚本、README 和汇报口径中，关键词不一定共现。 | 把评测指标定义整理成独立短文档或术语表，作为 evaluation_framework 的高质量检索源。 |

## Top Hit Diagnostics

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
