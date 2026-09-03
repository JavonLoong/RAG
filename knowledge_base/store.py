"""SQLite persistence and lifecycle rules for the normative knowledge base."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
from collections import Counter
from collections.abc import Generator, Iterable, Sequence
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .chunking import chunk_document, normalize_blocks, stable_sha256
from .models import (
    BackupArtifact,
    BlockInput,
    DocumentInput,
    DocumentRevision,
    EvidenceLocator,
    KnowledgeBaseError,
    KnowledgeBaseRelease,
    KnowledgeBaseSnapshot,
    PageInput,
    PublishedAsset,
    PublishedDocument,
    QualityIssue,
    QualityReport,
    ReviewDecision,
    RevisionStatus,
    SearchHit,
    StoredChunk,
    VersionDiff,
)

SCHEMA_VERSION = 1
_LATIN_TOKEN = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
_HAN_SEQUENCE = re.compile(r"[\u3400-\u9fff]+")


class KnowledgeBaseStore:
    """Transactional local store with immutable revisions and release snapshots."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS document_revisions (
                    revision_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    revision_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    source_uri TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('candidate','pending_review','published','deprecated')),
                    content_sha256 TEXT NOT NULL,
                    pipeline_fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    review_decision TEXT CHECK(review_decision IN ('approved','rejected')),
                    reviewer TEXT,
                    reviewed_at TEXT,
                    review_comment TEXT,
                    UNIQUE(document_id, revision_number),
                    UNIQUE(document_id, content_sha256, pipeline_fingerprint)
                );

                CREATE TABLE IF NOT EXISTS pages (
                    revision_id TEXT NOT NULL REFERENCES document_revisions(revision_id) ON DELETE CASCADE,
                    page_number INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY(revision_id, page_number)
                );

                CREATE TABLE IF NOT EXISTS blocks (
                    revision_id TEXT NOT NULL REFERENCES document_revisions(revision_id) ON DELETE CASCADE,
                    block_id TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    block_type TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    parent_block_id TEXT,
                    text TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY(revision_id, block_id),
                    FOREIGN KEY(revision_id, page_number) REFERENCES pages(revision_id, page_number)
                );

                CREATE TABLE IF NOT EXISTS assets (
                    revision_id TEXT NOT NULL REFERENCES document_revisions(revision_id) ON DELETE CASCADE,
                    asset_id TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    block_id TEXT,
                    uri TEXT NOT NULL,
                    caption TEXT NOT NULL,
                    checksum TEXT,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY(revision_id, asset_id),
                    FOREIGN KEY(revision_id, page_number) REFERENCES pages(revision_id, page_number)
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL REFERENCES document_revisions(revision_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    term_count INTEGER NOT NULL,
                    evidence_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(revision_id, ordinal)
                );

                CREATE TABLE IF NOT EXISTS chunk_terms (
                    chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
                    term TEXT NOT NULL,
                    term_frequency INTEGER NOT NULL,
                    PRIMARY KEY(chunk_id, term)
                );

                CREATE TABLE IF NOT EXISTS chunk_vectors (
                    chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
                    embedding_model TEXT NOT NULL,
                    dimension INTEGER NOT NULL,
                    vector_json TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(chunk_id, embedding_model)
                );

                CREATE TABLE IF NOT EXISTS reviews (
                    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision_id TEXT NOT NULL REFERENCES document_revisions(revision_id),
                    decision TEXT NOT NULL CHECK(decision IN ('approved','rejected')),
                    reviewer TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS releases (
                    version INTEGER PRIMARY KEY,
                    release_id TEXT NOT NULL UNIQUE,
                    parent_version INTEGER REFERENCES releases(version),
                    action TEXT NOT NULL CHECK(action IN ('publish','deprecate','rollback')),
                    manifest_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    note TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS release_documents (
                    version INTEGER NOT NULL REFERENCES releases(version) ON DELETE CASCADE,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    revision_id TEXT NOT NULL REFERENCES document_revisions(revision_id),
                    PRIMARY KEY(version, document_id)
                );

                CREATE TABLE IF NOT EXISTS knowledge_base_state (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    current_version INTEGER REFERENCES releases(version)
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_revisions_document ON document_revisions(document_id, revision_number);
                CREATE INDEX IF NOT EXISTS idx_revisions_status ON document_revisions(status);
                CREATE INDEX IF NOT EXISTS idx_chunks_revision ON chunks(revision_id, ordinal);
                CREATE INDEX IF NOT EXISTS idx_chunk_terms_term ON chunk_terms(term, chunk_id);
                CREATE INDEX IF NOT EXISTS idx_vectors_model ON chunk_vectors(embedding_model, chunk_id);
                CREATE INDEX IF NOT EXISTS idx_release_documents_revision ON release_documents(revision_id, version);
                CREATE INDEX IF NOT EXISTS idx_audit_subject ON audit_events(subject_id, created_at);
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            connection.execute("INSERT OR IGNORE INTO knowledge_base_state(singleton, current_version) VALUES(1, NULL)")

    def create_candidate(
        self,
        document: DocumentInput,
        *,
        created_by: str,
        chunk_size: int = 800,
        overlap: int = 100,
    ) -> DocumentRevision:
        self.initialize()
        self._validate_document(document)
        actor = _required(created_by, "created_by")
        content_hash = _document_hash(document)
        pipeline_fingerprint = stable_sha256(
            _json({"chunker": "evidence-v1", "chunk_size": chunk_size, "overlap": overlap})
        )
        normalized_blocks = normalize_blocks(document)
        now = _utc_now()

        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT revision_id FROM document_revisions
                WHERE document_id = ? AND content_sha256 = ? AND pipeline_fingerprint = ?
                """,
                (document.document_id, content_hash, pipeline_fingerprint),
            ).fetchone()
            if existing is not None:
                return self._revision_from_connection(connection, str(existing["revision_id"]))

            row = connection.execute(
                "SELECT COALESCE(MAX(revision_number), 0) AS value FROM document_revisions WHERE document_id = ?",
                (document.document_id,),
            ).fetchone()
            revision_number = int(row["value"]) + 1
            revision_id = "rev_" + stable_sha256(f"{document.document_id}|{revision_number}|{content_hash}")[:28]
            chunks = chunk_document(
                document_id=document.document_id,
                revision_id=revision_id,
                blocks=normalized_blocks,
                chunk_size=chunk_size,
                overlap=overlap,
            )
            if not chunks:
                raise KnowledgeBaseError("EMPTY_DOCUMENT", "Document produced no searchable chunks.")

            connection.execute(
                """
                INSERT INTO documents(document_id, title, source_uri, media_type, metadata_json, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    title=excluded.title,
                    source_uri=excluded.source_uri,
                    media_type=excluded.media_type,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    document.document_id,
                    document.title.strip(),
                    document.source_uri.strip(),
                    document.media_type.strip(),
                    _json(document.metadata),
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO document_revisions(
                    revision_id, document_id, revision_number, title, source_uri, media_type,
                    metadata_json, status, content_sha256, pipeline_fingerprint, created_at, created_by
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    document.document_id,
                    revision_number,
                    document.title.strip(),
                    document.source_uri.strip(),
                    document.media_type.strip(),
                    _json(document.metadata),
                    RevisionStatus.CANDIDATE.value,
                    content_hash,
                    pipeline_fingerprint,
                    now,
                    actor,
                ),
            )

            blocks_by_page: dict[int, list[Any]] = {}
            for block in normalized_blocks:
                blocks_by_page.setdefault(block.page_number, []).append(block)
            for page in sorted(document.pages, key=lambda item: item.page_number):
                page_blocks = blocks_by_page.get(page.page_number, [])
                connection.execute(
                    "INSERT INTO pages(revision_id, page_number, text, metadata_json) VALUES(?, ?, ?, ?)",
                    (
                        revision_id,
                        page.page_number,
                        "\n\n".join(item.text for item in page_blocks),
                        _json(page.metadata),
                    ),
                )
            for block in normalized_blocks:
                connection.execute(
                    """
                    INSERT INTO blocks(
                        revision_id, block_id, page_number, block_type, ordinal,
                        parent_block_id, text, metadata_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        revision_id,
                        block.block_id,
                        block.page_number,
                        block.block_type,
                        block.ordinal,
                        block.parent_block_id,
                        block.text,
                        _json(block.metadata),
                    ),
                )
            for index, asset in enumerate(document.assets):
                asset_id = (
                    "ast_"
                    + stable_sha256(f"{revision_id}|{index}|{asset.asset_type}|{asset.page_number}|{asset.uri}")[:24]
                )
                connection.execute(
                    """
                    INSERT INTO assets(
                        revision_id, asset_id, asset_type, page_number, block_id,
                        uri, caption, checksum, metadata_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        revision_id,
                        asset_id,
                        asset.asset_type,
                        asset.page_number,
                        asset.block_id,
                        asset.uri,
                        asset.caption,
                        asset.checksum,
                        _json(asset.metadata),
                    ),
                )
            for chunk in chunks:
                terms = Counter(tokenize(chunk.text))
                connection.execute(
                    """
                    INSERT INTO chunks(
                        chunk_id, revision_id, ordinal, text, content_sha256,
                        term_count, evidence_json, metadata_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        revision_id,
                        chunk.ordinal,
                        chunk.text,
                        chunk.content_sha256,
                        sum(terms.values()),
                        _json([_evidence_dict(item) for item in chunk.evidence]),
                        _json(chunk.metadata),
                    ),
                )
                connection.executemany(
                    "INSERT INTO chunk_terms(chunk_id, term, term_frequency) VALUES(?, ?, ?)",
                    ((chunk.chunk_id, term, frequency) for term, frequency in terms.items()),
                )
            self._audit(
                connection,
                "candidate_created",
                actor,
                revision_id,
                {
                    "document_id": document.document_id,
                    "content_sha256": content_hash,
                    "pipeline_fingerprint": pipeline_fingerprint,
                    "chunk_count": len(chunks),
                },
            )
            return self._revision_from_connection(connection, revision_id)

    def submit_for_review(self, revision_id: str, *, actor: str) -> DocumentRevision:
        self.initialize()
        with self._connect() as connection, connection:
            revision = self._revision_from_connection(connection, revision_id)
            if revision.status is not RevisionStatus.CANDIDATE:
                raise KnowledgeBaseError("INVALID_STATE", "Only candidate revisions can be submitted for review.")
            if revision.review_decision is not None:
                raise KnowledgeBaseError("REVISION_ALREADY_REVIEWED", "Create a new revision after a rejected review.")
            connection.execute(
                "UPDATE document_revisions SET status = ? WHERE revision_id = ?",
                (RevisionStatus.PENDING_REVIEW.value, revision_id),
            )
            self._audit(connection, "review_submitted", _required(actor, "actor"), revision_id, {})
            return self._revision_from_connection(connection, revision_id)

    def record_review(
        self,
        revision_id: str,
        *,
        decision: ReviewDecision,
        reviewer: str,
        comment: str = "",
    ) -> DocumentRevision:
        self.initialize()
        reviewer_name = _required(reviewer, "reviewer")
        with self._connect() as connection, connection:
            revision = self._revision_from_connection(connection, revision_id)
            if revision.status is not RevisionStatus.PENDING_REVIEW:
                raise KnowledgeBaseError("INVALID_STATE", "Only pending revisions can be reviewed.")
            now = _utc_now()
            next_status = (
                RevisionStatus.PENDING_REVIEW if decision is ReviewDecision.APPROVED else RevisionStatus.CANDIDATE
            )
            connection.execute(
                """
                UPDATE document_revisions
                SET status = ?, review_decision = ?, reviewer = ?, reviewed_at = ?, review_comment = ?
                WHERE revision_id = ?
                """,
                (next_status.value, decision.value, reviewer_name, now, comment, revision_id),
            )
            connection.execute(
                "INSERT INTO reviews(revision_id, decision, reviewer, comment, created_at) VALUES(?, ?, ?, ?, ?)",
                (revision_id, decision.value, reviewer_name, comment, now),
            )
            self._audit(
                connection,
                "review_recorded",
                reviewer_name,
                revision_id,
                {"decision": decision.value, "comment": comment},
            )
            return self._revision_from_connection(connection, revision_id)

    def publish(
        self,
        revision_ids: Sequence[str],
        *,
        actor: str,
        note: str = "",
        expected_base_version: int | None = None,
        require_embeddings: bool = False,
        embedding_model: str | None = None,
    ) -> KnowledgeBaseRelease:
        if not revision_ids:
            raise KnowledgeBaseError("EMPTY_RELEASE", "At least one approved revision is required.")
        if len(set(revision_ids)) != len(revision_ids):
            raise KnowledgeBaseError("DUPLICATE_REVISION", "A release cannot contain duplicate revision identifiers.")
        self.initialize()
        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._current_version(connection)
            self._check_expected_version(current, expected_base_version)
            snapshot = self._snapshot(connection, current)
            for revision_id in revision_ids:
                revision = self._revision_from_connection(connection, revision_id)
                if (
                    revision.status is not RevisionStatus.PENDING_REVIEW
                    or revision.review_decision is not ReviewDecision.APPROVED
                ):
                    raise KnowledgeBaseError(
                        "REVISION_NOT_APPROVED",
                        f"Revision {revision_id} must have an approved review before publication.",
                    )
                snapshot[revision.document_id] = revision.revision_id
            if require_embeddings:
                self._require_embeddings(connection, snapshot.values(), embedding_model)
            return self._create_release(connection, snapshot, "publish", actor, note, current)

    def deprecate_document(
        self,
        document_id: str,
        *,
        actor: str,
        note: str = "",
        expected_base_version: int | None = None,
    ) -> KnowledgeBaseRelease:
        self.initialize()
        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._current_version(connection)
            self._check_expected_version(current, expected_base_version)
            snapshot = self._snapshot(connection, current)
            if document_id not in snapshot:
                raise KnowledgeBaseError(
                    "DOCUMENT_NOT_PUBLISHED", f"Document {document_id} is not in the active release."
                )
            snapshot.pop(document_id)
            return self._create_release(connection, snapshot, "deprecate", actor, note, current)

    def rollback(
        self,
        target_version: int,
        *,
        actor: str,
        note: str = "",
        expected_base_version: int | None = None,
    ) -> KnowledgeBaseRelease:
        self.initialize()
        with self._connect() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._current_version(connection)
            self._check_expected_version(current, expected_base_version)
            if current == target_version:
                raise KnowledgeBaseError("ALREADY_CURRENT", "The target version is already active.")
            snapshot = self._snapshot(connection, target_version, require=True)
            return self._create_release(
                connection,
                snapshot,
                "rollback",
                actor,
                note or f"Rollback to version {target_version}",
                current,
            )

    def current_version(self) -> int | None:
        self.initialize()
        with self._connect() as connection:
            return self._current_version(connection)

    def get_revision(self, revision_id: str) -> DocumentRevision:
        self.initialize()
        with self._connect() as connection:
            return self._revision_from_connection(connection, revision_id)

    def get_release(self, version: int | None = None) -> KnowledgeBaseRelease:
        self.initialize()
        with self._connect() as connection:
            resolved = self._resolve_version(connection, version)
            row = connection.execute(
                """
                SELECT r.*,
                       COUNT(DISTINCT rd.document_id) AS document_count,
                       COUNT(DISTINCT c.chunk_id) AS chunk_count
                FROM releases r
                LEFT JOIN release_documents rd ON rd.version = r.version
                LEFT JOIN chunks c ON c.revision_id = rd.revision_id
                WHERE r.version = ?
                GROUP BY r.version
                """,
                (resolved,),
            ).fetchone()
            if row is None:
                raise KnowledgeBaseError("VERSION_NOT_FOUND", f"Knowledge-base version {resolved} does not exist.")
            return _release_from_row(row)

    def export_snapshot(self, version: int | None = None) -> KnowledgeBaseSnapshot:
        """Export an immutable, storage-independent M3 snapshot for M4."""

        self.initialize()
        with self._connect() as connection:
            resolved = self._resolve_version(connection, version)
            release = self._release_from_connection(connection, resolved)
            revision_rows = connection.execute(
                """
                SELECT dr.*
                FROM release_documents rd
                JOIN document_revisions dr ON dr.revision_id = rd.revision_id
                WHERE rd.version = ?
                ORDER BY dr.document_id
                """,
                (resolved,),
            ).fetchall()
            documents: list[PublishedDocument] = []
            for revision_row in revision_rows:
                revision_id = str(revision_row["revision_id"])
                page_rows = connection.execute(
                    "SELECT page_number, metadata_json FROM pages WHERE revision_id=? ORDER BY page_number",
                    (revision_id,),
                ).fetchall()
                pages: list[PageInput] = []
                for page_row in page_rows:
                    page_number = int(page_row["page_number"])
                    block_rows = connection.execute(
                        """
                        SELECT block_id, block_type, ordinal, parent_block_id, text, metadata_json
                        FROM blocks
                        WHERE revision_id=? AND page_number=?
                        ORDER BY ordinal, block_id
                        """,
                        (revision_id, page_number),
                    ).fetchall()
                    pages.append(
                        PageInput(
                            page_number=page_number,
                            blocks=tuple(
                                BlockInput(
                                    text=str(row["text"]),
                                    block_type=str(row["block_type"]),
                                    ordinal=int(row["ordinal"]),
                                    block_id=str(row["block_id"]),
                                    parent_block_id=(
                                        None if row["parent_block_id"] is None else str(row["parent_block_id"])
                                    ),
                                    metadata=json.loads(str(row["metadata_json"])),
                                )
                                for row in block_rows
                            ),
                            metadata=json.loads(str(page_row["metadata_json"])),
                        )
                    )
                asset_rows = connection.execute(
                    """
                    SELECT asset_id, asset_type, page_number, block_id, uri, caption, checksum, metadata_json
                    FROM assets WHERE revision_id=? ORDER BY page_number, asset_id
                    """,
                    (revision_id,),
                ).fetchall()
                chunk_rows = connection.execute(
                    """
                    SELECT chunk_id, ordinal, text, content_sha256, evidence_json, metadata_json
                    FROM chunks WHERE revision_id=? ORDER BY ordinal, chunk_id
                    """,
                    (revision_id,),
                ).fetchall()
                documents.append(
                    PublishedDocument(
                        document_id=str(revision_row["document_id"]),
                        revision_id=revision_id,
                        title=str(revision_row["title"]),
                        source_uri=str(revision_row["source_uri"]),
                        media_type=str(revision_row["media_type"]),
                        pages=tuple(pages),
                        assets=tuple(
                            PublishedAsset(
                                asset_id=str(row["asset_id"]),
                                asset_type=str(row["asset_type"]),
                                page_number=int(row["page_number"]),
                                uri=str(row["uri"]),
                                caption=str(row["caption"]),
                                block_id=None if row["block_id"] is None else str(row["block_id"]),
                                checksum=None if row["checksum"] is None else str(row["checksum"]),
                                metadata=json.loads(str(row["metadata_json"])),
                            )
                            for row in asset_rows
                        ),
                        chunks=tuple(
                            StoredChunk(
                                chunk_id=str(row["chunk_id"]),
                                revision_id=revision_id,
                                ordinal=int(row["ordinal"]),
                                text=str(row["text"]),
                                content_sha256=str(row["content_sha256"]),
                                evidence=tuple(
                                    EvidenceLocator(**item) for item in json.loads(str(row["evidence_json"]))
                                ),
                                metadata=json.loads(str(row["metadata_json"])),
                            )
                            for row in chunk_rows
                        ),
                        metadata=json.loads(str(revision_row["metadata_json"])),
                    )
                )
        return KnowledgeBaseSnapshot(
            schema_version="power-rag.m3-snapshot.v1",
            release=release,
            documents=tuple(documents),
        )

    def compare_versions(self, from_version: int, to_version: int) -> VersionDiff:
        self.initialize()
        with self._connect() as connection:
            before = self._snapshot(connection, from_version, require=True)
            after = self._snapshot(connection, to_version, require=True)
        before_ids = set(before)
        after_ids = set(after)
        common = before_ids & after_ids
        return VersionDiff(
            from_version=from_version,
            to_version=to_version,
            added=tuple(sorted(after_ids - before_ids)),
            removed=tuple(sorted(before_ids - after_ids)),
            changed=tuple(sorted(item for item in common if before[item] != after[item])),
            unchanged=tuple(sorted(item for item in common if before[item] == after[item])),
        )

    def index_embeddings(  # noqa: C901
        self,
        *,
        embedding_model: str,
        embedder: Any,
        version: int | None = None,
        revision_ids: Sequence[str] | None = None,
        batch_size: int = 64,
        force: bool = False,
    ) -> dict[str, int | str]:
        model = _required(embedding_model, "embedding_model")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.initialize()
        with self._connect() as connection:
            if revision_ids is not None:
                target_revisions = tuple(dict.fromkeys(revision_ids))
                if not target_revisions:
                    raise KnowledgeBaseError("EMPTY_EMBEDDING_TARGET", "revision_ids must not be empty.")
                placeholders = ",".join("?" for _ in target_revisions)
                existing_revisions = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM document_revisions WHERE revision_id IN ({placeholders})",  # noqa: S608
                        target_revisions,
                    ).fetchone()[0]
                )
                if existing_revisions != len(target_revisions):
                    raise KnowledgeBaseError(
                        "REVISION_NOT_FOUND", "At least one embedding target revision does not exist."
                    )
                target = f"revisions:{','.join(target_revisions)}"
            else:
                resolved = self._resolve_version(connection, version)
                target_revisions = tuple(self._snapshot(connection, resolved, require=True).values())
                target = f"version:{resolved}"
            if not target_revisions:
                return {"target": target, "embedding_model": model, "indexed": 0, "skipped": 0}
            placeholders = ",".join("?" for _ in target_revisions)
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM chunks WHERE revision_id IN ({placeholders})",  # noqa: S608
                    target_revisions,
                ).fetchone()[0]
            )
            stale_clause = "" if force else "AND (v.chunk_id IS NULL OR v.content_sha256 != c.content_sha256)"
            rows = connection.execute(
                f"""
                SELECT c.chunk_id, c.text, c.content_sha256, v.content_sha256 AS indexed_sha
                FROM chunks c
                LEFT JOIN chunk_vectors v ON v.chunk_id = c.chunk_id AND v.embedding_model = ?
                WHERE c.revision_id IN ({placeholders})
                  {stale_clause}
                ORDER BY c.chunk_id
                """,  # noqa: S608
                (model, *target_revisions),
            ).fetchall()
        indexed = 0
        expected_dimension: int | None = None
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            vectors = embedder.embed([str(row["text"]) for row in batch])
            if len(vectors) != len(batch):
                raise KnowledgeBaseError("EMBEDDING_COUNT_MISMATCH", "Embedding backend returned an unexpected count.")
            with self._connect() as connection, connection:
                for row, vector_value in zip(batch, vectors, strict=True):
                    vector = [float(value) for value in vector_value]
                    if not vector or any(not math.isfinite(value) for value in vector):
                        raise KnowledgeBaseError("INVALID_EMBEDDING", "Embedding vectors must contain finite values.")
                    if expected_dimension is None:
                        expected_dimension = len(vector)
                    if len(vector) != expected_dimension:
                        raise KnowledgeBaseError(
                            "EMBEDDING_DIMENSION_MISMATCH", "Embedding dimensions are inconsistent."
                        )
                    connection.execute(
                        """
                        INSERT INTO chunk_vectors(
                            chunk_id, embedding_model, dimension, vector_json, content_sha256, created_at
                        ) VALUES(?, ?, ?, ?, ?, ?)
                        ON CONFLICT(chunk_id, embedding_model) DO UPDATE SET
                            dimension=excluded.dimension,
                            vector_json=excluded.vector_json,
                            content_sha256=excluded.content_sha256,
                            created_at=excluded.created_at
                        """,
                        (
                            row["chunk_id"],
                            model,
                            len(vector),
                            _json(vector),
                            row["content_sha256"],
                            _utc_now(),
                        ),
                    )
                    indexed += 1
        return {"target": target, "embedding_model": model, "indexed": indexed, "skipped": total - indexed}

    def keyword_search(self, query: str, *, version: int | None = None, top_k: int = 10) -> list[SearchHit]:
        if top_k <= 0 or not query.strip():
            return []
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms:
            return []
        self.initialize()
        with self._connect() as connection:
            resolved = self._resolve_version(connection, version)
            total_row = connection.execute(
                "SELECT COUNT(c.chunk_id) FROM release_documents rd JOIN chunks c ON c.revision_id=rd.revision_id WHERE rd.version=?",
                (resolved,),
            ).fetchone()
            total = int(total_row[0])
            if total == 0:
                return []
            avg_row = connection.execute(
                "SELECT AVG(c.term_count) FROM release_documents rd JOIN chunks c ON c.revision_id=rd.revision_id WHERE rd.version=?",
                (resolved,),
            ).fetchone()
            average_length = float(avg_row[0] or 1.0)
            placeholders = ",".join("?" for _ in terms)
            rows = connection.execute(
                f"""
                SELECT ct.chunk_id, ct.term, ct.term_frequency, c.term_count
                FROM chunk_terms ct
                JOIN chunks c ON c.chunk_id = ct.chunk_id
                JOIN release_documents rd ON rd.revision_id = c.revision_id
                WHERE rd.version = ? AND ct.term IN ({placeholders})
                """,  # noqa: S608 -- placeholders are generated, values remain bound parameters.
                (resolved, *terms),
            ).fetchall()
            document_frequency = {
                str(row["term"]): int(row["count"])
                for row in connection.execute(
                    f"""
                    SELECT ct.term, COUNT(DISTINCT ct.chunk_id) AS count
                    FROM chunk_terms ct
                    JOIN chunks c ON c.chunk_id = ct.chunk_id
                    JOIN release_documents rd ON rd.revision_id = c.revision_id
                    WHERE rd.version = ? AND ct.term IN ({placeholders})
                    GROUP BY ct.term
                    """,  # noqa: S608
                    (resolved, *terms),
                ).fetchall()
            }
            scores: dict[str, float] = {}
            k1, b = 1.5, 0.75
            for row in rows:
                term = str(row["term"])
                frequency = int(row["term_frequency"])
                length = int(row["term_count"])
                df = document_frequency[term]
                inverse_frequency = math.log(1.0 + (total - df + 0.5) / (df + 0.5))
                denominator = frequency + k1 * (1 - b + b * length / average_length)
                contribution = inverse_frequency * frequency * (k1 + 1) / denominator
                chunk_id = str(row["chunk_id"])
                scores[chunk_id] = scores.get(chunk_id, 0.0) + contribution
            ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
            return [self._hit(connection, resolved, chunk_id, score, {"keyword": score}) for chunk_id, score in ranked]

    def semantic_search(
        self,
        query_vector: Sequence[float],
        *,
        embedding_model: str,
        version: int | None = None,
        top_k: int = 10,
    ) -> list[SearchHit]:
        if top_k <= 0:
            return []
        query = [float(value) for value in query_vector]
        if not query or any(not math.isfinite(value) for value in query):
            raise KnowledgeBaseError("INVALID_QUERY_EMBEDDING", "Query embedding must contain finite values.")
        self.initialize()
        with self._connect() as connection:
            resolved = self._resolve_version(connection, version)
            rows = connection.execute(
                """
                SELECT c.chunk_id, v.dimension, v.vector_json
                FROM release_documents rd
                JOIN chunks c ON c.revision_id = rd.revision_id
                JOIN chunk_vectors v ON v.chunk_id = c.chunk_id
                WHERE rd.version = ? AND v.embedding_model = ?
                """,
                (resolved, embedding_model),
            ).fetchall()
            scores: list[tuple[str, float]] = []
            for row in rows:
                if int(row["dimension"]) != len(query):
                    raise KnowledgeBaseError(
                        "EMBEDDING_DIMENSION_MISMATCH",
                        f"Query dimension does not match stored model {embedding_model}.",
                    )
                vector = [float(value) for value in json.loads(str(row["vector_json"]))]
                scores.append((str(row["chunk_id"]), _cosine(query, vector)))
            scores.sort(key=lambda item: (-item[1], item[0]))
            return [
                self._hit(connection, resolved, chunk_id, score, {"semantic": score})
                for chunk_id, score in scores[:top_k]
            ]

    def verify_version(  # noqa: C901
        self,
        version: int | None = None,
        *,
        require_embeddings: bool = False,
        embedding_model: str | None = None,
    ) -> QualityReport:
        self.initialize()
        issues: list[QualityIssue] = []
        with self._connect() as connection:
            resolved = self._resolve_version(connection, version)
            snapshot = self._snapshot(connection, resolved, require=True)
            expected_manifest = self._manifest(connection, snapshot)
            release_row = connection.execute(
                "SELECT manifest_sha256 FROM releases WHERE version=?", (resolved,)
            ).fetchone()
            if release_row is None or release_row["manifest_sha256"] != expected_manifest:
                issues.append(
                    QualityIssue("MANIFEST_MISMATCH", "Release manifest checksum does not match its contents.")
                )
            chunks = connection.execute(
                """
                SELECT c.chunk_id, c.revision_id, c.text, c.content_sha256, c.evidence_json, c.term_count,
                       dr.document_id
                FROM release_documents rd
                JOIN document_revisions dr ON dr.revision_id = rd.revision_id
                JOIN chunks c ON c.revision_id = rd.revision_id
                WHERE rd.version = ?
                """,
                (resolved,),
            ).fetchall()
            for row in chunks:
                chunk_id = str(row["chunk_id"])
                revision_id = str(row["revision_id"])
                document_id = str(row["document_id"])
                if stable_sha256(str(row["text"])) != row["content_sha256"]:
                    issues.append(
                        QualityIssue(
                            "CHUNK_HASH_MISMATCH", "Chunk content hash is invalid.", document_id, revision_id, chunk_id
                        )
                    )
                evidence_values = json.loads(str(row["evidence_json"]))
                if not evidence_values:
                    issues.append(
                        QualityIssue(
                            "EVIDENCE_MISSING",
                            "Published chunk has no evidence locator.",
                            document_id,
                            revision_id,
                            chunk_id,
                        )
                    )
                for locator in evidence_values:
                    block = connection.execute(
                        "SELECT text, page_number FROM blocks WHERE revision_id=? AND block_id=?",
                        (revision_id, locator["block_id"]),
                    ).fetchone()
                    if block is None or int(block["page_number"]) != int(locator["page_number"]):
                        issues.append(
                            QualityIssue(
                                "EVIDENCE_TARGET_MISSING",
                                "Evidence block or page does not exist.",
                                document_id,
                                revision_id,
                                chunk_id,
                            )
                        )
                        continue
                    if not (0 <= int(locator["char_start"]) < int(locator["char_end"]) <= len(str(block["text"]))):
                        issues.append(
                            QualityIssue(
                                "EVIDENCE_RANGE_INVALID",
                                "Evidence character range is outside the source block.",
                                document_id,
                                revision_id,
                                chunk_id,
                            )
                        )
                if int(row["term_count"]) <= 0:
                    issues.append(
                        QualityIssue(
                            "KEYWORD_INDEX_MISSING",
                            "Chunk is absent from the keyword index.",
                            document_id,
                            revision_id,
                            chunk_id,
                        )
                    )
            if require_embeddings:
                try:
                    self._require_embeddings(connection, snapshot.values(), embedding_model)
                except KnowledgeBaseError as exc:
                    issues.append(QualityIssue(exc.code, str(exc)))
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity.lower() != "ok":
                issues.append(QualityIssue("SQLITE_INTEGRITY_FAILED", integrity))
            metrics: dict[str, int | float | str] = {
                "document_count": len(snapshot),
                "chunk_count": len(chunks),
                "evidence_locator_count": sum(len(json.loads(str(row["evidence_json"]))) for row in chunks),
                "issue_count": len(issues),
                "sqlite_integrity": integrity,
            }
            return QualityReport(not issues, resolved, metrics, tuple(issues))

    def create_backup(self, backup_dir: str | Path, *, name: str | None = None) -> BackupArtifact:
        self.initialize()
        target_dir = Path(backup_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = name or f"knowledge-base-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        if not re.fullmatch(r"[A-Za-z0-9._-]+", stem):
            raise KnowledgeBaseError(
                "INVALID_BACKUP_NAME", "Backup name may contain only letters, digits, dot, dash, and underscore."
            )
        database_path = target_dir / f"{stem}.sqlite3"
        manifest_path = target_dir / f"{stem}.manifest.json"
        if database_path.exists() or manifest_path.exists():
            raise KnowledgeBaseError("BACKUP_EXISTS", "Backup destination already exists.")
        temporary = target_dir / f".{stem}.{os.getpid()}.tmp"
        try:
            with self._connect() as source, closing(sqlite3.connect(temporary)) as destination:
                source.backup(destination)
                destination.commit()
            checksum = _file_sha256(temporary)
            os.replace(temporary, database_path)
            version = self.current_version()
            created_at = _utc_now()
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "database_file": database_path.name,
                "sha256": checksum,
                "knowledge_base_version": version,
                "created_at": created_at,
            }
            _atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
            return BackupArtifact(str(database_path), str(manifest_path), checksum, version, created_at)
        finally:
            temporary.unlink(missing_ok=True)

    def restore_backup(self, database_path: str | Path, manifest_path: str | Path) -> QualityReport:
        source_path = Path(database_path)
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if source_path.name != manifest.get("database_file"):
            raise KnowledgeBaseError("BACKUP_MANIFEST_MISMATCH", "Manifest refers to a different database file.")
        if _file_sha256(source_path) != manifest.get("sha256"):
            raise KnowledgeBaseError("BACKUP_CHECKSUM_MISMATCH", "Backup checksum validation failed.")
        with closing(sqlite3.connect(source_path)) as source:
            integrity = str(source.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity.lower() != "ok":
                raise KnowledgeBaseError("BACKUP_INTEGRITY_FAILED", integrity)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(source_path)) as source, self._connect() as destination:
            source.backup(destination)
            destination.commit()
        return self.verify_version()

    def _create_release(
        self,
        connection: sqlite3.Connection,
        snapshot: dict[str, str],
        action: str,
        actor: str,
        note: str,
        parent_version: int | None,
    ) -> KnowledgeBaseRelease:
        version = int(connection.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM releases").fetchone()[0])
        manifest = self._manifest(connection, snapshot)
        release_id = f"kbv-{version:06d}-{manifest[:10]}"
        now = _utc_now()
        actor_name = _required(actor, "actor")
        connection.execute(
            """
            INSERT INTO releases(version, release_id, parent_version, action, manifest_sha256, created_at, created_by, note)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (version, release_id, parent_version, action, manifest, now, actor_name, note),
        )
        connection.executemany(
            "INSERT INTO release_documents(version, document_id, revision_id) VALUES(?, ?, ?)",
            ((version, document_id, revision_id) for document_id, revision_id in sorted(snapshot.items())),
        )
        connection.execute("UPDATE knowledge_base_state SET current_version=? WHERE singleton=1", (version,))
        connection.execute(
            "UPDATE document_revisions SET status=? WHERE status=?",
            (RevisionStatus.DEPRECATED.value, RevisionStatus.PUBLISHED.value),
        )
        if snapshot:
            placeholders = ",".join("?" for _ in snapshot)
            connection.execute(
                f"UPDATE document_revisions SET status=? WHERE revision_id IN ({placeholders})",  # noqa: S608
                (RevisionStatus.PUBLISHED.value, *snapshot.values()),
            )
        self._audit(
            connection, f"release_{action}", actor_name, release_id, {"version": version, "manifest_sha256": manifest}
        )
        return self._release_from_connection(connection, version)

    def _hit(
        self,
        connection: sqlite3.Connection,
        version: int,
        chunk_id: str,
        score: float,
        component_scores: dict[str, float],
    ) -> SearchHit:
        row = connection.execute(
            """
            SELECT c.chunk_id, c.revision_id, c.text, c.evidence_json,
                   dr.document_id, dr.title, dr.source_uri, dr.metadata_json
            FROM chunks c
            JOIN document_revisions dr ON dr.revision_id=c.revision_id
            JOIN release_documents rd ON rd.revision_id=c.revision_id AND rd.version=?
            WHERE c.chunk_id=?
            """,
            (version, chunk_id),
        ).fetchone()
        if row is None:
            raise KnowledgeBaseError("INDEX_VERSION_MISMATCH", f"Chunk {chunk_id} is not part of version {version}.")
        evidence = tuple(EvidenceLocator(**item) for item in json.loads(str(row["evidence_json"])))
        return SearchHit(
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            revision_id=str(row["revision_id"]),
            version=version,
            text=str(row["text"]),
            score=float(score),
            source_uri=str(row["source_uri"]),
            title=str(row["title"]),
            evidence=evidence,
            metadata=json.loads(str(row["metadata_json"])),
            component_scores=component_scores,
        )

    def _release_from_connection(self, connection: sqlite3.Connection, version: int) -> KnowledgeBaseRelease:
        row = connection.execute(
            """
            SELECT r.*,
                   COUNT(DISTINCT rd.document_id) AS document_count,
                   COUNT(DISTINCT c.chunk_id) AS chunk_count
            FROM releases r
            LEFT JOIN release_documents rd ON rd.version=r.version
            LEFT JOIN chunks c ON c.revision_id=rd.revision_id
            WHERE r.version=? GROUP BY r.version
            """,
            (version,),
        ).fetchone()
        if row is None:
            raise KnowledgeBaseError("VERSION_NOT_FOUND", f"Knowledge-base version {version} does not exist.")
        return _release_from_row(row)

    def _revision_from_connection(self, connection: sqlite3.Connection, revision_id: str) -> DocumentRevision:
        row = connection.execute(
            """
            SELECT dr.* FROM document_revisions dr WHERE dr.revision_id=?
            """,
            (revision_id,),
        ).fetchone()
        if row is None:
            raise KnowledgeBaseError("REVISION_NOT_FOUND", f"Revision {revision_id} does not exist.")
        return _revision_from_row(row)

    def _manifest(self, connection: sqlite3.Connection, snapshot: dict[str, str]) -> str:
        items: list[dict[str, str]] = []
        for document_id, revision_id in sorted(snapshot.items()):
            row = connection.execute(
                """
                SELECT content_sha256, pipeline_fingerprint
                FROM document_revisions WHERE revision_id=? AND document_id=?
                """,
                (revision_id, document_id),
            ).fetchone()
            if row is None:
                raise KnowledgeBaseError(
                    "SNAPSHOT_INVALID", f"Revision {revision_id} does not belong to {document_id}."
                )
            chunk_hashes = [
                str(item["content_sha256"])
                for item in connection.execute(
                    "SELECT content_sha256 FROM chunks WHERE revision_id=? ORDER BY ordinal",
                    (revision_id,),
                ).fetchall()
            ]
            items.append({
                "document_id": document_id,
                "revision_id": revision_id,
                "content_sha256": str(row["content_sha256"]),
                "pipeline_fingerprint": str(row["pipeline_fingerprint"]),
                "chunks_sha256": stable_sha256("|".join(chunk_hashes)),
            })
        return stable_sha256(_json(items))

    def _snapshot(
        self,
        connection: sqlite3.Connection,
        version: int | None,
        *,
        require: bool = False,
    ) -> dict[str, str]:
        if version is None:
            if require:
                raise KnowledgeBaseError("VERSION_NOT_FOUND", "No knowledge-base version has been published.")
            return {}
        exists = connection.execute("SELECT 1 FROM releases WHERE version=?", (version,)).fetchone()
        if exists is None:
            raise KnowledgeBaseError("VERSION_NOT_FOUND", f"Knowledge-base version {version} does not exist.")
        return {
            str(row["document_id"]): str(row["revision_id"])
            for row in connection.execute(
                "SELECT document_id, revision_id FROM release_documents WHERE version=? ORDER BY document_id",
                (version,),
            ).fetchall()
        }

    def _resolve_version(self, connection: sqlite3.Connection, version: int | None) -> int:
        resolved = version if version is not None else self._current_version(connection)
        if resolved is None:
            raise KnowledgeBaseError("VERSION_NOT_FOUND", "No knowledge-base version has been published.")
        if connection.execute("SELECT 1 FROM releases WHERE version=?", (resolved,)).fetchone() is None:
            raise KnowledgeBaseError("VERSION_NOT_FOUND", f"Knowledge-base version {resolved} does not exist.")
        return resolved

    def _require_embeddings(
        self,
        connection: sqlite3.Connection,
        revision_ids: Iterable[str],
        embedding_model: str | None,
    ) -> None:
        if not embedding_model:
            raise KnowledgeBaseError("EMBEDDING_MODEL_REQUIRED", "An embedding model is required by this quality gate.")
        revision_values = tuple(revision_ids)
        if not revision_values:
            return
        placeholders = ",".join("?" for _ in revision_values)
        missing = int(
            connection.execute(
                f"""
                SELECT COUNT(*) FROM chunks c
                LEFT JOIN chunk_vectors v ON v.chunk_id=c.chunk_id AND v.embedding_model=?
                WHERE c.revision_id IN ({placeholders})
                  AND (v.chunk_id IS NULL OR v.content_sha256 != c.content_sha256)
                """,  # noqa: S608
                (embedding_model, *revision_values),
            ).fetchone()[0]
        )
        if missing:
            raise KnowledgeBaseError("EMBEDDING_INDEX_INCOMPLETE", f"{missing} chunks are missing current embeddings.")

    @staticmethod
    def _current_version(connection: sqlite3.Connection) -> int | None:
        row = connection.execute("SELECT current_version FROM knowledge_base_state WHERE singleton=1").fetchone()
        return None if row is None or row["current_version"] is None else int(row["current_version"])

    @staticmethod
    def _check_expected_version(current: int | None, expected: int | None) -> None:
        if expected is not None and expected != current:
            raise KnowledgeBaseError(
                "VERSION_CONFLICT",
                f"Expected base version {expected}, but the active version is {current}.",
            )

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        event_type: str,
        actor: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO audit_events(event_type, actor, subject_id, payload_json, created_at) VALUES(?, ?, ?, ?, ?)",
            (event_type, actor, subject_id, _json(payload), _utc_now()),
        )

    @staticmethod
    def _validate_document(document: DocumentInput) -> None:
        _required(document.document_id, "document_id")
        _required(document.title, "title")
        _required(document.source_uri, "source_uri")
        if not document.pages:
            raise KnowledgeBaseError("EMPTY_DOCUMENT", "Document must contain at least one page.")
        page_numbers = [page.page_number for page in document.pages]
        if any(number <= 0 for number in page_numbers) or len(page_numbers) != len(set(page_numbers)):
            raise KnowledgeBaseError("INVALID_PAGE_NUMBER", "Page numbers must be unique positive integers.")
        known_pages = set(page_numbers)
        if any(asset.page_number not in known_pages for asset in document.assets):
            raise KnowledgeBaseError("ASSET_PAGE_MISSING", "Each asset must reference an existing page.")

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=30000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def tokenize(text: str) -> tuple[str, ...]:
    lowered = text.casefold()
    terms = _LATIN_TOKEN.findall(lowered)
    for sequence in _HAN_SEQUENCE.findall(lowered):
        terms.extend(sequence)
        if len(sequence) > 1:
            terms.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return tuple(terms)


def _document_hash(document: DocumentInput) -> str:
    payload = {
        "document_id": document.document_id,
        "title": document.title.strip(),
        "source_uri": document.source_uri.strip(),
        "media_type": document.media_type.strip(),
        "metadata": document.metadata,
        "pages": [
            {
                "page_number": page.page_number,
                "metadata": page.metadata,
                "blocks": [
                    {
                        "block_id": block.block_id,
                        "type": block.block_type,
                        "ordinal": block.ordinal,
                        "parent_block_id": block.parent_block_id,
                        "text": block.text,
                        "metadata": block.metadata,
                    }
                    for block in page.blocks
                ],
            }
            for page in document.pages
        ],
        "assets": [
            {
                "type": item.asset_type,
                "page": item.page_number,
                "block_id": item.block_id,
                "uri": item.uri,
                "caption": item.caption,
                "checksum": item.checksum,
                "metadata": item.metadata,
            }
            for item in document.assets
        ],
    }
    return stable_sha256(_json(payload))


def _revision_from_row(row: sqlite3.Row) -> DocumentRevision:
    decision = None if row["review_decision"] is None else ReviewDecision(str(row["review_decision"]))
    return DocumentRevision(
        document_id=str(row["document_id"]),
        revision_id=str(row["revision_id"]),
        revision_number=int(row["revision_number"]),
        title=str(row["title"]),
        source_uri=str(row["source_uri"]),
        media_type=str(row["media_type"]),
        status=RevisionStatus(str(row["status"])),
        content_sha256=str(row["content_sha256"]),
        pipeline_fingerprint=str(row["pipeline_fingerprint"]),
        created_at=str(row["created_at"]),
        created_by=str(row["created_by"]),
        review_decision=decision,
        reviewer=None if row["reviewer"] is None else str(row["reviewer"]),
        reviewed_at=None if row["reviewed_at"] is None else str(row["reviewed_at"]),
    )


def _release_from_row(row: sqlite3.Row) -> KnowledgeBaseRelease:
    return KnowledgeBaseRelease(
        version=int(row["version"]),
        release_id=str(row["release_id"]),
        parent_version=None if row["parent_version"] is None else int(row["parent_version"]),
        action=str(row["action"]),
        manifest_sha256=str(row["manifest_sha256"]),
        created_at=str(row["created_at"]),
        created_by=str(row["created_by"]),
        note=str(row["note"]),
        document_count=int(row["document_count"]),
        chunk_count=int(row["chunk_count"]),
    )


def _evidence_dict(item: EvidenceLocator) -> dict[str, Any]:
    return {
        "document_id": item.document_id,
        "revision_id": item.revision_id,
        "page_number": item.page_number,
        "block_id": item.block_id,
        "char_start": item.char_start,
        "char_end": item.char_end,
    }


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise KnowledgeBaseError(
            "METADATA_NOT_SERIALIZABLE", "Knowledge-base metadata must be finite JSON data."
        ) from exc


def _required(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise KnowledgeBaseError("REQUIRED_FIELD_MISSING", f"{field_name} is required.")
    return normalized


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
