# GPT Pro 项目完整上下文说明

更新时间：2026-06-05  
仓库路径：`D:\虚拟C盘\RAG`  
当前目标：把现有 RAG/GraphRAG 原型优化成一个能够结项、可演示、可评测、可答辩，并具备冲击清华大学挑战杯特等奖潜力的完整项目。

> 给 GPT Pro 的使用方式：  
> 请把本文件完整发给 GPT Pro。要求它不要泛泛鼓励，而是以“清华挑战杯特等奖评委 + AI/RAG 科研导师 + 工程负责人”的标准，对项目进行方案优化、工程重构规划、材料设计和答辩攻防设计。

---

## 1. 一句话项目定位

本项目希望构建一个面向动力装备专业技术资料的可追溯 GraphRAG 知识工程与智能问答系统，通过 OCR 清洗、混合检索、知识图谱抽取、社区级全局检索和证据引用，提升专业技术文档问答的可靠性、可解释性和可复现性。

---

## 2. 项目目标

### 2.1 当前真实目标

不是简单做一个普通 RAG demo，而是把现有混乱原型优化成一个完整项目：

- 能用于课程/项目结项；
- 能现场演示；
- 能用真实数据和评测证明有效；
- 能形成技术报告、答辩 PPT、演示系统、代码仓库、实验结果；
- 能以“清华大学挑战杯特等奖候选项目”的标准打磨叙事、创新点、工程质量和评测证据。

### 2.2 建议项目名

可选：

1. `面向动力装备技术文档的可追溯 GraphRAG 知识工程与智能问答系统`
2. `面向复杂工程文档的知识图谱增强检索与可信问答系统`
3. `动力装备领域知识图谱增强 RAG 系统及其可追溯问答方法`

建议使用第 1 个，领域明确、技术明确、交付形态明确。

---

## 3. 适合挑战杯的项目类别判断

更适合申报为：科技发明制作类。

理由：

- 项目最终应呈现为一个可运行系统，而不仅是论文；
- 有数据处理、检索引擎、知识图谱、问答系统、评测和前端演示；
- 可以展示工程应用价值：复杂工程资料的检索、问答、证据追溯和辅助知识管理；
- 如果只按自然科学论文类申报，目前理论创新还不够强，容易被质疑只是工程集成。

但技术报告中仍然需要学术化表达：

- 问题定义；
- 方法框架；
- 模块设计；
- 指标评测；
- 消融实验；
- 错误分析；
- 局限性。

---

## 4. 挑战杯评审导向提醒

公开资料中，清华挑战杯多次强调：

- 学术规范；
- 成果表述严谨；
- 交叉学科；
- 项目墙报/现场问辩；
- 科创引领和实际应用价值。

全国挑战杯章程中也强调优秀作品应体现较高学术理论水平、实际应用价值和创新意义。

参考链接：

- 清华第37届挑战杯终审报道：https://www.tsinghua.edu.cn/info/1181/35383.htm
- 清华第39届挑战杯终审报道：https://www.tsinghua.edu.cn/info/1175/82720.htm
- 挑战杯全国章程：https://www.tiaozhanbei.net/rules

因此，本项目不能只说“我做了 RAG”。必须证明：

- 真实问题重要；
- 方法比普通 RAG 更适合工程技术文档；
- 系统可以运行；
- 结果可以复现；
- 答案可以追溯；
- 评测能支持结论；
- 创新点不是包装出来的。

---

## 5. 当前仓库真实状态

### 5.1 当前分支

当前 Git 分支：

`feat/SOTA-graphrag-improvements`

### 5.2 工作区状态

工作区是脏的，存在大量未提交修改、删除和未跟踪文件。

重要提醒：

- 不要假设所有删除都是故意的；
- 不要贸然清理或 `git reset --hard`；
- 目前仓库里混有源码、交付材料、运行产物、截图、PPT、报告、历史资料和临时文件；
- 清理前必须先做资产盘点，区分“源码主线”“交付材料”“运行产物”“历史备份”“可删除临时文件”。

### 5.3 最大结构问题

这个仓库的核心问题不是“全是空文件”，而是边界混乱：

- 项目源码；
- OCR 中间产物；
- ChromaDB 运行数据；
- 课程/汇报交付包；
- GraphRAG 调研材料；
- 前端静态产物；
- 历史工作树或子模块；
- Codex 临时产物；
- node_modules；
- outputs；
- 截图文件；

全部混在同一个仓库视野里。

结果是：

- README 不可信，且部分中文乱码；
- 项目入口不清晰；
- 评委或合作者很难快速理解系统；
- 工程上难以复现；
- 很难说服别人这是一个成熟项目。

---

## 6. 当前项目已有能力

### 6.1 数据处理/OCR

已有：

- OCR 清洗脚本；
- OCR 质量审计报告；
- 多轮 OCR 处理产物；
- Label Studio JSON 解析；
- 文档清洗和分块；
- 公开书籍/工程资料 JSON 入库脚本。

相关目录：

- `data_pipeline/`
- `data_pipeline/reports/`
- `data_pipeline/prototype/power_rag_pipeline/`
- `scripts/clean_ocr_text.py`
- `scripts/ocr_scanned_pdfs.py`
- `scripts/audit_ocr_quality.py`
- `scripts/ingest_public_books_json_to_chroma.py`

问题：

- OCR 中间产物过多，和源码混在一起；
- 数据版本没有清晰编号；
- 还没有形成清楚的数据资产说明；
- 评测所用数据集和演示所用数据集需要固定。

### 6.2 向量检索和混合检索

已有：

- ChromaDB 入库；
- 基础语义检索；
- BM25/关键词检索；
- Hybrid/RRF 检索；
- reranker 模块；
- 检索 smoke test 和 baseline 脚本。

相关目录：

- `retrieval_engine/`
- `model_adapters/embedding.py`
- `model_adapters/reranker.py`
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/retrieval.py`
- `scripts/run_day3_retrieval_baselines.py`
- `scripts/run_retrieval_smoke_tests.py`

问题：

- API 主搜索路径是否完整接入 hybrid/rerank 仍需梳理；
- 检索评测需要更标准化；
- 需要固定 baseline：关键词、向量、hybrid、hybrid+rerank、GraphRAG。

### 6.3 知识图谱抽取与存储

已有：

- LLM 三元组抽取 pipeline；
- schema 约束；
- evidence 校验；
- `GraphStore` SQLite 存储；
- 知识图谱 POC；
- 三元组审核页面和图谱可视化材料。

相关目录：

- `kg_pipeline/`
- `kg_pipeline/llm_extraction/pipeline.py`
- `storage_layer/graph_store.py`
- `kg_pipeline/poc/`
- `docs/project_deliverables/05_知识图谱POC_三元组和人工判断/`

问题：

- 还没有形成稳定的“入库文档 chunk id -> 三元组 -> 图谱节点/边 -> 检索引用”的端到端 ID 链；
- LLM 抽取质量、错误率、人工审核一致性需要评测；
- 需要把图谱抽取变成可复现 pipeline，而不是一次性脚本结果。

### 6.4 GraphRAG

已有：

- 局部图检索；
- 社区检测；
- 社区摘要；
- 全局搜索；
- GraphRAG QA orchestration；
- 与普通检索结合的测试。

相关目录：

- `rag_orchestrator/graphrag_qa.py`
- `rag_orchestrator/global_search.py`
- `retrieval_engine/graph.py`
- `kg_pipeline/community_detection.py`
- `kg_pipeline/community_summary.py`
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_graphrag.py`

最近已修复：

- `global_searcher` 之前传入后默认不会运行，导致 GraphRAG 全局上下文断掉；
- 现在默认本地流程也会接入 community-level global context，除非 router 明确选择 `VECTOR_ONLY`。

问题：

- GraphRAG API 仍然更像调试接口，直接传 `graph_db_path`；
- 缺少 graph_id / collection_id 级别的数据源管理；
- 全局搜索、局部搜索、普通 RAG 的策略选择还需要产品化；
- 需要用评测证明 GraphRAG 在哪些问题上优于普通 RAG。

### 6.5 后端 API

当前主后端入口：

- `api_server/current_console/server.py`
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py`

当前 FastAPI 能力包括：

- 上传；
- 文件处理；
- 入库；
- stats；
- search；
- benchmark；
- logs；
- export；
- public books JSON ingest；
- GraphRAG community detect；
- GraphRAG summarize；
- GraphRAG global search；
- GraphRAG stats；
- communities list。

问题：

- `api.py` 仍然是约 1000 行单体模块；
- 路由、文件系统、日志、Chroma 操作、导出逻辑混在一起；
- 长耗时任务仍然同步执行；
- 缺少 job queue；
- 缺少统一错误响应；
- 缺少完善认证授权；
- `server.py` 当前仍绑定 `0.0.0.0`，如果不是本地演示需要谨慎；
- GraphRAG 路由还没有完全产品化。

已部分修复过的 P0：

- `api.py` 不再导入期创建 `app = create_app()`；
- 前端目录缺失时 `/` 返回 404，而不是 import 时 `StopIteration`；
- 默认 CORS 已限制到本地控制台来源；
- `public-books-json/ingest` 有路径白名单；
- GraphRAG db path 有 allowed roots 校验；
- 上传文件名和日志路径做了边界校验。

### 6.6 前端

相关目录：

- `frontend_app/current_console/`
- `frontend_app/current_console/index.html`
- `frontend_app/current_console/app.py`
- `frontend_app/current_console/assets/`

已有：

- 本地控制台前端；
- 上传、检索、展示等演示能力；
- 一些静态资产；
- OCR server 相关脚本。

问题：

- 前端是否真正围绕“挑战杯现场演示”设计还不够；
- 需要把第一屏改成评委能理解的系统界面，而不是普通工具页面；
- 需要有固定演示数据、固定演示问题、固定证据链展示；
- 需要有“普通 RAG vs Hybrid vs GraphRAG”的可视化对比。

### 6.7 评测

已有：

- `evaluation/`
- `evaluation/metrics.py`
- `evaluation/runner.py`
- `evaluation/system_eval_questions.jsonl`
- `evaluation/reports/`
- Day3 baseline comparison；
- Day4 failure analysis。

问题：

- 评测问题集和真实资料之间的对应关系需要固定；
- 指标体系需要更完整；
- 需要区分检索指标和问答指标；
- 需要做消融实验；
- 需要把失败案例转化为技术改进证据；
- 评测报告需要可以被评委快速读懂。

建议指标：

- Recall@k；
- MRR；
- nDCG；
- citation coverage；
- answer faithfulness；
- evidence exactness；
- entity/relation recall；
- GraphRAG 相比普通 RAG 的提升；
- latency；
- 构建成本。

---

## 7. 当前测试状态

最近一次验证结果：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```

结果：

```text
74 passed in 6.10s
```

API POC 测试：

```powershell
.\.venv\Scripts\python.exe -m pytest api_server/current_console/chroma_rag_poc/tests/test_pipeline.py -q
```

结果：

```text
19 passed, 1 warning in 116.79s
```

唯一警告：

- HuggingFace Hub 在 Windows 上 symlink cache 不可用，会退化为普通缓存；
- 这不是功能失败，但可能占用更多磁盘。

最近修复过的测试/功能问题：

1. GraphRAG 全局检索上下文没有默认接入；
2. LLM KG 抽取输出空 `valid_time` 字段破坏旧契约；
3. `data_pipeline/prototype/power_rag_pipeline/pipeline.py` 导入期替换 `sys.stdout`，导致 pytest 捕获模式崩溃。

---

## 8. 当前最严重问题清单

### P0：项目边界混乱

仓库现在不像一个清晰工程项目，更像多个阶段产物堆叠。

必须做：

- 建立 `src/` 或清晰模块边界；
- 固定主入口；
- 将运行产物和大型数据移出源码主线；
- 修复 README；
- 明确哪些是“演示数据”，哪些是“训练/评测/原始资料”，哪些是“历史产物”。

### P0：挑战杯叙事缺失

现在项目有功能，但没有清晰回答：

- 解决了什么重大问题？
- 为什么普通 RAG 不够？
- GraphRAG 的必要性在哪里？
- 与现有方法相比创新在哪里？
- 真实应用价值在哪里？
- 评测如何证明？
- 现场演示如何打动评委？

### P0：端到端闭环不够强

必须形成完整链条：

```text
原始工程资料
→ OCR/JSON 解析
→ 清洗与分块
→ 向量索引
→ LLM 三元组抽取
→ 图谱构建
→ 社区检测/摘要
→ Hybrid + GraphRAG 检索
→ LLM 证据约束回答
→ 引用追溯
→ 评测报告
→ 前端演示
```

### P1：API 单体化

`api.py` 仍然太大，应拆成：

```text
chroma_rag_poc/
  api_app.py
  routes/
    health.py
    frontend.py
    uploads.py
    ingest.py
    search.py
    stats.py
    export.py
    logs.py
    benchmark.py
    graphrag.py
  services/
    upload_service.py
    ingest_service.py
    search_service.py
    graph_service.py
    evaluation_service.py
  security/
    paths.py
    auth.py
```

### P1：评测证据不足

需要固定一个挑战杯评测集：

- 30-50 个真实问题；
- 每个问题有期望答案；
- 每个问题有证据来源；
- 区分事实型、因果型、流程型、对比型、综合型问题；
- 对比普通 RAG、BM25、Hybrid、GraphRAG；
- 形成图表。

### P1：演示系统不够“评委友好”

挑战杯现场演示不能只展示 API。

应展示：

- 文档入库进度；
- 知识图谱构建；
- 检索模式切换；
- 证据 chunk；
- 图谱路径；
- 社区摘要；
- 回答引用；
- 普通 RAG 和 GraphRAG 对比；
- 失败案例和改进。

---

## 9. 冲击特等奖需要补齐的 5 个核心闭环

### 闭环 1：数据可信闭环

输入：

- 真实动力装备技术资料；
- OCR 文本；
- Label Studio JSON；

处理：

- OCR 质量审计；
- 清洗；
- 分块；
- 元数据保留；

输出：

- 可复现实验数据集；
- 文档清单；
- 数据质量报告；

评委价值：

- 证明不是随便找文本做 demo；
- 证明数据工程可信。

### 闭环 2：检索增强闭环

输入：

- 固定问题集；
- 文档索引；

处理：

- BM25；
- Dense；
- Hybrid/RRF；
- rerank；

输出：

- Recall@k、MRR、nDCG；
- baseline comparison；

评委价值：

- 证明系统不是“套壳问答”；
- 证明检索层有优化。

### 闭环 3：知识图谱闭环

输入：

- 文档 chunk；

处理：

- LLM 三元组抽取；
- schema 校验；
- evidence 校验；
- 人工抽样审核；
- SQLite GraphStore；

输出：

- 实体/关系图；
- 抽取质量报告；
- 可视化图谱；

评委价值：

- 证明 GraphRAG 的图不是装饰；
- 证明知识结构可追溯。

### 闭环 4：GraphRAG 问答闭环

输入：

- 用户问题；

处理：

- query routing；
- text retrieval；
- graph retrieval；
- community global search；
- evidence constrained answer；

输出：

- 带引用答案；
- 图谱路径；
- 社区级上下文；

评委价值：

- 证明系统比普通 RAG 更适合复杂技术问题；
- 展示创新点。

### 闭环 5：现场演示和答辩闭环

输入：

- 3-5 个预设演示问题；

处理：

- 普通 RAG vs GraphRAG 对比；
- 展示证据链；
- 展示图谱路径；
- 展示失败案例修正；

输出：

- 前端演示；
- PPT；
- 技术报告；
- 评测图表；

评委价值：

- 让评委“一眼看懂项目价值”。

---

## 10. 推荐最终仓库结构

建议最终整理成：

```text
RAG/
  README.md
  pyproject.toml
  src/
    power_rag/
      data/
      retrieval/
      kg/
      graphrag/
      evaluation/
      api/
      services/
      schemas/
      security/
  apps/
    console/
      frontend/
      backend/
  datasets/
    README.md
    sample/
    eval/
  experiments/
    baselines/
    ablations/
    reports/
  docs/
    challenge_cup/
      申报书.md
      技术报告.md
      答辩PPT大纲.md
      演示脚本.md
      评委问答.md
    architecture/
    evaluation/
  scripts/
  tests/
    unit/
    integration/
    api/
    evaluation/
  artifacts/
    demo_outputs/
```

短期不一定真的全部迁移，但文档和主入口必须按这个逻辑展示。

---

## 11. 给 GPT Pro 的核心请求

请 GPT Pro 基于本文件输出：

1. 项目重新定位；
2. 特等奖差距分析；
3. 技术路线重构；
4. 工程整改路线；
5. 评测体系；
6. 消融实验设计；
7. 前端演示方案；
8. 结项材料清单；
9. 8 分钟答辩 PPT；
10. 评委 30 问；
11. 两周、四周、八周推进计划；
12. 哪些功能必须砍掉，哪些必须强化。

---

## 12. 建议直接发给 GPT Pro 的 Prompt

```text
你现在扮演三个角色：
1. 清华大学挑战杯特等奖评委；
2. AI/RAG/知识图谱方向的科研导师；
3. 能把混乱原型整理成可结项工程的技术负责人。

我会给你一个项目上下文文件。请你基于文件内容进行残酷、具体、可执行的方案优化。

我的目标不是做一个普通课程项目，而是把现有项目优化成一个完整、可信、可演示、可评测、可答辩、可结项，并具备冲击清华大学挑战杯特等奖潜力的项目。

请不要泛泛鼓励。请按以下结构输出：

A. 项目重新定位
- 最适合挑战杯的项目名称；
- 一句话、三句话、一分钟答辩稿；
- 适合科技发明制作类还是自然科学学术论文类。

B. 特等奖级别差距分析
按 0-10 分评价：
- 问题重要性；
- 技术创新性；
- 工程完整性；
- 实验与评测可信度；
- 可演示性；
- 应用价值；
- 答辩说服力；
- 材料完整度；
- 学术规范与可复现性。

C. 重构后的项目总方案
包括：
- 总体架构；
- 数据流；
- 模块边界；
- 核心算法路线；
- GraphRAG 与普通 RAG 的对比优势；
- 检索评测指标；
- 消融实验；
- 失败案例分析；
- 用户演示流程；
- 最终交付物清单。

D. 最小可获奖闭环
请告诉我时间有限时最应该完成的 5 个闭环。
每个闭环写：
- 输入；
- 处理流程；
- 输出；
- 可视化/演示方式；
- 评测指标；
- 答辩时怎么讲。

E. 工程整改路线
给出 2 周、4 周、8 周计划。
每个计划包括：
- 必做事项；
- 可放弃事项；
- 文件结构建议；
- 需要补的测试；
- 需要补的文档；
- 演示系统应该长什么样。

F. 挑战杯材料包
生成：
- 申报书大纲；
- 技术报告大纲；
- 8 分钟答辩 PPT 大纲；
- 现场演示脚本；
- 评委可能追问的 30 个问题及最佳回答方向；
- 项目创新点的保守版、进取版、冲奖版。

G. 风险清单
指出最可能被评委质疑的地方：
- 是否只是套壳 RAG；
- 是否有真实创新；
- 是否评测充分；
- 是否数据可靠；
- 是否工程可复现；
- 是否有应用场景；
并给出逐条补救方案。

请用严厉、具体、可执行的方式回答。所有建议都要能落到代码、实验、文档或答辩材料上。
```

---

## 13. 不希望 GPT Pro 做的事

请明确要求 GPT Pro 不要：

- 不要虚构已经完成的实验结果；
- 不要说“肯定能拿特等奖”；
- 不要把项目包装成已经成熟的工业系统；
- 不要只给营销话术；
- 不要只讲 RAG 常识；
- 不要忽略当前仓库混乱问题；
- 不要建议大规模重写而不保留已有测试和已有能力；
- 不要删除数据和交付材料，除非先做资产归档；
- 不要把 GraphRAG 说成万能，必须说明适用问题和局限。

---

## 14. 当前项目可以强调的真实亮点

可以强调：

- 不是纯聊天机器人，而是面向工程技术资料的知识工程系统；
- 已有 OCR、清洗、入库、检索、图谱、问答、评测、前端多个模块；
- 已有单元测试和 API 测试；
- 已开始做 GraphRAG，不只是普通向量 RAG；
- 有真实工程文档处理背景；
- 有失败案例分析和 baseline 对比材料；
- 有证据引用和可追溯方向；
- 有进一步产品化和科研化空间。

不要过度强调：

- “已经达到工业级”；
- “已经全面超过现有 RAG”；
- “已经具备特等奖水平”；
- “知识图谱已经完全可靠”。

更准确的说法：

> 当前项目已有较完整的技术雏形，但仍需通过数据闭环、评测闭环、工程收敛和答辩叙事，把它从功能堆叠打磨成一个可信的挑战杯项目。

---

## 15. 最应该让 GPT Pro 判断的问题

请 GPT Pro 重点判断：

1. 这个项目的挑战杯核心创新点到底应该怎么定？
2. GraphRAG 在这个项目里是否真的必要？
3. 哪些功能必须砍掉，否则会显得乱？
4. 哪些实验最能证明项目价值？
5. 哪些前端演示最容易打动评委？
6. 申报书里如何避免“套壳 RAG”的质疑？
7. 技术路线如何讲得既先进又诚实？
8. 如果只有两周，先做哪几件事？
9. 如果冲特等奖，必须补哪些硬证据？
10. 这个项目最可能死在评审哪一关？

---

## 16. 推荐下一步

第一步：

让 GPT Pro 先输出“特等奖差距诊断”和“2 周最小可获奖闭环”。

第二步：

不要马上全仓库重构。先固定：

- 项目名；
- 主线故事；
- 演示数据；
- 评测问题集；
- 3 个核心创新点；
- 5 个现场演示问题；
- 最终交付目录。

第三步：

再回到代码：

- 清理 README；
- 固定主启动命令；
- 固定 API 测试；
- 固定 eval 脚本；
- 打磨前端演示页面；
- 输出挑战杯材料包。

---

## 17. 当前可信结论

这个项目不是完全没救，也不是已经足够好。真实情况是：

- 有不少能工作的技术模块；
- 有测试支撑；
- 有 GraphRAG 方向；
- 有工程资料领域场景；
- 但仓库组织、项目叙事、评测证据和演示系统还达不到高水平竞赛要求。

如果目标只是结项，当前基础可以继续收敛。  
如果目标是清华挑战杯特等奖，必须把项目从“功能堆叠”升级为“问题清晰、方法可信、实验扎实、系统完整、表达锋利”的作品。

---

# 第二部分：给 GPT Pro 的扩展项目档案

下面内容用于让 GPT Pro 更完整地理解项目。请它不要只看前面的摘要，而要结合本扩展档案判断项目的真实工程状态、已有资产和差距。

---

## 18. 当前项目的真实主线与非主线

### 18.1 当前真实主线

如果必须从现在的仓库中抽出一条“能继续开发和结项”的主线，建议定义为：

```text
专业工程文档
→ OCR/JSON 解析与清洗
→ 文档 chunk 化
→ Chroma 向量索引
→ BM25/Hybrid/RRF 检索
→ LLM 三元组抽取
→ SQLite 知识图谱
→ 图检索 + 社区检测 + 社区摘要 + 全局搜索
→ GraphRAG 问答
→ 引用追溯
→ 评测报告
→ 前端演示
```

这条主线对应的核心代码目录是：

```text
api_server/current_console/chroma_rag_poc/
retrieval_engine/
rag_orchestrator/
kg_pipeline/
storage_layer/
model_adapters/
evaluation/
data_pipeline/prototype/power_rag_pipeline/
scripts/
frontend_app/current_console/
tests/
```

### 18.2 当前非主线但有价值的资产

这些不是主线源码，但对结项和挑战杯材料很有价值：

```text
docs/project_deliverables/
evaluation/reports/
data_pipeline/reports/
kg_pipeline/poc/
docs/project_deliverables/05_知识图谱POC_三元组和人工判断/
docs/project_deliverables/06_汇报材料_发群和组会/
docs/project_deliverables/06_四本书KG工具跑通演示/
```

它们可以支撑：

- 项目过程证明；
- 交付清单；
- PPT 材料；
- 失败案例；
- baseline 对比；
- 知识图谱演示；
- 现场答辩素材。

### 18.3 当前应隔离的内容

这些内容不应该出现在“评委第一眼看到的主仓库视野”里：

```text
node_modules/
outputs/
.pytest_cache/
codex-*.png
codex_*.md
codex-remote-control-keepalive.mjs
reset-codex-remote-control.ps1
main-uV0KCuhm.js
index.html  # 根目录下的大型前端构建产物，需要确认是否应归档
RAG_main_sync_worktree/  # Git 子模块/工作树引用
RAG_JSON_Files/  # 原始/临时 JSON 数据，需资产盘点
storage_layer/runtime/
```

处理原则：

- 不要直接删除；
- 先做资产盘点；
- 再分成 `archive/`、`datasets/`、`artifacts/`、`runtime/`、`external/`；
- 最终 README 只展示主线，不让评委被噪音淹没。

---

## 19. 后端 API 路由清单

当前 API 主体在：

```text
api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py
api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_graphrag.py
```

### 19.1 普通控制台 API

当前已有路由：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/` | 返回前端 index.html；前端缺失时返回 404 |
| GET | `/api/health` | 健康检查 |
| POST | `/api/upload` | 上传文档 |
| GET | `/api/uploads` | 查看上传文件和处理状态 |
| GET | `/api/logs` | 查看日志列表 |
| GET | `/api/logs/{filename}` | 查看单个日志 |
| DELETE | `/api/uploads/{filename}` | 删除单个上传文件 |
| POST | `/api/uploads/delete` | 批量删除上传文件，可选清理向量 |
| POST | `/api/process` | 处理已上传文件并入库 |
| POST | `/api/public-books-json/ingest` | 从白名单目录导入公开书籍 JSON |
| POST | `/api/ingest` | 直接上传 JSON payload 入库 |
| GET | `/api/stats` | 查看 ChromaDB 统计 |
| GET | `/api/search` | GET 搜索 |
| POST | `/api/search` | POST 搜索 |
| POST | `/api/benchmark` | Chroma 性能基准测试 |
| DELETE | `/api/collections/{name}` | 删除集合 |
| GET | `/api/export` | 导出整库 |
| GET | `/api/chroma/export` | 导出 Chroma DB |
| GET | `/api/export/{collection_name}` | 导出单集合 JSON |

### 19.2 GraphRAG API

当前已有路由：

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/graphrag/community/detect` | Leiden 社区检测 |
| POST | `/api/graphrag/community/summarize` | LLM 社区摘要 |
| POST | `/api/graphrag/search/global` | 基于社区摘要的全局搜索 |
| POST | `/api/graphrag/stats` | 图谱统计 |
| GET | `/api/graphrag/communities` | 查看社区及摘要 |

### 19.3 API 层当前问题

GPT Pro 应重点判断：

1. 哪些路由应该保留到最终演示系统；
2. 哪些只是开发调试接口；
3. 哪些需要隐藏或加认证；
4. 哪些需要改成后台任务；
5. 哪些需要统一错误格式；
6. GraphRAG 是否应该继续暴露 `graph_db_path`，还是改成 `graph_id` / `collection_id`；
7. 搜索 API 是否应该统一支持：

```text
mode = semantic | keyword | hybrid | hybrid_rerank | graphrag_local | graphrag_global | graphrag_hybrid
```

建议 GPT Pro 输出一份“最终答辩版 API 设计”，而不是只评价现状。

---

## 20. 核心 Python 模块职责

### 20.1 retrieval_engine

目录：

```text
retrieval_engine/
```

职责：

- 定义 `DocumentChunk`、`RetrievalResult`、`BaseRetriever`；
- 实现关键词检索；
- 实现 Hybrid 检索；
- 对接 Chroma 检索；
- 实现 SQLite 图检索。

关键文件：

```text
retrieval_engine/core.py
retrieval_engine/keyword.py
retrieval_engine/hybrid.py
retrieval_engine/chroma.py
retrieval_engine/graph.py
```

已有类：

- `DocumentChunk`
- `RetrievalResult`
- `BaseRetriever`
- `KeywordRetriever`
- `HybridRetriever`
- `ChromaRetriever`
- `SQLiteGraphRetriever`

当前价值：

- 可以支撑“检索策略可替换”的评测；
- 可以做普通 RAG、BM25、Hybrid、GraphRAG 的对照实验；
- 对挑战杯非常重要，因为能证明系统不是单一路线。

当前短板：

- API 主搜索路径是否完全用上这些抽象，需要继续核查；
- reranker 与检索主链路还需更清晰；
- 检索结果解释字段需要前端展示。

### 20.2 rag_orchestrator

目录：

```text
rag_orchestrator/
```

职责：

- GraphRAG 问答编排；
- query routing；
- 全局搜索；
- hallucination guard；
- 各种 adapter。

关键文件：

```text
rag_orchestrator/graphrag_qa.py
rag_orchestrator/global_search.py
rag_orchestrator/router.py
rag_orchestrator/hallucination_guard.py
rag_orchestrator/adapters.py
```

已有类：

- `GraphRagQAOrchestrator`
- `GraphRagQAResult`
- `EvidenceItem`
- `GlobalSearchOrchestrator`
- `GlobalSearchResult`
- `AdaptiveQueryRouter`
- `HallucinationGuard`

当前价值：

- 是项目区别于普通 RAG 的核心；
- 可以支撑“局部证据 + 图谱关系 + 社区摘要”的多证据问答；
- 可以做“复杂综合问题”的演示。

当前短板：

- query router 还需要稳定策略；
- hallucination guard 需要明确是否进入最终演示；
- 全局搜索的社区筛选和证据引用还可增强；
- 需要证明在什么问题类型上 GraphRAG 优于普通 RAG。

### 20.3 kg_pipeline

目录：

```text
kg_pipeline/
```

职责：

- LLM 三元组抽取；
- schema 约束；
- 社区检测；
- 社区摘要；
- POC 图谱数据。

关键文件：

```text
kg_pipeline/llm_extraction/pipeline.py
kg_pipeline/community_detection.py
kg_pipeline/community_summary.py
kg_pipeline/poc/
```

已有能力：

- `run_extraction`
- `read_chunks`
- `run_leiden_detection`
- `run_hierarchical_detection`
- `summarize_communities`

当前价值：

- 支撑“知识图谱增强”的真实技术链；
- 可以把专业文档从文本转为结构化知识；
- 可以做图谱可视化和人工审核。

当前短板：

- 三元组抽取质量评估不足；
- schema 设计需要更贴近动力装备领域；
- 缺少实体规范化、同义词归并、关系去重；
- 抽取结果和原文 chunk 的证据链需要进一步固化。

### 20.4 storage_layer

目录：

```text
storage_layer/
```

职责：

- SQLite 图数据库；
- 图谱节点/边导入；
- 社区和社区摘要存储；
- Neo4j Cypher 导出。

关键文件：

```text
storage_layer/graph_store.py
```

已有类/函数：

- `GraphStore`
- `GraphEdgeRecord`
- `import_edges`
- `neighbors`
- `edges_by_relation`
- `search_evidence`
- `store_communities`
- `store_community_summaries`
- `search_community_summaries`
- `write_neo4j_cypher`

当前价值：

- 本地可复现；
- 不依赖外部 Neo4j 就能跑；
- 适合答辩现场离线演示。

当前短板：

- SQLite 图谱能力有限；
- 需要更清楚的数据 schema 说明；
- 对大规模图谱性能需要说明边界。

### 20.5 model_adapters

目录：

```text
model_adapters/
```

职责：

- Embedding 适配；
- LLM 适配；
- reranker 适配。

关键文件：

```text
model_adapters/embedding.py
model_adapters/llm.py
model_adapters/reranker.py
```

已有能力：

- OpenAI-compatible LLM client；
- OpenAI embedding；
- SentenceTransformer embedding；
- Hashing embedding；
- CrossEncoder reranker；
- LLM reranker；
- NoOp reranker。

当前价值：

- 可以支持离线 deterministic test；
- 可以支持真实模型演示；
- 可以在技术报告中说明模型后端可替换。

当前短板：

- 环境变量和模型配置需要更清楚；
- 模型加载成本和失败降级策略需要写进文档；
- 手机/现场演示如果没有网络，应有离线 fallback。

### 20.6 evaluation

目录：

```text
evaluation/
```

职责：

- 系统级评测；
- 指标计算；
- 报告生成；
- 问题集管理。

关键文件：

```text
evaluation/metrics.py
evaluation/runner.py
evaluation/system_eval_questions.jsonl
evaluation/reports/
```

已有指标方向：

- faithfulness；
- relevancy；
- context recall；
- answer completeness；
- overall score。

当前已有报告：

```text
day3_retrieval_baseline_comparison_20260604_004434.md/json
day4_failure_analysis_20260604_012258.md/json
system_eval_day3_keyword_20260604_004434.md/json
system_eval_day3_dense_hashing_20260604_004434.md/json
system_eval_day3_hybrid_rrf_20260604_004434.md/json
day3_retrieval_outputs_keyword_20260604_004434.jsonl
day3_retrieval_outputs_dense_hashing_20260604_004434.jsonl
day3_retrieval_outputs_hybrid_rrf_20260604_004434.jsonl
```

当前价值：

- 已经有 baseline 和 failure analysis 的雏形；
- 非常适合转化为挑战杯“实验验证”章节。

当前短板：

- 评测问题是否覆盖完整知识能力，需要进一步分类；
- 评测报告需要图表化；
- 需要新增 GraphRAG 评测结果；
- 需要增加消融实验。

---

## 21. 当前测试覆盖地图

当前根目录单元测试：

```text
74 passed
```

覆盖主题包括：

### 21.1 文本清洗/OCR

```text
tests/unit/test_clean_ocr_text.py
tests/unit/test_ocr_night_correction.py
tests/unit/test_reocr_low_confidence_pages.py
```

覆盖：

- Tesseract TSV 行清理；
- 空文本 fallback；
- 低置信页识别；
- re-OCR 候选选择；
- 文本质量评分。

### 21.2 public books JSON ingestion

```text
tests/unit/test_public_books_json_ingest.py
```

覆盖：

- 最新 snapshot 选择；
- Label Studio export 解析；
- block 过滤；
- reading order；
- UTF-8 BOM；
- runtime dir 配置。

### 21.3 检索引擎

```text
tests/unit/test_retrieval_engine.py
tests/unit/test_graph_retriever.py
tests/unit/test_reranker.py
```

覆盖：

- DocumentChunk 元数据规范化；
- KeywordRetriever；
- HybridRetriever；
- ChromaRetriever 错误处理；
- SQLiteGraphRetriever；
- NoOp reranker。

### 21.4 知识图谱

```text
tests/unit/test_graph_store.py
tests/unit/test_llm_kg_extraction.py
tests/unit/test_community_detection.py
```

覆盖：

- triples JSON 导入 SQLite；
- graph links 导入；
- LLM JSON 解析；
- schema 外关系拒绝；
- 缺失 evidence 拒绝；
- Leiden 社区检测；
- 社区存储和读取。

### 21.5 GraphRAG

```text
tests/unit/test_global_search.py
tests/unit/test_graphrag_orchestrator.py
tests/unit/test_graphrag_integration.py
```

覆盖：

- text + graph + LLM 组合；
- context_only；
- missing LLM error；
- global search result；
- global search fallback；
- global context 接入。

### 21.6 模型适配器

```text
tests/unit/test_model_adapters_llm.py
```

覆盖：

- API key 缺失；
- OpenAI-compatible 设置；
- mock LLM 注入；
- chat completion payload。

### 21.7 API POC 测试

```text
api_server/current_console/chroma_rag_poc/tests/test_pipeline.py
```

当前：

```text
19 passed
```

覆盖：

- Label Studio 解析；
- generic JSON 解析；
- 清洗；
- 分块；
- ingest/search/stats；
- quality report；
- API ingest/search；
- upload/process/log；
- import-time no app side effect；
- frontend missing 404；
- CORS；
- unsupported upload path；
- top_k 边界；
- GraphRAG db path 越界拒绝；
- public-books-json input_dir 白名单；
- observability hardening；
- GraphRAG community detection route；
- benchmark。

### 21.8 测试短板

GPT Pro 应要求补：

1. 端到端 GraphRAG build pipeline 测试；
2. API route table snapshot；
3. OpenAPI contract snapshot；
4. `/api/search` 多模式行为测试；
5. GraphRAG search local/global/hybrid API 测试；
6. evaluation runner 对真实 system_eval_questions 的测试；
7. 前端 smoke test；
8. demo script 可复现测试；
9. 数据资产完整性检查；
10. README 命令可执行检查。

---

## 22. 当前交付资产盘点

### 22.1 docs/project_deliverables

当前包含多个阶段性交付目录：

```text
00_交给老师_阶段成果包
01_资料输入_14本PDF和问答JSON
02_OCR结果_13本扫描PDF
03_普通RAG数据库_14本资料
04_检索测试结果_10个问题
05_知识图谱POC_三元组和人工判断
06_四本书KG工具跑通演示
06_汇报材料_发群和组会
RAG技术架构与背景资料梳理.md
RAG核心流程图.mmd
RAG核心流程图.png
RAG核心流程图.puml
RAG核心流程图_矢量.svg
RAG核心流程图_高定版.html
RAG核心流程图_高清.png
README_先看这里.md
先看这里_项目成果总览.md
命名重构说明_旧目录到新目录.md
```

这些材料说明项目有过程成果，但现在有两个问题：

- 目录命名像课程交付，不像挑战杯申报；
- 部分旧目录路径在 Git 状态里显示断裂或删除，需确认是否真实存在。

建议：

把这些材料重新整理成：

```text
docs/challenge_cup/
  00_项目总览.md
  01_问题背景与应用价值.md
  02_技术路线.md
  03_系统架构.md
  04_数据资产说明.md
  05_评测报告.md
  06_失败案例分析.md
  07_现场演示脚本.md
  08_答辩问答.md
  09_申报书草稿.md
  10_PPT大纲.md
```

原始交付包保留到：

```text
archive/course_deliverables/
```

### 22.2 evaluation/reports

这些报告应该被 GPT Pro 重点利用：

- Day3 baseline comparison；
- keyword/dense/hybrid 输出；
- Day4 failure analysis；
- system eval reports。

建议让 GPT Pro 输出：

1. 如何把这些报告转化为挑战杯“实验验证”章节；
2. 缺哪些图表；
3. 哪些结果可以讲，哪些不能夸大；
4. 如何设计 GraphRAG 追加实验；
5. 如何把失败案例讲成“科学迭代过程”。

---

## 23. 项目技术创新点候选

注意：下面是候选，不代表都已经完全实现。GPT Pro 应判断哪些能作为正式创新点。

### 23.1 保守版创新点

1. 面向动力装备技术资料的 OCR 清洗、结构化分块和可追溯入库流程；
2. 面向中文工程术语的 BM25 + Dense + RRF 混合检索；
3. 基于证据约束的知识图谱抽取和 GraphRAG 问答原型。

适合结项，但冲奖力度不足。

### 23.2 中等强度创新点

1. 构建“文本证据 + 图谱关系 + 社区摘要”的多层证据 GraphRAG 框架；
2. 针对工程技术文档设计问题类型分类和检索策略路由；
3. 建立可追溯的从文档 chunk 到三元组、图谱路径、问答引用的证据链；
4. 通过 baseline、消融和失败案例分析验证系统优势。

比较适合挑战杯。

### 23.3 冲奖版创新点

1. 提出面向复杂工程技术文档的“多粒度证据约束 GraphRAG”方法：局部 chunk、实体关系路径和社区级摘要共同约束 LLM 回答；
2. 建立从 OCR 噪声文本到可信问答的端到端知识工程闭环，并通过可追溯 ID 链实现答案来源审计；
3. 针对动力装备领域问题构建检索-图谱-问答联合评测体系，证明 GraphRAG 在因果诊断、部件关联、维护措施和综合归纳类问题上优于普通 RAG；
4. 实现本地可复现的工程系统，支持文档入库、图谱构建、检索对比、证据引用和现场演示。

这个版本更适合冲特等奖，但必须用实验和演示支撑，不能只写在 PPT 上。

---

## 24. 需要固定的评测问题类型

挑战杯评测不应只用随机问题。建议固定 6 类问题：

### 24.1 事实定位型

示例：

- 某设备部件的定义是什么？
- 某参数的正常范围是多少？
- 某术语在哪些资料中出现？

主要考察：

- citation；
- Recall@k；
- source/page 定位。

### 24.2 部件关系型

示例：

- 燃气轮机由哪些关键部件组成？
- 压气机和燃烧室之间的关系是什么？

主要考察：

- 图谱实体关系；
- graph retriever；
- 三元组质量。

### 24.3 故障因果型

示例：

- 压气机出口温度偏高可能由哪些原因造成？
- 某故障现象对应哪些检查步骤？

主要考察：

- 多跳关系；
- evidence chain；
- GraphRAG 对普通 RAG 的优势。

### 24.4 维护措施型

示例：

- 出现振动升高时应采取哪些检查和处理措施？
- 某类报警对应的推荐处置流程是什么？

主要考察：

- action extraction；
- 文档流程信息；
- 答案完整性。

### 24.5 对比归纳型

示例：

- 不同资料对压气机喘振原因的描述有什么共同点？
- 某类故障在多本资料中的共性是什么？

主要考察：

- global search；
- community summary；
- 多文档聚合。

### 24.6 失败边界型

示例：

- 系统在哪些问题上会回答证据不足？
- 当 OCR 质量差或文档缺失时系统如何降级？

主要考察：

- 诚实回答；
- hallucination guard；
- 系统边界。

GPT Pro 应帮助设计 30-50 题评测集，并为每题标注：

```text
id
question
question_type
expected_answer
required_sources
required_entities
required_relations
difficulty
baseline_expected_failure
demo_priority
```

---

## 25. 消融实验设计

建议 GPT Pro 设计实验表格，至少包括：

| 实验组 | 检索方式 | 图谱 | rerank | global summary | 目的 |
|---|---|---|---|---|---|
| A | keyword only | 否 | 否 | 否 | 传统关键词 baseline |
| B | dense only | 否 | 否 | 否 | 普通向量 RAG baseline |
| C | hybrid RRF | 否 | 否 | 否 | 证明混合检索价值 |
| D | hybrid + rerank | 否 | 是 | 否 | 证明重排价值 |
| E | graph local only | 是 | 否 | 否 | 证明图谱局部关系 |
| F | hybrid + graph local | 是 | 可选 | 否 | 证明文本+图互补 |
| G | hybrid + graph + global summary | 是 | 可选 | 是 | 完整 GraphRAG |

指标建议：

- Recall@5；
- Recall@10；
- MRR；
- nDCG；
- citation coverage；
- evidence precision；
- answer completeness；
- faithfulness；
- latency；
- failure rate；
- “证据不足但拒答正确率”。

必须注意：

- 如果 GraphRAG 并非所有问题都更好，要诚实报告；
- 可以强调 GraphRAG 在“多跳关系、因果归纳、多文档综合”上优势更明显；
- 普通事实定位问题上 dense/hybrid 可能已经足够，这不是坏事，反而说明系统有策略路由必要性。

---

## 26. 现场演示设计

挑战杯演示不要从“上传文件”开始，除非时间很长。建议设计一个固定演示流程：

### 26.1 演示首页

第一屏应显示：

- 项目名称；
- 数据资产概览：文档数、chunk 数、实体数、关系数、社区数；
- 当前索引状态；
- 三种检索模式按钮：
  - 普通 RAG；
  - Hybrid RAG；
  - GraphRAG；
- 预设演示问题。

### 26.2 演示问题 1：事实定位

目的：

- 证明系统能准确找原文。

展示：

- 答案；
- chunk 引用；
- 文件名/页码；
- 原文高亮。

### 26.3 演示问题 2：故障因果

目的：

- 证明图谱关系有价值。

展示：

- 普通 RAG 答案；
- GraphRAG 答案；
- 相关实体；
- 故障 -> 原因 -> 检查措施路径；
- evidence。

### 26.4 演示问题 3：多文档综合

目的：

- 证明 global search / community summary 有价值。

展示：

- 涉及哪些社区；
- 每个社区摘要；
- 最终综合答案；
- 引用来源。

### 26.5 演示问题 4：证据不足

目的：

- 证明系统不会瞎编。

展示：

- 回答“证据不足”；
- 缺失证据说明；
- 建议补充资料。

### 26.6 演示问题 5：评测结果

目的：

- 证明不是现场挑例子。

展示：

- baseline 对比图；
- failure analysis；
- 消融实验结果；
- 改进前后对比。

---

## 27. 挑战杯材料包建议

### 27.1 申报书结构

建议：

```text
1. 项目名称
2. 项目摘要
3. 问题背景
4. 国内外相关工作
5. 项目核心创新
6. 技术路线
7. 系统实现
8. 实验评测
9. 应用价值
10. 可推广性
11. 团队分工
12. 已完成成果
13. 后续计划
14. 学术规范和数据说明
```

### 27.2 技术报告结构

建议：

```text
1. 引言
2. 问题定义
3. 数据集与预处理
4. 方法
   4.1 OCR 清洗与结构化分块
   4.2 Hybrid Retrieval
   4.3 Evidence-bound KG Extraction
   4.4 Graph Store
   4.5 Community Detection and Summary
   4.6 GraphRAG QA
5. 系统架构
6. 实验设置
7. 实验结果
8. 消融实验
9. 失败案例分析
10. 现场演示系统
11. 局限性
12. 结论
```

### 27.3 PPT 结构：8 分钟

建议 10-12 页：

```text
1. 标题：面向动力装备技术文档的可追溯 GraphRAG 系统
2. 痛点：复杂工程资料问答为什么难
3. 核心问题：普通 RAG 的三个不足
4. 总体方案：OCR → Hybrid → KG → GraphRAG → Citation
5. 技术创新 1：工程文档结构化与证据链
6. 技术创新 2：多策略检索和图谱增强
7. 技术创新 3：社区级全局检索与可信问答
8. 系统演示截图
9. 实验结果和消融
10. 失败案例与边界
11. 应用价值
12. 总结与后续
```

### 27.4 墙报结构

如果需要墙报，建议分成：

```text
左：问题背景和应用场景
中：技术路线和系统架构
右：实验结果、演示截图、创新点
底部：二维码/代码/报告/视频链接
```

---

## 28. 评委最可能追问的问题

GPT Pro 应帮忙扩展到 30 个问答。这里先列核心 20 个：

1. 你的项目和普通 RAG 有什么本质区别？
2. 为什么一定要知识图谱？
3. 图谱三元组是如何保证正确的？
4. LLM 抽取错误怎么办？
5. OCR 错误会不会传导到最终答案？
6. 你的数据集是否足够真实？
7. 评测问题是否人工挑选？
8. GraphRAG 是否在所有问题上都优于普通 RAG？
9. 如果不是所有问题都优于普通 RAG，你怎么解释？
10. 系统如何避免 hallucination？
11. 证据引用是否真的对应原文？
12. 与 LangChain/LlamaIndex/微软 GraphRAG 相比，你做了什么自己的工作？
13. 这个项目能否离线运行？
14. 现场没有网络怎么办？
15. 系统处理大规模资料的瓶颈在哪里？
16. 为什么选择 Chroma 和 SQLite？
17. 是否可以迁移到 Neo4j 或企业知识库？
18. 这个项目对动力装备行业有什么实际价值？
19. 如果换成医学/法律资料，是否可复用？
20. 你们团队每个人贡献是什么？

建议回答原则：

- 不要夸大；
- 先承认边界；
- 再说明当前设计；
- 最后给出实验或演示证据。

---

## 29. 两周最小冲刺计划

如果只剩两周，不建议大重构。建议目标是“可结项 + 可冲校内高奖的完整闭环”。

### 第 1-2 天：确定主线和数据集

必须完成：

- 固定项目名；
- 固定 10-20 个演示/评测问题；
- 固定 1 套演示数据；
- 写 `docs/challenge_cup/00_项目总览.md`；
- 写 `datasets/README.md`。

不要做：

- 不要全仓库迁移；
- 不要换框架；
- 不要引入复杂新数据库。

### 第 3-5 天：补 GraphRAG 评测

必须完成：

- 跑 keyword/dense/hybrid/GraphRAG 对比；
- 生成 markdown 和 JSON 报告；
- 至少画 3 张图：
  - Recall@k；
  - answer score；
  - question type breakdown。

### 第 6-8 天：打磨前端演示

必须完成：

- 固定演示问题按钮；
- 展示普通 RAG vs GraphRAG；
- 展示证据 chunk；
- 展示图谱路径；
- 展示社区摘要；
- 展示评测结果。

### 第 9-11 天：材料包

必须完成：

- 技术报告；
- 申报书草稿；
- 8 分钟 PPT；
- 演示脚本；
- 30 问答辩稿。

### 第 12-14 天：彩排和修补

必须完成：

- 本地一键启动；
- 录屏备份；
- 离线 fallback；
- README 修复；
- 测试全绿；
- 最终交付包。

---

## 30. 四周增强计划

如果有四周：

### 第 1 周：工程收敛

- 明确主线目录；
- 清理 README；
- 固定启动命令；
- 隔离 runtime/artifacts；
- API route table 文档化；
- 数据资产清单。

### 第 2 周：GraphRAG 闭环增强

- graph_id/collection_id 管理；
- 三元组抽取质量评估；
- 图谱路径引用；
- community summary 检索；
- query routing。

### 第 3 周：评测和消融

- 30-50 题评测集；
- 多模式 baseline；
- GraphRAG 消融；
- 失败案例；
- 指标图表。

### 第 4 周：挑战杯材料和演示

- 前端演示系统；
- 技术报告；
- 申报书；
- PPT；
- 墙报；
- 录屏；
- 问答稿。

---

## 31. 八周冲奖计划

如果有八周，可以尝试冲击更高水平：

### 第 1-2 周：项目重构和数据治理

- 完整资产盘点；
- `datasets/` 标准化；
- `docs/challenge_cup/` 建立；
- API 拆分；
- job queue 初版；
- OpenAPI snapshot。

### 第 3-4 周：算法增强

- 实体规范化；
- 同义词词典；
- graph-aware rerank；
- community vector index；
- DRIFT-style global-local fallback；
- hallucination guard 评测。

### 第 5-6 周：系统评测

- 50-100 题；
- 人工标注证据；
- 多维指标；
- 与主流框架/普通 RAG 对照；
- 统计显著性或至少分类型对比；
- 错误类型 taxonomy。

### 第 7-8 周：答辩产品化

- 演示 UI；
- 展示视频；
- 技术报告定稿；
- 申报书定稿；
- PPT 和墙报；
- 多轮模拟答辩。

---

## 32. 最终给 GPT Pro 的更强任务书

如果 GPT Pro 支持文件读取，请上传本文件，并发送下面这段：

```text
请完整读取我上传的项目上下文文件。你不要只总结，而要接管这个项目的“冲击清华挑战杯特等奖”方案设计。

请你基于文件中真实现状，输出一份可执行的《项目优化总方案》，要求：

1. 先用评委视角指出这个项目现在为什么还不够格；
2. 再判断它最有希望打磨成什么样的参赛作品；
3. 明确哪些已有能力可以保留，哪些只是噪音；
4. 给出最终项目定位、项目名称、摘要、创新点；
5. 设计完整技术路线；
6. 设计端到端工程闭环；
7. 设计实验和消融；
8. 设计前端演示；
9. 设计申报书、技术报告、PPT、墙报；
10. 给出两周、四周、八周执行计划；
11. 给出 30 个评委追问和回答；
12. 最后输出一个“从今天开始第一周每天该做什么”的任务清单。

请你保持严厉，不要鼓励式空话。凡是建议，都必须能落到：
- 一个代码模块；
- 一个实验；
- 一个文档；
- 一个演示页面；
- 一个答辩表达。

不要虚构已有成果。对于尚未完成的内容，请明确标注“需要补做”。
```

---

## 33. GPT Pro 输出后应该怎么用

GPT Pro 给方案后，不要一次性全做。建议按这个顺序落地：

1. 先确定项目名和一句话定位；
2. 再确定评测问题集；
3. 再固定演示数据；
4. 再跑 baseline；
5. 再补 GraphRAG 对比；
6. 再整理 README；
7. 再打磨前端；
8. 再写技术报告；
9. 再做 PPT；
10. 最后彩排问答。

判断一个建议是否值得做，用这个标准：

```text
它是否能增强问题闭环？
它是否能增强评测证据？
它是否能增强现场演示？
它是否能降低评委质疑？
它是否能在时间内完成？
```

如果答案是否，就先不做。

---

## 34. 当前项目一句最诚实的总结

这个项目现在不是“垃圾到无法挽救”，也不是“已经是挑战杯项目”。它更准确的状态是：

> 一个已经堆出了 OCR、RAG、Hybrid Retrieval、KG、GraphRAG、评测和前端雏形的复杂原型，但工程边界、项目叙事、评测证据和演示产品还没有收敛。它有打磨价值，但必须先从功能堆叠转向问题闭环。

GPT Pro 应基于这个判断给出方案。
