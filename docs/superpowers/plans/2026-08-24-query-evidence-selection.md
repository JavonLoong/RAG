# Query Evidence Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `graphrag.query.v1` with backward-compatible evidence-only requests that can select ordinary RAG, GraphRAG local/global, combined, auto, or custom Citation sources without invoking the final answer LLM.

**Architecture:** Keep `QueryMode` unchanged for all existing answer requests. Add an orthogonal `EvidenceSelectionProfile` that is valid only when `evidence_only=True`; resolve it to existing `CitationType` values and execute only the selected runtime components. Return the existing `QueryResponse` shape with empty answer text, typed citations, real hit counts, context, and explicit degradation warnings.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, Ruff, existing `core_domain.query_contracts` and `chroma_rag_poc.query_service`.

**Spec:** `docs/superpowers/specs/2026-08-24-rag-graphrag-evidence-selection-design.md`

## Global Constraints

- Do not add or rename any existing `QueryMode` value.
- A legacy `QueryRequest` that omits all new fields must execute and serialize exactly as before.
- `evidence_only=False` permits only `evidence_profile=auto` and an empty `evidence_types` tuple.
- Explicit evidence selection requires `mode=QueryMode.AUTO` and never performs silent cross-source fallback.
- `rag_only` must not call graph/global components; `graphrag_only` must not call the text retriever.
- `evidence_only=True` must never call the final answer LLM; GraphRAG global context generation may still call its configured global searcher.
- The response top-level field set and `schema_version="graphrag.query.v1"` remain unchanged.
- Tests use recording fakes only; no external model, real index, GraphStore, network, or production document is used.

---

### Task 1: Add the Backward-Compatible Evidence Selection Contract

**Files:**
- Modify: `core_domain/query_contracts.py:5-56`
- Modify: `core_domain/query_contracts.py:200-225`
- Test: `tests/unit/test_query_contracts.py`

**Interfaces:**
- Consumes: existing `CitationType`, `QueryMode`, and `_ContractModel`.
- Produces: `EvidenceSelectionProfile`; `QueryRequest.evidence_only`; `QueryRequest.evidence_profile`; `QueryRequest.evidence_types`; `selected_citation_types(request) -> tuple[CitationType, ...] | None` where `None` means auto-detect configured sources.

- [ ] **Step 1: Write failing default and enum tests**

Append these assertions to `tests/unit/test_query_contracts.py` and import `EvidenceSelectionProfile` plus `selected_citation_types`:

```python
def test_query_request_keeps_legacy_evidence_defaults() -> None:
    request = QueryRequest(query="pressure", workspace_id="ws-1")

    assert request.evidence_only is False
    assert request.evidence_profile is EvidenceSelectionProfile.AUTO
    assert request.evidence_types == ()
    assert selected_citation_types(request) is None


def test_evidence_profile_values_are_stable() -> None:
    assert tuple(item.value for item in EvidenceSelectionProfile) == (
        "auto",
        "rag_only",
        "graphrag_local_only",
        "graphrag_global_only",
        "graphrag_only",
        "combined",
        "custom",
    )
```

- [ ] **Step 2: Run the new contract tests and verify RED**

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_query_contracts.py::test_query_request_keeps_legacy_evidence_defaults tests/unit/test_query_contracts.py::test_evidence_profile_values_are_stable -q
```

Expected: collection fails because `EvidenceSelectionProfile` and `selected_citation_types` do not exist.

- [ ] **Step 3: Add profile mapping and request fields**

In `core_domain/query_contracts.py`, import `model_validator` and add:

```python
class EvidenceSelectionProfile(str, Enum):
    AUTO = "auto"
    RAG_ONLY = "rag_only"
    GRAPHRAG_LOCAL_ONLY = "graphrag_local_only"
    GRAPHRAG_GLOBAL_ONLY = "graphrag_global_only"
    GRAPHRAG_ONLY = "graphrag_only"
    COMBINED = "combined"
    CUSTOM = "custom"


_PROFILE_TYPES: dict[EvidenceSelectionProfile, tuple[CitationType, ...]] = {
    EvidenceSelectionProfile.RAG_ONLY: (CitationType.TEXT,),
    EvidenceSelectionProfile.GRAPHRAG_LOCAL_ONLY: (CitationType.GRAPH,),
    EvidenceSelectionProfile.GRAPHRAG_GLOBAL_ONLY: (CitationType.COMMUNITY,),
    EvidenceSelectionProfile.GRAPHRAG_ONLY: (CitationType.GRAPH, CitationType.COMMUNITY),
    EvidenceSelectionProfile.COMBINED: (
        CitationType.TEXT,
        CitationType.GRAPH,
        CitationType.COMMUNITY,
    ),
}
```

Because `CitationType` is currently declared after `QueryMode`, place `_PROFILE_TYPES` after `CitationType`. Extend `QueryRequest` with:

```python
    evidence_only: bool = False
    evidence_profile: EvidenceSelectionProfile = EvidenceSelectionProfile.AUTO
    evidence_types: tuple[CitationType, ...] = ()

    @model_validator(mode="after")
    def validate_evidence_selection(self) -> "QueryRequest":
        if not self.evidence_only:
            if self.evidence_profile is not EvidenceSelectionProfile.AUTO or self.evidence_types:
                raise ValueError("evidence selection requires evidence_only=true")
            return self
        if self.mode is not QueryMode.AUTO:
            raise ValueError("evidence_only requires mode=auto")
        if len(self.evidence_types) != len(set(self.evidence_types)):
            raise ValueError("evidence_types must not contain duplicates")
        if self.evidence_profile is EvidenceSelectionProfile.CUSTOM:
            if not self.evidence_types:
                raise ValueError("custom evidence profile requires evidence_types")
        elif self.evidence_types:
            raise ValueError("evidence_types are only valid for the custom profile")
        return self
```

Add this pure helper after `QueryRequest`:

```python
def selected_citation_types(request: QueryRequest) -> tuple[CitationType, ...] | None:
    if not request.evidence_only or request.evidence_profile is EvidenceSelectionProfile.AUTO:
        return None
    if request.evidence_profile is EvidenceSelectionProfile.CUSTOM:
        return request.evidence_types
    return _PROFILE_TYPES[request.evidence_profile]
```

Export both names in `__all__`.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_query_contracts.py::test_query_request_keeps_legacy_evidence_defaults tests/unit/test_query_contracts.py::test_evidence_profile_values_are_stable -q
```

Expected: `2 passed`.

- [ ] **Step 5: Write failing validation and mapping tests**

Add:

```python
@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("rag_only", (CitationType.TEXT,)),
        ("graphrag_local_only", (CitationType.GRAPH,)),
        ("graphrag_global_only", (CitationType.COMMUNITY,)),
        ("graphrag_only", (CitationType.GRAPH, CitationType.COMMUNITY)),
        ("combined", (CitationType.TEXT, CitationType.GRAPH, CitationType.COMMUNITY)),
    ],
)
def test_evidence_profiles_resolve_to_exact_citation_types(profile: str, expected) -> None:
    request = QueryRequest(
        query="pressure",
        workspace_id="ws-1",
        evidence_only=True,
        evidence_profile=profile,
    )
    assert selected_citation_types(request) == expected


def test_custom_evidence_profile_preserves_requested_order() -> None:
    request = QueryRequest(
        query="pressure",
        workspace_id="ws-1",
        evidence_only=True,
        evidence_profile="custom",
        evidence_types=(CitationType.COMMUNITY, CitationType.TEXT),
    )
    assert selected_citation_types(request) == (CitationType.COMMUNITY, CitationType.TEXT)


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence_profile": "rag_only"},
        {"evidence_types": ("text",)},
        {"evidence_only": True, "mode": "local", "evidence_profile": "rag_only"},
        {"evidence_only": True, "evidence_profile": "custom"},
        {"evidence_only": True, "evidence_profile": "rag_only", "evidence_types": ("text",)},
        {
            "evidence_only": True,
            "evidence_profile": "custom",
            "evidence_types": ("text", "text"),
        },
    ],
)
def test_invalid_evidence_selection_combinations_fail_before_execution(changes) -> None:
    payload = {"query": "pressure", "workspace_id": "ws-1", **changes}
    with pytest.raises(ValidationError):
        QueryRequest.model_validate(payload)
```

- [ ] **Step 6: Run all contract tests and lint**

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_query_contracts.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/query_contracts.py tests/unit/test_query_contracts.py
```

Expected: all contract tests pass and Ruff exits `0`.

- [ ] **Step 7: Commit the contract**

```powershell
git add core_domain/query_contracts.py tests/unit/test_query_contracts.py
git commit -m "feat(query): add evidence selection contract"
```

---

### Task 2: Execute Only the Selected Evidence Sources

**Files:**
- Modify: `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/query_service.py:284-520`
- Test: `tests/unit/test_query_service.py`

**Interfaces:**
- Consumes: Task 1 `selected_citation_types(request)` and existing recording runtime components.
- Produces: evidence-only `QueryResponse`; internal `_available_evidence_types(runtime)` and `_evidence_execution_types(request, runtime)` helpers; an evidence execution path that does not route through one legacy answer mode.

- [ ] **Step 1: Write the failing exact-component tests**

Add `EvidenceSelectionProfile` to imports and append:

```python
@pytest.mark.parametrize(
    ("profile", "selected"),
    [
        (EvidenceSelectionProfile.RAG_ONLY, {"text"}),
        (EvidenceSelectionProfile.GRAPHRAG_LOCAL_ONLY, {"graph"}),
        (EvidenceSelectionProfile.GRAPHRAG_GLOBAL_ONLY, {"global"}),
        (EvidenceSelectionProfile.GRAPHRAG_ONLY, {"graph", "global"}),
        (EvidenceSelectionProfile.COMBINED, {"text", "graph", "global"}),
    ],
)
def test_evidence_profile_calls_only_selected_components(profile, selected) -> None:
    service, _, _, components = _service()
    request = components["request"].model_copy(
        update={
            "mode": QueryMode.AUTO,
            "evidence_only": True,
            "evidence_profile": profile,
            "include_context": True,
        }
    )

    response = service.query(request)

    assert response.mode.requested is QueryMode.AUTO
    assert response.mode.used is QueryMode.AUTO
    assert bool(components["text"].calls) is ("text" in selected)
    assert bool(components["graph"].calls) is ("graph" in selected)
    assert bool(components["global"].calls) is ("global" in selected)
    assert components["llm"].prompts == []
    assert response.answer.text == ""
    assert response.answer.finish_reason == "stop"
    assert response.context is not None
```

- [ ] **Step 2: Run one profile test and verify RED**

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_query_service.py::test_evidence_profile_calls_only_selected_components -q
```

Expected: failures show the current mode-driven execution still routes through the legacy LOCAL component set and/or final LLM.

- [ ] **Step 3: Add evidence execution helpers**

Import `selected_citation_types`. Add:

```python
def _available_evidence_types(runtime: QueryRuntime) -> tuple[CitationType, ...]:
    result = [CitationType.TEXT]
    if runtime.graph_retriever is not None:
        result.append(CitationType.GRAPH)
    if runtime.global_searcher is not None:
        result.append(CitationType.COMMUNITY)
    return tuple(result)


def _evidence_execution_types(request: QueryRequest, runtime: QueryRuntime) -> tuple[CitationType, ...]:
    selected = selected_citation_types(request)
    return _available_evidence_types(runtime) if selected is None else selected
```

In `query()`, do not call the answer router for evidence requests and do not validate a selected legacy answer mode:

```python
if request.evidence_only:
    mode = QueryMode.AUTO
    mode_reason = f"evidence profile {request.evidence_profile.value} selected sources"
else:
    mode, mode_reason = self._select_mode(runtime, workspace, request)
    _ensure_mode_supported(workspace, mode)
    _ensure_index_ready(workspace, mode)
    _ensure_generation_available(runtime, mode)
```

The existing pre-runtime checks for an explicitly requested legacy mode remain unchanged because contract validation prevents `evidence_only=True` with a non-AUTO mode. This avoids rejecting `rag_only` because the workspace's default LOCAL graph index is unavailable, and it makes `ModeDecision.used=AUTO` an honest marker for profile-driven execution.

In `_execute_mode`, change the AUTO fallback to apply only to legacy answer requests:

```python
if mode_used is QueryMode.AUTO and not request.evidence_only:
    mode_used = QueryMode.LOCAL
```

Then derive booleans before retrieval:

```python
evidence_types = _evidence_execution_types(request, runtime) if request.evidence_only else ()
use_text = CitationType.TEXT in evidence_types if request.evidence_only else mode_used in (
    QueryMode.VECTOR,
    QueryMode.LOCAL,
    QueryMode.HYBRID,
)
use_graph = CitationType.GRAPH in evidence_types if request.evidence_only else mode_used in (
    QueryMode.LOCAL,
    QueryMode.HYBRID,
)
use_community = CitationType.COMMUNITY in evidence_types if request.evidence_only else mode_used in (
    QueryMode.GLOBAL,
    QueryMode.HYBRID,
)
```

Use these booleans for the three retrieval blocks. Pass `context_only=True` to `_global_search()` in every evidence-only call. Before the existing answer-generation branch add:

```python
if request.evidence_only:
    answer_text = ""
    finish_reason = "stop"
elif mode_used is QueryMode.VECTOR:
    answer_text = "\n\n".join(citation.quote for citation in text_citations)
elif mode_used is QueryMode.GLOBAL:
    ...
else:
    ...
```

Do not change legacy branches beyond replacing their component conditions with equivalent booleans.

- [ ] **Step 4: Run exact-component tests and verify GREEN**

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_query_service.py::test_evidence_profile_calls_only_selected_components -q
```

Expected: all five profile cases pass.

- [ ] **Step 5: Write failing custom, auto, and no-fallback tests**

Add:

```python
def test_custom_evidence_types_call_only_requested_sources() -> None:
    service, _, _, components = _service()
    request = components["request"].model_copy(
        update={
            "mode": QueryMode.AUTO,
            "evidence_only": True,
            "evidence_profile": EvidenceSelectionProfile.CUSTOM,
            "evidence_types": (CitationType.COMMUNITY, CitationType.TEXT),
        }
    )
    response = service.query(request)
    assert components["text"].calls
    assert not components["graph"].calls
    assert components["global"].calls
    assert [item.type for item in response.citations] == [CitationType.TEXT, CitationType.COMMUNITY]


def test_auto_evidence_profile_uses_every_configured_source_without_final_llm() -> None:
    service, _, _, components = _service()
    request = components["request"].model_copy(
        update={"mode": QueryMode.AUTO, "evidence_only": True}
    )
    response = service.query(request)
    assert components["text"].calls
    assert components["graph"].calls
    assert components["global"].calls
    assert components["llm"].prompts == []
    assert {item.type for item in response.citations} == {
        CitationType.TEXT,
        CitationType.GRAPH,
        CitationType.COMMUNITY,
    }
    assert components["router"] is None


def test_explicit_rag_only_failure_does_not_fall_back_to_graph() -> None:
    text = RecordingRetriever(RuntimeError("text unavailable"))
    service, _, _, components = _service(text=text)
    request = components["request"].model_copy(
        update={
            "mode": QueryMode.AUTO,
            "evidence_only": True,
            "evidence_profile": EvidenceSelectionProfile.RAG_ONLY,
        }
    )
    response = service.query(request)
    assert not components["graph"].calls
    assert not components["global"].calls
    assert response.citations == []
    assert any(item.code == "TEXT_RETRIEVAL_DEGRADED" for item in response.warnings)
```

If `RecordingRetriever` currently accepts only a list, add a local `FailingRetriever` with `retrieve()` that raises; do not alter production code for the fake.

- [ ] **Step 6: Make explicit evidence failures partial instead of legacy fatal**

The current VECTOR branch raises on text failure. Restrict that fatal behavior to non-evidence requests:

```python
if mode_used is QueryMode.VECTOR and not request.evidence_only:
    raise _query_failed("Text retrieval failed.", exc, stage="text_retrieval") from exc
```

Keep `TEXT_RETRIEVAL_DEGRADED` for evidence-only requests. Build `QueryStatus.PARTIAL` whenever warnings exist, using the existing response status logic.

- [ ] **Step 7: Run all QueryService tests and lint**

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_query_service.py tests/unit/test_query_contracts.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/query_contracts.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/query_service.py tests/unit/test_query_contracts.py tests/unit/test_query_service.py
```

Expected: all tests pass; the existing legacy component-selection parameterization remains unchanged; Ruff exits `0`.

- [ ] **Step 8: Commit evidence execution**

```powershell
git add api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/query_service.py tests/unit/test_query_service.py
git commit -m "feat(query): execute selected evidence sources"
```

---

### Task 3: Prove the Public v1 Shape and Streaming Handoff Remain Stable

**Files:**
- Modify: `tests/unit/test_query_contracts.py`
- Modify: `tests/integration/test_query_api_v1.py`
- Modify: `tests/integration/test_query_stream_v1.py`

**Interfaces:**
- Consumes: Tasks 1-2 QueryRequest and QueryService behavior.
- Produces: regression evidence that the HTTP/SSE adapters accept evidence selection without changing the response top-level schema or event ordering.

- [ ] **Step 1: Add the strict response-shape regression**

Extend `test_query_response_top_level_fields_are_stable_for_v1` only if needed; its expected field set must remain exactly:

```python
{
    "schema_version",
    "request_id",
    "trace_id",
    "status",
    "mode",
    "answer",
    "citations",
    "context",
    "retrieval",
    "usage",
    "warnings",
    "debug",
}
```

Add an evidence request serialization test:

```python
def test_evidence_request_extension_does_not_change_response_schema() -> None:
    request = QueryRequest(
        query="pressure",
        workspace_id="ws-1",
        evidence_only=True,
        evidence_profile="combined",
    )
    assert request.model_dump(mode="json")["evidence_profile"] == "combined"
    assert set(QueryResponse.model_fields) == {
        "schema_version", "request_id", "trace_id", "status", "mode", "answer",
        "citations", "context", "retrieval", "usage", "warnings", "debug",
    }
```

- [ ] **Step 2: Add an HTTP adapter request test**

In `tests/integration/test_query_api_v1.py`, use the existing injected fake service and POST helper to send:

```python
payload = {
    "query": "fuel pressure",
    "workspace_id": "power-equipment",
    "mode": "auto",
    "evidence_only": True,
    "evidence_profile": "graphrag_only",
}
```

Assert the captured `QueryRequest` has `evidence_only is True` and profile `GRAPHRAG_ONLY`. Do not alter the route path or response schema fixture.

- [ ] **Step 3: Add an SSE evidence ordering test**

In `tests/integration/test_query_stream_v1.py`, inject a response with empty answer text plus TEXT and GRAPH citations. Assert event order remains:

```text
meta -> citation -> citation -> final
```

and no synthetic answer delta is introduced by evidence-only mode.

- [ ] **Step 4: Run integration tests and verify GREEN**

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_query_contracts.py tests/unit/test_query_service.py tests/integration/test_query_api_v1.py tests/integration/test_query_stream_v1.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run the complete query interface regression and lint**

Run:

```powershell
& '.venv\Scripts\python.exe' -m pytest tests/unit/test_query_contracts.py tests/unit/test_query_service.py tests/integration/test_query_api_v1.py tests/integration/test_query_stream_v1.py tests/integration/test_query_skill_cli.py -q
& '.venv\Scripts\python.exe' -m ruff check core_domain/query_contracts.py api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/query_service.py tests/unit/test_query_contracts.py tests/unit/test_query_service.py tests/integration/test_query_api_v1.py tests/integration/test_query_stream_v1.py
```

Expected: all tests pass and Ruff exits `0`.

- [ ] **Step 6: Commit the public handoff proof**

```powershell
git add tests/unit/test_query_contracts.py tests/integration/test_query_api_v1.py tests/integration/test_query_stream_v1.py
git commit -m "test(query): prove evidence selection handoff"
```

## Plan Self-Review

- Spec sections 5-6 map to Tasks 1-2.
- Backward compatibility and public handoff map to Task 3.
- This plan intentionally stops before FMEA EvidenceSnapshot creation; that is the dependent second plan.
- No task implements M3 indexing, M4 graph construction, REST redesign, UI, exports, or an external model call.
