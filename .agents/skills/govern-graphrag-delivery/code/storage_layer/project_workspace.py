"""Project isolation, task center, audit, and workspace layout for PowerRAG V1.

The governed delivery database remains the source of truth for M2-M5 objects.
This registry is the product control plane above it: every project receives a
separate runtime directory and every long-running operation is discoverable by
project, status, stage, severity, and correlation id.
"""
# ruff: noqa: TRY003

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import traceback
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from core_domain.delivery import FMEA_FIELDS, DeliveryTask, GraphDomainSchema, Project, TaskStatus
from storage_layer.governance_store import GovernanceStore
from storage_layer.graph_store import GraphStore


class ProjectWorkspaceError(RuntimeError):
    """Raised when a project or task operation violates the product contract."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "project_workspace_error",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
PROJECT_DIRECTORIES = (
    "source_assets",
    "governance",
    "retrieval/chroma",
    "graph",
    "exports",
    "logs",
    "manifests",
)

TERMINAL_TASK_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.PUBLISHED,
}


class ProjectWorkspaceRegistry:
    """Durable catalog for projects, delivery tasks, idempotency, and audit."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.db_path = self.root_dir / "project_control.sqlite3"
        self.initialize()

    def initialize(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    domain TEXT NOT NULL DEFAULT 'gas_turbine',
                    status TEXT NOT NULL DEFAULT 'active',
                    configuration_json TEXT NOT NULL DEFAULT '{}',
                    data_policy_json TEXT NOT NULL DEFAULT '{}',
                    acceptance_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS delivery_tasks (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    severity TEXT NOT NULL DEFAULT 'info',
                    object_type TEXT,
                    object_id TEXT,
                    assigned_to TEXT,
                    correlation_id TEXT NOT NULL,
                    idempotency_key TEXT,
                    retryable INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    error_message TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    created_by TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_expires_at TEXT,
                    heartbeat_at TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_delivery_tasks_idempotency
                ON delivery_tasks(project_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_delivery_tasks_filter
                ON delivery_tasks(project_id, status, stage, severity, created_at DESC, task_id DESC);
                CREATE INDEX IF NOT EXISTS idx_delivery_tasks_correlation
                ON delivery_tasks(correlation_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS audit_records (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    object_version TEXT,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    change_summary_json TEXT NOT NULL DEFAULT '{}',
                    correlation_id TEXT NOT NULL,
                    client_request_id TEXT,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_project_object
                ON audit_records(project_id, object_type, object_id, audit_id DESC);

                CREATE TABLE IF NOT EXISTS provider_registrations (
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    provider_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    provider_type TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '',
                    timeout_seconds REAL NOT NULL DEFAULT 120,
                    cost_class TEXT NOT NULL DEFAULT 'local',
                    data_policy_json TEXT NOT NULL DEFAULT '{}',
                    capabilities_json TEXT NOT NULL DEFAULT '{}',
                    health_status TEXT NOT NULL DEFAULT 'unknown',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    configuration_json TEXT NOT NULL DEFAULT '{}',
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, provider_id)
                );
                CREATE INDEX IF NOT EXISTS idx_provider_capability
                ON provider_registrations(project_id, capability, enabled, health_status);

                CREATE TABLE IF NOT EXISTS graph_schema_versions (
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    schema_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    definition_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    approved_by TEXT,
                    approved_at TEXT,
                    PRIMARY KEY (project_id, schema_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_graph_schema_catalog
                ON graph_schema_versions(project_id, status, schema_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS fmea_template_versions (
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    template_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    definition_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    approved_by TEXT,
                    approved_at TEXT,
                    PRIMARY KEY (project_id, template_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_fmea_template_catalog
                ON fmea_template_versions(project_id, status, template_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS projection_states (
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    projection_name TEXT NOT NULL,
                    source_version_id TEXT,
                    status TEXT NOT NULL,
                    item_count INTEGER,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, projection_name)
                );

                CREATE TABLE IF NOT EXISTS task_comments (
                    comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES delivery_tasks(task_id),
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    actor TEXT NOT NULL,
                    message TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_task_comments_task
                ON task_comments(project_id, task_id, comment_id);

                CREATE TABLE IF NOT EXISTS idempotency_records (
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    idempotency_key TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    status_code INTEGER,
                    content_type TEXT,
                    response_body BLOB,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, idempotency_key)
                );
                """
            )
            task_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(delivery_tasks)").fetchall()
            }
            if "assigned_to" not in task_columns:
                connection.execute("ALTER TABLE delivery_tasks ADD COLUMN assigned_to TEXT")
        self.ensure_default_project()

    def ensure_default_project(self) -> Project:
        try:
            project = self.get_project("default")
        except ProjectWorkspaceError:
            return self.create_project(
                project_id="default",
                name="默认项目",
                created_by="system",
                description="兼容既有单项目数据与接口的本地默认项目。",
            )
        else:
            self._ensure_builtin_providers(project.project_id)
            self._ensure_builtin_graph_schemas(project.project_id)
            self._ensure_builtin_fmea_templates(project.project_id)
            return project

    def create_project(
        self,
        *,
        project_id: str,
        name: str,
        created_by: str,
        description: str = "",
        domain: str = "gas_turbine",
        configuration: Mapping[str, Any] | None = None,
        data_policy: Mapping[str, Any] | None = None,
        acceptance: Mapping[str, Any] | None = None,
    ) -> Project:
        project_id = _project_id(project_id)
        name = _required(name, "name")
        created_by = _required(created_by, "created_by")
        now = _utc_now()
        payload = Project(
            project_id=project_id,
            name=name,
            description=str(description).strip(),
            domain=_required(domain, "domain"),
            configuration=dict(configuration or {}),
            data_policy=dict(data_policy or {"external_providers_allowed": False}),
            acceptance=dict(acceptance or {}),
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO projects (
                        project_id, name, description, domain, status,
                        configuration_json, data_policy_json, acceptance_json,
                        created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.project_id,
                        payload.name,
                        payload.description,
                        payload.domain,
                        payload.status,
                        _json_dump(payload.configuration),
                        _json_dump(payload.data_policy),
                        _json_dump(payload.acceptance),
                        payload.created_by,
                        payload.created_at,
                        payload.updated_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ProjectWorkspaceError(
                    f"Project already exists: {project_id}",
                    code="project_already_exists",
                    details={"project_id": project_id},
                ) from exc
        self._create_workspace(payload)
        self.append_audit(
            project_id=project_id,
            object_type="project",
            object_id=project_id,
            action="create",
            actor=created_by,
            reason="Project workspace created",
            change_summary={"name": name, "domain": payload.domain},
            correlation_id=f"project-create-{uuid4().hex}",
            result="success",
        )
        self._ensure_builtin_providers(project_id)
        self._ensure_builtin_graph_schemas(project_id)
        self._ensure_builtin_fmea_templates(project_id)
        return payload

    def get_project(self, project_id: str) -> Project:
        project_id = _project_id(project_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if row is None:
            raise ProjectWorkspaceError(
                f"Unknown project: {project_id}",
                code="project_not_found",
                details={"project_id": project_id},
            )
        return _project_from_row(row)

    def list_projects(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        limit = max(1, min(int(limit), 200))
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(str(status))
        if cursor:
            clauses.append("project_id > ?")
            params.append(str(cursor))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM projects {where} ORDER BY project_id LIMIT ?",  # noqa: S608
                (*params, limit + 1),
            ).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        projects = [_project_from_row(row).to_dict() for row in rows]
        return {
            "items": projects,
            "count": len(projects),
            "next_cursor": projects[-1]["project_id"] if has_more and projects else None,
        }

    def update_project(
        self,
        project_id: str,
        *,
        actor: str,
        expected_updated_at: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        configuration: Mapping[str, Any] | None = None,
        data_policy: Mapping[str, Any] | None = None,
        acceptance: Mapping[str, Any] | None = None,
        reason: str = "",
        correlation_id: str | None = None,
    ) -> Project:
        current = self.get_project(project_id)
        if current.updated_at != str(expected_updated_at):
            raise ProjectWorkspaceError(
                "Project was modified by another request",
                code="version_conflict",
                details={"expected_version": expected_updated_at, "actual_version": current.updated_at},
            )
        now = _utc_now()
        updated = replace(
            current,
            name=_required(name, "name") if name is not None else current.name,
            description=str(description).strip() if description is not None else current.description,
            status=_required(status, "status") if status is not None else current.status,
            configuration=dict(configuration) if configuration is not None else current.configuration,
            data_policy=dict(data_policy) if data_policy is not None else current.data_policy,
            acceptance=dict(acceptance) if acceptance is not None else current.acceptance,
            updated_at=now,
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET name = ?, description = ?, status = ?, configuration_json = ?,
                    data_policy_json = ?, acceptance_json = ?, updated_at = ?
                WHERE project_id = ? AND updated_at = ?
                """,
                (
                    updated.name,
                    updated.description,
                    updated.status,
                    _json_dump(updated.configuration),
                    _json_dump(updated.data_policy),
                    _json_dump(updated.acceptance),
                    now,
                    current.project_id,
                    current.updated_at,
                ),
            )
            if cursor.rowcount != 1:
                raise ProjectWorkspaceError("Project update conflict", code="version_conflict")
        self._write_project_manifest(updated)
        self.append_audit(
            project_id=project_id,
            object_type="project",
            object_id=project_id,
            object_version=now,
            action="update",
            actor=actor,
            reason=reason,
            change_summary={
                key: value
                for key, value in {
                    "name": name,
                    "description": description,
                    "status": status,
                    "configuration": dict(configuration) if configuration is not None else None,
                    "data_policy": dict(data_policy) if data_policy is not None else None,
                    "acceptance": dict(acceptance) if acceptance is not None else None,
                }.items()
                if value is not None
            },
            correlation_id=correlation_id or f"project-update-{uuid4().hex}",
            result="success",
        )
        return updated

    def project_dir(self, project_id: str) -> Path:
        project_id = self.get_project(project_id).project_id
        resolved = (self.root_dir / project_id).resolve()
        try:
            resolved.relative_to(self.root_dir)
        except ValueError as exc:
            raise ProjectWorkspaceError("Project path escapes workspace", code="unsafe_project_path") from exc
        return resolved

    def governance_store(self, project_id: str) -> GovernanceStore:
        project = self.get_project(project_id)
        return GovernanceStore(
            self.project_dir(project.project_id) / "governance" / "delivery.sqlite3",
            project_id=project.project_id,
        )

    def graph_store(self, project_id: str) -> GraphStore:
        store = GraphStore(self.project_dir(project_id) / "graph" / "graph.sqlite3")
        store.initialize(reset=False)
        return store

    def upsert_provider(
        self,
        *,
        project_id: str,
        provider_id: str,
        capability: str,
        provider_type: str,
        actor: str,
        model: str = "",
        version: str = "",
        timeout_seconds: float = 120.0,
        cost_class: str = "local",
        data_policy: Mapping[str, Any] | None = None,
        capabilities: Mapping[str, Any] | None = None,
        health_status: str = "unknown",
        enabled: bool = True,
        configuration: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        provider_id = _required(provider_id, "provider_id")
        capability = _required(capability, "capability")
        provider_type = _required(provider_type, "provider_type").lower()
        if provider_type not in {"local", "external"}:
            raise ValueError("provider_type must be local or external")
        health_status = _required(health_status, "health_status").lower()
        if health_status not in {"ready", "degraded", "failed", "unknown", "disabled"}:
            raise ValueError("Unsupported provider health_status")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO provider_registrations (
                    project_id, provider_id, capability, provider_type, model, version,
                    timeout_seconds, cost_class, data_policy_json, capabilities_json,
                    health_status, enabled, configuration_json, updated_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, provider_id) DO UPDATE SET
                    capability = excluded.capability,
                    provider_type = excluded.provider_type,
                    model = excluded.model,
                    version = excluded.version,
                    timeout_seconds = excluded.timeout_seconds,
                    cost_class = excluded.cost_class,
                    data_policy_json = excluded.data_policy_json,
                    capabilities_json = excluded.capabilities_json,
                    health_status = excluded.health_status,
                    enabled = excluded.enabled,
                    configuration_json = excluded.configuration_json,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (
                    project_id,
                    provider_id,
                    capability,
                    provider_type,
                    str(model).strip(),
                    str(version).strip(),
                    max(1.0, float(timeout_seconds)),
                    _required(cost_class, "cost_class"),
                    _json_dump(dict(data_policy or {})),
                    _json_dump(dict(capabilities or {})),
                    health_status,
                    1 if enabled else 0,
                    _json_dump(dict(configuration or {})),
                    _required(actor, "actor"),
                    now,
                ),
            )
        provider = self.get_provider(project_id, provider_id)
        self._write_provider_manifest(project_id)
        self.append_audit(
            project_id=project_id,
            object_type="provider",
            object_id=provider_id,
            object_version=now,
            action="upsert",
            actor=actor,
            reason="Provider registration updated",
            change_summary={
                "capability": capability,
                "provider_type": provider_type,
                "model": model,
                "version": version,
                "health_status": health_status,
                "enabled": enabled,
            },
            correlation_id=correlation_id or f"provider-upsert-{uuid4().hex}",
            result="success",
        )
        return provider

    def get_provider(self, project_id: str, provider_id: str) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM provider_registrations WHERE project_id = ? AND provider_id = ?",
                (project_id, _required(provider_id, "provider_id")),
            ).fetchone()
        if row is None:
            raise ProjectWorkspaceError(
                f"Unknown provider: {provider_id}",
                code="provider_not_found",
                details={"project_id": project_id, "provider_id": provider_id},
            )
        return _provider_from_row(row)

    def list_providers(
        self,
        *,
        project_id: str,
        capability: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if capability:
            clauses.append("capability = ?")
            params.append(str(capability))
        if enabled is not None:
            clauses.append("enabled = ?")
            params.append(1 if enabled else 0)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM provider_registrations
                WHERE {' AND '.join(clauses)}
                ORDER BY capability, provider_id
                """,  # noqa: S608
                params,
            ).fetchall()
        items = [_provider_from_row(row) for row in rows]
        return {"project_id": project_id, "items": items, "count": len(items)}

    def register_graph_schema(
        self,
        *,
        project_id: str,
        schema_id: str,
        version: str,
        definition: Mapping[str, Any],
        actor: str,
        status: str = "draft",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        schema_id = _catalog_id(schema_id, "schema_id")
        version = _required(version, "version")
        normalized_status = _required(status, "status").lower()
        if normalized_status not in {"draft", "approved", "retired"}:
            raise ValueError("Graph schema status must be draft, approved, or retired")
        payload = dict(definition)
        if not payload.get("entity_types") or not payload.get("relation_types"):
            raise ProjectWorkspaceError(
                "Graph schema must define entity_types and relation_types",
                code="invalid_graph_schema",
            )
        content_hash = hashlib.sha256(_json_dump(payload).encode("utf-8")).hexdigest()
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM graph_schema_versions
                WHERE project_id = ? AND schema_id = ? AND version = ?
                """,
                (project_id, schema_id, version),
            ).fetchone()
            if existing is not None:
                current = _graph_schema_from_row(existing)
                if current["content_hash"] == content_hash:
                    return current
                raise ProjectWorkspaceError(
                    "Graph schema versions are immutable; register a new version",
                    code="graph_schema_version_exists",
                    details={"schema_id": schema_id, "version": version},
                )
            connection.execute(
                """
                INSERT INTO graph_schema_versions (
                    project_id, schema_id, version, status, definition_json,
                    content_hash, created_by, created_at, approved_by, approved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    schema_id,
                    version,
                    normalized_status,
                    _json_dump(payload),
                    content_hash,
                    _required(actor, "actor"),
                    now,
                    actor if normalized_status == "approved" else None,
                    now if normalized_status == "approved" else None,
                ),
            )
        self._write_graph_schema_manifest(project_id)
        self.append_audit(
            project_id=project_id,
            object_type="graph_schema",
            object_id=schema_id,
            object_version=version,
            action="register",
            actor=actor,
            reason=f"Registered graph schema {schema_id}@{version}",
            change_summary={"status": normalized_status, "content_hash": content_hash},
            correlation_id=correlation_id or f"schema-register-{uuid4().hex}",
            result="success",
        )
        return self.get_graph_schema(project_id, schema_id, version=version, approved_only=False)

    def approve_graph_schema(
        self,
        *,
        project_id: str,
        schema_id: str,
        version: str,
        actor: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        schema = self.get_graph_schema(project_id, schema_id, version=version, approved_only=False)
        if schema["status"] == "retired":
            raise ProjectWorkspaceError("Retired graph schema cannot be approved", code="graph_schema_retired")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE graph_schema_versions
                SET status = 'approved', approved_by = ?, approved_at = ?
                WHERE project_id = ? AND schema_id = ? AND version = ?
                """,
                (_required(actor, "actor"), now, project_id, schema_id, version),
            )
        self._write_graph_schema_manifest(project_id)
        self.append_audit(
            project_id=project_id,
            object_type="graph_schema",
            object_id=schema_id,
            object_version=version,
            action="approve",
            actor=actor,
            reason="Approved immutable graph schema version",
            change_summary={"content_hash": schema["content_hash"]},
            correlation_id=correlation_id or f"schema-approve-{uuid4().hex}",
            result="success",
        )
        return self.get_graph_schema(project_id, schema_id, version=version, approved_only=True)

    def get_graph_schema(
        self,
        project_id: str,
        schema_id: str,
        *,
        version: str | None = None,
        approved_only: bool = True,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        clauses = ["project_id = ?", "schema_id = ?"]
        params: list[Any] = [project_id, _catalog_id(schema_id, "schema_id")]
        if version:
            clauses.append("version = ?")
            params.append(str(version))
        if approved_only:
            clauses.append("status = 'approved'")
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT * FROM graph_schema_versions
                WHERE {' AND '.join(clauses)}
                ORDER BY approved_at DESC, created_at DESC LIMIT 1
                """,  # noqa: S608
                params,
            ).fetchone()
        if row is None:
            raise ProjectWorkspaceError(
                f"Unknown {'approved ' if approved_only else ''}graph schema: {schema_id}@{version or 'latest'}",
                code="graph_schema_not_found",
                details={"schema_id": schema_id, "version": version, "approved_only": approved_only},
            )
        return _graph_schema_from_row(row)

    def list_graph_schemas(
        self,
        *,
        project_id: str,
        status: str | None = None,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if status:
            clauses.append("status = ?")
            params.append(str(status))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM graph_schema_versions
                WHERE {' AND '.join(clauses)}
                ORDER BY schema_id, created_at DESC
                """,  # noqa: S608
                params,
            ).fetchall()
        items = [_graph_schema_from_row(row) for row in rows]
        return {"project_id": project_id, "items": items, "count": len(items)}

    def register_fmea_template(
        self,
        *,
        project_id: str,
        template_id: str,
        version: str,
        definition: Mapping[str, Any],
        actor: str,
        status: str = "draft",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        template_id = _catalog_id(template_id, "template_id")
        version = _required(version, "version")
        normalized_status = _required(status, "status").lower()
        if normalized_status not in {"draft", "approved", "retired"}:
            raise ValueError("FMEA template status must be draft, approved, or retired")
        payload = _validate_fmea_template_definition(
            definition,
            template_id=template_id,
            version=version,
        )
        content_hash = hashlib.sha256(_json_dump(payload).encode("utf-8")).hexdigest()
        now = _utc_now()
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT * FROM fmea_template_versions
                WHERE project_id = ? AND template_id = ? AND version = ?
                """,
                (project_id, template_id, version),
            ).fetchone()
            if existing is not None:
                current = _fmea_template_from_row(existing)
                if current["content_hash"] == content_hash:
                    return current
                raise ProjectWorkspaceError(
                    "FMEA template versions are immutable; register a new version",
                    code="fmea_template_version_exists",
                    details={"template_id": template_id, "version": version},
                )
            connection.execute(
                """
                INSERT INTO fmea_template_versions (
                    project_id, template_id, version, status, definition_json,
                    content_hash, created_by, created_at, approved_by, approved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    template_id,
                    version,
                    normalized_status,
                    _json_dump(payload),
                    content_hash,
                    _required(actor, "actor"),
                    now,
                    actor if normalized_status == "approved" else None,
                    now if normalized_status == "approved" else None,
                ),
            )
        self._write_fmea_template_manifest(project_id)
        self.append_audit(
            project_id=project_id,
            object_type="fmea_template",
            object_id=template_id,
            object_version=version,
            action="register",
            actor=actor,
            reason=f"Registered FMEA template {template_id}@{version}",
            change_summary={"status": normalized_status, "content_hash": content_hash},
            correlation_id=correlation_id or f"fmea-template-register-{uuid4().hex}",
            result="success",
        )
        return self.get_fmea_template(
            project_id,
            template_id,
            version=version,
            approved_only=False,
        )

    def approve_fmea_template(
        self,
        *,
        project_id: str,
        template_id: str,
        version: str,
        actor: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        template = self.get_fmea_template(
            project_id,
            template_id,
            version=version,
            approved_only=False,
        )
        if template["status"] == "retired":
            raise ProjectWorkspaceError(
                "Retired FMEA template cannot be approved",
                code="fmea_template_retired",
            )
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE fmea_template_versions
                SET status = 'approved', approved_by = ?, approved_at = ?
                WHERE project_id = ? AND template_id = ? AND version = ?
                """,
                (_required(actor, "actor"), now, project_id, template_id, version),
            )
        self._write_fmea_template_manifest(project_id)
        self.append_audit(
            project_id=project_id,
            object_type="fmea_template",
            object_id=template_id,
            object_version=version,
            action="approve",
            actor=actor,
            reason="Approved immutable FMEA template version",
            change_summary={"content_hash": template["content_hash"]},
            correlation_id=correlation_id or f"fmea-template-approve-{uuid4().hex}",
            result="success",
        )
        return self.get_fmea_template(project_id, template_id, version=version)

    def get_fmea_template(
        self,
        project_id: str,
        template_id: str,
        *,
        version: str | None = None,
        approved_only: bool = True,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        clauses = ["project_id = ?", "template_id = ?"]
        params: list[Any] = [project_id, _catalog_id(template_id, "template_id")]
        if version:
            clauses.append("version = ?")
            params.append(str(version))
        if approved_only:
            clauses.append("status = 'approved'")
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT * FROM fmea_template_versions
                WHERE {' AND '.join(clauses)}
                ORDER BY approved_at DESC, created_at DESC LIMIT 1
                """,  # noqa: S608
                params,
            ).fetchone()
        if row is None:
            raise ProjectWorkspaceError(
                f"Unknown {'approved ' if approved_only else ''}FMEA template: "
                f"{template_id}@{version or 'latest'}",
                code="fmea_template_not_found",
                details={
                    "template_id": template_id,
                    "version": version,
                    "approved_only": approved_only,
                },
            )
        return _fmea_template_from_row(row)

    def list_fmea_templates(
        self,
        *,
        project_id: str,
        status: str | None = None,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if status:
            clauses.append("status = ?")
            params.append(str(status))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM fmea_template_versions
                WHERE {' AND '.join(clauses)}
                ORDER BY template_id, created_at DESC
                """,  # noqa: S608
                params,
            ).fetchall()
        items = [_fmea_template_from_row(row) for row in rows]
        return {"project_id": project_id, "items": items, "count": len(items)}

    def begin_idempotent_request(
        self,
        *,
        project_id: str,
        idempotency_key: str,
        method: str,
        path: str,
        request_hash: str,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        key = _required(idempotency_key, "idempotency_key")
        method = _required(method, "method").upper()
        path = _required(path, "path")
        request_hash = _required(request_hash, "request_hash")
        now = _utc_now()
        created = False
        row = None
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO idempotency_records (
                        project_id, idempotency_key, method, path, request_hash,
                        state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'in_progress', ?, ?)
                    """,
                    (project_id, key, method, path, request_hash, now, now),
                )
            except sqlite3.IntegrityError:
                row = connection.execute(
                    """
                    SELECT * FROM idempotency_records
                    WHERE project_id = ? AND idempotency_key = ?
                    """,
                    (project_id, key),
                ).fetchone()
            else:
                created = True
        if created:
            return {
                "project_id": project_id,
                "idempotency_key": key,
                "state": "new",
            }
        if row is None:  # pragma: no cover - defensive race fallback
            raise ProjectWorkspaceError("Idempotency record disappeared", code="idempotency_conflict")
        if (
            str(row["method"]) != method
            or str(row["path"]) != path
            or str(row["request_hash"]) != request_hash
        ):
            raise ProjectWorkspaceError(
                "Idempotency key was already used for a different request",
                code="idempotency_key_reused",
                details={"method": row["method"], "path": row["path"]},
            )
        return {
            "project_id": project_id,
            "idempotency_key": key,
            "state": str(row["state"]),
            "status_code": row["status_code"],
            "content_type": _optional(row["content_type"]),
            "response_body": bytes(row["response_body"]) if row["response_body"] is not None else None,
        }

    def complete_idempotent_request(
        self,
        *,
        project_id: str,
        idempotency_key: str,
        status_code: int,
        content_type: str,
        response_body: bytes,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE idempotency_records
                SET state = 'completed', status_code = ?, content_type = ?,
                    response_body = ?, updated_at = ?
                WHERE project_id = ? AND idempotency_key = ?
                """,
                (
                    int(status_code),
                    str(content_type or "application/json"),
                    sqlite3.Binary(response_body),
                    _utc_now(),
                    self.get_project(project_id).project_id,
                    _required(idempotency_key, "idempotency_key"),
                ),
            )

    def abandon_idempotent_request(self, *, project_id: str, idempotency_key: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM idempotency_records WHERE project_id = ? AND idempotency_key = ?",
                (self.get_project(project_id).project_id, _required(idempotency_key, "idempotency_key")),
            )

    def authorize_provider_call(
        self,
        *,
        project_id: str,
        provider_id: str,
        capability: str,
        actor: str,
        data_scope: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        project = self.get_project(project_id)
        provider = self.get_provider(project_id, provider_id)
        if not provider["enabled"] or provider["health_status"] in {"failed", "disabled"}:
            raise ProjectWorkspaceError(
                "Provider is not available",
                code="provider_unavailable",
                details={"provider_id": provider_id, "health_status": provider["health_status"]},
            )
        if provider["capability"] != capability:
            raise ProjectWorkspaceError(
                "Provider capability does not match the requested operation",
                code="provider_capability_mismatch",
                details={"provider_id": provider_id, "expected": capability, "actual": provider["capability"]},
            )
        if provider["provider_type"] == "external":
            allowed = bool(project.data_policy.get("external_providers_allowed", False))
            allowed_ids = {str(item) for item in project.data_policy.get("allowed_provider_ids") or []}
            if not allowed or (allowed_ids and provider_id not in allowed_ids):
                raise ProjectWorkspaceError(
                    "Project data policy blocks this external provider",
                    code="external_provider_blocked",
                    details={"project_id": project_id, "provider_id": provider_id},
                )
        scope = dict(data_scope or {})
        self.append_audit(
            project_id=project_id,
            object_type="provider_call",
            object_id=provider_id,
            action="authorize",
            actor=actor,
            reason=f"Authorized provider capability {capability}",
            change_summary={
                "capability": capability,
                "provider_type": provider["provider_type"],
                "data_scope": scope,
            },
            correlation_id=correlation_id or f"provider-call-{uuid4().hex}",
            result="success",
        )
        return {**provider, "authorized": True, "data_scope": scope}

    def provider_health(self, project_id: str) -> dict[str, Any]:
        providers = self.list_providers(project_id=project_id)["items"]
        required_capabilities = {"document_parsing", "ocr", "embedding", "graph_extraction", "answer_generation"}
        available = {
            item["capability"]
            for item in providers
            if item["enabled"] and item["health_status"] in {"ready", "degraded"}
        }
        return {
            "project_id": project_id,
            "status": "ready" if required_capabilities <= available else "degraded",
            "providers": providers,
            "missing_capabilities": sorted(required_capabilities - available),
        }

    def create_task(
        self,
        *,
        project_id: str,
        task_type: str,
        stage: str,
        created_by: str,
        payload: Mapping[str, Any] | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        severity: str = "info",
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        retryable: bool = True,
    ) -> DeliveryTask:
        project_id = self.get_project(project_id).project_id
        normalized_key = _optional(idempotency_key)
        if normalized_key:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM delivery_tasks WHERE project_id = ? AND idempotency_key = ?",
                    (project_id, normalized_key),
                ).fetchone()
            if row is not None:
                return _task_from_row(row)
        now = _utc_now()
        task = DeliveryTask(
            task_id=f"DT-{uuid4().hex[:18]}",
            project_id=project_id,
            task_type=_required(task_type, "task_type"),
            status=TaskStatus.QUEUED,
            stage=_required(stage, "stage"),
            created_by=_required(created_by, "created_by"),
            severity=_required(severity, "severity"),
            object_type=_optional(object_type),
            object_id=_optional(object_id),
            correlation_id=_required(correlation_id or uuid4().hex, "correlation_id"),
            idempotency_key=normalized_key,
            retryable=bool(retryable),
            payload=dict(payload or {}),
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO delivery_tasks (
                        task_id, project_id, task_type, status, stage, progress,
                        severity, object_type, object_id, correlation_id,
                        idempotency_key, retryable, payload_json, result_json,
                        created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.project_id,
                        task.task_type,
                        task.status.value,
                        task.stage,
                        task.progress,
                        task.severity,
                        task.object_type,
                        task.object_id,
                        task.correlation_id,
                        task.idempotency_key,
                        1 if task.retryable else 0,
                        _json_dump(task.payload),
                        _json_dump(task.result),
                        task.created_by,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if normalized_key:
                    with self._connect() as retry_connection:
                        row = retry_connection.execute(
                            "SELECT * FROM delivery_tasks WHERE project_id = ? AND idempotency_key = ?",
                            (project_id, normalized_key),
                        ).fetchone()
                    if row is not None:
                        return _task_from_row(row)
                raise ProjectWorkspaceError("Could not create delivery task", code="task_create_failed") from exc
        self.append_audit(
            project_id=project_id,
            object_type="delivery_task",
            object_id=task.task_id,
            action="queue",
            actor=task.created_by,
            reason=f"Queued {task.task_type}",
            change_summary={"stage": task.stage, "object_type": object_type, "object_id": object_id},
            correlation_id=task.correlation_id,
            result="success",
        )
        return task

    def get_task(self, task_id: str, *, project_id: str | None = None) -> DeliveryTask:
        clauses = ["task_id = ?"]
        params: list[Any] = [_required(task_id, "task_id")]
        if project_id:
            clauses.append("project_id = ?")
            params.append(self.get_project(project_id).project_id)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM delivery_tasks WHERE {' AND '.join(clauses)}",  # noqa: S608
                params,
            ).fetchone()
        if row is None:
            raise ProjectWorkspaceError(
                f"Unknown delivery task: {task_id}",
                code="task_not_found",
                details={"task_id": task_id},
            )
        return _task_from_row(row)

    def list_tasks(
        self,
        *,
        project_id: str,
        statuses: Sequence[str] = (),
        stage: str | None = None,
        severity: str | None = None,
        task_type: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        limit = max(1, min(int(limit), 200))
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        normalized_statuses = [TaskStatus(value).value for value in statuses if str(value).strip()]
        if normalized_statuses:
            placeholders = ",".join("?" for _ in normalized_statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(normalized_statuses)
        for column, value in (("stage", stage), ("severity", severity), ("task_type", task_type)):
            if value:
                clauses.append(f"{column} = ?")
                params.append(str(value))
        if cursor:
            clauses.append("task_id < ?")
            params.append(str(cursor))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM delivery_tasks
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC, task_id DESC
                LIMIT ?
                """,  # noqa: S608
                (*params, limit + 1),
            ).fetchall()
        has_more = len(rows) > limit
        tasks = [_task_from_row(row).to_dict() for row in rows[:limit]]
        return {
            "project_id": project_id,
            "items": tasks,
            "count": len(tasks),
            "next_cursor": tasks[-1]["task_id"] if has_more and tasks else None,
        }

    def claim_task(
        self,
        task_id: str,
        *,
        worker_id: str,
        lease_seconds: int = 120,
    ) -> DeliveryTask:
        task = self.get_task(task_id)
        if task.status is not TaskStatus.QUEUED:
            raise ProjectWorkspaceError(
                f"Task {task_id} is not queued",
                code="task_not_claimable",
                details={"status": task.status.value},
            )
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=max(5, int(lease_seconds)))
        now_text = now.isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE delivery_tasks
                SET status = ?, lease_owner = ?, lease_expires_at = ?, heartbeat_at = ?,
                    started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (
                    TaskStatus.RUNNING.value,
                    _required(worker_id, "worker_id"),
                    expires.isoformat(),
                    now_text,
                    now_text,
                    now_text,
                    task_id,
                    TaskStatus.QUEUED.value,
                ),
            )
            if cursor.rowcount != 1:
                raise ProjectWorkspaceError("Task claim conflict", code="task_claim_conflict")
        return self.get_task(task_id)

    def heartbeat_task(
        self,
        task_id: str,
        *,
        worker_id: str,
        progress: float,
        stage: str | None = None,
        lease_seconds: int = 120,
    ) -> DeliveryTask:
        task = self.get_task(task_id)
        if task.status is not TaskStatus.RUNNING or task.lease_owner != worker_id:
            raise ProjectWorkspaceError("Task lease is not owned by this worker", code="task_lease_mismatch")
        normalized_progress = max(0.0, min(float(progress), 1.0))
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE delivery_tasks
                SET progress = ?, stage = ?, heartbeat_at = ?, lease_expires_at = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    normalized_progress,
                    str(stage or task.stage),
                    now.isoformat(),
                    (now + timedelta(seconds=max(5, int(lease_seconds)))).isoformat(),
                    now.isoformat(),
                    task_id,
                ),
            )
        return self.get_task(task_id)

    def finish_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | str,
        result: Mapping[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool | None = None,
        actor: str | None = None,
    ) -> DeliveryTask:
        task = self.get_task(task_id)
        normalized = status if isinstance(status, TaskStatus) else TaskStatus(str(status))
        if normalized not in TERMINAL_TASK_STATUSES and normalized is not TaskStatus.NEEDS_REVIEW:
            raise ValueError("finish status must be completed, failed, cancelled, published, or needs_review")
        if task.status in TERMINAL_TASK_STATUSES:
            if task.status is normalized:
                return task
            raise ProjectWorkspaceError("Terminal task cannot change status", code="task_terminal")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE delivery_tasks
                SET status = ?, progress = ?, result_json = ?, error_code = ?, error_message = ?,
                    retryable = ?, lease_owner = NULL, lease_expires_at = NULL,
                    completed_at = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    normalized.value,
                    1.0
                    if normalized in {TaskStatus.COMPLETED, TaskStatus.PUBLISHED, TaskStatus.NEEDS_REVIEW}
                    else task.progress,
                    _json_dump(dict(result or task.result)),
                    _optional(error_code),
                    _optional(error_message),
                    1 if (task.retryable if retryable is None else bool(retryable)) else 0,
                    now,
                    now,
                    task_id,
                ),
            )
        finished = self.get_task(task_id)
        self.append_audit(
            project_id=task.project_id,
            object_type="delivery_task",
            object_id=task_id,
            action=normalized.value,
            actor=actor or task.lease_owner or task.created_by,
            reason=error_message or f"Task {normalized.value}",
            change_summary={"error_code": error_code, "retryable": finished.retryable},
            correlation_id=task.correlation_id,
            result="success" if normalized is not TaskStatus.FAILED else "failed",
        )
        return finished

    def cancel_task(self, task_id: str, *, actor: str, reason: str) -> DeliveryTask:
        task = self.get_task(task_id)
        if task.status in TERMINAL_TASK_STATUSES:
            return task
        return self.finish_task(
            task_id,
            status=TaskStatus.CANCELLED,
            result={"cancel_reason": _required(reason, "reason")},
            retryable=False,
            actor=actor,
        )

    def retry_task(
        self,
        task_id: str,
        *,
        actor: str,
        idempotency_key: str | None = None,
    ) -> DeliveryTask:
        original = self.get_task(task_id)
        if original.status is not TaskStatus.FAILED or not original.retryable:
            raise ProjectWorkspaceError(
                "Only retryable failed tasks can be retried",
                code="task_not_retryable",
                details={"status": original.status.value, "retryable": original.retryable},
            )
        return self.create_task(
            project_id=original.project_id,
            task_type=original.task_type,
            stage=original.stage,
            created_by=actor,
            payload={**original.payload, "retry_of": original.task_id},
            object_type=original.object_type,
            object_id=original.object_id,
            severity=original.severity,
            idempotency_key=idempotency_key,
            correlation_id=original.correlation_id,
            retryable=True,
        )

    def assign_task(self, task_id: str, *, assignee: str, actor: str) -> DeliveryTask:
        task = self.get_task(task_id)
        normalized_assignee = _required(assignee, "assignee")
        normalized_actor = _required(actor, "actor")
        with self._connect() as connection:
            connection.execute(
                "UPDATE delivery_tasks SET assigned_to = ?, updated_at = ? WHERE task_id = ?",
                (normalized_assignee, _utc_now(), task_id),
            )
        self.append_audit(
            project_id=task.project_id,
            object_type="delivery_task",
            object_id=task_id,
            action="assign",
            actor=normalized_actor,
            reason=f"Assigned task to {normalized_assignee}",
            change_summary={"assigned_to": normalized_assignee},
            correlation_id=task.correlation_id,
            result="success",
        )
        return self.get_task(task_id)

    def add_task_comment(
        self,
        task_id: str,
        *,
        actor: str,
        message: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        task = self.get_task(task_id)
        normalized_actor = _required(actor, "actor")
        normalized_message = _required(message, "message")
        normalized_correlation = str(correlation_id or task.correlation_id or uuid4().hex)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO task_comments (
                    task_id, project_id, actor, message, correlation_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task.project_id,
                    normalized_actor,
                    normalized_message,
                    normalized_correlation,
                    _utc_now(),
                ),
            )
            comment_id = int(cursor.lastrowid)
        self.append_audit(
            project_id=task.project_id,
            object_type="delivery_task",
            object_id=task_id,
            action="comment",
            actor=normalized_actor,
            reason="Task comment added",
            change_summary={"comment_id": comment_id, "message_character_count": len(normalized_message)},
            correlation_id=normalized_correlation,
            result="success",
        )
        return self.list_task_comments(task_id)[-1]

    def list_task_comments(self, task_id: str) -> list[dict[str, Any]]:
        task = self.get_task(task_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT comment_id, task_id, project_id, actor, message, correlation_id, created_at
                FROM task_comments WHERE project_id = ? AND task_id = ? ORDER BY comment_id
                """,
                (task.project_id, task_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def append_audit(
        self,
        *,
        project_id: str,
        object_type: str,
        object_id: str,
        action: str,
        actor: str,
        correlation_id: str,
        result: str,
        object_version: str | None = None,
        reason: str = "",
        change_summary: Mapping[str, Any] | None = None,
        client_request_id: str | None = None,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        now = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_records (
                    project_id, object_type, object_id, object_version, action,
                    actor, reason, change_summary_json, correlation_id,
                    client_request_id, result, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    _required(object_type, "object_type"),
                    _required(object_id, "object_id"),
                    _optional(object_version),
                    _required(action, "action"),
                    _required(actor, "actor"),
                    str(reason).strip(),
                    _json_dump(dict(change_summary or {})),
                    _required(correlation_id, "correlation_id"),
                    _optional(client_request_id),
                    _required(result, "result"),
                    now,
                ),
            )
            audit_id = int(cursor.lastrowid or 0)
        return {
            "audit_id": audit_id,
            "project_id": project_id,
            "object_type": object_type,
            "object_id": object_id,
            "object_version": object_version,
            "action": action,
            "actor": actor,
            "reason": str(reason).strip(),
            "change_summary": dict(change_summary or {}),
            "correlation_id": correlation_id,
            "client_request_id": client_request_id,
            "result": result,
            "created_at": now,
        }

    def list_audit(
        self,
        *,
        project_id: str,
        object_type: str | None = None,
        object_id: str | None = None,
        limit: int = 100,
        before_audit_id: int | None = None,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if object_type:
            clauses.append("object_type = ?")
            params.append(str(object_type))
        if object_id:
            clauses.append("object_id = ?")
            params.append(str(object_id))
        if before_audit_id is not None:
            clauses.append("audit_id < ?")
            params.append(int(before_audit_id))
        limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM audit_records
                WHERE {' AND '.join(clauses)}
                ORDER BY audit_id DESC
                LIMIT ?
                """,  # noqa: S608
                (*params, limit + 1),
            ).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [
            {
                **{key: row[key] for key in row.keys() if key != "change_summary_json"},  # noqa: SIM118
                "change_summary": _json_load(row["change_summary_json"], {}),
            }
            for row in rows
        ]
        return {
            "project_id": project_id,
            "items": items,
            "count": len(items),
            "next_cursor": items[-1]["audit_id"] if has_more and items else None,
        }

    def record_projection_state(
        self,
        project_id: str,
        projection_name: str,
        *,
        status: str,
        source_version_id: str | None = None,
        item_count: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.get_project(project_id)
        projection_name = _required(projection_name, "projection_name")
        if status not in {"ready", "rebuilding", "failed", "not_initialized"}:
            raise ValueError(f"Unsupported projection status: {status}")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projection_states (
                    project_id, projection_name, source_version_id, status,
                    item_count, details_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, projection_name) DO UPDATE SET
                    source_version_id = excluded.source_version_id,
                    status = excluded.status,
                    item_count = excluded.item_count,
                    details_json = excluded.details_json,
                    updated_at = excluded.updated_at
                """,
                (
                    project_id,
                    projection_name,
                    source_version_id,
                    status,
                    item_count,
                    _json_dump(dict(details or {})),
                    _utc_now(),
                ),
            )
        return self.get_projection_state(project_id, projection_name) or {}

    def get_projection_state(self, project_id: str, projection_name: str) -> dict[str, Any] | None:
        self.get_project(project_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM projection_states
                WHERE project_id = ? AND projection_name = ?
                """,
                (project_id, projection_name),
            ).fetchone()
        if row is None:
            return None
        return {
            **{key: row[key] for key in row.keys() if key != "details_json"},  # noqa: SIM118
            "details": _json_load(row["details_json"], {}),
        }

    def health(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        workspace = self.project_dir(project_id)
        checks: dict[str, dict[str, Any]] = {}
        try:
            store = self.governance_store(project_id)
            with store._connect() as connection:
                connection.execute("SELECT 1").fetchone()
            checks["governance"] = {"status": "ready", "path": str(store.db_path)}
        except Exception as exc:  # pragma: no cover - platform/storage failure
            checks["governance"] = {"status": "failed", "message": str(exc)}
        graph_path = workspace / "graph" / "graph.sqlite3"
        graph_projection = self.get_projection_state(project_id, "graph_store")
        checks["graph"] = {
            "status": graph_projection["status"] if graph_projection else (
                "ready" if graph_path.exists() else "not_initialized"
            ),
            "path": str(graph_path),
            "projection": graph_projection,
        }
        retrieval_projection = self.get_projection_state(project_id, "governed_materials")
        checks["retrieval"] = {
            "status": retrieval_projection["status"] if retrieval_projection else (
                "ready" if (workspace / "retrieval" / "chroma").exists() else "not_initialized"
            ),
            "path": str(workspace / "retrieval" / "chroma"),
            "projection": retrieval_projection,
        }
        provider_health = self.provider_health(project_id)
        checks["providers"] = {
            "status": provider_health["status"],
            "missing_capabilities": provider_health["missing_capabilities"],
        }
        free_bytes = _free_bytes(workspace)
        checks["disk"] = {"status": "ready" if free_bytes > 512 * 1024 * 1024 else "warning", "free_bytes": free_bytes}
        with self._connect() as connection:
            failed = connection.execute(
                """
                SELECT task_id, task_type, stage, error_code, error_message, updated_at
                FROM delivery_tasks
                WHERE project_id = ? AND status = ?
                ORDER BY updated_at DESC LIMIT 10
                """,
                (project_id, TaskStatus.FAILED.value),
            ).fetchall()
        return {
            "project_id": project.project_id,
            "status": (
                "ready"
                if all(item["status"] not in {"failed", "degraded", "warning"} for item in checks.values())
                else "degraded"
            ),
            "checks": checks,
            "recent_failed_tasks": [dict(row) for row in failed],
            "checked_at": _utc_now(),
        }

    def record_http_metric(self, project_id: str, metric: Mapping[str, Any]) -> None:
        """Append a secret-free request metric to the project-local operational log."""

        project_id = self.get_project(project_id).project_id
        allowed = {
            "timestamp",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "actor",
            "correlation_id",
            "response_bytes",
        }
        payload = {key: metric.get(key) for key in allowed if key in metric}
        payload["project_id"] = project_id
        log_path = self.project_dir(project_id) / "logs" / "http-metrics.jsonl"
        _rotate_log(log_path)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    def record_task_failure(self, project_id: str, task_id: str, exc: BaseException) -> None:
        task = self.get_task(task_id, project_id=project_id)
        payload = {
            "timestamp": _utc_now(),
            "project_id": project_id,
            "task_id": task_id,
            "task_type": task.task_type,
            "stage": task.stage,
            "object_type": task.object_type,
            "object_id": task.object_id,
            "correlation_id": task.correlation_id,
            "error_code": str(getattr(exc, "code", "background_task_failed")),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "stacktrace": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        }
        log_path = self.project_dir(project_id) / "logs" / "task-errors.jsonl"
        _rotate_log(log_path)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    def http_metrics_summary(
        self,
        project_id: str,
        *,
        path_prefix: str | None = None,
        limit: int = 10000,
    ) -> dict[str, Any]:
        project_id = self.get_project(project_id).project_id
        log_path = self.project_dir(project_id) / "logs" / "http-metrics.jsonl"
        rows: list[dict[str, Any]] = []
        if log_path.is_file():
            for line in log_path.read_text(encoding="utf-8").splitlines()[-max(1, min(int(limit), 50000)) :]:
                payload = _json_load(line, {})
                if not isinstance(payload, dict):
                    continue
                if path_prefix and not str(payload.get("path") or "").startswith(path_prefix):
                    continue
                rows.append(payload)
        durations = [float(item.get("duration_ms") or 0) for item in rows]
        error_count = sum(int(item.get("status_code") or 0) >= 400 for item in rows)
        return {
            "project_id": project_id,
            "path_prefix": path_prefix,
            "sample_count": len(rows),
            "duration_ms": {
                "p50": _percentile(durations, 0.50),
                "p95": _percentile(durations, 0.95),
                "max": max(durations) if durations else None,
            },
            "error_count": error_count,
            "error_rate": round(error_count / len(rows), 6) if rows else None,
            "latest": rows[-20:],
        }

    def build_export_package(self, project_id: str) -> dict[str, Any]:
        project = self.get_project(project_id)
        workspace = self.project_dir(project_id)
        self._write_control_plane_manifest(project_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output_path = workspace / "exports" / f"{project.project_id}-backup-{timestamp}.zip"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot: list[tuple[str, bytes]] = []
        for path in sorted(workspace.rglob("*")):
            if not path.is_file() or path == output_path:
                continue
            relative = path.relative_to(workspace).as_posix()
            if relative.startswith("exports/") and relative.endswith(".zip"):
                continue
            snapshot.append((relative, path.read_bytes()))
        files = [
            {
                "path": relative,
                "byte_size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for relative, payload in snapshot
        ]
        manifest = {
            "format": "powerrag-project-package-v1",
            "project": project.to_dict(),
            "created_at": _utc_now(),
            "created_by": "system",
            "files": files,
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", manifest_bytes)
            for relative, payload in snapshot:
                archive.writestr(relative, payload)
        package = {
            "project_id": project_id,
            "path": str(output_path),
            "byte_size": output_path.stat().st_size,
            "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "file_count": len(files),
            "manifest": manifest,
        }
        self.append_audit(
            project_id=project_id,
            object_type="project",
            object_id=project_id,
            action="export_package",
            actor="system",
            reason="Project backup package created",
            change_summary={key: package[key] for key in ("byte_size", "sha256", "file_count")},
            correlation_id=f"project-export-{uuid4().hex}",
            result="success",
        )
        return package

    def verify_export_package(self, package_path: str | Path) -> dict[str, Any]:
        path = Path(package_path).resolve()
        if not path.is_file():
            raise ProjectWorkspaceError("Project package does not exist", code="package_not_found")
        with zipfile.ZipFile(path, "r") as archive:
            try:
                manifest = json.loads(archive.read("manifest.json"))
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                raise ProjectWorkspaceError("Project package manifest is invalid", code="invalid_package") from exc
            if manifest.get("format") != "powerrag-project-package-v1":
                raise ProjectWorkspaceError("Unsupported project package format", code="invalid_package")
            names = set(archive.namelist())
            mismatches: list[dict[str, Any]] = []
            for entry in manifest.get("files") or []:
                relative = _safe_archive_path(entry.get("path"))
                if relative not in names:
                    mismatches.append({"path": relative, "reason": "missing"})
                    continue
                payload = archive.read(relative)
                actual_hash = hashlib.sha256(payload).hexdigest()
                if actual_hash != str(entry.get("sha256") or ""):
                    mismatches.append({"path": relative, "reason": "sha256_mismatch"})
                try:
                    expected_size = int(entry["byte_size"])
                except (KeyError, TypeError, ValueError):
                    expected_size = -1
                if len(payload) != expected_size:
                    mismatches.append({"path": relative, "reason": "size_mismatch"})
            unsafe = [name for name in names if name != "manifest.json" and _unsafe_archive_path(name)]
            mismatches.extend({"path": name, "reason": "unsafe_path"} for name in unsafe)
        return {
            "path": str(path),
            "valid": not mismatches,
            "mismatches": mismatches,
            "manifest": manifest,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def restore_export_package(
        self,
        package_path: str | Path,
        *,
        project_id: str,
        name: str,
        actor: str,
    ) -> dict[str, Any]:
        verification = self.verify_export_package(package_path)
        if not verification["valid"]:
            raise ProjectWorkspaceError(
                "Project package failed integrity verification",
                code="package_integrity_failed",
                details={"mismatches": verification["mismatches"]},
            )
        source_project = dict(verification["manifest"].get("project") or {})
        project = self.create_project(
            project_id=project_id,
            name=name,
            created_by=actor,
            description=f"Restored from {source_project.get('project_id') or 'project package'}",
            domain=str(source_project.get("domain") or "gas_turbine"),
            configuration=dict(source_project.get("configuration") or {}),
            data_policy=dict(source_project.get("data_policy") or {}),
            acceptance=dict(source_project.get("acceptance") or {}),
        )
        workspace = self.project_dir(project_id)
        allowed_roots = {item.split("/", 1)[0] for item in PROJECT_DIRECTORIES}
        with zipfile.ZipFile(Path(package_path), "r") as archive:
            for entry in verification["manifest"].get("files") or []:
                relative = _safe_archive_path(entry.get("path"))
                if relative == "manifests/project.json":
                    continue
                if relative.split("/", 1)[0] not in allowed_roots:
                    raise ProjectWorkspaceError(
                        f"Package contains unsupported path: {relative}",
                        code="invalid_package_path",
                    )
                destination = (workspace / relative).resolve()
                destination.relative_to(workspace)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(relative))
        self._write_project_manifest(project)
        provider_manifest = workspace / "manifests" / "providers.json"
        if provider_manifest.is_file():
            restored_providers = _json_load(provider_manifest.read_text(encoding="utf-8"), {}).get("items") or []
            for provider in restored_providers:
                self.upsert_provider(
                    project_id=project_id,
                    provider_id=str(provider.get("provider_id") or ""),
                    capability=str(provider.get("capability") or ""),
                    provider_type=str(provider.get("provider_type") or "local"),
                    actor=actor,
                    model=str(provider.get("model") or ""),
                    version=str(provider.get("version") or ""),
                    timeout_seconds=float(provider.get("timeout_seconds") or 120),
                    cost_class=str(provider.get("cost_class") or "local"),
                    data_policy=dict(provider.get("data_policy") or {}),
                    capabilities=dict(provider.get("capabilities") or {}),
                    health_status=str(provider.get("health_status") or "unknown"),
                    enabled=bool(provider.get("enabled", True)),
                    configuration=dict(provider.get("configuration") or {}),
                )
        control_plane_manifest = workspace / "manifests" / "control-plane.json"
        restored_control_plane = {
            "tasks": 0,
            "task_comments": 0,
            "audit_records": 0,
            "projection_states": 0,
            "graph_schemas": 0,
        }
        if control_plane_manifest.is_file():
            restored_control_plane = self._restore_control_plane_snapshot(
                project_id,
                _json_load(control_plane_manifest.read_text(encoding="utf-8"), {}),
            )
        restored = {
            "project": project.to_dict(),
            "source_project_id": source_project.get("project_id"),
            "package_sha256": verification["sha256"],
            "restored_file_count": len(verification["manifest"].get("files") or []),
            "restored_control_plane": restored_control_plane,
        }
        self.append_audit(
            project_id=project_id,
            object_type="project",
            object_id=project_id,
            action="restore_package",
            actor=actor,
            reason="Project restored from verified package",
            change_summary=restored,
            correlation_id=f"project-restore-{uuid4().hex}",
            result="success",
        )
        return restored

    def _ensure_builtin_providers(self, project_id: str) -> None:
        builtins = (
            {
                "provider_id": "native-parser",
                "capability": "document_parsing",
                "provider_type": "local",
                "model": "native",
                "version": "1",
                "health_status": "ready",
                "capabilities": {"formats": ["pdf", "docx", "txt", "image"]},
            },
            {
                "provider_id": "local-ocr",
                "capability": "ocr",
                "provider_type": "local",
                "model": "unconfigured",
                "version": "",
                "health_status": "disabled",
                "enabled": False,
                "capabilities": {"page_level_retry": True},
            },
            {
                "provider_id": "hashing-embedding",
                "capability": "embedding",
                "provider_type": "local",
                "model": "hashing-384",
                "version": "1",
                "health_status": "degraded",
                "capabilities": {"test_only": True, "dimension": 384},
            },
            {
                "provider_id": "rules-graph",
                "capability": "graph_extraction",
                "provider_type": "local",
                "model": "auditable-rules",
                "version": "1",
                "health_status": "ready",
                "capabilities": {
                    "backends": ["rules"],
                    "deterministic": True,
                    "production_automation": False,
                },
            },
            {
                "provider_id": "local-answer",
                "capability": "answer_generation",
                "provider_type": "local",
                "model": "unconfigured",
                "version": "",
                "health_status": "disabled",
                "enabled": False,
                "capabilities": {"evidence_only_fallback": True},
            },
        )
        for provider in builtins:
            try:
                self.get_provider(project_id, str(provider["provider_id"]))
            except ProjectWorkspaceError as exc:
                if exc.code != "provider_not_found":
                    raise
                self.upsert_provider(
                    project_id=project_id,
                    actor="system",
                    timeout_seconds=120,
                    cost_class="local",
                    data_policy={"sends_raw_text_external": False},
                    configuration={},
                    **provider,
                )

    def _ensure_builtin_graph_schemas(self, project_id: str) -> None:
        base = GraphDomainSchema().to_dict()
        builtins = (
            (
                "gas_turbine_fmea",
                "1.0.0",
                {
                    **base,
                    "domain": "gas_turbine",
                    "description": "燃气轮机设备、部件、故障、原因、影响、检测和措施受约束 Schema。",
                },
            ),
            (
                "electric_motor_fmea",
                "1.0.0",
                {
                    **base,
                    "domain": "electric_motor",
                    "description": "电动机设备与轴承、绕组、转子、绝缘等故障链 Schema。需要独立金标准验收。",
                    "entity_aliases": {
                        **dict(base.get("entity_aliases") or {}),
                        "电动机": "电机",
                        "motor bearing": "轴承",
                        "stator winding": "定子绕组",
                    },
                },
            ),
        )
        for schema_id, version, definition in builtins:
            try:
                self.get_graph_schema(
                    project_id,
                    schema_id,
                    version=version,
                    approved_only=False,
                )
            except ProjectWorkspaceError as exc:
                if exc.code != "graph_schema_not_found":
                    raise
                self.register_graph_schema(
                    project_id=project_id,
                    schema_id=schema_id,
                    version=version,
                    definition=definition,
                    actor="system",
                    status="approved",
                )

    def _ensure_builtin_fmea_templates(self, project_id: str) -> None:
        template_dir = Path(__file__).resolve().parents[1] / "configs" / "fmea"
        for path in sorted(template_dir.glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            template_id = str(payload.get("template") or "")
            version = str(payload.get("version") or "")
            if not template_id or not version:
                continue
            try:
                self.get_fmea_template(
                    project_id,
                    template_id,
                    version=version,
                    approved_only=False,
                )
            except ProjectWorkspaceError as exc:
                if exc.code != "fmea_template_not_found":
                    raise
                self.register_fmea_template(
                    project_id=project_id,
                    template_id=template_id,
                    version=version,
                    definition=payload,
                    actor="system",
                    status="approved",
                )

    def _create_workspace(self, project: Project) -> None:
        workspace = (self.root_dir / project.project_id).resolve()
        workspace.relative_to(self.root_dir)
        for relative in PROJECT_DIRECTORIES:
            (workspace / relative).mkdir(parents=True, exist_ok=True)
        self._write_project_manifest(project)

    def _write_project_manifest(self, project: Project) -> None:
        manifest_path = self.project_dir(project.project_id) / "manifests" / "project.json"
        payload = project.to_dict()
        payload["workspace_layout"] = list(PROJECT_DIRECTORIES)
        payload["manifest_hash"] = hashlib.sha256(_json_dump(payload).encode("utf-8")).hexdigest()
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_provider_manifest(self, project_id: str) -> None:
        manifest_path = self.project_dir(project_id) / "manifests" / "providers.json"
        payload = _redact_secrets(self.list_providers(project_id=project_id))
        payload["manifest_hash"] = hashlib.sha256(_json_dump(payload).encode("utf-8")).hexdigest()
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_graph_schema_manifest(self, project_id: str) -> None:
        manifest_path = self.project_dir(project_id) / "manifests" / "graph-schemas.json"
        payload = self.list_graph_schemas(project_id=project_id)
        payload["manifest_hash"] = hashlib.sha256(_json_dump(payload).encode("utf-8")).hexdigest()
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_fmea_template_manifest(self, project_id: str) -> None:
        manifest_path = self.project_dir(project_id) / "manifests" / "fmea-templates.json"
        payload = self.list_fmea_templates(project_id=project_id)
        payload["manifest_hash"] = hashlib.sha256(_json_dump(payload).encode("utf-8")).hexdigest()
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_control_plane_manifest(self, project_id: str) -> None:
        """Persist a project-scoped, secret-free snapshot of the global control plane."""

        project = self.get_project(project_id)
        with self._connect() as connection:
            task_rows = connection.execute(
                "SELECT * FROM delivery_tasks WHERE project_id = ? ORDER BY created_at, task_id",
                (project_id,),
            ).fetchall()
            comment_rows = connection.execute(
                "SELECT * FROM task_comments WHERE project_id = ? ORDER BY comment_id",
                (project_id,),
            ).fetchall()
            audit_rows = connection.execute(
                "SELECT * FROM audit_records WHERE project_id = ? ORDER BY audit_id",
                (project_id,),
            ).fetchall()
            projection_rows = connection.execute(
                "SELECT * FROM projection_states WHERE project_id = ? ORDER BY projection_name",
                (project_id,),
            ).fetchall()
            graph_schema_rows = connection.execute(
                """
                SELECT * FROM graph_schema_versions
                WHERE project_id = ? ORDER BY schema_id, created_at
                """,
                (project_id,),
            ).fetchall()
            fmea_template_rows = connection.execute(
                """
                SELECT * FROM fmea_template_versions
                WHERE project_id = ? ORDER BY template_id, created_at
                """,
                (project_id,),
            ).fetchall()
        audit_records = [
            {
                **{key: row[key] for key in row.keys() if key != "change_summary_json"},  # noqa: SIM118
                "change_summary": _json_load(row["change_summary_json"], {}),
            }
            for row in audit_rows
        ]
        projection_states = [
            {
                **{key: row[key] for key in row.keys() if key != "details_json"},  # noqa: SIM118
                "details": _json_load(row["details_json"], {}),
            }
            for row in projection_rows
        ]
        payload = _redact_secrets(
            {
                "format": "powerrag-control-plane-v1",
                "project": project.to_dict(),
                "created_at": _utc_now(),
                "tasks": [_task_from_row(row).to_dict() for row in task_rows],
                "task_comments": [dict(row) for row in comment_rows],
                "audit_records": audit_records,
                "projection_states": projection_states,
                "graph_schemas": [_graph_schema_from_row(row) for row in graph_schema_rows],
                "fmea_templates": [_fmea_template_from_row(row) for row in fmea_template_rows],
                "providers": self.list_providers(project_id=project_id)["items"],
            }
        )
        payload["manifest_hash"] = hashlib.sha256(_json_dump(payload).encode("utf-8")).hexdigest()
        manifest_path = self.project_dir(project_id) / "manifests" / "control-plane.json"
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _restore_control_plane_snapshot(  # noqa: C901
        self,
        project_id: str,
        snapshot: Mapping[str, Any],
    ) -> dict[str, int]:
        """Restore immutable task/audit history and live projection metadata under a new project id."""

        if snapshot.get("format") != "powerrag-control-plane-v1":
            raise ProjectWorkspaceError("Control-plane manifest is invalid", code="invalid_package")
        source_project_id = str(snapshot.get("project", {}).get("project_id") or "")
        task_id_map: dict[str, str] = {}
        now = _utc_now()
        tasks = list(snapshot.get("tasks") or [])
        comments = list(snapshot.get("task_comments") or [])
        audits = list(snapshot.get("audit_records") or [])
        projections = list(snapshot.get("projection_states") or [])
        graph_schemas = list(snapshot.get("graph_schemas") or [])
        fmea_templates = list(snapshot.get("fmea_templates") or [])
        with self._connect() as connection:
            for item in tasks:
                old_task_id = str(item.get("task_id") or "")
                if not old_task_id:
                    continue
                new_task_id = f"DT-{uuid4().hex[:18]}"
                task_id_map[old_task_id] = new_task_id
                status = str(item.get("status") or TaskStatus.CANCELLED.value)
                if status in {TaskStatus.QUEUED.value, TaskStatus.RUNNING.value}:
                    status = TaskStatus.CANCELLED.value
                    error_code = "restored_task_not_resumed"
                    error_message = "Imported task history is non-resumable; retry explicitly in the restored project."
                    completed_at = now
                else:
                    error_code = _optional(item.get("error_code"))
                    error_message = _optional(item.get("error_message"))
                    completed_at = _optional(item.get("completed_at"))
                object_id = _optional(item.get("object_id"))
                if str(item.get("object_type") or "") == "project" and object_id == source_project_id:
                    object_id = project_id
                connection.execute(
                    """
                    INSERT INTO delivery_tasks (
                        task_id, project_id, task_type, status, stage, progress,
                        severity, object_type, object_id, assigned_to, correlation_id,
                        idempotency_key, retryable, error_code, error_message,
                        payload_json, result_json, created_by, lease_owner,
                        lease_expires_at, heartbeat_at, created_at, started_at,
                        completed_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?)
                    """,
                    (
                        new_task_id,
                        project_id,
                        str(item.get("task_type") or "restored_task"),
                        status,
                        str(item.get("stage") or "restored"),
                        float(item.get("progress") or 0),
                        str(item.get("severity") or "info"),
                        _optional(item.get("object_type")),
                        object_id,
                        _optional(item.get("assigned_to")),
                        str(item.get("correlation_id") or uuid4().hex),
                        1 if bool(item.get("retryable")) else 0,
                        error_code,
                        error_message,
                        _json_dump(_redact_secrets(item.get("payload") or {})),
                        _json_dump(_redact_secrets(item.get("result") or {})),
                        str(item.get("created_by") or "restored-package"),
                        str(item.get("created_at") or now),
                        _optional(item.get("started_at")),
                        completed_at,
                        str(item.get("updated_at") or now),
                    ),
                )
            restored_comments = 0
            for item in comments:
                mapped_task_id = task_id_map.get(str(item.get("task_id") or ""))
                if not mapped_task_id:
                    continue
                connection.execute(
                    """
                    INSERT INTO task_comments (
                        task_id, project_id, actor, message, correlation_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mapped_task_id,
                        project_id,
                        str(item.get("actor") or "restored-package"),
                        str(item.get("message") or ""),
                        str(item.get("correlation_id") or uuid4().hex),
                        str(item.get("created_at") or now),
                    ),
                )
                restored_comments += 1
            restored_audits = 0
            for item in audits:
                object_type = str(item.get("object_type") or "restored_object")
                object_id = str(item.get("object_id") or "unknown")
                if object_type == "delivery_task":
                    object_id = task_id_map.get(object_id, object_id)
                elif object_type == "project" and object_id == source_project_id:
                    object_id = project_id
                connection.execute(
                    """
                    INSERT INTO audit_records (
                        project_id, object_type, object_id, object_version, action,
                        actor, reason, change_summary_json, correlation_id,
                        client_request_id, result, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        object_type,
                        object_id,
                        _optional(item.get("object_version")),
                        str(item.get("action") or "restored_event"),
                        str(item.get("actor") or "restored-package"),
                        str(item.get("reason") or ""),
                        _json_dump(_redact_secrets(item.get("change_summary") or {})),
                        str(item.get("correlation_id") or uuid4().hex),
                        _optional(item.get("client_request_id")),
                        str(item.get("result") or "success"),
                        str(item.get("created_at") or now),
                    ),
                )
                restored_audits += 1
            for item in projections:
                connection.execute(
                    """
                    INSERT INTO projection_states (
                        project_id, projection_name, source_version_id, status,
                        item_count, details_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, projection_name) DO UPDATE SET
                        source_version_id = excluded.source_version_id,
                        status = excluded.status,
                        item_count = excluded.item_count,
                        details_json = excluded.details_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        project_id,
                        str(item.get("projection_name") or "restored_projection"),
                        _optional(item.get("source_version_id")),
                        str(item.get("status") or "not_initialized"),
                        item.get("item_count"),
                        _json_dump(_redact_secrets(item.get("details") or {})),
                        str(item.get("updated_at") or now),
                    ),
                )
            restored_graph_schemas = 0
            for item in graph_schemas:
                schema_id = _catalog_id(item.get("schema_id"), "schema_id")
                version = _required(item.get("version"), "version")
                definition = dict(item.get("definition") or {})
                content_hash = hashlib.sha256(_json_dump(definition).encode("utf-8")).hexdigest()
                existing = connection.execute(
                    """
                    SELECT content_hash FROM graph_schema_versions
                    WHERE project_id = ? AND schema_id = ? AND version = ?
                    """,
                    (project_id, schema_id, version),
                ).fetchone()
                if existing is not None:
                    if str(existing["content_hash"]) != content_hash:
                        raise ProjectWorkspaceError(
                            "Restored graph schema conflicts with an immutable built-in version",
                            code="graph_schema_restore_conflict",
                            details={"schema_id": schema_id, "version": version},
                        )
                    continue
                connection.execute(
                    """
                    INSERT INTO graph_schema_versions (
                        project_id, schema_id, version, status, definition_json,
                        content_hash, created_by, created_at, approved_by, approved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        schema_id,
                        version,
                        str(item.get("status") or "draft"),
                        _json_dump(definition),
                        content_hash,
                        str(item.get("created_by") or "restored-package"),
                        str(item.get("created_at") or now),
                        _optional(item.get("approved_by")),
                        _optional(item.get("approved_at")),
                    ),
                )
                restored_graph_schemas += 1
            restored_fmea_templates = 0
            for item in fmea_templates:
                template_id = _catalog_id(item.get("template_id"), "template_id")
                version = _required(item.get("version"), "version")
                definition = _validate_fmea_template_definition(
                    dict(item.get("definition") or {}),
                    template_id=template_id,
                    version=version,
                )
                content_hash = hashlib.sha256(_json_dump(definition).encode("utf-8")).hexdigest()
                existing = connection.execute(
                    """
                    SELECT content_hash FROM fmea_template_versions
                    WHERE project_id = ? AND template_id = ? AND version = ?
                    """,
                    (project_id, template_id, version),
                ).fetchone()
                if existing is not None:
                    if str(existing["content_hash"]) != content_hash:
                        raise ProjectWorkspaceError(
                            "Restored FMEA template conflicts with an immutable built-in version",
                            code="fmea_template_restore_conflict",
                            details={"template_id": template_id, "version": version},
                        )
                    continue
                connection.execute(
                    """
                    INSERT INTO fmea_template_versions (
                        project_id, template_id, version, status, definition_json,
                        content_hash, created_by, created_at, approved_by, approved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        template_id,
                        version,
                        str(item.get("status") or "draft"),
                        _json_dump(definition),
                        content_hash,
                        str(item.get("created_by") or "restored-package"),
                        str(item.get("created_at") or now),
                        _optional(item.get("approved_by")),
                        _optional(item.get("approved_at")),
                    ),
                )
                restored_fmea_templates += 1
        return {
            "tasks": len(task_id_map),
            "task_comments": restored_comments,
            "audit_records": restored_audits,
            "projection_states": len(projections),
            "graph_schemas": restored_graph_schemas,
            "fmea_templates": restored_fmea_templates,
        }

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _project_from_row(row: sqlite3.Row) -> Project:
    return Project(
        project_id=str(row["project_id"]),
        name=str(row["name"]),
        description=str(row["description"]),
        domain=str(row["domain"]),
        status=str(row["status"]),
        configuration=_json_load(row["configuration_json"], {}),
        data_policy=_json_load(row["data_policy_json"], {}),
        acceptance=_json_load(row["acceptance_json"], {}),
        created_by=str(row["created_by"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _provider_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "project_id": str(row["project_id"]),
        "provider_id": str(row["provider_id"]),
        "capability": str(row["capability"]),
        "provider_type": str(row["provider_type"]),
        "model": str(row["model"]),
        "version": str(row["version"]),
        "timeout_seconds": float(row["timeout_seconds"]),
        "cost_class": str(row["cost_class"]),
        "data_policy": _json_load(row["data_policy_json"], {}),
        "capabilities": _json_load(row["capabilities_json"], {}),
        "health_status": str(row["health_status"]),
        "enabled": bool(row["enabled"]),
        "configuration": _json_load(row["configuration_json"], {}),
        "updated_by": str(row["updated_by"]),
        "updated_at": str(row["updated_at"]),
    }


def _graph_schema_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "project_id": str(row["project_id"]),
        "schema_id": str(row["schema_id"]),
        "version": str(row["version"]),
        "status": str(row["status"]),
        "definition": _json_load(row["definition_json"], {}),
        "content_hash": str(row["content_hash"]),
        "created_by": str(row["created_by"]),
        "created_at": str(row["created_at"]),
        "approved_by": _optional(row["approved_by"]),
        "approved_at": _optional(row["approved_at"]),
    }


def _fmea_template_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "project_id": str(row["project_id"]),
        "template_id": str(row["template_id"]),
        "version": str(row["version"]),
        "status": str(row["status"]),
        "definition": _json_load(row["definition_json"], {}),
        "content_hash": str(row["content_hash"]),
        "created_by": str(row["created_by"]),
        "created_at": str(row["created_at"]),
        "approved_by": _optional(row["approved_by"]),
        "approved_at": _optional(row["approved_at"]),
    }


def _validate_fmea_template_definition(
    definition: Mapping[str, Any],
    *,
    template_id: str,
    version: str,
) -> dict[str, Any]:
    payload = dict(definition)
    declared_id = str(payload.get("template") or template_id).strip()
    declared_version = str(payload.get("version") or version).strip()
    if declared_id != template_id or declared_version != version:
        raise ProjectWorkspaceError(
            "FMEA template ID/version must match the catalog coordinates",
            code="invalid_fmea_template",
            details={
                "template_id": template_id,
                "version": version,
                "declared_template_id": declared_id,
                "declared_version": declared_version,
            },
        )
    raw_fields = payload.get("fields") or []
    field_names = tuple(
        str(item.get("name") or "").strip()
        for item in raw_fields
        if isinstance(item, Mapping)
    )
    if field_names != FMEA_FIELDS:
        raise ProjectWorkspaceError(
            "FMEA template fields must exactly match the governed FMEA contract",
            code="invalid_fmea_template_fields",
            details={"expected": list(FMEA_FIELDS), "actual": list(field_names)},
        )
    report_layout = dict(payload.get("report_layout") or {})
    orientation = str(report_layout.get("orientation") or "landscape").lower()
    if orientation not in {"landscape", "portrait"}:
        raise ProjectWorkspaceError(
            "FMEA report orientation must be landscape or portrait",
            code="invalid_fmea_report_template",
            details={"orientation": orientation},
        )
    report_layout["orientation"] = orientation
    payload.update(
        {
            "template": template_id,
            "version": version,
            "status": str(payload.get("status") or "draft").lower(),
            "report_layout": report_layout,
        }
    )
    return payload


def _task_from_row(row: sqlite3.Row) -> DeliveryTask:
    started_at = _optional(row["started_at"]) or str(row["created_at"])
    completed_at = _optional(row["completed_at"])
    return DeliveryTask(
        task_id=str(row["task_id"]),
        project_id=str(row["project_id"]),
        task_type=str(row["task_type"]),
        status=TaskStatus(str(row["status"])),
        stage=str(row["stage"]),
        created_by=str(row["created_by"]),
        progress=float(row["progress"]),
        severity=str(row["severity"]),
        object_type=_optional(row["object_type"]),
        object_id=_optional(row["object_id"]),
        assigned_to=_optional(row["assigned_to"]),
        correlation_id=str(row["correlation_id"]),
        idempotency_key=_optional(row["idempotency_key"]),
        retryable=bool(row["retryable"]),
        error_code=_optional(row["error_code"]),
        error_message=_optional(row["error_message"]),
        payload=_json_load(row["payload_json"], {}),
        result=_json_load(row["result_json"], {}),
        lease_owner=_optional(row["lease_owner"]),
        lease_expires_at=_optional(row["lease_expires_at"]),
        heartbeat_at=_optional(row["heartbeat_at"]),
        duration_ms=_iso_duration_ms(started_at, completed_at) if completed_at else None,
        created_at=str(row["created_at"]),
        started_at=_optional(row["started_at"]),
        completed_at=completed_at,
        updated_at=str(row["updated_at"]),
    )


def _required(value: Any, name: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{name} must not be empty")
    return clean


def _optional(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def _project_id(value: Any) -> str:
    clean = _required(value, "project_id").lower()
    if clean == "default":
        return clean
    if not PROJECT_ID_RE.fullmatch(clean):
        raise ProjectWorkspaceError(
            "project_id must be 2-63 lowercase letters, digits, underscores, or hyphens",
            code="invalid_project_id",
        )
    return clean


def _catalog_id(value: Any, name: str) -> str:
    clean = _required(value, name).lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,99}", clean):
        raise ProjectWorkspaceError(
            f"{name} must be 2-100 lowercase letters, digits, underscores, or hyphens",
            code=f"invalid_{name}",
        )
    return clean


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def _redact_secrets(value: Any) -> Any:
    secret_tokens = ("secret", "password", "api_key", "apikey", "access_token", "refresh_token")
    if isinstance(value, Mapping):
        return {
            str(key): _redact_secrets(item)
            for key, item in value.items()
            if not any(token in str(key).casefold() for token in secret_tokens)
        }
    if isinstance(value, list | tuple):
        return [_redact_secrets(item) for item in value]
    return value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _iso_duration_ms(started_at: str, completed_at: str) -> float | None:
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round(max(0.0, (completed - started).total_seconds() * 1000), 3)


def _free_bytes(path: Path) -> int:
    import shutil

    return int(shutil.disk_usage(path).free)


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(item) for item in values)
    index = max(0, min(len(ordered) - 1, int(quantile * len(ordered) + 0.999999) - 1))
    return round(ordered[index], 3)


def _rotate_log(path: Path, *, max_bytes: int = 10 * 1024 * 1024, backups: int = 5) -> None:
    if not path.is_file() or path.stat().st_size < max_bytes:
        return
    oldest = path.with_name(f"{path.name}.{backups}")
    oldest.unlink(missing_ok=True)
    for index in range(backups - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        if source.is_file():
            source.replace(path.with_name(f"{path.name}.{index + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))


def _safe_archive_path(value: Any) -> str:
    clean = str(value or "").replace("\\", "/").strip("/")
    if _unsafe_archive_path(clean):
        raise ProjectWorkspaceError(f"Unsafe project package path: {value}", code="invalid_package_path")
    return clean


def _unsafe_archive_path(value: str) -> bool:
    path = str(value or "").replace("\\", "/")
    parts = [part for part in path.split("/") if part]
    return (
        not path
        or path.startswith("/")
        or bool(re.match(r"^[A-Za-z]:", path))
        or any(part in {".", ".."} for part in parts)
    )
