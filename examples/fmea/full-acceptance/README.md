# Full FMEA offline acceptance

This directory contains runnable fixtures, not a second implementation of FMEA.
The entry point is `scripts/run_fmea_full_acceptance.py` from the repository root.

The source is synthetic: a versioned fuel-filter EvidencePack and deterministic
candidate/review/risk/propagation model responses. Profile selection uses the
existing query contract. No live RAG index, external model, or private project
document is needed. This is an application-contract acceptance, not a retrieval
quality benchmark, an engineering diagnosis, or certification.

The lifecycle shares one temporary SQLite database and immutable registries:

1. Candidate generation, field review and confirmed S/O/D risk.
2. Topology-bounded propagation proposal and human review.
3. Real revision assembly, human approval and publication.
4. Actual export runs, artifact-store verification, JSON/XLSX/DOCX delivery.
5. Template import and explicit human-confirmed migration to a draft child.
6. A separately approved child publication, supersession and withdrawal.
7. Idempotent replay and persisted audit/outbox collection.

The public output contains `manifest.json`, `evidence.json`, `exports/`, and the
plain source template `inputs/template.xlsx` (bound to the draft source hash).
The source template is intentionally distinct from the presentation XLSX:
presentation print-area defined names are rejected by the strict importer.
Private runtime databases and registries are not copied into it. A fresh pending
directory is verified before publication; failed partial directories never
advance `latest.json`. The independent verifier does not import these helpers.

The publication-body implementation stores version-bound FMEA fields, confirmed
risk, propagation, public evidence quotes, and review/approval summaries in an
immutable normalized snapshot. The saved template layout drives the reading
sections of XLSX and DOCX; the original machine-readable typed tables remain.
The Word machine appendix retains wide tables and is not a polished reading
section. Exact types and complete values remain available in canonical JSON.

Task 5 extends this runner and its independent verifier to compare those bodies
against approved native records in `evidence.json`, not merely compare export
hashes with one another. It also validates the visible XLSX/DOCX reading body,
pinned report layout and retrieval provenance. Completion evidence, package
version compatibility and the final artifact ID are recorded in
`docs/handoff/fmea-publication-body-task5.md`; this README remains descriptive,
not a substitute for that recorded test result. The public offline bundle is
not signed external evidence against an attacker who can rewrite every native
record and the entire bundle.

Fuel/combustion exercises the connected lifecycle. Electrical/software packs
exercise the same compiler/registries here and typed extension serialization and
three-format export in `test_fmea_cross_domain_acceptance.py`; those structural
checks do not certify complete domain-specific risk policies.

The 10,000-row scale test is separate so ordinary smoke acceptance stays small.
JSON `iter_chunks` bounds emitted chunks, while snapshot validation, normalized
projection, Office libraries, and the legacy ExportService may materialize full
data. No constant-total-memory claim is made.
