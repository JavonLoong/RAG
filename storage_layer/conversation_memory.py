"""SQLite-backed multi-turn conversation memory for RAG Q&A sessions."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True, slots=True)
class MemoryMessage:
    id: int
    session_id: str
    role: str
    content: str
    metadata: dict[str, Any]
    created_at: str


@dataclass(frozen=True, slots=True)
class MemorySummary:
    id: int
    session_id: str
    content: str
    source_message_ids: list[int]
    vector_id: str
    created_at: str


class ConversationMemoryStore:
    """Persist chat turns per session on disk (default under runtime/memory/)."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, id);

                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    source_message_ids_json TEXT NOT NULL DEFAULT '[]',
                    vector_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_summaries_session
                    ON summaries(session_id, id);
                """
            )
            self._ensure_session_columns(connection)

    def _ensure_session_columns(self, connection: sqlite3.Connection) -> None:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "last_summarized_message_id" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN last_summarized_message_id INTEGER NOT NULL DEFAULT 0"
            )

    def create_session(self, *, title: str = "", session_id: str | None = None) -> str:
        sid = (session_id or "").strip() or str(uuid.uuid4())
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = CASE
                        WHEN excluded.title != '' THEN excluded.title
                        ELSE sessions.title
                    END,
                    updated_at = excluded.updated_at
                """,
                (sid, title.strip(), now, now),
            )
        return sid

    def touch_session(self, session_id: str, *, title: str | None = None) -> None:
        now = _utc_now()
        with self._connect() as connection:
            if title is not None and title.strip():
                connection.execute(
                    "UPDATE sessions SET updated_at = ?, title = ? WHERE id = ?",
                    (now, title.strip(), session_id),
                )
            else:
                connection.execute(
                    "UPDATE sessions SET updated_at = ? WHERE id = ?",
                    (now, session_id),
                )

    def session_exists(self, session_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM sessions WHERE id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
        return row is not None

    def ensure_session(self, session_id: str | None = None, *, title: str = "") -> str:
        sid = (session_id or "").strip()
        if sid and self.session_exists(sid):
            self.touch_session(sid, title=title)
            return sid
        return self.create_session(title=title, session_id=sid or None)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryMessage:
        if not self.session_exists(session_id):
            self.create_session(session_id=session_id)
        role = role.strip().lower()
        if role not in {"user", "assistant", "system"}:
            raise ValueError(f"Unsupported role: {role}")
        text = str(content or "").strip()
        if not text:
            raise ValueError("Message content cannot be empty")
        now = _utc_now()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO messages (session_id, role, content, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, text, meta_json, now),
            )
            message_id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
        return MemoryMessage(
            id=message_id,
            session_id=session_id,
            role=role,
            content=text,
            metadata=metadata or {},
            created_at=now,
        )

    def list_messages(self, session_id: str, *, limit: int = 20) -> list[MemoryMessage]:
        limit = max(1, min(int(limit), 100))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, role, content, metadata_json, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        messages = [
            MemoryMessage(
                id=int(row[0]),
                session_id=str(row[1]),
                role=str(row[2]),
                content=str(row[3]),
                metadata=json.loads(row[4] or "{}"),
                created_at=str(row[5]),
            )
            for row in rows
        ]
        messages.reverse()
        return messages

    def count_messages(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row[0] or 0)

    def get_last_summarized_message_id(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT last_summarized_message_id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return 0
        return int(row[0] or 0)

    def set_last_summarized_message_id(self, session_id: str, message_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET last_summarized_message_id = ? WHERE id = ?",
                (int(message_id), session_id),
            )

    def add_summary(
        self,
        session_id: str,
        content: str,
        source_message_ids: list[int],
        *,
        vector_id: str,
    ) -> MemorySummary:
        text = str(content or "").strip()
        if not text:
            raise ValueError("Summary content cannot be empty")
        if not source_message_ids:
            raise ValueError("Summary must reference at least one message")
        now = _utc_now()
        ids_json = json.dumps([int(item) for item in source_message_ids], ensure_ascii=False)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO summaries (
                    session_id, content, source_message_ids_json, vector_id, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, text, ids_json, vector_id.strip(), now),
            )
            summary_id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
        return MemorySummary(
            id=summary_id,
            session_id=session_id,
            content=text,
            source_message_ids=[int(item) for item in source_message_ids],
            vector_id=vector_id.strip(),
            created_at=now,
        )

    def list_summaries(self, session_id: str, *, limit: int = 20) -> list[MemorySummary]:
        limit = max(1, min(int(limit), 100))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, content, source_message_ids_json, vector_id, created_at
                FROM summaries
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        summaries = [
            MemorySummary(
                id=int(row[0]),
                session_id=str(row[1]),
                content=str(row[2]),
                source_message_ids=json.loads(row[3] or "[]"),
                vector_id=str(row[4]),
                created_at=str(row[5]),
            )
            for row in rows
        ]
        summaries.reverse()
        return summaries

    def clear_summaries(self, session_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM summaries WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                """
                UPDATE sessions
                SET last_summarized_message_id = 0, updated_at = ?
                WHERE id = ?
                """,
                (_utc_now(), session_id),
            )
        return int(cursor.rowcount)

    def clear_session(self, session_id: str) -> int:
        now = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM summaries WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                """
                UPDATE sessions
                SET updated_at = ?, last_summarized_message_id = 0
                WHERE id = ?
                """,
                (now, session_id),
            )
        return int(cursor.rowcount)

    def delete_session(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def list_sessions(self, *, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 50))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count
                FROM sessions s
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "session_id": str(row[0]),
                "title": str(row[1] or ""),
                "created_at": str(row[2]),
                "updated_at": str(row[3]),
                "message_count": int(row[4] or 0),
            }
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
