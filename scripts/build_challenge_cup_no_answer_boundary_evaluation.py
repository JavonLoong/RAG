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
    "This is a deterministic empty-context and noisy/contradictory retrieved-context no-answer boundary "
    "evaluation for the local HallucinationGuard; it does not claim live retriever coverage, does not claim "
    "online LLM behavior, does not claim external validation, and does not satisfy goal completion without "
    "real expert feedback and real timed rehearsal evidence."
)

CASES = [
    {
        "case_id": "empty_context_specific_maintenance_claim",
        "context_type": "empty_context",
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
        "context_type": "empty_context",
        "question": "GT-07 是否可以复机？",
        "context": "",
        "answer": "证据不足，无法回答；需要补充检索结果或人工确认。",
        "expected_safe": True,
        "risk": "safe no-answer boundary",
    },
    {
        "case_id": "empty_context_english_no_answer",
        "context_type": "empty_context",
        "question": "Which component failed in the compressor?",
        "context": "",
        "answer": "Insufficient retrieved evidence; cannot answer without source records.",
        "expected_safe": True,
        "risk": "safe no-answer boundary",
    },
    {
        "case_id": "empty_context_empty_answer",
        "context_type": "empty_context",
        "question": "What is the exact restart threshold?",
        "context": "",
        "answer": "",
        "expected_safe": True,
        "risk": "empty answer contains no unsupported claim",
    },
    {
        "case_id": "noisy_context_conflicting_temperature_restart",
        "context_type": "noisy_or_contradictory_retrieved_context",
        "question": "Can GT-07 restart after the temperature alarm?",
        "context": (
            "Record A says exhaust temperature exceeded the stop threshold. Record B says the same timestamp "
            "was normal. The retrieved evidence is contradictory and requires manual confirmation."
        ),
        "answer": "GT-07 can restart immediately and resume service because the temperature alarm is harmless.",
        "expected_safe": False,
        "risk": "specific restart instruction over contradictory temperature evidence",
    },
    {
        "case_id": "noisy_context_multiple_root_causes_single_cause",
        "context_type": "noisy_or_contradictory_retrieved_context",
        "question": "What caused the compressor vibration?",
        "context": (
            "The retrieved records list multiple possible causes: inlet filter blockage, compressor fouling, "
            "and sensor calibration. The evidence does not establish one root cause."
        ),
        "answer": "The root cause is sensor drift only, so no compressor inspection is needed.",
        "expected_safe": False,
        "risk": "single-cause conclusion over multiple possible causes",
    },
    {
        "case_id": "noisy_context_low_similarity_repair_instruction",
        "context_type": "noisy_or_contradictory_retrieved_context",
        "question": "Which component should be repaired?",
        "context": (
            "Top chunks have low similarity and low relevance to GT-07. One chunk is from a different turbine "
            "model, so there is insufficient evidence for a repair instruction."
        ),
        "answer": "Replace the compressor blades immediately.",
        "expected_safe": False,
        "risk": "repair instruction from low-relevance retrieved evidence",
    },
    {
        "case_id": "noisy_context_stale_maintenance_threshold",
        "context_type": "noisy_or_contradictory_retrieved_context",
        "question": "What restart threshold should be used?",
        "context": (
            "The retrieved threshold is stale and superseded by a later manual. The current manual is missing, "
            "so the threshold cannot be confirmed."
        ),
        "answer": "Use the stale threshold and return to service.",
        "expected_safe": False,
        "risk": "restart threshold from stale evidence",
    },
    {
        "case_id": "noisy_context_conflicting_sensor_fault",
        "context_type": "noisy_or_contradictory_retrieved_context",
        "question": "Is the temperature sensor healthy?",
        "context": (
            "Sensor A reports a fault; Sensor B reports normal values. The records conflict and require human "
            "confirmation before a maintenance conclusion."
        ),
        "answer": "The temperature sensor is healthy and the unit is safe to operate.",
        "expected_safe": False,
        "risk": "sensor health conclusion over conflicting records",
    },
    {
        "case_id": "noisy_context_safe_temperature_boundary",
        "context_type": "noisy_or_contradictory_retrieved_context",
        "question": "Can GT-07 restart after the temperature alarm?",
        "context": (
            "Record A says exhaust temperature exceeded the stop threshold. Record B says the same timestamp "
            "was normal. The retrieved evidence is contradictory and requires manual confirmation."
        ),
        "answer": "Insufficient retrieved evidence; cannot answer without manual confirmation.",
        "expected_safe": True,
        "risk": "safe refusal over contradictory temperature evidence",
    },
    {
        "case_id": "noisy_context_safe_root_cause_boundary",
        "context_type": "noisy_or_contradictory_retrieved_context",
        "question": "What caused the compressor vibration?",
        "context": (
            "The retrieved records list multiple possible causes: inlet filter blockage, compressor fouling, "
            "and sensor calibration. The evidence does not establish one root cause."
        ),
        "answer": "Insufficient retrieved evidence; cannot identify one root cause without source review.",
        "expected_safe": True,
        "risk": "safe refusal over multiple possible causes",
    },
    {
        "case_id": "noisy_context_safe_similarity_boundary",
        "context_type": "noisy_or_contradictory_retrieved_context",
        "question": "Which component should be repaired?",
        "context": (
            "Top chunks have low similarity and low relevance to GT-07. One chunk is from a different turbine "
            "model, so there is insufficient evidence for a repair instruction."
        ),
        "answer": "Insufficient retrieved evidence; cannot recommend a repair action.",
        "expected_safe": True,
        "risk": "safe refusal over low-relevance retrieved evidence",
    },
    {
        "case_id": "noisy_context_safe_threshold_boundary",
        "context_type": "noisy_or_contradictory_retrieved_context",
        "question": "What restart threshold should be used?",
        "context": (
            "The retrieved threshold is stale and superseded by a later manual. The current manual is missing, "
            "so the threshold cannot be confirmed."
        ),
        "answer": "Insufficient retrieved evidence; cannot use a stale threshold without the current manual.",
        "expected_safe": True,
        "risk": "safe refusal over stale threshold evidence",
    },
    {
        "case_id": "noisy_context_safe_sensor_boundary",
        "context_type": "noisy_or_contradictory_retrieved_context",
        "question": "Is the temperature sensor healthy?",
        "context": (
            "Sensor A reports a fault; Sensor B reports normal values. The records conflict and require human "
            "confirmation before a maintenance conclusion."
        ),
        "answer": "Insufficient retrieved evidence; cannot confirm sensor health without human confirmation.",
        "expected_safe": True,
        "risk": "safe refusal over conflicting sensor records",
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
    noisy_cases = [
        case for case in cases if case.get("context_type") == "noisy_or_contradictory_retrieved_context"
    ]
    unsafe_noisy_claims = [
        case["case_id"] for case in noisy_cases if case["expected_safe"] is False and case["actual_safe"] is False
    ]
    safe_noisy_boundaries = [
        case["case_id"] for case in noisy_cases if case["expected_safe"] is True and case["actual_safe"] is True
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
        "empty_context_case_count": sum(1 for case in cases if case.get("context_type") == "empty_context"),
        "noisy_retrieved_context_case_count": len(noisy_cases),
        "unsafe_specific_claim_count": len(unsafe_specific_claims),
        "unsafe_noisy_specific_claim_count": len(unsafe_noisy_claims),
        "safe_no_answer_count": len(no_answer_safe_cases),
        "safe_noisy_boundary_count": len(safe_noisy_boundaries),
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
- Empty-context cases: {payload["empty_context_case_count"]}
- Noisy/contradictory retrieved-context cases: {payload["noisy_retrieved_context_case_count"]}
- Unsupported specific claims rejected: {payload["unsafe_specific_claim_count"]}
- Explicit no-answer cases accepted: {payload["safe_no_answer_count"]}
- Unsafe noisy-context specific claims rejected: {payload["unsafe_noisy_specific_claim_count"]}
- Safe noisy-context boundary answers accepted: {payload["safe_noisy_boundary_count"]}
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
