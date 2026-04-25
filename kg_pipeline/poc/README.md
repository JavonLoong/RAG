# 最小知识图谱 POC

本目录是会议要求的最小 graph construction 样例，主题是燃气轮机/设备故障文本。

重要说明：

- 当前版本是 `rule-based/manual baseline`。
- 没有调用 LLM。
- 没有跑通 Microsoft GraphRAG、Neo4j 或 LlamaIndex/LangChain。
- 目标是让老师能检查“文本、schema、三元组、人工评审、图谱展示”这一条链路是否合理。

## 文件清单

- `sample_text.md`：一段模拟燃气轮机故障文本，包含运行记录、检修记录、技术手册片段。
- `schema.json`：最小实体类型、关系类型、属性字段和评审字段定义。
- `triples.json`：三元组 JSON，带证据、置信度、评审状态。
- `triples.csv`：同一组三元组的 CSV 版本，方便放进表格或导入工具。
- `manual_review.csv`：人工评审表，逐条标注通过、待讨论或不通过。
- `graph_demo.html`：可直接打开的轻量图谱演示页面。

## 当前结论

这个 POC 只能证明最小流程可展示：

```text
样例文本 -> schema -> 三元组 -> 人工检查 -> 轻量可视化
```

它还不能证明：

- LLM 自动抽取效果已经可用。
- 完整 GraphRAG 问答系统已经跑通。
- Neo4j 图数据库已经部署。
- 该 schema 已适合真实生产数据。

## 下一步可选验证

1. 用同一段 `sample_text.md` 让 LLM 按 `schema.json` 抽取三元组。
2. 把 LLM 输出和 `triples.json` 这个人工/规则基线做差异对比。
3. 若老师确认需要落库，再把通过评审的关系转成 Neo4j 节点和边。
4. 若老师确认先做问答，再把通过评审的关系作为 GraphRAG 检索上下文。
