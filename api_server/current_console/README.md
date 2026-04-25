# Current RAG Console

这是当前可运行的 RAG 控制台后端与服务入口，已经从旧路径 `apps/jiwenlong-rag-console/` 迁移到 `api_server/current_console/`。

## 相关位置

```text
api_server/current_console/
├─ server.py                     # FastAPI 启动入口
├─ start_local.bat               # Windows 双击启动入口
├─ docs/
│  └─ user-guide.md              # 使用说明
├─ scripts/
│  ├─ benchmark_chroma.py        # Chroma 性能测试
│  ├─ generate_mock_data.py      # 生成模拟 JSON 数据
│  └─ smoke_test_api.py          # 本地接口烟测
├─ legacy/                       # 旧兼容入口
└─ chroma_rag_poc/
   ├─ pyproject.toml
   ├─ src/chroma_rag_poc/        # 核心包
   └─ tests/
```

前端页面已经迁移到：

```text
frontend_app/current_console/
```

运行数据已经迁移到：

```text
storage_layer/runtime/current_console/
├─ uploads/
├─ chroma/
├─ logs/
└─ mock-data/
```

## 启动方式

### Windows 双击

```text
api_server/current_console/start_local.bat
```

### 命令行

```powershell
cd "D:\虚拟C盘\RAG\api_server\current_console"
$env:PYTHONPATH="$PWD\chroma_rag_poc\src"
python server.py
```

启动后访问：

- 前端：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

## 说明

- `chroma_rag_poc` 包名暂时保持不动，减少导入和测试改动。
- 后端优先从 `frontend_app/current_console/` 挂载前端。
- 运行数据不再放在 API 代码目录中，而是由 `storage_layer/runtime/current_console/` 统一承接。
