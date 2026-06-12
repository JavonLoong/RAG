"""Embedding model adapters for RAG.

Provides a unified interface for text embedding, supporting both:
- Remote embedding APIs (OpenAI-compatible)
- Local models (sentence-transformers)
- Fallback hashing (for testing)
"""
from __future__ import annotations

import hashlib
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import requests

from .local_models import require_local_model_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    dimension: int


class BaseEmbeddingAdapter(ABC):
    """Base interface for all embedding adapters."""

    name = "base"

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts into vectors."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query text."""
        return self.embed([text])[0]


class OpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    """Embedding adapter using OpenAI-compatible API."""

    name = "openai"

    def __init__(
        self, *, api_key: str, base_url: str = "https://api.openai.com/v1",
        model: str = "text-embedding-3-small", timeout: float = 30.0, batch_size: int = 100,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.batch_size = batch_size
        self.session = requests.Session()

    def embed(self, texts: list[str]) -> list[list[float]]:
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            response = self.session.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"input": batch, "model": self.model},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            vectors = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
            all_vectors.extend(vectors)
        return all_vectors


class SentenceTransformerAdapter(BaseEmbeddingAdapter):
    """Embedding adapter using sentence-transformers local models."""

    name = "sentence_transformer"

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError("sentence-transformers required. Install with: pip install sentence-transformers") from exc
        resolved_model = require_local_model_path(model_name, env_var="RAG_EMBEDDING_MODEL_PATH")
        self.model_name = resolved_model
        self.model = SentenceTransformer(resolved_model, device=device)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()


class HashingEmbeddingAdapter(BaseEmbeddingAdapter):
    """Deterministic hashing-based embeddings for testing."""

    name = "hashing"

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_text(text) for text in texts]

    def _hash_text(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [((b / 255.0) * 2 - 1) for b in digest]
        while len(raw) < self.dimension:
            digest = hashlib.sha256(digest).digest()
            raw.extend(((b / 255.0) * 2 - 1) for b in digest)
        return raw[: self.dimension]


def build_embedding_from_env(
    *, default_model: str = "text-embedding-3-small", api_key_env: str = "OPENAI_API_KEY",
) -> BaseEmbeddingAdapter:
    """Build an embedding adapter from environment variables."""
    api_key = os.environ.get(api_key_env, "").strip()
    if api_key:
        return OpenAIEmbeddingAdapter(
            api_key=api_key,
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
            model=os.environ.get("EMBEDDING_MODEL", default_model).strip(),
        )
    logger.warning("No API key found for embedding, falling back to hashing.")
    return HashingEmbeddingAdapter()
