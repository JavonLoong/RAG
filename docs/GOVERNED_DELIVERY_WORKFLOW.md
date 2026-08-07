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
- 图谱实体和关系受燃气轮机最小 Schema 约束，并显示低置信度、别名归一和多来源冲突。
- 阻断级图谱问题（未知类型、未知关系、证据越界/缺失）不能被一次普通审核绕过。
- FMEA 只从已发布图谱生成，所有专业字段分别保存证据 ID；缺失值保持为空并生成审核问题。
- 人工修改、否定、批准和回滚都有审计记录。
- 不自动生成无依据的 S/O/D 或 RPN 评分。

## API

接口统一位于 `/api/delivery`：

| 能力 | 接口 |
|---|---|
| 解析并创建资料候选 | `POST /documents/intake` |
| 查看/审核/发布资料版本 | `GET /documents/{id}`、`POST /documents/{id}/review`、`POST /documents/{id}/publish` |
| 资料版本比较/回滚 | `GET /documents/compare/{left}/{right}`、`POST /documents/{document_id}/rollback` |
| 创建/查看/审核/发布图谱版本 | `POST /graphs/candidates`、`GET /graphs/{id}`、`POST /graphs/{id}/review`、`POST /graphs/{id}/publish` |
| 导出图谱三元组 | `GET /graphs/{id}/export` |
| 创建/查看/审核/发布 FMEA | `POST /fmea/tasks`、`GET /fmea/tasks/{id}`、`POST /fmea/tasks/{id}/review`、`POST /fmea/tasks/{id}/publish` |
| 导出 FMEA | `GET /fmea/tasks/{id}/export?format=json|csv` |
| 问题回流 | `POST /fmea/tasks/{id}/feedback` |

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
python -m pytest tests/unit/test_governed_delivery_workflow.py tests/unit/test_delivery_api.py -q
```

端到端测试覆盖：解析、证据定位、资料审核发布、图谱 Schema/证据门禁、FMEA 逐字段引用、人工修订、成果导出、版本比较、回滚和问题回流。
