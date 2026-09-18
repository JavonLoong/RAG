# M2–M5 可审核交付工作流

本工作流落实纪文龙在 GraphRAG 模块任务清单中的 M2、M3、M4、M5 交付责任，并复用仓库已有的解析/OCR、混合检索、图存储和 GraphRAG 问答能力。

## 已实现闭环

```text
文件解析（M2）
  -> 证据定位 + 质量问题 + 资料候选
  -> 人工审核 + 正式资料版本（M3）
  -> Schema 校验 + 别名归一 + 冲突检查 + 图谱候选
  -> 人工审核 + 正式图谱版本（M4）
  -> FMEA 候选 + 逐字段证据 + 缺失/冲突提示
  -> 人工修订/批准 + JSON/CSV 发布成果（M5）
  -> 问题按根因回流 M2/M3/M4/M5
```

控制面数据持久化在 `<persist_dir>/governance/delivery.sqlite3`。原文证据、资料版本、图谱版本、审核记录和 FMEA 任务均可独立追踪。

## 核心约束

- 资料只有在保留至少一条原文证据且最新人工审核为 `approve` 时才能发布。
- 图谱只接受已发布资料版本；每条关系必须绑定所选资料版本中的证据 ID。
- 图谱实体、关系和知识类型受版本化燃气轮机 Schema 约束；关系主客体 domain/range、型号作用域、别名归一、重复合并、跨型号差异和同型号来源冲突均独立校验。
- 阻断级图谱问题（未知类型、未知关系、证据越界/缺失）不能被一次普通审核绕过。
- FMEA 只从已发布图谱生成，所有专业字段分别保存证据 ID；缺失值保持为空并生成审核问题。
- 人工修改、否定、批准和回滚都有审计记录。
- 不自动生成无依据的 S/O/D 或 RPN 评分。

## API

接口统一位于 `/api/delivery`：

| 能力 | 接口 |
|---|---|
| 解析并创建资料候选 | `POST /documents/intake` |
| 接收逐页 OCR 结果并标出漏页/空页/低置信度 | `POST /documents/intake/ocr-result` |
| 人工纠错生成不可变新版本 | `POST /documents/{id}/revise` |
| 查看/审核/发布资料版本 | `GET /documents/{id}`、`POST /documents/{id}/review`、`POST /documents/{id}/publish` |
| 资料版本比较/回滚 | `GET /documents/compare/{left}/{right}`、`POST /documents/{document_id}/rollback` |
| 检索正式资料/查看或重建索引 | `GET /documents-search`、`GET /documents-index/status`、`POST /documents-index/rebuild` |
| 自动抽取/创建图谱候选 | `POST /graphs/extract`、`POST /graphs/candidates` |
| 查看/审核/发布图谱版本 | `GET /graphs/{id}`、`POST /graphs/{id}/review`、`POST /graphs/{id}/publish` |
| 图版本列表/比较/审计回滚 | `GET /graphs`、`GET /graphs/compare/{left}/{right}`、`POST /graphs/rollback` |
| 图视图/证据审计/导出/路径 | `GET /graphs/{id}/view`、`GET /graphs/{id}/evidence-audit`、`GET /graphs/{id}/export`、`GET /graphs/{id}/path` |
| 指定图版本 GraphRAG 问答 | `POST /graphs/{id}/query` |
| 普通 RAG / GraphRAG 同题对比 | `POST /graphs/{id}/compare-rag` |
| 创建/查看/审核/发布 FMEA | `POST /fmea/tasks`、`GET /fmea/tasks/{id}`、`POST /fmea/tasks/{id}/review`、`POST /fmea/tasks/{id}/publish` |
| 查看版本化 FMEA 模板 | `GET /fmea/templates`、`GET /fmea/templates/{template_id}?version=1.1.0` |
| 查看 FMEA 审核与状态迁移记录 | `GET /fmea/tasks/{id}/reviews`、`GET /fmea/tasks/{id}/status-history` |
| 导出并核对 FMEA | `GET /fmea/tasks/{id}/export?format=json|csv`、`GET /fmea/tasks/{id}/export-verify` |
| 问题回流及执行审计 | `POST/GET /fmea/tasks/{id}/feedback`、`POST /fmea/feedback/{feedback_id}/remediate`、`GET /fmea/feedback/{feedback_id}/runs` |

文件内容在 `documents/intake` 中使用 Base64 传输；解析仍由 `data_pipeline.document_intake` 选择原生解析、OCR 或外部解析路线。

## Python 调用

```python
from core_domain.delivery import FMEATaskRequest
from rag_orchestrator.fmea import FMEAService
from storage_layer.governance_store import GovernanceStore

store = GovernanceStore("runtime/delivery.sqlite3")
service = FMEAService(store)

task = service.run(
    FMEATaskRequest(
        requested_by="reviewer",
        graph_version_id="graph:v1",
        document_version_ids=("manual:v1",),
    )
)
```

燃气轮机最小字段模板见 `configs/fmea/gas_turbine_minimum_v1.yaml`。

## 验证

```powershell
python -m pytest tests/unit/test_governed_delivery_workflow.py tests/unit/test_delivery_api.py tests/unit/test_delivery_representative_inputs.py tests/unit/test_graphrag_completion_acceptance.py tests/unit/test_m5_completion.py -q
python scripts/run_governed_delivery_demo.py
python scripts/run_graphrag_completion_delivery.py
```

端到端测试覆盖：原生 PDF、扫描 PDF、DOCX、中英文文本、OCR 漏页、证据定位、资料纠错/审核/发布、版本化 Chroma 索引、三页真实 M701F OCR 摘录自动关系抽取、知识类型、型号差异、来源冲突、关系端点约束、证据全覆盖审计、历史图版本查询/查看/导出/回滚、GraphRAG 路径回答、普通 RAG 同题对比、查询级回退、FMEA 逐字段引用、双格式导出一致性和可执行问题回流。

演示脚本会在 `build/governed_delivery_demo/<运行时间>/` 生成自包含验收包。详细汇报口径见 `docs/GOVERNED_DELIVERY_TWO_WEEK_PROGRESS.md`。

完整 M4 验收脚本会在 `build/graphrag_completion_acceptance/<运行时间>/` 生成 Schema、已发布图谱、实体关系、冲突/约束结果、证据审计、图路径、GraphRAG 回答、同题对比、普通 RAG 回退和 FMEA 产物。
