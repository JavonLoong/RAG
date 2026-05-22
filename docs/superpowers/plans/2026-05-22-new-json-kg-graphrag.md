# New JSON KG GraphRAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete local pipeline from new Label Studio JSON files to filtered ChromaDB, KG extraction, human review, graph storage, and GraphRAG answering.

**Architecture:** JSON files stay local and are never committed. The pipeline converts raw annotation exports into auditable text blocks, writes selected text into ChromaDB, extracts evidence-bound triples from the selected text, stores graph data in a local graph store, then answers questions using vector evidence plus graph neighbors. UI exposes upload, filtering report, KG extraction, manual review, and GraphRAG query states.

**Tech Stack:** Python, ChromaDB, local SQLite graph store, optional Neo4j export, vanilla HTML/JS current console, pytest.

---

## Repository Policy

- Do not commit `.json` files. `.gitignore` must contain `*.json`.
- New JSON input path should be local-only: `data_pipeline/raw/private_json/`.
- Runtime ChromaDB and graph database outputs stay local-only under `storage_layer/runtime/`.
- Public demo artifacts should use `.md`, `.csv`, `.html`, `.svg`, or `.yaml`, not `.json`.

## Module/File Map

- `configs/label_text_filter_rules.yaml`: public rule config for deciding which annotated text can enter ChromaDB.
- `configs/kg_schema.yaml`: public schema for entity types, relation types, evidence fields, and relation direction.
- `data_pipeline/json_ingest/models.py`: dataclasses for JSON input records, text candidates, filtered blocks, and reports.
- `data_pipeline/json_ingest/parser.py`: parse Label Studio style JSON files into normalized text candidates.
- `data_pipeline/json_ingest/filter_rules.py`: apply annotation feedback rules before vector-store ingestion.
- `data_pipeline/json_ingest/chroma_ingest.py`: write filtered chunks into ChromaDB with stable metadata.
- `scripts/ingest_json_batch_to_chroma.py`: CLI for batch JSON ingestion.
- `kg_pipeline/llm_extraction/pipeline.py`: extend existing KG extraction to consume filtered chunks and schema.
- `kg_pipeline/review/queue.py`: create and persist manual review tasks for triples/entities.
- `storage_layer/graph_store.py`: persist entities, relations, evidence, review status, and graph traversal helpers.
- `rag_orchestrator/graphrag_qa.py`: build GraphRAG answer flow: vector retrieval -> graph expansion -> evidence prompt -> LLM.
- `api_server/current_console/server.py`: add local API endpoints for upload, filtering, KG extraction, review, and GraphRAG ask.
- `frontend_app/current_console/index.html`: update UI for batch upload, filtering report, KG review, and graph-aware Q&A.
- `tests/unit/test_json_ingest.py`: parser/filtering tests.
- `tests/unit/test_kg_review_queue.py`: manual review and graph-store update tests.
- `tests/unit/test_graphrag_orchestrator.py`: graph-aware retrieval/answer tests.

---

### Task 1: Keep JSON Private

**Files:**
- Modify: `.gitignore`
- Create: `data_pipeline/raw/private_json/.gitkeep`
- Test: shell verification

- [ ] **Step 1: Verify `.gitignore` blocks JSON**

Run:

```powershell
Select-String -Path .gitignore -Pattern '^\*\.json$'
```

Expected:

```text
*.json
```

- [ ] **Step 2: Create local-only input directory**

Run:

```powershell
New-Item -ItemType Directory -Force -Path data_pipeline/raw/private_json | Out-Null
New-Item -ItemType File -Force -Path data_pipeline/raw/private_json/.gitkeep | Out-Null
```

- [ ] **Step 3: Confirm JSON files will not be staged**

Run:

```powershell
git check-ignore data_pipeline/raw/private_json/sample.json
```

Expected:

```text
data_pipeline/raw/private_json/sample.json
```

---

### Task 2: Add Text Filtering Rules

**Files:**
- Create: `configs/label_text_filter_rules.yaml`
- Test: `tests/unit/test_json_ingest.py`

- [ ] **Step 1: Add rule config**

Create:

```yaml
version: 1
description: "Rules for selecting annotation text before ChromaDB ingestion."
accept_labels:
  - valid_text
  - useful_evidence
  - mechanism_description
  - fault_description
reject_labels:
  - invalid_text
  - table_noise
  - header_footer
  - duplicated
  - unreadable_ocr
minimum_text_chars: 20
maximum_noise_ratio: 0.35
required_fields:
  - text
  - source_file
  - record_id
metadata_fields:
  - source_file
  - page
  - annotator
  - label
  - confidence
```

- [ ] **Step 2: Write failing rule-load test**

Add to `tests/unit/test_json_ingest.py`:

```python
from pathlib import Path
from data_pipeline.json_ingest.filter_rules import load_filter_rules

def test_load_filter_rules():
    rules = load_filter_rules(Path("configs/label_text_filter_rules.yaml"))
    assert "valid_text" in rules.accept_labels
    assert "invalid_text" in rules.reject_labels
    assert rules.minimum_text_chars == 20
```

- [ ] **Step 3: Run test**

Run:

```powershell
pytest tests/unit/test_json_ingest.py::test_load_filter_rules -q
```

Expected: fail because module does not exist.

---

### Task 3: Normalize Batch JSON Into Text Candidates

**Files:**
- Create: `data_pipeline/json_ingest/__init__.py`
- Create: `data_pipeline/json_ingest/models.py`
- Create: `data_pipeline/json_ingest/parser.py`
- Modify: `tests/unit/test_json_ingest.py`

- [ ] **Step 1: Add data models**

Implement:

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class TextCandidate:
    record_id: str
    source_file: str
    text: str
    page: int | None = None
    annotator: str | None = None
    label: str | None = None
    confidence: float | None = None
    evidence_id: str | None = None
    metadata: dict[str, str | int | float | None] = field(default_factory=dict)

@dataclass(frozen=True)
class BatchJsonReport:
    input_files: list[Path]
    candidate_count: int
    accepted_count: int
    rejected_count: int
    rejection_reasons: dict[str, int]
```

- [ ] **Step 2: Add parser test with minimal Label Studio shape**

Add:

```python
from data_pipeline.json_ingest.parser import parse_labelstudio_export

def test_parse_labelstudio_export_extracts_text_candidates(tmp_path):
    path = tmp_path / "sample.json"
    path.write_text(
        """[
          {
            "id": 101,
            "data": {"source_file": "book-a.pdf", "page": 7},
            "annotations": [
              {"completed_by": 3, "result": [
                {"value": {"text": ["燃气轮机燃烧室会出现热声振荡。"], "labels": ["valid_text"]}}
              ]}
            ]
          }
        ]""",
        encoding="utf-8",
    )
    candidates = parse_labelstudio_export(path)
    assert len(candidates) == 1
    assert candidates[0].record_id == "101"
    assert candidates[0].source_file == "book-a.pdf"
    assert candidates[0].page == 7
    assert candidates[0].label == "valid_text"
```

- [ ] **Step 3: Implement parser with explicit supported shape**

Implement `parse_labelstudio_export(path)` to:

- load a local JSON file;
- require a top-level list;
- read `id`, `data.source_file`, `data.page`;
- read annotation `result[].value.text[0]` and `result[].value.labels[0]`;
- raise `ValueError` with file path and missing field when required fields are absent.

- [ ] **Step 4: Run parser tests**

Run:

```powershell
pytest tests/unit/test_json_ingest.py -q
```

Expected: parser tests pass.

---

### Task 4: Filter Text Before ChromaDB

**Files:**
- Create: `data_pipeline/json_ingest/filter_rules.py`
- Modify: `tests/unit/test_json_ingest.py`

- [ ] **Step 1: Add filtering tests**

Add:

```python
from data_pipeline.json_ingest.models import TextCandidate
from data_pipeline.json_ingest.filter_rules import FilterRules, filter_candidates

def test_filter_candidates_accepts_good_labeled_text():
    candidate = TextCandidate(
        record_id="1",
        source_file="a.pdf",
        text="燃气轮机燃烧室热声振荡通常和燃烧不稳定有关。",
        label="valid_text",
    )
    rules = FilterRules(
        accept_labels={"valid_text"},
        reject_labels={"invalid_text"},
        minimum_text_chars=20,
        maximum_noise_ratio=0.35,
    )
    accepted, rejected = filter_candidates([candidate], rules)
    assert accepted == [candidate]
    assert rejected == []

def test_filter_candidates_rejects_noise_label():
    candidate = TextCandidate(record_id="2", source_file="a.pdf", text="页眉", label="header_footer")
    rules = FilterRules(
        accept_labels={"valid_text"},
        reject_labels={"header_footer"},
        minimum_text_chars=20,
        maximum_noise_ratio=0.35,
    )
    accepted, rejected = filter_candidates([candidate], rules)
    assert accepted == []
    assert rejected[0].reason == "reject_label"
```

- [ ] **Step 2: Implement deterministic filtering**

Filtering rules:

- reject if label in `reject_labels`;
- reject if `len(text.strip()) < minimum_text_chars`;
- accept if label in `accept_labels`;
- reject unknown labels as `unknown_label`, so the team must update rules instead of silently ingesting bad text.

- [ ] **Step 3: Run tests**

Run:

```powershell
pytest tests/unit/test_json_ingest.py -q
```

Expected: all pass.

---

### Task 5: Batch Ingest Into ChromaDB

**Files:**
- Create: `data_pipeline/json_ingest/chroma_ingest.py`
- Create: `scripts/ingest_json_batch_to_chroma.py`
- Modify: `tests/unit/test_json_ingest.py`

- [ ] **Step 1: Add CLI behavior**

CLI command:

```powershell
python scripts/ingest_json_batch_to_chroma.py `
  --input-dir data_pipeline/raw/private_json `
  --rules configs/label_text_filter_rules.yaml `
  --persist-dir storage_layer/runtime/json_chroma `
  --collection gas_turbine_json_filtered
```

Expected outputs:

- local ChromaDB under `storage_layer/runtime/json_chroma`;
- markdown report under `data_pipeline/reports/json_ingest_report.md`;
- no JSON report committed.

- [ ] **Step 2: Implement chunk metadata**

Each Chroma document metadata must include:

```python
{
    "record_id": candidate.record_id,
    "source_file": candidate.source_file,
    "page": candidate.page,
    "label": candidate.label,
    "evidence_id": candidate.evidence_id,
}
```

- [ ] **Step 3: Add smoke test with fake Chroma client**

The test should assert that accepted text becomes a document and rejected text is absent.

- [ ] **Step 4: Run tests**

Run:

```powershell
pytest tests/unit/test_json_ingest.py -q
```

Expected: all pass.

---

### Task 6: Update UI For Batch JSON Upload And Filtering Report

**Files:**
- Modify: `api_server/current_console/server.py`
- Modify: `frontend_app/current_console/index.html`

- [ ] **Step 1: Add backend endpoints**

Endpoints:

```text
POST /api/json-ingest/upload
POST /api/json-ingest/run
GET  /api/json-ingest/report
```

Contract:

- upload accepts local files in browser session;
- run applies filter rules and writes Chroma;
- report returns accepted count, rejected count, and top rejection reasons.

- [ ] **Step 2: Update UI**

Add a Data Ingest panel section:

- "批量 JSON 上传";
- "文本筛选结果";
- "入库 ChromaDB";
- accepted/rejected counters;
- rejection reason table.

- [ ] **Step 3: UI verification**

Run:

```powershell
node tools/verify_console_rag_context.cjs
```

Expected: PASS.

---

### Task 7: Extract KG From Filtered Text

**Files:**
- Create: `configs/kg_schema.yaml`
- Modify: `kg_pipeline/llm_extraction/pipeline.py`
- Create: `tests/unit/test_kg_extraction_from_filtered_chunks.py`

- [ ] **Step 1: Add KG schema**

Create:

```yaml
version: 1
entity_types:
  - Equipment
  - Component
  - Fault
  - Cause
  - Symptom
  - Mechanism
  - Method
relation_types:
  causes:
    head: Cause
    tail: Fault
  has_symptom:
    head: Fault
    tail: Symptom
  occurs_in:
    head: Fault
    tail: Component
  belongs_to:
    head: Component
    tail: Equipment
  explained_by:
    head: Fault
    tail: Mechanism
evidence_required: true
```

- [ ] **Step 2: Add extraction test**

Test that extraction output refuses triples without evidence and refuses relation names outside schema.

- [ ] **Step 3: Implement schema-bound extraction**

Update pipeline to:

- read filtered chunks from Chroma;
- pass schema to LLM prompt;
- parse returned triples;
- validate entity type, relation type, direction, and evidence;
- write valid triples to graph store;
- write invalid triples to review queue.

- [ ] **Step 4: Run KG tests**

Run:

```powershell
pytest tests/unit/test_llm_kg_extraction.py tests/unit/test_kg_extraction_from_filtered_chunks.py -q
```

Expected: all pass.

---

### Task 8: Add Manual Review Queue

**Files:**
- Create: `kg_pipeline/review/queue.py`
- Modify: `storage_layer/graph_store.py`
- Create: `tests/unit/test_kg_review_queue.py`

- [ ] **Step 1: Define review states**

States:

```text
pending
accepted
rejected
edited
needs_schema_update
```

- [ ] **Step 2: Add review queue functions**

Functions:

```python
create_review_task(triple, evidence, reason) -> str
list_review_tasks(status="pending") -> list[ReviewTask]
apply_review_decision(task_id, decision, edited_triple=None) -> None
```

- [ ] **Step 3: Add graph-store update behavior**

Rules:

- accepted triples become active graph edges;
- rejected triples remain stored for audit but are not retrieved;
- edited triples create a new active edge and keep original evidence.

- [ ] **Step 4: Run review tests**

Run:

```powershell
pytest tests/unit/test_kg_review_queue.py tests/unit/test_graph_store.py -q
```

Expected: all pass.

---

### Task 9: Build GraphRAG Retrieval And Answering

**Files:**
- Modify: `retrieval_engine/hybrid.py`
- Modify: `rag_orchestrator/graphrag_qa.py`
- Create: `tests/unit/test_graphrag_end_to_end.py`

- [ ] **Step 1: Define retrieval flow**

Flow:

```text
question
-> Chroma vector search for candidate chunks
-> entity linking from question and chunks
-> graph expansion for 1-hop or 2-hop neighbors
-> merge vector evidence + graph evidence
-> LLM answer with citations
```

- [ ] **Step 2: Add end-to-end test**

Use a small in-memory graph:

```text
热声振荡 --occurs_in--> 燃烧室
燃烧不稳定 --causes--> 热声振荡
```

Question:

```text
燃烧室为什么可能出现热声振荡？
```

Expected answer must cite both:

- vector text evidence;
- graph relation evidence.

- [ ] **Step 3: Implement answer guard**

If neither Chroma nor graph returns evidence, the system must not call LLM and must return:

```text
没有从本地知识库检索到可用证据，已停止回答。
```

- [ ] **Step 4: Run GraphRAG tests**

Run:

```powershell
pytest tests/unit/test_graphrag_orchestrator.py tests/unit/test_graphrag_end_to_end.py -q
```

Expected: all pass.

---

### Task 10: Update UI For KG Review And GraphRAG

**Files:**
- Modify: `api_server/current_console/server.py`
- Modify: `frontend_app/current_console/index.html`

- [ ] **Step 1: Add backend endpoints**

Endpoints:

```text
POST /api/kg/extract
GET  /api/kg/review/tasks
POST /api/kg/review/decision
GET  /api/kg/graph
POST /api/graphrag/ask
```

- [ ] **Step 2: Add UI states**

UI must show:

- extracted triples;
- entity/relation/evidence;
- approve/reject/edit buttons;
- graph preview;
- GraphRAG answer with citations.

- [ ] **Step 3: Verify UI**

Run:

```powershell
node tools/verify_console_rag_context.cjs
```

Expected: PASS.

---

### Task 11: Final Acceptance Checklist

- [ ] Batch upload 2 or more JSON files from local folder.
- [ ] Filtering report shows accepted/rejected text and rejection reasons.
- [ ] Accepted text is queryable from ChromaDB.
- [ ] KG extraction produces schema-valid triples with evidence.
- [ ] Manual review can accept, reject, and edit triples.
- [ ] Graph store persists active and rejected triples separately.
- [ ] GraphRAG answer uses Chroma evidence and graph evidence.
- [ ] UI shows the whole path: JSON -> filter -> Chroma -> KG -> review -> GraphRAG answer.
- [ ] `git ls-files *.json **/*.json` returns no tracked JSON files.
- [ ] Core tests pass:

```powershell
pytest tests/unit/test_json_ingest.py `
  tests/unit/test_llm_kg_extraction.py `
  tests/unit/test_graph_store.py `
  tests/unit/test_kg_review_queue.py `
  tests/unit/test_graphrag_orchestrator.py `
  tests/unit/test_graphrag_end_to_end.py -q
```

---

## Delivery Message To Teacher

```text
我这边准备按新的标注 JSON 继续补完整流程：先做批量 JSON 上传和入库前文本筛选，把标注人员反馈固化成规则，再入 ChromaDB；筛选后的文本再做实体关系抽取，并保留 evidence 和人工判定入口；人工确认后的关系进入本地图谱存储；最后把文本检索和图谱检索合起来做 GraphRAG 问答。JSON 原始文件不放 GitHub，只放代码、规则、页面和可复现实验说明。
```

