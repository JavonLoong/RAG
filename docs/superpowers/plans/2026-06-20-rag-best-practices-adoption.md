# RAG Best Practices Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a directly usable adoption layer that imports the best practical patterns from RAGFlow, Dify/FastGPT/MaxKB, Haystack/LlamaIndex, LightRAG/Microsoft GraphRAG, and RAGAS-style evaluation into this repository without wholesale license-risky code copying.

**Architecture:** Add a small, testable "production RAG profile" layer that turns the system into explicit stages: document parsing productization, engineering boundaries, retrieval quality, GraphRAG, evaluation, and operating steps. Existing modules remain in place and can be wired into these stages incrementally.

**Tech Stack:** Python 3.11, dataclasses, existing `retrieval_engine`, `rag_orchestrator`, `kg_pipeline`, `evaluation`, pytest.

---

## File Structure

- Create `rag_orchestrator/production_profile.py`: defines stage metadata, maturity gates, adoption status, and a reusable runbook model.
- Create `tests/unit/test_production_profile.py`: verifies the default profile covers the requested areas and has directly actionable local components.
- Modify `rag_orchestrator/__init__.py`: exports the profile helpers for direct import.
- Create `docs/RAG成熟项目最佳实践接入.md`: human-readable adoption guide mapping external project patterns to this repo.

---

### Task 1: Production RAG Profile

**Files:**
- Create: `tests/unit/test_production_profile.py`
- Create: `rag_orchestrator/production_profile.py`
- Modify: `rag_orchestrator/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
from rag_orchestrator.production_profile import (
    REQUIRED_ADOPTION_AREAS,
    build_default_profile,
)


def test_default_profile_covers_requested_adoption_areas() -> None:
    profile = build_default_profile()

    assert {stage.area for stage in profile.stages} == set(REQUIRED_ADOPTION_AREAS)
    assert profile.ready_stage_count < profile.total_stage_count
    assert profile.overall_status in {"prototype", "partial"}


def test_each_stage_has_external_pattern_and_local_component() -> None:
    profile = build_default_profile()

    for stage in profile.stages:
        assert stage.external_patterns
        assert stage.local_components
        assert stage.direct_use_steps
        assert stage.gaps
        assert stage.next_actions


def test_profile_renders_actionable_markdown() -> None:
    profile = build_default_profile()
    markdown = profile.to_markdown()

    assert "# RAG Mature Project Adoption Profile" in markdown
    assert "document_parsing_product" in markdown
    assert "retrieval_quality" in markdown
    assert "graphrag" in markdown
    assert "evaluation" in markdown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_production_profile.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'rag_orchestrator.production_profile'`.

- [ ] **Step 3: Write minimal implementation**

Implement dataclasses:

```python
@dataclass(frozen=True, slots=True)
class AdoptionStage:
    area: str
    label: str
    external_patterns: tuple[str, ...]
    local_components: tuple[str, ...]
    direct_use_steps: tuple[str, ...]
    gaps: tuple[str, ...]
    next_actions: tuple[str, ...]
    status: Literal["missing", "prototype", "partial", "ready"]


@dataclass(frozen=True, slots=True)
class ProductionRagProfile:
    stages: tuple[AdoptionStage, ...]
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_production_profile.py -q`

Expected: PASS.

---

### Task 2: Best-Practice Adoption Guide

**Files:**
- Create: `docs/RAG成熟项目最佳实践接入.md`
- Test: `tests/unit/test_production_profile.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
from pathlib import Path


def test_adoption_guide_exists_and_mentions_source_projects() -> None:
    guide = Path("docs/RAG成熟项目最佳实践接入.md")

    assert guide.exists()
    text = guide.read_text(encoding="utf-8")
    for name in ("RAGFlow", "Dify", "Haystack", "LlamaIndex", "LightRAG", "RAGAS"):
        assert name in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_production_profile.py -q`

Expected: FAIL because the guide does not exist.

- [ ] **Step 3: Write guide**

Create a concise guide with:

- What to copy legally: architecture, API boundaries, UX flows, evaluation gates.
- What not to copy blindly: entire source trees without preserving license and attribution.
- Six adoption areas: document parsing product, engineering boundary, retrieval quality, GraphRAG, evaluation, operating steps.
- Immediate local command examples.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_production_profile.py -q`

Expected: PASS.

---

### Task 3: Follow-Up Implementation Targets

**Files:**
- Future create: `data_pipeline/document_intake_profile.py`
- Future create: `retrieval_engine/rrf.py`
- Future create: `rag_orchestrator/citation_enforcer.py`
- Future create: `evaluation/quality_gates.py`

- [ ] **Document parsing productization**

Add an intake classifier that routes files into native text, scanned OCR, table-aware parsing, image/formula risk review, and chunk preview.

- [ ] **Retrieval quality**

Add RRF fusion, query rewrite hooks, metadata filters, and mandatory rerank failure reporting.

- [ ] **GraphRAG quality**

Add graph build quality checks, community summary source citations, and local/global route evaluation.

- [ ] **Evaluation gates**

Add pass/fail gates for recall, citation coverage, hallucination risk, latency, and failed-file ratio.

