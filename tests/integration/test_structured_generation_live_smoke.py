from __future__ import annotations

import hashlib
import json
import os

import pytest

from core_domain.structured_generation import GenerationRunStatus, StructuredModelResponse
from scripts.structured_generation_skill import run_live_smoke


class FakeGateway:
    def __init__(self) -> None:
        self.calls = []

    def complete(self, request, *, max_attempts, timeout_seconds):
        self.calls.append((request, max_attempts, timeout_seconds))
        content = json.dumps({
            "template_id": "deepseek-connectivity-smoke",
            "template_version": "1.0.0",
            "template_hash": "0" * 64,
            "evidence_pack_id": "smoke-pack",
            "candidates": [{"candidate_id": "smoke-candidate", "payload": {"message": "ok"}, "claims": []}],
        })
        return StructuredModelResponse(
            content=content,
            model_id="deepseek-v4-flash",
            finish_reason="stop",
            input_tokens=10,
            output_tokens=5,
            response_hash=hashlib.sha256(content.encode()).hexdigest(),
            http_attempts=1,
        )


def test_fake_smoke_uses_one_flash_call_and_strict_decode() -> None:
    gateway = FakeGateway()

    result = run_live_smoke(gateway=gateway)

    assert result.status is GenerationRunStatus.SUCCEEDED
    assert result.model_id == "deepseek-v4-flash"
    assert len(gateway.calls) == 1
    assert gateway.calls[0][0].thinking_enabled is False


@pytest.mark.live_deepseek
def test_live_deepseek_smoke() -> None:
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY is not configured")
    assert run_live_smoke().status is GenerationRunStatus.SUCCEEDED
