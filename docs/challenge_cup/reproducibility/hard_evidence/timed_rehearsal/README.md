# Timed Rehearsal Evidence

放入真实计时彩排证据：计时截图、录屏、观察员备注或问题遗漏清单。
Required timing fields: opening_actual_seconds, demo_actual_seconds, offline_fallback_actual_seconds, killer_question_results.
Required JSON fields: evidence_type, rehearsal_date, observer, opening_actual_seconds, demo_actual_seconds, offline_fallback_actual_seconds, killer_question_results, recording_or_timer_source_path.
Use YYYY-MM-DD for rehearsal_date. recording_or_timer_source_path must point to the real timer screenshot, recording, or observer note, not the JSON summary itself.
Preferred CLI: `python scripts/run_challenge_cup_timed_rehearsal.py --id rehearsal-1 --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29 --confirm-real-rehearsal`.
Recommended CLI: `python scripts/record_challenge_cup_hard_evidence.py timed_rehearsal --id rehearsal-1 --source <real-timer-file> --evidence-type observer_note --rehearsal-date 2026-06-06 --observer observer-a --opening-actual-seconds 88 --demo-actual-seconds 170 --offline-fallback-actual-seconds 18 --killer-question-seconds 25 26 27 28 29`.
超时和答辩遗漏点必须保留，不能粉饰为通过。
