"""Safe, model-free loading of logical RAG workspace configuration."""

# The registry errors intentionally include field context for operator diagnosis.
# ruff: noqa: TRY003

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from core_domain.query_contracts import QueryMode


class WorkspaceConfigError(RuntimeError):
    """Raised when the workspace registry cannot be loaded safely."""


class WorkspaceNotFoundError(LookupError):
    """Raised when a requested workspace ID is not configured."""

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        super().__init__(f"Workspace '{workspace_id}' is not configured.")


class WorkspaceConfig(BaseModel):
    """Immutable runtime paths and query capabilities for one workspace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str
    chroma_persist_dir: Path
    chroma_collection: str
    graph_db_path: Path | None = None
    supported_modes: frozenset[QueryMode]
    default_mode: QueryMode


_SECRET_MARKERS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "private_key",
    "access_key",
)
_KEY_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")


def _reject_secret_like_keys(value: Any, *, location: str = "registry") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise WorkspaceConfigError(f"Registry key at {location} must be a string.")
            normalized_key = _KEY_SEPARATOR_RE.sub("_", key.casefold()).strip("_")
            if any(marker in normalized_key for marker in _SECRET_MARKERS):
                raise WorkspaceConfigError(f"Secret-like key '{key}' is not allowed in the workspace registry.")
            _reject_secret_like_keys(child, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_like_keys(child, location=f"{location}[{index}]")


def _resolve_configured_path(raw_path: Any, *, registry_dir: Path, field_name: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise WorkspaceConfigError(f"{field_name} must be a non-empty path string.")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = registry_dir / path
    return path.resolve()


def _ensure_contained(path: Path, *, allowed_root: Path, field_name: str) -> None:
    try:
        path.relative_to(allowed_root)
    except ValueError as exc:
        raise WorkspaceConfigError(f"{field_name} must be contained by allowed_root.") from exc


class WorkspaceRegistry:
    """Load workspace metadata from the JSON file named by ``RAG_WORKSPACE_CONFIG``."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        configured_path = config_path if config_path is not None else os.environ.get("RAG_WORKSPACE_CONFIG")
        if not configured_path:
            raise WorkspaceConfigError("RAG_WORKSPACE_CONFIG is not set.")

        self._config_path = Path(configured_path).expanduser().resolve()
        payload = self._read_payload()
        _reject_secret_like_keys(payload)
        self._workspaces = self._build_workspaces(payload)

    @classmethod
    def from_env(cls) -> WorkspaceRegistry:
        """Construct a registry using ``RAG_WORKSPACE_CONFIG``."""

        return cls()

    @classmethod
    def from_file(cls, config_path: str | Path) -> WorkspaceRegistry:
        """Construct a registry from an explicit JSON file path."""

        return cls(config_path)

    def get(self, workspace_id: str) -> WorkspaceConfig:
        """Return the configured workspace or raise a stable lookup error."""

        try:
            return self._workspaces[workspace_id]
        except KeyError as exc:
            raise WorkspaceNotFoundError(workspace_id) from exc

    def _read_payload(self) -> dict[str, Any]:
        try:
            with self._config_path.open(encoding="utf-8") as config_file:
                payload = json.load(config_file)
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceConfigError(f"Unable to load workspace registry '{self._config_path}'.") from exc
        if not isinstance(payload, dict):
            raise WorkspaceConfigError("Workspace registry root must be a JSON object.")
        return payload

    def _build_workspaces(self, payload: dict[str, Any]) -> dict[str, WorkspaceConfig]:
        registry_dir = self._config_path.parent
        allowed_root = _resolve_configured_path(
            payload.get("allowed_root"),
            registry_dir=registry_dir,
            field_name="allowed_root",
        )
        raw_workspaces = payload.get("workspaces")
        if not isinstance(raw_workspaces, dict):
            raise WorkspaceConfigError("workspaces must be a JSON object.")

        workspaces: dict[str, WorkspaceConfig] = {}
        for workspace_id, raw_workspace in raw_workspaces.items():
            if not isinstance(workspace_id, str) or not workspace_id:
                raise WorkspaceConfigError("Workspace IDs must be non-empty strings.")
            if not isinstance(raw_workspace, dict):
                raise WorkspaceConfigError(f"Workspace '{workspace_id}' must be a JSON object.")

            chroma_persist_dir = _resolve_configured_path(
                raw_workspace.get("chroma_persist_dir"),
                registry_dir=registry_dir,
                field_name=f"{workspace_id}.chroma_persist_dir",
            )
            _ensure_contained(
                chroma_persist_dir,
                allowed_root=allowed_root,
                field_name=f"{workspace_id}.chroma_persist_dir",
            )

            raw_graph_db_path = raw_workspace.get("graph_db_path")
            graph_db_path = None
            if raw_graph_db_path is not None:
                graph_db_path = _resolve_configured_path(
                    raw_graph_db_path,
                    registry_dir=registry_dir,
                    field_name=f"{workspace_id}.graph_db_path",
                )
                _ensure_contained(
                    graph_db_path,
                    allowed_root=allowed_root,
                    field_name=f"{workspace_id}.graph_db_path",
                )

            try:
                workspaces[workspace_id] = WorkspaceConfig(
                    workspace_id=workspace_id,
                    chroma_persist_dir=chroma_persist_dir,
                    chroma_collection=raw_workspace.get("chroma_collection"),
                    graph_db_path=graph_db_path,
                    supported_modes=raw_workspace.get("supported_modes"),
                    default_mode=raw_workspace.get("default_mode"),
                )
            except ValidationError as exc:
                raise WorkspaceConfigError(f"Invalid configuration for workspace '{workspace_id}'.") from exc
        return workspaces


__all__ = [
    "WorkspaceConfig",
    "WorkspaceConfigError",
    "WorkspaceNotFoundError",
    "WorkspaceRegistry",
]
