# Hard Evidence Intake

这个目录只收纳真实专家反馈和真实计时彩排的原始或摘要证据。

- `expert_feedback/`: signed feedback, email replies, meeting minutes, or chat screenshots.
- `timed_rehearsal/`: timer screenshots, recordings, observer notes, or missed-question lists.
- Each category must include at least one JSON summary with the required metadata fields; screenshots or recordings alone do not satisfy the readiness gate.
- Preflight expert feedback with `python scripts/preflight_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback` before recording.
- Record expert feedback with `python scripts/record_challenge_cup_hard_evidence.py expert_feedback ... --confirm-real-feedback`.
- Preferred timed rehearsal flow: `python scripts/run_challenge_cup_timed_rehearsal.py ... --source <real-timer-or-observer-file> --confirm-real-rehearsal` archives an independent real timer or observer attachment.
- Preflight source-based timed rehearsal evidence with `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal` before source-based recording.
- Record timed rehearsal evidence with `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal ... --confirm-real-rehearsal`.
- Recording and preflight `--source` paths must be the original external attachments, not files already inside `docs/challenge_cup/reproducibility/hard_evidence/**`.
- Within each category, duplicate `source_sha256` values are rejected so one attachment cannot count as multiple hard evidence records.
- If a previously recorded item must be replaced, `--force` requires a non-empty `--force-reason` and appends an audit entry to `docs/challenge_cup/reproducibility/hard_evidence/override_log.jsonl`.
- 不伪造证据；没有这两类真实证据前，不能标记目标完成。
