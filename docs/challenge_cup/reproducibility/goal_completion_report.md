# Challenge Cup Goal Completion Gate

- Status: `fail`
- Package readiness: `False` (readiness report status is not pass)
- Hard evidence complete: `False`
- completion_claim_allowed=False
- hard_evidence_status: `awaiting_real_external_feedback_and_timed_rehearsal`

## Required Hard Evidence

- `expert_feedback`: 真实专家反馈
- `timed_rehearsal`: 真实计时彩排

## Blocking Items

- completion_claim_allowed=False
- hard evidence status=awaiting_real_external_feedback_and_timed_rehearsal
- expert_feedback: missing 真实专家反馈; collected_count=0
- expert_feedback: evidence_files below required minimum
- expert_feedback: metadata json missing
- timed_rehearsal: missing 真实计时彩排; collected_count=0
- timed_rehearsal: evidence_files below required minimum
- timed_rehearsal: metadata json missing

## Next Actions

| Category | What to collect | Recording command | Acceptance signal |
| --- | --- | --- | --- |
| `expert_feedback` | 真实专家签字反馈、邮件回复、会议纪要或聊天截图，且包含 reviewer identity、role/org、review dimensions 和整改记录。 | `python scripts/record_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback` | `hard_evidence_ledger.categories.expert_feedback.collected_count >= 1` |
| `timed_rehearsal` | 真实计时截图、录屏、观察员记录或问题遗漏清单，且满足 90 秒开场、3 分钟演示、20 秒离线切换和 5 个杀手问题计时要求。 | `python scripts/run_challenge_cup_timed_rehearsal.py ... --confirm-real-rehearsal` | `hard_evidence_ledger.categories.timed_rehearsal.collected_count >= 1` |

Closeout checklist: `docs/challenge_cup/reproducibility/external_evidence_closeout_checklist.md`

After real evidence is recorded, rerun:

- `python scripts/build_challenge_cup_hard_evidence_ledger.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`
- `python scripts/check_challenge_cup_goal_completion.py`

Do not mark the goal complete until the final command returns `Status: pass` and `completion_claim_allowed=True`.

## Boundary

本报告区分 package readiness 与目标完成。没有真实专家反馈和真实计时彩排前，不能标记目标完成，也不能把 readiness gate 说成获奖保证。
