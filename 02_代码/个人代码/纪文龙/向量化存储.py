"""
纪文龙 — 向量化存储 Pipeline v3.0 → v2.0 兼容入口

本文件保留向后兼容性。
实际逻辑已重构到 chroma_rag_poc 模块化包中。
"""
import sys
from pathlib import Path

# 将新模块加入 Python 路径
_src_dir = Path(__file__).parent / "chroma_rag_poc" / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# 重新导出原有接口（保持兼容）
from chroma_rag_poc.schemas import TextBlock, ChunkRecord as Chunk, SourceRecord as Document
from chroma_rag_poc.parsing import load_json_file as parse_json, load_json_directory as parse_json_batch
from chroma_rag_poc.cleaning import clean_records as clean_blocks
from chroma_rag_poc.chunking import chunk_records as chunk_document


def main():
    """向后兼容入口：调用新的 CLI"""
    from chroma_rag_poc.__main__ import main as new_main
    new_main()


if __name__ == "__main__":
    main()
