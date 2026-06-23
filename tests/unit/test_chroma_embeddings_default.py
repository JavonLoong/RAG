from __future__ import annotations

import sys
from pathlib import Path


def test_chroma_embeddings_default_to_small_qwen3_model(tmp_path: Path) -> None:
    console_src = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
    if str(console_src) not in sys.path:
        sys.path.insert(0, str(console_src))

    from chroma_rag_poc.embeddings import (
        DEFAULT_SENTENCE_TRANSFORMER_MODEL,
        infer_sentence_transformer_dimension,
        resolve_sentence_transformer_model_path,
    )

    local_root = tmp_path / "models"
    model_dir = local_root / "Qwen" / "Qwen3-Embedding-0.6B"
    model_dir.mkdir(parents=True)

    assert DEFAULT_SENTENCE_TRANSFORMER_MODEL == "Qwen/Qwen3-Embedding-0.6B"
    assert infer_sentence_transformer_dimension(None) == 1024
    assert Path(resolve_sentence_transformer_model_path(local_roots=[local_root])) == model_dir
