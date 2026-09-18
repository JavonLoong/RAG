"""
向量化后端 — 基于项目2架构，默认改为 BGE-m3

支持两种后端：
1. sentence-transformer (默认 BGE-m3，质量最高)
2. hashing (轻量降级，不需要 GPU/模型下载)

项目2 的自动降级机制保留：sentence-transformer 不可用时自动回退 hashing
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .text_utils import TOKEN_PATTERN, normalize_text

DEFAULT_SENTENCE_TRANSFORMER_MODEL = "Qwen/Qwen3-Embedding-0.6B"
_MODEL_PATH_ENVS = ("RAG_EMBEDDING_MODEL_PATH", "RAG_SENTENCE_TRANSFORMER_MODEL_PATH")
_MODEL_ROOT_ENVS = ("RAG_LOCAL_MODEL_DIR", "RAG_MODELS_DIR", "RAG_MODEL_DIR")
_TRUE_VALUES = {"1", "true", "yes", "on"}


def resolve_sentence_transformer_model_path(
    model_name: str | None = None,
    *,
    local_roots: Iterable[str | os.PathLike[str]] | None = None,
) -> str:
    """Resolve a model id such as Qwen/Qwen3-Embedding-0.6B to a local offline directory."""
    requested = str(model_name or DEFAULT_SENTENCE_TRANSFORMER_MODEL).strip() or DEFAULT_SENTENCE_TRANSFORMER_MODEL

    for env_name in _MODEL_PATH_ENVS:
        for candidate in _split_path_env(os.environ.get(env_name)):
            if candidate.exists():
                return str(candidate.resolve())

    direct_path = Path(requested).expanduser()
    if direct_path.exists():
        return str(direct_path.resolve())

    for root in _iter_local_model_roots(local_roots):
        for relative in _candidate_model_paths(requested):
            candidate = root / relative
            if candidate.exists():
                return str(candidate.resolve())

    return requested


def _online_model_loading_allowed() -> bool:
    return os.environ.get("RAG_ALLOW_ONLINE_MODELS", "").strip().lower() in _TRUE_VALUES


def _sentence_transformer_runtime_enabled() -> bool:
    return os.environ.get("RAG_ENABLE_SENTENCE_TRANSFORMER_RUNTIME", "").strip().lower() in _TRUE_VALUES


def _is_existing_model_path(value: str | None) -> bool:
    if not value:
        return False
    try:
        path = Path(value).expanduser()
        if not path.exists():
            return False
        if path.is_file():
            return True
        markers = (
            "config.json",
            "modules.json",
            "sentence_bert_config.json",
            "model.safetensors",
            "pytorch_model.bin",
        )
        return any((path / marker).exists() for marker in markers)
    except OSError:
        return False


def _iter_local_model_roots(
    local_roots: Iterable[str | os.PathLike[str]] | None,
) -> Iterable[Path]:
    seen: set[Path] = set()
    for value in local_roots or ():
        root = Path(value).expanduser()
        if root not in seen:
            seen.add(root)
            yield root
    for env_name in _MODEL_ROOT_ENVS:
        for root in _split_path_env(os.environ.get(env_name)):
            if root not in seen:
                seen.add(root)
                yield root
    repo_root = Path(__file__).resolve().parents[5]
    package_root = Path(__file__).resolve().parents[2]
    for root in (
        repo_root / "models",
        repo_root / "local_models",
        package_root / "models",
        package_root / "local_models",
    ):
        if root not in seen:
            seen.add(root)
            yield root


def _split_path_env(value: str | None) -> list[Path]:
    if not value:
        return []
    return [Path(item).expanduser() for item in value.split(os.pathsep) if item.strip()]


def _candidate_model_paths(model_name: str) -> list[Path]:
    normalized = model_name.strip().strip("/\\")
    if not normalized:
        return []
    parts = [part for part in normalized.replace("\\", "/").split("/") if part]
    leaf = parts[-1] if parts else normalized
    candidates = [
        Path(*parts),
        Path(leaf),
        Path(normalized.replace("/", "__").replace("\\", "__")),
        Path(normalized.replace("/", "--").replace("\\", "--")),
    ]
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


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

    def embed_query(self, input: str | list[str]) -> list[float] | list[list[float]]:
        if isinstance(input, str):
            return self._embed_text(input)
        return self(input)

    @staticmethod
    def name() -> str:
        return "power_equipment_hashing"

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> dict[str, Any]:
        return {"dimension": self.dimension}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "HashingEmbeddingFunction":
        return HashingEmbeddingFunction(dimension=int(config.get("dimension") or 384))

    def is_legacy(self) -> bool:
        return False

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


def _normalize_backend_name(backend: str | None) -> str:
    requested = (backend or "sentence-transformer").strip().lower().replace("_", "-")
    aliases = {
        "sentence-transformers": "sentence-transformer",
        "hash": "hashing",
    }
    normalized = aliases.get(requested, requested)
    if normalized not in {"sentence-transformer", "hashing"}:
        raise ValueError(
            f"Unsupported embedding backend '{backend}'. Expected 'sentence-transformer' or 'hashing'."
        )
    return normalized


def infer_sentence_transformer_dimension(model_name: str | None = None) -> int:
    """Return the embedding dimension for known sentence-transformer families."""
    key = str(model_name or DEFAULT_SENTENCE_TRANSFORMER_MODEL).lower()
    if "qwen3-embedding-8b" in key:
        return 4096
    if "qwen3-embedding-4b" in key:
        return 2560
    if "qwen3-embedding-0.6b" in key:
        return 1024
    if "bge-m3" in key:
        return 1024
    return 384


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
    requested_backend = _normalize_backend_name(backend)
    requested_model = model_name or DEFAULT_SENTENCE_TRANSFORMER_MODEL

    if requested_backend == "sentence-transformer":
        resolved_model = resolve_sentence_transformer_model_path(requested_model)
        if (not _is_existing_model_path(resolved_model) or not _sentence_transformer_runtime_enabled()) and not _online_model_loading_allowed():
            warning = (
                f"Local sentence-transformer model not found for '{requested_model}', "
                "falling back to hashing. Set RAG_EMBEDDING_MODEL_PATH or "
                "RAG_LOCAL_MODEL_DIR, or set RAG_ENABLE_SENTENCE_TRANSFORMER_RUNTIME=1 "
                "after verifying the local sentence-transformer runtime."
            )
            print(warning)
            return ResolvedEmbeddingBackend(
                name="hashing",
                model_name=f"hashing-{dimension}",
                function=HashingEmbeddingFunction(dimension=dimension),
                dimension=dimension,
                warning=warning,
            )
        try:
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

            embedding_function = SentenceTransformerEmbeddingFunction(model_name=resolved_model)
            dim_key = f"{requested_model} {resolved_model}".lower()
            dim = infer_sentence_transformer_dimension(dim_key)
            return ResolvedEmbeddingBackend(
                name="sentence-transformer",
                model_name=resolved_model,
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
    requested_backend = _normalize_backend_name(backend)
    requested_model = model_name or DEFAULT_SENTENCE_TRANSFORMER_MODEL
    return _resolve_embedding_backend(requested_backend, requested_model, dimension)
