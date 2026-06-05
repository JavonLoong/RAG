# Hard Evidence Intake

这个目录只收纳真实专家反馈和真实计时彩排的原始或摘要证据。

- `expert_feedback/`: signed feedback, email replies, meeting minutes, or chat screenshots.
- `timed_rehearsal/`: timer screenshots, recordings, observer notes, or missed-question lists.
- Each category must include at least one JSON summary with the required metadata fields; screenshots or recordings alone do not satisfy the readiness gate.
- Record expert feedback with `python scripts/record_challenge_cup_hard_evidence.py expert_feedback ...`.
- Preferred timed rehearsal flow: `python scripts/run_challenge_cup_timed_rehearsal.py ... --confirm-real-rehearsal` generates an observer note from measured seconds and archives it.
- Record timed rehearsal evidence with `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal ...`.
- 不伪造证据；没有这两类真实证据前，不能标记目标完成。
