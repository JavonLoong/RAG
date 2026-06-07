# Timed Rehearsal Evidence

放入真实计时彩排证据：计时截图、录屏、观察员备注或问题遗漏清单。
Required timing fields: opening_actual_seconds, demo_actual_seconds, offline_fallback_actual_seconds, killer_question_results.
Acceptance timing limits: opening_actual_seconds <= 90, demo_actual_seconds <= 180, offline_fallback_actual_seconds <= 20, each killer-question actual_seconds <= 30, exactly five killer questions.
Required JSON fields: evidence_type, rehearsal_date, observer, opening_actual_seconds, demo_actual_seconds, offline_fallback_actual_seconds, killer_question_results, recording_or_timer_source_path, source_sha256, source_origin, real_rehearsal_confirmed.
Use YYYY-MM-DD for rehearsal_date; it must not be in the future. recording_or_timer_source_path must point to the real timer screenshot, recording, or observer note, not the JSON summary itself.
observer must be non-empty text.
The source attachment must be non-empty and must not be a JSON metadata file.
source_sha256 must match the source attachment content.
During preflight/record, --source must not point inside docs/challenge_cup/reproducibility/hard_evidence/**; duplicate source_sha256 values in this category are rejected.
If --force is used to replace an existing evidence item, --force-reason is mandatory and the replacement is recorded in hard_evidence/override_log.jsonl.
source_origin must be external_attachment; generated observer notes are archived but do not count.
Preferred CLI: `python scripts/run_challenge_cup_timed_rehearsal.py --id <real-rehearsal-id> --source <real-timer-or-observer-file> --rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`.
Preflight CLI: `python scripts/preflight_challenge_cup_hard_evidence.py timed_rehearsal --id <real-rehearsal-id> --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`.
Recommended CLI: `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id <real-rehearsal-id> --source <real-timer-or-observer-file> --evidence-type observer_note --rehearsal-date <real-rehearsal-date-yyyy-mm-dd> --observer <real-observer-alias> --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 25 25 25 25 --confirm-real-rehearsal`.
超时和答辩遗漏点必须保留，不能粉饰为通过。
