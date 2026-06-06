# Runtime Reproducibility Snapshot

- report_type: `challenge_cup_runtime_reproducibility_snapshot`
- status: `runtime_snapshot_ready_no_environment_portability_claim`
- runtime_scope: local challenge-cup package reproduction environment
- completion_claim_allowed: `False`
- does_not_satisfy_goal_completion: `True`
- external_validation_claimed: `False`

## Python Runtime

- current executable: `D:\虚拟C盘\RAG\.venv\Scripts\python.exe`
- current version: `3.11.9`
- project python: `.venv/Scripts/python.exe`
- project venv present: `True`
- pytest probe: `pytest 8.4.2`

## Node And Browser Automation

- node version: `v22.17.0`
- package.json present: `True`
- package-lock.json present: `False`
- node_modules present: `True`
- Playwright source: `C:\Users\15410\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\.pnpm\playwright@1.60.0\node_modules\playwright`
- frontend URL: `unavailable`

## Repository Controls

- `docs/challenge_cup/package_manifest.json`
- `docs/challenge_cup/reproducibility/evidence_hashes.json`
- `docs/challenge_cup/reproducibility/challenge_cup_submission_archive_manifest.json`
- `docs/challenge_cup/reproducibility/verify_submission_package.py`

## Verification Commands

- `.\.venv\Scripts\python.exe docs/challenge_cup/reproducibility/verify_submission_package.py --root .`
- `.\.venv\Scripts\python.exe scripts/check_challenge_cup_readiness.py`
- `.\.venv\Scripts\python.exe -m pytest tests/unit -q`

## Boundary

This snapshot records the local runtime used to reproduce the challenge-cup package; it is not a production deployment certification, does not guarantee a special-prize result, and does not replace real expert feedback or real timed rehearsal evidence.
