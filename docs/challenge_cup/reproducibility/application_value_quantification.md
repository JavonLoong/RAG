# Application Value Quantification

## Fixed Scenario

- Scenario: GT-07 abnormal-vibration diagnosis evidence chain.
- Source browser smoke: `docs/challenge_cup/reproducibility/browser_demo_smoke_report.json`
- Source application report: `docs/challenge_cup/reproducibility/application_validation_report.md`
- Collection: `gas_turbine_ocr_demo_snapshot`
- Retrieval latency: 41.8 ms
- Returned records: 5
- Visible records: 5
- Indexed scale: 2,655 chunks / 1,185,989 tokens
- Workflow contrast: 5.0x evidence consolidation

## Evidence Chain

| Stage | Record | Visible | Role |
| --- | --- | --- | --- |
| threshold_screening | `demo-maint-thresholds-076` | yes | threshold and early-warning screening |
| mechanism_explanation | `demo-structure-fault-130` | yes | mechanical-failure mechanism explanation |
| case_symptom | `demo-gt07-fault-021` | yes | GT-07 abnormal-vibration symptom |
| repair_result | `demo-gt07-repair-022` | yes | inspection, repair action, and restart result |
| disposition_recommendation | `demo-gt07-manual-023` | yes | maintenance checklist draft and human-confirmation boundary |

## Judge Value Claims

- `practical_value`: The fixed GT-07 scenario turns an abstract RAG demo into a five-stage maintenance evidence chain.
- `review_efficiency`: Five manual evidence lookup stages are consolidated into one visible result page with record IDs.
- `risk_boundary`: The quantified scenario keeps engineer confirmation and external validation boundaries explicit.

## Verification

- `python scripts/build_challenge_cup_application_value_quantification.py`
- `python scripts/build_challenge_cup_package.py`
- `python scripts/check_challenge_cup_readiness.py`

## Boundary

This is a local application-value quantification over the fixed GT-07 browser-smoke scenario; it is not a production validation, does not replace engineers, provides no external validation claim, and does not replace real expert feedback or real timed rehearsal evidence.
