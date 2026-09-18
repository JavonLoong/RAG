# Open Source 90 Quality Gate

This gate turns the "reach 90% of mature open-source RAG/GraphRAG quality" target into a repeatable local command.

Run:

```powershell
npm run quality:90
```

Run the external benchmark counterpart:

```powershell
npm run quality:90:external
```

The command currently checks:

- base local readiness through `npm run check`;
- the strict `open_source_90` evaluation profile;
- RAG harness behavior under the strict thresholds;
- GraphRAG graph quality guardrails;
- a seeded promoted GraphRAG triage regression fixture for full private-contact analysis;
- a generated target report in `evaluation/reports/`.

## Target Metrics

- citation coverage: 100%;
- source page accuracy: at least 95%;
- no-answer precision: at least 90%;
- recall@10: at least 90%;
- reranked top-3 evidence hit rate: at least 85%;
- hallucination rate: at most 2%;
- permission leak: 0;
- secret leak: 0.

## Important Limit

Passing this gate means the project wiring and local guardrails are healthy and the promoted regression path is not empty. It does not prove the real corpus has reached 90% quality until an expert gold set or external benchmark run is attached to the same profile.

For the WeChat broad-analysis class of questions, the gate should be expanded with promoted cases that force full-contact analysis, not top-k-only answers.

## External Benchmark Gate

`npm run quality:90:external` runs downloaded public RAG benchmarks through the local pipeline and compares the aggregate score, per-benchmark score, keyword recall, and no-result rate against the `open_source_90` profile. This command is allowed to fail while the system is below target; the failure report is the evidence used to drive retrieval improvements.

Latest external probes:

- Date: 2026-06-21
- Legal 10 after field-split keyword cleanup: PASS, `96.83 / 100`, keyword recall `0.983333`, report `evaluation/reports/open_source_90_external_benchmark_gate_open_source_90_probe_legal10_field_split_keywords.md`.
- Legal 50 before query expansion: FAIL, `49.0 / 100`, keyword recall `0.5`, report `evaluation/reports/open_source_90_external_benchmark_gate_open_source_90_probe_legal50_field_split_keywords.md`.
- Legal 50 after query expansion v1: FAIL, `66.37 / 100`, keyword recall `0.736667`, report `evaluation/reports/open_source_90_external_benchmark_gate_open_source_90_probe_legal50_query_expansion_v1.md`.
- Interpretation: the local smoke gate is healthy and the first external fixes are working, but Legal 50 still contradicts any claim that the full system has reached 90% market-level quality.

## Latest Local Verification

- Date: 2026-06-21
- Command: `npm run quality:90`
- Result: PASS
- Checks: base `npm run check` with 32 focused smoke tests, 16 strict quality/profile/regression tests, seeded promoted GraphRAG triage regression (`case_count=1`), and target report generation.
- Generated report: `evaluation/reports/open_source_90_gate_20260621_143108.md`
- Gap: the seeded private-contact case prevents empty regression passes, but broad WeChat/contact-level questions still need real promoted cases or an expert gold set before claiming actual 90% corpus quality.
