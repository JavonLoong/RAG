import os
import sys
import zipfile
import shutil
from pathlib import Path

# 添加源码路径
REPO_ROOT = Path(r"d:\虚拟C盘\RAG")
sys.path.insert(0, str(REPO_ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"))

from chroma_rag_poc.public_books_json import ingest_latest_snapshot_to_chroma
from chroma_rag_poc.pipeline import DEFAULT_PERSIST_DIR

input_root = r"D:\虚拟C盘\清华云盘_专业书籍_20260524\解压后"
persist_dir = r"C:\Users\15410\AppData\Local\PowerRAG\current_console\chroma"
collection_name = "professional_books"
zip_path = r"C:\Users\15410\Desktop\完整的数据库_全量入库完成.zip"

print(f"============================================================")
print(f" 开始执行后台数据直连入库...")
print(f" 数据来源: {input_root}")
print(f" 目标库: {persist_dir}")
print(f"============================================================\n")

try:
    summary = ingest_latest_snapshot_to_chroma(
        input_root=input_root,
        persist_dir=persist_dir,
        collection_name=collection_name,
        mode="append",
        chunk_size=500,
        overlap=50
    )
    print("\n[OK] 数据入库完成！")
    print(f"写入了 {summary.get('chunks_written', 0)} 个块。耗时: {summary.get('elapsed_s', 0):.1f} 秒。")
except Exception as e:
    print(f"入库过程中出现错误: {e}")
    sys.exit(1)

print("\n开始打包数据库文件，请稍候...")
try:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(persist_dir):
            for f in files:
                full = os.path.join(root, f)
                arc = os.path.relpath(full, persist_dir)
                zf.write(full, f"chroma/{arc}")
    print(f"\n============================================================")
    print(f" 🎉 大功告成！文件已生成至桌面:")
    print(f" 👉 {zip_path}")
    print(f"============================================================")
except Exception as e:
    print(f"打包时出现错误: {e}")
