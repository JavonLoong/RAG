# Power Equipment RAG Workspace

这是一个围绕“动力装备知识库 / RAG / 检索增强应用”整理后的工作区仓库。

当前仓库不再把根目录伪装成模板项目，而是明确分成三类内容：

- `apps/`：可直接运行、可演示、可持续维护的应用
- `src/` + `tests/`：仍保留在根仓的原型代码与基础测试
- `archive/`：历史代码、旧实验和保留材料

## 当前推荐入口

主入口是纪文龙的控制台应用：

- [apps/jiwenlong-rag-console](apps/jiwenlong-rag-console/)
- 启动脚本：[start_local.bat](apps/jiwenlong-rag-console/start_local.bat)
- 后端入口：[server.py](apps/jiwenlong-rag-console/server.py)

## 仓库结构

```text
power-equipment-rag-workspace/
├─ apps/
│  └─ jiwenlong-rag-console/        # 当前主应用，前后端一体的 Chroma RAG 控制台
├─ src/
│  └─ power_rag_pipeline/           # 根仓保留的轻量原型包
├─ tests/
│  └─ test_power_rag_pipeline.py    # 根仓原型的基础测试
├─ docs/
│  ├─ index.md                      # 文档首页
│  ├─ repository-layout.md          # 仓库结构说明
│  ├─ pipeline-prototype.md         # 原型包 API 文档页
│  └─ diagrams/
│     └─ logic-structure.html       # 逻辑结构图
├─ archive/
│  ├─ README.md                     # 归档说明
│  └─ legacy-code/
│     ├─ plant-graph-rag/           # 历史 gitlink / 子仓快照
│     └─ guo-demo/                  # 郭老师的早期实验脚本与页面
├─ .devcontainer/
├─ pyproject.toml
├─ Dockerfile
├─ Makefile
├─ mkdocs.yml
└─ .gitlab-ci.yml
```

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 启动主应用

Windows：

```text
apps/jiwenlong-rag-console/start_local.bat
```

命令行：

```powershell
cd "D:\虚拟C盘\RAG项目_动力装备知识库\apps\jiwenlong-rag-console"
$env:PYTHONPATH="$PWD\chroma_rag_poc\src"
python server.py
```

访问：

- 前端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

### 3. 查看根仓原型包

```bash
uv run python -m power_rag_pipeline.pipeline --help
```

说明：

- 根仓原型包主要用于保留早期 Label Studio -> 分块 -> 向量化 -> 检索的单文件实现思路
- 日常演示和继续开发，优先使用 `apps/jiwenlong-rag-console`

## 文档

- 仓库结构说明：[`docs/repository-layout.md`](docs/repository-layout.md)
- 原型包 API：[`docs/pipeline-prototype.md`](docs/pipeline-prototype.md)
- 逻辑结构图：[`docs/diagrams/logic-structure.html`](docs/diagrams/logic-structure.html)

## 说明

- `archive/` 下的内容默认视为历史材料，不作为当前主线开发入口
- 运行时产生的向量库、上传文件、benchmark 数据不提交到 Git
- 仓库根部的 CI / Docker / 文档配置已经统一改为指向当前工作区结构
