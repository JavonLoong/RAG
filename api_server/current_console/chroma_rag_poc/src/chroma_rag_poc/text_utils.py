"""
文本工具函数 — 来自项目2，直接复用

包括：文本规范化、稳定哈希、token 估算、集合名安全化
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

# 中文字符 + 英文单词 + 单个非空白字符
TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+(?:[-./][A-Za-z0-9_]+)*|[^\s]")


def normalize_text(text: str) -> str:
    """
    Unicode NFKC 规范化 + 空白字符清理。
    避免同一文本因编码差异被重复索引。
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\u3000]+", " ", line).strip() for line in normalized.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def estimate_token_count(text: str) -> int:
    """基于正则的中文 token 估算"""
    cleaned = normalize_text(text)
    if not cleaned:
        return 0
    return len(TOKEN_PATTERN.findall(cleaned))


def stable_hash(value: str) -> str:
    """SHA256 哈希，保证 chunk ID 全局唯一且稳定"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_collection_name(value: str) -> str:
    """集合名安全化：去除特殊字符"""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", (value or "").strip()).strip("-_").lower()
    return cleaned or "power-equipment"


def get_directory_size(path: Path) -> int:
    """计算目录总大小（字节）"""
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def format_megabytes(byte_count: int) -> float:
    """字节转 MB"""
    return round(byte_count / 1024 / 1024, 3)
