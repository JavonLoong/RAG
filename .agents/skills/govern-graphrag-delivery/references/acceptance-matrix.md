# M2–M5 acceptance matrix

Use this matrix for audits and completion claims. Mark each row Complete, Partial, Missing, or Deferred and cite executable evidence.

## M2 — parsing and annotation

| Requirement | Minimum acceptance evidence |
|---|---|
| Select a parser route by file type | Tests for native PDF, scanned PDF, DOCX, image, and text |
| Extract native text and run OCR | Parsed output plus OCR-required and OCR-success cases |
| Preserve headings, paragraphs, reading order, tables, images, and captions | Representative structural fixtures with locators |
| Detect language, preserve originals, and produce aligned translation when requested | Chinese and English fixtures plus alignment output |
| Repair encoding, sentence breaks, and basic structure | Before/after fixtures without silent text loss |
| Detect missing pages, low OCR quality, and table misalignment | Quality issues tied to pages or blocks |
| Create human review work with source/result comparison | Reviewable source locator and editable candidate |
| Save approve, reject, modify, and audit history | Durable decision records and corrected version behavior |
| Handle partial-page failure, timeout, and feedback | Failure injection and recovery or routing tests |

## M3 — canonical material library

| Requirement | Minimum acceptance evidence |
|---|---|
| Maintain one canonical document model | Versioned contract containing evidence locators |
| Distinguish candidate, needs-review, published, and retired | State-transition tests |
| Merge reviewed corrections into an official version | Published content reflects the reviewed correction |
| Preserve document/page/block/table/image relationships | Queryable relationship fields and fixtures |
| Chunk while preserving source evidence | Retrieval result resolves to the original locator |
| Build, update, and rebuild indexes | Published version drives index operations |
| Support keyword, semantic, and hybrid retrieval | Retrieval tests scoped to material version |
| Provide basic RAG with citations | Answer plus evidence and no-answer behavior |
| Compare, supersede, revoke, and roll back versions | Audited version-transition tests |
| Support incremental update, conflict, and recovery | Integration tests including backup or rebuild recovery |

## M4 — governed GraphRAG

| Requirement | Minimum acceptance evidence |
|---|---|
| Define gas-turbine entities, relations, and knowledge types | Versioned schema and validation tests |
| Extract equipment, components, failure modes, causes, effects, and actions | Automatic extraction from representative material |
| Resolve aliases, duplicates, model differences, and source conflicts | Normalization and conflict fixtures |
| Bind entities and relations to original evidence | Every published statement resolves to selected evidence |
| Version, query, view, and export graphs | Version-aware API and graph-store tests |
| Apply equipment hierarchy and minimum FMEA constraints | PART_OF and FMEA relation validation |
| Retrieve by GraphRAG and display graph paths | Query results include path and evidence |
| Compare ordinary RAG with GraphRAG on the same questions | Repeatable evaluation set and report |
| Fall back to ordinary RAG when graph quality is insufficient | Quality-gate and fallback tests |

## M5 — task and FMEA outputs

| Requirement | Minimum acceptance evidence |
|---|---|
| Define request, task states, errors, and result contract | API and state-transition tests |
| Select material version, graph version, and template | Request validation and lineage in output |
| Provide the minimum gas-turbine FMEA template | Versioned template with required fields |
| Derive failure mode, cause, effect, detection, and action | Graph-to-FMEA transformation tests |
| Bind source evidence per professional field | Every populated field resolves to evidence |
| Display missing evidence and source conflicts | Unknown and conflict fixtures |
| Support human approve, modify, reject, and confirm | Corrected result plus audit records |
| Publish and export reviewed results | JSON/CSV round-trip consistency |
| Route problems to M1–M4 and revalidate | Feedback creates actionable upstream work and triggers or documents rebuild |

## Evidence hierarchy

Prefer evidence in this order:

1. representative end-to-end or integration test result;
2. focused executable unit/API test;
3. connected implementation call path;
4. isolated component without integration;
5. documentation or plan only.

A lower-ranked artifact cannot by itself justify a higher-level completion claim.
