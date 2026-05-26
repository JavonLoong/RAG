"""
纪文龙 RAG 控制台后端入口。

保持一个独立、可直接运行的入口脚本，避免启动时依赖旧目录命名。
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
SRC_DIR = APP_DIR / "chroma_rag_poc" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from chroma_rag_poc.api import create_app
from chroma_rag_poc.pipeline import DEFAULT_RUNTIME_DIR

DATA_DIR = DEFAULT_RUNTIME_DIR
PERSIST_DIR = DATA_DIR / "chroma"
UPLOAD_DIR = DATA_DIR / "uploads"
LOG_DIR = DATA_DIR / "logs"

app = create_app(
    persist_dir=PERSIST_DIR,
    upload_dir=UPLOAD_DIR,
    log_dir=LOG_DIR,
)


if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("动力装备知识库 RAG 控制台")
    print("前端: http://localhost:8000")
    print("API 文档: http://localhost:8000/docs")
    print(f"向量库目录: {PERSIST_DIR}")
    print(f"上传目录: {UPLOAD_DIR}")
    print(f"日志目录: {LOG_DIR}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
