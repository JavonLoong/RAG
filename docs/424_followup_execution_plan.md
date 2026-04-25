# 424 会议后续任务执行计划

更新时间：2026-04-25 14:31

## 执行原则

- 先解决老师明确指出的工程可观测性问题，再补 Graph / GraphRAG 的最小验证样例。
- 前端只展示简洁状态，后端必须保留可定位的 `.log` 文件。
- 不把知识图谱误讲成“图片”，要把它讲成实体、关系、属性组成的数据结构。
- 不滥用兜底：如果没有调用 LLM，就明确标注为 rule-based/manual baseline，不把演示包装成已完成的智能抽取。
- 子 agent 不得调用孙 agent；主调度负责纠偏、验收和计划更新。

## 当前任务看板

| 模块 | 任务 | 负责人 | 状态 | 验收标准 |
| --- | --- | --- | --- | --- |
| 计划文档 | 建立本执行计划并持续更新 | 主调度 | 进行中 | 文档中能看到任务、负责人、状态、验收标准 |
| 可观测性 | 复核上传、处理、入库、统计、检索日志是否可定位 | 主调度 | 已完成 | 失败时能找到日志文件、阶段耗时、异常堆栈 |
| 调研网页 | `research_outline.html` 改成给老师看的后续计划 | Turing / gpt-5.5 xhigh | 已完成 | 页面强调当前情况、交付物、时间安排、待确认问题 |
| 概念解释 | `explainer.html` 加强知识图谱、GraphRAG、LLM、token、POC 解释 | Turing / gpt-5.5 xhigh | 已完成 | 卡片可点击展开或翻面，解释清楚常见卡点 |
| 三线演示 | `kg_demo.html` 展示 Microsoft GraphRAG、Neo4j、LlamaIndex/LangChain 三条线 | Turing / gpt-5.5 xhigh | 已完成 | 不混成“谁最好”，而是说明各自适合验证什么 |
| KG POC | 新增最小实体关系抽取样例、schema、三元组、人工评审、图谱 HTML | Turing / gpt-5.5 xhigh | 已完成 | 文件齐全，明确标注 baseline 性质 |
| 审核 | 使用 gpt-5.4 xhigh 审核实现和文档一致性 | Kierkegaard / gpt-5.4 xhigh | 已完成 | 审核无阻塞问题，确认可以收口 |
| 验证 | 运行后端测试、HTML/文件存在性检查、入口导入检查 | 主调度 | 已完成 | 测试通过，关键文件可打开 |

## 本轮交付物

- `docs/424_followup_execution_plan.md`：本执行计划。
- `docs/graphrag_research_pack/research_outline.html`：给老师看的后续计划页。
- `docs/graphrag_research_pack/explainer.html`：给自己和现场答疑用的概念解释页。
- `docs/graphrag_research_pack/kg_demo.html`：三条工具线对比演示页。
- `kg_pipeline/poc/`：最小知识图谱构建 POC 材料。

## 进度日志

- 03:35：建立执行计划；已派出执行子 agent Turing，模型为 gpt-5.5，reasoning effort 为 xhigh，并禁止调用孙 agent。
- 03:43：可观测性复核发现 `/api/benchmark` 尚未返回日志入口；已补压测阶段日志和前端“详细日志”链接，等待测试验证。
- 03:47：后端回归通过：`api_server/current_console/chroma_rag_poc/tests/test_pipeline.py -q`，结果 `10 passed`。
- 03:51：执行子 agent Turing 完成研究包和 `kg_pipeline/poc/` 最小样例交付，进入主调度验收和 gpt-5.4 xhigh 审核。
- 04:00：本地验收通过：POC 为 8 类实体、9 类关系、14 条三元组、14 条人工评审；HTML 内联脚本解析通过；根目录测试通过；`/api/benchmark` 返回 `log_file` 且日志包含 `benchmark_start` 与 `benchmark_result`。
- 14:20：审核子 agent Kierkegaard 完成 gpt-5.4 xhigh 只读审核，无阻塞问题；按审核建议补充 `/api/benchmark` API 级日志测试，后端回归结果 `11 passed`。
- 14:24：启动 Git 同步任务。当前本地只发现一个 `origin` 远端，指向自建 Git 服务/疑似 GitLab；暂未发现 GitHub remote。已派出 gpt-5.5 xhigh 子 agent 做只读同步风险复核，主调度准备本地提交并推送到现有远端。
- 14:29：已执行 `git fetch origin`，当前分支与 `origin/jiwenlong/vectorize-pipeline` 无 ahead/behind 分叉；准备暂存全部迁移与本轮实现。
- 14:31：gpt-5.5 xhigh 执行复核确认暂存区主要是目录迁移与本轮实现，无运行时缓存/日志误入；GitHub 同步因缺少 remote 继续阻塞。

## Git 同步看板

| 事项 | 状态 | 说明 |
| --- | --- | --- |
| 远端确认 | 已完成 | 已发现 `origin`；未发现 GitHub remote |
| 提交前复核 | 已完成 | 子 agent Chandrasekhar / gpt-5.5 xhigh 只读检查，无阻塞 |
| 本地提交 | 进行中 | 暂存区已排除 pyc、日志、Chroma SQLite、uploads 运行数据 |
| 推送 GitLab/Origin | 待开始 | 推送当前分支 `jiwenlong/vectorize-pipeline` |
| GitHub 同步 | 阻塞待确认 | 本地没有 GitHub remote，需要仓库地址或已配置 remote |
| 审核 | 待开始 | 推送后用 gpt-5.4 xhigh 做只读审核 |
