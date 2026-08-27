# Task 1 review fix A2 report

## Scope

Closed the FMEA risk-confirmation contract gap and corrected the delayed scoring-test fixture construction.

- Modified: `core_domain/fmea/scoring.py`
- Modified: `tests/unit/test_fmea_scoring.py`
- Added: `.superpowers/sdd/2026-08-27-fmea-risk-closure/task-1-fix-a2-report.md`
- Not modified: all other source and test files

## RED evidence

The first console-script invocation could not collect tests because the pytest executable did not include the repository root on `sys.path`:

```text
ModuleNotFoundError: No module named 'core_domain'
```

The equivalent repository-interpreter invocation reached the delayed tests and recorded the required RED state:

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_scoring.py -q
10 failed, 17 passed in 0.18s
```

The failures were the expected missing behavior: RiskProposal placeholder defaults, confirmation fallback/binding gaps, and RiskAssessmentRecord status/dimension consistency gaps.

## GREEN evidence

After the minimal implementation and fixture/import cleanup:

```text
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_scoring.py -q
27 passed in 0.06s

.venv\Scripts\python.exe -m pytest <all tests/unit/test_fmea_review_*.py> tests/unit/test_fmea_scoring.py tests/unit/test_fmea_entities.py -q
162 passed, 1 skipped in 1.97s

.venv\Scripts\ruff.exe check core_domain/fmea/scoring.py tests/unit/test_fmea_scoring.py
exit code 0

git diff --check
exit code 0; CRLF normalization warnings only
```

## Implementation result

- RiskProposal now requires explicit identity, version, dimensions, reason, and timestamp fields; placeholder defaults are removed and non-empty/unique invariants are enforced.
- Confirmation requires actual ScoringRulePack and EvidencePack instances, binds proposal workspace/pack identities, accepts only the exact severity/occurrence/detection dimension set, validates every score and evidence ID, and returns the derived RiskAssessment.
- RiskAssessmentRecord rejects duplicate dimensions, forbids derived assessments for UNSCORED/PROPOSED/REVIEWED, and enforces complete CONFIRMED identity plus derived S/O/D/RPN/rule/evidence consistency. INVALIDATED requires a non-empty reason.
- Existing ScoringRulePack construction defaults and calculate_risk behavior remain compatible.
- No actor-ID prefix authentication logic was added.

## Commit

`fix(fmea): bind risk confirmation to evidence` — local commit only; no push performed.

## Self-check

- Write set: the two requested implementation/test files plus this report.
- RED and GREEN evidence recorded above.
- Direct FMEA scoring/entities/review regression matrix passed.
- Ruff and `git diff --check` passed.
