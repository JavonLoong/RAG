# 硬证据台账

- report_type: `challenge_cup_hard_evidence_ledger`
- status: `awaiting_real_external_feedback_and_timed_rehearsal`
- completion_claim_allowed: `False`
- 边界：真实专家反馈和真实计时彩排尚未同时归档前，不伪造，不能标记目标完成。

## 必须归档的真实证据

| Category | Required Records | Evidence Records | Raw Files | Intake Dir |
| --- | ---: | ---: | ---: | --- |
| expert_feedback | 1 | 0 | 0 | `docs/challenge_cup/reproducibility/hard_evidence/expert_feedback` |
| timed_rehearsal | 1 | 0 | 0 | `docs/challenge_cup/reproducibility/hard_evidence/timed_rehearsal` |

## 原则

- 不伪造外部意见
- 不把内部自评写成专家背书
- 没有真实专家反馈和真实计时彩排前，不能标记目标完成

## 证据文件

- 尚未归档真实附件。

## Rerun Commands

- `python scripts/build_challenge_cup_hard_evidence_ledger.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`
