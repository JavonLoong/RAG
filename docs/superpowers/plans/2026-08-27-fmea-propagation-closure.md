# FMEA Propagation Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bounded, topology-constrained, evidence-bound, model-assisted, human-confirmed fault-propagation workflow for fuel and combustion systems.

**Architecture:** Extend the existing `PropagationEdge` policy into immutable graph revisions. Deterministic topology enumeration creates the only legal endpoint candidates; a model may suggest typed edges among them; deterministic validation enforces direction, units, operating modes, timing, barriers, evidence, cycles, and path depth. A dedicated propagation service and repository sit beside risk and review services.

**Tech Stack:** Python 3.11+, frozen dataclasses, Enum, Protocol, NetworkX 3+, Pydantic 2.13, FastAPI, SQLite, orjson, existing structured-generation gateway, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-27-full-fmea-modular-product-design.md`

## Global Constraints

- Phase 1 risk closure is complete and its DomainPack, outbox, actor, idempotency, and SQLite migration contracts are stable.
- Preserve current `PropagationEdge` field order and existing one/two-hop policy behavior unless an additive versioned contract supersedes it.
- A model cannot create endpoints outside the supplied immutable topology snapshot.
- Every edge binds its own evidence; one citation never automatically supports a complete path.
- Default automatic search depth is two hops; long, cyclic, high-risk, external, conflicting, incomplete, or evidence-free paths require human review.
- Propagation never reconnects to RAG/GraphRAG; supplemental evidence arrives as a new EvidencePack with lineage.
- Model actors create proposals only; only a human `propagation_reviewer` confirms edges or graph revisions.
- All writes use canonical idempotency keys, optimistic versions, atomic audit/outbox events, and strict workspace isolation.
- Default tests use deterministic topology and model fakes and incur no external-model cost.

## File map

- `core_domain/fmea/propagation.py`: additive graph/node/path/rule/status contracts and deterministic validation.
- `fmea_application/propagation_contracts.py`: requests, commands, results, and prepared transactions.
- `fmea_application/propagation_service.py`: enumerate, propose, review, confirm, invalidate, and query orchestration.
- `fmea_application/ports.py`: topology, propagation-rule, suggestion, and repository ports.
- `fmea_infrastructure/propagation_rule_registry.py`: immutable rule-pack registry.
- `fmea_infrastructure/topology_json.py`: contained topology-snapshot adapter for local testing and DomainPacks.
- `fmea_infrastructure/propagation_generator.py`: structured model suggestion adapter.
- `fmea_infrastructure/propagation_repository_sqlite.py`: graph/review persistence.
- `fmea_infrastructure/migrations/004_fmea_propagation_closure.sql`: topology, run, graph, edge-decision, and path-issue tables.
- `domain_packs/fuel-combustion/propagation/fuel-combustion-1.0.0.yaml`: first propagation rule pack.
- `domain_packs/fuel-combustion/topology/demo-1.0.0.json`: deterministic demonstration topology.
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_propagation_contracts.py`: REST schemas.
- `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_propagation_v1.py`: propagation routes.
- `scripts/fmea_skill.py`: `propagation` CLI group.
- `scripts/run_fmea_propagation_acceptance.py` and `scripts/verify_fmea_propagation_acceptance.py`: acceptance pack.

---

### Task 1: Freeze propagation graph, topology, and rule contracts

**Files:**
- Modify: `core_domain/fmea/propagation.py`
- Modify: `core_domain/fmea/states.py`
- Modify: `core_domain/fmea/__init__.py`
- Create: `fmea_application/propagation_contracts.py`
- Test: `tests/unit/test_fmea_propagation_graph.py`

**Interfaces:**
- Consumes: existing `PropagationEdge`, `EvidencePack`, `ClaimStatus`, `EvidenceSupportStatus`, and `RiskStatus`.
- Produces: `PropagationStatus`, `TopologyNode`, `TopologyInterface`, `TopologySnapshot`, `PropagationRulePack`, `PropagationPath`, `PropagationGraphRevision`, and exact validation functions.

- [ ] **Step 1: Write failing invariant tests**

```python
def test_graph_rejects_edge_endpoint_outside_topology():
    topology = topology_snapshot(nodes=(node("pump"), node("manifold")))
    edge = propagation_edge(source="pump", target="combustor")
    with pytest.raises(FmeaDomainError, match="endpoint is outside topology"):
        validate_graph_revision(graph_revision(edges=(edge,)), topology, propagation_rules())


def test_one_evidence_reference_cannot_implicitly_support_two_edges():
    path = propagation_path(
        edges=(edge("pump", "nozzle", evidence_ids=("E1",)), edge("nozzle", "flame", evidence_ids=())),
    )
    with pytest.raises(FmeaDomainError, match="edge evidence is required"):
        validate_path(path, evidence_pack("E1"), propagation_rules())
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_propagation.py tests/unit/test_fmea_propagation_graph.py -q`

Expected: FAIL because graph-level contracts do not exist.

- [ ] **Step 3: Implement immutable graph contracts**

```python
class PropagationStatus(str, Enum):
    NOT_ANALYZED = "not_analyzed"
    PROPOSED = "proposed"
    REVIEWED = "reviewed"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"


@dataclass(frozen=True, slots=True)
class PropagationGraphRevision:
    graph_revision_id: str
    workspace_id: str
    analysis_id: str
    analysis_record_version: int
    topology_snapshot_id: str
    topology_hash: str
    evidence_pack_ids: tuple[str, ...]
    domain_pack_id: str
    domain_pack_version: str
    rule_pack_id: str
    rule_pack_version: str
    status: PropagationStatus
    assistance_suggestion_ids: tuple[str, ...]
    nodes: tuple[TopologyNode, ...]
    edges: tuple[PropagationEdge, ...]
    paths: tuple[PropagationPath, ...]
    unresolved_issue_codes: tuple[str, ...]
    parent_graph_revision_id: str | None
    record_version: int
    created_at: str
```

Validate unique IDs, endpoint membership, matching analysis/workspace, supported relation types, interface-variable compatibility, unit equality, direction, operating-mode intersection, non-negative timing, path continuity, per-edge evidence, exact path length, and cycle flags. Preserve the current `PropagationEdge.auto_accept_allowed` property as an eligibility signal, not human confirmation.

- [ ] **Step 4: Run graph and existing policy tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_propagation.py tests/unit/test_fmea_propagation_graph.py tests/unit/test_fmea_entities.py -q`

Expected: PASS.

- [ ] **Step 5: Commit graph contracts**

```powershell
git add core_domain/fmea/propagation.py core_domain/fmea/states.py core_domain/fmea/__init__.py fmea_application/propagation_contracts.py tests/unit/test_fmea_propagation_graph.py tests/unit/test_fmea_propagation.py
git commit -m "feat(fmea): define propagation graph revisions"
```

### Task 2: Register fuel/combustion propagation rules and topology snapshots

**Files:**
- Modify: `fmea_application/ports.py`
- Create: `fmea_infrastructure/propagation_rule_registry.py`
- Create: `fmea_infrastructure/topology_json.py`
- Create: `domain_packs/fuel-combustion/propagation/fuel-combustion-1.0.0.yaml`
- Create: `domain_packs/fuel-combustion/topology/demo-1.0.0.json`
- Test: `tests/unit/test_fmea_propagation_rule_registry.py`
- Test: `tests/unit/test_fmea_topology_json.py`
- Test: `tests/integration/test_fmea_fuel_combustion_propagation_pack.py`

**Interfaces:**
- Consumes: DomainPack manifest and graph contracts from Task 1.
- Produces: `PropagationRuleRegistry.get()` and `SystemTopologyPort.load_snapshot()`.

- [ ] **Step 1: Write containment, identity, and domain-fixture tests**

```python
def test_topology_loader_rejects_symlink_escape(tmp_path):
    escaped = make_symlink_escape(tmp_path)
    with pytest.raises(FmeaDomainError, match="TOPOLOGY_PATH_OUTSIDE_ROOT"):
        JsonTopologyRepository(tmp_path).load_snapshot(escaped.name, "1.0.0")


def test_fuel_to_combustion_fixture_has_explicit_interfaces():
    snapshot = fuel_combustion_topology()
    assert interface(snapshot, "fuel_pump", "fuel_manifold").variable == "fuel_pressure"
    assert interface(snapshot, "fuel_nozzle", "combustor_flame").variable == "atomization_quality"
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_propagation_rule_registry.py tests/unit/test_fmea_topology_json.py tests/integration/test_fmea_fuel_combustion_propagation_pack.py -q`

Expected: FAIL because registries and fixtures are absent.

- [ ] **Step 3: Implement registries and first rule/topology set**

```python
class PropagationRuleRegistry(Protocol):
    def get(self, rule_pack_id: str, version: str) -> PropagationRulePack: ...


class SystemTopologyPort(Protocol):
    def load_snapshot(self, topology_id: str, version: str) -> TopologySnapshot: ...
    def neighbors(self, snapshot: TopologySnapshot, entity_id: str) -> tuple[TopologyInterface, ...]: ...
```

The rule YAML declares relation types, allowed interface variables and units, maximum automatic depth `2`, mandatory-review conditions, barrier semantics, timing constraints, risk escalation, and prohibited silent fallback. The topology fixture contains fuel pump, filter, manifold, nozzle, combustor flame, pressure sensor, controller, and explicit reverse feedback interfaces.

- [ ] **Step 4: Run registry, topology, and DomainPack tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_propagation_rule_registry.py tests/unit/test_fmea_topology_json.py tests/integration/test_fmea_fuel_combustion_propagation_pack.py tests/integration/test_fmea_fuel_combustion_pack.py -q`

Expected: PASS.

- [ ] **Step 5: Commit rules and topology**

```powershell
git add fmea_application/ports.py fmea_infrastructure/propagation_rule_registry.py fmea_infrastructure/topology_json.py domain_packs/fuel-combustion/propagation domain_packs/fuel-combustion/topology tests/unit/test_fmea_propagation_rule_registry.py tests/unit/test_fmea_topology_json.py tests/integration/test_fmea_fuel_combustion_propagation_pack.py
git commit -m "feat(fmea): register fuel combustion propagation rules"
```

### Task 3: Enumerate bounded candidates and generate model-assisted edges

**Files:**
- Create: `fmea_application/propagation_service.py`
- Create: `fmea_infrastructure/propagation_generator.py`
- Modify: `fmea_application/service_factory.py`
- Test: `tests/unit/test_fmea_propagation_service.py`
- Test: `tests/unit/test_fmea_propagation_generator.py`
- Test: `tests/regression/test_fmea_propagation_prompt_injection.py`

**Interfaces:**
- Consumes: accepted FMEA rows, confirmed risk when required, EvidencePacks, topology/rule registries, and structured model gateway.
- Produces: `PropagationAnalysisService.start_analysis()` and immutable graph proposals.

- [ ] **Step 1: Write candidate-boundary and injection tests**

```python
def test_generator_cannot_add_endpoint_outside_enumerated_candidates(service, fake_gateway):
    fake_gateway.respond_with(edge_json(source="fuel_pump", target="invented_turbine"))
    result = service.start_analysis(start_command(), analyst())
    assert result.status is RunStatus.FAILED
    assert result.error_code == "FMEA_PROPAGATION_ENDPOINT_INVALID"


def test_prompt_text_inside_evidence_cannot_raise_depth_budget(service, injection_pack):
    result = service.start_analysis(start_command(max_depth=2, pack=injection_pack), analyst())
    assert all(path.path_length <= 2 or path.requires_human_review for path in result.graph.paths)
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_propagation_service.py tests/unit/test_fmea_propagation_generator.py tests/regression/test_fmea_propagation_prompt_injection.py -q`

Expected: FAIL because the service and generator are absent.

- [ ] **Step 3: Implement deterministic enumeration before model generation**

```python
class PropagationSuggestionGenerator(Protocol):
    def generate(self, request: PropagationModelRequest) -> AssistanceSuggestion[tuple[PropagationEdgeProposal, ...]]: ...


class PropagationAnalysisService:
    def start_analysis(self, command: StartPropagationCommand, actor: ActorContext) -> PropagationRun: ...
    def get_run(self, run_id: str, actor: ActorContext) -> PropagationRun: ...
    def get_graph(self, analysis_id: str, actor: ActorContext) -> PropagationGraphRevision | None: ...
```

Enumerate candidate interfaces breadth-first with deterministic ordering and depth `2`. Build a projection containing only candidate endpoint IDs, interface metadata, bounded evidence, rule identity, and accepted source failures. Return the shared immutable `AssistanceSuggestion` envelope, persist it through the Phase 1 assistance repository, bind its ID into the graph proposal, and reuse Flash generation plus `deepseek-v4-pro` criticism with at most one repair through the existing provider-neutral pipeline. Decode strict JSON; reject unknown endpoints, unknown evidence IDs, unapproved relation types, and budget overrides. Validate every edge and path before persistence.

- [ ] **Step 4: Run generation, graph, and structured-model regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_propagation_service.py tests/unit/test_fmea_propagation_generator.py tests/regression/test_fmea_propagation_prompt_injection.py tests/unit/test_structured_generation_pipeline.py tests/unit/test_fmea_propagation_graph.py -q`

Expected: PASS.

- [ ] **Step 5: Commit bounded generation**

```powershell
git add fmea_application/propagation_service.py fmea_application/service_factory.py fmea_infrastructure/propagation_generator.py tests/unit/test_fmea_propagation_service.py tests/unit/test_fmea_propagation_generator.py tests/regression/test_fmea_propagation_prompt_injection.py
git commit -m "feat(fmea): generate bounded propagation candidates"
```

### Task 4: Persist graph revisions and apply human edge decisions

**Files:**
- Create: `fmea_infrastructure/migrations/004_fmea_propagation_closure.sql`
- Create: `fmea_infrastructure/propagation_repository_sqlite.py`
- Modify: `fmea_application/ports.py`
- Modify: `fmea_application/propagation_service.py`
- Modify: `fmea_infrastructure/composition.py`
- Modify: `fmea_infrastructure/local_auth.py`
- Test: `tests/integration/test_fmea_propagation_sqlite.py`
- Test: `tests/unit/test_fmea_propagation_review.py`
- Test: `tests/unit/test_fmea_local_auth.py`
- Test: `tests/regression/test_fmea_propagation_idempotency.py`

**Interfaces:**
- Consumes: graph proposals from Task 3 and shared audit/outbox/idempotency contracts.
- Produces: immutable edge decisions, confirmed/invalidated graph revisions, and exact replay.

- [ ] **Step 1: Write atomic review and invalidation tests**

```python
def test_confirm_graph_commits_decisions_revision_audit_and_outbox(repository):
    prepared = prepared_graph_confirmation(edge_actions=(accept("edge-1"), reject("edge-2")))
    result = repository.commit_graph_review(prepared)
    assert result.graph.status is PropagationStatus.CONFIRMED
    assert result.graph.edges == (expected_edge("edge-1"),)
    assert repository.replay_graph_review(prepared.scope, prepared.payload_hash) == result


def test_evidence_version_change_invalidates_confirmed_graph(service):
    confirmed = service.confirm_graph(valid_graph_review(), propagation_reviewer())
    invalidated = service.invalidate_if_stale(confirmed.analysis_id, changed_evidence_hash(), system_actor())
    assert invalidated.status is PropagationStatus.INVALIDATED
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py tests/unit/test_fmea_propagation_review.py tests/regression/test_fmea_propagation_idempotency.py -q`

Expected: FAIL because migration, repository, and review commands are absent.

- [ ] **Step 3: Add schema, repository, and review commands**

Migration `004` creates immutable topology snapshots, propagation runs, graph revisions, edge records, path records, edge decisions, graph decisions, and unresolved issues. Graph confirmation creates a child graph revision rather than updating a proposed graph payload.

```python
class PropagationRepository(Protocol):
    def save_run_and_proposal(self, prepared: PreparedPropagationProposal) -> PropagationRun: ...
    def get_graph(self, graph_revision_id: str, workspace_id: str) -> PropagationGraphRevision | None: ...
    def replay_graph_review(self, scope: IdempotencyScope, payload_hash: str) -> PropagationReviewResult | None: ...
    def commit_graph_review(self, prepared: PreparedPropagationReview) -> PropagationReviewResult: ...
    def invalidate(self, prepared: PreparedPropagationInvalidation) -> PropagationGraphRevision: ...
```

Require a human `propagation_reviewer`, exact graph version, one decision per reviewed edge, explicit acknowledgements for retained long/cyclic/high-risk/conflicting edges, and transactionally matching audit/outbox events. Extend opt-in local auth to return `reviewer`, `risk_reviewer`, and `propagation_reviewer`; keep production auth fail-closed behind the same provider port.

- [ ] **Step 4: Run propagation persistence and prior-phase regressions**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_sqlite.py tests/unit/test_fmea_propagation_review.py tests/unit/test_fmea_local_auth.py tests/regression/test_fmea_propagation_idempotency.py tests/integration/test_fmea_risk_sqlite.py tests/integration/test_fmea_review_sqlite.py -q`

Expected: PASS.

- [ ] **Step 5: Commit persistence and human review**

```powershell
git add fmea_infrastructure/migrations/004_fmea_propagation_closure.sql fmea_infrastructure/propagation_repository_sqlite.py fmea_application/ports.py fmea_application/propagation_service.py fmea_infrastructure/composition.py fmea_infrastructure/local_auth.py tests/integration/test_fmea_propagation_sqlite.py tests/unit/test_fmea_propagation_review.py tests/unit/test_fmea_local_auth.py tests/regression/test_fmea_propagation_idempotency.py
git commit -m "feat(fmea): review propagation graphs atomically"
```

### Task 5: Publish propagation REST and CLI contracts

**Files:**
- Create: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_propagation_contracts.py`
- Create: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_propagation_v1.py`
- Modify: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py`
- Modify: `scripts/fmea_skill.py`
- Test: `tests/unit/test_fmea_propagation_api_contracts.py`
- Test: `tests/integration/test_fmea_propagation_api_v1.py`
- Test: `tests/integration/test_fmea_propagation_cli.py`

**Interfaces:**
- Consumes: `PropagationAnalysisService`.
- Produces: matching REST and single-JSON CLI resources.

- [ ] **Step 1: Write transport parity and concurrency tests**

```python
def test_graph_review_rejects_stale_etag(client):
    response = client.post(
        "/api/v1/fmea/propagation-graphs/graph-1/reviews",
        headers={"If-Match": '"1"', "Idempotency-Key": UUID1},
        json=valid_graph_review_body(),
    )
    assert response.status_code == 412
    assert response.json()["error"]["code"] == "FMEA_PROPAGATION_VERSION_CONFLICT"


def test_cli_graph_show_matches_rest(client, invoke_cli):
    assert invoke_cli("propagation", "show", "--graph-id", "graph-1")["data"] == get_graph(client)["data"]
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_propagation_api_contracts.py tests/integration/test_fmea_propagation_api_v1.py tests/integration/test_fmea_propagation_cli.py -q`

Expected: FAIL because transports are absent.

- [ ] **Step 3: Implement strict routes and CLI**

REST resources:

```text
POST /api/v1/fmea/analyses/{analysis_id}/propagation-runs
GET  /api/v1/fmea/propagation-runs/{run_id}
GET  /api/v1/fmea/propagation-graphs/{graph_revision_id}
GET  /api/v1/fmea/propagation-graphs/{graph_revision_id}/paths
POST /api/v1/fmea/propagation-graphs/{graph_revision_id}/reviews
```

CLI commands:

```text
fmea_skill.py propagation start --analysis-id ID --record-version N --idempotency-key UUID
fmea_skill.py propagation status --run-id RUN
fmea_skill.py propagation show --graph-id GRAPH
fmea_skill.py propagation paths --graph-id GRAPH
fmea_skill.py propagation review --request-file FILE --confirm-human-propagation-review
```

Use pagination for paths, strict Pydantic bodies, 256 KiB command limit, ETag, stable safe errors, no topology/model override, and explicit human confirmation.

- [ ] **Step 4: Run new and existing API/CLI matrices**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_propagation_api_contracts.py tests/integration/test_fmea_propagation_api_v1.py tests/integration/test_fmea_propagation_cli.py tests/integration/test_fmea_risk_api_v1.py tests/integration/test_fmea_review_api_v1.py -q`

Expected: PASS.

- [ ] **Step 5: Commit transports**

```powershell
git add api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/fmea_propagation_contracts.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_fmea_propagation_v1.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/api.py scripts/fmea_skill.py tests/unit/test_fmea_propagation_api_contracts.py tests/integration/test_fmea_propagation_api_v1.py tests/integration/test_fmea_propagation_cli.py
git commit -m "feat(fmea): expose propagation interfaces"
```

### Task 6: Close propagation acceptance and security gates

**Files:**
- Create: `examples/fmea/propagation/fuel-combustion/`
- Create: `scripts/run_fmea_propagation_acceptance.py`
- Create: `scripts/verify_fmea_propagation_acceptance.py`
- Create: `tests/integration/test_fmea_propagation_acceptance.py`
- Create: `tests/regression/test_fmea_propagation_security.py`
- Create: `docs/handoff/fmea-propagation-closure.md`

**Interfaces:**
- Consumes: all Phase 2 resources.
- Produces: `graphrag.fmea.propagation.acceptance.v1` canonical artifacts.

- [ ] **Step 1: Write fixture and verifier tests**

```python
def test_acceptance_covers_forward_reverse_cycle_conflict_and_long_path(run_acceptance):
    summary = run_acceptance()
    assert set(summary["case_ids"]) == {"forward", "reverse", "cycle", "conflict", "long_path"}
    assert summary["invented_endpoint_count"] == 0
    assert summary["model_confirmation_count"] == 0


def test_verifier_rejects_edge_without_independent_evidence(tampered_pack):
    remove_second_edge_evidence(tampered_pack)
    assert verify(tampered_pack).error_code == "FMEA_PROPAGATION_EVIDENCE_INVALID"
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `.venv\Scripts\python.exe -m pytest tests/integration/test_fmea_propagation_acceptance.py tests/regression/test_fmea_propagation_security.py -q`

Expected: FAIL because acceptance assets are absent.

- [ ] **Step 3: Implement atomic runner, independent verifier, and handoff**

Generate topology, proposal, reviewed graph, paths, decisions, issues, audit summary, and acceptance summary in a contained temporary directory. Independently recompute topology/rule/graph hashes, path continuity, edge evidence, depth, cycle, risk and actor policies, then atomically publish. Reject duplicates, extra files, private markers, endpoint invention, missing evidence, or model confirmation.

- [ ] **Step 4: Run the complete Phase 2 gate**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_fmea_propagation.py tests/unit/test_fmea_propagation_graph.py tests/unit/test_fmea_propagation_rule_registry.py tests/unit/test_fmea_topology_json.py tests/unit/test_fmea_propagation_service.py tests/unit/test_fmea_propagation_generator.py tests/unit/test_fmea_propagation_review.py tests/unit/test_fmea_propagation_api_contracts.py tests/integration/test_fmea_fuel_combustion_propagation_pack.py tests/integration/test_fmea_propagation_sqlite.py tests/integration/test_fmea_propagation_api_v1.py tests/integration/test_fmea_propagation_cli.py tests/integration/test_fmea_propagation_acceptance.py tests/regression/test_fmea_propagation_idempotency.py tests/regression/test_fmea_propagation_prompt_injection.py tests/regression/test_fmea_propagation_security.py -q
.venv\Scripts\python.exe scripts/run_fmea_propagation_acceptance.py
.venv\Scripts\python.exe scripts/verify_fmea_propagation_acceptance.py --latest
.venv\Scripts\python.exe -m compileall -q core_domain fmea_application fmea_infrastructure scripts
.venv\Scripts\ruff.exe check core_domain/fmea fmea_application fmea_infrastructure scripts/fmea_skill.py scripts/run_fmea_propagation_acceptance.py scripts/verify_fmea_propagation_acceptance.py tests/unit/test_fmea_propagation*.py tests/integration/test_fmea_propagation*.py tests/regression/test_fmea_propagation*.py
git diff --check
```

Expected: every command exits 0. No paid live call is part of the default gate.

- [ ] **Step 5: Commit Phase 2 acceptance**

```powershell
git add examples/fmea/propagation/fuel-combustion scripts/run_fmea_propagation_acceptance.py scripts/verify_fmea_propagation_acceptance.py tests/integration/test_fmea_propagation_acceptance.py tests/regression/test_fmea_propagation_security.py docs/handoff/fmea-propagation-closure.md
git commit -m "test(fmea): close propagation workflow acceptance"
```

## Phase 2 completion checklist

- [ ] Topology and rule packs are immutable and version-bound.
- [ ] Model suggestions cannot invent endpoints or exceed server budgets.
- [ ] Every edge has independent evidence and deterministic validation.
- [ ] Long, cyclic, high-risk, external, conflicting, and incomplete paths remain human-reviewed.
- [ ] Graph confirmation and invalidation are atomic, idempotent, audited, and replayable.
- [ ] REST/CLI and independent acceptance pass without a paid model call.
