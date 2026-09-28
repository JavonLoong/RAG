# Skill 代码

这里是 `govern-graphrag-delivery` 的完整 M2–M5 实现，不是只有 yaml。

| 路径 | 做什么 |
|---|---|
| `core_domain/delivery.py` | 资料版本、证据、图谱、FMEA 的合同 |
| `data_pipeline/document_intake.py` | 解析 / OCR 入口 |
| `storage_layer/governance_store.py` | 审核、发布、回滚 |
| `storage_layer/graph_store.py` | 图谱存储 |
| `rag_orchestrator/graphrag_qa.py` | GraphRAG 路径问答 |
| `rag_orchestrator/fmea.py` | FMEA 生成与导出 |
| `api_server/.../routes_delivery.py` | `/api/delivery` |
| `configs/fmea/` | 燃气轮机 / 电动机模板 |
| `tests/unit/` | 工作流与 API 冒烟 |

仓库根目录里的同名文件是工作台运行时的导入路径。改完实现后，在本 Skill 目录执行：

```powershell
python scripts/pack_code.py
```
