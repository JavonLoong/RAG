# 提交完整性快照

本卡给评委、导师和结项接收人一页式复核入口：先确认包在哪里，再确认 hash / verifier / readiness / hard-evidence boundary。它不替代 manifest，也不承诺获奖。

## Package Snapshot

| Item | Current Value | Verification Source |
| --- | --- | --- |
| package path | `docs/challenge_cup/reproducibility/challenge_cup_submission_package.zip` | `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json` |
| archive manifest | `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json` | records archive bytes, file_count and sha256 |
| evidence hash manifest | `docs/challenge_cup/reproducibility/evidence_hashes.json` | records per-evidence sha256 except self reports |
| package manifest | `docs/challenge_cup/package_manifest.json` | records evidence_files, question_count and archive paths |
| offline verifier | `docs/challenge_cup/reproducibility/verify_submission_package.py --root .` | expected pass before handoff |

## Review Status

| Gate | Expected Result | Evidence |
| --- | --- | --- |
| readiness gate | pass `64/64` | `docs/challenge_cup/reproducibility/readiness_gate_report.md` |
| submission verifier | pass | `docs/challenge_cup/reproducibility/verify_submission_package.py` |
| final acceptance audit | `package_ready_awaiting_external_hard_evidence` | `docs/challenge_cup/reproducibility/final_acceptance_audit.md` |
| goal completion expected fail | fail until hard evidence is archived | `docs/challenge_cup/reproducibility/goal_completion_report.md` |

## Hard Evidence Boundary

- 真实专家反馈：尚未归档，必须按 `docs/challenge_cup/reproducibility/external_evidence_execution_kit.md` 采集真实来源。
- 真实计时彩排：尚未归档，必须按 `docs/challenge_cup/reproducibility/external_evidence_execution_kit.md` 记录真实观察与计时。
- 不承诺获奖；readiness gate、verifier、manifest 和本卡只证明提交包完整、可复核、边界清楚。

## One-command Verification

```powershell
.\.venv\Scripts\python.exe docs\challenge_cup\reproducibility\verify_submission_package.py --root .
.\.venv\Scripts\python.exe scripts\check_challenge_cup_readiness.py
.\.venv\Scripts\python.exe scripts\build_challenge_cup_final_acceptance_audit.py
.\.venv\Scripts\python.exe scripts\check_challenge_cup_goal_completion.py
```

生成时间：2026-06-05 21:06
