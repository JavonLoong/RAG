# ⚠️ 离线部署改动保护 — 请勿覆盖

> **提交人**: Ranhuiryan (qdgjhrh@outlook.com)
> **提交时间**: 2026-05-25
> **Commit**: `cfbedd3dd6dbcde4801f03d7aff5be546d276cdd`
> **说明**: `feat: enhance offline deployment with comprehensive setup script and environment configuration`

---

## ⚠️ 当前合并状态

**注意**: 该 commit (`cfbedd3d`) 目前在 GitLab 上存在，但尚未合并到我们本地的 `main` 分支。
我们本地的 `start_local.bat`、`embeddings.py`、`api.py`、`__main__.py` 等文件仍是旧版本。
在推送代码到 GitLab 时，**必须先 merge 或 rebase Ranhuiryan 的改动**，避免覆盖离线部署功能。

---

## 🚨 核心要求

**后续提交代码时，必须确保不覆盖以下离线部署相关改动。**
如需修改这些文件，请先与 @Ranhuiryan 确认，确保离线部署功能不受影响。

---

## 受保护的文件与改动清单

### 1. `start_local.bat` — 整文件重写（L1-228）

原脚本 53 行，仅做 Python 查找 + 启动。新脚本 228 行，包含 6 个阶段：

| 行范围 | 阶段 | 说明 |
|--------|------|------|
| L1-17 | 路径设置 | 计算 `REPO_ROOT`、`WHEELS_DIR`、`MODEL_DIR`、`VENV_DIR` 等关键路径 |
| L23-69 | 阶段 1：Python 检测 | 按优先级查找：已有 venv → PATH 中 3.11.x → 常见安装路径 → 提示安装 |
| L74-87 | 阶段 2：创建 venv | `python -m venv` 到项目根 `.venv/` |
| L92-154 | 阶段 3：离线安装依赖 | 3a 升级 pip → 3b CUDA torch 优先安装 → 3c requirements 安装 → 3d 关键模块验证 |
| L159-170 | 阶段 4：环境变量 | 设置 `PYTHONPATH`、`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、`POWER_RAG_EMBED_MODEL` |
| L175-195 | 阶段 5：诊断信息 | 打印 PyTorch 版本、CUDA 状态、GPU 型号、模型路径 |
| L200-228 | 阶段 6：启动服务 | 打开浏览器 + 运行 `server.py` |

**路径**: `api_server/current_console/start_local.bat`

### 2. `embeddings.py` — 3 处改动

| 行号 | 改动 |
|------|------|
| L13 | 新增 `import os` |
| L22 | 新增 `DEFAULT_EMBED_MODEL = os.environ.get("POWER_RAG_EMBED_MODEL") or "BAAI/bge-m3"` |
| L115 | `requested_model = model_name or DEFAULT_EMBED_MODEL`（原为 `"BAAI/bge-m3"`） |
| L156 | `requested_model = model_name or DEFAULT_EMBED_MODEL`（原为 `"BAAI/bge-m3"`） |

**路径**: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/embeddings.py`

### 3. `api.py` — 2 处改动

| 行号 | 改动 |
|------|------|
| L29 | 新增 `from .embeddings import DEFAULT_EMBED_MODEL` |
| L711 | `model_name: str = Form(DEFAULT_EMBED_MODEL)`（原为 `Form("BAAI/bge-m3")`） |

**路径**: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py`

### 4. `__main__.py` — 2 处改动

| 行号 | 改动 |
|------|------|
| L21 | 新增 `from .embeddings import DEFAULT_EMBED_MODEL` |
| L52 | `ingest_parser.add_argument("--model-name", default=DEFAULT_EMBED_MODEL)`（原为 `default="BAAI/bge-m3"`） |

**路径**: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/__main__.py`

### 5. `requirements_offline.txt` — 新增文件

完整离线 wheel 版本清单（90+ 包），L1-2 为 CUDA torch 优先安装项。

**路径**: `apps/jiwenlong-rag-console/offline/requirements_offline.txt`

### 6. `download_missing_wheels.bat` — 新增文件

联网环境补充缺失 wheel（`sniffio`、`Deprecated`）+ 临时 venv 验证完整性。

**路径**: `apps/jiwenlong-rag-console/offline/download_missing_wheels.bat`

### 7. `.gitignore` — 1 处改动

新增 `apps/jiwenlong-rag-console` 到忽略列表（离线资源目录，含模型和 wheel 包）。

---

## 环境变量

| 变量 | 用途 | 示例值 |
|------|------|--------|
| `POWER_RAG_EMBED_MODEL` | 离线嵌入模型目录路径（不设则回退到 `BAAI/bge-m3` HuggingFace Hub ID） | `D:\RAG\apps\jiwenlong-rag-console\models\bge-m3` |
| `HF_HUB_OFFLINE` | 禁止 HuggingFace Hub 下载 | `1` |
| `TRANSFORMERS_OFFLINE` | 禁止 transformers 自动下载 | `1` |
| `SENTENCE_TRANSFORMERS_HOME` | sentence-transformers 模型缓存目录 | `D:\RAG\apps\jiwenlong-rag-console\models` |

## 离线资源位置

```text
apps/jiwenlong-rag-console/
├─ models/bge-m3/                   # BGE-M3 嵌入模型文件（2.1GB）
├─ offline/
│  ├─ python-3.11.9-amd64.exe      # Python 安装包
│  ├─ wheels/                       # 离线 wheel 包（110+）
│  ├─ requirements_offline.txt      # 版本清单
│  └─ download_missing_wheels.bat   # 补充缺失 wheel 脚本
└─ data/                            # 预置数据（可选）
```

## GPU 支持

- 离线 wheel 包含 `torch-2.11.0+cu128`（CUDA 12.8），支持 RTX 5070 (Blackwell) 等新 GPU
- 需要 NVIDIA 显卡驱动 >= 570.x
- 如果 CUDA 不可用，启动脚本会自动回退到 CPU 模式
