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


_patch_numpy_aliases_for_legacy_chromadb()
