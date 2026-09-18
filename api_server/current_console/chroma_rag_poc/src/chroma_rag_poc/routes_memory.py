"""Conversation memory API for multi-turn RAG Q&A."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from storage_layer.conversation_memory import ConversationMemoryStore
from storage_layer.memory_vector_store import ConversationMemoryVectorStore
from storage_layer.tiered_memory import TieredMemoryService

router = APIRouter(prefix="/api/memory", tags=["memory"])


class EnsureSessionRequest(BaseModel):
    session_id: str | None = None
    title: str = ""


class AppendMessageRequest(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AppendTurnRequest(BaseModel):
    user: str = Field(..., min_length=1)
    assistant: str = Field(..., min_length=1)
    user_metadata: dict[str, Any] = Field(default_factory=dict)
    assistant_metadata: dict[str, Any] = Field(default_factory=dict)


def _store(request: Request) -> ConversationMemoryStore:
    db_path = getattr(request.app.state, "memory_db_path", None)
    if not db_path:
        raise HTTPException(status_code=500, detail="对话记忆存储未配置")
    store = ConversationMemoryStore(db_path)
    store.initialize()
    return store


def _vector_store(request: Request) -> ConversationMemoryVectorStore | None:
    persist_dir = getattr(request.app.state, "memory_vector_persist_dir", None)
    if not persist_dir:
        return None
    vector_store = ConversationMemoryVectorStore(persist_dir)
    vector_store.initialize()
    return vector_store


def _service(request: Request) -> TieredMemoryService:
    return TieredMemoryService(_store(request), _vector_store(request))


def _message_payload(message: Any) -> dict[str, Any]:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "metadata": message.metadata,
        "created_at": message.created_at,
    }


def _context_payload(context: Any) -> dict[str, Any]:
    return {
        "recent_messages": [_message_payload(item) for item in context.recent_messages],
        "memory_summaries": context.memory_summaries,
        "summary_count": context.summary_count,
        "message_count": context.message_count,
    }


@router.post("/sessions")
async def ensure_session(request: Request, payload: EnsureSessionRequest):
    store = _store(request)
    session_id = store.ensure_session(payload.session_id, title=payload.title)
    return {"session_id": session_id, "status": "ok"}


@router.get("/sessions")
async def list_sessions(request: Request, limit: int = 20):
    store = _store(request)
    return {"sessions": store.list_sessions(limit=limit)}


@router.get("/sessions/{session_id}/messages")
async def list_messages(request: Request, session_id: str, limit: int = 20):
    store = _store(request)
    if not store.session_exists(session_id):
        return {"session_id": session_id, "messages": []}
    messages = store.list_messages(session_id, limit=limit)
    return {
        "session_id": session_id,
        "messages": [_message_payload(item) for item in messages],
    }


@router.get("/sessions/{session_id}/context")
async def get_memory_context(
    request: Request,
    session_id: str,
    query: str = "",
    recent_limit: int = 8,
):
    service = _service(request)
    if not service.store.session_exists(session_id):
        return {
            "session_id": session_id,
            "recent_messages": [],
            "memory_summaries": [],
            "summary_count": 0,
            "message_count": 0,
        }
    context = service.get_context(session_id, query, recent_limit=recent_limit)
    payload = _context_payload(context)
    payload["session_id"] = session_id
    return payload


@router.post("/sessions/{session_id}/messages")
async def append_message(request: Request, session_id: str, payload: AppendMessageRequest):
    store = _store(request)
    store.ensure_session(session_id)
    try:
        message = store.append_message(
            session_id,
            payload.role,
            payload.content,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": _message_payload(message)}


@router.post("/sessions/{session_id}/turns")
async def append_turn(request: Request, session_id: str, payload: AppendTurnRequest):
    service = _service(request)
    service.store.ensure_session(session_id)
    try:
        result = service.append_turn(
            session_id,
            payload.user,
            payload.assistant,
            user_metadata=payload.user_metadata,
            assistant_metadata=payload.assistant_metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    context = service.get_context(session_id, payload.user)
    return {
        "session_id": session_id,
        "turn": result,
        "context": _context_payload(context),
    }


@router.delete("/sessions/{session_id}/messages")
async def clear_messages(request: Request, session_id: str):
    service = _service(request)
    if not service.store.session_exists(session_id):
        return {"session_id": session_id, "deleted": 0, "deleted_vectors": 0}
    result = service.clear_session(session_id)
    return {"session_id": session_id, **result}


@router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: str):
    service = _service(request)
    if service.store.session_exists(session_id):
        service.delete_session(session_id)
    return {"session_id": session_id, "status": "deleted"}
