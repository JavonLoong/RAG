# Jiwenlong RAG Console

这一套代码现在统一放在 `apps/jiwenlong-rag-console/` 下，目标是把纪文龙这条 PoC 线整理成一个独立、可运行、便于 GitLab 展示的最小应用单元。

## 目录说明

```text
apps/jiwenlong-rag-console/
├─ server.py                     # FastAPI 启动入口
├─ start_local.bat               # Windows 双击启动入口
├─ frontend/
│  └─ index.html                 # 单文件前端
├─ data/
│  ├─ uploads/                   # 上传暂存
│  ├─ chroma/                    # Chroma 持久化目录
│  └─ mock-data/                 # 可选的测试样例
├─ docs/
│  └─ user-guide.md              # 使用说明
├─ scripts/
│  ├─ benchmark_chroma.py        # Chroma 性能测试
│  ├─ generate_mock_data.py      # 生成模拟 JSON 数据
│  └─ smoke_test_api.py          # 本地接口烟测
├─ legacy/
│  ├─ console_legacy.py          # 旧控制台入口
│  ├─ vector_store_legacy.py     # 旧兼容入口
│  └─ save_results_legacy.py     # 旧结果导出脚本
└─ chroma_rag_poc/
   ├─ pyproject.toml
   ├─ src/chroma_rag_poc/        # 核心包
   └─ tests/
```

## 启动方式

### Windows 双击

直接运行：

```text
apps/jiwenlong-rag-console/start_local.bat
```

### 命令行

```powershell
cd "D:\虚拟C盘\RAG项目_动力装备知识库\apps\jiwenlong-rag-console"
$env:PYTHONPATH="$PWD\chroma_rag_poc\src"
python server.py
```

启动后访问：

- 前端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

## 常用脚本

生成模拟数据：

```powershell
python .\scripts\generate_mock_data.py
```

接口烟测：

```powershell
python .\scripts\smoke_test_api.py
```

性能测试：

```powershell
python .\scripts\benchmark_chroma.py
```

## 命名整理原则

- 入口文件统一改成英文、可读、可搜索的命名。
- 运行数据统一收口到 `data/`，不再混在代码目录里。
- 一次性实验脚本放到 `scripts/`。
- 兼容性脚本单独放到 `legacy/`，避免和当前主流程混在一起。
- 核心包 `chroma_rag_poc` 暂时保持包名不动，减少导入和测试改动。
