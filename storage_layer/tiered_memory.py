"""Tiered conversation memory: recent turns in SQLite + summaries in Chroma."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .conversation_memory import ConversationMemoryStore, MemoryMessage, MemorySummary
from .memory_vector_store import ConversationMemoryVectorStore, MemoryVectorHit


RECENT_MESSAGE_LIMIT = 8
SUMMARIZE_BATCH_SIZE = 4
VECTOR_TOP_K = 3


@dataclass(frozen=True, slots=True)
class MemoryContext:
    recent_messages: list[MemoryMessage]
    memory_summaries: list[dict[str, Any]]
    summary_count: int
    message_count: int


class TieredMemoryService:
    """Working memory (recent raw turns) + long-term memory (summaries + vector search)."""

    def __init__(
        self,
        store: ConversationMemoryStore,
        vector_store: ConversationMemoryVectorStore | None = None,
        *,
        recent_limit: int = RECENT_MESSAGE_LIMIT,
        summarize_batch: int = SUMMARIZE_BATCH_SIZE,
    ) -> None:
        self.store = store
        self.vector_store = vector_store
        self.recent_limit = max(2, int(recent_limit))
        self.summarize_batch = max(2, int(summarize_batch))

    def append_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        *,
        user_metadata: dict[str, Any] | None = None,
        assistant_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.store.ensure_session(session_id)
        user_message = self.store.append_message(
            session_id,
            "user",
            user_text,
            metadata=user_metadata,
        )
        assistant_message = self.store.append_message(
            session_id,
            "assistant",
            assistant_text,
            metadata=assistant_metadata,
        )
        created_summary = self._maybe_compact(session_id)
        return {
            "user_message_id": user_message.id,
            "assistant_message_id": assistant_message.id,
            "summary_created": created_summary is not None,
            "summary_id": created_summary.id if created_summary else None,
        }

    def get_context(
        self,
        session_id: str,
        query: str = "",
        *,
        recent_limit: int | None = None,
        vector_top_k: int = VECTOR_TOP_K,
    ) -> MemoryContext:
        limit = recent_limit or self.recent_limit
        recent = self.store.list_messages(session_id, limit=limit)
        summary_count = len(self.store.list_summaries(session_id, limit=100))
        message_count = self.store.count_messages(session_id)

        vector_hits: list[MemoryVectorHit] = []
        if self.vector_store and str(query or "").strip():
            vector_hits = self.vector_store.search(
                query,
                session_id=session_id,
                top_k=vector_top_k,
            )

        if vector_hits:
            memory_summaries = [
                {
                    "content": hit.content,
                    "score": hit.score,
                    "vector_id": hit.vector_id,
                    "source": "vector",
                }
                for hit in vector_hits
                if hit.content.strip()
            ]
        else:
            memory_summaries = [
                {
                    "content": item.content,
                    "score": 0.0,
                    "vector_id": item.vector_id,
                    "source": "sqlite",
                }
                for item in self.store.list_summaries(session_id, limit=2)
            ]

        return MemoryContext(
            recent_messages=recent,
            memory_summaries=memory_summaries,
            summary_count=summary_count,
            message_count=message_count,
        )

    def clear_session(self, session_id: str) -> dict[str, int]:
        deleted_messages = self.store.clear_session(session_id)
        deleted_vectors = 0
        if self.vector_store:
            deleted_vectors = self.vector_store.delete_session(session_id)
        return {"deleted_messages": deleted_messages, "deleted_vectors": deleted_vectors}

    def delete_session(self, session_id: str) -> None:
        if self.vector_store:
            self.vector_store.delete_session(session_id)
        self.store.delete_session(session_id)

    def _maybe_compact(self, session_id: str) -> MemorySummary | None:
        messages = self.store.list_messages(session_id, limit=500)
        if len(messages) <= self.recent_limit + self.summarize_batch:
            return None

        last_summarized_id = self.store.get_last_summarized_message_id(session_id)
        pending = [item for item in messages if item.id > last_summarized_id]
        if len(pending) <= self.recent_limit:
            return None

        batch = pending[: len(pending) - self.recent_limit][: self.summarize_batch]
        if len(batch) < self.summarize_batch:
            return None

        summary_text = self._build_extractive_summary(batch)
        vector_id = f"mem_{session_id}_{batch[-1].id}"
        summary = self.store.add_summary(
            session_id,
            summary_text,
            [item.id for item in batch],
            vector_id=vector_id,
        )
        self.store.set_last_summarized_message_id(session_id, batch[-1].id)
        if self.vector_store:
            self.vector_store.upsert_summary(
                vector_id,
                summary_text,
                session_id=session_id,
                summary_id=summary.id,
            )
        return summary

    @staticmethod
    def _build_extractive_summary(messages: list[MemoryMessage]) -> str:
        lines = ["【对话摘要】"]
        turn = 0
        idx = 0
        while idx < len(messages):
            turn += 1
            user = messages[idx]
            idx += 1
            assistant = messages[idx] if idx < len(messages) else None
            if idx < len(messages):
                idx += 1
            if user.role == "user":
                lines.append(f"- 第{turn}轮问：{user.content[:220]}")
            if assistant and assistant.role == "assistant":
                lines.append(f"  答：{assistant.content[:420]}")
        return "\n".join(lines)
