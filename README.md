# Power Equipment RAG Research System

这是围绕"动力装备知识库 / RAG / GraphRAG / 顶刊实验"重新整理后的工程工作区。

当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `frontend_app/current_console/`，运行数据迁移到 `storage_layer/runtime/current_console/`。

## 挑战杯 / 结项评审入口

挑战杯与结项材料入口见 [`docs/challenge_cup/README_先看这里.md`](docs/challenge_cup/README_先看这里.md)。该目录把项目一页纸、挑战杯项目书、技术白皮书、实验评测报告、系统演示脚本、答辩问答手册和结项验收清单集中到一个评审入口。

## ✨ GraphRAG 核心能力

| 功能 | 模块 | 状态 |
|------|------|------|
| 实体/关系抽取 | `kg_pipeline/llm_extraction/` | ✅ 完整 |
| 知识图谱存储 | `storage_layer/graph_store.py` | ✅ 完整 |
| **社区检测（Leiden）** | `kg_pipeline/community_detection.py` | ✅ 新增 |
| **社区摘要（LLM）** | `kg_pipeline/community_summary.py` | ✅ 新增 |
| **全局搜索（Map-Reduce）** | `rag_orchestrator/global_search.py` | ✅ 新增 |
| 局部搜索 | `rag_orchestrator/graphrag_qa.py` | ✅ 完整 |
| 混合检索 | `retrieval_engine/hybrid.py` | ✅ 完整 |
| **评估系统** | `evaluation/` | ✅ 新增 |
| **Embedding 适配器** | `model_adapters/embedding.py` | ✅ 新增 |
| **统一配置中心** | `configs/` | ✅ 新增 |
| **核心领域模型** | `core_domain/` | ✅ 新增 |
| **实验管理** | `experiments/` | ✅ 新增 |

## 当前推荐入口

- 后端与控制台入口：[`api_server/current_console`](api_server/current_console/)
- 启动脚本：[`api_server/current_console/start_local.bat`](api_server/current_console/start_local.bat)
- 后端入口：[`api_server/current_console/server.py`](api_server/current_console/server.py)
- 前端页面：[`frontend_app/current_console/index.html`](frontend_app/current_console/index.html)
- 运行数据：[`storage_layer/runtime/current_console`](storage_layer/runtime/current_console/)

## 目录结构

```text
RAG/
├─ configs/                  # 全局配置中心（JSON/环境变量）
├─ core_domain/              # 领域语义与共享数据结构
├─ data_pipeline/            # 数据导入、解析、清洗、切分与数据集
├─ kg_pipeline/              # 知识图谱构建、社区检测与摘要
│  ├─ community_detection.py # Leiden 社区检测
│  ├─ community_summary.py   # LLM 社区摘要生成
│  └─ llm_extraction/        # LLM 实体关系抽取
├─ retrieval_engine/         # dense/sparse/graph/hybrid 检索
├─ rag_orchestrator/         # RAG 编排、答案生成与引用验证
│  ├─ graphrag_qa.py         # 局部搜索（text + graph）
│  └─ global_search.py       # 全局搜索（map-reduce over communities）
├─ model_adapters/           # LLM + Embedding 模型适配
│  ├─ llm.py                 # OpenAI 兼容 LLM 适配
│  └─ embedding.py           # 多后端 Embedding 适配
├─ storage_layer/            # 向量库、图数据库、文档仓库
├─ evaluation/               # 自动化评估系统
│  ├─ metrics.py             # Faithfulness/Relevancy/Recall/Completeness
│  └─ runner.py              # 批量评估运行器
├─ experiments/              # 实验管理与追踪
├─ observability/            # 日志、trace、性能监控
├─ api_server/               # API 服务与当前控制台后端
├─ frontend_app/             # 前端应用与可视化界面
├─ scripts/                  # 工程脚本
├─ tests/                    # 单元、集成、回归、性能测试
└─ docs/                     # 架构、调研、会议、实验与复现文档
```

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 启动主控制台

Windows：

```text
api_server/current_console/start_local.bat
```

命令行：

```powershell
cd "D:\虚拟C盘\RAG\api_server\current_console"
$env:PYTHONPATH="$PWD\chroma_rag_poc\src"
python server.py
```

访问：

- 前端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

### 3. GraphRAG 全流程

```python
# 1. 社区检测
from kg_pipeline.community_detection import run_leiden_detection
from storage_layer.graph_store import GraphStore

store = GraphStore("graph.sqlite3")
result = run_leiden_detection(store, resolution=1.0)
print(f"检测到 {result.num_communities} 个社区")

# 2. 社区摘要
from kg_pipeline.community_summary import summarize_communities
from model_adapters import build_llm_from_env

llm = build_llm_from_env()
summaries = summarize_communities(store, llm, level=0)

# 3. 全局搜索
from rag_orchestrator import GlobalSearchOrchestrator

searcher = GlobalSearchOrchestrator(graph_store=store, llm_client=llm)
answer = searcher.search("本书的核心知识体系是什么？")
print(answer.answer)
```

### 4. 运行评估

```python
from evaluation import EvaluationRunner, EvaluationSuite

suite = EvaluationSuite.from_json("tests/fixtures/test_questions.json")
runner = EvaluationRunner(rag_system=my_rag, llm_client=llm)
report = runner.run(suite)
report.save("evaluation/reports/eval_report.json")
```

### 5. 运行测试

```bash
python -m pytest tests
```

## 说明

- `api_server/current_console/` 是当前可运行主线，短期内不要再移动它的内部包结构。
- `frontend_app/current_console/` 是当前控制台前端，后端会优先从这里挂载静态页面。
- `storage_layer/runtime/current_console/` 保存本地运行数据，不应作为论文实验结果直接引用。
- `data_pipeline/prototype/` 保存早期轻量原型，便于后续拆分进正式模块。
- `archive/` 保存历史材料，不作为当前主线开发入口。

