# GraphRAG 同题子集评测报告

## 一句话结论

60 题评测集中有 10 题显式标注需要 GraphRAG context/global；这些题应作为下一轮 GraphRAG local/global 同题实测的固定子集。

## 边界声明

本报告识别 GraphRAG 同题子集和当前文本 baseline 覆盖情况，不代表完整 GraphRAG 在线问答已优于 baseline。

## 子集统计

- 总题数：60
- GraphRAG 子集题数：10
- context 题数：8
- global 题数：4
- 当前文本 baseline 最优覆盖率均值：0.633333
- 优先补 GraphRAG 实测案例：6
- Graph evidence source: `docs/project_deliverables/06_四本书KG工具跑通演示/triples.csv` (240 base triples)
- manual evidence supplement: `docs/challenge_cup/reproducibility/graphrag_manual_evidence_supplement.csv` (5 triples)
- Graph evidence total triples: 245
- Graph evidence supported / partial / missing: 10 / 0 / 0

## Graph evidence coverage audit

Graph evidence coverage audits triples.csv keyword support; it is not a completed GraphRAG answer win-rate.
该审计只检查当前 triples.csv 对 GraphRAG 同题关键词的三元组覆盖，不代表完整 GraphRAG 在线问答已优于 baseline。

## 案例表

| ID | Graph mode | Best baseline | Baseline coverage | Graph evidence coverage | Graph evidence status | Question | Recommendation |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| cc032 | graphrag_context | keyword | 0.333333 | 1.0 | supported | 本项目为什么不能只说自己是一个普通问答页面？ | Prioritize local graph evidence because current text retrieval does not cover enough expected evidence. |
| cc033 | graphrag_global | keyword | 0.666667 | 0.833333 | supported | GraphRAG 在动力装备资料中适合解决哪一类普通 RAG 不稳定的问题？ | Use community/global summaries and compare against keyword/hybrid on cross-document synthesis. |
| cc034 | graphrag_context | keyword | 0.833333 | 0.666667 | supported | 为什么三元组必须绑定 evidence 才能用于可信问答？ | Keep as GraphRAG support case: text baseline is usable, but graph relations can improve explanation structure. |
| cc035 | graphrag_context | keyword | 1.0 | 1.0 | supported | 当前知识图谱 POC 的人工评审结果能证明什么，不能证明什么？ | Keep as GraphRAG support case: text baseline is usable, but graph relations can improve explanation structure. |
| cc039 | graphrag_context | keyword | 0.833333 | 0.5 | supported | 动力装备故障诊断类问题为什么需要同时返回可能原因和检查证据？ | Keep as GraphRAG support case: text baseline is usable, but graph relations can improve explanation structure. |
| cc040 | graphrag_context | keyword | 0.833333 | 0.666667 | supported | 燃气轮机运行监测中温度、压力和振动信号为什么常被放在一起分析？ | Keep as GraphRAG support case: text baseline is usable, but graph relations can improve explanation structure. |
| cc041 | graphrag_global | dense_hashing | 0.833333 | 1.0 | supported | 燃烧室相关问题为什么适合用图谱表达部件、现象和影响之间的关系？ | Use community/global summaries and compare against keyword/hybrid on cross-document synthesis. |
| cc043 | graphrag_global | dense_hashing | 0.166667 | 1.0 | supported | 如果 GraphRAG 没有在所有题上超过 keyword baseline，应该如何解释？ | Use community/global summaries and compare against keyword/hybrid on cross-document synthesis. |
| cc048 | graphrag_global | keyword | 0.5 | 1.0 | supported | GraphRAG global 更适合回答什么类型的问题？ | Use community/global summaries and compare against keyword/hybrid on cross-document synthesis. |
| cc056 | graphrag_context | keyword | 0.333333 | 1.0 | supported | 为什么知识图谱关系类型不能全部写成 related_to？ | Prioritize local graph evidence because current text retrieval does not cover enough expected evidence. |
