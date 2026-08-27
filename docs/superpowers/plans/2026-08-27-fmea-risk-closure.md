# FMEA Risk Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned, evidence-bound, model-assisted, human-confirmed S/O/D and risk workflow without weakening the existing review interface.

**Architecture:** Introduce a generic `DomainPack` registry and a dedicated risk capability beside `ReviewService`. Model output creates immutable score proposals; deterministic code validates and calculates risk; only a human command confirms scores. Risk persistence uses additive SQLite migration `003` and a focused repository adapter over the workspace-owned FMEA database.

**Tech Stack:** Python 3.11+, frozen dataclasses, Enum, Protocol, Pydantic 2.13, FastAPI 0.135+, SQLite, orjson, PyYAML, existing structured-generation/DeepSeek gateway, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-27-full-fmea-modular-product-design.md`

## Global Constraints

- Preserve existing `FmeaRow`, `EvidencePack`, review REST/CLI, evidence membership, projection-safe model view, and exact current/legacy audit decoding.
- Consume `rag_only`, `graphrag_local`, `graphrag_global`, `graphrag_only`, `combined`, `auto`, and `custom` only through the same immutable EvidencePack boundary; FMEA code never imports or branches on a retrieval backend.
- Model actors create proposals only; only a human with the `risk_reviewer` role may confirm or reject scores.
- Unknown, missing, or conflicting required dimensions never become zero and never produce a valid RPN.
- Bind every proposal and confirmation to workspace, row version, EvidencePack, DomainPack, template, and scoring-rule versions.
- A row, evidence, operating-context, DomainPack, template, or rule-pack change invalidates prior confirmation; it never re-confirms automatically.
- All writes require canonical UUID idempotency keys and optimistic version preconditions.
- Keep SQLite and local-auth details outside the domain and application service.
- Default tests use deterministic fakes and incur no external-model cost.
- Additive migration only; existing review records remain readable and immutable.

## File map

- `core_domain/fmea/domain_pack.py`: immutable DomainPack manifest contracts.
- `core_domain/fmea/entities.py`: backward-compatible typed extension values and field claims.
- `core_domain/fmea/value_objects.py`: additive supplemental EvidencePack lineage.
- `core_domain/fmea/scoring.py`: additive risk status, dimension, proposal, and assessment-record contracts around existing `RiskAssessment`.
- `fmea_application/assistance_contracts.py`: provider-neutral immutable assistance request/suggestion envelope.
- `fmea_application/analysis_assistance_service.py`: scope/system-boundary drafting without canonical writes.
- `fmea_application/assistance_service.py`: human-only, version-checked suggestion decisions and typed adoption handlers.
- `fmea_application/risk_contracts.py`: commands, results, model request/response, prepared transaction DTOs.
- `fmea_application/risk_service.py`: authorization, proposal, confirmation, rejection, invalidation, and query orchestration.
- `fmea_application/ports.py`: DomainPack, rule-pack, risk repository, and risk suggestion ports.
- `fmea_infrastructure/domain_pack_registry.py`: contained immutable file registry.
- `fmea_infrastructure/assistance_repository_sqlite.py`: shared append-only suggestion/decision persistence.
- `fmea_infrastructure/risk_repository_sqlite.py`: risk persistence against the existing FMEA database.
- `fmea_infrastructure/analysis_assistance_generator.py`: structured model adapter for scope/system-boundary drafts.
- `fmea_infrastructure/risk_generator.py`: structured model adapter for score proposals.
- `fmea_infrastructure/migrations/003_fmea_risk_closure.sql`: DomainPack/rule/risk/idempotency/outbox tables.
- `domain_packs/fuel-combustion/manifest.yaml`: first pack manifest.
- `domain_packs/fuel-combustion/scoring/sod-rpn-1.0.0.yaml`: first scoring rule pack.
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_risk_contracts.py`: strict REST schemas.
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_risk_v1.py`: risk resources and commands.
- `scripts/fmea_skill.py`: shared `assist` and Phase 1 `risk` CLI command groups.
- `scripts/run_fmea_risk_acceptance.py` and `scripts/verify_fmea_risk_acceptance.py`: deterministic independent acceptance.

---

### Task 1: Freeze DomainPack and risk-domain contracts

**Files:**
- Create: `core_domain/fmea/domain_pack.py`
- Modify: `core_domain/fmea/entities.py`
- Modify: `core_domain/fmea/scoring.py`
- Modify: `core_domain/fmea/states.py`
- Modify: `core_domain/fmea/value_objects.py`
- Modify: `core_domain/fmea/__init__.py`
- Create: `fmea_application/assistance_contracts.py`
- Test: `tests/unit/test_fmea_domain_pack.py`
- Test: `tests/unit/test_fmea_assistance_contracts.py`
- Test: `tests/unit/test_fmea_scoring.py`
- Test: `tests/unit/test_fmea_entities.py`
- Test: `tests/unit/test_fmea_evidence.py`

**Interfaces:**
- Consumes: existing `RiskAssessment`, `ScoringRulePack`, `VersionSet`, and `ClaimStatus`.
- Produces: `DomainPackManifest`, `FieldValue`, `FieldClaim`, EvidencePack lineage, the shared `AssistanceRequest`/`AssistanceSuggestion` envelope and `AssistanceDecision`, `RiskStatus`, `ScoreDimension`, `RiskProposal`, `RiskAssessmentRecord`, and `validate_risk_confirmation()`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_domain_pack_rejects_duplicate_template_identity():
    with pytest.raises(FmeaDomainError, match="duplicate template identity"):
        DomainPackManifest(
            pack_id="fuel-combustion",
            version="1.0.0",
            content_hash="a" * 64,
            compatible_schema_ids=("graphrag.fmea.v1",),
            analysis_types=("design_fmea",),
            template_identities=(("fuel-fmea", "1.0.0"), ("fuel-fmea", "1.0.0")),
            scoring_rule_identities=(("fuel-sod-rpn", "1.0.0"),),
            propagation_rule_identities=(),
            extension_fields=(),
        )


def test_missing_required_dimension_never_produces_confirmed_rpn():
    proposal = risk_proposal(severity=9, occurrence=None, detection=6)
    with pytest.raises(FmeaDomainError, match="required risk dimension"):
        validate_risk_confirmation(proposal, required_dimensions=("severity", "occurrence", "detection"))


def test_existing_row_constructor_remains_valid_and_extensions_are_typed():
    row = legacy_fmea_row()
    assert row.extension_values == ()
    extended = replace(row, extension_values=(FieldValue("gas_turbine.fuel.wobbe_index", "decimal", "48.2"),))
    validate_extension_values(extended, compiled_template())


def test_assistance_is_immutable_unapplied_and_version_bound():
    suggestion = assistance_suggestion(kind=AssistanceKind.SCORE_RECOMMENDATION)
    assert suggestion.applied is False
    assert suggestion.target_record_version == 3
    assert suggestion.evidence_pack_ids == ("pack-1",)
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_domain_pack.py tests/unit/test_fmea_assistance_contracts.py tests/unit/test_fmea_scoring.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_evidence.py -q`

Expected: FAIL because the new contracts and validation function do not exist.

- [ ] **Step 3: Add the immutable contracts**

```python
class RiskStatus(str, Enum):
    UNSCORED = "unscored"
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"


@dataclass(frozen=True, slots=True)
class ScoreDimension:
    name: str
    value: int | None
    evidence_ids: tuple[str, ...]
    reason: str
    uncertainty: str | None


@dataclass(frozen=True, slots=True)
class RiskAssessmentRecord:
    assessment_id: str
    workspace_id: str
    row_id: str
    source_record_version: int
    evidence_pack_id: str
    domain_pack_id: str
    domain_pack_version: str
    rule_pack_id: str
    rule_pack_version: str
    status: RiskStatus
    dimensions: tuple[ScoreDimension, ...]
    derived: RiskAssessment | None
    proposal_id: str | None
    assistance_suggestion_id: str | None
    confirmer_actor_id: str | None
    invalidated_reason: str | None
    record_version: int
    created_at: str
    updated_at: str
```

Add `FieldValue(field_key, value_type, value)` and `FieldClaim(field_key, claim_status, support_status, evidence_ids, uncertainty, conflict_ids)` as frozen validated values. Add `extension_values=()` and `field_claims=()` at the end of `FmeaRow` so old constructors and stored rows remain compatible; validate them against the compiled template and preserve legacy `field_evidence`, `field_support`, and row-level `claim_status` as readable compatibility projections.

Add optional `parent_pack_refs: tuple[tuple[str, str], ...] = ()`, `lineage_reason: str | None = None`, and `lineage_schema_version: str | None = None` at the end of `EvidencePack`; each parent reference carries pack ID plus hash. Include the envelope in new supplemental-pack hashing and reject self-reference, cycles, cross-workspace parents, unknown/mismatched parent hashes, and silent replacement. Existing packs with empty lineage continue to decode and verify under the legacy hash algorithm; supplemental packs require `graphrag.fmea.evidence-lineage.v1`.

Define `AssistanceKind` with `analysis_scope_draft`, `template_field_mapping`, `fmea_candidate_generation`, `score_recommendation`, `propagation_hypothesis`, `evidence_gap_explanation`, `review_summary`, `approval_readiness_checklist`, `migration_patch_proposal`, and `export_narrative_draft`. `AssistanceRequest` carries bounded target/evidence/version identities. Generic frozen `AssistanceSuggestion[T]` carries structured payload, evidence/conflict/uncertainty metadata, model/prompt hashes, run trace, target record version, and hard-coded `applied=False`. `AssistanceDecisionAction` defines `adopt`, `partial_adopt`, `edit_and_adopt`, `reject`, `defer`, and `request_evidence`; immutable `AssistanceDecision` records the exact suggestion hash/version, target version, human actor, optional bounded edits, reason, idempotency identity, and resulting canonical resource identity.

Implement `DomainPackManifest.__post_init__` with non-empty identities, semantic-version syntax, lowercase SHA-256, unique identities and extension keys, and a required compatibility range. Add deterministic validation that rejects duplicate dimensions, out-of-range values, missing required dimensions, evidence IDs outside the pack, and a derived RPN when an input is unknown.

Extend the existing `ScoringRulePack` additively with `required_dimensions: tuple[str, ...] = ("severity", "occurrence", "detection")` and `dimension_anchors: tuple[tuple[str, tuple[tuple[int, str], ...]], ...] = ()`. Preserve `severity_anchors` and `detection_positions` for backward compatibility, validate that every required dimension has a complete `score_min..score_max` anchor set once `dimension_anchors` is supplied, and keep existing constructors valid through the defaults.

- [ ] **Step 4: Run focused tests and domain regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_domain_pack.py tests/unit/test_fmea_assistance_contracts.py tests/unit/test_fmea_scoring.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_evidence.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the domain slice**

```powershell
git add core_domain/fmea/domain_pack.py core_domain/fmea/entities.py core_domain/fmea/scoring.py core_domain/fmea/states.py core_domain/fmea/value_objects.py core_domain/fmea/__init__.py fmea_application/assistance_contracts.py tests/unit/test_fmea_domain_pack.py tests/unit/test_fmea_assistance_contracts.py tests/unit/test_fmea_scoring.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_evidence.py
git commit -m "feat(fmea): define domain packs and risk records"
```

### Task 2: Add immutable DomainPack and scoring-rule registries

**Files:**
- Modify: `fmea_application/ports.py`
- Create: `fmea_infrastructure/domain_pack_registry.py`
- Create: `domain_packs/fuel-combustion/manifest.yaml`
- Create: `domain_packs/fuel-combustion/scoring/sod-rpn-1.0.0.yaml`
- Test: `tests/unit/test_fmea_domain_pack_registry.py`
- Test: `tests/integration/test_fmea_fuel_combustion_pack.py`

**Interfaces:**
- Consumes: `DomainPackManifest`, existing `ScoringRulePack`, `TemplateCompiler`, and `FileTemplateRegistry` containment/hash patterns.
- Produces: `DomainPackRegistry.get(pack_id, version)`, `ScoringRuleRegistry.get(rule_pack_id, version)`, and immutable registration methods.

- [ ] **Step 1: Write registry identity and collision tests**

```python
def test_same_domain_pack_identity_with_different_body_is_rejected(tmp_path):
    registry = FileDomainPackRegistry(tmp_path)
    registry.register(load_manifest(FUEL_MANIFEST))
    changed = replace(load_manifest(FUEL_MANIFEST), analysis_types=("process_fmea",))
    with pytest.raises(FmeaDomainError, match="DOMAIN_PACK_IDENTITY_CONFLICT"):
        registry.register(changed)


def test_fuel_scoring_pack_declares_required_sod_dimensions():
    pack = FileScoringRuleRegistry(FUEL_RULE_ROOT).get("fuel-sod-rpn", "1.0.0")
    assert pack.required_dimensions == ("severity", "occurrence", "detection")
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_domain_pack_registry.py tests/integration/test_fmea_fuel_combustion_pack.py -q`

Expected: FAIL because registries and pack files are absent.

- [ ] **Step 3: Implement contained immutable registries and pack files**

```python
class DomainPackRegistry(Protocol):
    def register(self, manifest: DomainPackManifest, source_bytes: bytes) -> DomainPackManifest: ...
    def get(self, pack_id: str, version: str) -> DomainPackManifest: ...


class ScoringRuleRegistry(Protocol):
    def register(self, rule_pack: ScoringRulePack, source_bytes: bytes) -> ScoringRulePack: ...
    def get(self, rule_pack_id: str, version: str) -> ScoringRulePack: ...
```

Use canonical JSON hashes, same-identity/same-body replay, same-identity/different-body conflict, temporary sibling writes plus `fsync` and atomic rename, containment and symlink checks. The fuel scoring YAML must define 1-10 anchors for S/O/D, explicit occurrence denominator/window, decision severity, RPN formula `S*O*D`, high-priority threshold, uncertainty behavior, and no automatic zero substitution.

- [ ] **Step 4: Run registry, template, and path-security tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_domain_pack_registry.py tests/integration/test_fmea_fuel_combustion_pack.py tests/unit/test_structured_output_file_registry.py -q`

Expected: PASS.

- [ ] **Step 5: Commit registries and first DomainPack**

```powershell
git add fmea_application/ports.py fmea_infrastructure/domain_pack_registry.py domain_packs/fuel-combustion tests/unit/test_fmea_domain_pack_registry.py tests/integration/test_fmea_fuel_combustion_pack.py
git commit -m "feat(fmea): register fuel combustion risk rules"
```

### Task 3: Persist risk proposals, confirmations, invalidations, and outbox events

**Files:**
- Create: `fmea_application/risk_contracts.py`
- Create: `fmea_infrastructure/migrations/003_fmea_risk_closure.sql`
- Create: `fmea_infrastructure/assistance_repository_sqlite.py`
- Create: `fmea_infrastructure/risk_repository_sqlite.py`
- Modify: `fmea_application/ports.py`
- Test: `tests/unit/test_fmea_assistance_repository_contract.py`
- Test: `tests/unit/test_fmea_risk_repository_contract.py`
- Test: `tests/integration/test_fmea_assistance_sqlite.py`
- Test: `tests/integration/test_fmea_risk_sqlite.py`
- Test: `tests/regression/test_fmea_risk_idempotency.py`

**Interfaces:**
- Consumes: current workspace-owned database, `IdempotencyScope`, `AuditEvent`, and new risk contracts.
- Produces: `AssistanceRepository` for immutable suggestion lookup and decisions, plus `RiskRepository` with atomic proposal, confirmation, rejection, invalidation, audit, idempotency, and outbox operations.

- [ ] **Step 1: Write migration and transaction tests**

```python
def test_confirm_risk_commits_assessment_audit_idempotency_and_outbox_atomically(repository):
    prepared = prepared_risk_confirmation(expected_assessment_version=1)
    result = repository.commit_confirmation(prepared)
    assert result.assessment.status is RiskStatus.CONFIRMED
    assert repository.replay_confirmation(prepared.scope, prepared.payload_hash) == result
    assert repository.list_outbox_events(result.assessment.assessment_id)[-1].event_type == "risk.confirmed"


def test_stale_confirmation_rolls_back_every_table(repository):
    prepared = prepared_risk_confirmation(expected_assessment_version=99)
    with pytest.raises(ReviewError, match="FMEA_RISK_VERSION_CONFLICT"):
        repository.commit_confirmation(prepared)
    assert repository.count_risk_decisions() == 0
    assert repository.count_outbox_events() == 0


def test_assistance_suggestion_is_append_only_and_workspace_scoped(assistance_repository):
    saved = assistance_repository.save_suggestion(prepared_assistance_suggestion())
    assert assistance_repository.get_suggestion(saved.suggestion_id, "ws-1") == saved
    assert assistance_repository.get_suggestion(saved.suggestion_id, "ws-2") is None
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_assistance_repository_contract.py tests/unit/test_fmea_risk_repository_contract.py tests/integration/test_fmea_assistance_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/regression/test_fmea_risk_idempotency.py -q`

Expected: FAIL because migration `003` and repository do not exist.

- [ ] **Step 3: Add schema and focused repository**

Migration `003` creates immutable `fmea_domain_packs`, `fmea_scoring_rule_packs`, `fmea_assistance_suggestions`, `fmea_assistance_decisions`, `fmea_risk_proposals`, `fmea_risk_assessments`, `fmea_risk_decisions`, and additive `fmea_outbox_events`. It adds indexes by workspace/target/kind/status/version and no-update/no-delete triggers for suggestions, decisions, proposals, confirmed assessments, and emitted outbox payloads.

```python
class RiskRepository(Protocol):
    def get_row(self, row_id: str, workspace_id: str) -> FmeaRow | None: ...
    def get_evidence_pack(self, pack_id: str, workspace_id: str) -> EvidencePack | None: ...
    def get_current_assessment(self, row_id: str, workspace_id: str) -> RiskAssessmentRecord | None: ...
    def save_proposal(self, prepared: PreparedRiskProposal) -> RiskAssessmentRecord: ...
    def replay_confirmation(self, scope: IdempotencyScope, payload_hash: str) -> RiskConfirmationResult | None: ...
    def commit_confirmation(self, prepared: PreparedRiskConfirmation) -> RiskConfirmationResult: ...
    def invalidate(self, prepared: PreparedRiskInvalidation) -> RiskAssessmentRecord: ...


class AssistanceRepository(Protocol):
    def save_suggestion(self, prepared: PreparedAssistanceSuggestion) -> AssistanceSuggestion[object]: ...
    def get_suggestion(self, suggestion_id: str, workspace_id: str) -> AssistanceSuggestion[object] | None: ...
    def append_decision(self, prepared: PreparedAssistanceDecision) -> AssistanceDecision: ...
```

Reuse the same migration hash verification and strict JSON decoding rules as `SqliteFmeaRepository`; do not import its private helpers. Extract only genuinely shared canonical codec helpers into `fmea_infrastructure/sqlite_codec.py`, with regression tests proving legacy audit replay is unchanged.

- [ ] **Step 4: Run repository and existing review replay tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_assistance_repository_contract.py tests/unit/test_fmea_risk_repository_contract.py tests/integration/test_fmea_assistance_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/regression/test_fmea_risk_idempotency.py tests/integration/test_fmea_review_sqlite.py tests/regression/test_fmea_review_idempotency.py -q`

Expected: PASS.

- [ ] **Step 5: Commit persistence**

```powershell
git add fmea_application/risk_contracts.py fmea_application/ports.py fmea_infrastructure/migrations/003_fmea_risk_closure.sql fmea_infrastructure/assistance_repository_sqlite.py fmea_infrastructure/risk_repository_sqlite.py fmea_infrastructure/sqlite_codec.py tests/unit/test_fmea_assistance_repository_contract.py tests/unit/test_fmea_risk_repository_contract.py tests/integration/test_fmea_assistance_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/regression/test_fmea_risk_idempotency.py tests/integration/test_fmea_review_sqlite.py
git commit -m "feat(fmea): persist risk lifecycle atomically"
```

### Task 4: Implement model-assisted proposal and human confirmation service

**Files:**
- Create: `fmea_application/analysis_assistance_service.py`
- Create: `fmea_application/assistance_service.py`
- Create: `fmea_application/risk_service.py`
- Create: `fmea_infrastructure/analysis_assistance_generator.py`
- Create: `fmea_infrastructure/risk_generator.py`
- Modify: `fmea_application/service_factory.py`
- Modify: `fmea_infrastructure/composition.py`
- Modify: `fmea_infrastructure/local_auth.py`
- Test: `tests/unit/test_fmea_analysis_assistance_service.py`
- Test: `tests/unit/test_fmea_assistance_service.py`
- Test: `tests/unit/test_fmea_risk_service.py`
- Test: `tests/unit/test_fmea_risk_generator.py`
- Test: `tests/unit/test_fmea_local_auth.py`
- Test: `tests/integration/test_fmea_risk_runs.py`

**Interfaces:**
- Consumes: `ReviewContext`, projection-safe evidence, `StructuredGenerationPipeline`, DomainPack/rule registries, and `RiskRepository`.
- Produces: `AnalysisAssistanceService.suggest_scope()`, `AssistanceDecisionService.decide()`, plus `RiskAssessmentService.propose()`, `confirm()`, `reject()`, `get()`, and `invalidate_if_stale()`.

- [ ] **Step 1: Write authority, calculation, and invalidation tests**

```python
def test_model_proposal_cannot_confirm_risk(service, model_actor):
    proposal = service.propose(start_risk_command(), model_actor)
    assert proposal.status is RiskStatus.PROPOSED
    with pytest.raises(ReviewError, match="FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED"):
        service.confirm(confirm_risk_command(proposal), model_actor)


def test_scope_suggestion_cannot_create_analysis(analysis_assistance, model_actor, repository):
    suggestion = analysis_assistance.suggest_scope(scope_request(), model_actor)
    assert suggestion.kind is AssistanceKind.ANALYSIS_SCOPE_DRAFT
    assert suggestion.applied is False
    assert repository.get_analysis(suggestion.target_id) is None


def test_human_assistance_decision_is_separate_and_version_checked(assistance_decisions, human_actor):
    decision = assistance_decisions.decide(adopt_scope_suggestion(expected_target_version=3), human_actor)
    assert decision.action is AssistanceDecisionAction.ADOPT
    assert decision.actor_type is ActorType.HUMAN


def test_confirmed_risk_is_invalidated_after_row_version_change(service, reviewer):
    confirmed = service.confirm(valid_confirmation(), reviewer)
    service.invalidate_if_stale(confirmed.row_id, changed_dependencies(row_version=2), system_actor())
    assert service.get(confirmed.row_id, reviewer).status is RiskStatus.INVALIDATED
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_analysis_assistance_service.py tests/unit/test_fmea_assistance_service.py tests/unit/test_fmea_risk_service.py tests/unit/test_fmea_risk_generator.py tests/integration/test_fmea_risk_runs.py -q`

Expected: FAIL because the service and generator are absent.

- [ ] **Step 3: Implement bounded proposal and confirmation orchestration**

```python
class RiskSuggestionGenerator(Protocol):
    def generate(self, request: RiskModelRequest) -> AssistanceSuggestion[RiskProposal]: ...


class AnalysisAssistanceService:
    def suggest_scope(
        self, request: AssistanceRequest[AnalysisScopeDraftInput], actor: ActorContext
    ) -> AssistanceSuggestion[AnalysisScopeDraft]: ...


class AssistanceDecisionService:
    def decide(self, command: DecideAssistanceCommand, actor: ActorContext) -> AssistanceDecision: ...


class RiskAssessmentService:
    def propose(self, command: StartRiskProposalCommand, actor: ActorContext) -> RiskAssessmentRecord: ...
    def get(self, row_id: str, actor: ActorContext) -> RiskAssessmentRecord | None: ...
    def confirm(self, command: ConfirmRiskCommand, actor: ActorContext) -> RiskConfirmationResult: ...
    def reject(self, command: RejectRiskCommand, actor: ActorContext) -> RiskAssessmentRecord: ...
    def invalidate_if_stale(self, row_id: str, dependencies: RiskDependencySnapshot, actor: ActorContext) -> RiskAssessmentRecord | None: ...
```

The analysis generator drafts scope, system boundary, exclusions, modes, assumptions, and limitations only; a human must pass adopted or edited-and-adopted values through the decision service before the existing `FmeaService.create_analysis()` command writes canonical state. `AssistanceDecisionService` supports `adopt`, `partial_adopt`, `edit_and_adopt`, `reject`, `defer`, and `request_evidence`, requires a human actor and exact suggestion/target versions, appends an immutable decision, and invokes only an allowlisted typed handler. The risk generator receives only bounded review context, scoring anchors, and validated evidence. It returns an `AssistanceSuggestion[RiskProposal]` with dimensions and evidence IDs, never derived authority state. Persist each suggestion through the shared assistance repository before saving the linked risk proposal. Reuse the current provider-neutral pipeline and its configured DeepSeek profile: Flash generation, `deepseek-v4-pro` criticism, and at most one bounded repair; do not add provider imports to application code. The service validates every value, calculates derived risk with existing deterministic code, stores `proposed`, and requires a human `risk_reviewer` for confirmation. Extend the opt-in local auth provider to return `reviewer` and `risk_reviewer`; production auth remains fail-closed and interface-driven. Use existing executor/run patterns without sharing mutable run state.

- [ ] **Step 4: Run service, structured-generation, and review regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_analysis_assistance_service.py tests/unit/test_fmea_assistance_service.py tests/unit/test_fmea_risk_service.py tests/unit/test_fmea_risk_generator.py tests/unit/test_fmea_local_auth.py tests/integration/test_fmea_risk_runs.py tests/unit/test_structured_generation_pipeline.py tests/unit/test_fmea_review_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the risk application slice**

```powershell
git add fmea_application/analysis_assistance_service.py fmea_application/assistance_service.py fmea_application/risk_service.py fmea_application/service_factory.py fmea_infrastructure/analysis_assistance_generator.py fmea_infrastructure/risk_generator.py fmea_infrastructure/composition.py fmea_infrastructure/local_auth.py tests/unit/test_fmea_analysis_assistance_service.py tests/unit/test_fmea_assistance_service.py tests/unit/test_fmea_risk_service.py tests/unit/test_fmea_risk_generator.py tests/unit/test_fmea_local_auth.py tests/integration/test_fmea_risk_runs.py
git commit -m "feat(fmea): propose and confirm evidence bound risk"
```

### Task 5: Publish REST and CLI risk contracts

**Files:**
- Create: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_assistance_contracts.py`
- Create: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_assistance_v1.py`
- Create: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_risk_contracts.py`
- Create: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_risk_v1.py`
- Modify: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py`
- Modify: `scripts/fmea_skill.py`
- Test: `tests/unit/test_fmea_assistance_api_contracts.py`
- Test: `tests/unit/test_fmea_risk_api_contracts.py`
- Test: `tests/integration/test_fmea_risk_api_v1.py`
- Test: `tests/integration/test_fmea_risk_cli.py`

**Interfaces:**
- Consumes: `AnalysisAssistanceService`, `RiskAssessmentService`, and current auth/workspace runtime.
- Produces: versioned assistance/risk resources and matching single-JSON CLI commands.

- [ ] **Step 1: Write API/CLI parity tests**

```python
def test_risk_confirm_requires_if_match_idempotency_and_human_actor(client):
    response = client.post("/api/v1/fmea/rows/row-1/risk-confirmations", json=valid_confirmation_body())
    assert response.status_code == 428
    assert response.json()["error"]["code"] == "FMEA_PRECONDITION_REQUIRED"


def test_cli_and_rest_serialize_the_same_confirmed_assessment(client, invoke_cli):
    rest = confirm_via_rest(client)
    cli = invoke_cli("risk", "show", "--row-id", "row-1")
    assert cli["data"] == rest["data"]


def test_scope_assistance_returns_unapplied_suggestion(client):
    response = client.post("/api/v1/fmea/assistance/analysis-scope-runs", json=scope_request_body())
    assert response.status_code == 202
    assert response.json()["data"]["applied"] is False


def test_model_cannot_submit_assistance_decision(client_as_model):
    response = client_as_model.post(
        "/api/v1/fmea/assistance/suggestions/suggestion-1/decisions",
        headers={"If-Match": '"1"', "Idempotency-Key": UUID1},
        json={"action": "adopt", "target_record_version": 3},
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_assistance_api_contracts.py tests/unit/test_fmea_risk_api_contracts.py tests/integration/test_fmea_risk_api_v1.py tests/integration/test_fmea_risk_cli.py -q`

Expected: FAIL because risk transports are absent.

- [ ] **Step 3: Add strict resources and commands**

REST resources:

```text
POST /api/v1/fmea/assistance/analysis-scope-runs
GET  /api/v1/fmea/assistance/suggestions/{suggestion_id}
POST /api/v1/fmea/assistance/suggestions/{suggestion_id}/decisions
GET  /api/v1/fmea/rows/{row_id}/risk
POST /api/v1/fmea/rows/{row_id}/risk-proposal-runs
GET  /api/v1/fmea/risk-proposal-runs/{run_id}
POST /api/v1/fmea/rows/{row_id}/risk-confirmations
POST /api/v1/fmea/rows/{row_id}/risk-rejections
```

CLI commands:

```text
fmea_skill.py assist scope --request-file FILE
fmea_skill.py assist decide --request-file FILE --confirm-human-assistance-decision
fmea_skill.py risk show --row-id ROW
fmea_skill.py risk propose --row-id ROW --record-version N --idempotency-key UUID
fmea_skill.py risk proposal-status --run-id RUN
fmea_skill.py risk confirm --request-file FILE --confirm-human-risk-review
fmea_skill.py risk reject --request-file FILE --confirm-human-risk-review
```

Use strict Pydantic models, 256 KiB body limit, stable safe errors, ETag on reads and writes, canonical UUID idempotency keys, no model/provider override, and one bounded JSON CLI object.

- [ ] **Step 4: Run new and existing route/CLI tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_assistance_api_contracts.py tests/unit/test_fmea_risk_api_contracts.py tests/unit/test_fmea_assistance_service.py tests/integration/test_fmea_risk_api_v1.py tests/integration/test_fmea_risk_cli.py tests/integration/test_fmea_review_api_v1.py tests/integration/test_fmea_review_cli.py -q`

Expected: PASS.

- [ ] **Step 5: Commit transports**

```powershell
git add api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_assistance_contracts.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_assistance_v1.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_risk_contracts.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_risk_v1.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py scripts/fmea_skill.py tests/unit/test_fmea_assistance_api_contracts.py tests/unit/test_fmea_risk_api_contracts.py tests/integration/test_fmea_risk_api_v1.py tests/integration/test_fmea_risk_cli.py
git commit -m "feat(fmea): expose risk review interfaces"
```

### Task 6: Close risk acceptance, security, and handoff gates

**Files:**
- Create: `examples/fmea/risk/fuel-combustion/`
- Create: `scripts/run_fmea_risk_acceptance.py`
- Create: `scripts/verify_fmea_risk_acceptance.py`
- Create: `tests/integration/test_fmea_risk_acceptance.py`
- Create: `tests/regression/test_fmea_risk_security.py`
- Create: `docs/handoff/fmea-risk-closure.md`

**Interfaces:**
- Consumes: all Phase 1 risk resources.
- Produces: `graphrag.fmea.risk.acceptance.v1` canonical artifact pack and independent verifier.

- [ ] **Step 1: Write acceptance and negative-security tests**

```python
def test_acceptance_covers_confirmed_unknown_conflict_and_invalidation(run_acceptance):
    summary = run_acceptance()
    assert summary["schema_version"] == "graphrag.fmea.risk.acceptance.v1"
    assert summary["cases"] == ["analysis_scope", "confirmed", "unknown", "conflict", "invalidated"]
    assert summary["model_confirmation_count"] == 0


@pytest.mark.parametrize(
    "retrieval_mode",
    ["rag_only", "graphrag_local", "graphrag_global", "graphrag_only", "combined", "auto", "custom"],
)
def test_acceptance_consumes_every_supported_evidence_mode_through_one_contract(run_acceptance, retrieval_mode):
    result = run_acceptance(retrieval_mode=retrieval_mode)
    assert result["evidence_pack"]["retrieval_mode"] == retrieval_mode
    assert result["fmea_backend_import_count"] == 0


def test_acceptance_artifacts_contain_no_secret_or_private_path(run_acceptance):
    for payload in run_acceptance().artifact_bytes:
        assert b"Authorization" not in payload
        assert b"DEEPSEEK_API_KEY" not in payload
        assert b"C:\\private" not in payload
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_risk_acceptance.py tests/regression/test_fmea_risk_security.py -q`

Expected: FAIL because acceptance assets are absent.

- [ ] **Step 3: Implement deterministic runner, verifier, and handoff**

The runner writes canonical `analysis-scope-suggestion.json`, `proposal.json`, `confirmation.json`, `invalidation.json`, `audit-summary.json`, and `acceptance-summary.json` under a contained temporary directory, verifies them, then atomically renames the directory. Its mode matrix supplies equivalent immutable packs from `rag_only`, GraphRAG local/global, `graphrag_only`, `combined`, `auto`, and `custom` fixtures without changing FMEA service construction. The verifier independently recomputes hashes, assistance target/version bindings, `applied=false`, rule applicability, RPN, status transitions, actor types, idempotency replay, and private-marker absence. It rejects retrieval-backend imports, missing, extra, duplicate-case, partial, or tampered artifacts.

Document local setup, DomainPack/rule registration, API/CLI examples, optional live DeepSeek command, and the explicit statement that fixture agreement is not industrial certification.

- [ ] **Step 4: Run the complete Phase 1 gate**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_domain_pack.py tests/unit/test_fmea_assistance_contracts.py tests/unit/test_fmea_analysis_assistance_service.py tests/unit/test_fmea_assistance_service.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_evidence.py tests/unit/test_fmea_scoring.py tests/unit/test_fmea_domain_pack_registry.py tests/unit/test_fmea_assistance_repository_contract.py tests/unit/test_fmea_risk_repository_contract.py tests/unit/test_fmea_risk_service.py tests/unit/test_fmea_risk_generator.py tests/unit/test_fmea_assistance_api_contracts.py tests/unit/test_fmea_risk_api_contracts.py tests/integration/test_fmea_fuel_combustion_pack.py tests/integration/test_fmea_assistance_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_risk_runs.py tests/integration/test_fmea_risk_api_v1.py tests/integration/test_fmea_risk_cli.py tests/integration/test_fmea_risk_acceptance.py tests/regression/test_fmea_risk_idempotency.py tests/regression/test_fmea_risk_security.py -q
.venv\Scripts\python.exe scripts/run_fmea_risk_acceptance.py
.venv\Scripts\python.exe scripts/verify_fmea_risk_acceptance.py --latest
.venv\Scripts\python.exe -m compileall -q core_domain fmea_application fmea_infrastructure scripts
.venv\Scripts\ruff.exe check core_domain/fmea fmea_application fmea_infrastructure scripts/fmea_skill.py scripts/run_fmea_risk_acceptance.py scripts/verify_fmea_risk_acceptance.py tests/unit/test_fmea_risk*.py tests/integration/test_fmea_risk*.py tests/regression/test_fmea_risk*.py
git diff --check
```

Expected: every command exits 0. Do not run a paid live model gate unless separately authorized.

- [ ] **Step 5: Commit Phase 1 acceptance**

```powershell
git add examples/fmea/risk/fuel-combustion scripts/run_fmea_risk_acceptance.py scripts/verify_fmea_risk_acceptance.py tests/integration/test_fmea_risk_acceptance.py tests/regression/test_fmea_risk_security.py docs/handoff/fmea-risk-closure.md
git commit -m "test(fmea): close risk workflow acceptance"
```

## Phase 1 completion checklist

- [ ] DomainPack and scoring rules are immutable, hash-bound, and contained.
- [ ] Model output can propose but cannot confirm scores.
- [ ] Unknown/conflicting required dimensions do not produce valid RPN.
- [ ] Human confirmation is versioned, idempotent, audited, and optimistic-lock protected.
- [ ] Dependency changes invalidate confirmed risk without silent re-confirmation.
- [ ] REST and CLI expose the same safe contract.
- [ ] Offline acceptance and independent verification pass without external-model cost.
