"""Unified configuration management for the GraphRAG system.

Supports YAML/JSON config file loading with environment variable overrides.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LLMConfig:
    """LLM connection configuration."""
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    timeout: float = 60.0
    temperature: float = 0.0

    @classmethod
    def from_env(cls) -> LLMConfig:
        return cls(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
            timeout=float(os.environ.get("LLM_TIMEOUT", "60")),
            temperature=float(os.environ.get("LLM_TEMPERATURE", "0")),
        )


@dataclass(slots=True)
class EmbeddingConfig:
    """Embedding model configuration."""
    backend: str = "hashing"  # "openai" | "sentence_transformer" | "hashing"
    model: str = "text-embedding-3-small"
    dimension: int = 384

    @classmethod
    def from_env(cls) -> EmbeddingConfig:
        return cls(
            backend=os.environ.get("EMBEDDING_BACKEND", "hashing"),
            model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
            dimension=int(os.environ.get("EMBEDDING_DIMENSION", "384")),
        )


@dataclass(slots=True)
class StorageConfig:
    """Storage paths configuration."""
    chroma_persist_dir: str = "chroma_db"
    graph_db_path: str = "graph.sqlite3"
    upload_dir: str = "uploads"
    log_dir: str = "logs"

    @classmethod
    def from_env(cls) -> StorageConfig:
        return cls(
            chroma_persist_dir=os.environ.get("CHROMA_PERSIST_DIR", "chroma_db"),
            graph_db_path=os.environ.get("GRAPH_DB_PATH", "graph.sqlite3"),
            upload_dir=os.environ.get("UPLOAD_DIR", "uploads"),
            log_dir=os.environ.get("LOG_DIR", "logs"),
        )


@dataclass(slots=True)
class RetrievalConfig:
    """Retrieval parameters."""
    top_k: int = 5
    hybrid_alpha: float = 0.7
    max_scan_rows: int = 5000
    rerank_enabled: bool = False


@dataclass(slots=True)
class CommunityConfig:
    """Community detection parameters."""
    resolution: float = 1.0
    min_community_size: int = 2
    hierarchical_levels: list[float] = field(default_factory=lambda: [0.5, 1.0, 2.0])


@dataclass(slots=True)
class GraphRAGConfig:
    """Top-level configuration combining all sub-configs."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    community: CommunityConfig = field(default_factory=CommunityConfig)

    @classmethod
    def from_env(cls) -> GraphRAGConfig:
        return cls(
            llm=LLMConfig.from_env(),
            embedding=EmbeddingConfig.from_env(),
            storage=StorageConfig.from_env(),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> GraphRAGConfig:
        """Load config from a JSON file with env var overrides."""
        config_path = Path(path)
        if not config_path.exists():
            return cls.from_env()

        data = json.loads(config_path.read_text(encoding="utf-8"))
        config = cls.from_env()

        # Override from file
        if "llm" in data:
            for key, value in data["llm"].items():
                if hasattr(config.llm, key):
                    setattr(config.llm, key, value)
        if "embedding" in data:
            for key, value in data["embedding"].items():
                if hasattr(config.embedding, key):
                    setattr(config.embedding, key, value)
        if "storage" in data:
            for key, value in data["storage"].items():
                if hasattr(config.storage, key):
                    setattr(config.storage, key, value)
        if "retrieval" in data:
            for key, value in data["retrieval"].items():
                if hasattr(config.retrieval, key):
                    setattr(config.retrieval, key, value)
        if "community" in data:
            for key, value in data["community"].items():
                if hasattr(config.community, key):
                    setattr(config.community, key, value)

        return config

    def to_dict(self) -> dict[str, Any]:
        import dataclasses
        result = {}
        for f in dataclasses.fields(self):
            sub = getattr(self, f.name)
            result[f.name] = {
                sf.name: getattr(sub, sf.name)
                for sf in dataclasses.fields(sub)
            }
        return result
