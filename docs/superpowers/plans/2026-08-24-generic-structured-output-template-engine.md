# Generic Structured Output Template Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, immutable, cross-domain JSON/YAML template engine that validates standard JSON payloads and field-level EvidencePack claims for the reusable RAG skill output layer.

**Architecture:** A dependency-free structured-output domain owns frozen contracts, canonical JSON and safe pointer policies. Application services compile JSON Schema 2020-12 plus a separate evidence-binding manifest, validate candidates against an existing EvidencePack, and consume an abstract registry. Infrastructure supplies safe JSON/YAML loading, Draft 2020-12 validation, an atomic file registry and a single-JSON CLI; FMEA and external LLMs remain downstream.

**Tech Stack:** Python 3.11+, frozen dataclasses, `orjson`, `jsonschema>=4.23`, `PyYAML>=6.0`, SHA-256, pytest, Ruff, PowerShell CLI tests.

**Spec:** `docs/superpowers/specs/2026-08-24-generic-structured-output-template-engine-design.md`

## Global Constraints

- Use JSON Schema dialect exactly `https://json-schema.org/draft/2020-12/schema`.
- Template source is at most `1_048_576` bytes, schema depth 16, properties 500, bindings 500, candidates 100, claims per candidate 1000, array items 1000 and strings 65536 characters.
- Permit package-local `$defs/$ref`; reject remote/file refs, `$dynamicRef`, `$dynamicAnchor`, direct/indirect recursive refs, executable/custom YAML objects and YAML aliases/anchors.
- Evidence binding patterns support RFC 6901 property segments and whole-segment `*` only; no `**`, filters, expressions, negative indexes or URI fragments.
- Compilation, registration, example generation and candidate validation must never access the network or call an LLM.
- Same template ID/version/hash registration is idempotent; same ID/version with a different hash fails closed.
- `core_domain.structured_output` must not import FMEA, QueryService, Chroma, GraphStore or model adapters.
- CLI stdout is exactly one JSON object; diagnostics go to stderr. Exit codes: success `0`, validation `2`, dependency/registry `3`, internal error `1`.
- This plan does not implement DeepSeek, candidate generation, FMEA mapping/scoring/propagation, Excel/Word import, UI, review/publication or output export.

---

### Task 1: Add Direct Dependencies and Stable Domain Contracts

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `core_domain/structured_output/__init__.py`
- Create: `core_domain/structured_output/contracts.py`
- Test: `tests/unit/test_structured_output_contracts.py`

**Interfaces:**
- Consumes: `core_domain.fmea.value_objects.EvidencePack` only in later application code, not in these domain contracts.
- Produces: `JsonValue`, `ClaimState`, `TemplateMetadata`, `EvidenceBinding`, `CompiledTemplate`, `CandidateClaim`, `StructuredCandidate`, `StructuredCandidateBatch`, `ValidationIssue`, `TemplateValidationReport`, `CandidateValidationReport`, and `StructuredOutputError`.

- [ ] **Step 1: Write failing contract-shape and immutability tests**

```python
from dataclasses import FrozenInstanceError, fields

import pytest

from core_domain.structured_output import (
    CandidateClaim,
    ClaimState,
    EvidenceBinding,
    StructuredCandidate,
    StructuredCandidateBatch,
    TemplateMetadata,
)


def test_template_and_candidate_contracts_are_frozen_and_tuple_normalized() -> None:
    metadata = TemplateMetadata(
        template_id="maintenance-checklist",
        version="1.0.0",
        title="Maintenance checklist",
        description="",
        domain_tags=["maintenance", "equipment"],
        schema_dialect="https://json-schema.org/draft/2020-12/schema",
    )
    binding = EvidenceBinding(target="/checks/*/result", requirement="required", min_refs=1)
    claim = CandidateClaim(target="/checks/0/result", state=ClaimState.KNOWN, evidence_ids=["ev-1"])
    candidate = StructuredCandidate(candidate_id="candidate-1", payload={"checks": []}, claims=[claim])
    batch = StructuredCandidateBatch(
        template_id=metadata.template_id,
        template_version=metadata.version,
        template_hash="a" * 64,
        evidence_pack_id="pack-1",
        candidates=[candidate],
    )

    assert metadata.domain_tags == ("maintenance", "equipment")
    assert candidate.claims == (claim,)
    assert batch.candidates == (candidate,)
    assert tuple(field.name for field in fields(EvidenceBinding)) == (
        "target", "requirement", "min_refs", "max_refs", "allowed_source_types"
    )
    with pytest.raises(FrozenInstanceError):
        metadata.title = "changed"
```

- [ ] **Step 2: Run the tests and verify the missing package failure**

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_contracts.py -q
```

Expected: FAIL during collection because `core_domain.structured_output` does not exist.

- [ ] **Step 3: Add explicit runtime dependencies**

Add to root `pyproject.toml` project dependencies:

```toml
"jsonschema>=4.23,<5",
"PyYAML>=6.0,<7",
```

Refresh the lock without upgrading unrelated packages:

```powershell
uv lock --offline
```

Verify the lock contains direct requirements for the workspace package and retains the installed compatible `jsonschema`/`PyYAML` versions.

- [ ] **Step 4: Implement frozen contracts with constructor validation**

`contracts.py` must define exact enums and dataclasses. Constructors tuple-normalize list input, reject duplicate evidence IDs/bindings/candidate IDs, reject non-64-character lowercase SHA-256 strings, and use `StructuredOutputError(code, message, pointer="")` for domain failures.

```python
class ClaimState(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class CompiledTemplate:
    metadata: TemplateMetadata
    output_schema: dict[str, JsonValue]
    evidence_bindings: tuple[EvidenceBinding, ...]
    template_hash: str
    canonical_json: str


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    pointer: str
    candidate_id: str | None = None
    target: str | None = None
    binding: str | None = None
```

`TemplateValidationReport` has `valid`, `issues`, and `compiled_template`; `CandidateValidationReport` has `valid`, `issues`, and `batch`. A valid report has an empty issue tuple.

- [ ] **Step 5: Run contract tests and static checks**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_contracts.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/structured_output tests/unit/test_structured_output_contracts.py
git diff --check
```

Expected: all commands pass.

- [ ] **Step 6: Commit the domain slice**

```powershell
git add pyproject.toml uv.lock core_domain/structured_output tests/unit/test_structured_output_contracts.py
git commit -m "feat(output): add generic template contracts"
```

---

### Task 2: Implement Canonical JSON, Pointer Patterns and Resource Policies

**Files:**
- Create: `core_domain/structured_output/canonical.py`
- Create: `core_domain/structured_output/policies.py`
- Modify: `core_domain/structured_output/__init__.py`
- Test: `tests/unit/test_structured_output_canonical.py`
- Test: `tests/unit/test_structured_output_policies.py`

**Interfaces:**
- Consumes: `JsonValue`, `StructuredOutputError` from Task 1.
- Produces: `canonical_json()`, `canonical_hash()`, `parse_pointer()`, `resolve_pointer()`, `pattern_matches()`, `expand_pattern()`, `TemplateLimits`, `validate_json_value()`, and `measure_schema()`.

- [ ] **Step 1: Write failing canonicalization and pointer tests**

```python
def test_equivalent_objects_have_identical_canonical_hash() -> None:
    left = {"b": [2, 1], "a": {"z": True}}
    right = {"a": {"z": True}, "b": [2, 1]}
    assert canonical_hash(left) == canonical_hash(right)


def test_pointer_pattern_expands_array_members_and_escapes_tokens() -> None:
    payload = {"a/b": {"effects": ["low pressure", "unstable flame"]}}
    assert expand_pattern(payload, "/a~1b/effects/*") == (
        "/a~1b/effects/0",
        "/a~1b/effects/1",
    )
    assert resolve_pointer(payload, "/a~1b/effects/1") == "unstable flame"
```

Add parameterized rejection tests for empty/non-leading-slash pointers, URI fragments, `**`, embedded `*`, negative array indexes, invalid `~` escapes, NaN/Infinity, non-string dict keys, bytes and arbitrary Python objects.

- [ ] **Step 2: Run tests and verify missing helpers fail**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_canonical.py tests/unit/test_structured_output_policies.py -q
```

Expected: FAIL because the modules/functions do not exist.

- [ ] **Step 3: Implement deterministic JSON and RFC 6901 helpers**

Use `orjson.dumps(value, option=orjson.OPT_SORT_KEYS)` after recursively validating JSON values. `canonical_hash()` returns SHA-256 hex. Pointer parsing must decode only `~0` and `~1`, and canonical output re-encodes tokens.

`pattern_matches(pattern, target)` compares equal segment counts and treats a whole pattern segment `*` as one wildcard. `expand_pattern(payload, pattern)` walks object properties or every current array member in input order and returns exact encoded pointers.

- [ ] **Step 4: Implement fixed limits and resource measurement**

```python
@dataclass(frozen=True, slots=True)
class TemplateLimits:
    max_source_bytes: int = 1_048_576
    max_schema_depth: int = 16
    max_properties: int = 500
    max_bindings: int = 500
    max_candidates: int = 100
    max_claims_per_candidate: int = 1000
    max_array_items: int = 1000
    max_string_length: int = 65536
```

`validate_json_value()` traverses payloads with a depth counter, validates finite numbers, array length/string length, and reports the exact pointer. `measure_schema()` counts `properties` entries and structural depth without following `$ref`; ref graph safety belongs to Task 3.

- [ ] **Step 5: Run targeted tests and Ruff**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_canonical.py tests/unit/test_structured_output_policies.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/structured_output tests/unit/test_structured_output_canonical.py tests/unit/test_structured_output_policies.py
```

Expected: all pass.

- [ ] **Step 6: Commit canonical policy primitives**

```powershell
git add core_domain/structured_output tests/unit/test_structured_output_canonical.py tests/unit/test_structured_output_policies.py
git commit -m "feat(output): add canonical template policies"
```

---

### Task 3: Add Safe JSON/YAML Loading and Draft 2020-12 Validation

**Files:**
- Create: `structured_output_infrastructure/__init__.py`
- Create: `structured_output_infrastructure/source_loader.py`
- Create: `structured_output_infrastructure/jsonschema_adapter.py`
- Test: `tests/unit/test_structured_output_source_loader.py`
- Test: `tests/unit/test_structured_output_jsonschema.py`

**Interfaces:**
- Consumes: `JsonValue`, `TemplateLimits`, `ValidationIssue`.
- Produces: `load_template_source(path, limits) -> dict[str, JsonValue]` and `Draft202012SchemaAdapter.check_schema(schema) -> tuple[ValidationIssue, ...]`, `.validate(instance, schema) -> tuple[ValidationIssue, ...]`.

- [ ] **Step 1: Write failing safe-loader tests**

Create temporary equivalent JSON/YAML files and assert equal objects. Add fixtures that exceed byte limits, use `!!python/object`, YAML aliases/anchors, multiple YAML documents, scalar roots, unsupported suffixes and malformed UTF-8. Every failure must expose a stable `TEMPLATE_SOURCE_INVALID` or `TEMPLATE_LIMIT_EXCEEDED` code without leaking file contents.

```python
def test_yaml_alias_and_anchor_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.yaml"
    source.write_text("base: &base {type: string}\ncopy: *base\n", encoding="utf-8")
    with pytest.raises(StructuredOutputError) as error:
        load_template_source(source, TemplateLimits())
    assert error.value.code == "TEMPLATE_SOURCE_INVALID"
```

- [ ] **Step 2: Write failing Schema safety tests**

Test valid local `#/$defs/item` refs and reject:

```text
https://example.com/schema.json
file:///private/schema.json
../schema.json
#/$defs/self -> #/$defs/self
A -> B -> A
$dynamicRef
$dynamicAnchor
contentEncoding
contentMediaType
```

Also prove instance errors return stable `CANDIDATE_SCHEMA_INVALID` issues sorted by instance pointer and validator name.

- [ ] **Step 3: Run tests and verify modules are absent**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_source_loader.py tests/unit/test_structured_output_jsonschema.py -q
```

Expected: FAIL during import.

- [ ] **Step 4: Implement the loader without source-side execution**

Read bytes first and enforce size, decode strict UTF-8, then:

- `.json`: `orjson.loads`;
- `.yaml`/`.yml`: inspect `yaml.parse(text)` events and reject any event with a non-null anchor or any `AliasEvent`, then `yaml.safe_load`;
- reject multiple `DocumentStartEvent` entries;
- require one object root;
- call `validate_json_value()` before returning.

- [ ] **Step 5: Implement the Schema adapter and local ref graph check**

Use `jsonschema.Draft202012Validator.check_schema`. Walk every object node, reject forbidden keywords, accept `$ref` only when it matches `#/$defs/<escaped-name>`, resolve definitions from the root, and DFS the ref graph with visiting/visited sets to reject cycles.

Enforce an explicit keyword allowlist matching the spec's first-version subset. Reject unsupported combinators/conditionals and implicit evaluators including `allOf`, `anyOf`, `oneOf`, `not`, `if`, `then`, `else`, `contains`, `dependentSchemas`, `patternProperties`, `unevaluatedProperties`, `unevaluatedItems`, and `format` with `TEMPLATE_SCHEMA_UNSUPPORTED`; otherwise the deterministic example builder could not honor every accepted schema.

Map `jsonschema.ValidationError.absolute_path` to RFC 6901 pointers. Do not return raw schema values or payload values in public messages.

- [ ] **Step 6: Run loader/schema tests and dependency smoke**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_source_loader.py tests/unit/test_structured_output_jsonschema.py -q
& '.venv\Scripts\python.exe' -c "import jsonschema, yaml; print('ok')"
& '.venv\Scripts\python.exe' -m ruff check structured_output_infrastructure tests/unit/test_structured_output_source_loader.py tests/unit/test_structured_output_jsonschema.py
```

Expected: tests pass and smoke prints `ok`.

- [ ] **Step 7: Commit safe loading and Schema validation**

```powershell
git add structured_output_infrastructure tests/unit/test_structured_output_source_loader.py tests/unit/test_structured_output_jsonschema.py
git commit -m "feat(output): load and validate safe templates"
```

---

### Task 4: Compile Templates and Prove Cross-Format Determinism

**Files:**
- Create: `structured_output_application/__init__.py`
- Create: `structured_output_application/ports.py`
- Create: `structured_output_application/compiler.py`
- Test: `tests/unit/test_structured_output_compiler.py`
- Create: `tests/fixtures/structured_output/fmea.yaml`
- Create: `tests/fixtures/structured_output/maintenance.json`
- Create: `tests/fixtures/structured_output/research.yaml`

**Interfaces:**
- Consumes: Tasks 1-3 contracts, canonical helpers, limits, source loader and `Draft202012SchemaAdapter`.
- Produces: `TemplateSourceLoader` and `SchemaValidatorPort` Protocols; `TemplateCompiler.compile(source: dict[str, JsonValue]) -> CompiledTemplate`; `compile_path(path) -> CompiledTemplate`.

- [ ] **Step 1: Add three unrelated fixture templates**

The fixtures must use disjoint business fields:

- FMEA: `item`, `failure_mode`, `effects`;
- maintenance: `asset_id`, `checks[].result`, `checks[].note`;
- research: `paper_id`, `claims[].statement`, `claims[].limitations`.

Every fixture uses `additionalProperties: false`, at least one required evidence binding and one wildcard array binding where appropriate.

- [ ] **Step 2: Write failing compiler tests**

Cover:

- all three fixtures compile through one API;
- semantically equal JSON/YAML and reordered keys produce equal canonical JSON/hash;
- changed binding/schema/version changes hash;
- root keys other than `template`, `output_schema`, `evidence_bindings` reject;
- invalid ID, SemVer, duplicate tags, binding count and duplicate target reject;
- required/optional/forbidden min/max invariants;
- pattern static reachability through objects, arrays and local refs;
- `/rows/*/field` accepted while `/rows/**/field` rejects;
- zero-match binding returns `TEMPLATE_BINDING_TARGET_INVALID`.

- [ ] **Step 3: Run compiler tests to establish RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_compiler.py -q
```

Expected: FAIL because the application package/compiler does not exist.

- [ ] **Step 4: Define application ports and implement strict compilation**

```python
class TemplateRegistry(Protocol):
    def register(self, template: CompiledTemplate, source_bytes: bytes, source_suffix: str) -> CompiledTemplate: ...
    def get(self, template_id: str, version: str) -> CompiledTemplate: ...


class SchemaValidatorPort(Protocol):
    def check_schema(self, schema: dict[str, JsonValue]) -> tuple[ValidationIssue, ...]: ...
    def validate(self, instance: JsonValue, schema: dict[str, JsonValue]) -> tuple[ValidationIssue, ...]: ...
```

Compiler sequence is fixed: root shape → metadata → Schema adapter → limits → binding parsing/invariants → static target reachability → canonical object → hash → `CompiledTemplate`.

Canonical object includes metadata, output schema and sorted bindings, but excludes source path, YAML comments and source suffix. Sort `domain_tags` and `allowed_source_types`; reject duplicates before sorting so accidental duplicates are visible.

- [ ] **Step 5: Run compiler and prior tests**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_contracts.py tests/unit/test_structured_output_canonical.py tests/unit/test_structured_output_policies.py tests/unit/test_structured_output_source_loader.py tests/unit/test_structured_output_jsonschema.py tests/unit/test_structured_output_compiler.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/structured_output structured_output_application structured_output_infrastructure tests/unit/test_structured_output_compiler.py
```

Expected: all pass.

- [ ] **Step 6: Commit the compiler and fixtures**

```powershell
git add structured_output_application tests/fixtures/structured_output tests/unit/test_structured_output_compiler.py
git commit -m "feat(output): compile cross-domain templates"
```

---

### Task 5: Validate Structured Candidates Against One EvidencePack

**Files:**
- Create: `structured_output_application/validators.py`
- Modify: `structured_output_application/__init__.py`
- Test: `tests/unit/test_structured_candidate_validator.py`

**Interfaces:**
- Consumes: `CompiledTemplate`, `StructuredCandidateBatch`, `CandidateValidationReport`, pointer helpers, Schema validator, `core_domain.fmea.value_objects.EvidencePack`.
- Produces: `StructuredCandidateValidator.validate(batch, template, evidence_pack) -> CandidateValidationReport`.

- [ ] **Step 1: Write failing happy-path tests for all claim states**

Use the existing deterministic EvidencePack fixture and a template with required/optional/forbidden bindings. Prove:

- known satisfies min/max refs and allowed source type;
- unknown and not_applicable require no refs;
- insufficient_evidence may keep zero or partial refs but report the candidate as structurally valid and not known;
- conflict requires two distinct refs;
- wildcard bindings require a claim for every actual array element;
- candidate/input order is retained while issues are sorted deterministically.

- [ ] **Step 2: Write failing rejection tests**

Parameterize exact expected codes for:

```text
template ID/version/hash mismatch -> TEMPLATE_HASH_MISMATCH or TEMPLATE_NOT_FOUND
evidence pack ID mismatch -> EVIDENCE_PACK_MISMATCH
payload schema failure -> CANDIDATE_SCHEMA_INVALID
claim target absent -> CANDIDATE_TARGET_INVALID
zero/multiple pattern matches -> CANDIDATE_BINDING_AMBIGUOUS
required payload node without claim -> CANDIDATE_EVIDENCE_MISSING
evidence ID absent/current pack mismatch -> CANDIDATE_EVIDENCE_MISSING
source type disallowed -> CANDIDATE_EVIDENCE_SOURCE_FORBIDDEN
state/ref count mismatch -> CANDIDATE_CLAIM_STATE_INVALID
duplicate candidate IDs/targets/evidence IDs -> constructor failure
candidate/claim/resource limit -> TEMPLATE_LIMIT_EXCEEDED
```

- [ ] **Step 3: Run validator tests to establish RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_candidate_validator.py -q
```

Expected: FAIL because `StructuredCandidateValidator` does not exist.

- [ ] **Step 4: Implement full deterministic validation before any downstream use**

Validation order:

1. template and pack identity;
2. batch/candidate resource limits;
3. JSON Schema payload issues;
4. exact claim target resolution;
5. pattern-to-binding match cardinality;
6. required binding coverage over expanded actual payload nodes;
7. EvidencePack membership/source type;
8. state/min/max rules.

Build `refs_by_id` once. Never use retrieval score/rank/metadata. Return every non-fatal candidate issue and `valid=False` if any issue exists. Issue sort key is `(candidate input index, target or pointer, code, binding or "")`.

- [ ] **Step 5: Run candidate and evidence regressions**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_candidate_validator.py tests/unit/test_fmea_evidence_provider.py tests/integration/test_fmea_evidence_handoff.py -q
& '.venv\Scripts\python.exe' -m ruff check structured_output_application/validators.py tests/unit/test_structured_candidate_validator.py
```

Expected: all pass.

- [ ] **Step 6: Commit candidate validation**

```powershell
git add structured_output_application/validators.py structured_output_application/__init__.py tests/unit/test_structured_candidate_validator.py
git commit -m "feat(output): validate evidence-bound candidates"
```

---

### Task 6: Add the Atomic File Registry and Application Service

**Files:**
- Create: `structured_output_infrastructure/file_registry.py`
- Create: `structured_output_application/services.py`
- Modify: `structured_output_infrastructure/__init__.py`
- Test: `tests/unit/test_structured_output_file_registry.py`
- Test: `tests/unit/test_structured_output_service.py`

**Interfaces:**
- Consumes: `TemplateRegistry`, compiler, candidate validator, source loader, Schema adapter and existing EvidencePack codec.
- Produces: `FileTemplateRegistry`; `StructuredOutputService.validate_source()`, `.compile_source()`, `.register_source()`, `.get_template()`, `.make_example()`, `.validate_candidates()`.

- [ ] **Step 1: Write failing registry tests**

Prove:

- files land only at `<root>/<id>/<version>/{source.*,compiled.json,manifest.json}`;
- same ID/version/hash is idempotent and does not change mtimes;
- same ID/version/different hash raises `TEMPLATE_VERSION_CONFLICT`;
- traversal in root/ID/version cannot escape resolved root;
- interrupted temp write leaves no final version directory;
- compiled or manifest tampering raises `TEMPLATE_HASH_MISMATCH`;
- a new registry process reads exactly the same frozen template.

- [ ] **Step 2: Write failing service/example tests**

`make_example()` must produce one deterministic candidate with schema-valid neutral placeholders and unknown/not_applicable claims, including required arrays at `minItems`. Repeated calls return equal batches. It must not use evidence IDs, domain facts, current time or randomness.

Test each service method delegates only to its intended dependency and that candidate validation always loads the registered template before checking the batch.

- [ ] **Step 3: Run tests to establish RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_file_registry.py tests/unit/test_structured_output_service.py -q
```

Expected: FAIL because registry/service modules do not exist.

- [ ] **Step 4: Implement atomic immutable persistence**

Serialize `compiled.json` from `canonical_json`. `manifest.json` contains only ID, version, hash, source suffix and schema dialect. Before write, resolve and verify every target parent is under the configured root. Write to a sibling temporary directory, flush/fsync files, and atomically rename only when all files exist. Remove only that validated temporary directory on failure.

On read, parse `compiled.json`, reconstruct through the same contracts, recompute canonical hash, then compare manifest and directory identity.

- [ ] **Step 5: Implement the application service and deterministic example builder**

The service constructor receives compiler, registry, Schema adapter, validator and limits. Example generation supports the approved schema subset:

- `const` first, then first `enum` item;
- object required properties only;
- arrays generate exactly `minItems` members;
- string uses `"?" * max(1, minLength)` capped by max string length;
- integer/number uses minimum if present, otherwise 0;
- boolean false; null null.

Claims for required binding matches use `unknown` and no evidence IDs. Mark the CLI response with an `example_only` wrapper flag; do not add that flag to `StructuredCandidateBatch`.

- [ ] **Step 6: Run service/registry tests and diff check**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_file_registry.py tests/unit/test_structured_output_service.py -q
& '.venv\Scripts\python.exe' -m ruff check structured_output_application structured_output_infrastructure tests/unit/test_structured_output_file_registry.py tests/unit/test_structured_output_service.py
git diff --check
```

Expected: all pass.

- [ ] **Step 7: Commit registry and service**

```powershell
git add structured_output_application/services.py structured_output_infrastructure tests/unit/test_structured_output_file_registry.py tests/unit/test_structured_output_service.py
git commit -m "feat(output): register immutable templates"
```

---

### Task 7: Expose a Stable Skill CLI

**Files:**
- Create: `scripts/output_template_skill.py`
- Create: `tests/integration/test_output_template_skill_cli.py`
- Modify: `pyproject.toml` (mypy file list only)

**Interfaces:**
- Consumes: `StructuredOutputService`, file registry, loader, compiler, Schema adapter, candidate validator, `decode_evidence_pack()`.
- Produces: process commands `validate`, `compile`, `register`, `show`, `example`, `validate-candidate` with one JSON stdout object and stable exit codes.

- [ ] **Step 1: Write process-level failing CLI tests**

Use `.venv\Scripts\python.exe` in subprocesses. Test every command, compact and `--pretty` output, stdout JSON cardinality, stderr separation and exact exit mapping.

```python
def test_register_and_show_round_trip_across_processes(tmp_path: Path) -> None:
    registered = run_cli("register", str(FMEA_TEMPLATE), "--registry", str(tmp_path))
    shown = run_cli("show", "fuel-combustion-fmea@1.0.0", "--registry", str(tmp_path))
    assert registered.returncode == shown.returncode == 0
    assert payload(registered)["template_hash"] == payload(shown)["template_hash"]
```

Add adversarial argument values containing secret markers/private paths and prove stdout/stderr do not echo them. Test no abbreviations, missing commands, missing registry, invalid candidate, tampered registry and internal exception sanitization.

- [ ] **Step 2: Run CLI tests to establish RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/integration/test_output_template_skill_cli.py -q
```

Expected: FAIL because the script does not exist.

- [ ] **Step 3: Implement parser, composition root and public envelopes**

Success envelope:

```json
{"schema_version":"rag.structured-output.v1","status":"ok","command":"show","result":{}}
```

Error envelope:

```json
{"schema_version":"rag.structured-output.v1","status":"error","error":{"code":"TEMPLATE_NOT_FOUND","message":"Template was not found.","details":{}}}
```

Do not serialize internal exception messages. Public error codes map validation to exit 2 and registry/dependency to exit 3. `compile --out` validates the output path against its resolved parent and writes one canonical UTF-8 JSON file; command stdout still returns the metadata/hash envelope.

For `validate-candidate`, decode the candidate batch with strict unknown-field rejection and use `decode_evidence_pack()` for the pack file before application validation.

- [ ] **Step 4: Add CLI to mypy scope and run process tests**

Append these paths under `[tool.mypy].files`:

```toml
"core_domain/structured_output",
"structured_output_application",
"structured_output_infrastructure",
"scripts/output_template_skill.py",
```

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/integration/test_output_template_skill_cli.py -q
& '.venv\Scripts\python.exe' -m ruff check scripts/output_template_skill.py tests/integration/test_output_template_skill_cli.py
```

Expected: all pass.

- [ ] **Step 5: Commit the CLI**

```powershell
git add scripts/output_template_skill.py tests/integration/test_output_template_skill_cli.py pyproject.toml
git commit -m "feat(output): expose template skill cli"
```

---

### Task 8: Prove Cross-Domain Handoff and Document Template Authoring

**Files:**
- Create: `tests/integration/test_structured_output_cross_domain.py`
- Create: `docs/handoff/generic-structured-output-templates.md`
- Create: `templates/examples/fuel-combustion-fmea.yaml`
- Create: `templates/examples/maintenance-checklist.yaml`
- Create: `templates/examples/research-summary.yaml`

**Interfaces:**
- Consumes: all previous tasks and existing EvidencePack fixture.
- Produces: executable cross-domain acceptance, user-facing Chinese authoring/extension guide, three versioned example templates.

- [ ] **Step 1: Write the failing cross-domain acceptance matrix**

For each example template execute:

```text
source file
 -> safe load
 -> compile
 -> register
 -> reload
 -> make deterministic example
 -> construct evidence-bound candidate
 -> validate candidate
```

Assert one service implementation and one CLI contract handle all domains. Add an import-boundary subprocess proving `import core_domain.structured_output` and `import structured_output_application` do not import FMEA application/infrastructure, QueryService, Chroma, GraphStore or model adapters. Importing `validators` may import only the stable `core_domain.fmea.value_objects` EvidencePack contract.

- [ ] **Step 2: Run acceptance test to verify fixture/docs gap**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/integration/test_structured_output_cross_domain.py -q
```

Expected: FAIL until the final example templates/acceptance fixtures are present.

- [ ] **Step 3: Add production-quality example templates**

Examples must compile under default limits, use no model-specific fields, include title/description/domain tags and document every binding. The FMEA example is only a template demonstration; it must not contain S/O/D or propagation behavior not implemented by Plan A.

- [ ] **Step 4: Write the Chinese handoff guide**

Document:

- M3/M4/M5/FMEA ownership;
- JSON/YAML source anatomy;
- JSON Schema supported/forbidden subset;
- evidence binding pattern rules;
- candidate envelope and all claim states;
- validate/compile/register/show/example/validate-candidate commands;
- version/hash and immutable registry behavior;
- how a human or LLM drafts a template but CLI/human registration gates it;
- how future Excel/Word importers produce the same source contract;
- how Plan B injects DeepSeek without modifying the template core;
- common error codes and migration procedure.

- [ ] **Step 5: Run full scoped verification**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_contracts.py tests/unit/test_structured_output_canonical.py tests/unit/test_structured_output_policies.py tests/unit/test_structured_output_source_loader.py tests/unit/test_structured_output_jsonschema.py tests/unit/test_structured_output_compiler.py tests/unit/test_structured_candidate_validator.py tests/unit/test_structured_output_file_registry.py tests/unit/test_structured_output_service.py tests/integration/test_output_template_skill_cli.py tests/integration/test_structured_output_cross_domain.py tests/unit/test_query_contracts.py tests/unit/test_query_service.py tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_application.py tests/unit/test_fmea_evidence_provider.py tests/integration/test_fmea_evidence_handoff.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/structured_output structured_output_application structured_output_infrastructure scripts/output_template_skill.py tests/unit/test_structured_output_*.py tests/unit/test_structured_candidate_validator.py tests/integration/test_output_template_skill_cli.py tests/integration/test_structured_output_cross_domain.py
git diff --check
```

Expected: all scoped tests pass, Ruff exits 0 and Git reports no whitespace errors.

- [ ] **Step 6: Run full-suite baseline comparison**

```powershell
& '.venv\Scripts\python.exe' -m pytest -s -q
```

Expected: no new failures. The two pre-existing `tests/unit/test_graphrag_integration.py` global-search failures may remain and must be reported separately rather than attributed to Plan A.

- [ ] **Step 7: Commit handoff and examples**

```powershell
git add tests/integration/test_structured_output_cross_domain.py docs/handoff/generic-structured-output-templates.md templates/examples
git commit -m "docs(output): prove cross-domain template handoff"
```

## Plan Self-Review

- Tasks 1-2 establish stable immutable contracts and deterministic primitives before any parser or registry consumes them.
- Task 3 isolates third-party JSON/YAML/JSON-Schema libraries in infrastructure.
- Task 4 compiles standard Schema plus sidecar bindings without importing FMEA or retrieval code.
- Task 5 is the only generic-to-EvidencePack application seam and reads stable domain value objects only.
- Task 6 keeps registry persistence behind a Protocol and makes idempotency/tamper detection executable.
- Task 7 exposes the required RAG skill process contract without network/model calls.
- Task 8 proves cross-domain use, documents human/template migration and retains the existing query/FMEA regression boundary.
- Every task has a genuine RED test, a bounded implementation, targeted verification and an isolated commit.
- DeepSeek V4 Flash/Pro, FMEA candidate mapping, scoring, propagation, UI and importers are absent by design and remain Plan B/later work.
