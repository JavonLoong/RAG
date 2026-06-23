from __future__ import annotations

import sys
from pathlib import Path


def test_engine_bridge_default_embedding_adapter_uses_small_qwen3_sentence_transformer(monkeypatch) -> None:
    console_src = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
    if str(console_src) not in sys.path:
        sys.path.insert(0, str(console_src))

    from chroma_rag_poc import engine_bridge
    import model_adapters.embedding as embedding

    class FakeSentenceTransformerAdapter:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

    monkeypatch.setattr(embedding, "SentenceTransformerAdapter", FakeSentenceTransformerAdapter)

    adapter = engine_bridge.get_embedding_adapter()

    assert isinstance(adapter, FakeSentenceTransformerAdapter)
    assert adapter.model_name == "Qwen/Qwen3-Embedding-0.6B"
