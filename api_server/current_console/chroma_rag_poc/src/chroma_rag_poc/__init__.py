"""
chroma_rag_poc — 动力装备知识库 RAG Pipeline
合并版：项目2模块化架构 + 项目1核心功能(混合检索/Title分块/暗色前端)
"""

from __future__ import annotations


def _patch_numpy_aliases_for_legacy_chromadb() -> None:
    """Allow ChromaDB 0.5.x to import under NumPy 2.x in existing environments."""
    try:
        import numpy as np
    except Exception:
        return

    aliases = {
        "float_": "float64",
        "complex_": "complex128",
    }
    for alias, replacement in aliases.items():
        try:
            getattr(np, alias)
        except AttributeError:
            try:
                setattr(np, alias, getattr(np, replacement))
            except AttributeError:
                pass


def _patch_chromadb_sqlite_int_seq_id() -> None:
    """Allow ChromaDB 0.5.x to read stores whose seq_id is returned as int."""
    try:
        import chromadb.segment.impl.metadata.sqlite as sqlite_metadata
    except Exception:
        return

    original = getattr(sqlite_metadata, "_decode_seq_id", None)
    if getattr(original, "_powerrag_accepts_int_seq_id", False):
        return

    def _decode_seq_id_compat(seq_id_bytes: object) -> object:
        if isinstance(seq_id_bytes, int):
            return seq_id_bytes
        if original is None:
            if isinstance(seq_id_bytes, (bytes, bytearray, memoryview)):
                return int.from_bytes(bytes(seq_id_bytes), "big")
            return seq_id_bytes
        return original(seq_id_bytes)

    setattr(_decode_seq_id_compat, "_powerrag_accepts_int_seq_id", True)
    setattr(sqlite_metadata, "_decode_seq_id", _decode_seq_id_compat)


_patch_numpy_aliases_for_legacy_chromadb()
_patch_chromadb_sqlite_int_seq_id()
