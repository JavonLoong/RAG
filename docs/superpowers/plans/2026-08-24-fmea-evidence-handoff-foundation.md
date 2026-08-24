# FMEA Multi-Source Evidence Handoff Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden propagation auto-acceptance, establish the FMEA application boundary, and adapt one evidence-only QueryService response into an immutable, auditable EvidenceSnapshot that supports RAG-only, GraphRAG-only, combined, auto, and custom source selection.

**Architecture:** FMEA consumes the query contract through a narrow `EvidenceProvider`; it never imports a vector database, graph database, retriever, chunker, or GraphRAG implementation. `EvidenceSnapshot` wraps the immutable engineering `EvidencePack` with execution audit facts, while `EvidenceRef` receives only allowlisted stable provenance. Deterministic domain validation and persistence remain independent from external LLMs and concrete storage.

**Tech Stack:** Python 3.11+, dataclasses, Protocol, Pydantic v2 query contracts, pytest, Ruff, SHA-256, canonical JSON.

**Spec:** `docs/superpowers/specs/2026-08-24-rag-graphrag-evidence-selection-design.md`

**Dependency:** Complete `docs/superpowers/plans/2026-08-24-query-evidence-selection.md` Tasks 1-3 first.

## Global Constraints

- This plan owns FMEA domain/application and the query-to-FMEA adapter only; it does not implement M3 indexing/retrieval or M4 graph construction/search algorithms.
- `QueryServiceEvidenceProvider.create_snapshot()` performs exactly one `QueryService.query()` call per request.
- The adapter must not import Chroma, Neo4j, GraphStore, a concrete retriever, or a concrete QueryService class; use a structural Protocol.
- `EvidencePack` contains engineering evidence only. Query warnings, selected profile, source counts, and incomplete state stay in `EvidenceSnapshot`.
- Retrieval score, rank, arbitrary citation metadata, prompts, and model output are never copied into `EvidenceRef`.
- No final-answer LLM, candidate-generation LLM, database migration, UI, export, template builder, or external API call is added in this plan.
- Tests use deterministic fakes and injected clock/ID factories; no production documents, indices, graph stores, network, or model credentials are required.

---

### Task 1: Harden PropagationEdge Validation and Auto-Acceptance

**Responsibility:** `OWN`; this is the approved Task 4.1 correction before application orchestration.

**Files:**
- Modify: `core_domain/fmea/propagation.py:18-64`
- Modify: `core_domain/fmea/policies.py:46-61`
- Modify: `tests/unit/test_fmea_propagation.py`
- Modify: `tests/fmea_fixtures.py`

**Interfaces:**
- Consumes: existing frozen `PropagationEdge`, `ClaimStatus`, `EvidenceSupportStatus`, and `EvidencePack`.
- Produces: closed risk-priority validation and conservative auto-acceptance without changing the serialized field model.

- [ ] **Step 1: Replace the permissive tests with failing safety cases**

Change the existing path parameterization from `(0, 1, 2)` to `(1, 2)`, then add:

```python
@pytest.mark.parametrize("path_length", (0, -1))
def test_non_positive_path_length_is_rejected(path_length: int) -> None:
    with pytest.raises(FmeaDomainError, match="path_length"):
        validate_propagation_edge(edge(path_length=path_length), None)


@pytest.mark.parametrize(
    "claim_status",
    (
        ClaimStatus.UNKNOWN,
        ClaimStatus.INSUFFICIENT_EVIDENCE,
        ClaimStatus.CONFLICT,
        ClaimStatus.NOT_APPLICABLE,
    ),
)
def test_only_known_claims_can_be_auto_accepted(claim_status: ClaimStatus) -> None:
    assert edge(claim_status=claim_status).auto_accept_allowed is False


@pytest.mark.parametrize("risk_priority", (None, "high", "critical", "urgent"))
def test_missing_high_or_unknown_risk_requires_review(risk_priority: str | None) -> None:
    assert edge(risk_priority=risk_priority).auto_accept_allowed is False


def test_unknown_risk_priority_is_rejected_by_validation() -> None:
    with pytest.raises(FmeaDomainError, match="risk_priority"):
        validate_propagation_edge(edge(risk_priority="urgent"), None)
```

Strengthen the codec test with:

```python
assert decoded.claim_status is ClaimStatus.KNOWN
assert decoded.evidence_support is EvidenceSupportStatus.SUPPORTED
assert tuple(field.name for field in fields(PropagationEdge)) == EXPECTED_PROPAGATION_FIELDS
```

Define `EXPECTED_PROPAGATION_FIELDS` in the test as the current full field sequence, ending in `record_version`, so accidental insertions or reorderings fail visibly.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_fmea_propagation.py -q
```

Expected: the non-positive path, non-known claim, missing/unknown priority, and unknown-priority validation cases fail against the current permissive policy.

- [ ] **Step 3: Close the policy without changing the public field type**

In `core_domain/fmea/propagation.py`, add module constants:

```python
RISK_PRIORITIES = frozenset({"normal", "medium", "high", "critical"})
AUTO_ACCEPT_RISK_PRIORITIES = frozenset({"normal", "medium"})
```

Replace `auto_accept_allowed` with:

```python
return (
    self.path_length in {1, 2}
    and not self.is_cyclic
    and not self.is_unprocessed
    and not self.is_external
    and bool(self.evidence_ids)
    and self.evidence_support
    in {EvidenceSupportStatus.SUPPORTED, EvidenceSupportStatus.PARTIALLY_SUPPORTED}
    and self.claim_status is ClaimStatus.KNOWN
    and self.risk_priority in AUTO_ACCEPT_RISK_PRIORITIES
)
```

In `core_domain/fmea/policies.py`, validate before the optional pack return:

```python
if edge.path_length < 1:
    raise FmeaDomainError("path_length must be at least 1")
if edge.risk_priority is not None and edge.risk_priority not in RISK_PRIORITIES:
    raise FmeaDomainError(f"unknown risk_priority: {edge.risk_priority}")
```

`None` remains representable as an explicitly unassessed risk, but it can never auto-accept. Keep the existing `str | None` schema to avoid an unplanned migration.

- [ ] **Step 4: Update only fixtures that used path zero or an invalid priority**

The canonical fixture stays `path_length=2`, `risk_priority="normal"`. Do not silently rewrite test-specific unsafe values; they are required negative cases.

- [ ] **Step 5: Run propagation/domain regressions and lint**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_fmea_propagation.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_states.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/fmea/propagation.py core_domain/fmea/policies.py tests/unit/test_fmea_propagation.py tests/fmea_fixtures.py
```

Expected: all selected tests pass and Ruff exits `0`.

- [ ] **Step 6: Commit the safety correction**

```powershell
git add core_domain/fmea/propagation.py core_domain/fmea/policies.py tests/unit/test_fmea_propagation.py tests/fmea_fixtures.py
git commit -m "fix(fmea): harden propagation acceptance policy"
```

---

### Task 2: Add FMEA Application Ports, EvidenceSnapshot, and Stable Re-Exports

**Responsibility:** `OWN`; this establishes the handoff seam before writing the concrete adapter.

**Files:**
- Create: `fmea_application/__init__.py`
- Create: `fmea_application/ports.py`
- Create: `core_domain/fmea/contracts.py`
- Test: `tests/unit/test_fmea_application_contracts.py`

**Interfaces:**
- Consumes: FMEA domain models and query-side `CitationType`/`EvidenceSelectionProfile` from the dependent plan.
- Produces: `EvidenceRequest`, `EvidenceSnapshot`, `EvidenceProvider`, `PropagationEvidenceProvider`, and `FmeaRepository` Protocols.

- [ ] **Step 1: Write failing frozen-contract tests**

Create `tests/unit/test_fmea_application_contracts.py`:

```python
from dataclasses import FrozenInstanceError, fields
from typing import get_type_hints

import pytest

from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from fmea_application.ports import EvidenceRequest, EvidenceSnapshot


def test_evidence_request_defaults_to_combined_sources(fixture_versions) -> None:
    request = EvidenceRequest(
        workspace_id="ws-1",
        analysis_id="analysis-1",
        query="fuel pressure",
        versions=fixture_versions,
        acl_scope=("engineering",),
    )
    assert request.evidence_profile is EvidenceSelectionProfile.COMBINED
    assert request.evidence_types == ()
    assert request.max_hits == 20
    with pytest.raises(FrozenInstanceError):
        request.query = "changed"


def test_evidence_snapshot_separates_pack_from_run_audit(fixture_pack) -> None:
    snapshot = EvidenceSnapshot(
        pack=fixture_pack,
        profile=EvidenceSelectionProfile.COMBINED,
        source_counts=((CitationType.TEXT, 1), (CitationType.GRAPH, 0)),
        warnings=("GRAPH_RETRIEVAL_DEGRADED: graph unavailable",),
        incomplete=True,
    )
    assert tuple(field.name for field in fields(EvidenceSnapshot)) == (
        "pack", "profile", "source_counts", "warnings", "incomplete"
    )
    assert "score" not in get_type_hints(type(snapshot))


@pytest.mark.parametrize("max_hits", (0, -1, 101))
def test_evidence_request_rejects_invalid_hit_limits(fixture_versions, max_hits) -> None:
    with pytest.raises(ValueError, match="max_hits"):
        EvidenceRequest(
            "ws-1", "analysis-1", "fuel pressure", fixture_versions,
            ("engineering",), max_hits=max_hits,
        )
```

Add tests that `custom` requires non-empty unique `evidence_types`, while all non-custom profiles reject non-empty `evidence_types`. Also assert every tuple input is normalized to a tuple.

- [ ] **Step 2: Run the contract test and verify RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_fmea_application_contracts.py -q
```

Expected: collection fails because `fmea_application` does not exist.

- [ ] **Step 3: Define request and snapshot contracts**

In `fmea_application/ports.py`:

```python
@dataclass(frozen=True, slots=True)
class EvidenceRequest:
    workspace_id: str
    analysis_id: str
    query: str
    versions: VersionSet
    acl_scope: tuple[str, ...]
    evidence_profile: EvidenceSelectionProfile = EvidenceSelectionProfile.COMBINED
    evidence_types: tuple[CitationType, ...] = ()
    max_hits: int = 20

    def __post_init__(self) -> None:
        object.__setattr__(self, "acl_scope", tuple(self.acl_scope))
        object.__setattr__(self, "evidence_types", tuple(self.evidence_types))
        if not 1 <= self.max_hits <= 100:
            raise ValueError("max_hits must be between 1 and 100")
        if self.evidence_profile is EvidenceSelectionProfile.CUSTOM:
            if not self.evidence_types:
                raise ValueError("custom evidence profile requires evidence_types")
        elif self.evidence_types:
            raise ValueError("evidence_types require the custom evidence profile")
        if len(self.evidence_types) != len(set(self.evidence_types)):
            raise ValueError("evidence_types must not contain duplicates")


@dataclass(frozen=True, slots=True)
class EvidenceSnapshot:
    pack: EvidencePack
    profile: EvidenceSelectionProfile
    source_counts: tuple[tuple[CitationType, int], ...]
    warnings: tuple[str, ...]
    incomplete: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_counts", tuple(self.source_counts))
        object.__setattr__(self, "warnings", tuple(self.warnings))
```

- [ ] **Step 4: Define narrow structural ports**

Use Protocols, not concrete imports:

```python
class EvidenceProvider(Protocol):
    def create_snapshot(self, request: EvidenceRequest) -> EvidenceSnapshot: ...
    def read_refs(
        self, pack: EvidencePack, evidence_ids: tuple[str, ...]
    ) -> tuple[EvidenceRef, ...]: ...
    def load_pack(self, workspace_id: str, pack_id: str) -> EvidencePack: ...


class PropagationEvidenceProvider(Protocol):
    def find_propagation_edges(
        self, request: PropagationRequest
    ) -> tuple[PropagationEdge, ...]: ...
```

Separating `PropagationEvidenceProvider` prevents ordinary evidence snapshot creation from acquiring a GraphStore dependency. Also define the exact `FmeaRepository` methods from `2026-08-23-fmea-foundation.md` Task 5: initialize, save/get analysis, save/get pack, save/get row, save/get edge, and append audit event.

- [ ] **Step 5: Add one stable downstream domain seam**

Create `core_domain/fmea/contracts.py` as re-exports only; do not duplicate models. Its `__all__` is:

```python
__all__ = [
    "ActorType", "ClaimStatus", "EvidencePack", "EvidenceRef",
    "EvidenceSupportStatus", "FmeaAnalysis", "FmeaRow", "PropagationEdge",
    "PublicationStatus", "ReviewStatus", "RiskAssessment", "RunStatus",
    "ScoringRulePack", "VersionSet",
]
```

Add an identity test such as `contracts.EvidencePack is value_objects.EvidencePack` for each re-exported model class/enum.

- [ ] **Step 6: Run contract tests, import smoke tests, and lint**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_fmea_application_contracts.py tests/unit/test_query_contracts.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/fmea/contracts.py fmea_application tests/unit/test_fmea_application_contracts.py
```

Expected: all selected tests pass; importing `fmea_application.ports` does not initialize any database or external client.

- [ ] **Step 7: Commit the ports**

```powershell
git add core_domain/fmea/contracts.py fmea_application/__init__.py fmea_application/ports.py tests/unit/test_fmea_application_contracts.py
git commit -m "feat(fmea): add evidence snapshot application ports"
```

---

### Task 3: Add the Deterministic FmeaService Persistence Boundary

**Responsibility:** `OWN`; no LLM, evidence retrieval, or concrete database is allowed here.

**Files:**
- Create: `fmea_application/services.py`
- Test: `tests/unit/test_fmea_application.py`

**Interfaces:**
- Consumes: Task 2 `FmeaRepository` and current FMEA domain validators.
- Produces: `FmeaService.create_analysis`, `register_evidence_pack`, `save_row`, `save_propagation_edge`, and `persist_candidate_bundle`.

- [ ] **Step 1: Write failing service tests with an in-memory repository**

Copy the complete `MemoryRepository` shape from `2026-08-23-fmea-foundation.md` Task 5 into the test, then cover:

```python
def test_candidate_bundle_saves_pack_before_candidates(...):
    # repository records call order
    assert repository.calls == ["save_pack", "save_row", "save_edge"]


def test_candidate_bundle_marks_rows_suggested_and_unpublished(...):
    assert result_rows[0].review_status is ReviewStatus.SUGGESTED
    assert result_rows[0].publication_status is PublicationStatus.UNPUBLISHED


def test_candidate_bundle_routes_long_or_unsafe_edges_to_review(...):
    long_edge = replace(fixture_edge, path_length=3)
    unknown_edge = replace(fixture_edge, claim_status=ClaimStatus.UNKNOWN)
    _, result_edges = service.persist_candidate_bundle(..., edges=(long_edge, unknown_edge), ...)
    assert all(edge.review_status is ReviewStatus.IN_REVIEW for edge in result_edges)
```

Also test wrong analysis ID, wrong pack ID, missing evidence ID, and that no write occurs after validation fails.

- [ ] **Step 2: Run the service test and verify RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_fmea_application.py -q
```

Expected: collection fails because `fmea_application.services` does not exist.

- [ ] **Step 3: Implement deterministic validation and persistence**

`persist_candidate_bundle()` must validate the entire bundle before the first repository call, then save the pack once. Use `dataclasses.replace`:

```python
row_candidate = replace(
    row,
    review_status=ReviewStatus.SUGGESTED,
    publication_status=PublicationStatus.UNPUBLISHED,
)
edge_candidate = replace(
    edge,
    review_status=(
        ReviewStatus.SUGGESTED
        if edge.auto_accept_allowed
        else ReviewStatus.IN_REVIEW
    ),
    publication_status=PublicationStatus.UNPUBLISHED,
)
```

This tightens the earlier foundation wording: any edge that fails the complete auto-accept policy, not only paths over two hops, enters review. Return `tuple(saved_rows), tuple(saved_edges)`.

- [ ] **Step 4: Run application/domain regressions and lint**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_fmea_application.py tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_entities.py tests/unit/test_fmea_propagation.py -q
& '.venv\Scripts\python.exe' -m ruff check fmea_application tests/unit/test_fmea_application.py
```

Expected: all selected tests pass and Ruff exits `0`.

- [ ] **Step 5: Commit the service boundary**

```powershell
git add fmea_application/services.py tests/unit/test_fmea_application.py
git commit -m "feat(fmea): add deterministic candidate persistence"
```

---

### Task 4: Adapt One QueryService Call into an Immutable EvidenceSnapshot

**Responsibility:** `INTEGRATE`; this is the only component in this plan that understands both query citations and FMEA evidence.

**Files:**
- Create: `fmea_infrastructure/__init__.py`
- Create: `fmea_infrastructure/evidence_provider.py`
- Test: `tests/unit/test_fmea_evidence_provider.py`

**Interfaces:**
- Consumes: Task 2 `EvidenceRequest`/`EvidenceSnapshot`/`FmeaRepository`, dependent-plan `QueryRequest`/`QueryResponse`, injected QueryService Protocol, clock, and pack ID factory.
- Produces: `QueryServiceEvidenceProvider.create_snapshot`, `read_refs`, and `load_pack`.

- [ ] **Step 1: Write a failing recording QueryService test**

Create a fake with `calls: list[QueryRequest]` and a prebuilt QueryResponse containing one TEXT, one GRAPH, and one COMMUNITY citation. Assert:

```python
snapshot = provider.create_snapshot(
    EvidenceRequest(
        workspace_id="ws-1",
        analysis_id="analysis-1",
        query="fuel pressure to combustor",
        versions=fixture_versions,
        acl_scope=("engineering",),
        evidence_profile=EvidenceSelectionProfile.COMBINED,
    )
)

assert len(query_service.calls) == 1
assert query_service.calls[0].mode is QueryMode.AUTO
assert query_service.calls[0].evidence_only is True
assert query_service.calls[0].evidence_profile is EvidenceSelectionProfile.COMBINED
assert query_service.calls[0].include_context is True
assert query_service.calls[0].top_k == 20
assert [ref.source_type for ref in snapshot.pack.refs] == [
    "rag_text", "graphrag_relation", "graphrag_community"
]
assert repository.save_pack_calls == 1
```

Use injected `clock=lambda: "2026-08-24T00:00:00Z"` and `pack_id_factory=lambda: "pack-1"`.

- [ ] **Step 2: Run the provider test and verify RED**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_fmea_evidence_provider.py -q
```

Expected: collection fails because `fmea_infrastructure.evidence_provider` does not exist.

- [ ] **Step 3: Define a structural query port and make one request**

In the adapter module:

```python
class QueryPort(Protocol):
    def query(self, request: QueryRequest) -> QueryResponse: ...
```

Construct exactly one request:

```python
response = self._query_service.query(
    QueryRequest(
        query=request.query,
        workspace_id=request.workspace_id,
        mode=QueryMode.AUTO,
        top_k=request.max_hits,
        include_context=True,
        evidence_only=True,
        evidence_profile=request.evidence_profile,
        evidence_types=request.evidence_types,
    )
)
```

Do not call QueryService once per source and do not call GraphStore directly.

- [ ] **Step 4: Canonicalize only allowlisted provenance**

Normalize quote whitespace with `" ".join(citation.quote.split())`. Build a canonical JSON locator with `sort_keys=True`, `separators=(",", ":")`:

- TEXT: `document_id`, `file`, `page`, `chunk_id` from `citation.source` when present.
- GRAPH: `subject`, `predicate`, `object` from `citation.triple`, plus `edge_id=citation.id` and optional source document ID.
- COMMUNITY: `community_id=citation.id` and `title` only when `metadata["title"]` is a string.

Use stable fallback IDs:

```text
text:<workspace_id>:<citation_id>
graph:<graph_version>:<citation_id>
community:<graph_version>:<citation_id>
```

Resolve document version from allowlisted string `metadata["document_version"]`; otherwise use `versions.data_version` for TEXT and `versions.graph_version` for GRAPH/COMMUNITY. Resolve only these additional metadata keys:

```text
source_trust: non-empty string, default "unrated"
is_primary: literal True only, default False
```

Hash deterministically:

```python
content_hash = sha256(normalized_quote.encode("utf-8")).hexdigest()
identity = canonical_json({
    "source_type": source_type,
    "document_id": document_id,
    "document_version": document_version,
    "locator": locator,
    "normalized_quote": normalized_quote,
})
evidence_hash = sha256(identity.encode("utf-8")).hexdigest()
evidence_id = f"ev-{evidence_hash[:24]}"
```

Never copy score, rank, or the remaining metadata into `EvidenceRef`.

- [ ] **Step 5: Add failing dedupe, conflict, warning, and zero-source cases**

Cover all of the following:

- exact duplicate citations create one EvidenceRef;
- same quote on a different page/version/source type creates distinct refs;
- conflicting allowlisted locator facts retain both refs and add `EVIDENCE_IDENTITY_CONFLICT` warning;
- query warnings become stable `"<code>: <message>"` strings;
- RAG-only counts only TEXT and never invents graph refs;
- GraphRAG-only accepts GRAPH plus COMMUNITY without text refs;
- combined with a selected zero-hit type is incomplete;
- custom preserves requested types;
- no citations yields an empty immutable pack and `incomplete=True`;
- arbitrary metadata keys and score changes do not change EvidenceRef hashes.

For conflict detection, use a pre-normalization citation key of `(citation.type, citation.id, document_id, document_version)`. If that key repeats with identical canonical locator and normalized quote, deduplicate it. If it repeats with different allowlisted locator facts or quote, retain both hash-derived EvidenceRefs and add the conflict warning; never choose one silently.

- [ ] **Step 6: Compute source counts and incomplete state explicitly**

Count the response citations before EvidenceRef dedupe in stable type order TEXT, GRAPH, COMMUNITY. Determine expected types from the explicit request profile using the query contract helper. For `AUTO`, only warnings or a completely empty response force incomplete because configured-but-absent sources are not knowable at the adapter boundary. For other profiles:

```python
incomplete = bool(warnings) or any(source_counts[type_] == 0 for type_ in expected_types)
```

Build `EvidencePack` with the injected pack ID and clock, persist it exactly once through `repository.save_evidence_pack(..., actor_id="evidence-provider", actor_type=ActorType.SYSTEM)`, then return `EvidenceSnapshot`.

- [ ] **Step 7: Implement read-only pack helpers**

`read_refs()` preserves requested evidence ID order and raises a typed FMEA domain/infrastructure error when an ID is absent. `load_pack(workspace_id, pack_id)` calls the repository once, rejects not-found packs, and rejects workspace mismatch. Neither helper invokes QueryService.

- [ ] **Step 8: Run provider/application/query regressions and lint**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_fmea_evidence_provider.py tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_application.py tests/unit/test_query_contracts.py tests/unit/test_query_service.py -q
& '.venv\Scripts\python.exe' -m ruff check fmea_infrastructure/evidence_provider.py tests/unit/test_fmea_evidence_provider.py
```

Expected: all selected tests pass; recording fake proves one query and one pack save.

- [ ] **Step 9: Commit the adapter**

```powershell
git add fmea_infrastructure/__init__.py fmea_infrastructure/evidence_provider.py tests/unit/test_fmea_evidence_provider.py
git commit -m "feat(fmea): adapt query evidence snapshots"
```

---

### Task 5: Prove Cross-Team Handoff and Document the Boundary

**Responsibility:** `INTEGRATE`; this is executable handoff evidence, not a new retrieval implementation.

**Files:**
- Create: `tests/integration/test_fmea_evidence_handoff.py`
- Create: `docs/handoff/rag-graphrag-fmea-evidence.md`
- Modify: `docs/superpowers/plans/2026-08-23-fmea-generation-propagation.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: deterministic RAG-only/GraphRAG-only/combined handoff fixtures and a Chinese ownership/extension guide.

- [ ] **Step 1: Write end-to-end fake handoff scenarios**

Without a real store or model, execute the public seam:

```text
EvidenceRequest
  -> QueryServiceEvidenceProvider
  -> one fake QueryService.query
  -> QueryResponse citations/warnings
  -> EvidenceSnapshot
  -> FmeaService.register_evidence_pack or persist_candidate_bundle
```

Parameterize at least:

| profile | citations | expected refs | incomplete |
| --- | --- | ---: | --- |
| rag_only | TEXT | 1 | false |
| graphrag_local_only | GRAPH | 1 | false |
| graphrag_global_only | COMMUNITY | 1 | false |
| graphrag_only | GRAPH + COMMUNITY | 2 | false |
| combined | TEXT + GRAPH + COMMUNITY | 3 | false |
| combined | TEXT + warning | 1 | true |
| custom(TEXT, COMMUNITY) | TEXT + COMMUNITY | 2 | false |

Assert all created candidates reference IDs present in exactly one saved pack.

- [ ] **Step 2: Add executable architecture-boundary assertions**

Use Python module inspection in the test to assert:

- `fmea_infrastructure.evidence_provider` exposes no Chroma/Neo4j/GraphStore concrete type;
- fake QueryService satisfies the adapter without inheriting from production classes;
- importing M3/M4-facing query contracts does not import `fmea_application` or `fmea_infrastructure`;
- EvidenceRef serialization contains no `score`, `rank`, `metadata`, or `prompt` field.

Do not use broad source-text checks for behavior; reserve import-name checks for the architectural dependency boundary only.

- [ ] **Step 3: Write the Chinese handoff guide**

Document:

- what belongs to M3, M4, M5 query interface, and FMEA;
- one request/response example for each profile;
- Citation-to-EvidenceRef allowlist table;
- warnings/incomplete behavior and no-silent-fallback rule;
- how another developer supplies a fake or real QueryService by Protocol;
- how a future template plugs in after EvidenceSnapshot without changing retrieval;
- explicit non-goals: index construction, graph extraction, generic answer generation, UI/export, and template authoring;
- next dependent work: LLM gateway, candidate schema/critic/repair, propagation analyzer, review/publish, SQLite, templates, and exports.

- [ ] **Step 4: Supersede the stale multi-call provider section**

In `2026-08-23-fmea-generation-propagation.md`, add a prominent note above its EvidenceProvider task:

```text
Superseded for evidence acquisition by the approved 2026-08-24 query evidence
selection spec and plans. Implement one evidence-only QueryService request returning
EvidenceSnapshot; do not implement the older VECTOR+LOCAL+GLOBAL multi-call design.
PropagationEvidenceProvider remains a separate later dependency.
```

Do not rewrite unrelated later candidate/critic/propagation tasks.

- [ ] **Step 5: Run the full handoff verification**

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_query_contracts.py tests/unit/test_query_service.py tests/integration/test_query_api_v1.py tests/integration/test_query_stream_v1.py tests/unit/test_fmea_propagation.py tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_application.py tests/unit/test_fmea_evidence_provider.py tests/integration/test_fmea_evidence_handoff.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/query_contracts.py core_domain/fmea fmea_application fmea_infrastructure tests/unit/test_fmea_application_contracts.py tests/unit/test_fmea_application.py tests/unit/test_fmea_evidence_provider.py tests/integration/test_fmea_evidence_handoff.py
git diff --check
```

Expected: all selected tests pass, Ruff exits `0`, and Git reports no whitespace errors.

- [ ] **Step 6: Commit the handoff proof**

```powershell
git add tests/integration/test_fmea_evidence_handoff.py docs/handoff/rag-graphrag-fmea-evidence.md docs/superpowers/plans/2026-08-23-fmea-generation-propagation.md
git commit -m "docs(fmea): prove multi-source evidence handoff"
```

## Plan Self-Review

- Spec sections 7-10 map to Tasks 2, 4, and 5; propagation safety maps to Task 1; deterministic persistence maps to Task 3.
- The plan uses one QueryService call and one EvidencePack save for each snapshot.
- `EvidenceSnapshot` carries execution audit; `EvidencePack`/`EvidenceRef` carry immutable engineering provenance only.
- Ordinary RAG and GraphRAG implementations remain replaceable behind the existing query contract.
- A future FMEA template is downstream of EvidenceSnapshot, so adding one does not require changing vector/graph retrieval or Citation normalization.
- The separate `PropagationEvidenceProvider` avoids forcing a GraphStore dependency into ordinary evidence acquisition.
- This plan intentionally stops before SQLite, external LLM calls, candidate generation/critic/repair, propagation analysis, review UI, publication/export, and template tooling; those remain in the already approved later FMEA plans.
