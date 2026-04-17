"""
纪文龙 — 动力装备知识库 管理后端 兼容入口

实际逻辑已迁移到 chroma_rag_poc.api 模块。
"""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

# 将新模块加入 Python 路径
_src_dir = Path(__file__).parent / "chroma_rag_poc" / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from chroma_rag_poc.api import create_app

# 使用旧路径作为数据目录（向后兼容）
BASE_DIR = Path(__file__).parent
app = create_app(
    persist_dir=BASE_DIR / "向量数据库",
    upload_dir=BASE_DIR / "uploads",
)

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 动力装备知识库管理系统 v2.0")
    print(f"   前端: http://localhost:8000")
    print(f"   API 文档: http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
