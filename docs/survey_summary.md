# RAG / GraphRAG 技术调研摘要

更新时间：2026-06-01

本文围绕普通 RAG、GraphRAG、知识图谱注入和维护类智能体四条线整理核心论文。目标不是单纯复述论文，而是明确它们和当前“动力装备知识库”项目的关系：我们已经有 OCR 文本、JSON 标注数据、ChromaDB 入库、基础检索、GraphRAG POC 和可视化页面，下一步需要把这些工程成果转化为稳定的研究路线。

## 1. 总体结论

普通 RAG 的核心价值是把外部文档作为可检索记忆，让大模型回答时不只依赖参数中的通用知识。它适合处理“答案主要存在于若干文本片段中”的问题，例如定义、参数说明、故障描述、操作步骤。Lewis et al. 2020 奠定了 RAG 的基本范式：一个参数化生成模型负责回答，一个非参数化检索库负责提供证据。后来的 Gao et al. 2024 进一步把 RAG 拆成预检索、检索、后检索、生成和评估等模块，说明 RAG 不是单个算法，而是一套可调的工程流水线。

GraphRAG 不是把知识图谱画成一张图片，也不是简单地把普通 RAG 换成图数据库。它的关键是：先从文档中抽取实体、关系和证据，把文本里的关联显式结构化，再在检索阶段利用图结构扩展上下文。Microsoft GraphRAG 的代表性工作把这个思路落到“局部实体关系”和“全局社区摘要”两个层面：局部问题可以围绕实体和关系找证据，全局问题可以先聚合社区摘要再生成答案。GraphRAG 的优势主要出现在跨文档、跨实体、跨主题的问题上；如果只是问单段文本里的事实，普通 RAG 往往更简单、更稳定。

知识图谱注入类方法，例如 Liu et al. 的 K-BERT，说明结构化知识可以改善语言模型对实体和关系的利用方式。但这类方法更偏模型训练或输入增强，和我们现在的工程目标不同。我们目前不是要重新训练模型，而是要在外部构建“可检索、可审查、可维护”的知识结构。因此，K-BERT 对我们的启发主要是：知识图谱必须控制噪声，实体关系不能无限扩张，否则引入的知识会干扰模型。

PARAM 这类维护智能体工作更接近我们的应用场景。它把机械维护数据、手册、向量检索、Web 检索和 LLM 推荐结合起来，面向的是“从异常检测走向可执行维护建议”。这和我们的动力装备知识库方向高度相关：我们的材料不是开放百科，而是燃气轮机、燃烧室、部件、参数、故障和维修知识。最终系统也不应该只回答“是什么”，还要能回答“为什么可能故障、应该查哪里、证据来自哪里”。

## 2. 论文与方法梳理

| 文献 | 核心问题 | 方法特点 | 对本项目的启发 |
|---|---|---|---|
| Lewis et al. 2020, RAG | 大模型参数知识难更新、难追溯 | 检索器找外部文档，生成器基于检索结果回答 | 普通 RAG 是必须先做好的 baseline |
| Gao et al. 2024, RAG Survey | RAG 工程环节复杂，缺少统一框架 | 总结索引、检索、重排、生成、评估等模块 | 我们要把 chunk、embedding、reranker、评估拆开记录 |
| Edge et al. 2024, Microsoft GraphRAG | 长文档/大语料的全局理解困难 | 抽取实体关系，做社区检测和社区摘要 | GraphRAG 的重点是 construction + community summary |
| Zhang et al. 2025 / Han et al. 2025, GraphRAG 综述与比较 | GraphRAG 是否一定优于 RAG | 梳理图检索类型，并比较 RAG 与 GraphRAG 适用场景 | 不能默认 GraphRAG 更好，要做对比实验 |
| Liu et al. 2020, K-BERT | 语言模型如何利用知识图谱 | 把知识图谱三元组注入输入，并控制可见性 | 关系和证据需要约束，避免知识噪声 |
| Harbola & Purwar 2025, PARAM | 工业维护如何从检测走向建议 | 振动数据 + 维护手册 + 向量检索 + 多智能体生成 | 我们项目可向“故障诊断与维护建议”靠拢 |

## 3. 普通 RAG：本项目必须先稳定的基线

Lewis et al. 2020 提出的 RAG 可以理解为“参数记忆 + 外部记忆”的组合。参数记忆是大模型内部已经学到的通用知识，外部记忆是可更新的文档索引。对于我们来说，外部记忆就是经过 OCR、文本筛选、chunk 切分后写入 ChromaDB 的动力装备资料。用户提问时，系统先检索相关 chunk，再把这些 chunk 作为上下文交给 LLM 生成回答。

这个思路非常适合当前阶段，因为我们已经有四个关键工程件：第一，OCR 后的燃气轮机资料；第二，公开书籍 JSON 和文本筛选逻辑；第三，ChromaDB 向量库；第四，前端检索和 RAG 问答界面。普通 RAG 的任务是把这些东西稳定串起来。它应该回答的问题包括：检索能不能命中相关证据？LLM 是否只基于检索到的材料回答？回答里能不能保留来源和页码？如果这些问题还不稳定，直接做复杂 GraphRAG 会把问题掩盖掉。

Gao et al. 2024 的综述提醒我们，RAG 的质量不只取决于 LLM。chunk 的大小、overlap、embedding 模型、top-k、reranker、上下文压缩都会影响结果。当前项目里已经讨论过 chunk overlap 设为 5% 左右、加入 reranker 的方向。这是合理的：overlap 用于减少切块造成的上下文断裂，reranker 用于在初步检索结果中做二次排序。当前 hashing embedding 能证明流程跑通，但语义能力较弱；后续可以接 BGE-m3 或 Google embedding 做对比。

因此，普通 RAG 的阶段性目标应该是：固定一批代表性问题，分别记录 top-k 检索结果、证据命中情况、LLM 回答质量和失败原因。这样才能形成论文里的 baseline，而不是只展示一个能问答的页面。

## 4. GraphRAG：不是图片，而是结构化检索

GraphRAG 的核心不是“可视化图谱图片”，而是文档知识被整理成图结构。图谱图片只是展示层，真正有价值的是底层数据：实体、关系、属性、证据、来源、页码和置信度。以我们的项目为例，“燃气轮机”“燃烧室”“压气机”“异常振动”“温度场不均匀”都可能是实体；“HAS_COMPONENT”“HAS_PROBLEM”“HAS_PARAMETER”“CAUSES”“AFFECTS”这类是关系；每条关系都应该绑定 evidence，证明它不是模型凭空猜的。

Microsoft GraphRAG 的思路对我们最直接的启发是 construction。它先把文本转成实体和关系，再做社区检测和摘要，最后支持局部和全局两类问题。局部问题类似“某个故障可能和哪些部件有关”，全局问题类似“这批资料中燃烧室问题主要分为哪几类”。普通 RAG 对局部证据检索较强，但面对跨文档归纳时容易漏掉结构；GraphRAG 则希望通过图和社区摘要补上这一层。

但是，GraphRAG 不是免费收益。Han et al. 的 RAG vs GraphRAG 系统比较也提醒我们：图结构会增加构建成本、抽取误差、维护复杂度和参数选择难度。如果实体抽错、关系粒度失控、证据绑定不完整，GraphRAG 反而会产生更复杂的错误。因此我们不能简单说“用了 GraphRAG 就更高级”，而要在相同问题集上比较：普通 RAG 是否能答，GraphRAG 是否答得更完整，是否更可追溯，是否值得多出来的构图成本。

当前项目已经做过小范围 POC：JSON / OCR 文本块进入 chunk，按 schema 抽取三元组，绑定 evidence，再由人工判断关系准确性。这条路线是正确的。下一步不是先扩展成很大的图，而是先把 schema 和关系粒度稳定下来。关系太宽泛，例如全部变成 `related_to`，检索价值不大；关系太细，例如把每个中文谓语都翻译成英文关系，图谱会碎片化，也会浪费上下文。更合理的做法是先维护少量高频、可解释、和检索目标相关的关系类型，再根据失败案例迭代。

## 5. 知识注入与知识噪声

Liu et al. 的 K-BERT 不是 RAG 系统，但它对知识图谱项目有重要提醒：知识不是越多越好。K-BERT 的核心问题是，外部知识插入模型输入后可能破坏原句语义，也可能引入噪声。因此它设计了可见矩阵等机制，让模型在利用知识的同时尽量不被无关知识干扰。

这个思想放到我们的项目里，就是 schema、evidence 和人工评审的重要性。我们不能让 LLM 随便抽关系，也不能让图谱无限扩张。每条三元组至少要回答三个问题：实体是否真实来自文本？关系是否符合 schema？证据是否能支持这条关系？如果证据只说明两个概念同时出现，而没有说明它们之间的因果、组成或参数关系，就不能强行建边。

这也是为什么人工评审不是“多余步骤”。人工评审的作用不是替代模型，而是给模型抽取质量提供基准。后续如果设计 skill 或自动校验器，就可以拿人工判断结果做对比，看模型是否能自己发现错误关系、方向错误和证据不足。

## 6. PARAM 与动力装备维护场景

Harbola & Purwar 2025 的 PARAM 方向和我们的应用最接近。它关注工业机械维护，不只是把文档问答做出来，而是把状态数据、故障识别、维护手册检索和 LLM 推荐结合起来。论文中使用轴承振动频率等数据进行故障类型和严重程度判断，再让多智能体组件处理维护手册、向量检索和 Web 检索，最终生成结构化维护建议。

这对我们项目有两个启发。第一，动力装备知识库不应该只停留在“资料检索”。燃气轮机资料中包含大量部件、参数、故障、工况和维修知识，最终应该服务于“诊断和维护建议”。第二，RAG 和 GraphRAG 可以分工：普通 RAG 负责把原文证据找出来，GraphRAG 负责把部件、故障、参数之间的关系组织起来，LLM 负责在证据基础上生成建议。也就是说，研究主线可以从“能不能问答”推进到“能不能给出可追溯的故障分析链”。

不过 PARAM 也提示一个风险：维护建议属于高风险输出，不能只靠模型自由生成。我们的系统如果将来回答“应该怎么修”，必须保留证据、来源和不确定性说明。更稳妥的阶段目标是先做“证据型建议”：系统给出可能原因、需要检查的部件、相关参数和出处，而不是直接替代工程师做最终决策。

## 7. 和当前项目的对应关系

当前项目可以分成三层。第一层是数据层：OCR 文本、Label Studio JSON、公开书籍资料、文本筛选结果和 ChromaDB。第二层是检索层：chunk 切分、embedding、向量检索、reranker、GraphRAG 图检索。第三层是生成与评估层：LLM 基于证据回答、人工评审三元组、问题集测试、日志记录和失败分析。

目前已经完成的是数据入库和小规模 GraphRAG POC。更具体地说，最新 JSON 快照已经能经过筛选后进入 ChromaDB；OCR 质量较稳定的书籍可以作为公开测试数据；GraphRAG 侧已经有三元组、evidence 和可视化检查页；前端也能展示检索和问答。还没有完全完成的是：正式 embedding 对比、reranker 接入、Neo4j 或真正图数据库存储、GraphRAG 问答闭环、大规模质量评测。

因此，下一步建议不要直接追求“大而全”。应先做一个可发表实验雏形：以普通 RAG 为 baseline，以 GraphRAG 为结构增强方法，用同一批动力装备问题进行对比。对比指标包括检索命中率、证据可追溯性、回答完整性、幻觉率、耗时和构建成本。这样才能把工程成果变成论文论证。

## 8. 后续工作清单

1. 固定 20 到 50 个代表性问题，覆盖定义类、部件类、故障原因类、参数类、跨文档总结类问题。
2. 普通 RAG 侧完成 embedding 对比：当前 hashing、BGE-m3、Google embedding 至少比较两种。
3. 加入 reranker，记录加入前后 top-k 证据变化。
4. GraphRAG 侧先固定小 schema，不急着扩关系类型。
5. 每条三元组保留 evidence、来源页码和人工判断状态。
6. 做普通 RAG 与 GraphRAG 的同题对比，不只看答案是否好看，还看证据是否命中。
7. 记录失败案例：OCR 错误、chunk 切断、embedding 未命中、关系抽错、LLM 过度推断。
8. 把实验结果写入后续 RP / 论文方案，形成“为什么需要 GraphRAG”的证据。

## 参考文献

1. Lewis et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. arXiv:2005.11401. https://arxiv.org/abs/2005.11401
2. Gao et al. Retrieval-Augmented Generation for Large Language Models: A Survey. arXiv:2312.10997. https://arxiv.org/abs/2312.10997
3. Edge et al. From Local to Global: A Graph RAG Approach to Query-Focused Summarization. arXiv:2404.16130. https://arxiv.org/abs/2404.16130
4. Zhang et al. A Survey of Graph Retrieval-Augmented Generation for Customized Large Language Models. arXiv:2501.13958. https://arxiv.org/abs/2501.13958
5. Han et al. RAG vs. GraphRAG: A Systematic Evaluation and Key Insights. arXiv:2502.11371. https://arxiv.org/abs/2502.11371
6. Liu et al. K-BERT: Enabling Language Representation with Knowledge Graph. arXiv:1909.07606. https://arxiv.org/abs/1909.07606
7. Harbola and Purwar. Prescriptive Agents based on RAG for Automated Maintenance (PARAM). arXiv:2508.04714. https://arxiv.org/abs/2508.04714
