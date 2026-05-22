# Power Equipment RAG Research System

这是围绕“动力装备知识库 / RAG / GraphRAG / 顶刊实验”重新整理后的工程工作区。

当前根目录按照核心能力切分：每个一级文件夹代表一个高内聚模块；已经可运行的 RAG 控制台被迁移到 `api_server/current_console/`，其前端迁移到 `frontend_app/current_console/`，运行数据迁移到 `storage_layer/runtime/current_console/`。

## 当前推荐入口

- 后端与控制台入口：[`api_server/current_console`](api_server/current_console/)
- 启动脚本：[`api_server/current_console/start_local.bat`](api_server/current_console/start_local.bat)
- 后端入口：[`api_server/current_console/server.py`](api_server/current_console/server.py)
- 前端页面：[`frontend_app/current_console/index.html`](frontend_app/current_console/index.html)
- 运行数据：[`storage_layer/runtime/current_console`](storage_layer/runtime/current_console/)

## 新目录结构

```text
RAG/
├─ configs/                  # 全局配置中心
├─ core_domain/              # 领域语义与共享数据结构
├─ data_pipeline/            # 数据导入、解析、清洗、切分与数据集
│  ├─ prototype/             # 早期 power_rag_pipeline 原型包
│  └─ datasets/              # 实验数据集与解码数据
├─ kg_pipeline/              # 知识图谱构建与摘要
├─ retrieval_engine/         # dense/sparse/graph/hybrid 检索
├─ rag_orchestrator/         # RAG 编排、答案生成与引用验证
├─ model_adapters/           # LLM、Embedding、Reranker 等模型适配
├─ storage_layer/            # 向量库、图数据库、文档仓库、运行数据
├─ observability/            # 日志、trace、性能监控与错误归因
├─ evaluation/               # 指标、人工评估、消融与显著性检验
├─ experiments/              # 顶刊实验脚本与配置矩阵
├─ paper_assets/             # 论文图表、案例、附录与演示材料
├─ api_server/               # API 服务与当前控制台后端
├─ frontend_app/             # 前端应用与可视化界面
├─ scripts/                  # 工程脚本
├─ tests/                    # 单元、集成、回归、性能测试
└─ docs/                     # 架构、调研、会议、实验与复现文档
```

完整蓝图见：[docs/rag_full_engineering_blueprint.md](docs/rag_full_engineering_blueprint.md)。

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

### 3. 运行测试

根仓原型测试：

```bash
python -m pytest tests
```

当前控制台测试：

```powershell
.\.venv\Scripts\python.exe -S -c "import sys; sys.path.insert(0, str(__import__('pathlib').Path.cwd() / '.venv' / 'Lib' / 'site-packages')); import pytest; raise SystemExit(pytest.main([r'api_server/current_console/chroma_rag_poc/tests/test_pipeline.py']))"
```

## 说明

- `api_server/current_console/` 是当前可运行主线，短期内不要再移动它的内部包结构。
- `frontend_app/current_console/` 是当前控制台前端，后端会优先从这里挂载静态页面。
- `storage_layer/runtime/current_console/` 保存本地运行数据，不应作为论文实验结果直接引用。
- `data_pipeline/prototype/` 保存早期轻量原型，便于后续拆分进正式模块。
- `archive/` 保存历史材料，不作为当前主线开发入口。
