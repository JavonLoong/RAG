# GraphRAG 调研交付包

这个文件夹现在按会议要求分成三层，不再把所有内容混成“阅读顺序”：

- `research_outline.html`：给老师看的后续计划。重点是当前情况、下次交付物、补进度时间表、希望老师确认的问题。
- `explainer.html`：概念解释页。解释知识图谱不是图片、Graph 与 GraphRAG 的关系，以及 token、POC、LLM、schema、chunk、三元组等易卡概念。
- `kg_demo.html`：三条工具线演示。分别说明 Microsoft GraphRAG、Neo4j GraphRAG、LlamaIndex/LangChain 是什么、适合验证什么，不做“谁最好”的简单结论。

## 最小 POC

本轮新增的最小知识图谱样例放在：

- `../../kg_pipeline/poc/README.md`
- `../../kg_pipeline/poc/sample_text.md`
- `../../kg_pipeline/poc/schema.json`
- `../../kg_pipeline/poc/triples.json`
- `../../kg_pipeline/poc/triples.csv`
- `../../kg_pipeline/poc/manual_review.csv`
- `../../kg_pipeline/poc/graph_demo.html`

这个 POC 明确标注为 `rule-based/manual baseline`：当前只用人工和简单规则整理样例，没有调用 LLM，也不假装已经跑通完整 GraphRAG。

## 汇报建议

下次会议建议按这个顺序讲：

1. 本周因为期中考试，实际推进有限。
2. 当前先聚焦 graph construction，也就是从领域文本抽实体关系并建一个可检查的图。
3. 展示 `kg_pipeline/poc/graph_demo.html`，说明样例文本、schema、三元组和人工评审表。
4. 请老师确认：是否先做 graph、是否可以先用公开/模拟文本、评估更看实体关系准确性还是最终问答效果、后续是否需要 Neo4j。

## 资料入口

原有调研资料仍保留在本文件夹中：

- `00_tonight_talk_track.md`
- `01_graphrag_research_brief.md`
- `02_tool_comparison.md`
- `03_poc_plan.md`
- `04_source_links.md`
- `papers/`
- `official_docs/`
