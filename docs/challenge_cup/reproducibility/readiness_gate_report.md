# Challenge Cup Readiness Gate

- Status: `pass`
- Passed: 25/25
- Scope: challenge-cup package docs, control files, numeric consistency, GraphRAG evidence audit, GraphRAG context demo, GraphRAG answer benchmark, claim-evidence matrix, acceptance checklist, special-prize rubric, expert review index, defense rehearsal pack, defense rehearsal scorecard, defense rehearsal result packet, expert feedback request packet, application validation, fixed scenario demo, scenario walkthrough script, expert feedback protocol, evaluation dataset, evaluation coverage profile, evidence manifest, evidence hashes, live smoke, browser smoke, screenshots, KG artifact links

| Gate | Result | Evidence |
| --- | --- | --- |
| package documents | pass | all required challenge cup docs exist |
| package control files | pass | 2 control files exist, are git-tracked, and are clean |
| 60 evaluation questions | pass | 60 evaluation questions |
| evaluation coverage profile | pass | 60 questions across 11 task types, 17 source scopes, 10 GraphRAG-tagged questions |
| package evidence files | pass | 32 evidence files exist, are git-tracked, and are clean; 60 questions |
| evidence integrity hashes | pass | 31 evidence hashes verified; excluded=['docs/challenge_cup/reproducibility/readiness_gate_report.md'] |
| numeric consistency | pass | 60 questions, 32 evidence files, and 5 visible search records are consistent |
| graphrag evidence audit | pass | 3 supported, 3 partial, 4 missing cases over 240 triples |
| graphrag context demo | pass | 3 context-only cases with text and graph citations |
| graphrag answer benchmark | pass | 10 fixed GraphRAG answer cases; supported=3, missing=4, graph_avg=0.3 |
| claim-evidence matrix | pass | award claims mapped to evidence, commands, and boundaries; 23 evidence links verified |
| acceptance checklist | pass | submission materials, acceptance steps, offline fallback, boundaries, and conclusion verified; 13 evidence links verified |
| special-prize rubric self-assessment | pass | public Tsinghua rubric dimensions mapped to evidence; 16 evidence links verified |
| expert review index | pass | judge-facing review path maps claims, commands, and boundaries; 20 evidence links verified |
| defense rehearsal pack | pass | timed defense script, killer questions, and boundaries mapped to evidence; 17 evidence links verified |
| defense rehearsal scorecard | pass | 5 timed demo steps, 5 killer questions, 12 evidence files |
| defense rehearsal result packet | pass | 5 killer-question templates, 6 evidence files, no actual result claimed |
| expert feedback request packet | pass | 3 recipient roles, 8 review questions, 13 evidence files |
| application validation evidence | pass | fixed GT-07 application case, evidence records, benefits, and boundaries verified; 9 evidence links verified |
| scenario demo evidence | pass | fixed abnormal-vibration query returns 5 GT-07 evidence records with human-confirmation boundary |
| scenario walkthrough script | pass | fixed scenario walkthrough, fallback screenshot, evidence records, and human-confirmation boundary verified; 8 evidence links verified |
| expert feedback protocol | pass | feedback form, integrity boundary, archival rule, and remediation loop verified; 10 evidence links verified |
| live demo smoke checks | pass | 5/5 checks pass |
| browser smoke checks | pass | 13/13 checks pass |
| browser visual evidence | pass | 4 screenshots, 4 KG artifacts, and 5 visible search records verified |

## Required Browser Checks

KG SVG render, KG artifact links, assets route, deliverables route, desktop console health, desktop not blank, health endpoint, libs route, mobile console health, mobile not blank, page identity, search interaction, search results visible

## Boundary

This gate proves package readiness and demo evidence completeness. It does not claim final award probability; judges still evaluate innovation, presentation, and live defense quality.
