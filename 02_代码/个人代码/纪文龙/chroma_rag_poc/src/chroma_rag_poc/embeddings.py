"""
向量化后端 — 基于项目2架构，默认改为 BGE-m3

支持两种后端：
1. sentence-transformer (默认 BGE-m3，质量最高)
2. hashing (轻量降级，不需要 GPU/模型下载)

项目2 的自动降级机制保留：sentence-transformer 不可用时自动回退 hashing
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .text_utils import TOKEN_PATTERN, normalize_text


@dataclass(slots=True)
class ResolvedEmbeddingBackend:
    """已解析的向量化后端"""
    name: str
    model_name: str
    function: object
    dimension: int = 1024
    warning: str | None = None


class HashingEmbeddingFunction:
    """
    基于哈希的轻量向量化（来自项目2）。
    不需要 GPU 和模型下载，适合快速测试。
    """
    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in input]

    def _embed_text(self, text: str) -> list[float]:
        tokens = TOKEN_PATTERN.findall(normalize_text(text))
        vector = np.zeros(self.dimension, dtype=np.float32)
        if not tokens:
            return vector.tolist()
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], byteorder="little") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 8) / 8
            vector[index] += sign * weight
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector.tolist()


@lru_cache(maxsize=8)
def _resolve_embedding_backend(
    backend: str | None = None,
    model_name: str | None = None,
    dimension: int = 1024,
) -> ResolvedEmbeddingBackend:
    """
    创建向量化后端。
    
    默认使用 sentence-transformer + BGE-m3（项目1的选择，质量最高）。
    加载失败时自动降级到 hashing。
    """
    requested_backend = (backend or "sentence-transformer").strip().lower()
    requested_model = model_name or "BAAI/bge-m3"

    if requested_backend == "sentence-transformer":
        try:
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

            embedding_function = SentenceTransformerEmbeddingFunction(model_name=requested_model)
            # 推断维度
            dim = 1024 if "bge-m3" in requested_model else 384
            return ResolvedEmbeddingBackend(
                name="sentence-transformer",
                model_name=requested_model,
                function=embedding_function,
                dimension=dim,
            )
        except Exception as exc:
            warning = f"⚠️ sentence-transformer 不可用，降级到 hashing: {exc}"
            print(warning)
            return ResolvedEmbeddingBackend(
                name="hashing",
                model_name=f"hashing-{dimension}",
                function=HashingEmbeddingFunction(dimension=dimension),
                dimension=dimension,
                warning=warning,
            )

    # 明确请求 hashing
    return ResolvedEmbeddingBackend(
        name="hashing",
        model_name=f"hashing-{dimension}",
        function=HashingEmbeddingFunction(dimension=dimension),
        dimension=dimension,
    )


def create_embedding_backend(
    backend: str | None = None,
    model_name: str | None = None,
    dimension: int = 1024,
) -> ResolvedEmbeddingBackend:
    requested_backend = (backend or "sentence-transformer").strip().lower()
    requested_model = model_name or "BAAI/bge-m3"
    return _resolve_embedding_backend(requested_backend, requested_model, dimension)
