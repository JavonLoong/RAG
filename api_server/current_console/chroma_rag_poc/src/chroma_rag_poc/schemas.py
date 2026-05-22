"""
数据结构定义 — 合并项目1/项目2

项目2 的 slots dataclass 结构
+ 项目1 的 label/page_num/doc_id 字段
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MetadataValue = str | int | float | bool


@dataclass(slots=True)
class TextBlock:
    """单个标注文本块（合并两版字段）"""
    text: str
    block_type: str          # "Title" / "Para" / "List"
    order: int
    page_num: int = -1       # ← 项目1: 页码
    doc_id: int = -1         # ← 项目1: 文档ID
    x: float = 0.0           # ← 项目2: 水平坐标
    y: float = 0.0           # ← 项目2: 纵坐标（用于排序）


@dataclass(slots=True)
class SourceRecord:
    """一个来源记录（一页 / 一个 task 的解析结果）"""
    source_file: str
    record_id: str
    filename: str
    page_num: int | None
    text: str
    blocks: list[TextBlock] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    total_pages: int = 0     # ← 项目1: 文档总页数
    doc_id: int = -1         # ← 项目1: 文档ID


@dataclass(slots=True)
class ChunkRecord:
    """向量化前的文本块"""
    chunk_id: str
    text: str
    metadata: dict[str, MetadataValue]
