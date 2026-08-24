# Structured Generation, DeepSeek, and FMEA Candidate Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a provider-neutral, bounded structured-generation loop using DeepSeek V4 Flash for generation and DeepSeek V4 Pro for independent criticism and at most one repair, then conservatively adapt valid outputs into complete non-scored FMEA row suggestions.

**Architecture:** New structured-generation core/application/infrastructure packages consume Plan A `CompiledTemplate`, `StructuredCandidateBatch`, `StructuredCandidateValidator`, and the stable `EvidencePack` value object without changing their contracts. A requests-based DeepSeek adapter implements one model gateway; a separate FMEA profile adapter maps a valid generic result into server-owned `FmeaRow` IDs and review-safe states.

**Tech Stack:** Python 3.11+, frozen dataclasses and Protocols, `orjson`, existing `requests`, DeepSeek OpenAI-compatible Chat Completions, pytest, Ruff, mypy, existing Plan A template registry/validator and FMEA value objects.

**Spec:** `docs/superpowers/specs/2026-08-24-structured-generation-deepseek-fmea-design.md`

## Global Constraints

- Do not change Plan A template root shape, canonical hash, immutable registry layout, ClaimState semantics, or offline commands.
- `core_domain.structured_generation` must not import requests, DeepSeek, FMEA, registry, QueryService, or model SDK code.
- Application code may import only the stable `core_domain.fmea.value_objects.EvidencePack`; the generic pipeline must not import `FmeaRow` or FMEA services.
- Default model aliases are exactly `deepseek-v4-flash` for generation and `deepseek-v4-pro` for critic/repair; the only live base URL is `https://api.deepseek.com`.
- `DEEPSEEK_API_KEY` is the only required secret and must never enter repr, stdout, stderr, prompts, traces, errors, fixtures, commits, or exception messages.
- Hard defaults are 20 candidates, 20 evidence refs, 2,000 chars per quote, 24,000 total evidence chars, 48,000 prompt chars, 128,000 response chars, 8,000 output tokens, 3 logical calls, 6 HTTP attempts, one repair, 30 seconds per request, and 90 seconds per run.
- Repair returns a complete replacement batch, occurs at most once, is never followed by another critic, and can produce at most `needs_review`, never automatic success.
- Only connection errors, timeout, 429, and 500/502/503/504 retry. Authentication, other 4xx, empty content, malformed JSON, schema/claim/critic defects, model mismatch, and limits do not retry.
- Evidence projection sends only `evidence_id`, `source_type`, `source_trust`, `is_primary`, bounded `quote`, and a truncation marker. It never sends workspace, ACL, document identity, locator/path/URL, hidden metadata, or a full document.
- Model output cannot change template, registry, EvidencePack, provider, URL, budget, tools, row IDs, risk, review acceptance, or publication state.
- Automated tests must make no live network call and require no API key. The live smoke is explicit and excluded from default pytest.
- FMEA output is a complete non-scored suggestion: `risk_assessment=None`, `ReviewStatus.SUGGESTED`, `PublicationStatus.UNPUBLISHED`; S/O/D, RPN, propagation, approval and publication remain absent.
- Existing two `tests/unit/test_graphrag_integration.py` global-search baseline failures may remain and must be reported separately; no new scoped failure is acceptable.
- Every task uses RED-GREEN TDD, narrow staging, one or more task-local commits, and a Luna xhigh implementer/reviewer when that channel responds.

---

### Task 1: Add Stable Structured-Generation Contracts, Budgets, and Ports

**Files:**
- Create: `core_domain/structured_generation/__init__.py`
- Create: `core_domain/structured_generation/contracts.py`
- Create: `core_domain/structured_generation/policies.py`
- Create: `structured_generation_application/__init__.py`
- Create: `structured_generation_application/contracts.py`
- Create: `structured_generation_application/ports.py`
- Test: `tests/unit/test_structured_generation_contracts.py`

**Interfaces:**
- Consumes: Plan A `CompiledTemplate`, `StructuredCandidateBatch`, `ValidationIssue`; stable `core_domain.fmea.value_objects.EvidencePack` only in application contracts.
- Produces: `GenerationStage`, `GenerationRunStatus`, `CriticVerdict`, `SemanticSupport`, `StructuredGenerationError`, `GenerationIssue`, `GenerationBudget`, `StructuredModelRequest`, `StructuredModelResponse`, `CriticFinding`, `CriticReport`, `ModelCallTrace`, `GenerationRunResult`, `GenerationRunRequest`, `StructuredModelGateway`, `CandidateBatchCodec`, `CriticReportCodec`.

- [ ] **Step 1: Write failing immutable-contract and boundary tests**

Use literal values so wrong defaults, mutable sequences, secret-bearing reprs and invalid state combinations fail observably:

```python
def test_generation_budget_defaults_and_bounds_are_server_owned() -> None:
    budget = GenerationBudget()
    assert (
        budget.max_candidates,
        budget.max_evidence_refs,
        budget.max_quote_chars_per_ref,
        budget.max_evidence_chars,
        budget.max_prompt_chars,
        budget.max_response_chars,
        budget.max_output_tokens,
        budget.max_logical_calls,
        budget.max_http_attempts,
        budget.max_repairs,
        budget.request_timeout_seconds,
        budget.total_timeout_seconds,
    ) == (20, 20, 2000, 24000, 48000, 128000, 8000, 3, 6, 1, 30.0, 90.0)
    with pytest.raises(StructuredGenerationError, match="configured limit"):
        GenerationBudget(max_repairs=2)


def test_model_response_rejects_secret_or_invalid_audit_values() -> None:
    response = StructuredModelResponse(
        content='{"ok":true}', model_id="deepseek-v4-flash", finish_reason="stop",
        input_tokens=10, output_tokens=4, response_hash="a" * 64, http_attempts=1,
    )
    assert "secret" not in repr(response).lower()
    with pytest.raises(StructuredGenerationError):
        replace(response, http_attempts=0)


def test_core_generation_import_has_no_provider_or_fmea_side_effects() -> None:
    script = """
import json, sys
import core_domain.structured_generation
forbidden = ('requests', 'model_adapters', 'fmea_application', 'fmea_infrastructure')
print(json.dumps(sorted(name for name in sys.modules if name.startswith(forbidden))))
"""
    completed = subprocess.run([sys.executable, "-c", script], text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout) == []
```

Also test exact-enum values, tuple normalization, duplicate critic findings, invalid SHA-256, blank IDs/codes, `GenerationRunResult` status/batch invariants, and `StructuredGenerationError(code, stage, retryable, attempts)` safe public fields.

- [ ] **Step 2: Run the contract tests to establish RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_generation_contracts.py -q
```

Expected: import failure because `core_domain.structured_generation` and application contracts do not exist.

- [ ] **Step 3: Implement the frozen contracts and invariant helpers**

Public signatures must be exact:

```python
class StructuredGenerationError(ValueError):
    def __init__(self, code: str, message: str, *, stage: GenerationStage | None = None,
                 retryable: bool = False, attempts: int = 0) -> None: ...

@dataclass(frozen=True, slots=True)
class GenerationBudget:
    max_candidates: int = 20
    max_evidence_refs: int = 20
    max_quote_chars_per_ref: int = 2000
    max_evidence_chars: int = 24000
    max_prompt_chars: int = 48000
    max_response_chars: int = 128000
    max_output_tokens: int = 8000
    max_logical_calls: int = 3
    max_http_attempts: int = 6
    max_repairs: int = 1
    request_timeout_seconds: float = 30.0
    total_timeout_seconds: float = 90.0

@dataclass(frozen=True, slots=True)
class StructuredModelRequest:
    stage: GenerationStage
    model_id: str
    system_prompt: str
    user_prompt: str
    max_output_tokens: int
    thinking_enabled: bool
    reasoning_effort: Literal["low", "high", "max"] | None

@dataclass(frozen=True, slots=True)
class StructuredModelResponse:
    content: str
    model_id: str
    finish_reason: str
    input_tokens: int | None
    output_tokens: int | None
    response_hash: str
    http_attempts: int

class StructuredModelGateway(Protocol):
    def complete(self, request: StructuredModelRequest, *, max_attempts: int,
                 timeout_seconds: float) -> StructuredModelResponse: ...

class CandidateBatchCodec(Protocol):
    def decode_batch(self, content: str) -> StructuredCandidateBatch: ...

class CriticReportCodec(Protocol):
    def decode_critic(self, content: str) -> CriticReport: ...
```

`GenerationRunRequest` is the only new generic application contract that imports `EvidencePack`; it validates nonblank `run_id`/`task`, approved model aliases, and template/evidence identities without copying or mutating either input.

- [ ] **Step 4: Run Task 1 tests, import boundary, Ruff, and mypy**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_generation_contracts.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/structured_generation structured_generation_application tests/unit/test_structured_generation_contracts.py
& '.venv\Scripts\python.exe' -m mypy core_domain/structured_generation structured_generation_application
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- core_domain/structured_generation structured_generation_application tests/unit/test_structured_generation_contracts.py
git commit -m "feat(output): add structured generation contracts"
```

---

### Task 2: Strict Candidate/Critic JSON Codecs and Semantic Critic Validation

**Files:**
- Create: `structured_generation_infrastructure/__init__.py`
- Create: `structured_generation_infrastructure/json_codec.py`
- Create: `structured_generation_application/critic_validation.py`
- Modify: `structured_generation_application/__init__.py`
- Test: `tests/unit/test_structured_generation_json_codec.py`
- Test: `tests/unit/test_structured_generation_critic.py`

**Interfaces:**
- Consumes: Task 1 codecs/contracts, Plan A frozen candidate contracts and `EvidencePack`.
- Produces: `StrictCandidateBatchCodec.decode_batch()`, `StrictCriticReportCodec.decode_critic()`, `validate_critic_report(report, batch, pack) -> tuple[GenerationIssue, ...]`.

- [ ] **Step 1: Write strict-codec RED tests**

Use a hand-authored valid JSON object and mutate one boundary at a time:

```python
def test_batch_codec_decodes_one_exact_object() -> None:
    batch = StrictCandidateBatchCodec().decode_batch(VALID_BATCH_JSON)
    assert batch.template_id == "maintenance-checklist"
    assert batch.candidates[0].claims[0].target == "/checks/0/result"


@pytest.mark.parametrize("mutation", ["unknown_root", "unknown_claim", "bad_hash", "duplicate_claim", "trailing_json"])
def test_batch_codec_fails_closed_without_echoing_content(mutation: str) -> None:
    secret = "sk-private-codec-marker"
    with pytest.raises(StructuredGenerationError) as caught:
        StrictCandidateBatchCodec().decode_batch(invalid_batch(mutation, secret))
    assert caught.value.code == "MODEL_OUTPUT_INVALID"
    assert secret not in str(caught.value)
```

Critic JSON is exactly:

```json
{
  "verdict": "accept",
  "findings": [{
    "candidate_id": "candidate-1",
    "target": "/failure_mode",
    "support": "supported",
    "code": "EVIDENCE_SUPPORTS_CLAIM",
    "evidence_ids": ["ev-1"],
    "explanation": "The cited quote directly states the failure mode."
  }],
  "summary": "All evidence-bearing claims are supported."
}
```

Reject unknown fields, duplicate candidate/target pairs, blank/overlong strings, invalid support/verdict, non-array evidence IDs, trailing JSON, and responses over the codec byte/character limit.

- [ ] **Step 2: Write critic-reference RED tests**

```python
def test_critic_requires_exact_coverage_of_evidence_bearing_claims(
    valid_batch: StructuredCandidateBatch, fixture_pack: EvidencePack
) -> None:
    report = CriticReport(verdict=CriticVerdict.ACCEPT, findings=(), summary="none")
    issues = validate_critic_report(report, valid_batch, fixture_pack)
    assert [(issue.code, issue.pointer) for issue in issues] == [
        ("CRITIC_FINDING_MISSING", "/candidates/candidate-1/claims/failure_mode")
    ]


def test_critic_cannot_cite_another_claim_or_pack() -> None:
    report = critic_with(candidate_id="candidate-1", target="/failure_mode", evidence_ids=("ev-outside",))
    assert {issue.code for issue in validate_critic_report(report, valid_batch, fixture_pack)} == {
        "CRITIC_EVIDENCE_INVALID"
    }
```

Also prove `known + contradicted/not_supported + accept` is invalid, conflict/partial cannot produce `accept`, and deterministic issue ordering is stable.

- [ ] **Step 3: Run Task 2 tests to establish RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_generation_json_codec.py tests/unit/test_structured_generation_critic.py -q
```

Expected: missing codec/critic modules.

- [ ] **Step 4: Implement strict decoders and critic validation**

Use `orjson.loads` only after checking response length. A private exact-object helper must compare `set(mapping)` to the required key set. Construct Plan A dataclasses rather than reimplementing their invariant rules. Convert every JSON/type/value failure to:

```python
StructuredGenerationError(
    "MODEL_OUTPUT_INVALID",
    "Model output is not a valid structured-generation object.",
)
```

`validate_critic_report()` derives expected findings from claims whose state is `known`, `conflict`, or `insufficient_evidence` and whose `evidence_ids` are nonempty. It returns stable sorted `GenerationIssue` values and never mutates or normalizes the report.

- [ ] **Step 5: Run cumulative codec/critic verification**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_generation_contracts.py tests/unit/test_structured_generation_json_codec.py tests/unit/test_structured_generation_critic.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/structured_generation structured_generation_application structured_generation_infrastructure tests/unit/test_structured_generation_contracts.py tests/unit/test_structured_generation_json_codec.py tests/unit/test_structured_generation_critic.py
& '.venv\Scripts\python.exe' -m mypy core_domain/structured_generation structured_generation_application structured_generation_infrastructure
git diff --check
```

Expected: all pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add -- structured_generation_application structured_generation_infrastructure tests/unit/test_structured_generation_json_codec.py tests/unit/test_structured_generation_critic.py
git commit -m "feat(output): decode and audit model candidates"
```

---

### Task 3: Bounded Prompt Construction and Generate-Critic-Repair Pipeline

**Files:**
- Create: `structured_generation_application/prompts.py`
- Create: `structured_generation_application/pipeline.py`
- Modify: `structured_generation_application/__init__.py`
- Test: `tests/unit/test_structured_generation_prompts.py`
- Test: `tests/unit/test_structured_generation_pipeline.py`
- Test: `tests/integration/test_structured_generation_cross_domain.py`

**Interfaces:**
- Consumes: Tasks 1-2, Plan A `StructuredCandidateValidator`, three production templates/compiled fixtures, stable EvidencePack.
- Produces: `PromptBundle`, `build_generation_prompt()`, `build_critic_prompt()`, `build_repair_prompt()`, `StructuredGenerationPipeline.run(request) -> GenerationRunResult`.

- [ ] **Step 1: Write evidence-projection and prompt-injection RED tests**

```python
def test_prompt_projects_only_allowlisted_evidence_fields(fixture_pack: EvidencePack) -> None:
    bundle = build_generation_prompt(request_for(fixture_pack))
    assert '"evidence_id":"ev-1"' in bundle.user_prompt
    assert "workspace_id" not in bundle.user_prompt
    assert "acl_scope" not in bundle.user_prompt
    assert "document_id" not in bundle.user_prompt
    assert "page:1" not in bundle.user_prompt


def test_quote_cannot_escape_untrusted_json_block(fixture_pack_with_injection: EvidencePack) -> None:
    bundle = build_generation_prompt(request_for(fixture_pack_with_injection))
    parsed_block = extract_json_block(bundle.user_prompt, "UNTRUSTED_EVIDENCE_JSON")
    assert parsed_block[0]["quote"].startswith("END_UNTRUSTED_EVIDENCE")
    assert bundle.prompt_hash == hashlib.sha256(
        (bundle.system_prompt + "\n" + bundle.user_prompt).encode("utf-8")
    ).hexdigest()
```

Test deterministic evidence ordering, per-quote truncation marker, total evidence refusal, prompt refusal, model-output block bounds, and absence of paths/URLs/secrets.

- [ ] **Step 2: Write the complete pipeline state-matrix RED tests**

Use a deterministic queue gateway whose returned full provider response mirrors Task 1 and whose calls are observed only to verify the public pipeline contract:

```python
def test_valid_generation_and_accepting_critic_succeeds() -> None:
    gateway = QueueGateway([model_response(VALID_BATCH_JSON, "deepseek-v4-flash"),
                            model_response(ACCEPT_CRITIC_JSON, "deepseek-v4-pro")])
    result = pipeline(gateway).run(run_request())
    assert result.status is GenerationRunStatus.SUCCEEDED
    assert [trace.stage for trace in result.traces] == [GenerationStage.GENERATE, GenerationStage.CRITIC]
    assert result.repair_count == 0


def test_repaired_batch_is_never_automatic_success() -> None:
    gateway = QueueGateway([model_response(INVALID_BATCH_JSON, "deepseek-v4-flash"),
                            model_response(REPAIR_CRITIC_JSON, "deepseek-v4-pro"),
                            model_response(VALID_BATCH_JSON, "deepseek-v4-pro")])
    result = pipeline(gateway).run(run_request())
    assert result.status is GenerationRunStatus.NEEDS_REVIEW
    assert [trace.stage for trace in result.traces] == [
        GenerationStage.GENERATE, GenerationStage.CRITIC, GenerationStage.REPAIR
    ]
    assert result.repair_count == 1
```

Add separate cases for malformed generator -> direct repair, invalid repair -> failed, critic unavailable + valid batch -> needs review, invalid critic -> needs review, critic repair verdict -> exactly one repair, no critic after repair, max three logical calls, max six attempts across responses/errors, 90-second deadline, deterministic validation issues retained, and no batch fabrication on failure.

- [ ] **Step 3: Write cross-domain RED acceptance**

Compile FMEA demonstration, maintenance checklist and research summary through the existing compiler. For each, provide one valid model batch and critic report and assert the same pipeline type returns `succeeded`. Use EvidencePacks containing `primary_document`, `rag_text`, `graphrag_relation`, and `graphrag_community` across the matrix. Assert no query/retrieval/model-provider module besides the injected gateway is imported.

- [ ] **Step 4: Run prompt/pipeline tests to establish RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_generation_prompts.py tests/unit/test_structured_generation_pipeline.py tests/integration/test_structured_generation_cross_domain.py -q
```

Expected: missing prompt and pipeline modules.

- [ ] **Step 5: Implement prompt builders and the explicit pipeline state machine**

Required signature:

```python
@dataclass(frozen=True, slots=True)
class PromptBundle:
    system_prompt: str
    user_prompt: str
    prompt_hash: str

class StructuredGenerationPipeline:
    def __init__(self, *, gateway: StructuredModelGateway,
                 batch_codec: CandidateBatchCodec, critic_codec: CriticReportCodec,
                 candidate_validator: StructuredCandidateValidator,
                 monotonic: Callable[[], float] = time.monotonic) -> None: ...

    def run(self, request: GenerationRunRequest) -> GenerationRunResult: ...
```

Implement stages as named private methods rather than recursion. Track logical calls, attempts, elapsed time and repair count in one local run state. Catch only `StructuredGenerationError`; an unexpected exception remains an internal error for the CLI boundary. Failed gateway calls produce a trace with `response_hash=None`, `finish_reason=None`, safe `error_code`, and consumed attempts.

- [ ] **Step 6: Run cumulative pipeline verification**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_generation_contracts.py tests/unit/test_structured_generation_json_codec.py tests/unit/test_structured_generation_critic.py tests/unit/test_structured_generation_prompts.py tests/unit/test_structured_generation_pipeline.py tests/integration/test_structured_generation_cross_domain.py tests/unit/test_structured_candidate_validator.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/structured_generation structured_generation_application structured_generation_infrastructure tests/unit/test_structured_generation_contracts.py tests/unit/test_structured_generation_json_codec.py tests/unit/test_structured_generation_critic.py tests/unit/test_structured_generation_prompts.py tests/unit/test_structured_generation_pipeline.py tests/integration/test_structured_generation_cross_domain.py
& '.venv\Scripts\python.exe' -m mypy core_domain/structured_generation structured_generation_application structured_generation_infrastructure
git diff --check
```

Expected: all pass.

- [ ] **Step 7: Commit Task 3**

```powershell
git add -- structured_generation_application tests/unit/test_structured_generation_prompts.py tests/unit/test_structured_generation_pipeline.py tests/integration/test_structured_generation_cross_domain.py
git commit -m "feat(output): orchestrate bounded model generation"
```

---

### Task 4: DeepSeek V4 HTTP Gateway, Retry Budget, and Environment Configuration

**Files:**
- Create: `structured_generation_infrastructure/retry.py`
- Create: `structured_generation_infrastructure/deepseek_gateway.py`
- Modify: `structured_generation_infrastructure/__init__.py`
- Test: `tests/unit/test_deepseek_structured_gateway.py`

**Interfaces:**
- Consumes: Task 1 `StructuredModelRequest/Response/Error` and gateway Protocol.
- Produces: `DeepSeekStructuredGateway`, `build_deepseek_gateway_from_env()`, deterministic transient retry helper.

- [ ] **Step 1: Write exact outbound-request RED tests with a complete fake response**

```python
def test_flash_request_uses_json_output_and_disables_thinking() -> None:
    session = FakeSession([http_json(200, COMPLETE_FLASH_RESPONSE)])
    response = DeepSeekStructuredGateway(api_key="test-key", session=session, sleeper=no_sleep).complete(
        flash_request(), max_attempts=2, timeout_seconds=30.0
    )
    sent = session.requests[0]
    assert sent.url == "https://api.deepseek.com/chat/completions"
    assert sent.headers == {"Authorization": "Bearer test-key", "Content-Type": "application/json"}
    assert sent.json["response_format"] == {"type": "json_object"}
    assert sent.json["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in sent.json
    assert response.model_id == "deepseek-v4-flash"
    assert response.http_attempts == 1


def test_pro_request_enables_high_thinking_without_sampling_parameters() -> None:
    sent = complete_once(critic_request()).request_json
    assert sent["thinking"] == {"type": "enabled"}
    assert sent["reasoning_effort"] == "high"
    assert not ({"temperature", "top_p", "presence_penalty", "frequency_penalty"} & set(sent))
```

The complete fake response includes `id`, `object`, `created`, `model`, `choices[0].index`, `choices[0].message.role/content/reasoning_content`, `finish_reason`, and `usage.prompt_tokens/completion_tokens/total_tokens`. Assert `reasoning_content` and raw response are absent from the returned dataclass.

- [ ] **Step 2: Write retry/error/security RED tests**

Table-test connection error, timeout, 429 and 500/502/503/504 retry; 400, 401, 403, 404, empty content, invalid JSON response, bad choices/message/usage, and returned model mismatch do not retry. Prove max attempts, injected backoff, safe error messages and attempt counts:

```python
def test_rate_limit_retries_within_the_call_budget() -> None:
    session = FakeSession([http_json(429, {"error": {"message": "secret"}}),
                           http_json(200, COMPLETE_FLASH_RESPONSE)])
    response = gateway(session).complete(flash_request(), max_attempts=2, timeout_seconds=30.0)
    assert response.http_attempts == 2
    assert len(session.requests) == 2


def test_authentication_failure_never_echoes_key_or_provider_body() -> None:
    session = FakeSession([http_json(401, {"error": {"message": "sk-leaked"}})])
    with pytest.raises(StructuredGenerationError) as caught:
        gateway(session, api_key="sk-private").complete(flash_request(), max_attempts=3, timeout_seconds=30.0)
    assert (caught.value.code, caught.value.attempts, len(session.requests)) == (
        "MODEL_AUTHENTICATION_FAILED", 1, 1
    )
    assert "sk-private" not in str(caught.value)
    assert "sk-leaked" not in str(caught.value)
```

Test `build_deepseek_gateway_from_env()` requires only `DEEPSEEK_API_KEY`, validates model aliases from the separate run request, never honors a base URL env/request override, and keeps API key out of repr.

- [ ] **Step 3: Run gateway tests to establish RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_deepseek_structured_gateway.py -q
```

Expected: missing gateway and retry modules.

- [ ] **Step 4: Implement gateway and retry classification**

Use the injected session's `.post()` and `response.raise_for_status()` only after classifying status. Parse response JSON without storing it. Compute `response_hash` from UTF-8 `content`; reject blank content, wrong model, non-string finish reason and bool-as-token integers. The public builder is:

```python
def build_deepseek_gateway_from_env(*, session: object | None = None,
                                    sleeper: Callable[[float], None] = time.sleep
                                    ) -> DeepSeekStructuredGateway: ...
```

Backoff is deterministic `min(2 ** (attempt - 1), 4)` seconds and never sleeps after the final attempt. `MODEL_RATE_LIMITED`, `MODEL_TIMEOUT`, and `MODEL_UPSTREAM_UNAVAILABLE` errors retain `retryable=True` and actual attempt count even when the call budget is exhausted.

- [ ] **Step 5: Run cumulative HTTP verification**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_deepseek_structured_gateway.py tests/unit/test_structured_generation_contracts.py tests/unit/test_structured_generation_json_codec.py tests/unit/test_structured_generation_critic.py tests/unit/test_structured_generation_prompts.py tests/unit/test_structured_generation_pipeline.py tests/integration/test_structured_generation_cross_domain.py -q
& '.venv\Scripts\python.exe' -m ruff check structured_generation_infrastructure tests/unit/test_deepseek_structured_gateway.py
& '.venv\Scripts\python.exe' -m mypy core_domain/structured_generation structured_generation_application structured_generation_infrastructure
git diff --check
```

Expected: all pass without network access.

- [ ] **Step 6: Commit Task 4**

```powershell
git add -- structured_generation_infrastructure tests/unit/test_deepseek_structured_gateway.py
git commit -m "feat(output): call DeepSeek structured models safely"
```

---

### Task 5: Complete FMEA Template, Strict Profile, and Conservative Row Adapter

**Files:**
- Create: `templates/examples/fuel-combustion-fmea-full.yaml`
- Create: `templates/fmea_profiles/fuel-combustion-fmea-full.json`
- Create: `fmea_application/structured_candidate_adapter.py`
- Create: `fmea_infrastructure/profile_loader.py`
- Modify: `fmea_application/__init__.py`
- Modify: `fmea_infrastructure/__init__.py`
- Modify: `core_domain/fmea/policies.py`
- Test: `tests/unit/test_fmea_structured_candidate_adapter.py`
- Test: `tests/unit/test_fmea_profile_loader.py`
- Test: `tests/integration/test_fmea_structured_generation_handoff.py`

**Interfaces:**
- Consumes: valid Plan A candidate batch, Task 1 result/critic contracts, existing `FmeaAnalysis`, `FmeaRow`, `EvidencePack` and FMEA status/policy contracts.
- Produces: `FmeaTemplateProfile`, `FmeaAdaptationResult`, `StructuredCandidateFmeaAdapter.adapt()`, `load_fmea_template_profile()` and production template/profile artifacts.

- [ ] **Step 1: Write template/profile RED acceptance**

```python
def test_full_fmea_template_compiles_and_requires_no_risk_or_workflow_fields() -> None:
    template = compiler().compile_path(FULL_FMEA_TEMPLATE)
    assert template.metadata.template_id == "fuel-combustion-fmea-full"
    assert set(template.output_schema["required"]) == {
        "item", "function", "failure_mode", "causes", "mechanisms", "effects",
        "symptoms", "controls", "barriers", "actions",
    }
    serialized = template.canonical_json.lower()
    for forbidden in ("severity", "occurrence", "detection", "rpn", "propagation", "publication"):
        assert forbidden not in serialized


def test_profile_loader_rejects_unknown_fields_and_template_mismatch(tmp_path: Path) -> None:
    profile = load_fmea_template_profile(PROFILE)
    assert profile.fields[0] == ("item_id", "/item")
    with pytest.raises(FmeaDomainError, match="profile"):
        load_fmea_template_profile(write_profile(tmp_path, extra={"expression": "$.item"}))
```

Profile exact fields are `profile_id`, `version`, `template_id`, `template_version`, `fields`; `fields` exact keys are `item_id`, `function_id`, `failure_mode`, `causes`, `mechanisms`, `effects`, `symptoms`, `controls`, `barriers`, `actions` with the literal pointers from the spec.

- [ ] **Step 2: Write deterministic FmeaRow mapping RED tests**

```python
def test_supported_candidate_maps_to_server_owned_fmea_row(
    fixture_analysis: FmeaAnalysis, fixture_pack: EvidencePack
) -> None:
    result = adapter().adapt(
        analysis=fixture_analysis, evidence_pack=fixture_pack,
        template=compiled_full_template(), batch=full_fmea_batch(),
        critic_report=supported_critic(), profile=loaded_profile(), repair_count=0,
        deterministic_issues=(),
    )
    row = result.rows[0]
    assert row.row_id == "fmea-row-" + EXPECTED_ROW_DIGEST
    assert row.item_id == "item-" + EXPECTED_ITEM_DIGEST
    assert row.function_id == "function-" + EXPECTED_FUNCTION_DIGEST
    assert row.risk_assessment is None
    assert row.review_status is ReviewStatus.SUGGESTED
    assert row.publication_status is PublicationStatus.UNPUBLISHED
    assert row.field_evidence == EXPECTED_FIELD_EVIDENCE


def test_repaired_or_uncriticised_candidate_is_never_known() -> None:
    result = adapt(critic_report=None, repair_count=1)
    assert result.needs_review is True
    assert result.rows[0].claim_status is ClaimStatus.INSUFFICIENT_EVIDENCE
    assert all(status is EvidenceSupportStatus.NOT_SUPPORTED for _, status in result.rows[0].field_support)
```

Test normalization and literal SHA-256 digests, array-element evidence aggregation, stable sorting/deduplication, profile/template mismatch, batch/template/pack mismatch, unresolved item/function, conflict/unknown/insufficient priority, conservative support priority, critic findings outside mapped fields, duplicate candidates, and refusal when deterministic issues remain.

- [ ] **Step 3: Write FMEA policy RED regression**

Extend `validate_row_evidence()` to accept `item_id` and `function_id` in both field mappings while still rejecting arbitrary names. Prove old eight fields remain accepted and a known row still requires evidence and non-contradicted support.

- [ ] **Step 4: Run FMEA tests to establish RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_fmea_structured_candidate_adapter.py tests/unit/test_fmea_profile_loader.py tests/integration/test_fmea_structured_generation_handoff.py -q
```

Expected: missing adapter/profile and production artifacts.

- [ ] **Step 5: Implement the strict profile and adapter**

Public signatures:

```python
@dataclass(frozen=True, slots=True)
class FmeaTemplateProfile:
    profile_id: str
    version: str
    template_id: str
    template_version: str
    fields: tuple[tuple[str, str], ...]

@dataclass(frozen=True, slots=True)
class FmeaAdaptationResult:
    rows: tuple[FmeaRow, ...]
    issues: tuple[GenerationIssue, ...]
    needs_review: bool

class StructuredCandidateFmeaAdapter:
    def adapt(self, *, analysis: FmeaAnalysis, evidence_pack: EvidencePack,
              template: CompiledTemplate, batch: StructuredCandidateBatch,
              critic_report: CriticReport | None, profile: FmeaTemplateProfile,
              repair_count: int, deterministic_issues: tuple[ValidationIssue, ...]
              ) -> FmeaAdaptationResult: ...

def load_fmea_template_profile(path: str | Path) -> FmeaTemplateProfile: ...
```

Use normalized Unicode NFKC plus collapsed whitespace only for ID hashes; preserve original payload text in row fields. The conservative support ordering is `NOT_SUPPORTED`, `CONTRADICTED`, `PARTIALLY_SUPPORTED`, `SUPPORTED`. Never persist from the adapter.

- [ ] **Step 6: Run FMEA and Plan A regressions**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_fmea_structured_candidate_adapter.py tests/unit/test_fmea_profile_loader.py tests/integration/test_fmea_structured_generation_handoff.py tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_application.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_evidence_provider.py tests/unit/test_fmea_propagation.py tests/unit/test_fmea_scoring.py tests/unit/test_fmea_states.py tests/integration/test_fmea_evidence_handoff.py tests/unit/test_structured_output_contracts.py tests/unit/test_structured_output_canonical.py tests/unit/test_structured_output_policies.py tests/unit/test_structured_output_source_loader.py tests/unit/test_structured_output_jsonschema.py tests/unit/test_structured_output_compiler.py tests/unit/test_structured_output_file_registry.py tests/unit/test_structured_output_service.py tests/unit/test_structured_candidate_validator.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/fmea fmea_application fmea_infrastructure tests/unit/test_fmea_structured_candidate_adapter.py tests/unit/test_fmea_profile_loader.py tests/integration/test_fmea_structured_generation_handoff.py
git diff --check
```

Expected: all scoped tests pass.

- [ ] **Step 7: Commit Task 5**

```powershell
git add -- templates/examples/fuel-combustion-fmea-full.yaml templates/fmea_profiles/fuel-combustion-fmea-full.json core_domain/fmea/policies.py fmea_application fmea_infrastructure/profile_loader.py fmea_infrastructure/__init__.py tests/unit/test_fmea_structured_candidate_adapter.py tests/unit/test_fmea_profile_loader.py tests/integration/test_fmea_structured_generation_handoff.py
git commit -m "feat(fmea): adapt structured generation candidates"
```

---

### Task 6: Skill CLI, Live Smoke, Documentation, and Final Acceptance

**Files:**
- Create: `structured_generation_application/services.py`
- Create: `scripts/structured_generation_skill.py`
- Create: `tests/integration/test_structured_generation_skill_cli.py`
- Create: `tests/integration/test_structured_generation_live_smoke.py`
- Create: `docs/handoff/structured-generation-deepseek-fmea.md`
- Modify: `pyproject.toml`
- Modify: `structured_generation_application/__init__.py`

**Interfaces:**
- Consumes: Tasks 1-5, existing template registry/compiler/validator, existing `decode_evidence_pack()` and `decode_analysis()`.
- Produces: `StructuredGenerationService`, CLI commands `run`, `run-fmea`, `smoke`, stable `rag.structured-generation.v1` process envelope, Chinese operator/handoff guide.

- [ ] **Step 1: Write CLI RED tests against injected composition**

Import `main(argv, compose=...)` so tests use real parser/serialization and fake only the external gateway composition. Test compact/pretty cardinality and exact exit classes:

```python
def test_run_emits_one_success_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(RUN_ARGS, compose=lambda _: successful_service())
    captured = capsys.readouterr()
    body = orjson.loads(captured.out)
    assert (exit_code, body["schema_version"], body["status"], captured.err) == (
        0, "rag.structured-generation.v1", "succeeded", ""
    )


def test_run_fmea_outputs_unpersisted_suggestion() -> None:
    exit_code, body = invoke_main(RUN_FMEA_ARGS, service=successful_service())
    assert exit_code == 0
    assert body["result"]["fmea"]["persisted"] is False
    assert body["result"]["fmea"]["rows"][0]["review_status"] == "suggested"
    assert body["result"]["fmea"]["rows"][0]["publication_status"] == "unpublished"
```

Cover needs_review exit 4, validation 2, registry/config 3, model 5, internal 1, parser abbreviation rejection, unknown request fields, bounded file reads, missing files, template/profile mismatch, and no raw model content.

- [ ] **Step 2: Write secret/privacy RED tests**

Use marker-bearing argv, API key, request task, evidence quote, path, provider exception and model content. For every error path assert neither stdout nor stderr contains any marker. Assert success output contains only IDs/hashes/safe issues, not prompts, quotes, reasoning content or raw response.

- [ ] **Step 3: Write explicit smoke RED tests**

`smoke` without `DEEPSEEK_API_KEY` must return configuration exit 3 without calling a gateway. With injected fake gateway it performs one Flash logical call using a fixed non-FMEA JSON task and verifies decode. Mark the real test:

```python
@pytest.mark.live_deepseek
def test_live_deepseek_smoke() -> None:
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY is not configured")
    assert run_live_smoke().status is GenerationRunStatus.SUCCEEDED
```

Configure pytest so `live_deepseek` is registered and excluded from default test commands; document the exact explicit command.

- [ ] **Step 4: Run CLI tests to establish RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/integration/test_structured_generation_skill_cli.py -q
```

Expected: missing service and CLI.

- [ ] **Step 5: Implement service composition and CLI**

Service API:

```python
class StructuredGenerationService:
    def __init__(self, *, registry: TemplateRegistry,
                 pipeline: StructuredGenerationPipeline,
                 fmea_adapter: StructuredCandidateFmeaAdapter | None = None) -> None: ...

    def run(self, *, template_id: str, version: str, run_id: str,
            task: str, evidence_pack: EvidencePack) -> GenerationRunResult: ...

    def run_fmea(self, *, template_id: str, version: str, run_id: str,
                 task: str, evidence_pack: EvidencePack, analysis: FmeaAnalysis,
                 profile: FmeaTemplateProfile) -> tuple[GenerationRunResult, FmeaAdaptationResult]: ...
```

CLI `main()` accepts an injectable zero-secret composition callable only as a Python parameter, not a CLI flag or environment escape hatch. The production composition builds the fixed DeepSeek gateway from environment and the existing file registry. Error mapping uses only stable codes/messages.

- [ ] **Step 6: Write the Chinese operator/handoff guide**

Document exact environment configuration, template registration, `run`, `run-fmea`, `smoke`, result statuses, exit codes, cost/call limits, privacy projection, RAG-only/GraphRAG-only/combined behavior, critic/repair semantics, FMEA non-goals, API key rotation, test commands, common errors, and how a second provider implements only `StructuredModelGateway`.

- [ ] **Step 7: Add new packages/scripts to mypy and run Plan B acceptance**

Add these paths to `[tool.mypy].files` without altering other settings:

```toml
"core_domain/structured_generation",
"structured_generation_application",
"structured_generation_infrastructure",
"fmea_application/structured_candidate_adapter.py",
"fmea_infrastructure/profile_loader.py",
"scripts/structured_generation_skill.py",
```

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_generation_contracts.py tests/unit/test_structured_generation_json_codec.py tests/unit/test_structured_generation_critic.py tests/unit/test_structured_generation_prompts.py tests/unit/test_structured_generation_pipeline.py tests/unit/test_deepseek_structured_gateway.py tests/unit/test_fmea_structured_candidate_adapter.py tests/unit/test_fmea_profile_loader.py tests/integration/test_structured_generation_cross_domain.py tests/integration/test_fmea_structured_generation_handoff.py tests/integration/test_structured_generation_skill_cli.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/structured_generation structured_generation_application structured_generation_infrastructure fmea_application/structured_candidate_adapter.py fmea_infrastructure/profile_loader.py scripts/structured_generation_skill.py tests/unit/test_structured_generation_contracts.py tests/unit/test_structured_generation_json_codec.py tests/unit/test_structured_generation_critic.py tests/unit/test_structured_generation_prompts.py tests/unit/test_structured_generation_pipeline.py tests/unit/test_deepseek_structured_gateway.py tests/unit/test_fmea_structured_candidate_adapter.py tests/unit/test_fmea_profile_loader.py tests/integration/test_structured_generation_cross_domain.py tests/integration/test_fmea_structured_generation_handoff.py tests/integration/test_structured_generation_skill_cli.py
& '.venv\Scripts\python.exe' -m mypy core_domain/structured_generation structured_generation_application structured_generation_infrastructure fmea_application/structured_candidate_adapter.py fmea_infrastructure/profile_loader.py scripts/structured_generation_skill.py
git diff --check
```

Expected: all Plan B tests and checks pass without `DEEPSEEK_API_KEY` or network.

- [ ] **Step 8: Run Plan A/FMEA regression and full-suite comparison**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_structured_output_contracts.py tests/unit/test_structured_output_canonical.py tests/unit/test_structured_output_policies.py tests/unit/test_structured_output_source_loader.py tests/unit/test_structured_output_jsonschema.py tests/unit/test_structured_output_compiler.py tests/unit/test_structured_output_file_registry.py tests/unit/test_structured_output_service.py tests/unit/test_structured_candidate_validator.py tests/integration/test_output_template_skill_cli.py tests/integration/test_structured_output_cross_domain.py tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_application.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_evidence_provider.py tests/unit/test_fmea_propagation.py tests/unit/test_fmea_scoring.py tests/unit/test_fmea_states.py tests/integration/test_fmea_evidence_handoff.py -q
& '.venv\Scripts\python.exe' -m pytest -s -q
```

Expected: all scoped Plan A/FMEA regression tests pass. Full suite has no new failures; report the two known GraphRAG global-search failures separately if they remain.

- [ ] **Step 9: Commit Task 6**

```powershell
git add -- structured_generation_application/services.py structured_generation_application/__init__.py scripts/structured_generation_skill.py tests/integration/test_structured_generation_skill_cli.py tests/integration/test_structured_generation_live_smoke.py docs/handoff/structured-generation-deepseek-fmea.md pyproject.toml
git commit -m "feat(output): expose DeepSeek generation skill"
```

## Plan Self-Review

- Task 1 creates only provider-neutral contracts and keeps the concrete EvidencePack dependency in application, not generic core.
- Task 2 makes model JSON and semantic critic output independently strict before orchestration trusts either.
- Task 3 proves all pipeline states with a fake gateway and shares one implementation across three domains and four evidence source types.
- Task 4 is the only live HTTP boundary and maps current official DeepSeek V4 JSON/thinking behavior without changing the existing ordinary-LLM client.
- Task 5 keeps FMEA mapping out of the generic pipeline, derives all IDs server-side, preserves field evidence, and cannot create risk, approval or publication.
- Task 6 exposes both generic and FMEA flows, keeps live smoke explicit, and proves no default test makes a paid call.
- Every spec acceptance criterion maps to at least one executable test or scoped regression command.
- No task implements S/O/D, RPN, propagation, review acceptance, publication, cache, REST/SSE, UI, Excel/Word import or a second provider.
