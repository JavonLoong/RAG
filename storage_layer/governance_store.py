"""SQLite persistence for governed document, graph, and FMEA deliveries.

This store deliberately keeps workflow metadata separate from the existing
retrieval and graph databases.  It is the audit/control plane: immutable source
evidence, version transitions, review records, and task outputs live here while
the existing stores remain optimized for retrieval.
"""
# ruff: noqa: TRY003

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from core_domain.delivery import (
    CanonicalDocumentVersion,
    ContentStatus,
    EvidenceLocator,
    FMEAItem,
    FMEATaskRequest,
    FMEATaskResult,
    GraphDomainSchema,
    GraphStatement,
    GraphVersion,
    IssueSeverity,
    QualityIssue,
    ReviewDecision,
    ReviewRecord,
    TaskStatus,
)


class GovernanceError(RuntimeError):
    """Raised when a governed lifecycle transition is invalid."""


class GovernanceStore:
    """Durable M2-M5 control plane backed by one local SQLite file."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.initialize()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS document_versions (
                    version_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    source_name TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quality_issues_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    published_at TEXT,
                    supersedes_version_id TEXT,
                    UNIQUE(document_id, version)
                );

                CREATE TABLE IF NOT EXISTS evidence_locators (
                    evidence_id TEXT PRIMARY KEY,
                    document_version_id TEXT NOT NULL REFERENCES document_versions(version_id),
                    chunk_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    page TEXT,
                    block_id TEXT,
                    table_id TEXT,
                    image_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS graph_versions (
                    graph_version_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    source_document_version_ids_json TEXT NOT NULL,
                    schema_json TEXT NOT NULL,
                    quality_issues_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    published_at TEXT,
                    supersedes_version_id TEXT
                );

                CREATE TABLE IF NOT EXISTS graph_statements (
                    statement_id TEXT PRIMARY KEY,
                    graph_version_id TEXT NOT NULL REFERENCES graph_versions(graph_version_id),
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object_name TEXT NOT NULL,
                    subject_type TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    confidence REAL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS reviews (
                    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    corrections_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fmea_tasks (
                    task_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    items_json TEXT NOT NULL DEFAULT '[]',
                    errors_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    published_at TEXT
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    feedback_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES fmea_tasks(task_id),
                    item_id TEXT,
                    code TEXT NOT NULL,
                    message TEXT NOT NULL,
                    routed_module TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open'
                );

                CREATE INDEX IF NOT EXISTS idx_doc_versions_document ON document_versions(document_id, version);
                CREATE INDEX IF NOT EXISTS idx_evidence_version ON evidence_locators(document_version_id);
                CREATE INDEX IF NOT EXISTS idx_graph_statements_version ON graph_statements(graph_version_id);
                CREATE INDEX IF NOT EXISTS idx_reviews_target ON reviews(target_type, target_id, review_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_task ON feedback(task_id, created_at);
                """
            )

    # ------------------------------------------------------------------
    # M2/M3: parsed candidates, evidence, review, and document versions

    def create_document_candidate_from_intake(
        self,
        document_id: str,
        intake_result: Any,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> CanonicalDocumentVersion:
        profile = getattr(intake_result, "profile", None)
        source_name = str(getattr(profile, "source_name", "") or "").strip()
        if not source_name:
            raise ValueError("The intake result must expose profile.source_name")
        merged_metadata = dict(metadata or {})
        to_dict = getattr(profile, "to_dict", None)
        if callable(to_dict):
            merged_metadata["intake_profile"] = to_dict()
        merged_metadata["processing_plan"] = dict(getattr(intake_result, "processing_plan", {}) or {})
        return self.create_document_candidate(
            document_id=document_id,
            source_name=source_name,
            chunks=list(getattr(intake_result, "chunks", []) or []),
            intake_status=str(getattr(intake_result, "status", "failed")),
            quality=dict(getattr(intake_result, "quality", {}) or {}),
            warnings=list(getattr(intake_result, "warnings", []) or []),
            errors=list(getattr(intake_result, "errors", []) or []),
            metadata=merged_metadata,
        )

    def create_document_candidate(
        self,
        *,
        document_id: str,
        source_name: str,
        chunks: Sequence[Any],
        intake_status: str = "parsed",
        quality: Mapping[str, Any] | None = None,
        warnings: Sequence[str] = (),
        errors: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> CanonicalDocumentVersion:
        document_id = _required(document_id, "document_id")
        source_name = _required(source_name, "source_name")
        quality_payload = dict(quality or {})
        normalized_chunks = [
            _chunk_to_payload(chunk, source_name, index) for index, chunk in enumerate(chunks, start=1)
        ]
        now = _utc_now()

        with self._connect() as connection:
            version, supersedes = self._next_document_version(connection, document_id)
            version_id = f"{document_id}:v{version}"
            evidence = tuple(
                EvidenceLocator(
                    evidence_id=_stable_id("EV", version_id, chunk["chunk_id"], str(index)),
                    document_version_id=version_id,
                    chunk_id=chunk["chunk_id"],
                    text=chunk["text"],
                    source_file=chunk["source_file"],
                    page=chunk["page"],
                    block_id=chunk["block_id"],
                    table_id=chunk["table_id"],
                    image_id=chunk["image_id"],
                    metadata=chunk["metadata"],
                )
                for index, chunk in enumerate(normalized_chunks, start=1)
            )
            issues = _intake_issues(
                version_id=version_id,
                intake_status=intake_status,
                evidence=evidence,
                quality=quality_payload,
                warnings=warnings,
                errors=errors,
            )
            status = ContentStatus.NEEDS_REVIEW if issues else ContentStatus.CANDIDATE
            content_hash = hashlib.sha256("\n".join(item.text for item in evidence).encode("utf-8")).hexdigest()
            connection.execute(
                """
                INSERT INTO document_versions (
                    version_id, document_id, version, source_name, content_hash, status,
                    quality_issues_json, metadata_json, created_at, supersedes_version_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    document_id,
                    version,
                    source_name,
                    content_hash,
                    status.value,
                    _json_dump([issue.to_dict() for issue in issues]),
                    _json_dump({**dict(metadata or {}), "intake_quality": quality_payload}),
                    now,
                    supersedes,
                ),
            )
            connection.executemany(
                """
                INSERT INTO evidence_locators (
                    evidence_id, document_version_id, chunk_id, text, source_file, page,
                    block_id, table_id, image_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.evidence_id,
                        item.document_version_id,
                        item.chunk_id,
                        item.text,
                        item.source_file,
                        item.page,
                        item.block_id,
                        item.table_id,
                        item.image_id,
                        _json_dump(item.metadata),
                    )
                    for item in evidence
                ],
            )
        return self.get_document_version(version_id)

    def get_document_version(self, version_id: str) -> CanonicalDocumentVersion:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM document_versions WHERE version_id = ?", (version_id,)).fetchone()
            if row is None:
                raise GovernanceError(f"Unknown document version: {version_id}")
            evidence_rows = connection.execute(
                "SELECT * FROM evidence_locators WHERE document_version_id = ? ORDER BY rowid", (version_id,)
            ).fetchall()
        return _document_from_rows(row, evidence_rows)

    def list_document_versions(self, document_id: str) -> list[CanonicalDocumentVersion]:
        with self._connect() as connection:
            ids = [
                str(row["version_id"])
                for row in connection.execute(
                    "SELECT version_id FROM document_versions WHERE document_id = ? ORDER BY version", (document_id,)
                ).fetchall()
            ]
        return [self.get_document_version(version_id) for version_id in ids]

    def publish_document(self, version_id: str) -> CanonicalDocumentVersion:
        document = self.get_document_version(version_id)
        if not document.evidence:
            raise GovernanceError("A document version without source evidence cannot be published")
        self._require_approval("document", version_id)
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE document_versions SET status = ? WHERE document_id = ? AND status = ? AND version_id <> ?",
                (ContentStatus.RETIRED.value, document.document_id, ContentStatus.PUBLISHED.value, version_id),
            )
            connection.execute(
                "UPDATE document_versions SET status = ?, published_at = ? WHERE version_id = ?",
                (ContentStatus.PUBLISHED.value, now, version_id),
            )
        return self.get_document_version(version_id)

    def rollback_document(
        self, document_id: str, target_version_id: str, *, reviewer: str, comment: str = ""
    ) -> CanonicalDocumentVersion:
        target = self.get_document_version(target_version_id)
        if target.document_id != document_id:
            raise GovernanceError("Rollback target does not belong to the requested document")
        candidate = self.create_document_candidate(
            document_id=document_id,
            source_name=target.source_name,
            chunks=[
                {
                    "chunk_id": item.chunk_id,
                    "text": item.text,
                    "source_file": item.source_file,
                    "page": item.page,
                    "block_id": item.block_id,
                    "table_id": item.table_id,
                    "image_id": item.image_id,
                    "metadata": item.metadata,
                }
                for item in target.evidence
            ],
            metadata={**target.metadata, "rollback_target": target_version_id},
        )
        self.record_review(
            target_type="document",
            target_id=candidate.version_id,
            reviewer=reviewer,
            decision=ReviewDecision.ROLLBACK,
            comment=comment or f"Rollback to content from {target_version_id}",
        )
        self.record_review(
            target_type="document",
            target_id=candidate.version_id,
            reviewer=reviewer,
            decision=ReviewDecision.APPROVE,
            comment="Approved rollback version",
        )
        return self.publish_document(candidate.version_id)

    def compare_document_versions(self, left_id: str, right_id: str) -> dict[str, Any]:
        left = self.get_document_version(left_id)
        right = self.get_document_version(right_id)
        left_chunks = {item.chunk_id: item.text for item in left.evidence}
        right_chunks = {item.chunk_id: item.text for item in right.evidence}
        common = left_chunks.keys() & right_chunks.keys()
        return {
            "left_version_id": left_id,
            "right_version_id": right_id,
            "content_changed": left.content_hash != right.content_hash,
            "added_chunks": sorted(right_chunks.keys() - left_chunks.keys()),
            "removed_chunks": sorted(left_chunks.keys() - right_chunks.keys()),
            "modified_chunks": sorted(
                chunk_id for chunk_id in common if left_chunks[chunk_id] != right_chunks[chunk_id]
            ),
        }

    # ------------------------------------------------------------------
    # M4: schema-constrained graph candidates and graph versions

    def create_graph_candidate(
        self,
        *,
        source_document_version_ids: Sequence[str],
        statements: Sequence[GraphStatement | Mapping[str, Any]],
        schema: GraphDomainSchema | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> GraphVersion:
        schema = schema or GraphDomainSchema()
        source_ids = tuple(
            dict.fromkeys(_required(item, "source_document_version_id") for item in source_document_version_ids)
        )
        if not source_ids:
            raise GovernanceError("At least one published document version is required")
        for source_id in source_ids:
            document = self.get_document_version(source_id)
            if document.status is not ContentStatus.PUBLISHED:
                raise GovernanceError(f"Graph sources must be published: {source_id}")

        with self._connect() as connection:
            version_row = connection.execute(
                "SELECT version, graph_version_id FROM graph_versions ORDER BY version DESC LIMIT 1"
            ).fetchone()
            version = int(version_row["version"]) + 1 if version_row else 1
            supersedes = str(version_row["graph_version_id"]) if version_row else None
            graph_version_id = f"graph:v{version}"

            allowed_evidence = {
                str(row["evidence_id"]): str(row["document_version_id"])
                for row in connection.execute(
                    f"SELECT evidence_id, document_version_id FROM evidence_locators WHERE document_version_id IN ({','.join('?' for _ in source_ids)})",  # noqa: S608 - placeholders remain parameterized
                    source_ids,
                ).fetchall()
            }

            normalized, issues = _normalize_graph_statements(
                graph_version_id=graph_version_id,
                raw_statements=statements,
                schema=schema,
                allowed_evidence=allowed_evidence,
            )
            if not normalized:
                issues.append(
                    QualityIssue(
                        issue_id=f"{graph_version_id}:Q001",
                        code="empty_graph",
                        message="The graph candidate contains no valid statements.",
                        severity=IssueSeverity.ERROR,
                    )
                )
            status = ContentStatus.NEEDS_REVIEW if issues else ContentStatus.CANDIDATE
            now = _utc_now()
            connection.execute(
                """
                INSERT INTO graph_versions (
                    graph_version_id, version, status, source_document_version_ids_json,
                    schema_json, quality_issues_json, metadata_json, created_at, supersedes_version_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    graph_version_id,
                    version,
                    status.value,
                    _json_dump(source_ids),
                    _json_dump(schema.to_dict()),
                    _json_dump([issue.to_dict() for issue in issues]),
                    _json_dump(dict(metadata or {})),
                    now,
                    supersedes,
                ),
            )
            connection.executemany(
                """
                INSERT INTO graph_statements (
                    statement_id, graph_version_id, subject, predicate, object_name,
                    subject_type, object_type, evidence_ids_json, confidence, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.statement_id,
                        graph_version_id,
                        item.subject,
                        item.predicate,
                        item.object_name,
                        item.subject_type,
                        item.object_type,
                        _json_dump(item.evidence_ids),
                        item.confidence,
                        _json_dump(item.metadata),
                    )
                    for item in normalized
                ],
            )
        return self.get_graph_version(graph_version_id)

    def get_graph_version(self, graph_version_id: str) -> GraphVersion:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM graph_versions WHERE graph_version_id = ?", (graph_version_id,)
            ).fetchone()
            if row is None:
                raise GovernanceError(f"Unknown graph version: {graph_version_id}")
            statement_rows = connection.execute(
                "SELECT * FROM graph_statements WHERE graph_version_id = ? ORDER BY rowid", (graph_version_id,)
            ).fetchall()
        return _graph_from_rows(row, statement_rows)

    def publish_graph(self, graph_version_id: str) -> GraphVersion:
        graph = self.get_graph_version(graph_version_id)
        if not graph.statements:
            raise GovernanceError("An empty graph cannot be published")
        blocking = [
            issue for issue in graph.quality_issues if issue.severity is IssueSeverity.ERROR and not issue.resolved
        ]
        if blocking:
            raise GovernanceError(
                f"Graph has unresolved blocking issues: {', '.join(issue.code for issue in blocking)}"
            )
        self._require_approval("graph", graph_version_id)
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE graph_versions SET status = ? WHERE status = ? AND graph_version_id <> ?",
                (ContentStatus.RETIRED.value, ContentStatus.PUBLISHED.value, graph_version_id),
            )
            connection.execute(
                "UPDATE graph_versions SET status = ?, published_at = ? WHERE graph_version_id = ?",
                (ContentStatus.PUBLISHED.value, now, graph_version_id),
            )
        return self.get_graph_version(graph_version_id)

    def graph_as_edge_payload(self, graph_version_id: str) -> list[dict[str, Any]]:
        """Export a governed graph in the shape accepted by GraphStore.normalize_kg_payload."""
        graph = self.get_graph_version(graph_version_id)
        return [
            {
                "triple_id": item.statement_id,
                "subject": item.subject,
                "subject_type": item.subject_type,
                "predicate": item.predicate,
                "object": item.object_name,
                "object_type": item.object_type,
                "confidence": item.confidence,
                "evidence": "\n".join(self.get_evidence(evidence_id).text for evidence_id in item.evidence_ids),
                "source_chunk_id": ",".join(item.evidence_ids),
                "metadata": {
                    **item.metadata,
                    "graph_version_id": graph_version_id,
                    "evidence_ids": list(item.evidence_ids),
                },
            }
            for item in graph.statements
        ]

    # ------------------------------------------------------------------
    # M5: task lifecycle, human review, publication, and feedback

    def create_fmea_task(self, request: FMEATaskRequest) -> FMEATaskResult:
        graph = self.get_graph_version(request.graph_version_id)
        if graph.status is not ContentStatus.PUBLISHED:
            raise GovernanceError("FMEA tasks require a published graph version")
        requested_docs = tuple(dict.fromkeys(request.document_version_ids))
        if not requested_docs:
            raise GovernanceError("FMEA tasks require at least one published document version")
        unknown_sources = set(requested_docs) - set(graph.source_document_version_ids)
        if unknown_sources:
            raise GovernanceError(f"Task document versions are not graph sources: {sorted(unknown_sources)}")
        for version_id in requested_docs:
            if self.get_document_version(version_id).status is not ContentStatus.PUBLISHED:
                raise GovernanceError(f"FMEA source is not published: {version_id}")

        task_id = f"fmea-{uuid4().hex[:12]}"
        now = _utc_now()
        normalized_request = replace(request, document_version_ids=requested_docs)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO fmea_tasks (task_id, request_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, _json_dump(normalized_request.to_dict()), TaskStatus.QUEUED.value, now, now),
            )
        return self.get_fmea_task(task_id)

    def save_fmea_result(
        self,
        task_id: str,
        *,
        status: TaskStatus,
        items: Sequence[FMEAItem],
        errors: Sequence[str] = (),
    ) -> FMEATaskResult:
        self.get_fmea_task(task_id)
        if status not in {TaskStatus.RUNNING, TaskStatus.NEEDS_REVIEW, TaskStatus.APPROVED, TaskStatus.FAILED}:
            raise GovernanceError(f"Invalid generated task status: {status.value}")
        with self._connect() as connection:
            connection.execute(
                "UPDATE fmea_tasks SET status = ?, items_json = ?, errors_json = ?, updated_at = ? WHERE task_id = ?",
                (
                    status.value,
                    _json_dump([item.to_dict() for item in items]),
                    _json_dump(list(errors)),
                    _utc_now(),
                    task_id,
                ),
            )
        return self.get_fmea_task(task_id)

    def get_fmea_task(self, task_id: str) -> FMEATaskResult:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM fmea_tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise GovernanceError(f"Unknown FMEA task: {task_id}")
        return _fmea_task_from_row(row)

    def publish_fmea_task(self, task_id: str) -> FMEATaskResult:
        task = self.get_fmea_task(task_id)
        if not task.items:
            raise GovernanceError("An empty FMEA task cannot be published")
        self._require_approval("fmea", task_id)
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE fmea_tasks SET status = ?, updated_at = ?, published_at = ? WHERE task_id = ?",
                (TaskStatus.PUBLISHED.value, now, now, task_id),
            )
        return self.get_fmea_task(task_id)

    def add_feedback(
        self,
        *,
        task_id: str,
        code: str,
        message: str,
        created_by: str,
        item_id: str | None = None,
    ) -> dict[str, Any]:
        self.get_fmea_task(task_id)
        feedback_id = f"FB-{uuid4().hex[:12]}"
        routed_module = _feedback_module(code)
        payload = {
            "feedback_id": feedback_id,
            "task_id": task_id,
            "item_id": item_id,
            "code": _required(code, "code"),
            "message": _required(message, "message"),
            "routed_module": routed_module,
            "created_by": _required(created_by, "created_by"),
            "created_at": _utc_now(),
            "status": "open",
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feedback (
                    feedback_id, task_id, item_id, code, message, routed_module, created_by, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload[key] for key in payload),
            )
        return payload

    # ------------------------------------------------------------------
    # Shared review/evidence operations

    def record_review(
        self,
        *,
        target_type: str,
        target_id: str,
        reviewer: str,
        decision: ReviewDecision | str,
        comment: str = "",
        corrections: Mapping[str, Any] | None = None,
    ) -> ReviewRecord:
        target_type = _required(target_type, "target_type").lower()
        if target_type not in {"document", "graph", "fmea"}:
            raise ValueError("target_type must be document, graph, or fmea")
        self._ensure_target_exists(target_type, target_id)
        normalized_decision = decision if isinstance(decision, ReviewDecision) else ReviewDecision(str(decision))
        now = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO reviews (target_type, target_id, reviewer, decision, comment, corrections_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_type,
                    target_id,
                    _required(reviewer, "reviewer"),
                    normalized_decision.value,
                    str(comment).strip(),
                    _json_dump(dict(corrections or {})),
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise GovernanceError("Failed to persist review record")
            review_id = int(cursor.lastrowid)
        return ReviewRecord(
            review_id=review_id,
            target_type=target_type,
            target_id=target_id,
            reviewer=reviewer,
            decision=normalized_decision,
            comment=str(comment).strip(),
            corrections=dict(corrections or {}),
            created_at=now,
        )

    def list_reviews(self, target_type: str, target_id: str) -> list[ReviewRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM reviews WHERE target_type = ? AND target_id = ? ORDER BY review_id",
                (target_type, target_id),
            ).fetchall()
        return [_review_from_row(row) for row in rows]

    def get_evidence(self, evidence_id: str) -> EvidenceLocator:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM evidence_locators WHERE evidence_id = ?", (evidence_id,)).fetchone()
        if row is None:
            raise GovernanceError(f"Unknown evidence: {evidence_id}")
        return _evidence_from_row(row)

    def _require_approval(self, target_type: str, target_id: str) -> None:
        reviews = self.list_reviews(target_type, target_id)
        if not reviews or reviews[-1].decision is not ReviewDecision.APPROVE:
            raise GovernanceError(f"{target_type} {target_id} requires a latest human approval before publication")

    def _ensure_target_exists(self, target_type: str, target_id: str) -> None:
        if target_type == "document":
            self.get_document_version(target_id)
        elif target_type == "graph":
            self.get_graph_version(target_id)
        else:
            self.get_fmea_task(target_id)

    @staticmethod
    def _next_document_version(connection: sqlite3.Connection, document_id: str) -> tuple[int, str | None]:
        row = connection.execute(
            "SELECT version, version_id FROM document_versions WHERE document_id = ? ORDER BY version DESC LIMIT 1",
            (document_id,),
        ).fetchone()
        return (int(row["version"]) + 1, str(row["version_id"])) if row else (1, None)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _chunk_to_payload(chunk: Any, source_name: str, index: int) -> dict[str, Any]:
    get = chunk.get if isinstance(chunk, Mapping) else lambda key, default=None: getattr(chunk, key, default)
    metadata = dict(get("metadata", {}) or {})
    chunk_id = str(get("chunk_id") or get("id") or f"chunk-{index:05d}").strip()
    text = str(get("text") or get("content") or "").strip()
    if not text:
        raise ValueError(f"Chunk {chunk_id} has no text")
    page = get("page") or get("page_num") or metadata.get("page") or metadata.get("page_num")
    return {
        "chunk_id": chunk_id,
        "text": text,
        "source_file": str(get("source_file") or metadata.get("source_file") or source_name),
        "page": str(page) if page not in (None, "") else None,
        "block_id": _optional_text(get("block_id") or metadata.get("block_id")),
        "table_id": _optional_text(get("table_id") or metadata.get("table_id")),
        "image_id": _optional_text(get("image_id") or metadata.get("image_id")),
        "metadata": metadata,
    }


def _intake_issues(
    *,
    version_id: str,
    intake_status: str,
    evidence: Sequence[EvidenceLocator],
    quality: Mapping[str, Any],
    warnings: Sequence[str],
    errors: Sequence[str],
) -> tuple[QualityIssue, ...]:
    raw: list[tuple[str, str, IssueSeverity, dict[str, Any]]] = []
    if not evidence:
        raw.append(("empty_document", "No indexable evidence chunks were produced.", IssueSeverity.ERROR, {}))
    if intake_status != "parsed":
        raw.append(("intake_not_parsed", f"Document intake status is {intake_status}.", IssueSeverity.ERROR, {}))
    gate = str(quality.get("quality_gate_status") or quality.get("status") or "").lower()
    if gate and gate != "pass":
        raw.append((
            "quality_gate_failed",
            f"Document quality gate status is {gate}.",
            IssueSeverity.ERROR,
            dict(quality),
        ))
    raw.extend(("intake_error", str(message), IssueSeverity.ERROR, {}) for message in errors if str(message).strip())
    raw.extend(
        ("intake_warning", str(message), IssueSeverity.WARNING, {}) for message in warnings if str(message).strip()
    )
    return tuple(
        QualityIssue(
            issue_id=f"{version_id}:Q{index:03d}",
            code=code,
            message=message,
            severity=severity,
            metadata=metadata,
        )
        for index, (code, message, severity, metadata) in enumerate(raw, start=1)
    )


def _normalize_graph_statements(  # noqa: C901 - one pass keeps validation issues aligned to statements
    *,
    graph_version_id: str,
    raw_statements: Sequence[GraphStatement | Mapping[str, Any]],
    schema: GraphDomainSchema,
    allowed_evidence: Mapping[str, str],
) -> tuple[list[GraphStatement], list[QualityIssue]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    issue_specs: list[tuple[str, str, IssueSeverity, tuple[str, ...], dict[str, Any]]] = []
    for index, raw in enumerate(raw_statements, start=1):
        payload = raw.to_dict() if isinstance(raw, GraphStatement) else dict(raw)
        subject = schema.normalize_entity(str(payload.get("subject") or ""))
        object_name = schema.normalize_entity(
            str(payload.get("object_name") or payload.get("object") or payload.get("target") or "")
        )
        predicate = schema.normalize_relation(str(payload.get("predicate") or payload.get("relation") or ""))
        subject_type = str(payload.get("subject_type") or "").strip().upper()
        object_type = str(payload.get("object_type") or payload.get("target_type") or "").strip().upper()
        evidence_ids = tuple(
            dict.fromkeys(str(item).strip() for item in payload.get("evidence_ids", ()) if str(item).strip())
        )
        confidence = _optional_float(payload.get("confidence"))
        label = f"statement #{index}"

        if not subject or not object_name or not predicate:
            issue_specs.append((
                "invalid_statement",
                f"{label} is missing subject, predicate, or object.",
                IssueSeverity.ERROR,
                evidence_ids,
                {},
            ))
            continue
        if subject_type not in schema.entity_types:
            issue_specs.append((
                "unknown_entity_type",
                f"{label} has unsupported subject type {subject_type or '<empty>'}.",
                IssueSeverity.ERROR,
                evidence_ids,
                {"statement": index},
            ))
        if object_type not in schema.entity_types:
            issue_specs.append((
                "unknown_entity_type",
                f"{label} has unsupported object type {object_type or '<empty>'}.",
                IssueSeverity.ERROR,
                evidence_ids,
                {"statement": index},
            ))
        if predicate not in schema.relation_types:
            issue_specs.append((
                "unknown_relation_type",
                f"{label} has unsupported relation {predicate}.",
                IssueSeverity.ERROR,
                evidence_ids,
                {"statement": index},
            ))
        missing_evidence = tuple(item for item in evidence_ids if item not in allowed_evidence)
        if not evidence_ids or missing_evidence:
            issue_specs.append((
                "missing_source_evidence",
                f"{label} has no evidence or references evidence outside the selected material versions.",
                IssueSeverity.ERROR,
                evidence_ids,
                {"missing_evidence_ids": list(missing_evidence)},
            ))
        if confidence is None or confidence < schema.min_confidence:
            issue_specs.append((
                "low_confidence",
                f"{label} confidence is below {schema.min_confidence:.2f}.",
                IssueSeverity.WARNING,
                evidence_ids,
                {"confidence": confidence},
            ))
        key = (subject, predicate, object_name)
        existing = merged.setdefault(
            key,
            {
                "subject": subject,
                "predicate": predicate,
                "object_name": object_name,
                "subject_type": subject_type,
                "object_type": object_type,
                "evidence_ids": [],
                "confidence": confidence,
                "metadata": dict(payload.get("metadata") or {}),
            },
        )
        existing["evidence_ids"] = list(dict.fromkeys([*existing["evidence_ids"], *evidence_ids]))
        if confidence is not None and (existing["confidence"] is None or confidence > existing["confidence"]):
            existing["confidence"] = confidence

    conflict_groups: dict[tuple[str, str], set[str]] = {}
    for subject, predicate, object_name in merged:
        conflict_groups.setdefault((subject, predicate), set()).add(object_name)
    for (subject, predicate), objects in conflict_groups.items():
        if len(objects) > 1:
            evidence_ids = tuple(
                dict.fromkeys(
                    evidence_id for obj in objects for evidence_id in merged[(subject, predicate, obj)]["evidence_ids"]
                )
            )
            issue_specs.append((
                "source_conflict",
                f"{subject} / {predicate} has conflicting objects: {', '.join(sorted(objects))}.",
                IssueSeverity.WARNING,
                evidence_ids,
                {"subject": subject, "predicate": predicate, "objects": sorted(objects)},
            ))

    statements = [
        GraphStatement(
            statement_id=f"{graph_version_id}:S{index:04d}",
            subject=item["subject"],
            predicate=item["predicate"],
            object_name=item["object_name"],
            subject_type=item["subject_type"],
            object_type=item["object_type"],
            evidence_ids=tuple(item["evidence_ids"]),
            confidence=item["confidence"],
            metadata=item["metadata"],
        )
        for index, item in enumerate(merged.values(), start=1)
    ]
    issues = [
        QualityIssue(
            issue_id=f"{graph_version_id}:Q{index:03d}",
            code=code,
            message=message,
            severity=severity,
            evidence_ids=evidence_ids,
            metadata=metadata,
        )
        for index, (code, message, severity, evidence_ids, metadata) in enumerate(issue_specs, start=1)
    ]
    return statements, issues


def _document_from_rows(row: sqlite3.Row, evidence_rows: Sequence[sqlite3.Row]) -> CanonicalDocumentVersion:
    return CanonicalDocumentVersion(
        version_id=str(row["version_id"]),
        document_id=str(row["document_id"]),
        version=int(row["version"]),
        source_name=str(row["source_name"]),
        content_hash=str(row["content_hash"]),
        status=ContentStatus(str(row["status"])),
        evidence=tuple(_evidence_from_row(item) for item in evidence_rows),
        quality_issues=tuple(_quality_issue_from_dict(item) for item in _json_load(row["quality_issues_json"], [])),
        metadata=_json_load(row["metadata_json"], {}),
        created_at=str(row["created_at"]),
        published_at=_optional_text(row["published_at"]),
        supersedes_version_id=_optional_text(row["supersedes_version_id"]),
    )


def _evidence_from_row(row: sqlite3.Row) -> EvidenceLocator:
    return EvidenceLocator(
        evidence_id=str(row["evidence_id"]),
        document_version_id=str(row["document_version_id"]),
        chunk_id=str(row["chunk_id"]),
        text=str(row["text"]),
        source_file=str(row["source_file"]),
        page=_optional_text(row["page"]),
        block_id=_optional_text(row["block_id"]),
        table_id=_optional_text(row["table_id"]),
        image_id=_optional_text(row["image_id"]),
        metadata=_json_load(row["metadata_json"], {}),
    )


def _graph_from_rows(row: sqlite3.Row, statement_rows: Sequence[sqlite3.Row]) -> GraphVersion:
    schema_payload = _json_load(row["schema_json"], {})
    schema = GraphDomainSchema(
        entity_types=tuple(schema_payload.get("entity_types") or ()),
        relation_types=tuple(schema_payload.get("relation_types") or ()),
        entity_aliases=dict(schema_payload.get("entity_aliases") or {}),
        relation_aliases=dict(schema_payload.get("relation_aliases") or {}),
        min_confidence=float(schema_payload.get("min_confidence", 0.7)),
    )
    statements = tuple(
        GraphStatement(
            statement_id=str(item["statement_id"]),
            subject=str(item["subject"]),
            predicate=str(item["predicate"]),
            object_name=str(item["object_name"]),
            subject_type=str(item["subject_type"]),
            object_type=str(item["object_type"]),
            evidence_ids=tuple(_json_load(item["evidence_ids_json"], [])),
            confidence=_optional_float(item["confidence"]),
            metadata=_json_load(item["metadata_json"], {}),
        )
        for item in statement_rows
    )
    return GraphVersion(
        graph_version_id=str(row["graph_version_id"]),
        version=int(row["version"]),
        status=ContentStatus(str(row["status"])),
        source_document_version_ids=tuple(_json_load(row["source_document_version_ids_json"], [])),
        statements=statements,
        quality_issues=tuple(_quality_issue_from_dict(item) for item in _json_load(row["quality_issues_json"], [])),
        schema=schema,
        metadata=_json_load(row["metadata_json"], {}),
        created_at=str(row["created_at"]),
        published_at=_optional_text(row["published_at"]),
        supersedes_version_id=_optional_text(row["supersedes_version_id"]),
    )


def _quality_issue_from_dict(payload: Mapping[str, Any]) -> QualityIssue:
    return QualityIssue(
        issue_id=str(payload.get("issue_id") or ""),
        code=str(payload.get("code") or ""),
        message=str(payload.get("message") or ""),
        severity=IssueSeverity(str(payload.get("severity") or IssueSeverity.WARNING.value)),
        evidence_ids=tuple(payload.get("evidence_ids") or ()),
        resolved=bool(payload.get("resolved", False)),
        metadata=dict(payload.get("metadata") or {}),
    )


def _review_from_row(row: sqlite3.Row) -> ReviewRecord:
    return ReviewRecord(
        review_id=int(row["review_id"]),
        target_type=str(row["target_type"]),
        target_id=str(row["target_id"]),
        reviewer=str(row["reviewer"]),
        decision=ReviewDecision(str(row["decision"])),
        comment=str(row["comment"]),
        corrections=_json_load(row["corrections_json"], {}),
        created_at=str(row["created_at"]),
    )


def _fmea_task_from_row(row: sqlite3.Row) -> FMEATaskResult:
    request_payload = _json_load(row["request_json"], {})
    request = FMEATaskRequest(
        requested_by=str(request_payload.get("requested_by") or ""),
        graph_version_id=str(request_payload.get("graph_version_id") or ""),
        document_version_ids=tuple(request_payload.get("document_version_ids") or ()),
        template=str(request_payload.get("template") or "gas_turbine_minimum_v1"),
        metadata=dict(request_payload.get("metadata") or {}),
    )
    items = tuple(_fmea_item_from_dict(payload) for payload in _json_load(row["items_json"], []))
    return FMEATaskResult(
        task_id=str(row["task_id"]),
        request=request,
        status=TaskStatus(str(row["status"])),
        items=items,
        errors=tuple(_json_load(row["errors_json"], [])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        published_at=_optional_text(row["published_at"]),
    )


def _fmea_item_from_dict(payload: Mapping[str, Any]) -> FMEAItem:
    return FMEAItem(
        item_id=str(payload.get("item_id") or ""),
        fields=dict(payload.get("fields") or {}),
        field_evidence={key: tuple(value or ()) for key, value in dict(payload.get("field_evidence") or {}).items()},
        issues=tuple(_quality_issue_from_dict(item) for item in payload.get("issues") or ()),
        review_status=str(payload.get("review_status") or "pending"),
        metadata=dict(payload.get("metadata") or {}),
    )


def _feedback_module(code: str) -> str:
    normalized = str(code).strip().lower()
    if any(token in normalized for token in ("ocr", "parse", "page", "layout", "table")):
        return "M2"
    if any(token in normalized for token in ("document", "chunk", "index", "version", "retrieval")):
        return "M3"
    if any(token in normalized for token in ("graph", "entity", "relation", "schema", "conflict")):
        return "M4"
    return "M5"


def _required(value: Any, name: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{name} must not be empty")
    return clean


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    clean = str(value).strip()
    return clean or None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_load(payload: str | None, default: Any) -> Any:
    if not payload:
        return default
    try:
        return json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return default
