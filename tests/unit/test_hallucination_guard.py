from __future__ import annotations

from rag_orchestrator import HallucinationGuard


class RaisingLLM:
    def __call__(self, prompt: str) -> str:
        raise AssertionError(f"LLM should not be called for empty-context boundary checks: {prompt}")


def test_hallucination_guard_rejects_specific_answer_without_context() -> None:
    guard = HallucinationGuard(RaisingLLM())

    result = guard.verify(
        "GT-07 should continue running because the vibration is caused only by a harmless sensor drift.",
        "",
    )

    assert result.is_safe is False
    assert result.score == 0.0
    assert any("No retrieved evidence" in claim for claim in result.hallucinated_claims)


def test_hallucination_guard_allows_explicit_no_answer_without_context() -> None:
    guard = HallucinationGuard(RaisingLLM())

    result = guard.verify("证据不足，无法回答；需要补充检索结果或人工确认。", "")

    assert result.is_safe is True
    assert result.score == 1.0
    assert result.hallucinated_claims == []


def test_hallucination_guard_keeps_empty_answer_safe_without_context() -> None:
    guard = HallucinationGuard(RaisingLLM())

    result = guard.verify("", "")

    assert result.is_safe is True
    assert result.score == 1.0
    assert result.hallucinated_claims == []
