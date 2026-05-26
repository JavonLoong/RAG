"""GraphRAG-specific API routes.

Extracted from the monolithic api.py (as recommended by the evaluation report)
to provide a modular route structure. These routes expose the new GraphRAG
capabilities: community detection, global search, and evaluation.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

router = APIRouter(prefix="/api/graphrag", tags=["graphrag"])


# ── Pydantic Models ──────────────────────────────────────────────


class CommunityDetectionRequest(BaseModel):
    graph_db_path: str = Field(..., description="Path to the SQLite graph database")
    resolution: float = Field(default=1.0, description="Louvain resolution (higher = more communities)")
    level: int = Field(default=0, description="Hierarchical level for the detection")


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
    max_communities: int = Field(default=20, description="Maximum communities to include")


class GraphStatsRequest(BaseModel):
    graph_db_path: str = Field(..., description="Path to the SQLite graph database")


# ── Routes ───────────────────────────────────────────────────────


@router.post("/community/detect", response_model=CommunityDetectionResponse)
async def detect_communities(payload: CommunityDetectionRequest):
    """Run Louvain community detection on the knowledge graph."""
    try:
        from kg_pipeline.community_detection import run_louvain_detection
        from storage_layer.graph_store import GraphStore

        db_path = Path(payload.graph_db_path)
        if not db_path.exists():
            raise HTTPException(status_code=404, detail=f"Graph database not found: {payload.graph_db_path}")

        store = GraphStore(db_path)
        store.initialize(reset=False)
        result = run_louvain_detection(
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
async def summarize_communities(payload: GlobalSearchRequest):
    """Generate summaries for detected communities using LLM."""
    try:
        from kg_pipeline.community_summary import summarize_communities as _summarize
        from model_adapters.llm import OpenAICompatibleLLMClient
        from storage_layer.graph_store import GraphStore

        db_path = Path(payload.graph_db_path)
        if not db_path.exists():
            raise HTTPException(status_code=404, detail=f"Graph database not found: {payload.graph_db_path}")

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
async def global_search(payload: GlobalSearchRequest):
    """Execute global search over community summaries (map-reduce)."""
    try:
        from model_adapters.llm import OpenAICompatibleLLMClient
        from rag_orchestrator.global_search import GlobalSearchOrchestrator
        from storage_layer.graph_store import GraphStore

        db_path = Path(payload.graph_db_path)
        if not db_path.exists():
            raise HTTPException(status_code=404, detail=f"Graph database not found: {payload.graph_db_path}")

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
async def graph_stats(payload: GraphStatsRequest):
    """Get knowledge graph statistics including community info."""
    try:
        from storage_layer.graph_store import GraphStore

        db_path = Path(payload.graph_db_path)
        if not db_path.exists():
            raise HTTPException(status_code=404, detail=f"Graph database not found: {payload.graph_db_path}")

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


@router.get("/communities")
async def list_communities(graph_db_path: str, level: int = 0):
    """List all detected communities and their summaries."""
    try:
        from storage_layer.graph_store import GraphStore

        db_path = Path(graph_db_path)
        if not db_path.exists():
            raise HTTPException(status_code=404, detail=f"Graph database not found: {graph_db_path}")

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
