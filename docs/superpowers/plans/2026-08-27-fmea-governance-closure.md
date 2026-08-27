# FMEA Governance Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assemble complete FMEA revisions and add human approval, immutable publication, withdrawal, supersession, normalized snapshots, audit, and outbox replay.

**Architecture:** A new `RevisionGovernanceService` composes accepted rows, confirmed risk records, confirmed propagation graphs, evidence and version manifests into an immutable revision candidate. Approval binds to the exact revision hash. Publication atomically stores the approved revision, publication manifest, canonical normalized snapshot, audit event, idempotency response, and outbox event; withdrawal and supersession are additive events.

**Tech Stack:** Python 3.11+, frozen dataclasses, Enum, Protocol, Pydantic 2.13, FastAPI, SQLite, orjson, SHA-256 canonical serialization, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-27-full-fmea-modular-product-design.md`

## Global Constraints

- Risk and propagation closure phases are complete and expose stable query contracts.
- Review, risk, propagation, approval, and publication states remain orthogonal.
- Model actors cannot approve, publish, withdraw, supersede, or alter readiness policy.
- The initial local account may hold reviewer, risk reviewer, propagation reviewer, approver, and publisher roles, but every authority command remains separate.
- Approval binds to one immutable revision hash; any child change requires a new approval.
- Published revisions and manifests are immutable and never deleted or updated in place.
- Withdrawal and supersession append records and preserve the original publication payload and audit chain.
- All writes require canonical UUID idempotency keys, optimistic preconditions, workspace isolation, and atomic audit/outbox records.
- JSON stored for revisions, manifests, snapshots, and events is strict, canonical, finite, duplicate-key-free, and hash-verified.
- Existing review REST/CLI and database records remain compatible.

## File map

- `core_domain/fmea/governance.py`: revision, readiness, approval, publication, withdrawal, and manifest contracts.
- `core_domain/fmea/states.py`: additive approval and superseded publication states.
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

---

### Task 1: Freeze revision, readiness, approval, publication, and snapshot contracts

**Files:**
- Create: `core_domain/fmea/governance.py`
- Modify: `core_domain/fmea/states.py`
- Modify: `core_domain/fmea/__init__.py`
- Create: `fmea_application/snapshot_contracts.py`
- Create: `fmea_application/governance_contracts.py`
- Test: `tests/unit/test_fmea_governance_contracts.py`
- Test: `tests/unit/test_fmea_snapshot_contracts.py`

**Interfaces:**
- Consumes: accepted `FmeaRow`, confirmed `RiskAssessmentRecord`, confirmed `PropagationGraphRevision`, EvidencePacks, DomainPack, and version identities.
- Produces: `ApprovalStatus`, `FmeaRevision`, `ReadinessIssue`, `ApprovalDecision`, `PublicationManifest`, `PublishedRevision`, `WithdrawalRecord`, `NormalizedFmeaSnapshot`.

- [ ] **Step 1: Write immutable contract and hash tests**

```python
def test_approval_decision_binds_exact_revision_hash():
    decision = approval_decision(revision_hash="a" * 64)
    with pytest.raises(FmeaDomainError, match="approval revision hash mismatch"):
        validate_approval_binding(decision, fmea_revision(revision_hash="b" * 64))


def test_normalized_snapshot_rejects_different_publication_revision():
    with pytest.raises(FmeaDomainError, match="snapshot publication binding"):
        normalized_snapshot(revision_id="rev-1", publication_revision_id="rev-2")
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


@dataclass(frozen=True, slots=True)
class FmeaRevision:
    revision_id: str
    workspace_id: str
    analysis_id: str
    parent_revision_id: str | None
    row_versions: tuple[tuple[str, int, str], ...]
    risk_versions: tuple[tuple[str, int, str], ...]
    propagation_graph_revision_id: str | None
    evidence_pack_hashes: tuple[tuple[str, str], ...]
    domain_pack_identity: tuple[str, str, str]
    template_identities: tuple[tuple[str, str, str], ...]
    scoring_rule_identities: tuple[tuple[str, str, str], ...]
    propagation_rule_identity: tuple[str, str, str] | None
    unresolved_items: tuple[ReadinessIssue, ...]
    revision_hash: str
    created_at: str
```

Add `PublicationStatus.SUPERSEDED`. Canonicalize sorted identities and records with orjson, reject non-finite values and duplicate identities, and verify all supplied hashes. `NormalizedFmeaSnapshot` contains only bounded, export-safe semantic data and no credentials, prompts, private paths, or raw provider output.

- [ ] **Step 4: Run governance, snapshot, and existing codec tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_review_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit governance contracts**

```powershell
git add core_domain/fmea/governance.py core_domain/fmea/states.py core_domain/fmea/__init__.py fmea_application/snapshot_contracts.py fmea_application/governance_contracts.py tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py
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
- Consumes: repository query ports for rows, source packs, risk, propagation, decisions, DomainPack, templates, and rules.
- Produces: `RevisionAssembler.assemble()`, `PublicationReadinessPolicy.evaluate()`, and immutable model-assisted readiness checklists that cannot change deterministic readiness.

- [ ] **Step 1: Write complete and blocked-readiness tests**

```python
def test_revision_assembler_is_order_independent():
    first = assembler(rows=(row_b(), row_a())).assemble(request())
    second = assembler(rows=(row_a(), row_b())).assemble(request())
    assert first.revision_hash == second.revision_hash


def test_high_risk_unresolved_propagation_blocks_approval():
    revision = revision_with(issue(code="PROPAGATION_HIGH_RISK_UNRESOLVED", severity="critical"))
    report = PublicationReadinessPolicy(domain_pack()).evaluate(revision)
    assert not report.ready
    assert report.blocking_codes == ("PROPAGATION_HIGH_RISK_UNRESOLVED",)


def test_model_readiness_checklist_cannot_clear_a_blocker(assistance_service):
    report = blocked_readiness_report()
    suggestion = assistance_service.suggest_readiness_checklist(report, model_actor())
    assert suggestion.kind is AssistanceKind.APPROVAL_READINESS_CHECKLIST
    assert suggestion.applied is False
    assert report.ready is False
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py -q`

Expected: FAIL because assembler and policy are absent.

- [ ] **Step 3: Implement deterministic assembly and readiness**

```python
class GovernanceSourcePort(Protocol):
    def list_revision_rows(self, analysis_id: str, workspace_id: str) -> tuple[FmeaRow, ...]: ...
    def list_confirmed_risk(self, analysis_id: str, workspace_id: str) -> tuple[RiskAssessmentRecord, ...]: ...
    def get_confirmed_propagation(self, analysis_id: str, workspace_id: str) -> PropagationGraphRevision | None: ...
    def load_evidence_packs(self, pack_ids: tuple[str, ...], workspace_id: str) -> tuple[EvidencePack, ...]: ...


class RevisionAssembler:
    def assemble(self, request: AssembleRevisionRequest) -> FmeaRevision: ...


class PublicationReadinessPolicy:
    def evaluate(self, revision: FmeaRevision) -> PublicationReadinessReport: ...


class GovernanceAssistanceService:
    def suggest_readiness_checklist(
        self, report: PublicationReadinessReport, actor: ActorContext
    ) -> AssistanceSuggestion[ReadinessChecklistDraft]: ...
```

Sort rows and identities canonically. Reject non-accepted required rows, stale/invalidated risk, stale/invalidated propagation, unresolved version/hash identities, active mutating runs, missing required evidence, and unacknowledged critical issues. Preserve human acknowledgements in the revision and later publication manifest; do not erase them to obtain readiness. Run deterministic readiness first; the optional model receives the immutable report and bounded evidence only, returns the shared `AssistanceSuggestion` envelope, and cannot add/remove blockers or set `ready`. Reuse the existing Flash plus `deepseek-v4-pro` pipeline profile.

- [ ] **Step 4: Run assembler and prior capability tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py tests/unit/test_fmea_risk_service.py tests/unit/test_fmea_propagation_review.py tests/unit/test_fmea_review_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit revision assembly**

```powershell
git add fmea_application/revision_assembler.py fmea_application/governance_assistance_service.py fmea_infrastructure/governance_assistance_generator.py fmea_application/ports.py fmea_infrastructure/composition.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py
git commit -m "feat(fmea): assemble publication ready revisions"
```

### Task 3: Persist revisions, approvals, publications, withdrawals, snapshots, and outbox

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
    assert result.publication.manifest.revision_hash == prepared.revision.revision_hash
    assert result.snapshot.snapshot_hash == prepared.expected_snapshot_hash
    assert repository.replay_publication(prepared.scope, prepared.payload_hash) == result


def test_published_payload_cannot_be_updated_or_deleted(repository):
    published = repository.commit_publication(prepared_publication())
    with pytest.raises(sqlite3.IntegrityError, match="immutable fmea_publications"):
        repository.raw_update_publication_for_test(published.publication.publication_id)
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py -q`

Expected: FAIL because migration `005` and repository are absent.

- [ ] **Step 3: Add additive schema and repository**

Migration `005` creates immutable revision candidates, readiness reports, approval decisions, publication manifests, published revisions, normalized snapshots, withdrawals, supersession links, and indexes. It adds no-update/no-delete triggers to approvals, publications, snapshots, withdrawals, and supersession links.

```python
class GovernanceRepository(Protocol):
    def save_revision(self, prepared: PreparedRevision) -> FmeaRevision: ...
    def get_revision(self, revision_id: str, workspace_id: str) -> FmeaRevision | None: ...
    def replay_approval(self, scope: IdempotencyScope, payload_hash: str) -> ApprovalResult | None: ...
    def commit_approval(self, prepared: PreparedApproval) -> ApprovalResult: ...
    def replay_publication(self, scope: IdempotencyScope, payload_hash: str) -> PublicationResult | None: ...
    def commit_publication(self, prepared: PreparedPublication) -> PublicationResult: ...
    def commit_withdrawal(self, prepared: PreparedWithdrawal) -> WithdrawalResult: ...
    def get_snapshot(self, publication_id: str, workspace_id: str) -> NormalizedFmeaSnapshot | None: ...
```

Store canonical payload plus hash for every immutable object. Verify approval-revision binding and publication-approval binding again inside the transaction. Use separate event types `revision.assembled`, `approval.approved`, `approval.rejected`, `publication.published`, `publication.withdrawn`, and `publication.superseded`.

- [ ] **Step 4: Run governance, risk, propagation, and review persistence tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q`

Expected: PASS.

- [ ] **Step 5: Commit governance persistence**

```powershell
git add fmea_infrastructure/migrations/005_fmea_governance_closure.sql fmea_infrastructure/governance_repository_sqlite.py fmea_application/ports.py tests/unit/test_fmea_governance_repository_contract.py tests/integration/test_fmea_governance_sqlite.py tests/regression/test_fmea_governance_idempotency.py
git commit -m "feat(fmea): persist immutable governance lifecycle"
```

### Task 4: Implement human approval, publication, withdrawal, and supersession service

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
def test_model_actor_cannot_approve_or_publish(service, model_actor):
    with pytest.raises(ReviewError, match="FMEA_HUMAN_APPROVAL_REQUIRED"):
        service.approve(approve_command(), model_actor)
    with pytest.raises(ReviewError, match="FMEA_HUMAN_PUBLICATION_REQUIRED"):
        service.publish(publish_command(), model_actor)


def test_content_change_after_approval_requires_new_approval(service, approver, publisher):
    approved = service.approve(approve_command(revision_hash="a" * 64), approver)
    with pytest.raises(ReviewError, match="FMEA_APPROVAL_STALE"):
        service.publish(publish_command(revision_hash="b" * 64, approval_id=approved.approval_id), publisher)
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_service.py tests/unit/test_fmea_governance_authority.py tests/integration/test_fmea_governance_lifecycle.py -q`

Expected: FAIL because service and roles are absent.

- [ ] **Step 3: Implement governance orchestration and explicit roles**

```python
class RevisionGovernanceService:
    def assemble(self, command: AssembleRevisionCommand, actor: ActorContext) -> RevisionResult: ...
    def readiness(self, revision_id: str, actor: ActorContext) -> PublicationReadinessReport: ...
    def approve(self, command: ApprovalCommand, actor: ActorContext) -> ApprovalResult: ...
    def reject(self, command: ApprovalRejectionCommand, actor: ActorContext) -> ApprovalResult: ...
    def publish(self, command: PublishCommand, actor: ActorContext) -> PublicationResult: ...
    def withdraw(self, command: WithdrawPublicationCommand, actor: ActorContext) -> WithdrawalResult: ...
    def supersede(self, command: SupersedePublicationCommand, actor: ActorContext) -> SupersessionResult: ...
```

Local dev auth returns a human actor with explicit `reviewer`, `risk_reviewer`, `propagation_reviewer`, `approver`, and `publisher` roles when enabled. Each method requires its own role and explicit confirmation flag at transport boundaries. Publish re-runs readiness and all hash bindings inside the command, builds the normalized snapshot deterministically, and commits once.

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
    assert response.json()["error"]["code"] == "FMEA_PUBLICATION_CONFIRMATION_REQUIRED"


def test_cli_snapshot_matches_rest(client, invoke_cli):
    assert invoke_cli("publication", "snapshot", "--publication-id", "pub-1")["data"] == get_snapshot(client)["data"]


def test_readiness_suggestion_does_not_change_deterministic_report(client):
    before = client.get("/api/v1/fmea/revisions/rev-1/readiness").json()["data"]
    suggested = client.post("/api/v1/fmea/revisions/rev-1/readiness-suggestion-runs", json={})
    assert suggested.status_code == 202
    assert suggested.json()["data"]["applied"] is False
    assert client.get("/api/v1/fmea/revisions/rev-1/readiness").json()["data"] == before
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
POST /api/v1/fmea/revisions/{revision_id}/approvals
POST /api/v1/fmea/revisions/{revision_id}/approval-rejections
POST /api/v1/fmea/revisions/{revision_id}/publications
GET  /api/v1/fmea/publications/{publication_id}
GET  /api/v1/fmea/publications/{publication_id}/snapshot
POST /api/v1/fmea/publications/{publication_id}/withdrawals
POST /api/v1/fmea/publications/{publication_id}/supersessions
```

CLI groups mirror each command, include `approval readiness-suggest`, and require `--confirm-human-approval`, `--confirm-publication`, or `--confirm-withdrawal` for authority-bearing writes. Keep one bounded JSON envelope, ETags, canonical idempotency keys, pagination for history, and stable problem details.

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
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_governance_acceptance.py tests/regression/test_fmea_governance_security.py -q`

Expected: FAIL because acceptance assets are absent.

- [ ] **Step 3: Implement atomic runner, independent verifier, and handoff**

The runner assembles, checks readiness, approves, publishes, replays duplicate commands, creates a child revision, supersedes, and withdraws while retaining every immutable payload. The verifier independently recomputes revision, manifest, snapshot, audit-chain, and outbox hashes; validates human actors, state order, preconditions, exact replay, no deletes, and private-marker absence; rejects partial or extra files.

- [ ] **Step 4: Run the complete Phase 3 gate**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_governance_contracts.py tests/unit/test_fmea_snapshot_contracts.py tests/unit/test_fmea_revision_assembler.py tests/unit/test_fmea_publication_readiness.py tests/unit/test_fmea_governance_assistance.py tests/unit/test_fmea_governance_repository_contract.py tests/unit/test_fmea_governance_service.py tests/unit/test_fmea_governance_authority.py tests/unit/test_fmea_governance_api_contracts.py tests/integration/test_fmea_governance_sqlite.py tests/integration/test_fmea_governance_lifecycle.py tests/integration/test_fmea_governance_api_v1.py tests/integration/test_fmea_governance_cli.py tests/integration/test_fmea_governance_acceptance.py tests/regression/test_fmea_governance_idempotency.py tests/regression/test_fmea_governance_security.py -q
.venv\Scripts\python.exe scripts/run_fmea_governance_acceptance.py
.venv\Scripts\python.exe scripts/verify_fmea_governance_acceptance.py --latest
.venv\Scripts\python.exe -m compileall -q core_domain fmea_application fmea_infrastructure scripts
.venv\Scripts\ruff.exe check core_domain/fmea fmea_application fmea_infrastructure scripts/fmea_skill.py scripts/run_fmea_governance_acceptance.py scripts/verify_fmea_governance_acceptance.py tests/unit/test_fmea_governance*.py tests/integration/test_fmea_governance*.py tests/regression/test_fmea_governance*.py
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 5: Commit Phase 3 acceptance**

```powershell
git add examples/fmea/governance/fuel-combustion scripts/run_fmea_governance_acceptance.py scripts/verify_fmea_governance_acceptance.py tests/integration/test_fmea_governance_acceptance.py tests/regression/test_fmea_governance_security.py docs/handoff/fmea-governance-closure.md
git commit -m "test(fmea): close governance workflow acceptance"
```

## Phase 3 completion checklist

- [ ] Complete revisions are deterministic, hash-bound, and readiness-checked.
- [ ] Human approval binds one exact revision and cannot be reused for a changed child.
- [ ] Publication atomically stores manifest, snapshot, audit, idempotency, and outbox.
- [ ] Withdrawal and supersession preserve all prior immutable payloads.
- [ ] Model actors cannot perform any authority transition.
- [ ] REST/CLI and independent acceptance prove replay and hash consistency.
