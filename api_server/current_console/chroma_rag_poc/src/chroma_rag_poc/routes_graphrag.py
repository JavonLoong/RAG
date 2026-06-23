"""GraphRAG-specific API routes.

Extracted from the monolithic api.py (as recommended by the evaluation report)
to provide a modular route structure. These routes expose the new GraphRAG
capabilities: community detection, global search, and evaluation.
"""
from __future__ import annotations

import io
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from kg_pipeline.community_summary import build_summary_sentence_evidence
from rag_orchestrator.triage import GraphRagTriageStore

router = APIRouter(prefix="/api/graphrag", tags=["graphrag"])
GRAPH_DB_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def _graph_allowed_roots(request: Request) -> list[Path]:
    roots = [_REPO_ROOT]
    for state_name in ("persist_dir", "upload_dir"):
        state_path = getattr(request.app.state, state_name, None)
        if state_path is None:
            continue
        path = Path(state_path).resolve()
        roots.append(path)
        roots.append(path.parent)

    unique_roots: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique_roots.append(root)
    return unique_roots


def _relative_graph_roots(request: Request) -> list[Path]:
    roots: list[Path] = []
    for state_name in ("persist_dir", "upload_dir"):
        state_path = getattr(request.app.state, state_name, None)
        if state_path is not None:
            roots.append(Path(state_path).resolve())
    roots.append(_REPO_ROOT)

    unique_roots: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            unique_roots.append(root)
    return unique_roots


def _candidate_graph_db_paths(request: Request, raw_path: str) -> list[Path]:
    requested = Path(str(raw_path).strip()).expanduser()
    if requested.is_absolute():
        return [requested.resolve()]
    return [(root / requested).resolve() for root in _relative_graph_roots(request)]


def _validate_graph_db_path(request: Request, db_path: Path) -> None:
    if db_path.suffix.lower() not in GRAPH_DB_SUFFIXES:
        raise HTTPException(status_code=400, detail="Graph database path must point to a SQLite .db/.sqlite file")
    allowed_roots = _graph_allowed_roots(request)
    if not any(db_path.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=400, detail="Graph database path is outside the allowed runtime roots")


def _resolve_graph_db_path(request: Request, raw_path: str) -> Path:
    if not raw_path or not str(raw_path).strip():
        raise HTTPException(status_code=400, detail="Graph database path is required")

    candidates = _candidate_graph_db_paths(request, raw_path)
    for db_path in candidates:
        _validate_graph_db_path(request, db_path)
        if db_path.exists() and db_path.is_file():
            return db_path
        if db_path.exists() and not db_path.is_file():
            raise HTTPException(status_code=400, detail="Graph database path must be a file")

    db_path = candidates[0]
    _validate_graph_db_path(request, db_path)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Graph database not found: {raw_path}")
    if not db_path.is_file():
        raise HTTPException(status_code=400, detail="Graph database path must be a file")
    return db_path


def _sqlite_database_files(db_path: Path) -> list[Path]:
    return [
        db_path,
        Path(str(db_path) + "-wal"),
        Path(str(db_path) + "-shm"),
        Path(str(db_path) + "-journal"),
    ]


def _edge_evidence_text(edge: Any) -> str:
    return str(getattr(edge, "evidence", "") or "").strip()


def _edge_triple_id(edge: Any) -> str:
    return str(getattr(edge, "triple_id", "") or "").strip()


def _edge_to_summary_dict(edge: Any) -> dict[str, str]:
    return {
        "triple_id": _edge_triple_id(edge),
        "subject": str(getattr(edge, "subject", "") or ""),
        "predicate": str(getattr(edge, "predicate", "") or ""),
        "object": str(getattr(edge, "object_name", "") or ""),
        "evidence": _edge_evidence_text(edge),
        "source_file": str(getattr(edge, "source_file", "") or ""),
        "source_page": str(getattr(edge, "source_page", "") or ""),
        "source_chunk_id": str(getattr(edge, "source_chunk_id", "") or ""),
    }


def _normalize_import_edges(edges: list[Any]) -> list[Any]:
    normalized: list[Any] = []
    for edge in edges:
        confidence = getattr(edge, "confidence", None)
        if confidence is None and _edge_evidence_text(edge):
            confidence = 0.78
        normalized.append(replace(edge, confidence=confidence))
    return normalized


def _fallback_component_assignments(edges: list[Any]) -> list[dict[str, str]]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        subject = str(getattr(edge, "subject", "") or "").strip()
        obj = str(getattr(edge, "object_name", "") or "").strip()
        if not subject or not obj:
            continue
        adjacency.setdefault(subject, set()).add(obj)
        adjacency.setdefault(obj, set()).add(subject)

    visited: set[str] = set()
    components: list[list[str]] = []
    for node in sorted(adjacency):
        if node in visited:
            continue
        stack = [node]
        component: list[str] = []
        visited.add(node)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency.get(current, ())):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)
        components.append(sorted(component))

    components.sort(key=lambda item: (-len(item), item[0] if item else ""))
    assignments: list[dict[str, str]] = []
    for index, nodes in enumerate(components):
        community_id = f"C{index}"
        assignments.extend({"community_id": community_id, "node_name": node} for node in nodes)
    return assignments


def _detect_import_communities(store: Any, edges: list[Any], *, reset_level: bool) -> list[dict[str, str]]:
    try:
        from kg_pipeline.community_detection import run_leiden_detection

        result = run_leiden_detection(store, resolution=0.7, level=0)
        assignments = [
            {"community_id": item.community_id, "node_name": item.node_name}
            for item in getattr(result, "assignments", [])
        ]
        if assignments:
            return assignments
    except Exception:
        pass

    assignments = _fallback_component_assignments(edges)
    if assignments:
        store.store_communities(assignments, level=0, reset_level=reset_level)
    return assignments


def _store_import_community_summaries(store: Any, edges: list[Any], assignments: list[dict[str, str]], *, reset_level: bool) -> None:
    if not assignments:
        return

    community_by_node = {
        str(item["node_name"]): str(item["community_id"])
        for item in assignments
        if str(item.get("node_name") or "").strip()
    }
    nodes_by_community: dict[str, set[str]] = {}
    for node, community_id in community_by_node.items():
        nodes_by_community.setdefault(community_id, set()).add(node)

    edges_by_community: dict[str, list[Any]] = {community_id: [] for community_id in nodes_by_community}
    for edge in edges:
        source_community = community_by_node.get(str(getattr(edge, "subject", "") or ""))
        target_community = community_by_node.get(str(getattr(edge, "object_name", "") or ""))
        if source_community and source_community == target_community:
            edges_by_community.setdefault(source_community, []).append(edge)

    summaries: list[dict[str, Any]] = []
    for community_id, members in sorted(nodes_by_community.items(), key=lambda item: (-len(item[1]), item[0])):
        community_edges = edges_by_community.get(community_id, [])
        relation_counts: dict[str, int] = {}
        for edge in community_edges:
            predicate = str(getattr(edge, "predicate", "") or "RELATES_TO")
            relation_counts[predicate] = relation_counts.get(predicate, 0) + 1

        top_members = sorted(members)[:12]
        triple_lines = [
            f"- {edge.subject} --{edge.predicate}--> {edge.object_name}"
            for edge in community_edges[:20]
        ]
        relation_line = ", ".join(f"{name}:{count}" for name, count in sorted(relation_counts.items())) or "none"
        summary = "\n".join(
            [
                f"Community {community_id} contains {len(members)} entities and {len(community_edges)} internal relationships.",
                f"Top entities: {', '.join(top_members) if top_members else 'none'}.",
                f"Relationship type counts: {relation_line}.",
                "Representative triples:",
                *(triple_lines or ["- none"]),
            ]
        )
        edge_dicts = [_edge_to_summary_dict(edge) for edge in community_edges]
        evidence_edges = [edge for edge in edge_dicts if edge.get("triple_id") and edge.get("evidence")]
        evidence_triple_ids = [edge["triple_id"] for edge in evidence_edges]
        evidence_sample = evidence_edges[:200]
        summaries.append(
            {
                "community_id": community_id,
                "title": f"Community {community_id}",
                "summary": summary,
                "entity_count": len(members),
                "edge_count": len(community_edges),
                "metadata": {
                    "evidence_triple_ids": evidence_triple_ids[:500],
                    "source": "browser_graph_import",
                    "sentence_evidence": build_summary_sentence_evidence(summary, evidence_sample),
                },
            }
        )

    store.store_community_summaries(summaries, level=0, reset_level=reset_level)


def _resolve_graph_db_output_path(request: Request, raw_path: str) -> Path:
    if not raw_path or not str(raw_path).strip():
        db_path = (Path(request.app.state.persist_dir) / "graph_store.sqlite").resolve()
    else:
        candidates = _candidate_graph_db_paths(request, raw_path)
        existing = next((candidate for candidate in candidates if candidate.exists()), None)
        db_path = existing or candidates[0]
    _validate_graph_db_path(request, db_path)
    if db_path.exists() and not db_path.is_file():
        raise HTTPException(status_code=400, detail="Graph database path must be a file")
    return db_path


# ── Pydantic Models ──────────────────────────────────────────────


class CommunityDetectionRequest(BaseModel):
    graph_db_path: str = Field(..., description="Path to the SQLite graph database")
    resolution: float = Field(default=1.0, description="Leiden resolution (higher = more communities)")
    level: int = Field(default=0, description="Hierarchical level for the detection")


class GraphImportRequest(BaseModel):
    graph_db_path: str = Field(default="", description="Optional SQLite graph database output path")
    graph: dict[str, Any] | None = Field(default=None, description="Browser graph snapshot with nodes and links")
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
    reset: bool = True
    preserve_isolated_nodes: bool = Field(default=False, description="Keep nodes that are not connected by an imported edge")


class GraphResetRequest(BaseModel):
    graph_db_path: str = Field(default="", description="Optional SQLite graph database path to remove")


class CommunityDetectionResponse(BaseModel):
    total_nodes: int
    total_edges: int
    num_communities: int
    level: int
    community_sizes: dict[str, int]


class GlobalSearchRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question to answer")
    graph_db_path: str = Field(..., description="Path to the SQLite graph database")
    llm_api_key: str = Field(default="", description="LLM API key")
    llm_base_url: str = Field(default="https://api.openai.com/v1", description="LLM base URL")
    llm_model: str = Field(default="gpt-4.1-mini", description="LLM model name")
    level: int = Field(default=0, description="Community hierarchy level to search")
    max_communities: int = Field(default=100, ge=1, le=100, description="Maximum communities to include")


class GraphStatsRequest(BaseModel):
    graph_db_path: str = Field(..., description="Path to the SQLite graph database")


class TriageReviewRequest(BaseModel):
    review_status: str = Field(..., min_length=1)
    review_note: str = ""


class TriagePromoteRequest(BaseModel):
    expected_evidence_keywords: list[str] = Field(default_factory=list)
    reference_answer: str = ""
    grading_notes: str = ""


# ── Routes ───────────────────────────────────────────────────────


def _triage_store(request: Request) -> GraphRagTriageStore:
    persist_dir = Path(getattr(request.app.state, "persist_dir"))
    return GraphRagTriageStore(persist_dir / "graphrag_triage.jsonl")


def _triage_regression_dataset_path(request: Request) -> Path:
    persist_dir = Path(getattr(request.app.state, "persist_dir"))
    path = persist_dir / "evaluation" / "graphrag_triage_regression.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _sanitize_case_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value).strip("_")
    return safe or "graphrag_triage"


def _expected_mode_from_route(record: dict[str, Any]) -> str:
    strategy = str((record.get("route") or {}).get("strategy") or record.get("strategy") or "").lower()
    if "global" in strategy:
        return "global"
    if "local" in strategy:
        return "local"
    if "vector" in strategy:
        return "vector"
    if "aggregation" in strategy:
        return "aggregation"
    return "graph"


def _fallback_keywords(question: str) -> list[str]:
    words = ["".join(ch for ch in part if ch.isalnum()) for part in str(question or "").split()]
    keywords = [word for word in words if len(word) >= 3]
    return keywords[:5] or ["GraphRAG"]


def _build_triage_regression_case(record: dict[str, Any], payload: TriagePromoteRequest) -> dict[str, Any]:
    from evaluation import RAGEvaluationCase

    keywords = [str(item).strip() for item in payload.expected_evidence_keywords if str(item).strip()]
    if not keywords:
        keywords = _fallback_keywords(str(record.get("question") or ""))
    notes = [
        f"promoted_from={record.get('id')}",
        f"graph_quality_status={record.get('graph_quality_status')}",
        f"review_status={record.get('review_status')}",
    ]
    if record.get("review_note"):
        notes.append(f"review_note={record.get('review_note')}")
    if payload.grading_notes.strip():
        notes.append(payload.grading_notes.strip())
    case = RAGEvaluationCase(
        id=f"triage_{_sanitize_case_id(str(record.get('id') or ''))}",
        question=str(record.get("question") or ""),
        reference_answer=payload.reference_answer.strip() or str(record.get("answer_preview") or ""),
        expected_evidence_keywords=keywords,
        task_type="graphrag_triage",
        source_scope=str(record.get("graph_db_path") or "graphrag"),
        grading_notes="; ".join(notes),
        expected_modes=[_expected_mode_from_route(record)],
    )
    return case.to_dataset_record()


@router.get("/triage")
async def list_graphrag_triage(
    request: Request,
    limit: int = 50,
    graph_quality_status: str = "",
    review_status: str = "",
    route_strategy: str = "",
):
    """List recent GraphRAG quality and source-evidence triage records."""
    return {
        "items": _triage_store(request).list(
            limit=limit,
            graph_quality_status=graph_quality_status,
            review_status=review_status,
            route_strategy=route_strategy,
        )
    }


@router.get("/triage/export")
async def export_graphrag_triage(
    request: Request,
    limit: int = 1000,
    graph_quality_status: str = "",
    review_status: str = "",
    route_strategy: str = "",
):
    """Export filtered GraphRAG triage records as newline-delimited JSON."""
    items = _triage_store(request).list(
        limit=limit,
        graph_quality_status=graph_quality_status,
        review_status=review_status,
        route_strategy=route_strategy,
    )
    body = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in items).encode("utf-8")
    buffer = io.BytesIO(body)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        buffer,
        media_type="application/x-ndjson; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="graphrag_triage_{timestamp}.jsonl"'},
    )


@router.get("/triage/analytics")
async def graphrag_triage_analytics(
    request: Request,
    graph_quality_status: str = "",
    review_status: str = "",
    route_strategy: str = "",
):
    """Summarize GraphRAG triage quality, review, route, and failure metrics."""
    return _triage_store(request).analytics(
        graph_quality_status=graph_quality_status,
        review_status=review_status,
        route_strategy=route_strategy,
    )


@router.get("/triage/{triage_id}")
async def get_graphrag_triage(request: Request, triage_id: str):
    record = _triage_store(request).get(triage_id)
    if record is None:
        raise HTTPException(status_code=404, detail="GraphRAG triage record not found")
    return record


@router.post("/triage/{triage_id}/review")
async def review_graphrag_triage(request: Request, triage_id: str, payload: TriageReviewRequest):
    record = _triage_store(request).review(
        triage_id,
        review_status=payload.review_status,
        review_note=payload.review_note,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="GraphRAG triage record not found")
    return record


@router.post("/triage/{triage_id}/promote")
async def promote_graphrag_triage(request: Request, triage_id: str, payload: TriagePromoteRequest):
    store = _triage_store(request)
    record = store.get(triage_id)
    if record is None:
        raise HTTPException(status_code=404, detail="GraphRAG triage record not found")
    case = _build_triage_regression_case(record, payload)
    dataset_path = _triage_regression_dataset_path(request)
    with dataset_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    updated = store.mark_promoted(triage_id, evaluation_case_id=case["id"], dataset_path=dataset_path)
    return {"case": case, "dataset_path": str(dataset_path), "record": updated}


@router.post("/reset")
async def reset_graph_store(request: Request, payload: GraphResetRequest):
    """Remove the runtime SQLite GraphStore and its SQLite sidecar files."""
    db_path = _resolve_graph_db_output_path(request, payload.graph_db_path)
    deleted_files: list[str] = []
    for file_path in _sqlite_database_files(db_path):
        if not file_path.exists():
            continue
        if not file_path.is_file():
            raise HTTPException(status_code=400, detail="Graph database path must be a file")
        try:
            file_path.unlink()
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail="Graph database is currently in use") from exc
        deleted_files.append(str(file_path))
    return {
        "graph_db_path": str(db_path),
        "deleted": bool(deleted_files),
        "deleted_files": deleted_files,
    }


@router.post("/import")
async def import_graph_snapshot(request: Request, payload: GraphImportRequest):
    """Import a browser-built graph snapshot into the SQLite GraphStore used by /api/query."""
    try:
        from storage_layer.graph_store import GraphStore, normalize_kg_payload

        graph_payload: dict[str, Any]
        if isinstance(payload.graph, dict):
            graph_payload = payload.graph
        else:
            graph_payload = {"nodes": payload.nodes, "links": payload.links}
        if not isinstance(graph_payload.get("links"), list) and not isinstance(graph_payload.get("triples"), list):
            raise HTTPException(status_code=400, detail="Graph payload must include links or triples")

        db_path = _resolve_graph_db_output_path(request, payload.graph_db_path)
        edges = _normalize_import_edges(normalize_kg_payload(graph_payload))
        if not edges:
            raise HTTPException(status_code=400, detail="Graph payload did not contain importable edges")

        store = GraphStore(db_path)
        summary = store.import_edges(edges, reset=payload.reset)
        if payload.preserve_isolated_nodes and isinstance(graph_payload.get("nodes"), list):
            summary = store.upsert_nodes(graph_payload["nodes"])
        assignments = _detect_import_communities(store, edges, reset_level=payload.reset)
        _store_import_community_summaries(store, edges, assignments, reset_level=payload.reset)
        summary = store.summary()
        return {
            **summary,
            "graph_db_path": str(db_path),
            "imported_edge_count": len(edges),
            "community_count": len({item["community_id"] for item in assignments}),
            "isolated_nodes_preserved": bool(payload.preserve_isolated_nodes),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph import failed: {exc}") from exc


@router.post("/community/detect", response_model=CommunityDetectionResponse)
async def detect_communities(request: Request, payload: CommunityDetectionRequest):
    """Run Leiden community detection on the knowledge graph."""
    try:
        from kg_pipeline.community_detection import run_leiden_detection
        from storage_layer.graph_store import GraphStore

        db_path = _resolve_graph_db_path(request, payload.graph_db_path)
        store = GraphStore(db_path)
        store.initialize(reset=False)
        result = run_leiden_detection(
            store, resolution=payload.resolution, level=payload.level
        )
        return CommunityDetectionResponse(**result.to_dict())
    except HTTPException:
        raise
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"Missing dependency: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Community detection failed: {exc}") from exc


@router.post("/community/summarize")
async def summarize_communities(request: Request, payload: GlobalSearchRequest):
    """Generate summaries for detected communities using LLM."""
    try:
        from kg_pipeline.community_summary import summarize_communities as _summarize
        from model_adapters.llm import OpenAICompatibleLLMClient
        from storage_layer.graph_store import GraphStore

        db_path = _resolve_graph_db_path(request, payload.graph_db_path)
        store = GraphStore(db_path)
        store.initialize(reset=False)

        if not payload.llm_api_key:
            raise HTTPException(status_code=400, detail="LLM API key is required for community summarization")

        llm = OpenAICompatibleLLMClient(
            api_key=payload.llm_api_key,
            base_url=payload.llm_base_url,
            model=payload.llm_model,
        )
        result = _summarize(store, llm, level=payload.level)
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Community summarization failed: {exc}") from exc


@router.post("/search/global")
async def global_search(request: Request, payload: GlobalSearchRequest):
    """Execute global search over community summaries (map-reduce)."""
    try:
        from model_adapters.llm import OpenAICompatibleLLMClient
        from rag_orchestrator.global_search import GlobalSearchOrchestrator
        from storage_layer.graph_store import GraphStore

        db_path = _resolve_graph_db_path(request, payload.graph_db_path)
        store = GraphStore(db_path)
        store.initialize(reset=False)

        if not payload.llm_api_key:
            raise HTTPException(status_code=400, detail="LLM API key is required for global search")

        llm = OpenAICompatibleLLMClient(
            api_key=payload.llm_api_key,
            base_url=payload.llm_base_url,
            model=payload.llm_model,
        )
        searcher = GlobalSearchOrchestrator(
            graph_store=store,
            llm_client=llm,
            max_communities=payload.max_communities,
        )
        result = searcher.search(payload.question, level=payload.level)
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Global search failed: {exc}") from exc


@router.post("/stats")
async def graph_stats(request: Request, payload: GraphStatsRequest):
    """Get knowledge graph statistics including community info."""
    try:
        from storage_layer.graph_store import GraphStore

        db_path = _resolve_graph_db_path(request, payload.graph_db_path)
        store = GraphStore(db_path)
        store.initialize(reset=False)

        basic_stats = store.summary()

        # Add community stats if available
        community_info = {}
        try:
            communities = store.get_communities(level=0)
            summaries = store.get_community_summaries(level=0)
            community_info = {
                "community_count": len(communities),
                "summary_count": len(summaries),
                "communities": communities[:20],
            }
        except Exception:
            community_info = {"community_count": 0, "summary_count": 0}

        return {**basic_stats, "community_info": community_info}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph stats failed: {exc}") from exc


@router.get("/export")
async def export_graph(request: Request, graph_db_path: str):
    """Export the SQLite knowledge graph as portable JSON."""
    try:
        from storage_layer.graph_store import GraphStore

        db_path = _resolve_graph_db_path(request, graph_db_path)
        store = GraphStore(db_path)
        store.initialize(reset=False)
        payload = store.export_graph()
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        buffer = io.BytesIO(body)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in db_path.stem).strip("_")
        filename = f"graphrag_graph_export_{safe_stem or 'graph'}_{timestamp}.json"
        return StreamingResponse(
            buffer,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph export failed: {exc}") from exc


@router.get("/communities")
async def list_communities(request: Request, graph_db_path: str, level: int = 0):
    """List all detected communities and their summaries."""
    try:
        from storage_layer.graph_store import GraphStore

        db_path = _resolve_graph_db_path(request, graph_db_path)
        store = GraphStore(db_path)
        store.initialize(reset=False)

        communities = store.get_communities(level=level)
        summaries = store.get_community_summaries(level=level)

        # Merge summaries with community data
        summary_map = {s["community_id"]: s for s in summaries}
        result = []
        for comm in communities:
            cid = comm["community_id"]
            entry = {**comm}
            if cid in summary_map:
                entry["title"] = summary_map[cid].get("title", "")
                entry["summary"] = summary_map[cid].get("summary", "")
                entry["edge_count"] = summary_map[cid].get("edge_count", 0)
            result.append(entry)

        return {"level": level, "communities": result, "total": len(result)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"List communities failed: {exc}") from exc
