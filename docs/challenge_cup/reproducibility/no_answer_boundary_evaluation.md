# No-Answer Boundary Evaluation

- report_type: `challenge_cup_no_answer_boundary_evaluation`
- status: `no_answer_boundary_guard_verified_no_live_llm_claim`
- completion_claim_allowed: `False`
- does_not_satisfy_goal_completion: `True`
- external_validation_claimed: `False`
- live_retriever_claimed: `False`
- online_llm_behavior_claimed: `False`
- deterministic_guard_only: `True`

## Summary

- Guard: `rag_orchestrator.HallucinationGuard`
- Cases: 4
- Unsupported specific claims rejected: 1
- Explicit no-answer cases accepted: 2
- All cases passed: True

## Cases

| Case | Expected safe | Actual safe | Score | Risk | Claims |
| --- | ---: | ---: | ---: | --- | --- |
| `empty_context_specific_maintenance_claim` | False | False | 0.0 | unsupported specific maintenance conclusion | No retrieved evidence is available to support this answer. |
| `empty_context_chinese_no_answer` | True | True | 1.0 | safe no-answer boundary | none |
| `empty_context_english_no_answer` | True | True | 1.0 | safe no-answer boundary | none |
| `empty_context_empty_answer` | True | True | 1.0 | empty answer contains no unsupported claim | none |

## Example Safe Boundary Answer

证据不足，无法回答；需要补充检索结果或人工确认。

## Failures

- none

## Verification

- `python scripts/build_challenge_cup_no_answer_boundary_evaluation.py`
- `python scripts/check_challenge_cup_readiness.py`

## Boundary

This is a deterministic empty-context no-answer boundary evaluation for the local HallucinationGuard; it does not claim live retriever coverage, does not claim online LLM behavior, does not claim external validation, and does not satisfy goal completion without real expert feedback and real timed rehearsal evidence.
