from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

API_PROJECT_ROOT = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc"
API_SRC_ROOT = API_PROJECT_ROOT / "src"
if str(API_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(API_SRC_ROOT))

from chroma_rag_poc.api import create_app  # noqa: E402


class FakeCompareRouterLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, **_: object) -> str:
        self.prompts.append(prompt)
        if "smart query router" in prompt:
            return '{"strategy":"COMPARE_SYNTHESIS","reason":"compare requested"}'
        raise AssertionError("context_only advanced API test should not synthesize an answer")

    def complete(self, prompt: str, **kwargs: object) -> str:
        return self.generate(prompt, **kwargs)


def test_unified_query_uses_advanced_compare_branch_for_electron_api() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tempdir:
        root = Path(tempdir)
        persist_dir = root / "chroma"
        upload_dir = root / "uploads"
        persist_dir.mkdir()
        upload_dir.mkdir()
        app = create_app(persist_dir=persist_dir, upload_dir=upload_dir)
        client = TestClient(app)
        fake_llm = FakeCompareRouterLLM()

        with patch("chroma_rag_poc.api.OpenAICompatibleLLMClient", return_value=fake_llm), patch(
            "chroma_rag_poc.api.query_collection",
            side_effect=lambda query_text, **_: {
                "results": [
                    {
                        "id": f"{query_text}-chunk",
                        "text": f"retrieved evidence for {query_text}",
                        "source": "manual.md",
                        "score": 0.9,
                        "metadata": {"source_file": "manual.md"},
                    }
                ]
            },
        ) as query_collection:
            response = client.post(
                "/api/query",
                json={
                    "question": "pump vs combustor risk",
                    "collection": "api-demo",
                    "llm_api_key": "test-key",
                    "mode": "auto",
                    "top_k": 2,
                    "context_only": True,
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["route"]["task_route"] == "COMPARE_SYNTHESIS"
    assert payload["advanced_mode"] == "COMPARE_SYNTHESIS"
    assert payload["answer"] is None
    assert {"pump", "combustor"}.issubset({row["object"] for row in payload["comparison_table"]})
    assert "| Object | Evidence count | Key evidence | Citations |" in payload["context"]
    assert payload["capabilities"]["router"] is True
    assert payload["capabilities"]["graph"] is False
    assert query_collection.call_count >= 2
