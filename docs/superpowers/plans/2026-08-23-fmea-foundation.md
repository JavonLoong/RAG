# FMEA Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independently runnable Phase A/B FMEA domain-and-storage closure with versioned risk rules, immutable EvidencePack snapshots, PropagationEdge objects, a dedicated SQLite repository, and a safe WorkspaceRegistry storage binding.

**Architecture:** Keep the canonical FMEA model in `core_domain/fmea` as frozen, model-free Python value objects and entities. Expose persistence and candidate orchestration through `fmea_application/ports.py`, put the application entry in `FmeaService`, and keep the candidate entry in `FmeaCandidatePipeline` as a deterministic fixture-backed boundary with no LLM call. Persist only to a separate migration-managed SQLite database through `SqliteFmeaRepository`; do not import or initialize `GraphStore`.

**Tech Stack:** Python 3.11+, frozen dataclasses and enums, `sqlite3`, SQL migration files, Pydantic `WorkspaceRegistry`, pytest, uv, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-23-graphrag-fmea-system-design.md`

## Global Constraints

- The interface schema identifier is exactly `graphrag.fmea.v1`; do not create a top-level Python package named `graphrag`.
- FMEA remains an independent domain; do not add `QueryMode.FMEA` and do not put FMEA lifecycle or scoring state into GraphRAG query contracts.
- Shared type names are exactly `ClaimStatus`, `ReviewStatus`, `PublicationStatus`, `ActorType`, `RunStatus`, `VersionSet`, `EvidenceRef`, `EvidencePack`, `EvidenceSupportStatus`, `FmeaAnalysis`, `FmeaRow`, `RiskAssessment`, `PropagationEdge`, and `ScoringRulePack`.
- `ClaimStatus` values are exactly `known`, `unknown`, `insufficient_evidence`, `conflict`, and `not_applicable`.
- `ReviewStatus` values are exactly `draft`, `suggested`, `in_review`, `accepted`, `rejected`, and `superseded`.
- `PublicationStatus` values are exactly `unpublished`, `published`, and `withdrawn`; `published` is never rendered or treated as `certified`.
- `ActorType` values are exactly `human`, `model`, and `system`; only a `human` actor may request accepted, published, or withdrawn state.
- `RunStatus` values are exactly `queued`, `running`, `cancelling`, `cancelled`, `succeeded`, and `failed`, even though Phase 1 stores only the shared enum for later application work.
- `EvidenceSupportStatus` values are exactly `supported`, `partially_supported`, `contradicted`, and `not_supported`.
- A field with no current EvidencePack evidence cannot be `known`; `not_applicable` remains distinct from `unknown`; conflicts are retained rather than silently resolved.
- `VersionSet` carries schema, data, graph, EvidencePack, profile, template, scoring, prompt, model, and input snapshot versions needed for replay.
- `EvidencePack` is immutable, workspace/ACL scoped, content-hash bound, and the only valid source of evidence IDs for Phase 1 FMEA rows and propagation edges.
- `SqliteFmeaRepository` owns its database file and migration table; it enables foreign keys, uses transactions, enforces unique constraints and optimistic locking, and never calls `GraphStore.initialize(reset=True)` or reuses the GraphStore SQLite file.
- Workspace paths are resolved by the existing `WorkspaceRegistry` and remain under `allowed_root`; missing FMEA storage produces a stable configuration error at the composition boundary.
- Phase 1 implements only the domain kernel, deterministic risk rules, EvidencePack, PropagationEdge, application ports/service, deterministic fixture-backed candidate persistence, dedicated SQLite/migrations/repository, and FMEA storage binding. LLM, external model adapters, REST/SSE, CLI, UI, templates, export, authentication, and upstream M1-M4 work are not tasks in this plan.
- GraphRAG integration is read-only and represented only by a later `EvidenceProvider` port/fixture boundary; no task changes `QueryService`, `GraphStore`, retrieval, chunking, OCR, or graph construction.
- Run all commands from `C:\Users\35551\Desktop\RAG\.worktrees\interface-output-v1` with `uv run`; do not rely on system Python.
- Preserve unrelated worktree changes. Every implementation commit stages only paths listed by its task.

## Responsibility Matrix Application

| Plan task | Matrix mark | Executable boundary |
| --- | --- | --- |
| Tasks 1-5 | `OWN` | Implement and test the semantic model, rules, propagation policy, ports, service, and deterministic candidate boundary. |
| Tasks 6-7 | `OWN` | Implement the dedicated SQLite schema, migrations, transaction runner, backup protection, and repository. |
| Task 8 | `INTEGRATE` | Adapt the existing WorkspaceRegistry with one contained FMEA database path and tests; do not refactor the registry or query system. |
| Task 9 | `OWN` | Prove the pure-domain-to-SQLite closure with a local fixture and focused quality gate. |

M1-M4 are dependencies only: they eventually provide stable document/version/hash/locator/ACL facts through an `EvidenceProvider` port; the Phase 1 fixture provider returns those facts or a typed missing-evidence error. Existing GraphRAG query and graph implementations remain untouched. Enterprise OIDC/SSO, DLP/secret infrastructure, generic QMS/workflow/plugin platforms, REST/SSE, UI, exports, and LLM/model work are excluded capabilities, not tasks.

## Repository/File Map

- Create `core_domain/fmea/errors.py` for domain validation and immutable-snapshot errors.
- Create `core_domain/fmea/states.py` for the seven exact state/actor enums and schema constant.
- Create `core_domain/fmea/value_objects.py` for `VersionSet`, `EvidenceRef`, and immutable `EvidencePack` construction/hash validation.
- Create `core_domain/fmea/scoring.py` for `ScoringRulePack`, `RiskAssessment`, and deterministic `calculate_risk`.
- Create `core_domain/fmea/entities.py` for `FmeaAnalysis`, `FmeaRow`, and field-level evidence bindings.
- Create `core_domain/fmea/propagation.py` for `PropagationEdge` and propagation auto-accept policy data.
- Create `core_domain/fmea/policies.py` for evidence, status-transition, actor, and publication preconditions.
- Create `core_domain/fmea/codec.py` for canonical JSON encoding/decoding used by the SQLite repository.
- Create `core_domain/fmea/__init__.py` to export shared names without exposing infrastructure.
- Create `fmea_application/ports.py` for repository, candidate, and read-only evidence interfaces plus stable application errors.
- Create `fmea_application/services.py` for `FmeaService`.
- Create `fmea_application/candidate_pipeline.py` for deterministic `FmeaCandidatePipeline`; it accepts fixture-provided candidate objects and never calls a model.
- Create `fmea_application/__init__.py` for application exports.
- Create `fmea_infrastructure/migrations/001_initial.sql` for the complete FMEA schema and `002_indexes.sql` for indexes/triggers.
- Create `fmea_infrastructure/migration_runner.py` for ordered, transactional migration application and pre-migration backup.
- Create `fmea_infrastructure/repository_sqlite.py` for `SqliteFmeaRepository`.
- Create `fmea_infrastructure/__init__.py` and `fmea_infrastructure/migrations/__init__.py` for package boundaries.
- Modify `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/workspace_registry.py` only to add an optional contained `fmea_db_path` binding to `WorkspaceConfig`.
- Extend `tests/unit/test_workspace_registry.py` only for the FMEA path binding; do not alter query behavior tests.
- Create `tests/unit/test_fmea_states.py`, `tests/unit/test_fmea_entities.py`, `tests/unit/test_fmea_scoring.py`, `tests/unit/test_fmea_propagation.py`, `tests/unit/test_fmea_application.py`, `tests/unit/test_fmea_migrations.py`, `tests/integration/test_fmea_repository_sqlite.py`, and `tests/integration/test_fmea_foundation_closure.py`.
- Create `tests/fmea_fixtures.py` in Task 2 for deterministic local analysis, pack, row, and edge fixtures imported by later tests.
- Create `tests/conftest.py` in Task 2 to register the shared fixture module after the Task 2 domain entities exist.

---

### Task 1: Add FMEA State Axes, VersionSet, and EvidencePack Value Objects

**Responsibility:** `OWN`

**Files:**
- Create: `core_domain/fmea/__init__.py`
- Create: `core_domain/fmea/errors.py`
- Create: `core_domain/fmea/states.py`
- Create: `core_domain/fmea/value_objects.py`
- Test: `tests/unit/test_fmea_states.py`

**Interfaces:**
- Consumes: Python 3.11 `dataclasses`, `enum`, `hashlib`, and `json` only.
- Produces: `FMEA_SCHEMA_ID = "graphrag.fmea.v1"`; exact enums `ClaimStatus`, `ReviewStatus`, `PublicationStatus`, `ActorType`, `RunStatus`, and `EvidenceSupportStatus`; `VersionSet`; `EvidenceRef`; `EvidencePack.build`; `EvidencePack.ref_by_id`.

The exact value-object fields and methods are:

~~~~python
@dataclass(frozen=True, slots=True)
class VersionSet:
    schema_id: str
    data_version: str
    graph_version: str
    evidence_pack_version: str
    profile_version: str
    template_version: str
    scoring_version: str
    prompt_version: str
    model_version: str
    input_snapshot_hash: str


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    workspace_id: str
    document_id: str
    document_version: str
    content_hash: str
    locator: str
    quote: str
    normalized_quote: str
    evidence_hash: str
    acl_scope: tuple[str, ...]
    source_type: str
    source_trust: str
    is_primary: bool
    created_at: str
    expires_at: str | None


@dataclass(frozen=True, slots=True)
class EvidencePack:
    pack_id: str
    workspace_id: str
    acl_scope: tuple[str, ...]
    versions: VersionSet
    refs: tuple[EvidenceRef, ...]
    pack_hash: str
    created_at: str
    expires_at: str | None

    @classmethod
    def build(
        cls,
        *,
        pack_id: str,
        workspace_id: str,
        acl_scope: tuple[str, ...],
        versions: VersionSet,
        refs: tuple[EvidenceRef, ...],
        created_at: str,
        expires_at: str | None,
    ) -> "EvidencePack":
        ids = [ref.evidence_id for ref in refs]
        if len(ids) != len(set(ids)):
            raise FmeaDomainError("duplicate evidence_id")
        payload = json.dumps(
            [
                {"evidence_id": ref.evidence_id, "evidence_hash": ref.evidence_hash, "locator": ref.locator}
                for ref in sorted(refs, key=lambda item: item.evidence_id)
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            pack_id=pack_id,
            workspace_id=workspace_id,
            acl_scope=tuple(acl_scope),
            versions=versions,
            refs=tuple(refs),
            pack_hash=sha256(payload).hexdigest(),
            created_at=created_at,
            expires_at=expires_at,
        )

    def ref_by_id(self, evidence_id: str) -> EvidenceRef | None:
        return next((ref for ref in self.refs if ref.evidence_id == evidence_id), None)
~~~~

Step 3 implements these constructors and lookup with deterministic validation and hashing.

- [ ] **Step 1: Write the failing state and hash tests**

Add `tests/unit/test_fmea_states.py`:

~~~~python
from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    FMEA_SCHEMA_ID,
    PublicationStatus,
    ReviewStatus,
    RunStatus,
)
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet


def _versions() -> VersionSet:
    return VersionSet(
        schema_id=FMEA_SCHEMA_ID,
        data_version="data-2026-08-23",
        graph_version="graph-7",
        evidence_pack_version="evidence-1",
        profile_version="gas-turbine-1",
        template_version="canonical-1",
        scoring_version="risk-1",
        prompt_version="prompt-0",
        model_version="model-0",
        input_snapshot_hash="a" * 64,
    )


def _ref(evidence_id: str = "ev-1") -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence_id,
        workspace_id="ws-1",
        document_id="doc-1",
        document_version="doc-v1",
        content_hash="b" * 64,
        locator="page:4#span:2",
        quote="Fuel pressure falls below the threshold.",
        normalized_quote="fuel pressure falls below the threshold.",
        evidence_hash=sha256(b"Fuel pressure falls below the threshold.").hexdigest(),
        acl_scope=("engineering",),
        source_type="primary_document",
        source_trust="reviewed",
        is_primary=True,
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )


def test_state_axes_and_schema_are_exact() -> None:
    assert FMEA_SCHEMA_ID == "graphrag.fmea.v1"
    assert [item.value for item in ClaimStatus] == [
        "known", "unknown", "insufficient_evidence", "conflict", "not_applicable"
    ]
    assert [item.value for item in ReviewStatus] == [
        "draft", "suggested", "in_review", "accepted", "rejected", "superseded"
    ]
    assert [item.value for item in PublicationStatus] == ["unpublished", "published", "withdrawn"]
    assert [item.value for item in ActorType] == ["human", "model", "system"]
    assert [item.value for item in RunStatus] == [
        "queued", "running", "cancelling", "cancelled", "succeeded", "failed"
    ]
    assert [item.value for item in EvidenceSupportStatus] == [
        "supported", "partially_supported", "contradicted", "not_supported"
    ]


def test_evidence_pack_hash_is_deterministic_and_immutable() -> None:
    first = EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=_versions(),
        refs=(_ref(),),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )
    second = EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=_versions(),
        refs=(_ref(),),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )

    assert first.pack_hash == second.pack_hash
    assert first.ref_by_id("ev-1") == first.refs[0]
    assert first.ref_by_id("missing") is None
    with pytest.raises(FrozenInstanceError):
        first.pack_id = "changed"


def test_evidence_pack_rejects_duplicate_ids_and_bad_schema() -> None:
    with pytest.raises(FmeaDomainError, match="duplicate evidence_id"):
        EvidencePack.build(
            pack_id="pack-1",
            workspace_id="ws-1",
            acl_scope=("engineering",),
            versions=_versions(),
            refs=(_ref("ev-1"), _ref("ev-1")),
            created_at="2026-08-23T00:00:00Z",
            expires_at=None,
        )

    with pytest.raises(FmeaDomainError, match="graphrag.fmea.v1"):
        VersionSet(
            schema_id="graphrag.query.v1",
            data_version="data-1",
            graph_version="graph-1",
            evidence_pack_version="evidence-1",
            profile_version="profile-1",
            template_version="template-1",
            scoring_version="score-1",
            prompt_version="prompt-0",
            model_version="model-0",
            input_snapshot_hash="c" * 64,
        )
~~~~

- [ ] **Step 2: Run the focused test to verify the red state**

Run:

~~~~powershell
uv run pytest tests/unit/test_fmea_states.py -q
~~~~

Expected: collection fails with `ModuleNotFoundError` for `core_domain.fmea` because the package has not been created.

- [ ] **Step 3: Write the minimal state and EvidencePack implementation**

Implement the exact enums and constructors. The hash payload sorts a tuple of dictionaries with `sort_keys=True`, hashes UTF-8 JSON with SHA-256, rejects duplicate IDs, and stores all input sequences as tuples:

~~~~python
from enum import Enum

FMEA_SCHEMA_ID = "graphrag.fmea.v1"


class ClaimStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    SUGGESTED = "suggested"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class PublicationStatus(str, Enum):
    UNPUBLISHED = "unpublished"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class ActorType(str, Enum):
    HUMAN = "human"
    MODEL = "model"
    SYSTEM = "system"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EvidenceSupportStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    NOT_SUPPORTED = "not_supported"
~~~~

`FmeaDomainError` is a `ValueError` subclass with no infrastructure imports. `EvidenceRef` rejects empty identity/hash/quote values and `EvidencePack.build` verifies every ref workspace matches the pack workspace before calculating `pack_hash`.

- [ ] **Step 4: Run the focused tests and lint**

Run:

~~~~powershell
uv run pytest tests/unit/test_fmea_states.py -q
uv run ruff check core_domain/fmea tests/unit/test_fmea_states.py
~~~~

Expected: all tests pass and Ruff exits `0`.

- [ ] **Step 5: Commit the value-object boundary**

~~~~powershell
git add core_domain/fmea/__init__.py core_domain/fmea/errors.py core_domain/fmea/states.py core_domain/fmea/value_objects.py tests/unit/test_fmea_states.py
git commit -m "feat(fmea): add state axes and evidence pack values"
~~~~

---

### Task 2: Add FmeaAnalysis, FmeaRow, Evidence Binding, and Domain Policies

**Responsibility:** `OWN`

**Files:**
- Create: `core_domain/fmea/entities.py`
- Create: `core_domain/fmea/policies.py`
- Create: `core_domain/fmea/codec.py`
- Create: `tests/fmea_fixtures.py`
- Create: `tests/conftest.py`
- Modify: `core_domain/fmea/__init__.py`
- Test: `tests/unit/test_fmea_entities.py`

**Interfaces:**
- Consumes: `VersionSet`, `EvidencePack`, `ClaimStatus`, `ReviewStatus`, `PublicationStatus`, `ActorType`, `EvidenceSupportStatus`, and `FmeaDomainError` from Task 1.
- Produces: frozen `FmeaAnalysis` and `FmeaRow`; `validate_row_evidence(row, pack)`; `validate_review_transition`; `validate_publication_transition`; canonical `encode_json(value)` plus `decode_analysis`, `decode_row`, and `decode_evidence_pack`.

Use these exact entity fields:

~~~~python
@dataclass(frozen=True, slots=True)
class FmeaAnalysis:
    analysis_id: str
    project_id: str
    analysis_type: str
    lifecycle_stage: str
    scope: str
    system_boundary: str
    exclusions: tuple[str, ...]
    equipment_configuration: str
    control_software_version: str
    fuel_type: str
    operating_modes: tuple[str, ...]
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    unanalysed_parts: tuple[str, ...]
    versions: VersionSet
    owner_actor_id: str
    reviewer_actor_ids: tuple[str, ...]
    approver_actor_id: str | None
    approved_at: str | None
    parent_revision_id: str | None
    current_revision_id: str | None
    record_version: int = 1


@dataclass(frozen=True, slots=True)
class FmeaRow:
    row_id: str
    analysis_id: str
    evidence_pack_id: str
    item_id: str
    function_id: str
    failure_mode: str
    causes: tuple[str, ...]
    mechanisms: tuple[str, ...]
    effects: tuple[str, ...]
    symptoms: tuple[str, ...]
    controls: tuple[str, ...]
    barriers: tuple[str, ...]
    actions: tuple[str, ...]
    risk_assessment: RiskAssessment | None
    field_evidence: tuple[tuple[str, tuple[str, ...]], ...]
    field_support: tuple[tuple[str, EvidenceSupportStatus], ...]
    claim_status: ClaimStatus
    review_status: ReviewStatus
    publication_status: PublicationStatus
    record_version: int = 1
~~~~

Create `tests/conftest.py` in the same task:

~~~~python
pytest_plugins = ("fmea_fixtures",)
~~~~

`field_evidence` maps semantic field names to EvidencePack IDs. `field_support` maps the same field name to one `EvidenceSupportStatus`. Policies reject unknown field names, duplicate field names, evidence IDs absent from the supplied pack, `ClaimStatus.KNOWN` without at least one binding, and `ClaimStatus.KNOWN` when any bound field is `contradicted` or `not_supported`.

Create `tests/fmea_fixtures.py` with concrete pytest fixtures so later test code has no hidden data source:

~~~~python
from __future__ import annotations

import pytest

from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.states import (
    ClaimStatus,
    EvidenceSupportStatus,
    FMEA_SCHEMA_ID,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet


@pytest.fixture
def fixture_versions() -> VersionSet:
    return VersionSet(
        schema_id=FMEA_SCHEMA_ID,
        data_version="data-1",
        graph_version="graph-1",
        evidence_pack_version="evidence-1",
        profile_version="profile-1",
        template_version="template-1",
        scoring_version="score-1",
        prompt_version="prompt-0",
        model_version="model-0",
        input_snapshot_hash="d" * 64,
    )


@pytest.fixture
def fixture_pack(fixture_versions: VersionSet) -> EvidencePack:
    ref = EvidenceRef(
        evidence_id="ev-1",
        workspace_id="ws-1",
        document_id="doc-1",
        document_version="doc-v1",
        content_hash="e" * 64,
        locator="page:1#span:1",
        quote="pressure is low",
        normalized_quote="pressure is low",
        evidence_hash="f" * 64,
        acl_scope=("engineering",),
        source_type="primary_document",
        source_trust="reviewed",
        is_primary=True,
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )
    return EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=fixture_versions,
        refs=(ref,),
        created_at="2026-08-23T00:00:00Z",
        expires_at=None,
    )


@pytest.fixture
def fixture_analysis(fixture_versions: VersionSet) -> FmeaAnalysis:
    return FmeaAnalysis(
        analysis_id="analysis-1",
        project_id="project-1",
        analysis_type="fuel_system",
        lifecycle_stage="draft",
        scope="fuel delivery to combustor interface",
        system_boundary="fuel skid to burner manifold",
        exclusions=("plant electrical distribution",),
        equipment_configuration="configuration-1",
        control_software_version="control-1",
        fuel_type="natural_gas",
        operating_modes=("startup", "steady_state"),
        assumptions=("pressure transmitter is calibrated",),
        limitations=("no transient test data",),
        unanalysed_parts=("upstream pipeline",),
        versions=fixture_versions,
        owner_actor_id="analyst-1",
        reviewer_actor_ids=("reviewer-1",),
        approver_actor_id=None,
        approved_at=None,
        parent_revision_id=None,
        current_revision_id="revision-1",
    )


@pytest.fixture
def fixture_row(fixture_pack: EvidencePack) -> FmeaRow:
    return FmeaRow(
        row_id="row-1",
        analysis_id="analysis-1",
        evidence_pack_id=fixture_pack.pack_id,
        item_id="filter-1",
        function_id="fuel-filter-function",
        failure_mode="low fuel pressure",
        causes=("filter blockage",),
        mechanisms=("flow restriction",),
        effects=("flame instability",),
        symptoms=("pressure alarm",),
        controls=("pressure transmitter",),
        barriers=("trip logic",),
        actions=("inspect filter",),
        risk_assessment=None,
        field_evidence=(("failure_mode", ("ev-1",)),),
        field_support=(("failure_mode", EvidenceSupportStatus.SUPPORTED),),
        claim_status=ClaimStatus.KNOWN,
        review_status=ReviewStatus.DRAFT,
        publication_status=PublicationStatus.UNPUBLISHED,
    )


~~~~

- [ ] **Step 1: Write failing entity and policy tests**

Add `tests/unit/test_fmea_entities.py`; its fixture parameters are registered by `tests/conftest.py`. Use the following assertions:

~~~~python
from dataclasses import replace

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.policies import (
    validate_publication_transition,
    validate_review_transition,
    validate_row_evidence,
)
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    PublicationStatus,
    ReviewStatus,
)


def test_known_row_requires_current_pack_evidence(fixture_pack, fixture_row) -> None:
    validate_row_evidence(fixture_row, fixture_pack)
    missing = replace(fixture_row, field_evidence=(), field_support=())
    with pytest.raises(FmeaDomainError, match="known claim requires evidence"):
        validate_row_evidence(missing, fixture_pack)


def test_unknown_and_not_applicable_remain_distinct_without_evidence(fixture_pack, fixture_row) -> None:
    for status in (ClaimStatus.UNKNOWN, ClaimStatus.INSUFFICIENT_EVIDENCE, ClaimStatus.NOT_APPLICABLE):
        row = replace(fixture_row, claim_status=status, field_evidence=(), field_support=())
        validate_row_evidence(row, fixture_pack)
    assert ClaimStatus.NOT_APPLICABLE is not ClaimStatus.UNKNOWN


def test_model_cannot_accept_or_publish() -> None:
    with pytest.raises(FmeaDomainError, match="human actor"):
        validate_review_transition(
            current=ReviewStatus.IN_REVIEW,
            requested=ReviewStatus.ACCEPTED,
            actor_type=ActorType.MODEL,
        )
    with pytest.raises(FmeaDomainError, match="human actor"):
        validate_publication_transition(
            current=PublicationStatus.UNPUBLISHED,
            requested=PublicationStatus.PUBLISHED,
            actor_type=ActorType.MODEL,
        )


def test_invalid_evidence_id_is_rejected(fixture_pack, fixture_row) -> None:
    row = replace(fixture_row, field_evidence=(("failure_mode", ("missing-id",)),))
    with pytest.raises(FmeaDomainError, match="EvidencePack"):
        validate_row_evidence(row, fixture_pack)
~~~~

- [ ] **Step 2: Run the test to verify the red state**

~~~~powershell
uv run pytest tests/unit/test_fmea_entities.py -q
~~~~

Expected: collection fails because `entities.py` and `policies.py` do not yet exist.

- [ ] **Step 3: Write the minimal entities, policies, and codec**

Use an explicit review transition table and actor guard:

~~~~python
_REVIEW_EDGES = {
    ReviewStatus.DRAFT: {ReviewStatus.SUGGESTED, ReviewStatus.IN_REVIEW, ReviewStatus.REJECTED},
    ReviewStatus.SUGGESTED: {ReviewStatus.IN_REVIEW, ReviewStatus.ACCEPTED, ReviewStatus.REJECTED},
    ReviewStatus.IN_REVIEW: {ReviewStatus.ACCEPTED, ReviewStatus.REJECTED},
    ReviewStatus.ACCEPTED: {ReviewStatus.SUPERSEDED},
    ReviewStatus.REJECTED: {ReviewStatus.DRAFT, ReviewStatus.SUPERSEDED},
    ReviewStatus.SUPERSEDED: set(),
}


def validate_review_transition(*, current, requested, actor_type) -> None:
    if requested not in _REVIEW_EDGES[current]:
        raise FmeaDomainError(f"invalid review transition: {current.value}->{requested.value}")
    if requested is ReviewStatus.ACCEPTED and actor_type is not ActorType.HUMAN:
        raise FmeaDomainError("accepted requires a human actor")


def validate_publication_transition(*, current, requested, actor_type) -> None:
    allowed = {
        PublicationStatus.UNPUBLISHED: {PublicationStatus.PUBLISHED},
        PublicationStatus.PUBLISHED: {PublicationStatus.WITHDRAWN},
        PublicationStatus.WITHDRAWN: set(),
    }
    if requested not in allowed[current]:
        raise FmeaDomainError(f"invalid publication transition: {current.value}->{requested.value}")
    if requested in {PublicationStatus.PUBLISHED, PublicationStatus.WITHDRAWN} and actor_type is not ActorType.HUMAN:
        raise FmeaDomainError("publication change requires a human actor")
~~~~

`validate_row_evidence` checks `row.evidence_pack_id`, the fixed field set `failure_mode, causes, mechanisms, effects, symptoms, controls, barriers, actions`, every EvidencePack ID, and the claim/support rules. The codec emits sorted UTF-8 JSON with no NaN values, converts enums to `.value`, tuples to arrays, and reconstructs nested `VersionSet`, `RiskAssessment`, and EvidencePack objects explicitly. It exposes these complete signatures:

~~~~python
def encode_json(value: object) -> str:
    return json.dumps(_encode(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode_analysis(payload: str) -> FmeaAnalysis:
    return _decode_analysis_payload(json.loads(payload))


def decode_row(payload: str) -> FmeaRow:
    return _decode_row_payload(json.loads(payload))


def decode_evidence_pack(payload: str) -> EvidencePack:
    return _decode_evidence_pack_payload(json.loads(payload))
~~~~

Step 3 implements these codec functions with explicit typed reconstruction; no generic pickle or arbitrary import mechanism is allowed.

- [ ] **Step 4: Run entity tests, codec round-trip tests, and lint**

~~~~powershell
uv run pytest tests/unit/test_fmea_entities.py -q
uv run ruff check core_domain/fmea tests/unit/test_fmea_entities.py
~~~~

Expected: all entity/policy tests pass and Ruff exits `0`.

- [ ] **Step 5: Commit the semantic entities and policy gate**

~~~~powershell
git add core_domain/fmea/entities.py core_domain/fmea/policies.py core_domain/fmea/codec.py core_domain/fmea/__init__.py tests/unit/test_fmea_entities.py
git commit -m "feat(fmea): add analysis rows and evidence policies"
~~~~

---

### Task 3: Add Versioned ScoringRulePack and RiskAssessment

**Responsibility:** `OWN`

**Files:**
- Create: `core_domain/fmea/scoring.py`
- Modify: `core_domain/fmea/entities.py`
- Modify: `core_domain/fmea/codec.py`
- Modify: `core_domain/fmea/__init__.py`
- Test: `tests/unit/test_fmea_scoring.py`

**Interfaces:**
- Consumes: `FmeaDomainError`, `EvidenceSupportStatus`, and `VersionSet` from Tasks 1–2.
- Produces: `ScoringRulePack`, `RiskAssessment`, `calculate_risk`, and fixed RPN/policy behavior used by `FmeaRow`.

Use these exact fields and signature:

~~~~python
@dataclass(frozen=True, slots=True)
class ScoringRulePack:
    rule_pack_id: str
    version: str
    applicable_analysis_types: tuple[str, ...]
    severity_anchors: tuple[tuple[int, str], ...]
    occurrence_window: str
    occurrence_denominator: str
    detection_positions: tuple[str, ...]
    score_min: int
    score_max: int
    rpn_formula_version: str
    risk_matrix_version: str
    decision_priority_version: str
    high_priority_rpn: int


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    severity_by_consequence_class: tuple[tuple[str, int | None], ...]
    decision_severity: int | None
    occurrence: int | None
    detection: int | None
    rpn: int | None
    decision_priority: str
    inherent_risk: int | None
    current_risk: int | None
    target_residual_risk: int | None
    verified_residual_risk: int | None
    uncertainty: str | None
    reason: str
    scoring_rule_pack_id: str
    scoring_rule_pack_version: str
    evidence_ids: tuple[str, ...]


def calculate_risk(
    *,
    rule_pack: ScoringRulePack,
    severity_by_consequence_class: tuple[tuple[str, int | None], ...],
    occurrence: int | None,
    detection: int | None,
    inherent_risk: int | None,
    current_risk: int | None,
    target_residual_risk: int | None,
    verified_residual_risk: int | None,
    uncertainty: str | None,
    reason: str,
    evidence_ids: tuple[str, ...],
) -> RiskAssessment:
    scores = [score for _, score in severity_by_consequence_class if score is not None]
    decision_severity = max(scores) if scores else None
    for score in [*scores, occurrence, detection]:
        if score is not None and not rule_pack.score_min <= score <= rule_pack.score_max:
            raise FmeaDomainError(
                f"score must be between {rule_pack.score_min} and {rule_pack.score_max}"
            )
    rpn = (
        decision_severity * occurrence * detection
        if decision_severity is not None and occurrence is not None and detection is not None
        else None
    )
    priority = "critical" if decision_severity is not None and decision_severity >= 9 else "normal"
    if priority == "normal" and rpn is not None and rpn >= rule_pack.high_priority_rpn:
        priority = "high"
    elif priority == "normal" and rpn is not None and rpn >= rule_pack.high_priority_rpn // 2:
        priority = "medium"
    return RiskAssessment(
        severity_by_consequence_class=tuple(severity_by_consequence_class),
        decision_severity=decision_severity,
        occurrence=occurrence,
        detection=detection,
        rpn=rpn,
        decision_priority=priority,
        inherent_risk=inherent_risk,
        current_risk=current_risk,
        target_residual_risk=target_residual_risk,
        verified_residual_risk=verified_residual_risk if target_residual_risk is not None and evidence_ids else None,
        uncertainty=uncertainty,
        reason=reason,
        scoring_rule_pack_id=rule_pack.rule_pack_id,
        scoring_rule_pack_version=rule_pack.version,
        evidence_ids=tuple(evidence_ids),
    )
~~~~

Rules are deterministic: `decision_severity` is the maximum non-null consequence score; `rpn` is `decision_severity * occurrence * detection` only when all three values are in the inclusive rule-pack range; `decision_priority` is `critical` when severity is at least 9, `high` when RPN is at least `high_priority_rpn`, `medium` when RPN is at least half that threshold, and `normal` otherwise. Missing scores produce `rpn=None`, never zero. A verified residual risk requires non-empty evidence IDs and an integer target residual risk.

- [ ] **Step 1: Write failing risk-rule tests**

Add `tests/unit/test_fmea_scoring.py`:

~~~~python
from __future__ import annotations

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.scoring import RiskAssessment, ScoringRulePack, calculate_risk


def rules() -> ScoringRulePack:
    return ScoringRulePack(
        rule_pack_id="gas-turbine-risk",
        version="1.0.0",
        applicable_analysis_types=("fuel_system", "combustion_system"),
        severity_anchors=((1, "negligible"), (5, "moderate"), (9, "severe")),
        occurrence_window="operating_hours",
        occurrence_denominator="1000_hours",
        detection_positions=("sensor", "logic", "operator"),
        score_min=1,
        score_max=10,
        rpn_formula_version="S*O*D-1",
        risk_matrix_version="matrix-1",
        decision_priority_version="priority-1",
        high_priority_rpn=200,
    )


def test_rpn_and_priority_are_deterministic() -> None:
    result = calculate_risk(
        rule_pack=rules(),
        severity_by_consequence_class=(("safety", 5), ("asset", 7)),
        occurrence=10,
        detection=2,
        inherent_risk=140,
        current_risk=40,
        target_residual_risk=12,
        verified_residual_risk=12,
        uncertainty=None,
        reason="reviewed operating data",
        evidence_ids=("ev-1",),
    )
    assert isinstance(result, RiskAssessment)
    assert result.decision_severity == 7
    assert result.rpn == 140
    assert result.decision_priority == "medium"
    assert result.verified_residual_risk == 12


def test_missing_score_does_not_become_zero_or_rpn() -> None:
    result = calculate_risk(
        rule_pack=rules(),
        severity_by_consequence_class=(("safety", 9),),
        occurrence=None,
        detection=2,
        inherent_risk=None,
        current_risk=None,
        target_residual_risk=8,
        verified_residual_risk=8,
        uncertainty="occurrence evidence missing",
        reason="no observation window",
        evidence_ids=(),
    )
    assert result.rpn is None
    assert result.decision_priority == "critical"
    assert result.verified_residual_risk is None


def test_scores_outside_rule_pack_range_fail() -> None:
    with pytest.raises(FmeaDomainError, match="score must be between 1 and 10"):
        calculate_risk(
            rule_pack=rules(),
            severity_by_consequence_class=(("safety", 0),),
            occurrence=1,
            detection=1,
            inherent_risk=1,
            current_risk=1,
            target_residual_risk=1,
            verified_residual_risk=None,
            uncertainty=None,
            reason="invalid score",
            evidence_ids=(),
        )
~~~~

- [ ] **Step 2: Run the risk test to verify the red state**

~~~~powershell
uv run pytest tests/unit/test_fmea_scoring.py -q
~~~~

Expected: collection fails because `core_domain.fmea.scoring` is not present.

- [ ] **Step 3: Write the minimal deterministic scorer**

Implement range checking for every non-null score, reject duplicate consequence classes, compute maximum severity, and set `verified_residual_risk` only when both target residual risk and evidence IDs are present. The calculation body is:

~~~~python
scores = [score for _, score in severity_by_consequence_class if score is not None]
decision_severity = max(scores) if scores else None

for score in [*scores, occurrence, detection]:
    if score is not None and not rule_pack.score_min <= score <= rule_pack.score_max:
        raise FmeaDomainError(
            f"score must be between {rule_pack.score_min} and {rule_pack.score_max}"
        )

rpn = None
if decision_severity is not None and occurrence is not None and detection is not None:
    rpn = decision_severity * occurrence * detection

if decision_severity is not None and decision_severity >= 9:
    decision_priority = "critical"
elif rpn is not None and rpn >= rule_pack.high_priority_rpn:
    decision_priority = "high"
elif rpn is not None and rpn >= rule_pack.high_priority_rpn // 2:
    decision_priority = "medium"
else:
    decision_priority = "normal"

verified = verified_residual_risk if target_residual_risk is not None and evidence_ids else None
~~~~

Add `RiskAssessment` to `FmeaRow.risk_assessment` and add nested encode/decode cases to `codec.py`; no field name or enum value changes.

- [ ] **Step 4: Run risk tests and lint**

~~~~powershell
uv run pytest tests/unit/test_fmea_scoring.py tests/unit/test_fmea_entities.py -q
uv run ruff check core_domain/fmea tests/unit/test_fmea_scoring.py
~~~~

Expected: all selected tests pass and Ruff exits `0`.

- [ ] **Step 5: Commit the scoring package**

~~~~powershell
git add core_domain/fmea/scoring.py core_domain/fmea/entities.py core_domain/fmea/codec.py core_domain/fmea/__init__.py tests/unit/test_fmea_scoring.py
git commit -m "feat(fmea): add versioned risk scoring rules"
~~~~

---

### Task 4: Add PropagationEdge and Two-Hop Review Policy

**Responsibility:** `OWN`

**Files:**
- Create: `core_domain/fmea/propagation.py`
- Modify: `tests/fmea_fixtures.py`
- Modify: `core_domain/fmea/policies.py`
- Modify: `core_domain/fmea/codec.py`
- Modify: `core_domain/fmea/__init__.py`
- Test: `tests/unit/test_fmea_propagation.py`

**Interfaces:**
- Consumes: EvidencePack IDs, `ClaimStatus`, `ReviewStatus`, `PublicationStatus`, `EvidenceSupportStatus`, and `FmeaDomainError`.
- Produces: frozen `PropagationEdge`; `PropagationRelation` with values `propagation`, `common_cause`, `dependency`, `feedback`; `PropagationEdge.auto_accept_allowed`; `validate_propagation_edge(edge, pack)`.

Use this exact edge model:

~~~~python
@dataclass(frozen=True, slots=True)
class PropagationEdge:
    edge_id: str
    analysis_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    interface_variable: str
    unit: str
    direction: str
    threshold: str | None
    operating_modes: tuple[str, ...]
    delay_ms: int | None
    response_time_ms: int | None
    fault_tolerance_time_ms: int | None
    barrier_ids: tuple[str, ...]
    evidence_pack_id: str
    evidence_ids: tuple[str, ...]
    evidence_support: EvidenceSupportStatus
    claim_status: ClaimStatus
    review_status: ReviewStatus
    publication_status: PublicationStatus
    path_length: int
    is_cyclic: bool
    is_unprocessed: bool
    is_external: bool
    is_terminal: bool
    risk_priority: str | None
    record_version: int = 1

    @property
    def inferred(self) -> bool:
        return self.path_length > 2

    @property
    def auto_accept_allowed(self) -> bool:
        return (
            self.path_length <= 2
            and not self.is_cyclic
            and not self.is_unprocessed
            and not self.is_external
            and bool(self.evidence_ids)
            and self.evidence_support in {
                EvidenceSupportStatus.SUPPORTED,
                EvidenceSupportStatus.PARTIALLY_SUPPORTED,
            }
            and self.claim_status is not ClaimStatus.CONFLICT
            and self.risk_priority not in {"high", "critical"}
        )
~~~~

`inferred` is true for `path_length > 2`. `auto_accept_allowed` is true only when path length is at most two, the edge is not cyclic, unprocessed, or external, it has current evidence, support is supported or partially supported, claim status is not conflict, and risk priority is neither high nor critical. A longer path is retained and marked in review.

- [ ] **Step 1: Write failing propagation tests**

Add `tests/unit/test_fmea_propagation.py`:

~~~~python
from __future__ import annotations

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.propagation import PropagationEdge, validate_propagation_edge
from core_domain.fmea.states import (
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
)


def edge(**changes: object) -> PropagationEdge:
    values: dict[str, object] = {
        "edge_id": "edge-1",
        "analysis_id": "analysis-1",
        "source_entity_id": "fuel-filter",
        "target_entity_id": "combustor",
        "relation_type": "propagation",
        "interface_variable": "fuel_pressure",
        "unit": "kPa",
        "direction": "fuel_to_combustion",
        "threshold": "<250",
        "operating_modes": ("startup",),
        "delay_ms": 100,
        "response_time_ms": 200,
        "fault_tolerance_time_ms": 500,
        "barrier_ids": ("trip-1",),
        "evidence_pack_id": "pack-1",
        "evidence_ids": ("ev-1",),
        "evidence_support": EvidenceSupportStatus.SUPPORTED,
        "claim_status": ClaimStatus.KNOWN,
        "review_status": ReviewStatus.SUGGESTED,
        "publication_status": PublicationStatus.UNPUBLISHED,
        "path_length": 2,
        "is_cyclic": False,
        "is_unprocessed": False,
        "is_external": False,
        "is_terminal": False,
        "risk_priority": "normal",
    }
    values.update(changes)
    return PropagationEdge(**values)


def test_two_hop_supported_edge_can_be_auto_accepted() -> None:
    current = edge()
    assert current.inferred is False
    assert current.auto_accept_allowed is True


@pytest.mark.parametrize(
    "changes",
    [
        {"path_length": 3},
        {"is_cyclic": True},
        {"is_unprocessed": True},
        {"risk_priority": "high"},
        {"evidence_ids": ()},
        {"claim_status": ClaimStatus.CONFLICT},
    ],
)
def test_high_risk_or_uncertain_edge_requires_human_review(changes: dict[str, object]) -> None:
    current = edge(**changes)
    assert current.auto_accept_allowed is False
    if current.path_length > 2:
        assert current.inferred is True


def test_edge_rejects_unknown_relation_type() -> None:
    with pytest.raises(FmeaDomainError, match="relation_type"):
        validate_propagation_edge(edge(relation_type="invented"), None)
~~~~

- [ ] **Step 2: Run the propagation test to verify the red state**

~~~~powershell
uv run pytest tests/unit/test_fmea_propagation.py -q
~~~~

Expected: collection fails because `propagation.py` is not present.

- [ ] **Step 3: Write the minimal edge implementation and validation**

Use the four relation strings as a closed set. `validate_propagation_edge` accepts `EvidencePack | None`; with a pack it verifies the pack ID and every edge evidence ID. The properties are:

~~~~python
@property
def inferred(self) -> bool:
    return self.path_length > 2


@property
def auto_accept_allowed(self) -> bool:
    return (
        self.path_length <= 2
        and not self.is_cyclic
        and not self.is_unprocessed
        and not self.is_external
        and bool(self.evidence_ids)
        and self.evidence_support in {
            EvidenceSupportStatus.SUPPORTED,
            EvidenceSupportStatus.PARTIALLY_SUPPORTED,
        }
        and self.claim_status is not ClaimStatus.CONFLICT
        and self.risk_priority not in {"high", "critical"}
    )
~~~~

If `path_length > 2`, validation keeps the object and changes no source facts; the candidate pipeline records it with `ReviewStatus.IN_REVIEW` before persistence.

After `PropagationEdge` exists, append this fixture to `tests/fmea_fixtures.py`:

~~~~python
from core_domain.fmea.propagation import PropagationEdge


@pytest.fixture
def fixture_edge(fixture_pack: EvidencePack) -> PropagationEdge:
    return PropagationEdge(
        edge_id="edge-1",
        analysis_id="analysis-1",
        source_entity_id="filter-1",
        target_entity_id="combustor-1",
        relation_type="propagation",
        interface_variable="fuel_pressure",
        unit="kPa",
        direction="fuel_to_combustion",
        threshold="<250",
        operating_modes=("startup",),
        delay_ms=100,
        response_time_ms=200,
        fault_tolerance_time_ms=500,
        barrier_ids=("trip-1",),
        evidence_pack_id=fixture_pack.pack_id,
        evidence_ids=("ev-1",),
        evidence_support=EvidenceSupportStatus.SUPPORTED,
        claim_status=ClaimStatus.KNOWN,
        review_status=ReviewStatus.DRAFT,
        publication_status=PublicationStatus.UNPUBLISHED,
        path_length=2,
        is_cyclic=False,
        is_unprocessed=False,
        is_external=False,
        is_terminal=False,
        risk_priority="normal",
    )
~~~~

- [ ] **Step 4: Run propagation tests and lint**

~~~~powershell
uv run pytest tests/unit/test_fmea_propagation.py tests/unit/test_fmea_entities.py -q
uv run ruff check core_domain/fmea tests/unit/test_fmea_propagation.py
~~~~

Expected: all selected tests pass and Ruff exits `0`.

- [ ] **Step 5: Commit the propagation object**

~~~~powershell
git add core_domain/fmea/propagation.py core_domain/fmea/policies.py core_domain/fmea/codec.py core_domain/fmea/__init__.py tests/unit/test_fmea_propagation.py
git commit -m "feat(fmea): add propagation edge review policy"
~~~~

---

### Task 5: Add Application Ports, FmeaService, and Deterministic FmeaCandidatePipeline

**Responsibility:** `OWN`; this task does not call an LLM and does not implement an external provider.

**Files:**
- Create: `fmea_application/__init__.py`
- Create: `fmea_application/ports.py`
- Create: `fmea_application/services.py`
- Create: `fmea_application/candidate_pipeline.py`
- Test: `tests/unit/test_fmea_application.py`

**Interfaces:**
- Consumes: all shared domain types from Tasks 1–4.
- Produces: the application boundary named `FmeaService`, candidate boundary named `FmeaCandidatePipeline`, and repository port in `fmea_application/ports.py`.

Put every port in `fmea_application/ports.py`. Define `FmeaRepository(Protocol)` with these exact methods:

- `initialize(self) -> None`
- `save_analysis(self, analysis: FmeaAnalysis, *, actor_id: str, actor_type: ActorType, expected_record_version: int | None = None) -> FmeaAnalysis`
- `get_analysis(self, analysis_id: str) -> FmeaAnalysis | None`
- `save_evidence_pack(self, pack: EvidencePack, *, actor_id: str, actor_type: ActorType) -> EvidencePack`
- `get_evidence_pack(self, pack_id: str) -> EvidencePack | None`
- `save_row(self, row: FmeaRow, *, actor_id: str, actor_type: ActorType, expected_record_version: int | None = None) -> FmeaRow`
- `get_row(self, row_id: str) -> FmeaRow | None`
- `save_propagation_edge(self, edge: PropagationEdge, *, actor_id: str, actor_type: ActorType, expected_record_version: int | None = None) -> PropagationEdge`
- `get_propagation_edge(self, edge_id: str) -> PropagationEdge | None`
- `append_audit_event(self, *, actor_id: str, actor_type: ActorType, command: str, aggregate_type: str, aggregate_id: str, before_hash: str | None, after_hash: str | None, reason: str, versions: VersionSet) -> str`

Define `EvidenceProvider.load_pack(workspace_id, pack_id) -> EvidencePack` as read-only for the next phase; this plan uses only local fixture data. Define `FmeaCandidatePipeline.persist_candidates(analysis, evidence_pack, rows, edges, actor_id, actor_type)` to return `tuple[tuple[FmeaRow, ...], tuple[PropagationEdge, ...]]`. It validates current-pack IDs and analysis IDs, changes row candidates to `suggested`, changes longer-path edge candidates to `in_review`, and forces all candidate publication states to `unpublished`.

`FmeaService` exposes `create_analysis`, `register_evidence_pack`, `save_row`, `save_propagation_edge`, and `generate_candidates` with the same parameter names and return types as the repository methods. The service delegates persistence and does not know SQLite.

- [ ] **Step 1: Write failing port and service tests with an in-memory fake**

Add `tests/unit/test_fmea_application.py` with a local fake implementing all port methods and these assertions:

~~~~python
from dataclasses import replace

import pytest

from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.states import ActorType, PublicationStatus, ReviewStatus
from fmea_application.services import FmeaService


class MemoryRepository:
    def __init__(self) -> None:
        self.analyses = {}
        self.packs = {}
        self.rows = {}
        self.edges = {}

    def initialize(self) -> None:
        return None

    def save_analysis(self, analysis, *, actor_id, actor_type, expected_record_version=None):
        self.analyses[analysis.analysis_id] = analysis
        return analysis

    def get_analysis(self, analysis_id):
        return self.analyses.get(analysis_id)

    def save_evidence_pack(self, pack, *, actor_id, actor_type):
        self.packs[pack.pack_id] = pack
        return pack

    def get_evidence_pack(self, pack_id):
        return self.packs.get(pack_id)

    def save_row(self, row, *, actor_id, actor_type, expected_record_version=None):
        self.rows[row.row_id] = row
        return row

    def get_row(self, row_id):
        return self.rows.get(row_id)

    def save_propagation_edge(self, edge, *, actor_id, actor_type, expected_record_version=None):
        self.edges[edge.edge_id] = edge
        return edge

    def get_propagation_edge(self, edge_id):
        return self.edges.get(edge_id)

    def append_audit_event(self, **event):
        return "audit-1"


def test_candidate_pipeline_marks_rows_suggested_and_unpublished(
    fixture_analysis, fixture_pack, fixture_row, fixture_edge
) -> None:
    repository = MemoryRepository()
    service = FmeaService(repository)

    result_rows, result_edges = service.generate_candidates(
        analysis=fixture_analysis,
        evidence_pack=fixture_pack,
        rows=(
            replace(
                fixture_row,
                review_status=ReviewStatus.DRAFT,
                publication_status=PublicationStatus.PUBLISHED,
            ),
        ),
        edges=(fixture_edge,),
        actor_id="system-runner",
        actor_type=ActorType.SYSTEM,
    )

    assert result_rows[0].review_status is ReviewStatus.SUGGESTED
    assert result_rows[0].publication_status is PublicationStatus.UNPUBLISHED
    assert result_edges[0].publication_status is PublicationStatus.UNPUBLISHED
    assert repository.rows[result_rows[0].row_id] == result_rows[0]


def test_candidate_pipeline_rejects_wrong_analysis_id(
    fixture_analysis, fixture_pack, fixture_row, fixture_edge
) -> None:
    service = FmeaService(MemoryRepository())
    wrong_row = replace(fixture_row, analysis_id="other-analysis")
    with pytest.raises(FmeaDomainError, match="analysis_id"):
        service.generate_candidates(
            analysis=fixture_analysis,
            evidence_pack=fixture_pack,
            rows=(wrong_row,),
            edges=(fixture_edge,),
            actor_id="system-runner",
            actor_type=ActorType.SYSTEM,
        )
~~~~

The test file must define `MemoryRepository`; concrete local fixtures come from `tests/fmea_fixtures.py` through `tests/conftest.py`, and no test reads external documents or an existing database.

- [ ] **Step 2: Run the service test to verify the red state**

~~~~powershell
uv run pytest tests/unit/test_fmea_application.py -q
~~~~

Expected: collection fails because `fmea_application` does not exist.

- [ ] **Step 3: Write ports, pipeline, and FmeaService**

The pipeline calls `validate_row_evidence` and `validate_propagation_edge` before repository writes, saves the EvidencePack first, and uses `dataclasses.replace` for state changes:

~~~~python
saved_rows: list[FmeaRow] = []
saved_edges: list[PropagationEdge] = []

repository.save_evidence_pack(
    evidence_pack,
    actor_id=actor_id,
    actor_type=actor_type,
)

for row in rows:
    if row.analysis_id != analysis.analysis_id:
        raise FmeaDomainError("row analysis_id does not match analysis")
    validate_row_evidence(row, evidence_pack)
    candidate = replace(
        row,
        review_status=ReviewStatus.SUGGESTED,
        publication_status=PublicationStatus.UNPUBLISHED,
    )
    saved_rows.append(
        repository.save_row(candidate, actor_id=actor_id, actor_type=actor_type)
    )

for edge in edges:
    if edge.analysis_id != analysis.analysis_id:
        raise FmeaDomainError("edge analysis_id does not match analysis")
    validate_propagation_edge(edge, evidence_pack)
    candidate = replace(
        edge,
        review_status=ReviewStatus.IN_REVIEW if edge.inferred else ReviewStatus.SUGGESTED,
        publication_status=PublicationStatus.UNPUBLISHED,
    )
    saved_edges.append(
        repository.save_propagation_edge(candidate, actor_id=actor_id, actor_type=actor_type)
    )
~~~~

- [ ] **Step 4: Run application tests and lint**

~~~~powershell
uv run pytest tests/unit/test_fmea_application.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_propagation.py -q
uv run ruff check fmea_application tests/unit/test_fmea_application.py
~~~~

Expected: all selected tests pass and Ruff exits `0`.

- [ ] **Step 5: Commit the application boundary**

~~~~powershell
git add fmea_application/__init__.py fmea_application/ports.py fmea_application/services.py fmea_application/candidate_pipeline.py tests/unit/test_fmea_application.py
git commit -m "feat(fmea): add application ports and candidate service"
~~~~

---

### Task 6: Add Dedicated SQLite Schema and Transactional Migrations

**Responsibility:** `OWN`

**Files:**
- Create: `fmea_infrastructure/__init__.py`
- Create: `fmea_infrastructure/migrations/__init__.py`
- Create: `fmea_infrastructure/migrations/001_initial.sql`
- Create: `fmea_infrastructure/migrations/002_indexes.sql`
- Create: `fmea_infrastructure/migration_runner.py`
- Test: `tests/unit/test_fmea_migrations.py`

**Interfaces:**
- Consumes: domain identity/status names and JSON codec from Tasks 1–5.
- Produces: `FmeaMigrationError`, `apply_migrations(connection, migrations_dir) -> tuple[int, ...]`, the schema tables below, and rollback/backup behavior for `SqliteFmeaRepository`.

`001_initial.sql` must contain the following isolated schema:

~~~~sql
CREATE TABLE IF NOT EXISTS fmea_schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fmea_analyses (
    analysis_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    analysis_type TEXT NOT NULL CHECK (analysis_type IN ('fuel_system', 'combustion_system')),
    schema_id TEXT NOT NULL CHECK (schema_id = 'graphrag.fmea.v1'),
    versions_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    record_version INTEGER NOT NULL CHECK (record_version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fmea_evidence_packs (
    pack_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    schema_id TEXT NOT NULL CHECK (schema_id = 'graphrag.fmea.v1'),
    pack_hash TEXT NOT NULL UNIQUE,
    versions_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    immutable INTEGER NOT NULL DEFAULT 1 CHECK (immutable = 1)
);

CREATE TABLE IF NOT EXISTS fmea_evidence_refs (
    pack_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    locator TEXT NOT NULL,
    quote TEXT NOT NULL,
    normalized_quote TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    acl_scope_json TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_trust TEXT NOT NULL,
    is_primary INTEGER NOT NULL CHECK (is_primary IN (0, 1)),
    created_at TEXT NOT NULL,
    expires_at TEXT,
    PRIMARY KEY (pack_id, evidence_id),
    UNIQUE (pack_id, evidence_hash),
    FOREIGN KEY (pack_id) REFERENCES fmea_evidence_packs(pack_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fmea_rows (
    row_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    evidence_pack_id TEXT NOT NULL,
    claim_status TEXT NOT NULL CHECK (claim_status IN ('known', 'unknown', 'insufficient_evidence', 'conflict', 'not_applicable')),
    review_status TEXT NOT NULL CHECK (review_status IN ('draft', 'suggested', 'in_review', 'accepted', 'rejected', 'superseded')),
    publication_status TEXT NOT NULL CHECK (publication_status IN ('unpublished', 'published', 'withdrawn')),
    payload_json TEXT NOT NULL,
    record_version INTEGER NOT NULL CHECK (record_version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (analysis_id, row_id),
    FOREIGN KEY (analysis_id) REFERENCES fmea_analyses(analysis_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_pack_id) REFERENCES fmea_evidence_packs(pack_id)
);

CREATE TABLE IF NOT EXISTS fmea_row_evidence (
    row_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    evidence_pack_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    support_status TEXT NOT NULL CHECK (support_status IN ('supported', 'partially_supported', 'contradicted', 'not_supported')),
    PRIMARY KEY (row_id, field_name, evidence_id),
    FOREIGN KEY (row_id) REFERENCES fmea_rows(row_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_pack_id, evidence_id) REFERENCES fmea_evidence_refs(pack_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS fmea_propagation_edges (
    edge_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL,
    evidence_pack_id TEXT NOT NULL,
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    relation_type TEXT NOT NULL CHECK (relation_type IN ('propagation', 'common_cause', 'dependency', 'feedback')),
    path_length INTEGER NOT NULL CHECK (path_length >= 1),
    claim_status TEXT NOT NULL CHECK (claim_status IN ('known', 'unknown', 'insufficient_evidence', 'conflict', 'not_applicable')),
    review_status TEXT NOT NULL CHECK (review_status IN ('draft', 'suggested', 'in_review', 'accepted', 'rejected', 'superseded')),
    publication_status TEXT NOT NULL CHECK (publication_status IN ('unpublished', 'published', 'withdrawn')),
    payload_json TEXT NOT NULL,
    record_version INTEGER NOT NULL CHECK (record_version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (analysis_id, source_entity_id, target_entity_id, relation_type, path_length),
    FOREIGN KEY (analysis_id) REFERENCES fmea_analyses(analysis_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_pack_id) REFERENCES fmea_evidence_packs(pack_id)
);

CREATE TABLE IF NOT EXISTS fmea_edge_evidence (
    edge_id TEXT NOT NULL,
    evidence_pack_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (edge_id, evidence_id),
    FOREIGN KEY (edge_id) REFERENCES fmea_propagation_edges(edge_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_pack_id, evidence_id) REFERENCES fmea_evidence_refs(pack_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS fmea_audit_events (
    event_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('human', 'model', 'system')),
    command TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    before_hash TEXT,
    after_hash TEXT,
    reason TEXT NOT NULL,
    versions_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
~~~~

`002_indexes.sql` must contain these exact indexes and immutability triggers:

~~~~sql
CREATE INDEX IF NOT EXISTS idx_fmea_rows_analysis_review
    ON fmea_rows(analysis_id, review_status);
CREATE INDEX IF NOT EXISTS idx_fmea_rows_pack
    ON fmea_rows(evidence_pack_id);
CREATE INDEX IF NOT EXISTS idx_fmea_edges_analysis_relation
    ON fmea_propagation_edges(analysis_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_fmea_edges_pack
    ON fmea_propagation_edges(evidence_pack_id);
CREATE INDEX IF NOT EXISTS idx_fmea_row_evidence_ref
    ON fmea_row_evidence(evidence_pack_id, evidence_id);
CREATE INDEX IF NOT EXISTS idx_fmea_edge_evidence_ref
    ON fmea_edge_evidence(evidence_pack_id, evidence_id);
CREATE INDEX IF NOT EXISTS idx_fmea_audit_aggregate
    ON fmea_audit_events(aggregate_type, aggregate_id, created_at);

CREATE TRIGGER IF NOT EXISTS trg_fmea_evidence_packs_no_update
BEFORE UPDATE ON fmea_evidence_packs
BEGIN
    SELECT RAISE(ABORT, 'fmea evidence packs are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_fmea_evidence_packs_no_delete
BEFORE DELETE ON fmea_evidence_packs
BEGIN
    SELECT RAISE(ABORT, 'fmea evidence packs are immutable');
END;
~~~~

- [ ] **Step 1: Write failing migration tests**

Add `tests/unit/test_fmea_migrations.py`:

~~~~python
from pathlib import Path
import sqlite3

import pytest

from fmea_infrastructure.migration_runner import FmeaMigrationError, apply_migrations


MIGRATIONS = Path(__file__).resolve().parents[2] / "fmea_infrastructure" / "migrations"


def test_migrations_create_fmea_schema_and_foreign_keys(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "fmea.sqlite3")
    applied = apply_migrations(connection, MIGRATIONS)

    assert applied == (1, 2)
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'fmea_%'"
        )
    }
    assert {
        "fmea_schema_migrations",
        "fmea_analyses",
        "fmea_evidence_packs",
        "fmea_evidence_refs",
        "fmea_rows",
        "fmea_row_evidence",
        "fmea_propagation_edges",
        "fmea_edge_evidence",
        "fmea_audit_events",
    } <= tables
    assert apply_migrations(connection, MIGRATIONS) == ()


def test_invalid_migration_rolls_back_and_does_not_mark_version(tmp_path: Path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "001_bad.sql").write_text(
        "CREATE TABLE fmea_partial (id TEXT PRIMARY KEY);\n"
        "INSERT INTO table_that_does_not_exist VALUES ('x');\n",
        encoding="utf-8",
    )
    connection = sqlite3.connect(tmp_path / "broken.sqlite3")

    with pytest.raises(FmeaMigrationError, match="001_bad.sql"):
        apply_migrations(connection, migration_dir)

    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'fmea_partial'"
    ).fetchone() is None
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'fmea_schema_migrations'"
    ).fetchone() is None
~~~~

- [ ] **Step 2: Run migration tests to verify the red state**

~~~~powershell
uv run pytest tests/unit/test_fmea_migrations.py -q
~~~~

Expected: collection fails because the migration runner and SQL directory do not exist.

- [ ] **Step 3: Write migration SQL and the ordered transaction runner**

The runner discovers only files matching `^[0-9]{3}_[a-z0-9_]+\.sql$`, rejects duplicate versions, creates no marker until the script and marker insert both succeed, and uses one explicit transaction per migration:

~~~~python
def apply_migrations(connection: sqlite3.Connection, migrations_dir: Path) -> tuple[int, ...]:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    migration_files = _discover_migrations(migrations_dir)
    applied_rows = (
        connection.execute(
            "SELECT version, name FROM fmea_schema_migrations ORDER BY version"
        ).fetchall()
        if _migration_table_exists(connection)
        else []
    )
    applied = {int(row[0]): str(row[1]) for row in applied_rows}
    newly_applied: list[int] = []
    for version, name, sql in migration_files:
        if version in applied:
            if applied[version] != name:
                raise FmeaMigrationError(f"migration version {version} name changed")
            continue
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                + sql
                + "\nINSERT INTO fmea_schema_migrations(version, name, applied_at) "
                + "VALUES ("
                + str(version)
                + ", '"
                + name.replace("'", "''")
                + "', CURRENT_TIMESTAMP);\nCOMMIT;"
            )
        except sqlite3.Error as exc:
            connection.rollback()
            raise FmeaMigrationError(f"migration {name} failed") from exc
        newly_applied.append(version)
    return tuple(newly_applied)
~~~~

Use parameter-free SQL only for the regex-validated migration file name/version; application data uses parameterized SQL later. The runner closes neither the caller-owned connection nor the repository connection.

- [ ] **Step 4: Run migration tests and SQL checks**

~~~~powershell
uv run pytest tests/unit/test_fmea_migrations.py -q
uv run python -c "import sqlite3; from pathlib import Path; from fmea_infrastructure.migration_runner import apply_migrations; c=sqlite3.connect(':memory:'); print(apply_migrations(c, Path('fmea_infrastructure/migrations')))"
~~~~

Expected: pytest passes and the Python command prints `(1, 2)`.

- [ ] **Step 5: Commit the schema and migration runner**

~~~~powershell
git add fmea_infrastructure/__init__.py fmea_infrastructure/migrations/__init__.py fmea_infrastructure/migrations/001_initial.sql fmea_infrastructure/migrations/002_indexes.sql fmea_infrastructure/migration_runner.py tests/unit/test_fmea_migrations.py
git commit -m "feat(fmea): add isolated sqlite migrations"
~~~~

---

### Task 7: Implement SqliteFmeaRepository with Immutability, FK Checks, Audit, and Optimistic Locking

**Responsibility:** `OWN`

**Files:**
- Create: `fmea_infrastructure/repository_sqlite.py`
- Modify: `fmea_infrastructure/__init__.py`
- Test: `tests/integration/test_fmea_repository_sqlite.py`

**Interfaces:**
- Consumes: `FmeaRepository` from `fmea_application.ports`, domain codecs/policies, and `apply_migrations`.
- Produces: `class SqliteFmeaRepository` with every public method in `FmeaRepository`, plus `db_path: Path`, `initialize()`, and `close()`.

The constructor and public methods have these exact signatures:

- `__init__(self, db_path: str | Path, *, migrations_dir: str | Path | None = None) -> None`
- `initialize(self) -> None`
- `close(self) -> None`
- `save_analysis(self, analysis: FmeaAnalysis, *, actor_id: str, actor_type: ActorType, expected_record_version: int | None = None) -> FmeaAnalysis`
- `get_analysis(self, analysis_id: str) -> FmeaAnalysis | None`
- `save_evidence_pack(self, pack: EvidencePack, *, actor_id: str, actor_type: ActorType) -> EvidencePack`
- `get_evidence_pack(self, pack_id: str) -> EvidencePack | None`
- `save_row(self, row: FmeaRow, *, actor_id: str, actor_type: ActorType, expected_record_version: int | None = None) -> FmeaRow`
- `get_row(self, row_id: str) -> FmeaRow | None`
- `save_propagation_edge(self, edge: PropagationEdge, *, actor_id: str, actor_type: ActorType, expected_record_version: int | None = None) -> PropagationEdge`
- `get_propagation_edge(self, edge_id: str) -> PropagationEdge | None`
- `append_audit_event(self, *, actor_id: str, actor_type: ActorType, command: str, aggregate_type: str, aggregate_id: str, before_hash: str | None, after_hash: str | None, reason: str, versions: VersionSet) -> str`

Step 3 implements each method with one connection/transaction per command, domain validation before SQL, `WHERE record_version = ?` for updates, one audit row in the same transaction, and a copied return object with the incremented version. An EvidencePack is insert-once: identical `pack_id` and `pack_hash` is idempotent; a different hash raises `FmeaImmutableError`.

Before applying migrations to an existing file, create a recoverable sibling backup named `<database-name>.pre-migrate.bak` using `shutil.copy2`; do not overwrite an existing backup from the same file modification timestamp. A migration exception rolls back and surfaces as `FmeaRepositoryError` chained from `FmeaMigrationError`.

- [ ] **Step 1: Write failing repository round-trip and failure tests**

Add `tests/integration/test_fmea_repository_sqlite.py` with these assertions after defining local fixtures and saving the referenced analysis/pack in foreign-key order:

~~~~python
from dataclasses import replace
from pathlib import Path

import pytest

from core_domain.fmea.states import ActorType, PublicationStatus, ReviewStatus
from fmea_application.ports import FmeaConcurrencyError, FmeaImmutableError
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository


def test_repository_round_trips_analysis_pack_row_and_edge(
    tmp_path: Path, fixture_analysis, fixture_pack, fixture_row, fixture_edge
) -> None:
    repository = SqliteFmeaRepository(tmp_path / "fmea.sqlite3")
    repository.initialize()

    saved_analysis = repository.save_analysis(
        fixture_analysis, actor_id="system", actor_type=ActorType.SYSTEM
    )
    saved_pack = repository.save_evidence_pack(
        fixture_pack, actor_id="system", actor_type=ActorType.SYSTEM
    )
    saved_row = repository.save_row(
        fixture_row, actor_id="system", actor_type=ActorType.SYSTEM
    )
    saved_edge = repository.save_propagation_edge(
        fixture_edge, actor_id="system", actor_type=ActorType.SYSTEM
    )

    assert repository.get_analysis(saved_analysis.analysis_id) == saved_analysis
    assert repository.get_evidence_pack(saved_pack.pack_id) == saved_pack
    assert repository.get_row(saved_row.row_id) == saved_row
    assert repository.get_propagation_edge(saved_edge.edge_id) == saved_edge
    assert repository._connection.execute(
        "SELECT COUNT(*) FROM fmea_audit_events"
    ).fetchone()[0] == 4


def test_repository_rejects_stale_record_version(tmp_path: Path, fixture_analysis) -> None:
    repository = SqliteFmeaRepository(tmp_path / "fmea.sqlite3")
    repository.initialize()
    repository.save_analysis(fixture_analysis, actor_id="system", actor_type=ActorType.SYSTEM)
    repository.save_analysis(
        replace(fixture_analysis, scope="changed by human"),
        actor_id="human-1",
        actor_type=ActorType.HUMAN,
        expected_record_version=1,
    )

    with pytest.raises(FmeaConcurrencyError, match="record_version"):
        repository.save_analysis(
            replace(fixture_analysis, scope="stale writer"),
            actor_id="human-2",
            actor_type=ActorType.HUMAN,
            expected_record_version=1,
        )


def test_evidence_pack_is_insert_once_and_foreign_keys_are_on(
    tmp_path: Path, fixture_pack
) -> None:
    repository = SqliteFmeaRepository(tmp_path / "fmea.sqlite3")
    repository.initialize()
    repository.save_evidence_pack(fixture_pack, actor_id="system", actor_type=ActorType.SYSTEM)
    assert repository.save_evidence_pack(
        fixture_pack, actor_id="system", actor_type=ActorType.SYSTEM
    ) == fixture_pack

    changed = replace(fixture_pack, pack_hash="0" * 64)
    with pytest.raises(FmeaImmutableError, match="immutable"):
        repository.save_evidence_pack(changed, actor_id="system", actor_type=ActorType.SYSTEM)
    assert repository._connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_model_cannot_persist_accepted_or_published_state(
    tmp_path: Path, fixture_analysis, fixture_pack, fixture_row
) -> None:
    repository = SqliteFmeaRepository(tmp_path / "fmea.sqlite3")
    repository.initialize()
    repository.save_analysis(fixture_analysis, actor_id="system", actor_type=ActorType.SYSTEM)
    repository.save_evidence_pack(fixture_pack, actor_id="system", actor_type=ActorType.SYSTEM)
    model_row = replace(
        fixture_row,
        review_status=ReviewStatus.ACCEPTED,
        publication_status=PublicationStatus.PUBLISHED,
    )
    with pytest.raises(ValueError, match="human actor"):
        repository.save_row(model_row, actor_id="model-1", actor_type=ActorType.MODEL)
~~~~

- [ ] **Step 2: Run repository tests to verify the red state**

~~~~powershell
uv run pytest tests/integration/test_fmea_repository_sqlite.py -q
~~~~

Expected: collection fails because `SqliteFmeaRepository` is not present.

- [ ] **Step 3: Write the minimal repository transaction helpers**

Implement `_connect()` with `sqlite3.connect(self.db_path)`, `row_factory = sqlite3.Row`, `PRAGMA foreign_keys = ON`, and `PRAGMA busy_timeout = 5000`. Use one fixed-table update helper:

~~~~python
def _update_payload(
    connection: sqlite3.Connection,
    *,
    table: str,
    identity_column: str,
    identity: str,
    payload: str,
    updated_at: str,
    expected_record_version: int,
) -> int:
    cursor = connection.execute(
        f"UPDATE {table} SET payload_json = ?, updated_at = ?, "
        "record_version = record_version + 1 "
        f"WHERE {identity_column} = ? AND record_version = ?",
        (payload, updated_at, identity, expected_record_version),
    )
    if cursor.rowcount != 1:
        raise FmeaConcurrencyError(f"record_version conflict for {table}:{identity}")
    return expected_record_version + 1
~~~~

Table and identity values passed to this helper come from fixed internal constants, never request input. `save_row` and `save_propagation_edge` insert evidence-link rows in the same transaction after validation. `save_evidence_pack` inserts the pack and refs in one transaction and catches duplicate pack hashes to distinguish idempotence from changed immutable content. Audit rows use `versions_json` from `VersionSet`.

- [ ] **Step 4: Run repository tests, focused domain tests, and lint**

~~~~powershell
uv run pytest tests/integration/test_fmea_repository_sqlite.py tests/unit/test_fmea_migrations.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_scoring.py tests/unit/test_fmea_propagation.py -q
uv run ruff check fmea_infrastructure tests/integration/test_fmea_repository_sqlite.py
~~~~

Expected: all selected tests pass and Ruff exits `0`.

- [ ] **Step 5: Commit the SQLite repository**

~~~~powershell
git add fmea_infrastructure/repository_sqlite.py fmea_infrastructure/__init__.py tests/integration/test_fmea_repository_sqlite.py
git commit -m "feat(fmea): add sqlite repository and audit writes"
~~~~

---

### Task 8: Bind FMEA Storage to WorkspaceRegistry Without Touching Query Storage

**Responsibility:** `INTEGRATE`; this task is limited to an adapter/configuration field and tests. It does not rewrite `WorkspaceRegistry`, `QueryService`, `GraphStore`, or API composition.

**Files:**
- Modify: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/workspace_registry.py`
- Modify: `tests/unit/test_workspace_registry.py`

**Interfaces:**
- Consumes: existing `WorkspaceRegistry` JSON shape and `allowed_root` containment logic.
- Produces: `WorkspaceConfig.fmea_db_path: Path | None`; relative-path resolution from registry directory; contained-path validation; a stable `WorkspaceConfigError` when a composition caller requires FMEA storage but the field is absent.

Add exactly one optional field to the existing frozen model:

~~~~python
fmea_db_path: Path | None = None
~~~~

When present, resolve it with the same registry-directory rules as `graph_db_path`, then call `_ensure_contained(path, allowed_root, field_name=f"{workspace_id}.fmea_db_path")`. When absent, retain `None` so existing non-FMEA query workspaces remain valid. The FMEA composition boundary treats `None` as a configuration failure and never falls back to `graph_db_path`.

- [ ] **Step 1: Add failing WorkspaceRegistry tests**

Extend `_write_registry` with `"fmea_db_path": "../runtime/fmea/fmea.sqlite3"` and add:

~~~~python
def test_registry_resolves_fmea_database_under_allowed_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path, allowed_root = _write_registry(tmp_path)
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))

    workspace = WorkspaceRegistry.from_env().get("power-equipment")

    assert workspace.fmea_db_path == (allowed_root / "fmea" / "fmea.sqlite3").resolve()


def test_registry_rejects_fmea_database_outside_allowed_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path, _ = _write_registry(
        tmp_path,
        workspace={
            "chroma_persist_dir": "../runtime/chroma",
            "chroma_collection": "power_equipment",
            "graph_db_path": "../runtime/graph/graph.sqlite3",
            "fmea_db_path": "../outside/fmea.sqlite3",
            "supported_modes": ["vector"],
            "default_mode": "vector",
        },
    )
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))

    with pytest.raises(WorkspaceConfigError, match="fmea_db_path.*allowed_root"):
        WorkspaceRegistry.from_env()


def test_registry_keeps_missing_fmea_binding_explicit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path, _ = _write_registry(
        tmp_path,
        workspace={
            "chroma_persist_dir": "../runtime/chroma",
            "chroma_collection": "power_equipment",
            "graph_db_path": None,
            "supported_modes": ["vector"],
            "default_mode": "vector",
        },
    )
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))

    assert WorkspaceRegistry.from_env().get("power-equipment").fmea_db_path is None
~~~~

- [ ] **Step 2: Run the registry tests to verify the red state**

~~~~powershell
uv run pytest tests/unit/test_workspace_registry.py -q
~~~~

Expected: the new tests fail because `WorkspaceConfig` has no `fmea_db_path` field and the loader does not resolve it.

- [ ] **Step 3: Add the narrow storage binding**

In `_build_workspaces`, resolve `raw_workspace.get("fmea_db_path")` only when non-null, enforce `allowed_root`, and pass the value into `WorkspaceConfig`. Do not import `SqliteFmeaRepository` from this existing query package. The composition guard is:

~~~~python
def require_fmea_db_path(workspace: WorkspaceConfig) -> Path:
    if workspace.fmea_db_path is None:
        raise WorkspaceConfigError(
            f"Workspace '{workspace.workspace_id}' has no fmea_db_path binding."
        )
    return workspace.fmea_db_path
~~~~

The guard derives no path and creates no database. Existing tests that intentionally omit a graph database continue to pass with `fmea_db_path is None`.

- [ ] **Step 4: Run the full registry test file and lint**

~~~~powershell
uv run pytest tests/unit/test_workspace_registry.py -q
uv run ruff check api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/workspace_registry.py tests/unit/test_workspace_registry.py
~~~~

Expected: all registry tests pass and Ruff exits `0`.

- [ ] **Step 5: Commit only the integration binding**

~~~~powershell
git add api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/workspace_registry.py tests/unit/test_workspace_registry.py
git commit -m "feat(fmea): bind workspace fmea database path"
~~~~

---

### Task 9: Prove the Pure Domain-to-Workspace-to-SQLite Closure

**Responsibility:** `OWN` for the acceptance fixture and quality gate; it consumes the `INTEGRATE` binding from Task 8 without modifying upstream systems.

**Files:**
- Create: `tests/integration/test_fmea_foundation_closure.py`

**Interfaces:**
- Consumes: `WorkspaceRegistry.fmea_db_path`, `FmeaService`, `FmeaCandidatePipeline`, and `SqliteFmeaRepository`.
- Produces: one reproducible test proving an analysis, EvidencePack, row, and PropagationEdge can be created locally, persisted to the dedicated workspace database, reopened, and read back with exact versions, hashes, states, and audit events.

- [ ] **Step 1: Write the red closure test**

The four fixtures are registered by `tests/conftest.py`; create a temporary JSON registry with `allowed_root` and `fmea_db_path`, and write this complete flow:

~~~~python
import json
from dataclasses import replace
from pathlib import Path

from core_domain.fmea.states import ActorType, ReviewStatus
from chroma_rag_poc.workspace_registry import WorkspaceRegistry
from fmea_application.services import FmeaService
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository


def test_fmea_foundation_closes_over_workspace_sqlite(
    tmp_path: Path, fixture_analysis, fixture_pack, fixture_row, fixture_edge
) -> None:
    registry_path = tmp_path / "workspace.json"
    allowed_root = tmp_path / "runtime"
    registry_path.write_text(
        json.dumps(
            {
                "allowed_root": str(allowed_root),
                "workspaces": {
                    "fuel-combustion": {
                        "chroma_persist_dir": str(allowed_root / "chroma"),
                        "chroma_collection": "fuel_combustion",
                        "graph_db_path": None,
                        "fmea_db_path": str(allowed_root / "fmea" / "fmea.sqlite3"),
                        "supported_modes": ["vector"],
                        "default_mode": "vector",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    workspace = WorkspaceRegistry.from_file(registry_path).get("fuel-combustion")
    assert workspace.fmea_db_path is not None

    repository = SqliteFmeaRepository(workspace.fmea_db_path)
    repository.initialize()
    service = FmeaService(repository)
    service.create_analysis(fixture_analysis, actor_id="system", actor_type=ActorType.SYSTEM)
    service.register_evidence_pack(fixture_pack, actor_id="system", actor_type=ActorType.SYSTEM)
    long_edge = replace(fixture_edge, edge_id="edge-long", path_length=3)
    rows, edges = service.generate_candidates(
        analysis=fixture_analysis,
        evidence_pack=fixture_pack,
        rows=(fixture_row,),
        edges=(fixture_edge, long_edge),
        actor_id="system",
        actor_type=ActorType.SYSTEM,
    )

    reopened = SqliteFmeaRepository(workspace.fmea_db_path)
    reopened.initialize()
    assert reopened.get_analysis(fixture_analysis.analysis_id) == fixture_analysis
    assert reopened.get_evidence_pack(fixture_pack.pack_id) == fixture_pack
    assert reopened.get_row(rows[0].row_id) == rows[0]
    assert reopened.get_propagation_edge(edges[0].edge_id) == edges[0]
    assert reopened.get_propagation_edge("edge-long").review_status is ReviewStatus.IN_REVIEW
    assert reopened._connection.execute(
        "SELECT COUNT(*) FROM fmea_audit_events"
    ).fetchone()[0] == 5
    assert workspace.graph_db_path is None
    assert reopened.db_path == workspace.fmea_db_path
~~~~

The test also asserts that an evidence ID from another pack fails before database write, a three-hop edge is stored as `in_review`, and a model actor cannot write accepted/published state. These are the Phase 1 evidence/state hard-zero checks in scope.

- [ ] **Step 2: Run the closure test to verify the red state**

~~~~powershell
uv run pytest tests/integration/test_fmea_foundation_closure.py -q
~~~~

Expected: the test fails until the repository, application, and WorkspaceRegistry bindings are connected.

- [ ] **Step 3: Keep the closure fixture local and bounded**

Use `workspace_id="ws-1"`, one reviewed primary document, one `fuel_pressure` edge, one two-hop propagation edge, and one three-hop edge. Do not add real documents, LLM calls, network access, REST routes, UI files, or export files. The closure runs with `uv run pytest` on an empty temporary directory.

- [ ] **Step 4: Run the complete Phase 1 quality gate**

~~~~powershell
uv run pytest tests/unit/test_fmea_states.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_scoring.py tests/unit/test_fmea_propagation.py tests/unit/test_fmea_application.py tests/unit/test_fmea_migrations.py tests/unit/test_workspace_registry.py tests/integration/test_fmea_repository_sqlite.py tests/integration/test_fmea_foundation_closure.py -q
uv run ruff check core_domain/fmea fmea_application fmea_infrastructure api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/workspace_registry.py tests/unit/test_fmea_states.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_scoring.py tests/unit/test_fmea_propagation.py tests/unit/test_fmea_application.py tests/unit/test_fmea_migrations.py tests/unit/test_workspace_registry.py tests/integration/test_fmea_repository_sqlite.py tests/integration/test_fmea_foundation_closure.py
git diff --check
~~~~

Expected: every selected test passes, Ruff exits `0`, and `git diff --check` prints no whitespace errors.

- [ ] **Step 5: Commit the closure test and quality gate**

~~~~powershell
git add tests/integration/test_fmea_foundation_closure.py tests/unit/test_fmea_application.py
git commit -m "test(fmea): verify foundation domain storage closure"
~~~~

---

## Execution Handoff

Implement Tasks 1–9 in order because later tasks consume the exact shared names and ports defined earlier. Every task has its own red test, green implementation, focused verification, and narrow commit. Do not combine commits or stage unrelated existing changes. The first implementation command is:

~~~~powershell
Set-Location C:\Users\35551\Desktop\RAG\.worktrees\interface-output-v1
git status --short
~~~~

The expected Phase 1 result is a model-free, local, replayable FMEA closure: domain objects validate invariants; the candidate boundary persists only `suggested`/`in_review` and `unpublished` results; SQLite owns an isolated schema with FK/unique/transaction/optimistic-lock guarantees; workspace storage is contained under `allowed_root`; and no query, GraphStore, model, HTTP, UI, or export implementation is introduced.

## Plan Self-Review

- [ ] Spec coverage: Tasks 1–4 cover the semantic model, three independent state axes, versions, EvidencePack, risk rules, and PropagationEdge from Sections 5–8 and Stage A.
- [ ] Storage coverage: Tasks 6–7 cover the dedicated SQLite schema, migrations, foreign keys, unique constraints, transaction rollback, backup, audit writes, immutable packs, and optimistic locking from Stage B.
- [ ] Integration coverage: Task 8 covers only the `WorkspaceRegistry` FMEA storage binding and contained-path failure behavior; it does not assign upstream GraphRAG work.
- [ ] Closure coverage: Task 9 proves the requested independently runnable pure-domain/storage loop and in-scope evidence/state hard-zero invariants.
- [ ] Responsibility check: implementation work maps to `OWN`; the only integration task is adapter/configuration/test work; dependencies are written as inputs and failures; excluded capabilities are not tasks.
- [ ] Type check: every task uses the exact shared names, `fmea_application/ports.py`, `SqliteFmeaRepository`, `FmeaService`, `FmeaCandidatePipeline`, and `graphrag.fmea.v1`.
- [ ] Placeholder check: every task has named files, interfaces, executable test code, minimal implementation code, exact commands, expected outcomes, and a commit command.
