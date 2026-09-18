from __future__ import annotations

from pathlib import Path


def test_model_adapters_prefer_local_model_directories(tmp_path: Path) -> None:
    from model_adapters.local_models import resolve_local_model_path

    local_root = tmp_path / "models"
    embedding_dir = local_root / "BAAI" / "bge-m3"
    reranker_dir = local_root / "BAAI" / "bge-reranker-v2-m3"
    embedding_dir.mkdir(parents=True)
    reranker_dir.mkdir(parents=True)

    assert Path(resolve_local_model_path("BAAI/bge-m3", local_roots=[local_root])) == embedding_dir
    assert (
        Path(resolve_local_model_path("BAAI/bge-reranker-v2-m3", local_roots=[local_root]))
        == reranker_dir
    )


def test_model_adapters_default_embedding_model_is_qwen3_0_6b(tmp_path: Path) -> None:
    from model_adapters.local_models import DEFAULT_EMBEDDING_MODEL, resolve_local_model_path

    local_root = tmp_path / "models"
    embedding_dir = local_root / "Qwen" / "Qwen3-Embedding-0.6B"
    embedding_dir.mkdir(parents=True)

    assert DEFAULT_EMBEDDING_MODEL == "Qwen/Qwen3-Embedding-0.6B"
    assert Path(resolve_local_model_path(None, local_roots=[local_root])) == embedding_dir


def test_model_adapters_default_reranker_model_is_small_bge_base(tmp_path: Path) -> None:
    from model_adapters.local_models import DEFAULT_RERANKER_MODEL, resolve_local_model_path

    local_root = tmp_path / "models"
    reranker_dir = local_root / "BAAI" / "bge-reranker-base"
    reranker_dir.mkdir(parents=True)

    assert DEFAULT_RERANKER_MODEL == "BAAI/bge-reranker-base"
    assert (
        Path(resolve_local_model_path(None, local_roots=[local_root], default_model=DEFAULT_RERANKER_MODEL))
        == reranker_dir
    )
