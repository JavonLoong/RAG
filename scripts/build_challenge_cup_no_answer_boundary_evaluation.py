from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rag_orchestrator import HallucinationGuard

OUTPUT_MD_RELATIVE = "docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.md"
OUTPUT_JSON_RELATIVE = "docs/challenge_cup/reproducibility/no_answer_boundary_evaluation.json"
OUTPUT_MD = REPO_ROOT / OUTPUT_MD_RELATIVE
OUTPUT_JSON = REPO_ROOT / OUTPUT_JSON_RELATIVE

REPORT_TYPE = "challenge_cup_no_answer_boundary_evaluation"
STATUS = "no_answer_boundary_guard_verified_no_live_llm_claim"
BOUNDARY = (
    "This is a deterministic empty-context no-answer boundary evaluation for the local HallucinationGuard; "
    "it does not claim live retriever coverage, does not claim online LLM behavior, does not claim external "
    "validation, and does not satisfy goal completion without real expert feedback and real timed rehearsal evidence."
)

CASES = [
    {
        "case_id": "empty_context_specific_maintenance_claim",
        "question": "Can GT-07 continue operating after abnormal compressor vibration?",
        "context": "",
        "answer": (
            "GT-07 should continue running because the vibration is caused only by a harmless sensor drift."
        ),
        "expected_safe": False,
        "risk": "unsupported specific maintenance conclusion",
    },
    {
        "case_id": "empty_context_chinese_no_answer",
        "question": "GT-07 是否可以复机？",
        "context": "",
        "answer": "证据不足，无法回答；需要补充检索结果或人工确认。",
        "expected_safe": True,
        "risk": "safe no-answer boundary",
    },
    {
        "case_id": "empty_context_english_no_answer",
        "question": "Which component failed in the compressor?",
        "context": "",
        "answer": "Insufficient retrieved evidence; cannot answer without source records.",
        "expected_safe": True,
        "risk": "safe no-answer boundary",
    },
    {
        "case_id": "empty_context_empty_answer",
        "question": "What is the exact restart threshold?",
        "context": "",
        "answer": "",
        "expected_safe": True,
        "risk": "empty answer contains no unsupported claim",
    },
]


class NoLiveLLM:
    def __call__(self, prompt: str) -> str:
        raise RuntimeError(f"no-answer boundary evaluation must not call a live LLM: {prompt[:120]}")


def repo_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def evaluate_cases() -> list[dict[str, Any]]:
    guard = HallucinationGuard(NoLiveLLM())
    results: list[dict[str, Any]] = []
    for case in CASES:
        result = guard.verify(str(case["answer"]), str(case["context"]))
        passed = result.is_safe is case["expected_safe"]
        results.append(
            {
                **case,
                "actual_safe": result.is_safe,
                "score": result.score,
                "hallucinated_claims": result.hallucinated_claims,
                "passed": passed,
            }
        )
    return results


def build_payload() -> dict[str, Any]:
    cases = evaluate_cases()
    failures = [
        f"{case['case_id']}: expected_safe={case['expected_safe']} actual_safe={case['actual_safe']}"
        for case in cases
        if not case["passed"]
    ]
    unsafe_specific_claims = [
        case["case_id"] for case in cases if case["expected_safe"] is False and case["actual_safe"] is False
    ]
    no_answer_safe_cases = [
        case["case_id"]
        for case in cases
        if case["expected_safe"] is True and case["actual_safe"] is True and str(case["answer"]).strip()
    ]
    return {
        "report_type": REPORT_TYPE,
        "status": STATUS if not failures else "no_answer_boundary_guard_failed",
        "completion_claim_allowed": False,
        "does_not_satisfy_goal_completion": True,
        "external_validation_claimed": False,
        "live_retriever_claimed": False,
        "online_llm_behavior_claimed": False,
        "deterministic_guard_only": True,
        "guard": "rag_orchestrator.HallucinationGuard",
        "case_count": len(cases),
        "unsafe_specific_claim_count": len(unsafe_specific_claims),
        "safe_no_answer_count": len(no_answer_safe_cases),
        "all_cases_passed": not failures,
        "cases": cases,
        "failures": failures,
        "boundary": BOUNDARY,
        "verification_commands": [
            "python scripts/build_challenge_cup_no_answer_boundary_evaluation.py",
            "python scripts/check_challenge_cup_readiness.py",
        ],
        "output_files": [OUTPUT_MD_RELATIVE, OUTPUT_JSON_RELATIVE],
    }


def build_markdown(payload: dict[str, Any]) -> str:
    rows = [
        "| Case | Expected safe | Actual safe | Score | Risk | Claims |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for case in payload["cases"]:
        claims = "<br>".join(case["hallucinated_claims"]) or "none"
        rows.append(
            f"| `{case['case_id']}` | {case['expected_safe']} | {case['actual_safe']} | "
            f"{case['score']:.1f} | {case['risk']} | {claims} |"
        )
    failures = "\n".join(f"- {failure}" for failure in payload["failures"]) or "- none"
    commands = "\n".join(f"- `{command}`" for command in payload["verification_commands"])
    return f"""# No-Answer Boundary Evaluation

- report_type: `{payload["report_type"]}`
- status: `{payload["status"]}`
- completion_claim_allowed: `{payload["completion_claim_allowed"]}`
- does_not_satisfy_goal_completion: `{payload["does_not_satisfy_goal_completion"]}`
- external_validation_claimed: `{payload["external_validation_claimed"]}`
- live_retriever_claimed: `{payload["live_retriever_claimed"]}`
- online_llm_behavior_claimed: `{payload["online_llm_behavior_claimed"]}`
- deterministic_guard_only: `{payload["deterministic_guard_only"]}`

## Summary

- Guard: `{payload["guard"]}`
- Cases: {payload["case_count"]}
- Unsupported specific claims rejected: {payload["unsafe_specific_claim_count"]}
- Explicit no-answer cases accepted: {payload["safe_no_answer_count"]}
- All cases passed: {payload["all_cases_passed"]}

## Cases

{chr(10).join(rows)}

## Example Safe Boundary Answer

证据不足，无法回答；需要补充检索结果或人工确认。

## Failures

{failures}

## Verification

{commands}

## Boundary

{payload["boundary"]}
"""


def write_outputs(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or build_payload()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(payload).rstrip() + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = write_outputs()
    print(f"Wrote {repo_path(OUTPUT_MD)}")
    print(f"Wrote {repo_path(OUTPUT_JSON)}")
    print(f"Status: {payload['status']}")
    return 0 if payload["all_cases_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
