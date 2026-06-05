# GraphRAG answer benchmark

本报告把 10 道 GraphRAG 同题从 context-only 推进到答案级覆盖对照：使用固定参考答案、expected evidence keywords、文本 baseline 覆盖率和 triples.csv 图谱证据覆盖率做确定性离线评测。

- Boundary: This is a deterministic offline answer benchmark over the fixed GraphRAG subset; it does not claim online LLM answer win-rate or that GraphRAG beats every baseline question.
- LLM answer generated: `False`
- Benchmark mode: deterministic offline reference keyword coverage
- 10 道 GraphRAG 同题：10
- Graph supported / partial / missing: 10 / 0 / 0
- P0 missing 已补证: `True`
- Best baseline average coverage: 0.633333
- GraphRAG evidence average coverage: 0.866667
- All fixed GraphRAG evidence gaps closed: `True`
- 结论：不宣称 GraphRAG 全面优于 baseline；本报告只证明固定 GraphRAG 子集的本地证据覆盖，不证明在线 LLM answer win-rate。

## 案例表

| ID | Graph mode | Best baseline | Baseline coverage | GraphRAG coverage | Status | Verdict | Question |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| cc032 | graphrag_context | keyword | 0.333333 | 1.0 | supported | graph_supported | 本项目为什么不能只说自己是一个普通问答页面？ |
| cc033 | graphrag_global | keyword | 0.666667 | 0.833333 | supported | graph_supported | GraphRAG 在动力装备资料中适合解决哪一类普通 RAG 不稳定的问题？ |
| cc034 | graphrag_context | keyword | 0.833333 | 0.666667 | supported | graph_supported | 为什么三元组必须绑定 evidence 才能用于可信问答？ |
| cc035 | graphrag_context | keyword | 1.0 | 1.0 | supported | graph_supported | 当前知识图谱 POC 的人工评审结果能证明什么，不能证明什么？ |
| cc039 | graphrag_context | keyword | 0.833333 | 0.5 | supported | graph_supported | 动力装备故障诊断类问题为什么需要同时返回可能原因和检查证据？ |
| cc040 | graphrag_context | keyword | 0.833333 | 0.666667 | supported | graph_supported | 燃气轮机运行监测中温度、压力和振动信号为什么常被放在一起分析？ |
| cc041 | graphrag_global | dense_hashing | 0.833333 | 1.0 | supported | graph_supported | 燃烧室相关问题为什么适合用图谱表达部件、现象和影响之间的关系？ |
| cc043 | graphrag_global | dense_hashing | 0.166667 | 1.0 | supported | graph_supported | 如果 GraphRAG 没有在所有题上超过 keyword baseline，应该如何解释？ |
| cc048 | graphrag_global | keyword | 0.5 | 1.0 | supported | graph_supported | GraphRAG global 更适合回答什么类型的问题？ |
| cc056 | graphrag_context | keyword | 0.333333 | 1.0 | supported | graph_supported | 为什么知识图谱关系类型不能全部写成 related_to？ |

## All fixed GraphRAG evidence gaps closed

固定 GraphRAG 同题子集当前没有 partial/missing 本地证据缺口；该结论仍限于离线关键词覆盖审计，不代表在线 LLM answer win-rate。

## Boundary

This is a deterministic offline answer benchmark over the fixed GraphRAG subset; it does not claim online LLM answer win-rate or that GraphRAG beats every baseline question.
