# Phase 4 Task 2 Report — Safe template import and patch review

## Scope and baseline

- Task: Phase 4 Task 2 only.
- Baseline: `9a38b0508630e89345e74a229733992a9d7c2a8b`.
- Worktree: `C:\Users\35551\Desktop\RAG\.worktrees\interface-output-v1`.
- Branch: `feat/interface-output-v1`.
- No push, pull request, migration SQL, persistence, exporter, route, CLI, Skill, or UI work was performed.
- Runtime dependencies added are `openpyxl>=3.1.5,<4` for XLSX parsing and `defusedxml>=0.7.1,<1` for encoding-aware DTD/entity rejection; `uv.lock` reproducibly contains `openpyxl 3.1.5`, `et-xmlfile 2.0.0`, and `defusedxml 0.7.1`.
- The local `.venv` already contained `uv 0.8.15`; it was invoked as `python -m uv` because no global `uv` executable is on `PATH`.

## TDD evidence

The four required test files were created before the production modules. The genuine RED command was:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_import_excel.py tests/unit/test_fmea_template_import_docx.py tests/unit/test_fmea_template_patch_generator.py tests/integration/test_fmea_template_draft_lifecycle.py -q
```

RED result: exit code `1`; pytest collected four module-import errors because the four Task 2 production modules did not yet exist:

- `ModuleNotFoundError: No module named 'fmea_infrastructure.template_import_excel'`
- `ModuleNotFoundError: No module named 'fmea_infrastructure.template_import_docx'`
- `ModuleNotFoundError: No module named 'fmea_infrastructure.template_patch_generator'`
- `ModuleNotFoundError: No module named 'fmea_application.domain_pack_service'`

After the implementation and independent-review remediation slices, the same command produced:

```text
54 passed, 1 warning
```

The single warning is pytest's expected `zipfile` warning while constructing a duplicate-member negative fixture; it is not an importer warning or a test failure.

## Implementation slices

### 1. Shared safe ZIP inspection and Office importers

- Added explicit package limits for source bytes, member count, member/total decompressed bytes, compression ratio, sheets, rows, columns, cells, paragraphs, tables, relationships, text, and retained structure items.
- Inspects ZIP member names, duplicate entries, encryption flags, declared sizes/ratios, bounded reads, CRC failures, macros, embedded executable parts, external relationships, XML declarations/entities, required parts, and required XLSX/DOCX content types before `openpyxl` or `python-docx` opens the package.
- XLSX resolves worksheets through `xl/workbook.xml` and `xl/_rels/workbook.xml.rels`, so structural extraction does not depend on ZIP member order. It preserves source SHA-256, sheet/cell/merge locators, row-1 field candidates, unknown fields, and ambiguous mappings without evaluating formulas.
- DOCX preserves paragraph/table-cell/relationship locators and the same generic field classification. It rejects Word fields, executable XML elements, external relationships, macros, malformed containers, and bounded-limit violations.
- Field aliases remain domain-neutral generic FMEA concepts only; no fuel or combustion fields were added.

### 2. Provider-neutral patch generator

- Added `TemplatePatchModelGateway` as the provider seam. A deterministic fake is used by default tests; no network call or paid model call is made.
- Validates the model response as exactly `{diff, evidence_ids}`.
- Allows only bounded `add`/`replace`/`remove` operations on `/fields/...` or `/mappings/...` paths with unique paths and JSON-safe scalar/mapping/list values.
- Rejects code, expressions, URLs, filesystem paths, shell/database instructions, secrets, private markers, arbitrary keys, duplicate evidence IDs, non-finite numbers, excessive depth, and excessive output size.
- Produces a frozen, unapplied `TemplatePatchCandidate` with exact draft/template/DomainPack/EvidencePack/run/trace/model/prompt provenance and hashes.
- The generic `AssistanceSuggestion` remains canonical JSON-safe. FMEA exposes a frozen `TemplatePatchSuggestion(candidate, envelope)` wrapper, and validates that the typed candidate exactly round-trips through the generic envelope payload.
- Added a structured adapter that reuses the existing Flash generation -> `deepseek-v4-pro` critic -> at-most-one-repair pipeline. The adapter gives the model only bounded headers/mappings and selected bounded evidence excerpts, replaces real workspace/pack/document/path identity with a model-only projection, and binds the envelope to the final Pro trace hashes.

### 3. `DomainPackService` authority lifecycle

- `import_template` selects a port by validated extension and stores only an immutable `TemplateDraft`.
- `suggest_patch` passes a bounded immutable request to the provider-neutral generator and stores only an unapplied suggestion/candidate. It rechecks all candidate and envelope provenance against the request and draft.
- `accept_patch` requires a non-model human actor with `template_admin`, exact draft/source/template/DomainPack/EvidencePack preconditions, and `confirm_template_change=True`. It calls the compiler once and registry once, only after all checks pass, then records the terminal decision.
- `reject_patch` requires the same human authority and a non-empty reason, returns and records an immutable `TemplatePatchDecision`, and never calls compiler or registry. Accepted and rejected decisions retain the exact candidate diff, including mapping-only operations.
- Workspace mismatch, stale hashes/versions, duplicate/replay decisions, wrong suggestion identity, non-admin/model actors, malformed candidates, and invalid provenance fail closed.
- In-memory draft/suggestion/decision state is deliberate Task 2 scaffolding. Durable persistence, idempotency/outbox, migration, route, and export integration remain Task 3+ work.
- Accepted source mappings are stored in the optional generic compiled-template `source_mappings` member. Missing or empty mappings preserve legacy canonical hashes; non-empty mappings are bounded, target top-level output properties, participate in canonical hashing, and round-trip through `FileTemplateRegistry`.

## Verification matrix

Compatibility tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_output_template_skill_cli.py tests/unit/test_structured_output_file_registry.py tests/unit/test_fmea_template_migration_contracts.py -q
```

Result: `100 passed in 5.88s`.

Generic compiler/registry and cross-domain regression matrix:

```text
132 passed in 2.74s
```

Scoped static checks:

```text
ruff check <Task 2 scoped Python files>: All checks passed! (exit 0)
ruff format --check <Task 2 scoped Python files>: all files already formatted (exit 0)
python -m compileall -q <Task 2 production files>: exit 0
python -m uv lock --check --offline: resolved 166 packages (exit 0)
git diff --check: exit 0; only Windows LF-to-CRLF working-copy warnings were emitted
```

## Changed files

- `pyproject.toml`
- `uv.lock`
- `docs/superpowers/plans/2026-08-27-fmea-migration-delivery-closure.md`
- `docs/superpowers/specs/2026-08-27-full-fmea-modular-product-design.md`
- `fmea_application/__init__.py`
- `fmea_application/ports.py`
- `fmea_application/template_patch_contracts.py`
- `fmea_application/domain_pack_service.py`
- `core_domain/structured_output/contracts.py`
- `structured_output_application/compiler.py`
- `structured_output_infrastructure/file_registry.py`
- `fmea_infrastructure/office_package.py`
- `fmea_infrastructure/template_import_excel.py`
- `fmea_infrastructure/template_import_docx.py`
- `fmea_infrastructure/template_patch_generator.py`
- `templates/examples/fmea-template-patch.yaml`
- `tests/unit/test_fmea_template_import_excel.py`
- `tests/unit/test_fmea_template_import_docx.py`
- `tests/unit/test_fmea_template_patch_generator.py`
- `tests/integration/test_fmea_template_draft_lifecycle.py`
- this report

## Residual concerns and handoff

1. This Task 2 service intentionally uses in-memory lifecycle state. Task 3 must add durable persistence and replay/idempotency before production acceptance.
2. The Office safety layer rejects external relationships and embedded executable content, but it is not a general Office document sanitizer. Future formats must reuse the same pre-parser ZIP inspection port and add format-specific content-type/structure rules.
3. The DeepSeek adapter is implemented and deterministically tested through the real structured-generation pipeline, but no paid/network call is part of default acceptance. A separately authorized live smoke test remains optional.

## Independent review round 1 remediation

- C1 resolved: acceptance now loads the immutable hash-bound base, applies exact `/fields` and `/mappings` semantics, stores mappings in generic canonical `source_mappings`, compiles the changed source, and registers only a strictly higher immutable version. A real `TemplateCompiler` + `FileTemplateRegistry` test proves the base is unchanged and both output schema and mapping state changed exactly.
- C2/I6/M1 resolved: XLSX and DOCX share one fail-closed OPC package seam covering every relationship part and XML part before Office parser entry, including duplicate/case-colliding members, internal target containment/existence, type/content bindings, ActiveX/plugins/embeddings/macros, formulas, defined names, Word fields, and bounded ZIP/package/parser resources.
- I1/I8 resolved: model input and output are byte-bounded; only selected evidence IDs/excerpts enter the model projection, while workspace, pack identity/hash, document identity, ACL, private locators and full document structure remain private. Provider errors normalize to stable unavailable/invalid codes.
- I2 resolved: normalized source and target collisions become ambiguous rather than silently collapsing.
- I3/M2 resolved within Task 2: process-local decisions are serialized, failure before registration leaves no terminal decision and permits retry, and immutable accepted/rejected decision records are queryable. Durable cross-process exactly-once remains Task 3.
- I4 resolved: the FMEA typed wrapper and generic JSON-safe envelope are both retained and cross-validated.
- I5 resolved: the shared Flash/Pro structured pipeline is reused with final trace hashes and at most one repair.
- I7 resolved: `uv.lock` includes both `openpyxl` and `et-xmlfile` and passes `uv lock --check`.
- I9 resolved with compact boundary tests for package/member/relationship/compression, sheet/row/column/cell, paragraph/table, content type, collision, concurrency, retry, real registration, projection privacy, response bounds and deterministic Flash/Pro execution.

## Independent split review round 2 remediation

- One Critical mapping-persistence finding was valid. The template compiler now supports a bounded optional generic `source_mappings` root member, includes non-empty mappings in canonical identity, preserves hashes for missing/empty legacy mappings, validates targets, and round-trips the mapping through the file registry.
- Three Important Office/privacy findings were valid. XML is now parsed with `defusedxml` using DTD/entity/external rejection; scanning covers the union of XML filename suffixes and OPC XML content types; relationship target content types are checked; UTF-16 DTD and non-XML-suffix formula bypass fixtures fail closed. Evidence IDs are validated before sorting/gateway entry and replaced by deterministic model-only aliases that map back to server-owned IDs after output validation.
- Three Minor findings were valid. DOCX structure limits are enforced incrementally, direct structured-pipeline runtime failures normalize to a safe retryable error, and boolean/non-finite compression-ratio limits are rejected.
- Fresh post-remediation evidence: Task 2 focused `51 passed, 1 expected warning`; structured-output/cross-domain `132 passed`; compatibility `100 passed`; Ruff, format, compileall, offline uv-lock check, and diff check all exit `0`.

Task 3 may start only after an independent reviewer compares the implementation commit against the stated baseline and confirms this report's scoped evidence.

## Fix report — multilingual identity and concurrent suggestion closure

Commits: `83230f42..d26b1fb2`.

The final review findings were addressed with test-first changes:

- source-header mapping identities now preserve only already-valid ASCII identifiers verbatim; every normalized punctuation, Unicode, or oversized header receives a readable prefix plus a bounded SHA-256 suffix, preventing silent `A/B` versus `A B` collapse;
- mapping targets may reference any existing top-level JSON property name, including Unicode or digit-prefixed names, while mapping source identities remain safe ASCII path segments;
- `CompiledTemplate` and the compiler expose the same `TEMPLATE_MAPPING_INVALID` boundary;
- evidence IDs must be canonical non-path identifiers before model alias projection, covering Windows and Unix path forms and whitespace drift;
- `suggest_patch` reserves a patch identity under the process-local decision lock before model generation and releases the reservation on every success/failure path, so concurrent calls cannot overwrite the reviewed candidate;
- templates with non-empty `source_mappings` remain valid bases for subsequent immutable patch versions.

Covering verification command:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_import_excel.py tests/unit/test_fmea_template_import_docx.py tests/unit/test_fmea_template_patch_generator.py tests/integration/test_fmea_template_draft_lifecycle.py tests/unit/test_structured_output_compiler.py tests/unit/test_structured_output_contracts.py tests/unit/test_structured_output_file_registry.py tests/integration/test_output_template_skill_cli.py -q
```

Result: `121 passed, 1 expected duplicate-ZIP fixture warning in 9.88s`.

Additional verification:

```text
ruff check (9 amended Python files): All checks passed
ruff format --check (9 amended Python files): 9 files already formatted
compileall (5 production files): exit 0
git diff --check: exit 0, LF/CRLF working-copy warnings only
python -m uv lock --check --offline: resolved 166 packages, exit 0
```

No network model call, push, pull request, migration, exporter, REST/CLI, or UI work was performed in this fix round.

## Fix report — reserved generated-key namespace

The remaining Important finding was fixed by reserving the generated source-key shape (a letter-starting readable slug of at most 103 characters, `_`, and 24 lowercase hexadecimal digest characters). Already-valid ASCII identities are preserved only outside that namespace; a literal key in the namespace is normalized again. Generated keys for non-letter-starting slugs now receive a `source_` prefix so every result remains a safe ASCII path segment starting with a letter and no longer than 128 characters.

### TDD RED

Command:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_patch_generator.py -q -k generated_key_namespace
```

Output summary: exit code `1`; `1 failed, 15 deselected in 0.41s`. The failure was the expected assertion that the literal generated key must be transformed; before the fix it was returned unchanged.

### TDD GREEN

Command:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_patch_generator.py -q -k generated_key_namespace
```

Output summary: exit code `0`; `1 passed, 15 deselected in 0.21s`.

### Final focused verification

- `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_template_patch_generator.py -q`: `16 passed in 0.64s`.
- `.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_template_draft_lifecycle.py -q -k mapping`: `1 passed, 8 deselected in 0.51s`.
- `.venv\Scripts\ruff.exe check fmea_application/template_patch_contracts.py tests/unit/test_fmea_template_patch_generator.py`: `All checks passed!` (exit code `0`).
- `.venv\Scripts\ruff.exe format --check fmea_application/template_patch_contracts.py tests/unit/test_fmea_template_patch_generator.py`: `2 files already formatted` (exit code `0`).
- `git diff --check`: exit code `0`; only expected Windows LF/CRLF working-copy warnings.

### Final independent re-review

- Review range: `d26b1fb2..1027b131`.
- Open Important finding: generated mapping-key namespace could collide with a literal valid header equal to the generated key.
- Verdict: `ADDRESSED`; the generated-key shape is reserved, literal keys in that namespace are normalized again, and focused reviewer checks passed (`2 passed, 14 deselected`).
- New Critical/Important breakage: none.
- Final Task 2 related matrix after the fix: `122 passed, 1 expected duplicate-ZIP fixture warning in 8.63s`; Ruff check and format check pass.
