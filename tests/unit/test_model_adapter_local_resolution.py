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
