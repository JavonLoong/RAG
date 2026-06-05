# GraphRAG context-only QA demo

本报告把 GraphRAG 同题 supported 案例转成固定 context-only QA 快照：同时展示文本检索证据和 triples.csv 图谱关系证据，但不生成 LLM 答案。

- Boundary: This report is a context-only GraphRAG retrieval demo; it does not generate LLM answers or prove online answer win-rate.
- Graph source: `docs/project_deliverables/06_四本书KG工具跑通演示/triples.csv`
- Text baseline: `keyword` / `evaluation/reports/day3_retrieval_outputs_keyword_20260605_210540.jsonl`
- Selection policy: `supported_domain_graph_cases_first`
- Demo cases: 3 (cc039, cc040, cc041)

## Cases

| ID | Graph mode | Text evidence | Graph evidence | Context-only boundary |
| --- | --- | ---: | ---: | --- |
| cc039 | graphrag_context | 2 | 3 | 不生成 LLM 答案 |
| cc040 | graphrag_context | 2 | 3 | 不生成 LLM 答案 |
| cc041 | graphrag_global | 2 | 3 | 不生成 LLM 答案 |

## Retrieved Context Snapshots

### cc039 动力装备故障诊断类问题为什么需要同时返回可能原因和检查证据？

```text
# GraphRAG context-only QA demo

Question: 动力装备故障诊断类问题为什么需要同时返回可能原因和检查证据？

Context-only debug mode: no LLM answer was generated.

## Text retrieval evidence
[T1] data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\10_e461d0cc931e\document.txt score=59.09
喘振或超温 带动变速负荷的单轴燃气轮机和无论带动什么负荷(变速或恒速)的分轴燃气轮机， 在加载过程中出现器振或超温现象,其主要原因是加速过快引起的。当加速过程快到一定 程度时,过程线可能落入压气机喘振区,引起机组喘振,即使过程线未落入压气机器振区， *7936. ## Page 330 在机组不发生喘振的情况下还可能发生超温现象。因此,在加载过程中,应适当降低加载 的速度,按机组规定的时间来完成加载过程。 11.4.2.2带不足抽荷、 机组在额定转速下,带不足与大气温度和压力相对应的最大负荷,同时机组的效率也 有所下降。出现此故障现象的可能原因及处理办法如下， (1)排气温度达不到允许值,可...

[T2] data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\11_f9ae274e182b\document.txt score=57.64
C1)密封圈的平均寿命为5 192 h,从一开始的故障率就较高,需要定期更换， 在4000h的时候需要对密封圈进行检查,确定是和否更换。 (2)滤蕊出现的故障风险比较高,而由于集中在保养时更换,因此说明平时的 故障概率是较小的,但是集中保养时可能的故障通常已经积累到了一定程度。 (3)从表中可以看出,基于最大故障率和最低可靠性的剩余寿命在4 000 h以 内,实际上能用到8 000 h的较少,由于前置过滤器工作条件比过滤器差,4 000 h 以前的检查也是必要的。 8.4状态监测故障诊断与视情维护 该燃驱压缩机组测点布置如表8-7所示。 表8-7燃驱压缩机组测点列表 部件测点 进口压力,进口...

## Graph retrieval evidence
[G1] 燃烧室 --HAS_PROBLEM--> 熄火 source=先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR (金如山，索建秦著) (z-library.sk, 1lib.sk, z-lib.sk).pdf confidence=0.75
Evidence: 对军用发动机，要求在发射导弹时燃烧室吸和导弹燃烧尾气而不熄火，通常由模拟试验来检查

[G2] 燃气轮机 --HAS_COMPONENT--> 压气机 source=燃气轮机原理、结构与应用 上 (沈阳黎明航空发动机（集团）有限责任公司编著) (z-library.sk, 1lib.sk, z-lib.sk).pdf confidence=0.72
Evidence: 本书主要叙述了人燃气轮机及其组成部件一一压气机、燃烧室和透平的工作原理、设计特点及其试验、变工况性能和结构,以及调节控制联合循环和应用等

[G3] 燃气轮机 --HAS_PARAMETER--> 热效率 source=燃气轮机 (南京燃气轮机研究所编) (z-library.sk, 1lib.sk, z-lib.sk).pdf confidence=0.79
Evidence: 随着技术进步和发展，燃气轮机越来越多地为人们所揭示和了解，它不但具有重量轻、体积小、启动快、运行维护方便、便于集中控制、少用水或不用水的优点，而且随着热效率不断提高和采用燃气-蒸汽联合循环的方式运行，联合循环发电装置的热效率已超过大功率高参数火电机组的水平
```

### cc040 燃气轮机运行监测中温度、压力和振动信号为什么常被放在一起分析？

```text
# GraphRAG context-only QA demo

Question: 燃气轮机运行监测中温度、压力和振动信号为什么常被放在一起分析？

Context-only debug mode: no LLM answer was generated.

## Text retrieval evidence
[T1] data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\07_b1a5f133347e\document.txt score=98.39
烟气轮机、风机等设备，开展了转子在线运行监测与故障诊浙机理及治理措施领域的工 作,取得了显著的经济效益 振动问题是回转机械运行中最主要的问题，拔动信号包含了丰富的机机运行状态信息并易于在线条 集和诊断。振动分析方法是最主要的故障诊断方法，可对故障类型作分析判断。对直气轮机的故障监测 与诊断对象主要是回转机械的核心部件转子及组件，如轴颈的振动及支撑轴承，还有回转机械运行中所 产生的多种参数变化，如咖声、力、扭短、压力、温度、功率.电流、位移等，这些信息反映机器状态 变化的信号均有各自的特点。通过监测这些信息来获取机组运行中稳坊、咀态过程参数，基于机器的下 障机理，从中提取故障特征，经周密的分析...

[T2] data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\11_f9ae274e182b\document.txt score=77.76
障类型的信号特征,然后根据这个信 号特征查找出振动类型及振动源。再结合RCM的方法,即可给出合理的维护建 综上所述,状态监测是结构强度故障中主要的维护方法,将状态监测所得的故 障征兆与FMEA表格结合进行分析可以给出有效的维护策略。 6.4燃气轮机结构强度故障诊断 旋转机械振动测试的主要对象是一个转动部件一一转子或转轴,在进行振动 测量和信和号分析时,也总是将振动与转动密切结合起来,以给出整个转子运动的某 些特征。大多数振动故障是与转子直接相关的,而且当这些故障出现时,转子振动 状态的变化要比非转动部件的振动变化敏感得多,因此,直接测量转子的振动状态 能够获得更多的有关故障的信息。因此燃气轮...

## Graph retrieval evidence
[G1] 燃烧室 --HAS_FUNCTION--> 将化学能〈燃油加空气)转化为燃烧产物和剩余的未燃空气的热能《温度升高) source=先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR (金如山，索建秦著) (z-library.sk, 1lib.sk, z-lib.sk).pdf confidence=0.74
Evidence: 燃烧室的作用是将化学能〈燃油加空气)转化为燃烧产物和剩余的未燃空气的热能《温度升高)

[G2] 燃烧室 --HAS_PARAMETER--> 压力损失 source=先进燃气轮机燃烧室=ADVANCED GAS TURBINE COMBUSTOR (金如山，索建秦著) (z-library.sk, 1lib.sk, z-lib.sk).pdf confidence=0.76
Evidence: 灼烧室工况复杂，其研究内容涉及气体动力学、燃烧学、化学动力学、热力学、传热学、排放污染控制、声学等多个学科和领域发动机对燃烧室的基本要求是燃烧效率高、压力损失小、重量轻、寿命长、污染排放低，另外燃烧室还要满足贫油炸火边界高空点火、出口温度分布、结构、强度、寿命、维护等方面的要求

[G3] 燃气轮机 --HAS_COMPONENT--> 压气机 source=燃气轮机原理、结构与应用 上 (沈阳黎明航空发动机（集团）有限责任公司编著) (z-library.sk, 1lib.sk, z-lib.sk).pdf confidence=0.72
Evidence: 此外,书中注意跟踪当今燃气轮机的新技术成就,介绍了先进的大功率燃气轮机和联合循环,新的航机改型机组,与高速发电机设计成整体的微型燃气轮机,压气机的可控扩压叶型,单轴燃气轮机型式的压气机全尺寸性能试验方法,干式低污染排放燃烧室,透平叶片的蒸汽闭环冷却和高效率的弯扭叶片,刷子气封,MARK$V控制系统,新的热力循环,以及燃
```

### cc041 燃烧室相关问题为什么适合用图谱表达部件、现象和影响之间的关系？

```text
# GraphRAG context-only QA demo

Question: 燃烧室相关问题为什么适合用图谱表达部件、现象和影响之间的关系？

Context-only debug mode: no LLM answer was generated.

## Text retrieval evidence
[T1] data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\01_422e6d6e9786\document.txt score=67.46
1 Pao Pe 9,Ra. Pa Py TPO ORE但- 在由>1时，要另外计算。 (2)平均光束长aa。对燃气轮机构烧室，最常用的如下。 ## Page 368 对单管燃烧室 对环形燃烧室 Sh ie Py Re 式中:五一一环形火焰简环高。 (3)7,的计算需要燃烧区的FAR.和效率 式中:AT7.一一燃烧室压力、进口温度、FAR.下的理论温升。 7>99%(或者最终的燃烧效率)。 以下讨论为什么方程(12-8)不对，应该是什么? 吸收系数无论如何不能大于1。问题出在哪里?这里有两个方面的问题。 (1)at=(Ze)，指数1.5是一个特定情况，普遍的情况应该是 g wl é,了 的书...

[T2] data_pipeline\ocr_processing_stages\ocr_text_cleaned\tsinghua_gas_turbine_books\03_8262abdfa4ad\document.txt score=61.54
上降低污染物排 ik, 本章主要分为6个部分: (1)污染排放相关问题及已制定的标准的概述; (2)污染物生成机理和降低传统燃气涡轮发动机污染物排放的方法 《3)可变几何结构和分级侈烧在通过控制火焰温度降低排放方面的应| (4)干低氨氧化物(NO,)排放和超低氨氧化物(NO,)排放燃烧室设计的基本方 (5)实现超低氨氧化物〈N0.)排放的方法，包括富油燃烧-Fe-贫油燃烧 《CRQL)二烧室和催化堪烧室; (6)氨氧化物(NO,)排放和一氧化碳(CO)排放之间的关系。 关于控制排放的新方法和生物质燃料在燃气涡轮发动机中的应用将在第10章进行 WE Site, 9.2，相关问题 航室发动机的排...

## Graph retrieval evidence
[G1] 燃气轮机 --HAS_COMPONENT--> 压气机 source=燃气轮机原理、结构与应用 上 (沈阳黎明航空发动机（集团）有限责任公司编著) (z-library.sk, 1lib.sk, z-lib.sk).pdf confidence=0.72
Evidence: 本书主要叙述了人燃气轮机及其组成部件一一压气机、燃烧室和透平的工作原理、设计特点及其试验、变工况性能和结构,以及调节控制联合循环和应用等

[G2] 压气机 --HAS_COMPONENT--> 涡轮 source=燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf confidence=0.8
Evidence: 中文版序燃气涌轮发动机主灼烧室是洪气涡轮发动机核心机的主要部件之一，将压气机压缩后的空气与江油充分混合、燃烧，将燃料中的化学能转化为热能

[G3] 压气机 --HAS_COMPONENT--> 涡轮 source=燃气涡轮发动机燃烧 第3版 (（英）A.H.勒菲沃（Arthur etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf confidence=0.8
Evidence: 中文版序燃气涌轮发动机主灼烧室是洪气涡轮发动机核心机的主要部件之一，将压气机压缩后的空气与江油充分混合、燃烧，将燃料中的化学能转化为热能
```
