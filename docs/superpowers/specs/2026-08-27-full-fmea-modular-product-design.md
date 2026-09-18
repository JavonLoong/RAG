# Full FMEA Modular Product Gap-Closure Design

**Status:** USER_REVIEW

**Date:** 2026-08-27

**Baseline branch:** `feat/interface-output-v1`

**Baseline commit:** `4841fd958e3bb5f0c0b10ce4308ae3c5ccbad15e`

**Predecessor:** `docs/superpowers/specs/2026-08-23-graphrag-fmea-system-design.md`

## 1. Decision and purpose

The owner is responsible for the complete FMEA subsystem, not only its review or output interface. The complete responsibility starts when an upstream RAG or GraphRAG implementation supplies a versioned `EvidencePack` and ends when a human-approved immutable FMEA revision is published and exported.

This specification closes the gap between the current branch and a complete, reusable FMEA product. It preserves the predecessor specification's evidence, authority, versioning, security, and audit semantics. Where the predecessor grouped work by the original project phases, this document controls the current gap-driven decomposition and modular extension model.

The chosen architecture is a modular monolith with extraction-ready ports. Fuel and combustion systems are the first `DomainPack`; they are not embedded in the generic FMEA kernel. Scoring, propagation, review, approval, publication, migration, export, and the workbench remain separate capabilities even when deployed in one process.

## 2. Goals

The product must:

1. consume immutable ordinary-RAG, GraphRAG, combined, or custom evidence without depending on one retrieval backend;
2. create evidence-bound FMEA candidates under immutable template and domain rules;
3. support deterministic and human-confirmed S/O/D, RPN, decision priority, and alternative risk methods;
4. analyze typed, evidence-bound, bounded fault propagation across fuel and combustion systems;
5. allow an external model to assist every human stage without granting the model review, approval, publication, or template-administration authority;
6. separate field review, risk confirmation, propagation confirmation, revision approval, and publication;
7. publish immutable, replayable revisions and generate canonical JSON, XLSX, and DOCX from one normalized snapshot;
8. add future FMEA domains through versioned `DomainPack` manifests, declarative templates, rule packs, adapters, and explicit migrations;
9. run locally with the current simple account and SQLite while preserving ports for enterprise identity, PostgreSQL, worker queues, and additional model providers;
10. expose the same application behavior through REST, CLI, Codex Skill, and a thin browser workbench.

## 3. Non-goals and external dependencies

The FMEA subsystem does not own OCR, parsing, chunking, source publication, vector indexing, graph extraction, community detection, or generic question answering. Those systems provide stable citations, versions, ACL information, and retrieval provenance through existing query and evidence contracts.

The product is an auditable engineering-assistance system, not a certified safety authority. Internal fixtures and model evaluations do not replace domain-expert validation, organizational approval, or regulatory certification.

The first release does not become a general QMS, work-order system, arbitrary workflow platform, digital twin, full FTA engine, or unrestricted low-code runtime. Templates and rule packs cannot execute arbitrary JavaScript, Python, SQL, network requests, loops, or cross-workspace queries.

## 4. Current implementation baseline

| Capability | Current state at the baseline | Gap controlled by this specification |
| --- | --- | --- |
| Evidence selection | Implemented for `rag_only`, GraphRAG local/global, `graphrag_only`, `combined`, `auto`, and `custom` | Preserve exact profile/type validation and incomplete/warning semantics |
| EvidencePack | Implemented with immutable identity, versions, ACL, refs, and hashes | Add revision lineage for explicit supplemental-evidence cycles |
| Generic structured templates | Implemented with compilation, canonical hash, immutable file registry, and evidence bindings | Package templates and policies inside a versioned DomainPack lifecycle |
| Structured generation | Implemented with provider-neutral ports, DeepSeek Flash generation, Pro criticism, and at most one repair | Generalize assistance contracts to scoring, propagation, migration, approval preparation, and report drafting |
| FMEA candidate adaptation | Implemented for ten non-scored fuel/combustion fields | Add typed extension fields and preserve existing canonical field compatibility |
| Review interface | Implemented with sanitized context, immutable model suggestion, human decision, optimistic locking, idempotency, SQLite, REST, CLI, and audit | Integrate risk, propagation, revision approval, publication, and withdrawal without creating a second authority path |
| Risk scoring | Pure domain rule-pack and calculation primitives exist | Add proposal, confirmation, invalidation, persistence, APIs, and publish gates |
| Propagation | Edge value object and validation policy exist | Add topology ports, candidate analysis, path review, persistence, APIs, and publish gates |
| Approval/publication | Not connected to the current review slice | Add immutable revision approval, publication manifest, withdrawal, and supersession |
| Template migration | Compile/register CLI exists | Add DomainPack registry, import drafts, mapping patches, compatibility checks, and dry-run migrations |
| Export/workbench | Not connected to the current review slice | Add normalized snapshot, JSON/XLSX/DOCX adapters, and thin workbench |

Existing evidence membership, projection-safe model views, pack identity, strict current/legacy audit decoding, stable error codes, and human-only decision rules are compatibility requirements. Later work must not weaken them.

## 5. Architecture

```text
Upstream evidence boundary
  QueryService / compatible provider
              |
              v
  EvidencePack + RetrievalProvenance
              |
              v
Generic FMEA kernel
  Analysis / Row / FieldClaim / Revision
  RiskAssessment / PropagationGraph
  Review / Approval / Publication / Audit
              |
              v
Capability services
  CandidateGenerationService
  RiskAssessmentService
  PropagationAnalysisService
  ReviewService
  RevisionGovernanceService
  DomainPackService
  ExportService
              |
              v
Domain packs
  fuel-combustion@1.x
  future electrical / software / medical / custom packs
              |
              v
Infrastructure adapters
  DeepSeek / future model gateway
  SQLite / future PostgreSQL
  local auth / future enterprise identity
  JSON / XLSX / DOCX
  REST / CLI / Skill / browser workbench
```

Dependencies point inward. The generic kernel imports no retrieval implementation, DeepSeek code, database driver, office library, UI code, or fuel/combustion-specific module. Capability services depend on kernel contracts and ports. Domain packs depend on public kernel contracts but do not modify kernel state directly. Infrastructure adapters implement ports and remain replaceable.

The modular monolith records additive domain events in the same transaction as state changes through a local outbox. No message broker is required initially. A future deployment may publish the outbox and extract scoring, propagation, export, or model workers without changing command identities or event payloads.

## 6. Canonical data model

### 6.1 Stable core

The current `FmeaAnalysis`, `FmeaRow`, `EvidencePack`, `RiskAssessment`, and `PropagationEdge` identities remain stable. Existing canonical row fields remain directly readable:

- item;
- function;
- failure mode;
- causes;
- mechanisms;
- effects;
- symptoms;
- controls;
- barriers;
- recommended actions.

New domains add typed values through `FieldValue(field_key, value_type, value)` where `field_key` is namespaced, such as `gas_turbine.fuel.wobbe_index`. A compiled template validates every extension value. Unvalidated arbitrary dictionaries are not part of the domain contract.

`FieldClaim` binds one canonical or extension field to a claim status, support status, evidence IDs, uncertainty, and optional conflict references. An empty or incomplete EvidencePack may support `unknown` or `insufficient_evidence`; it cannot support a `known` claim.

### 6.2 Independent artifacts

Risk and propagation are separate versioned artifacts rather than mutable fields hidden inside model output:

- `RiskAssessmentRecord` binds a row revision, scoring rule pack, proposal source, confirmed scores, derived values, evidence, confirmer, and status;
- `PropagationGraphRevision` binds an analysis revision, topology snapshot, propagation rule pack, nodes, edges, paths, evidence, reviewer decisions, and status;
- `AssistanceSuggestion` binds a target type and target version to immutable model output and remains `applied=false`;
- `ApprovalDecision` applies to an exact revision hash;
- `PublicationManifest` identifies the immutable approved snapshot and all version bindings.

### 6.3 Version envelope

Every generated, reviewed, approved, published, migrated, or exported artifact records:

- schema ID and schema version;
- DomainPack ID and version;
- template ID, version, and hash;
- scoring rule pack ID, version, and hash when scoring applies;
- propagation rule pack ID, version, and hash when propagation applies;
- EvidencePack IDs and hashes;
- source document and graph versions;
- prompt and model versions for model-assisted content;
- parent revision ID and content hash;
- actor, request, trace, and run identities.

## 7. Orthogonal state axes

One mega-state is prohibited. The following axes are stored independently and constrained by policies:

| Axis | States |
| --- | --- |
| Content review | `draft`, `suggested`, `in_review`, `accepted`, `rejected`, `superseded` |
| Risk | `unscored`, `proposed`, `reviewed`, `confirmed`, `invalidated` |
| Propagation | `not_analyzed`, `proposed`, `reviewed`, `confirmed`, `invalidated` |
| Approval | `not_submitted`, `pending`, `approved`, `rejected`, `withdrawn` |
| Publication | `unpublished`, `published`, `withdrawn`, `superseded` |
| Run | `queued`, `running`, `cancelling`, `cancelled`, `succeeded`, `failed` |
| Claim | `known`, `unknown`, `insufficient_evidence`, `conflict`, `not_applicable` |

Model actors may create only suggestions or proposals. Human reviewers may review fields, risk proposals, and propagation edges. Human approvers approve an exact immutable revision. Human publishers publish or withdraw an approved revision. The initial local account may hold all roles, but each command and audit event remains distinct.

An accepted field is not automatically scored. A confirmed score is not approval. Approval is not publication. Publication never means certification.

Published records are immutable. A correction creates a child revision and invalidates affected risk or propagation artifacts. Withdrawal adds an event and a new publication state; it never deletes the published payload or audit chain.

## 8. Risk and scoring capability

### 8.1 Rule packs

`ScoringRulePack` is immutable and declares:

- applicable FMEA and analysis types;
- score dimensions, ranges, anchors, units, and required context;
- S/O/D or alternative dimension semantics;
- RPN formula version;
- decision-priority or action-priority logic;
- risk matrix and thresholds;
- missing, interval, uncertainty, and conflict behavior;
- confirmation and invalidation policy.

Ordinary anchors, formulas, thresholds, and matrices are declarative. A non-standard calculator requires a server allowlisted adapter and contract tests. A template cannot define executable formulas.

### 8.2 Proposal and confirmation

A model may propose each dimension with evidence, rationale, uncertainty, and an explicit unknown value. Deterministic validation checks anchors, ranges, evidence membership, monotonicity, and rule applicability. The deterministic calculator derives RPN and priority only from confirmed input scores.

Missing, unknown, or conflicting required dimensions do not become zero and do not yield a valid RPN. A human confirms or rejects each proposed dimension. The service stores proposed and confirmed values separately.

Any change to the row revision, relevant evidence, operating context, DomainPack, or scoring rule pack marks the assessment `invalidated`. Recalculation never silently re-confirms human scores.

## 9. Propagation capability

### 9.1 Analysis sequence

Propagation uses a bounded sequence:

1. load an immutable analysis revision, EvidencePack set, topology snapshot, and rule pack;
2. enumerate structurally possible neighbors and interface variables through a `SystemTopologyPort`;
3. allow a model to propose semantically plausible typed edges only among bounded candidates;
4. deterministically validate endpoints, direction, operating mode, units, thresholds, delays, barriers, cycles, path length, evidence, and risk policy;
5. store a proposed graph revision;
6. require human decisions for edges and unresolved paths;
7. confirm a graph revision only when its applicable review policy passes.

The default automatic search depth is two hops. Longer paths remain explicit inference candidates. High-risk, cyclic, external, evidence-free, conflicting, or unprocessed edges always require human review. The model cannot create an endpoint absent from the supplied topology snapshot.

Each edge records source and target entities, relation type, interface variable, unit, direction, threshold, operating modes, timing values, barrier IDs, evidence IDs, support and claim states, risk priority, path length, cycle status, external status, and terminal status.

### 9.2 Evidence behavior

One citation cannot automatically support an entire multi-edge path. Every edge has independent evidence binding. Missing support produces a review issue or supplemental-evidence request. Propagation analysis does not reconnect to a retrieval backend. New evidence is supplied through a new EvidencePack with explicit lineage.

## 10. Model assistance at every human stage

All assistance uses one provider-neutral contract:

```text
AssistanceRequest
  -> bounded projection-safe context
  -> StructuredModelGateway
  -> deterministic decode and validation
  -> immutable AssistanceSuggestion(applied=false)
  -> separate human command
```

Supported assistance kinds are:

- analysis-scope and system-boundary drafting;
- template and import-field mapping;
- FMEA candidate generation;
- score recommendation;
- propagation hypothesis;
- evidence conflict and gap explanation;
- review summary;
- approval-readiness checklist;
- migration patch proposal;
- export narrative drafting.

Every suggestion records target identity and version, EvidencePack identity, DomainPack/template/rule identities, structured values, evidence references, uncertainty, conflicts, model and prompt versions, hashes, run trace, and `applied=false`.

The separate human command may adopt, partially adopt, edit-and-adopt, reject, defer, or request evidence. The model cannot mutate canonical FMEA state, confirm a score, accept an edge, approve a revision, publish or withdraw, change permissions, publish a template, or rewrite history.

The existing projection-safe evidence rule remains mandatory: model-visible values are bounded and validated while source pack identity, workspace, ACL, versions, and timestamps remain intact. Secrets, authorization headers, private paths, raw provider errors, and unbounded prompts never enter suggestions or outputs.

## 11. Review, approval, publication, and withdrawal

`ReviewDecision`, `ApprovalDecision`, and `PublishCommand` are separate commands and audit events.

A revision may enter approval only when:

- all required fields are accepted or have human-authored unresolved acknowledgements;
- required risk assessments are confirmed;
- required propagation analysis is confirmed;
- critical conflicts, incomplete evidence, and high-risk exceptions are resolved or explicitly acknowledged under the DomainPack policy;
- every referenced version and hash resolves;
- no generation, evidence-refresh, migration, or export-preview run can mutate the candidate revision;
- the revision content hash matches the approval request precondition.

Approval binds to one revision hash. Any content, score, graph, evidence, template, or rule change invalidates pending or completed approval for the child revision. Publication creates an immutable `PublishedRevision`, `PublicationManifest`, normalized snapshot, audit-chain hash, and export eligibility record in one transaction.

Withdrawal identifies the prior publication, actor, reason, time, and replacement when present. Supersession links old and new publications without removing either.

## 12. DomainPack and template migration

### 12.1 DomainPack manifest

Each pack declares:

- pack ID, semantic version, content hash, and compatibility range;
- supported FMEA and analysis types;
- template identities;
- canonical and extension field definitions;
- scoring and propagation rule-pack identities;
- review, approval, and unresolved-item policies;
- import and export mappings;
- allowlisted server adapters when declarative behavior is insufficient;
- explicit migrations;
- deterministic fixtures and acceptance invariants.

`fuel-combustion@1.0.0` is the first pack. A future electrical, software, medical, or custom pack uses the same kernel and capability ports.

### 12.2 Change classes

| Change | Required extension |
| --- | --- |
| Labels, order, required flags, export columns | Declarative template and export mapping |
| New typed domain fields | Template, namespaced field definitions, and adapter tests |
| New scoring or propagation semantics | New immutable rule pack and validator/calculator adapter when required |
| New review or approval semantics | Versioned server policy adapter and full lifecycle migration |
| New model, database, identity provider, or export library | Existing infrastructure port implementation |

### 12.3 Import and migration

Excel or Word import creates a `TemplateDraft`; it never registers or publishes a template directly. The draft preserves source hash, workbook/document structure, sheets, rows, columns, cell addresses, merges, identified fields, unknown fields, ambiguous mappings, and parser warnings.

A model may produce a `TemplatePatchCandidate` with the exact immutable base-template identity/version/hash, model and prompt versions, diff, evidence, and status. It cannot select a registered output version. A human template administrator accepts or rejects each patch; acceptance supplies an explicit higher output version, deterministically applies the declarative diff to the server-loaded and hash-verified base source, stores normalized import mappings in the optional generic `source_mappings` member, compiles it, and registers a new immutable template version. Already-valid ASCII identities are preserved only outside the reserved generated-key namespace: a letter-starting readable ASCII slug of at most 103 characters followed by `_` and 24 lowercase hexadecimal digest characters. A literal header in that namespace is normalized again with its own digest; every other source header requiring normalization receives a readable ASCII prefix plus a deterministic content digest, and that exact key is exposed in the bounded model projection so punctuation variants, long headers, Chinese, and other non-Latin templates remain distinct and portable. Mapping targets remain arbitrary existing top-level JSON property names rather than being restricted to ASCII identifiers. Omitting or supplying an empty `source_mappings` member preserves the pre-extension canonical identity, while a non-empty mapped version remains a legal base for later patch cycles.

The generic assistance envelope remains canonical JSON. The FMEA template workflow exposes a typed immutable wrapper containing both that envelope and the revalidated `TemplatePatchCandidate`, rather than weakening the shared JSON-safe assistance contract. Model-visible template context is a bounded header/mapping projection plus explicitly selected, length-bounded evidence IDs and excerpts: workspace/ACL/EvidencePack identity and hash, document identity, private paths, and complete imported document content remain server-side. XLSX/DOCX packages pass shared bounded OPC relationship/content validation before Office libraries open them. Task 2 serializes acceptance and records immutable process-local decisions containing the exact reviewed candidate; Task 3 provides durable idempotency, checkpoints, audit, and replay.

Migration is always:

```text
compatibility check
  -> dry-run against immutable source revisions
  -> deterministic migration report
  -> human confirmation
  -> child revisions
  -> risk and propagation invalidation/revalidation
  -> acceptance gates
```

No migration rewrites a published revision in place. Missing migration paths fail closed.

## 13. Normalized export and workbench

`NormalizedFmeaSnapshot` is the sole semantic source for canonical JSON, XLSX, and DOCX. It contains revision, field, risk, propagation, evidence, review, approval, publication, version-manifest, unresolved-item, and audit-summary data.

JSON is canonical. XLSX and DOCX are presentation adapters over the same snapshot. Every export records the same `revision_id`, `snapshot_hash`, DomainPack/template/rule versions, row IDs, evidence counts, decisions, and publication identity. Draft preview exports are visibly marked and cannot be confused with a published artifact.

The browser workbench is a thin REST client. It never imports repository or database code. Its first complete navigation includes:

- project and analysis scope;
- evidence and retrieval provenance;
- FMEA table and field review;
- S/O/D and risk confirmation;
- propagation table and read-only path graph;
- approval and publication readiness;
- DomainPack/template import and mapping;
- export requests and artifacts;
- immutable audit history.

Model suggestions and canonical human-confirmed values use different visual states. Color is not the only state indicator. Destructive or authority-bearing commands require explicit confirmation and show the affected revision.

## 14. API, persistence, and scale seams

REST, CLI, Skill, and UI call the same application services. No transport reads SQLite directly. Existing body-size limits, stable problem details, `If-Match`, canonical UUID idempotency keys, pagination, cursors, and loopback local-auth restrictions remain.

Long-running generation, propagation, migration, and export commands return durable run identities and polling locations. They support bounded retries, cooperative cancellation, and additive run events. Provider failure changes only the assistance run; it cannot corrupt or roll back an already committed FMEA revision.

SQLite remains the first repository with WAL, foreign keys, bounded busy timeout, migrations, one transactional writer, and paginated reads. Application services depend only on repository and unit-of-work ports. They do not rely on SQLite row IDs, SQL syntax, or connection behavior, preserving a PostgreSQL adapter path.

All list APIs paginate. Full-project export streams from an immutable normalized snapshot rather than loading browser state. Synthetic acceptance must cover an analysis with 10,000 rows without changing contracts or using unbounded response payloads. This is an engineering scalability check, not a promise of a certified production capacity.

The transactional outbox records domain events with aggregate identity, version, event type, canonical payload hash, actor, trace, and publication status. Initially it drives local workers. Later it may feed a queue without changing command behavior.

## 15. Error, security, and recovery policy

All boundaries fail closed with stable, bounded error codes. Internal exceptions, tracebacks, local paths, credentials, prompts, raw model output, and private evidence do not cross REST, CLI, export, run-event, or audit-summary boundaries.

The following are distinct and never collapsed into a generic success:

- invalid request or version precondition;
- unavailable or incomplete evidence;
- deterministic schema, rule, or evidence failure;
- model-provider unavailability or invalid output;
- scoring or propagation policy conflict;
- approval-readiness failure;
- migration incompatibility;
- storage conflict or unavailability;
- export-generation or artifact-verification failure.

Every write is idempotent and optimistic-lock protected. Repository state changes, audit events, and outbox events commit atomically. Export artifacts and acceptance packs are written to contained temporary directories, verified, and atomically published. Partial artifacts are not selected by `latest` resolution.

DomainPack files, templates, rule packs, migration adapters, and export mappings are constrained to workspace-owned roots. Parent escapes, UNC paths, symlink escapes, overlapping database/registry paths, arbitrary plugin loading, and untrusted formula execution are rejected.

## 16. Gap-driven delivery decomposition

The work is divided into four independently testable subprojects. Each receives its own implementation plan after this specification is approved.

### Phase 1: Risk closure

Deliver DomainPack and scoring-rule registries, score proposals, deterministic validation/calculation, human confirmation, invalidation, persistence, REST/CLI, audit, fuel/combustion fixtures, and an offline acceptance pack.

Exit criterion: an evidence-bound row can move from unscored through proposed to human-confirmed risk, and any relevant version change invalidates the result without silently retaining approval.

### Phase 2: Propagation closure

Deliver topology contracts, propagation rule packs, bounded candidate enumeration, model-assisted edge proposals, deterministic path validation, edge/path review, graph revisions, persistence, REST/CLI, fuel-to-combustion and reverse-impact fixtures, and acceptance/security gates.

Exit criterion: an accepted failure mode can produce a two-hop evidence-bound graph, preserve cycles/conflicts/long paths for review, and never invent an endpoint outside the topology snapshot.

### Phase 3: Governance closure

Deliver complete revision assembly, approval readiness, separate approval and publication commands, immutable manifests and normalized snapshots, withdrawal/supersession, roles, outbox, REST/CLI, and lifecycle acceptance gates.

Exit criterion: only an exact human-approved revision can publish, any child change requires new approval, and every published or withdrawn revision remains replayable.

### Phase 4: Migration and delivery closure

Deliver DomainPack packaging, Excel/Word template import drafts, model patch suggestions, compatibility and dry-run migration, canonical JSON/XLSX/DOCX export, thin browser workbench, multi-domain fixtures, export consistency, and UI main-chain tests.

Exit criterion: fuel/combustion and at least two structurally different demonstration domains use the same kernel; JSON, XLSX, and DOCX reference one verified snapshot; a new declarative template can be imported, reviewed, registered, migrated, and used without changing the generic core.

## 17. Verification strategy

Every phase follows test-first implementation and reports validation layers separately:

1. pure domain tests for state transitions, scoring, propagation, versions, and invariants;
2. contract tests for DomainPack, repository, topology, model, identity, and export ports;
3. SQLite integration and migration tests, including rollback and restart;
4. REST/CLI parity, authorization, ETag, idempotency, pagination, cancellation, and replay tests;
5. deterministic model fakes for default gates; paid live DeepSeek tests only by explicit authorization;
6. counterfactual tests where removing or replacing evidence changes support, score eligibility, or propagation eligibility;
7. tamper, prompt-injection, secret-leak, path-escape, symlink, concurrency, duplicate-event, and provider-fault regression tests;
8. multi-domain fixtures for fuel/combustion, electrical, and software FMEA;
9. normalized JSON/XLSX/DOCX consistency and artifact-hash verification;
10. browser main-chain tests for scope, evidence, review, risk, propagation, approval, publication, migration, and export;
11. bounded scale tests for pagination, background runs, 10,000-row normalized export, and outbox replay;
12. independent acceptance runners and verifiers with canonical schemas and no private markers.

No internal metric or fixture may be described as industrial certification. P0 acceptance requires zero model approvals/publications, zero known claims without valid evidence, zero confirmed scores with invalid required dimensions, zero accepted high-risk evidence-free propagation edges, zero duplicate state transitions on retry, zero cross-workspace reads, and zero mismatched snapshot hashes across export formats.

## 18. Compatibility and migration from the current branch

Implementation extends rather than replaces the current evidence, template, structured-generation, and review contracts.

1. Existing `FmeaRow` JSON and SQLite records remain readable.
2. New extension fields, risk records, propagation graph revisions, approvals, publications, DomainPacks, and outbox records use additive migrations.
3. Current review suggestions and decisions remain immutable history.
4. Current REST review routes remain valid; new resources compose around them rather than changing their semantics.
5. Existing audit events continue to decode through the exact current/legacy field-set rule. New event versions are explicit and cannot be mixed partially with old schemas.
6. Existing EvidencePack identity and projection rules remain unchanged.
7. A migration command creates child revisions and reports any item that cannot map deterministically.

## 19. Locked design decisions

The following decisions require a new user-approved specification to change:

1. modular monolith first, with ports, outbox, and extraction seams;
2. the owner controls the complete FMEA subsystem after the EvidencePack boundary;
3. fuel/combustion is a DomainPack, not generic-kernel code;
4. stable core fields plus typed, namespaced extension fields;
5. orthogonal review, risk, propagation, approval, publication, run, and claim states;
6. model assistance at every human stage, but no model authority for confirmation, approval, publication, withdrawal, or template publication;
7. deterministic scoring and rule validation take precedence over model recommendations;
8. propagation uses bounded topology candidates and per-edge evidence;
9. immutable published revisions, explicit withdrawal, and no in-place migration;
10. one normalized snapshot for JSON, XLSX, and DOCX;
11. gap-driven implementation in four independently accepted phases;
12. simple local account and SQLite first, without coupling application contracts to either.

## 20. Reference documents

- `docs/superpowers/specs/2026-08-23-graphrag-fmea-system-design.md`
- `docs/superpowers/specs/2026-08-24-generic-structured-output-template-engine-design.md`
- `docs/superpowers/specs/2026-08-24-structured-generation-deepseek-fmea-design.md`
- `docs/superpowers/specs/2026-08-25-fmea-review-interface-design.md`
- `docs/handoff/rag-graphrag-fmea-evidence.md`
- `docs/handoff/generic-structured-output-templates.md`
- `docs/handoff/structured-generation-deepseek-fmea.md`
- `docs/handoff/fmea-review-interface.md`
