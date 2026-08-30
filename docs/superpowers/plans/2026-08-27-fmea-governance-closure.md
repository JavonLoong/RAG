# FMEA Governance Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assemble complete FMEA revisions and add human approval, immutable publication, withdrawal, supersession, normalized snapshots, audit, and outbox replay.

**Architecture:** A new `RevisionGovernanceService` consumes only immutable Phase 1/2 records and composes accepted rows, confirmed risk records, a confirmed propagation graph, EvidencePack lineage, DomainPack/template/rule identities, and human acknowledgements into one hash-bound revision. Approval submission, approval decision, publication, withdrawal, and supersession are separate human commands. Publication atomically stores the exact approved revision, immutable manifest, canonical normalized snapshot, audit event, idempotency response, export-eligibility record, and outbox event; later lifecycle changes append events and links without rewriting the publication.

**Tech Stack:** Python 3.11+, frozen dataclasses, Enum, Protocol, Pydantic 2.13, FastAPI, SQLite/WAL, orjson, SHA-256 canonical serialization, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-27-full-fmea-modular-product-design.md`

**Revalidated baseline:** Phase 2 commit `281d9c55` on 2026-08-30. Before execution, confirm the current branch is this commit or a reviewed descendant and rerun the Phase 2 verifier.

## Global Constraints

- Risk and propagation closure phases are complete and expose stable query contracts.
- Governance starts at the immutable FMEA boundary: accepted row revisions, confirmed risk, confirmed propagation, and versioned EvidencePacks. It never calls `retrieval_engine`, `kg_pipeline`, `rag_orchestrator`, or a GraphRAG backend.
- `rag_only`, `graphrag_local_only`, `graphrag_global_only`, `graphrag_only`, `combined`, `custom`, and `auto -> combined` remain upstream EvidencePack provenance. Governance preserves requested/resolved profiles and evidence types but does not reinterpret retrieval mode.
- Review, risk, propagation, approval, and publication states remain orthogonal.
- Model actors cannot approve, publish, withdraw, supersede, or alter readiness policy.
- The initial local account may hold reviewer, risk reviewer, propagation reviewer, approver, and publisher roles, but every authority command remains separate.
- Approval submission creates `pending`; an approver records `approved` or `rejected`; approval withdrawal is a separate append-only command. No command silently skips an approval state.
- Approval binds to one immutable revision hash; any child change requires a new approval.
- Published revisions and manifests are immutable and never deleted or updated in place.
- Withdrawal and supersession append records and preserve the original publication payload and audit chain.
- Compatibility ruling: existing row/edge `PublicationStatus` and the `fmea_rows` CHECK remain unchanged. Phase 3 introduces revision-level `ApprovalStatus` and `RevisionPublicationStatus`; supersession belongs to immutable revision publications, not mutable row records.
- All writes require canonical UUID idempotency keys, optimistic preconditions, workspace isolation, and atomic audit/outbox records.
- JSON stored for revisions, manifests, snapshots, and events is strict, canonical, finite, duplicate-key-free, and hash-verified.
- Existing review REST/CLI and database records remain compatible.
- REST/CLI receive revision/publication IDs and authority confirmations only; DomainPack, template, rule, EvidencePack, risk, and topology identities are resolved from server-owned persisted records.
- Model readiness assistance is optional and provider-neutral. Default acceptance is deterministic/offline; `deepseek-v4-pro` is allowed only through explicit environment configuration and is never required by a completion gate.
- Phase 3 creates canonical JSON snapshots and export eligibility only. XLSX/DOCX generation, template import/migration, browser workbench, and multi-domain delivery remain Phase 4.

## File map

- `core_domain/fmea/governance.py`: revision, readiness, revision-level approval/publication states, withdrawal, supersession, and manifest contracts; legacy row/edge states remain untouched.
- `fmea_application/snapshot_contracts.py`: normalized snapshot DTO.
- `fmea_application/revision_assembler.py`: deterministic revision and snapshot assembly.
- `fmea_application/governance_assistance_service.py`: immutable readiness-checklist suggestion orchestration.
- `fmea_application/governance_contracts.py`: commands, results, and prepared transactions.
- `fmea_application/governance_service.py`: readiness, approval, publication, withdrawal, supersession, and query orchestration.
- `fmea_application/ports.py`: governance repository and source-query ports.
- `fmea_infrastructure/governance_assistance_generator.py`: bounded approval-readiness checklist assistance.
- `fmea_infrastructure/governance_repository_sqlite.py`: immutable governance persistence.
- `fmea_infrastructure/migrations/005_fmea_governance_closure.sql`: revision, approval, publication, snapshot, withdrawal, and outbox indexes.
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_governance_contracts.py`: REST schemas.
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_governance_v1.py`: governance routes.
- `scripts/fmea_skill.py`: `revision`, `approval`, and `publication` CLI groups.
- `scripts/run_fmea_governance_acceptance.py` and `scripts/verify_fmea_governance_acceptance.py`: independent acceptance.
- `tests/fmea_governance_fixtures.py`: deterministic Phase 1/2 source records and prepared governance transactions shared by focused tests.

## Task dependency and review gates

Task 1 freezes contracts. Task 2 depends only on Task 1 and existing Phase 1/2 query ports. Task 3 depends on Task 1 and may use fake prepared transactions before the orchestration service exists. Task 4 integrates Tasks 2 and 3. Task 5 exposes only Task 4 application services. Task 6 consumes the entire Phase 3 surface and must not compensate for missing lower-layer validation inside the acceptance scripts.

Each Task is one independently reviewable commit group. After its focused GREEN run, dispatch a read-only scoped review against that Task's fixed commit range; resolve Critical and Important findings before starting the next Task. Minor findings are either fixed in the same Task or recorded with an explicit deferral reason and owner. Task 6 completion additionally requires one final review of the whole Phase 3 range and fresh main-session execution of the exact Phase 3 gate.

---

### Task 1: Freeze revision, readiness, approval, publication, and snapshot contracts

**Files:**
- Create: `core_domain/fmea/governance.py`
- Modify: `core_domain/fmea/__init__.py`
- Create: `fmea_application/snapshot_contracts.py`
- Create: `fmea_application/governance_contracts.py`
- Create: `tests/fmea_governance_fixtures.py`
- Test: `tests/unit/test_fmea_governance_contracts.py`
- Test: `tests/unit/test_fmea_snapshot_contracts.py`

**Interfaces:**
- Consumes: accepted `FmeaRow`, confirmed `RiskAssessmentRecord`, confirmed `PropagationGraphRevision`, EvidencePacks, DomainPack, and version identities.
- Produces: `ApprovalStatus`, `RevisionPublicationStatus`, `FmeaRevision`, `ReadinessIssue`, `ApprovalSubmission`, `ApprovalDecision`, `ApprovalWithdrawalRecord`, `PublicationManifest`, `PublishedRevision`, `PublicationWithdrawalRecord`, `SupersessionRecord`, `PublicationLifecycleView`, `NormalizedFmeaSnapshot`, `NormalizedSnapshotPage`, `build_normalized_snapshot()`, `iter_normalized_snapshot_pages()`, canonical body/hash helpers, and deterministic test factories.

- [ ] **Step 1: Write immutable contract and hash tests**

```python
def test_approval_decision_binds_exact_revision_hash():
    decision = make_approval_decision(revision_hash="a" * 64)
    with pytest.raises(FmeaDomainError, match="approval revision hash mismatch"):
        validate_approval_binding(decision, make_fmea_revision(revision_hash="b" * 64))


def test_normalized_snapshot_rejects_different_publication_revision():
    with pytest.raises(FmeaDomainError, match="snapshot publication binding"):
        make_normalized_snapshot(revision_id="rev-1", publication_revision_id="rev-2")


def test_supersession_is_a_link_and_does_not_mutate_old_publication():
    old_revision = make_fmea_revision(revision_id="rev-old")
    new_revision = make_fmea_revision(revision_id="rev-new", parent_revision_id=old_revision.revision_id)
    old = make_published_revision(publication_id="pub-old", revision_id=old_revision.revision_id)
    new = make_published_revision(publication_id="pub-new", revision_id=new_revision.revision_id)
    link = make_supersession_record(old_publication_id=old.publication_id, new_publication_id=new.publication_id)
    validate_supersession_binding(
        link,
        old=old,
        replacement=new,
        old_revision=old_revision,
        replacement_revision=new_revision,
    )
    view = project_publication_lifecycle(old, withdrawal=None, supersession=link)
    assert view.publication == old
    assert view.effective_status is RevisionPublicationStatus.SUPERSEDED
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py -q`

Expected: FAIL because governance contracts are absent.

- [ ] **Step 3: Implement immutable contracts and canonical hash functions**

```python
class ApprovalStatus(str, Enum):
    NOT_SUBMITTED = "not_submitted"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class RevisionPublicationStatus(str, Enum):
    UNPUBLISHED = "unpublished"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class RetrievalProvenanceSnapshot:
    requested_profile: str
    resolved_profile: str
    evidence_types: tuple[str, ...]
    source_counts: tuple[tuple[str, int], ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FmeaRevision:
    revision_id: str
    workspace_id: str
    analysis_id: str
    analysis_record_version: int
    analysis_hash: str
    parent_revision_id: str | None
    parent_revision_hash: str | None
    row_versions: tuple[tuple[str, int, str], ...]
    risk_versions: tuple[tuple[str, int, str], ...]
    propagation_graph_revision_id: str | None
    propagation_graph_hash: str | None
    evidence_pack_hashes: tuple[tuple[str, str], ...]
    retrieval_provenance: RetrievalProvenanceSnapshot
    domain_pack_identity: tuple[str, str, str]
    template_identities: tuple[tuple[str, str, str], ...]
    scoring_rule_identities: tuple[tuple[str, str, str], ...]
    propagation_rule_identity: tuple[str, str, str] | None
    unresolved_items: tuple[ReadinessIssue, ...]
    revision_hash: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ReadinessIssue:
    code: str
    severity: Literal["info", "warning", "blocking", "critical"]
    source_type: str
    source_id: str
    evidence_ids: tuple[str, ...]
    acknowledgement_decision_id: str | None


@dataclass(frozen=True, slots=True)
class ApprovalSubmission:
    submission_id: str
    workspace_id: str
    revision_id: str
    revision_hash: str
    status: ApprovalStatus
    submitter_actor_id: str
    record_version: int
    created_at: str


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    approval_id: str
    submission_id: str
    revision_id: str
    revision_hash: str
    status: ApprovalStatus
    approver_actor_id: str
    reason: str
    record_version: int
    created_at: str


@dataclass(frozen=True, slots=True)
class ApprovalWithdrawalRecord:
    withdrawal_id: str
    approval_id: str
    revision_id: str
    revision_hash: str
    actor_id: str
    reason: str
    created_at: str


@dataclass(frozen=True, slots=True)
class PublicationManifest:
    manifest_id: str
    revision_id: str
    revision_hash: str
    approval_id: str
    snapshot_id: str
    snapshot_hash: str
    version_manifest_hash: str
    previous_audit_chain_head: str | None
    export_eligible: bool
    manifest_hash: str
    created_at: str


@dataclass(frozen=True, slots=True)
class PublishedRevision:
    publication_id: str
    workspace_id: str
    analysis_id: str
    revision_id: str
    revision_hash: str
    approval_id: str
    manifest_id: str
    manifest_hash: str
    snapshot_id: str
    snapshot_hash: str
    audit_chain_head: str
    publisher_actor_id: str
    record_version: int
    created_at: str


@dataclass(frozen=True, slots=True)
class PublicationWithdrawalRecord:
    withdrawal_id: str
    publication_id: str
    replacement_publication_id: str | None
    actor_id: str
    reason: str
    created_at: str


@dataclass(frozen=True, slots=True)
class SupersessionRecord:
    supersession_id: str
    old_publication_id: str
    new_publication_id: str
    actor_id: str
    reason: str
    created_at: str


@dataclass(frozen=True, slots=True)
class PublicationLifecycleView:
    publication: PublishedRevision
    effective_status: RevisionPublicationStatus
    withdrawal: PublicationWithdrawalRecord | None
    supersession: SupersessionRecord | None


@dataclass(frozen=True, slots=True)
class NormalizedFmeaSnapshot:
    schema_version: Literal["graphrag.fmea.normalized-snapshot.v1"]
    snapshot_id: str
    workspace_id: str
    analysis_id: str
    revision_id: str
    revision_hash: str
    publication_id: str
    manifest_id: str
    rows: tuple[Mapping[str, object], ...]
    risk_records: tuple[Mapping[str, object], ...]
    propagation: Mapping[str, object] | None
    evidence_summary: tuple[Mapping[str, object], ...]
    decision_summary: tuple[Mapping[str, object], ...]
    version_manifest: Mapping[str, object]
    unresolved_items: tuple[Mapping[str, object], ...]
    audit_summary: Mapping[str, object]
    row_count: int
    snapshot_hash: str
    created_at: str


@dataclass(frozen=True, slots=True)
class NormalizedSnapshotPage:
    rows: tuple[Mapping[str, object], ...]
    next_offset: int | None


@dataclass(frozen=True, slots=True)
class NormalizedSnapshotInput:
    revision: FmeaRevision
    publication_id: str
    manifest_id: str
    rows: tuple[Mapping[str, object], ...]
    risk_records: tuple[Mapping[str, object], ...]
    propagation: Mapping[str, object] | None
    evidence_summary: tuple[Mapping[str, object], ...]
    decision_summary: tuple[Mapping[str, object], ...]
    version_manifest: Mapping[str, object]
    audit_summary: Mapping[str, object]
    created_at: str


def build_normalized_snapshot(source: NormalizedSnapshotInput) -> NormalizedFmeaSnapshot:
    body = canonical_normalized_snapshot_body(source)
    return NormalizedFmeaSnapshot(
        **body,
        snapshot_hash=sha256(canonical_json_bytes(body)).hexdigest(),
    )


def iter_normalized_snapshot_pages(
    snapshot: NormalizedFmeaSnapshot, *, page_size: int
) -> Iterator[NormalizedSnapshotPage]:
    if isinstance(page_size, bool) or not 1 <= page_size <= 500:
        raise ValueError("page_size must be between 1 and 500")
    for offset in range(0, snapshot.row_count, page_size):
        rows = snapshot.rows[offset : offset + page_size]
        next_offset = offset + page_size if offset + page_size < snapshot.row_count else None
        yield NormalizedSnapshotPage(rows=rows, next_offset=next_offset)


@dataclass(frozen=True, slots=True)
class RevisionAssemblyRequest:
    analysis_id: str
    parent_revision_id: str | None
    expected_analysis_version: int


@dataclass(frozen=True, slots=True)
class AssembleRevisionCommand:
    request: RevisionAssemblyRequest
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class SubmitApprovalCommand:
    revision_id: str
    revision_hash: str
    expected_revision_version: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ApprovalCommand:
    submission_id: str
    revision_id: str
    revision_hash: str
    expected_submission_version: int
    reason: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ApprovalRejectionCommand:
    submission_id: str
    revision_id: str
    revision_hash: str
    expected_submission_version: int
    reason: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class WithdrawApprovalCommand:
    approval_id: str
    revision_hash: str
    expected_approval_version: int
    reason: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class PublishCommand:
    revision_id: str
    revision_hash: str
    approval_id: str
    expected_revision_version: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class WithdrawPublicationCommand:
    publication_id: str
    expected_publication_version: int
    reason: str
    replacement_publication_id: str | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class SupersedePublicationCommand:
    publication_id: str
    replacement_publication_id: str
    expected_publication_version: int
    expected_replacement_version: int
    reason: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class GovernanceHistoryQuery:
    workspace_id: str
    resource_type: Literal["revision", "publication"]
    resource_id: str
    page_size: int
    cursor: str | None
    descending: bool = False
```

Do not add `SUPERSEDED` to the legacy row/edge `PublicationStatus`. `RevisionPublicationStatus` is the lifecycle projection for immutable revision publications; `SupersessionRecord` is authoritative evidence and the old/new `PublishedRevision` payloads remain byte-identical. `ApprovalSubmission` records the exact `revision_id`, `revision_hash`, submitter, and `PENDING` status. `ApprovalDecision` records only `APPROVED` or `REJECTED`; withdrawal appends a separate approval lifecycle record.

Every `Prepared*` transaction in `governance_contracts.py` is a frozen record with `scope: IdempotencyScope`, `payload_hash: str`, the canonical command payload, the exact expected record version(s), the immutable domain object(s) being written, one actor-bound audit event, and one matching `OutboxEvent`. Result types carry the committed object IDs, versions, audit/outbox IDs, and `replayed: bool`; no result may report success when its audit or outbox binding is missing.

Canonicalize sorted identities and records with the existing strict canonical JSON rules, reject non-finite values and duplicate identities, and verify all supplied hashes. The revision content hash excludes transport metadata (`trace_id`, request ID) and volatile persistence metadata, but includes parent revision identity/hash, every child record version/hash, EvidencePack lineage/hash, DomainPack/template/rule identities, acknowledged issue identities, and retrieval provenance. `NormalizedFmeaSnapshot` contains bounded export-safe semantic data and no credentials, prompts, private paths, raw provider output, or mutable URLs.

`tests/fmea_governance_fixtures.py` defines the exact factories used by later tasks: `make_fmea_revision`, `make_large_revision`, `make_readiness_issue`, `make_blocked_readiness_report`, `make_approval_submission`, `make_approval_decision`, `make_published_revision`, `make_normalized_snapshot`, `make_normalized_snapshot_input`, `make_supersession_record`, `make_governance_actor`, `make_governance_inputs`, `make_assemble_request`, `make_readiness_context`, `make_domain_policy`, `make_approval_command`, `make_publish_command`, `make_cross_analysis_supersession_command`, `prepared_revision`, `prepared_approval_submission`, `prepared_approval`, `prepared_approval_withdrawal`, `prepared_publication`, `prepared_publication_withdrawal`, `prepared_supersession`, and `persisted_publication_pair`. The fixture module may compose existing `tests/fmea_fixtures.py` and `tests/fmea_propagation_fixtures.py`, but must not duplicate production validation logic.

- [ ] **Step 4: Run governance, snapshot, and existing codec tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_review_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit governance contracts**

```powershell
git add core_domain/fmea/governance.py core_domain/fmea/__init__.py fmea_application/snapshot_contracts.py fmea_application/governance_contracts.py tests/fmea_governance_fixtures.py tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py
git commit -m "feat(fmea): define immutable governance revisions"
```

### Task 2: Assemble revisions and evaluate publication readiness

**Files:**
- Create: `fmea_application/revision_assembler.py`
- Create: `fmea_application/governance_assistance_service.py`
- Create: `fmea_infrastructure/governance_assistance_generator.py`
- Modify: `fmea_application/ports.py`
- Modify: `fmea_infrastructure/composition.py`
- Test: `tests/unit/test_fmea_revision_assembler.py`
- Test: `tests/unit/test_fmea_publication_readiness.py`
- Test: `tests/unit/test_fmea_governance_assistance.py`

**Interfaces:**
- Consumes: repository query ports for rows, source packs, risk, propagation, decisions, active mutating runs, DomainPack, templates, and rules. No retrieval or GraphRAG service is accepted by the constructor.
- Produces: `GovernanceInputs`, `GovernanceSourcePort.load_inputs()`, `RevisionAssembler.assemble()`, `PublicationReadinessPolicy.evaluate()`, and immutable model-assisted readiness checklists that cannot change deterministic readiness.

- [ ] **Step 1: Write complete and blocked-readiness tests**

```python
def test_revision_assembler_is_order_independent():
    first = assembler(rows=(row_b(), row_a())).assemble(request())
    second = assembler(rows=(row_a(), row_b())).assemble(request())
    assert first.revision_hash == second.revision_hash


def test_high_risk_unresolved_propagation_blocks_approval():
    revision = make_fmea_revision(
        unresolved_items=(
            make_readiness_issue(code="PROPAGATION_HIGH_RISK_UNRESOLVED", severity="critical"),
        )
    )
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(revision, make_readiness_context())
    assert not report.ready
    assert report.blocking_codes == ("PROPAGATION_HIGH_RISK_UNRESOLVED",)


def test_model_readiness_checklist_cannot_clear_a_blocker(assistance_service):
    report = make_blocked_readiness_report()
    suggestion = assistance_service.suggest_readiness_checklist(
        report,
        make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset()),
    )
    assert suggestion.kind is AssistanceKind.APPROVAL_READINESS_CHECKLIST
    assert suggestion.applied is False
    assert report.ready is False


def test_assembler_preserves_retrieval_provenance_without_retrieval_dependency():
    inputs = make_governance_inputs(requested_profile="graphrag_only", resolved_profile="graphrag_only")
    revision = RevisionAssembler().assemble(make_assemble_request(), inputs)
    assert revision.retrieval_provenance.resolved_profile == "graphrag_only"
    assert revision.retrieval_provenance.evidence_types == ("graph", "community")


def test_active_mutating_run_blocks_readiness():
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(
        make_fmea_revision(),
        make_readiness_context(active_run_ids=("propagation-run-1",)),
    )
    assert report.blocking_codes == ("ACTIVE_MUTATION_RUN",)
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py -q`

Expected: FAIL because assembler and policy are absent.

- [ ] **Step 3: Implement deterministic assembly and readiness**

```python
@dataclass(frozen=True, slots=True)
class PublicationReadinessContext:
    active_run_ids: tuple[str, ...]
    current_analysis_version: int
    current_child_hashes: tuple[tuple[str, str], ...]


class GovernanceSourcePort(Protocol):
    def load_inputs(self, analysis_id: str, workspace_id: str) -> GovernanceInputs: ...


class RevisionAssembler:
    def assemble(self, request: RevisionAssemblyRequest, inputs: GovernanceInputs) -> FmeaRevision: ...


class PublicationReadinessPolicy:
    def evaluate(
        self, revision: FmeaRevision, context: PublicationReadinessContext
    ) -> PublicationReadinessReport: ...


class GovernanceAssistanceService:
    def suggest_readiness_checklist(
        self, report: PublicationReadinessReport, actor: ActorContext
    ) -> AssistanceSuggestion[ReadinessChecklistDraft]: ...
```

`GovernanceInputs` is a frozen application DTO containing the exact accepted rows, confirmed risk records, confirmed graph, EvidencePacks, DomainPack/template/rule manifests, human decision references, and active mutation run IDs. Its adapter composes existing review/risk/propagation repositories behind the port and rejects mixed workspace/analysis identities before assembly.

Sort rows and identities canonically. Reject non-accepted required rows, missing or stale/invalidated risk, missing or stale/invalidated required propagation, unresolved version/hash identities, active generation/evidence-refresh/propagation/migration/export-preview runs, missing required evidence, and unacknowledged critical issues. Preserve only existing human-authored acknowledgement references from prior review/risk/propagation decisions in the revision and later manifest; readiness assistance cannot create an acknowledgement or erase a blocker. Run deterministic readiness first; the optional model receives the immutable bounded report and projection-safe evidence only, returns the shared `AssistanceSuggestion(applied=false)` envelope, and cannot add/remove blockers or set `ready`. Reuse the existing provider-neutral structured gateway with the offline deterministic default; permit `deepseek-v4-pro` only through the existing environment-selected profile.

- [ ] **Step 4: Run assembler and prior capability tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py tests/unit/test_fmea_risk_service.py tests/unit/test_fmea_propagation_review.py tests/unit/test_fmea_review_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit revision assembly**

```powershell
git add fmea_application/revision_assembler.py fmea_application/governance_assistance_service.py fmea_infrastructure/governance_assistance_generator.py fmea_application/ports.py fmea_infrastructure/composition.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py
git commit -m "feat(fmea): assemble publication ready revisions"
```

### Task 3: Persist revisions, approval lifecycle, publications, withdrawals, supersession, snapshots, and outbox

**Files:**
- Create: `fmea_infrastructure/migrations/005_fmea_governance_closure.sql`
- Create: `fmea_infrastructure/governance_repository_sqlite.py`
- Modify: `fmea_application/ports.py`
- Test: `tests/unit/test_fmea_governance_repository_contract.py`
- Test: `tests/integration/test_fmea_governance_sqlite.py`
- Test: `tests/regression/test_fmea_governance_idempotency.py`

**Interfaces:**
- Consumes: Task 1 contracts and shared strict SQLite codecs/outbox/idempotency.
- Produces: atomic storage and exact replay for assembly, approval, publication, withdrawal, and supersession.

- [ ] **Step 1: Write atomic publication and immutability tests**

```python
def test_publication_commits_manifest_snapshot_audit_and_outbox_atomically(repository):
    prepared = prepared_publication()
    result = repository.commit_publication(prepared)
    assert result.manifest.revision_hash == prepared.revision.revision_hash
    assert result.publication.manifest_hash == result.manifest.manifest_hash
    assert result.snapshot.snapshot_hash == prepared.expected_snapshot_hash
    assert repository.replay_publication(prepared.scope, prepared.payload_hash) == result


def test_published_payload_cannot_be_updated_or_deleted(repository, database_path):
    result = repository.commit_publication(prepared_publication())
    with pytest.raises(sqlite3.IntegrityError, match="immutable fmea_publications"):
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE fmea_publications SET revision_hash=? WHERE publication_id=?",
                ("f" * 64, result.publication.publication_id),
            )


def test_same_idempotency_key_with_different_payload_is_rejected(repository):
    first = prepared_approval_submission(idempotency_key=UUID1, revision_hash="a" * 64)
    repository.commit_approval_submission(first)
    second = prepared_approval_submission(idempotency_key=UUID1, revision_hash="b" * 64)
    with pytest.raises(ReviewError, match="FMEA_IDEMPOTENCY_CONFLICT"):
        repository.commit_approval_submission(second)


def test_supersession_preserves_both_publications(repository):
    old, replacement = persisted_publication_pair(repository)
    repository.commit_supersession(prepared_supersession(old, replacement))
    assert repository.get_publication(old.publication_id, old.workspace_id) == old
    assert repository.get_publication(replacement.publication_id, replacement.workspace_id) == replacement
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py -q`

Expected: FAIL because migration `005` and repository are absent.

- [ ] **Step 3: Add additive schema and repository**

Migration `005` creates immutable revision candidates, readiness reports, approval submissions, approval decisions, approval withdrawals, publication manifests, published revisions, normalized snapshots, publication withdrawals, supersession links, export-eligibility records, and indexes. It reuses the existing `fmea_audit_events`, `fmea_outbox_events`, and canonical idempotency chain instead of creating parallel audit/outbox tables. Every authority table has workspace-qualified foreign keys and no-update/no-delete triggers. The legacy `fmea_rows.publication_status` CHECK is left untouched because governance never mutates row publication state; revision publication tables carry the Phase 3 lifecycle.

```python
class GovernanceRepository(Protocol):
    def replay_revision(self, scope: IdempotencyScope, payload_hash: str) -> RevisionResult | None: ...
    def commit_revision(self, prepared: PreparedRevision) -> RevisionResult: ...
    def get_revision(self, revision_id: str, workspace_id: str) -> FmeaRevision | None: ...
    def replay_approval_submission(
        self, scope: IdempotencyScope, payload_hash: str
    ) -> ApprovalSubmissionResult | None: ...
    def commit_approval_submission(self, prepared: PreparedApprovalSubmission) -> ApprovalSubmissionResult: ...
    def replay_approval_decision(self, scope: IdempotencyScope, payload_hash: str) -> ApprovalResult | None: ...
    def commit_approval(self, prepared: PreparedApproval) -> ApprovalResult: ...
    def replay_approval_withdrawal(
        self, scope: IdempotencyScope, payload_hash: str
    ) -> ApprovalWithdrawalResult | None: ...
    def commit_approval_withdrawal(self, prepared: PreparedApprovalWithdrawal) -> ApprovalWithdrawalResult: ...
    def replay_publication(self, scope: IdempotencyScope, payload_hash: str) -> PublicationResult | None: ...
    def commit_publication(self, prepared: PreparedPublication) -> PublicationResult: ...
    def replay_publication_withdrawal(
        self, scope: IdempotencyScope, payload_hash: str
    ) -> PublicationWithdrawalResult | None: ...
    def commit_publication_withdrawal(
        self, prepared: PreparedPublicationWithdrawal
    ) -> PublicationWithdrawalResult: ...
    def replay_supersession(self, scope: IdempotencyScope, payload_hash: str) -> SupersessionResult | None: ...
    def commit_supersession(self, prepared: PreparedSupersession) -> SupersessionResult: ...
    def get_publication(self, publication_id: str, workspace_id: str) -> PublishedRevision | None: ...
    def get_snapshot(self, publication_id: str, workspace_id: str) -> NormalizedFmeaSnapshot | None: ...
    def list_approval_events(self, query: GovernanceHistoryQuery) -> GovernanceHistoryPage: ...
    def list_publication_events(self, query: GovernanceHistoryQuery) -> GovernanceHistoryPage: ...
```

Store canonical payload plus hash for every immutable object. Verify approval-revision binding, publication-approval binding, same-workspace analysis lineage, replacement publication existence, and no supersession cycle again inside the transaction. Idempotency scope is `(workspace_id, actor_id, resource_type, resource_id, action, canonical_uuid_key)`; same scope/key with a different canonical payload hash fails closed. Use separate event types `revision.assembled`, `approval.submitted`, `approval.approved`, `approval.rejected`, `approval.withdrawn`, `publication.published`, `publication.withdrawn`, and `publication.superseded`. Repository fault injection must prove revision/decision/manifest/snapshot/audit/outbox/idempotency writes roll back as one unit.

- [ ] **Step 4: Run governance, risk, propagation, and review persistence tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q`

Expected: PASS.

- [ ] **Step 5: Commit governance persistence**

```powershell
git add fmea_infrastructure/migrations/005_fmea_governance_closure.sql fmea_infrastructure/governance_repository_sqlite.py fmea_application/ports.py tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py
git commit -m "feat(fmea): persist immutable governance lifecycle"
```

### Task 4: Implement human submission, approval, publication, withdrawal, and supersession service

**Files:**
- Create: `fmea_application/governance_service.py`
- Modify: `fmea_application/service_factory.py`
- Modify: `fmea_infrastructure/composition.py`
- Modify: `fmea_infrastructure/local_auth.py`
- Test: `tests/unit/test_fmea_governance_service.py`
- Test: `tests/unit/test_fmea_governance_authority.py`
- Test: `tests/integration/test_fmea_governance_lifecycle.py`

**Interfaces:**
- Consumes: assembler, readiness policy, governance repository, and existing actor context.
- Produces: assemble, approve, reject, publish, withdraw, supersede, and query methods.

- [ ] **Step 1: Write authority and stale-binding tests**

```python
def test_model_actor_cannot_approve_or_publish(service):
    model_actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())
    with pytest.raises(ReviewError, match="FMEA_GOVERNANCE_APPROVAL_FORBIDDEN"):
        service.approve(make_approval_command(), model_actor)
    with pytest.raises(ReviewError, match="FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN"):
        service.publish(make_publish_command(), model_actor)


def test_content_change_after_approval_requires_new_approval(service, approver, publisher):
    approved = service.approve(make_approval_command(revision_hash="a" * 64), approver)
    with pytest.raises(ReviewError, match="FMEA_GOVERNANCE_APPROVAL_STALE"):
        service.publish(
            make_publish_command(revision_hash="b" * 64, approval_id=approved.approval_id),
            publisher,
        )


def test_approver_cannot_publish_without_publisher_role(service):
    actor = make_governance_actor(roles={"approver"})
    with pytest.raises(ReviewError, match="FMEA_PUBLICATION_FORBIDDEN"):
        service.publish(make_publish_command(), actor)


def test_supersession_requires_published_child_of_same_analysis(service, publisher):
    with pytest.raises(ReviewError, match="FMEA_SUPERSESSION_INVALID"):
        service.supersede(make_cross_analysis_supersession_command(), publisher)
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_service.py tests/unit/test_fmea_governance_authority.py tests/integration/test_fmea_governance_lifecycle.py -q`

Expected: FAIL because service and roles are absent.

- [ ] **Step 3: Implement governance orchestration and explicit roles**

```python
class RevisionGovernanceService:
    def assemble(self, command: AssembleRevisionCommand, actor: ActorContext) -> RevisionResult: ...
    def readiness(self, revision_id: str, actor: ActorContext) -> PublicationReadinessReport: ...
    def submit_for_approval(self, command: SubmitApprovalCommand, actor: ActorContext) -> ApprovalSubmissionResult: ...
    def approve(self, command: ApprovalCommand, actor: ActorContext) -> ApprovalResult: ...
    def reject(self, command: ApprovalRejectionCommand, actor: ActorContext) -> ApprovalResult: ...
    def withdraw_approval(self, command: WithdrawApprovalCommand, actor: ActorContext) -> ApprovalWithdrawalResult: ...
    def publish(self, command: PublishCommand, actor: ActorContext) -> PublicationResult: ...
    def withdraw_publication(
        self, command: WithdrawPublicationCommand, actor: ActorContext
    ) -> PublicationWithdrawalResult: ...
    def supersede(self, command: SupersedePublicationCommand, actor: ActorContext) -> SupersessionResult: ...
    def get_revision(self, revision_id: str, actor: ActorContext) -> FmeaRevision: ...
    def get_publication(self, publication_id: str, actor: ActorContext) -> PublicationLifecycleView: ...
    def get_snapshot(self, publication_id: str, actor: ActorContext) -> NormalizedFmeaSnapshot: ...
    def list_approval_events(self, query: GovernanceHistoryQuery, actor: ActorContext) -> GovernanceHistoryPage: ...
    def list_publication_events(self, query: GovernanceHistoryQuery, actor: ActorContext) -> GovernanceHistoryPage: ...
```

Local dev auth returns a human actor with explicit `reviewer`, `risk_reviewer`, `propagation_reviewer`, `approver`, and `publisher` roles only when the existing loopback simple-account mode is enabled. This is convenience identity, not collapsed authority: submission requires reviewer authority, approval/rejection/approval-withdrawal requires `approver`, and publication/withdrawal/supersession requires `publisher`. Model and system actors cannot perform these commands. Transport confirmation booleans are validated before service invocation, while the application service independently enforces actor type, role, workspace, expected record version, and revision hash.

Approval operates only on a current `PENDING` submission and appends a decision. Publish requires one current `APPROVED` decision for the exact revision hash, re-runs readiness against server-loaded inputs, rejects stale child identities, builds the normalized snapshot deterministically, and commits once. Withdrawal never permits subsequent republish of the same publication ID. Supersession requires an already published replacement whose revision descends from the old revision, belongs to the same workspace/analysis, and is not withdrawn; it appends one acyclic old-to-new link and leaves both publication payloads immutable.

Publication construction has a non-circular hash order: derive stable publication/manifest/snapshot IDs from the idempotency scope; hash the normalized snapshot; hash the manifest with the previous audit-chain head; hash the publication audit event containing revision, approval, snapshot, and manifest hashes; then store the resulting audit-chain head on `PublishedRevision` and bind the outbox payload to those final hashes. The repository recomputes this order inside the transaction before inserting anything.

Required stable codes are: `FMEA_GOVERNANCE_REVISION_NOT_FOUND`, `FMEA_GOVERNANCE_REVISION_STALE`, `FMEA_GOVERNANCE_NOT_READY`, `FMEA_GOVERNANCE_ACTIVE_RUN`, `FMEA_GOVERNANCE_APPROVAL_NOT_FOUND`, `FMEA_GOVERNANCE_APPROVAL_STATE_INVALID`, `FMEA_GOVERNANCE_APPROVAL_STALE`, `FMEA_GOVERNANCE_APPROVAL_FORBIDDEN`, `FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN`, `FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID`, `FMEA_GOVERNANCE_SUPERSESSION_INVALID`, `FMEA_GOVERNANCE_VERSION_CONFLICT`, `FMEA_GOVERNANCE_IDEMPOTENCY_CONFLICT`, `FMEA_GOVERNANCE_CURSOR_INVALID`, `FMEA_GOVERNANCE_STORAGE_UNAVAILABLE`, and `FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID`. Transport confirmation failures add `FMEA_GOVERNANCE_APPROVAL_CONFIRMATION_REQUIRED`, `FMEA_GOVERNANCE_PUBLICATION_CONFIRMATION_REQUIRED`, `FMEA_GOVERNANCE_WITHDRAWAL_CONFIRMATION_REQUIRED`, and `FMEA_GOVERNANCE_SUPERSESSION_CONFIRMATION_REQUIRED`. They map through the existing stable problem envelope and never expose local paths, SQL, private evidence, prompts, raw model output, or provider errors.

- [ ] **Step 4: Run lifecycle and existing authority regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_service.py tests/unit/test_fmea_governance_authority.py tests/integration/test_fmea_governance_lifecycle.py tests/unit/test_fmea_local_auth.py tests/unit/test_fmea_review_service.py tests/unit/test_fmea_risk_service.py tests/unit/test_fmea_propagation_review.py -q`

Expected: PASS.

- [ ] **Step 5: Commit governance service**

```powershell
git add fmea_application/governance_service.py fmea_application/service_factory.py fmea_infrastructure/composition.py fmea_infrastructure/local_auth.py tests/unit/test_fmea_governance_service.py tests/unit/test_fmea_governance_authority.py tests/integration/test_fmea_governance_lifecycle.py tests/unit/test_fmea_local_auth.py
git commit -m "feat(fmea): govern approval and publication"
```

### Task 5: Publish governance REST and CLI contracts

**Files:**
- Create: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_governance_contracts.py`
- Create: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_governance_v1.py`
- Modify: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py`
- Modify: `scripts/fmea_skill.py`
- Test: `tests/unit/test_fmea_governance_api_contracts.py`
- Test: `tests/integration/test_fmea_governance_api_v1.py`
- Test: `tests/integration/test_fmea_governance_cli.py`

**Interfaces:**
- Consumes: `RevisionGovernanceService` and `GovernanceAssistanceService`.
- Produces: matching REST/CLI revision, deterministic readiness, readiness-suggestion, approval, publication, withdrawal, and snapshot resources.

- [ ] **Step 1: Write explicit-confirmation and transport-parity tests**

```python
def test_publish_requires_explicit_confirmation(client):
    response = client.post(
        "/api/v1/fmea/revisions/rev-1/publications",
        headers={"If-Match": '"1"', "Idempotency-Key": UUID1},
        json={"approval_id": "approval-1", "confirm_publication": False},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FMEA_GOVERNANCE_PUBLICATION_CONFIRMATION_REQUIRED"


def test_cli_snapshot_matches_rest(client, invoke_cli):
    assert invoke_cli("publication", "snapshot", "--publication-id", "pub-1")["data"] == get_snapshot(client)["data"]


def test_readiness_suggestion_does_not_change_deterministic_report(client):
    before = client.get("/api/v1/fmea/revisions/rev-1/readiness").json()["data"]
    suggested = client.post("/api/v1/fmea/revisions/rev-1/readiness-suggestion-runs", json={})
    assert suggested.status_code == 202
    assert suggested.json()["data"]["applied"] is False
    assert client.get("/api/v1/fmea/revisions/rev-1/readiness").json()["data"] == before


def test_history_cursor_is_bound_to_workspace_and_resource(client, signed_cursor):
    response = client.get(
        "/api/v1/fmea/revisions/rev-2/approval-events",
        headers=workspace_headers("ws-2"),
        params={"cursor": signed_cursor(workspace_id="ws-1", resource_id="rev-1")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "FMEA_GOVERNANCE_CURSOR_INVALID"
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_api_contracts.py tests/integration/test_fmea_governance_api_v1.py tests/integration/test_fmea_governance_cli.py -q`

Expected: FAIL because transports are absent.

- [ ] **Step 3: Add strict REST resources and CLI groups**

REST resources:

```text
POST /api/v1/fmea/analyses/{analysis_id}/revisions
GET  /api/v1/fmea/revisions/{revision_id}
GET  /api/v1/fmea/revisions/{revision_id}/readiness
POST /api/v1/fmea/revisions/{revision_id}/readiness-suggestion-runs
POST /api/v1/fmea/revisions/{revision_id}/approval-submissions
POST /api/v1/fmea/approval-submissions/{submission_id}/approvals
POST /api/v1/fmea/approval-submissions/{submission_id}/rejections
POST /api/v1/fmea/approvals/{approval_id}/withdrawals
GET  /api/v1/fmea/revisions/{revision_id}/approval-events
POST /api/v1/fmea/revisions/{revision_id}/publications
GET  /api/v1/fmea/publications/{publication_id}
GET  /api/v1/fmea/publications/{publication_id}/snapshot
POST /api/v1/fmea/publications/{publication_id}/withdrawals
POST /api/v1/fmea/publications/{publication_id}/supersessions
GET  /api/v1/fmea/publications/{publication_id}/lifecycle-events
```

CLI groups mirror each command, including `revision assemble/show/readiness`, `approval readiness-suggest/submit/approve/reject/withdraw/history`, and `publication publish/show/snapshot/withdraw/supersede/history`. Require `--confirm-human-approval`, `--confirm-publication`, `--confirm-approval-withdrawal`, `--confirm-publication-withdrawal`, or `--confirm-supersession` for authority-bearing writes. Start/authority DTOs do not accept topology, DomainPack, rule-pack, EvidencePack, snapshot-path, or model-provider overrides; those identities come from server-owned revision state.

Use one bounded JSON envelope, ETags, canonical UUID idempotency keys, stable problem details, and nonzero CLI exits for failed runs or commands. Approval/publication history uses signed cursors bound to workspace, resource type, resource ID, sort direction, page size, and filter hash; REST and CLI expose the same ordering and page contract. No transport reads SQLite directly, and response DTOs serialize only projection-safe snapshot or lifecycle data.

- [ ] **Step 4: Run governance and prior transport matrices**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_api_contracts.py tests/integration/test_fmea_governance_api_v1.py tests/integration/test_fmea_governance_cli.py tests/integration/test_fmea_propagation_api_v1.py tests/integration/test_fmea_risk_api_v1.py tests/integration/test_fmea_review_api_v1.py -q`

Expected: PASS.

- [ ] **Step 5: Commit governance transports**

```powershell
git add api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_governance_contracts.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_governance_v1.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py scripts/fmea_skill.py tests/unit/test_fmea_governance_api_contracts.py tests/integration/test_fmea_governance_api_v1.py tests/integration/test_fmea_governance_cli.py
git commit -m "feat(fmea): expose governance interfaces"
```

### Task 6: Close governance acceptance, replay, and security gates

**Files:**
- Create: `examples/fmea/governance/fuel-combustion/`
- Create: `scripts/run_fmea_governance_acceptance.py`
- Create: `scripts/verify_fmea_governance_acceptance.py`
- Create: `tests/integration/test_fmea_governance_acceptance.py`
- Create: `tests/regression/test_fmea_governance_security.py`
- Create: `tests/regression/test_fmea_governance_atomic_publish.py`
- Create: `docs/handoff/fmea-governance-closure.md`

**Interfaces:**
- Consumes: all Phase 3 resources.
- Produces: `graphrag.fmea.governance.acceptance.v1` canonical artifacts.

- [ ] **Step 1: Write end-to-end lifecycle and tamper tests**

```python
def test_acceptance_publishes_with_human_actors_and_replays_withdrawal(run_acceptance):
    summary = run_acceptance()
    assert summary["approval_actor_type"] == "human"
    assert summary["publisher_actor_type"] == "human"
    assert summary["model_publication_count"] == 0
    assert summary["withdrawn_publication_retained"] is True


def test_verifier_rejects_snapshot_hash_mismatch(tampered_acceptance):
    tampered_acceptance.snapshot["rows"][0]["failure_mode"] = "tampered"
    assert verify(tampered_acceptance).error_code == "FMEA_SNAPSHOT_HASH_MISMATCH"


def test_acceptance_preserves_all_upstream_evidence_profiles(run_acceptance):
    summary = run_acceptance()
    assert summary["profile_cases"] == {
        "rag_only": ["text"],
        "graphrag_only": ["graph", "community"],
        "combined": ["text", "graph", "community"],
        "auto": ["text", "graph", "community"],
    }


def test_replace_failure_keeps_previous_latest(monkeypatch, acceptance_root):
    previous = run_acceptance(output_root=acceptance_root)
    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        run_acceptance(output_root=acceptance_root)
    assert verify_latest(acceptance_root).artifact_id == previous.artifact_id


def test_ten_thousand_row_snapshot_is_streamable_and_bounded(make_large_revision):
    source = make_normalized_snapshot_input(revision=make_large_revision(row_count=10_000))
    snapshot = build_normalized_snapshot(source)
    pages = tuple(iter_normalized_snapshot_pages(snapshot, page_size=250))
    assert snapshot.row_count == 10_000
    assert max(len(page.rows) for page in pages) == 250
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_acceptance.py tests/regression/test_fmea_governance_security.py -q`

Expected: FAIL because acceptance assets are absent.

- [ ] **Step 3: Implement atomic runner, independent verifier, and handoff**

The runner assembles, checks readiness, submits approval, approves, publishes, replays duplicate commands, creates a changed child revision, proves the parent approval is stale for that child, obtains a new approval, publishes the child, supersedes the parent publication, and withdraws a publication while retaining every immutable payload. It uses deterministic offline assistance only and exercises `rag_only`, `graphrag_only`, `combined`, and `auto -> combined` provenance without calling retrieval. The 10,000-row synthetic case validates bounded page iteration and snapshot hashing without embedding all rows in REST/CLI responses.

The verifier is independent: it does not import runner validation functions. It reads raw bytes, rejects duplicate keys/non-canonical JSON/non-finite numbers/extra or missing files, recomputes revision/manifest/snapshot/audit/outbox hashes, validates human actors, role separation, state order, ETags, idempotent replay, approval staleness, supersession acyclicity, retained withdrawn payloads, server-owned resource identities, and private-marker absence. Acceptance output uses a contained unique temporary directory, completes full verification before atomic publication, and updates `latest` only after success. Tests inject failures after partial writes and around `os.replace`, verify temporary cleanup, and prove the prior latest artifact remains selected. Windows symlink/reparse tests may skip only on explicit privilege failure and must have a deterministic component-walk test that runs unprivileged.

- [ ] **Step 4: Run the complete Phase 3 gate**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py tests/unit/test_fmea_governance_repository_contract.py tests/unit/test_fmea_governance_service.py tests/unit/test_fmea_governance_authority.py tests/unit/test_fmea_governance_api_contracts.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_governance_lifecycle.py tests/integration/test_fmea_governance_api_v1.py tests/integration/test_fmea_governance_cli.py tests/integration/test_fmea_governance_acceptance.py tests/regression/test_fmea_governance_idempotency.py tests/regression/test_fmea_governance_security.py -q
.venv\Scripts\python.exe -m pytest tests/regression/test_fmea_governance_atomic_publish.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_review_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_review_api_v1.py tests/integration/test_fmea_risk_api_v1.py tests/integration/test_fmea_propagation_api_v1.py -q
.venv\Scripts\python.exe scripts/run_fmea_governance_acceptance.py
.venv\Scripts\python.exe scripts/verify_fmea_governance_acceptance.py --latest
.venv\Scripts\python.exe -m compileall -q core_domain fmea_application fmea_infrastructure scripts api_server/current_console/chroma_rag_poc/src/chroma_rag_poc
.venv\Scripts\ruff.exe check core_domain/fmea fmea_application fmea_infrastructure api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_governance_contracts.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_governance_v1.py scripts/fmea_skill.py scripts/run_fmea_governance_acceptance.py scripts/verify_fmea_governance_acceptance.py tests/unit/test_fmea_governance*.py tests/integration/test_fmea_governance*.py tests/regression/test_fmea_governance*.py
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 5: Commit Phase 3 acceptance**

```powershell
git add examples/fmea/governance/fuel-combustion scripts/run_fmea_governance_acceptance.py scripts/verify_fmea_governance_acceptance.py tests/integration/test_fmea_governance_acceptance.py tests/regression/test_fmea_governance_security.py tests/regression/test_fmea_governance_atomic_publish.py docs/handoff/fmea-governance-closure.md
git commit -m "test(fmea): close governance workflow acceptance"
```

## Phase 3 completion checklist

- [ ] Complete revisions are deterministic, hash-bound, and readiness-checked.
- [ ] Revision assembly consumes accepted review, confirmed risk, confirmed propagation, server-owned manifests, and immutable EvidencePack provenance without reconnecting to RAG or GraphRAG.
- [ ] Approval submission, approval decision, approval withdrawal, publication, publication withdrawal, and supersession are distinct authority commands and audit events.
- [ ] Human approval binds one exact revision and cannot be reused for a changed child.
- [ ] Publication atomically stores manifest, snapshot, audit, idempotency, and outbox.
- [ ] Withdrawal and supersession preserve all prior immutable payloads; supersession is an acyclic old-to-new publication link.
- [ ] Model actors cannot perform any authority transition.
- [ ] REST/CLI have server-owned resource identities, explicit confirmation, ETag/idempotency parity, tenant-bound pagination, and nonzero failure exits.
- [ ] Independent acceptance proves replay, hash consistency, atomic latest publication, tamper rejection, retrieval-profile preservation, and a bounded 10,000-row normalized snapshot.
- [ ] No Phase 4 template import, XLSX/DOCX generation, browser UI, or migration workflow has leaked into Phase 3.
