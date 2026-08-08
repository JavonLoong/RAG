# GraphRAG M2—M5 两周开发进度汇报

## 汇报结论

本阶段已经从“接口和数据结构样例”推进到一条可重复运行、可审核、可导出的基础闭环：资料解析/OCR 结果进入候选库，人工纠错形成新版本，正式资料进入版本化检索，原文自动形成带证据的知识图谱，图谱生成 FMEA，问题还能回流并留下真实执行记录。

按功能、集成、证据和测试四个维度综合评估，当前建议汇报为 **7.5/10**。这足以代表两周开发进度，但不应表述为生产系统已经 100% 完成。

## 两周完成内容

| 模块 | 通俗目标 | 已完成且可现场验证 | 当前边界 |
|---|---|---|---|
| M2 资料读取 | 把各种资料可靠地读进来，哪里读不准要能指出来并纠正 | 原生 PDF、扫描 PDF 路由、DOCX、中英文文本；逐页 OCR 结果接入；漏页、空页、低置信度和版面风险；人工修订生成新版本并保留页码/块定位/审计 | 图片和扫描件仍依赖外部 OCR 产出；内容纠错必须人工确认 |
| M3 资料库 | 只让正式版本被检索，换版本后索引也要跟着换 | 正式资料发布自动同步 Chroma；按资料版本过滤检索；索引状态和全量重建；回滚后重新同步；结果返回 evidence ID 和原页定位 | 演示包为可离线复现使用 hashing；生产配置应启用 Qwen3-Embedding-0.6B，并用真实语料评测后决定是否升级 |
| M4 知识图谱 | 把句子拆成“设备—故障—原因—影响—检测—措施”的网络 | 可审计规则基线自动抽取；支持注入小模型/LLM；实体关系 Schema、证据和冲突门禁；发布后同步 GraphStore；可查询带原文证据的关系路径 | 规则基线覆盖常见句式，不等于训练好的行业小模型；仍需中文标注集做准确率基准和人工复核 |
| M5 FMEA | 把图谱整理成可审核、可导出的 FMEA 表 | 从正式图谱生成；每个专业字段绑定证据；审核发布；JSON/CSV 导出逐字段一致性检查；M2—M5 问题路由；M3/M4/M5 回流产生真实动作和执行记录 | S/O/D 与 RPN 没有可靠依据时保持空白；M1 权限/来源问题仍需人员补充 |

## 现场展示：六步、八分钟

1. 打开 `ocr_candidate.json`：指出第 146 页置信度低，并展示错误术语“者塞”。
2. 打开 `published_document.json`：展示人工修正为“堵塞”、版本从 v1 变 v2，原始页码仍为 146。
3. 打开 `retrieval_result.json`：问“过滤器堵塞的原因和检测方法”，展示命中的正式版本、证据 ID 和页码。
4. 打开 `published_graph.json` 与 `graph_path.json`：展示自动抽取的 6 类关系，以及“燃气轮机→油液污染”的证据路径。
5. 同时打开 `fmea.json` 和 `fmea.csv`：展示故障模式、原因、影响、检测和措施都能追溯到证据，并说明一致性检查通过。
6. 打开 `feedback_remediation.json`：展示“索引过期”问题不是只登记，而是实际触发正式资料索引重建并记录执行人、时间和结果。

现场一句话可以这样说：

> 这两周完成的不是一个静态页面，而是从资料纠错、正式检索、图谱构建到 FMEA 和反馈回流的一条可运行闭环；每一步都有版本、有原文证据，也保留了人工审核门禁。

## 一键复现

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts\run_governed_delivery_demo.py
```

脚本会在 `build/governed_delivery_demo/<运行时间>/` 生成：

- `两周开发进度验收报告.md`：现场讲稿和阶段评分；
- `manifest.json`：本次运行的自动验收结果；
- `ocr_candidate.json`、`published_document.json`：M2 修订前后；
- `retrieval_result.json`：M3 检索证据；
- `published_graph.json`、`graph_path.json`：M4 图谱与路径；
- `fmea.json`、`fmea.csv`：M5 交付成果；
- `feedback_remediation.json`：问题回流的执行证据。

## 验收证据

```powershell
.\.venv\Scripts\ruff.exe check storage_layer/governed_index.py storage_layer/governance_store.py kg_pipeline/governed_extraction.py rag_orchestrator/fmea.py rag_orchestrator/delivery_remediation.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_delivery.py scripts/run_governed_delivery_demo.py tests/unit/test_governed_delivery_workflow.py tests/unit/test_delivery_api.py tests/unit/test_delivery_representative_inputs.py
.\.venv\Scripts\python.exe -m pytest tests/unit/test_governed_delivery_workflow.py tests/unit/test_delivery_api.py tests/unit/test_delivery_representative_inputs.py -q
```

当前阶段的相关自动化验收为 **13/13 passed**，静态检查通过。演示脚本还会独立验证检索有命中、自动抽取至少 6 条候选关系、证据路径可达、JSON/CSV 一致、反馈执行完成。

## 下一阶段发展方向

优先级建议如下：

1. 建立 100—300 条中文行业标注集，比较规则、GLiNER/PURE 类小模型和 LLM 的实体/关系准确率，而不是先盲目更换模型。
2. 用实际资料做 Qwen3-Embedding-0.6B、BGE-M3 等候选的 Recall@K、MRR、延迟和显存对比，再确定生产向量模型。
3. 把 M2 OCR 置信度、表格结构和阅读顺序风险做成审核界面，降低人工核对成本。
4. 补齐权限、许可和资料来源台账；这是 M1 治理问题，不能由模型自动猜测。
5. 增加前端图谱交互和 FMEA 审核页面，但后端版本、证据和发布门禁保持不变。

达到 9/10 需要：真实资料集上的量化评测、生产向量模型、经过标注集验证的小模型抽取、权限台账和用户验收；达到 10/10 还需要部署、监控、备份恢复、性能和安全验收。
