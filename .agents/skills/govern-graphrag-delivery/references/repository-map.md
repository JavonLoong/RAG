# Repository map

Use this map only for the PowerRAG/RAG repository. Inspect the current branch because paths and behavior may evolve.

## Core implementation

The skill package keeps a full copy under `code/`. The workbench imports the same modules from the repository root. Refresh with `python scripts/pack_code.py`.

| Capability | Skill copy | Repo import path |
|---|---|---|
| Shared M2–M5 contracts | `code/core_domain/delivery.py` | `core_domain/delivery.py` |
| Document intake and parser routing | `code/data_pipeline/document_intake.py` | `data_pipeline/document_intake.py` |
| External layout parsing | `code/data_pipeline/external_document_parsers.py` | `data_pipeline/external_document_parsers.py` |
| Governed SQLite control plane | `code/storage_layer/governance_store.py` | `storage_layer/governance_store.py` |
| Existing retrieval graph store | `code/storage_layer/graph_store.py` | `storage_layer/graph_store.py` |
| FMEA generation and review | `code/rag_orchestrator/fmea.py` | `rag_orchestrator/fmea.py` |
| GraphRAG QA and fallback | `code/rag_orchestrator/graphrag_qa.py` | `rag_orchestrator/graphrag_qa.py` |
| LLM graph extraction component | `code/kg_pipeline/llm_extraction/pipeline.py` | `kg_pipeline/llm_extraction/pipeline.py` |
| Delivery API | `code/api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_delivery.py` | `api_server/current_console/chroma_rag_poc/src/chroma_rag_poc/routes_delivery.py` |
| Minimum FMEA config | `code/configs/fmea/gas_turbine_minimum_v1.yaml` | `configs/fmea/gas_turbine_minimum_v1.yaml` |
| Workflow smoke tests | `code/tests/unit/test_governed_delivery_workflow.py` | `tests/unit/test_governed_delivery_workflow.py` |
| Delivery API smoke tests | `code/tests/unit/test_delivery_api.py` | `tests/unit/test_delivery_api.py` |

## Important architectural distinction

`GovernanceStore` is an audit/control plane. It stores evidence locators, document and graph versions, reviews, FMEA tasks, and feedback separately from the retrieval and graph databases.

Do not assume these integrations exist merely because compatible export shapes exist:

- publishing a canonical document does not necessarily update or rebuild the retrieval index;
- publishing a governed graph does not necessarily import it into `GraphStore`;
- graph candidate creation may still require callers to supply `statements`;
- creating a feedback record does not necessarily re-run M2, M3, or M4.

Verify each integration by tracing executable calls and tests.

## Efficient inspection commands

Prefer commit-tree inspection for remote-branch audits when the worktree is dirty:

```powershell
git status -sb
git rev-parse HEAD
git show --stat --oneline HEAD
git grep -n "create_graph_candidate\|publish_document\|import_edges\|add_feedback" HEAD -- .
```

Inspect public interfaces and tests:

```powershell
rg -n "^class |^def |^async def |@router" `
  core_domain storage_layer rag_orchestrator `
  api_server/current_console/chroma_rag_poc/src tests/unit
```

## Current smoke-test boundary

The focused M2–M5 tests prove a synthetic text-to-FMEA path, review gates, evidence binding, export, version comparison, rollback, and feedback routing. Check the actual tests before reporting broader coverage. Hand-authored triples and a TXT fixture do not prove automatic extraction or real-document acceptance.
