"""Hallucination Guard for GraphRAG.

Validates the final LLM generated answer against the retrieved evidence to
ensure no information was hallucinated or fabricated.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GuardResult:
    is_safe: bool
    hallucinated_claims: list[str]
    score: float


GUARD_PROMPT = """You are an strict fact-checking assistant. Your task is to evaluate whether a generated answer contains ANY claims that are NOT supported by the provided evidence.

## Retrieved Evidence:
{evidence}

## Generated Answer:
{answer}

## Instructions:
1. Carefully compare the generated answer against the retrieved evidence.
2. If the answer contains specific claims, numbers, facts, or entities that are NOT present in or logically deducible from the evidence, that is a hallucination.
3. Minor rephrasings are fine, but introducing new external information is strictly prohibited.
4. Respond with ONLY a valid JSON object matching exactly this structure:
{{
    "is_safe": true/false,
    "hallucinated_claims": ["claim 1", "claim 2"] // empty list if is_safe is true
}}
"""


class HallucinationGuard:
    """Detects hallucinations in LLM-generated answers."""

    def __init__(self, llm_client: Any) -> None:
        self.llm_client = llm_client

    def verify(self, answer: str, context: str) -> GuardResult:
        stripped_answer = answer.strip()
        stripped_context = context.strip()
        if not stripped_answer:
            return GuardResult(is_safe=True, hallucinated_claims=[], score=1.0)
        if not stripped_context:
            if self._is_no_answer_boundary(stripped_answer):
                return GuardResult(is_safe=True, hallucinated_claims=[], score=1.0)
            return GuardResult(
                is_safe=False,
                hallucinated_claims=["No retrieved evidence is available to support this answer."],
                score=0.0,
            )

        prompt = GUARD_PROMPT.format(evidence=stripped_context[:3000], answer=stripped_answer[:2000])

        try:
            response = self._call_llm(prompt)
            return self._parse_response(response)
        except Exception as exc:
            logger.warning("Hallucination guard failed, assuming safe. Error: %s", exc)
            # Default to safe if the guard fails to avoid breaking the pipeline
            return GuardResult(is_safe=True, hallucinated_claims=[], score=1.0)

    def _call_llm(self, prompt: str) -> str:
        for method_name in ("generate", "complete", "invoke"):
            method = getattr(self.llm_client, method_name, None)
            if callable(method):
                return str(method(prompt))
        if callable(self.llm_client):
            return str(self.llm_client(prompt))
        raise TypeError("LLM client must be callable or expose generate/complete/invoke.")

    def _parse_response(self, text: str) -> GuardResult:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            parsed = json.loads(text)
            is_safe = bool(parsed.get("is_safe", True))
            claims = parsed.get("hallucinated_claims", [])
            score = 1.0 if is_safe else 0.0
            return GuardResult(is_safe=is_safe, hallucinated_claims=claims, score=score)
        except json.JSONDecodeError:
            # Fallback heuristic
            if "false" in text.lower() or "hallucinated" in text.lower():
                return GuardResult(is_safe=False, hallucinated_claims=["Heuristic match: hallucination detected"], score=0.0)
            return GuardResult(is_safe=True, hallucinated_claims=[], score=1.0)

    @staticmethod
    def _is_no_answer_boundary(answer: str) -> bool:
        normalized = answer.casefold()
        boundary_patterns = (
            r"证据不足",
            r"无法回答",
            r"不能回答",
            r"没有检索到",
            r"未检索到",
            r"缺少(?:检索)?(?:结果|证据|上下文)",
            r"insufficient (?:retrieved )?evidence",
            r"not enough (?:retrieved )?evidence",
            r"no (?:retrieved )?(?:evidence|context|sources?)",
            r"cannot answer",
            r"can't answer",
            r"unable to answer",
        )
        return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in boundary_patterns)
