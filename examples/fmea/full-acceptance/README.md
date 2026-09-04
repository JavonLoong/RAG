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

The existing governance publisher stores row/risk/graph identity summaries in
its normalized snapshot, so this connected fixture's published documents show
those identity projections. Detailed field, score, evidence, and graph DTOs are
available in `evidence.json` and independently hash-bound to those summaries.
This is not a claim that the publisher already emits a formatted engineering
FMEA body report; rich adapter projections are exercised separately below.

Fuel/combustion exercises the connected lifecycle. Electrical/software packs
exercise the same compiler/registries here and typed extension serialization and
three-format export in `test_fmea_cross_domain_acceptance.py`; those structural
checks do not certify complete domain-specific risk policies.

The 10,000-row scale test is separate so ordinary smoke acceptance stays small.
JSON `iter_chunks` bounds emitted chunks, while snapshot validation, normalized
projection, Office libraries, and the legacy ExportService may materialize full
data. No constant-total-memory claim is made.
