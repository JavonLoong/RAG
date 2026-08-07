"""Behavioral tests for the safe workspace registry boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from chroma_rag_poc.workspace_registry import (  # noqa: E402
    WorkspaceConfigError,
    WorkspaceNotFoundError,
    WorkspaceRegistry,
)

from core_domain.query_contracts import QueryMode  # noqa: E402


def _write_registry(tmp_path: Path, workspace: dict | None = None) -> tuple[Path, Path]:
    config_dir = tmp_path / "config"
    allowed_root = tmp_path / "runtime"
    config_dir.mkdir()
    registry_path = config_dir / "workspaces.json"
    registry_path.write_text(
        json.dumps({
            "allowed_root": "../runtime",
            "workspaces": {
                "power-equipment": workspace
                or {
                    "chroma_persist_dir": "../runtime/chroma",
                    "chroma_collection": "power_equipment",
                    "graph_db_path": "../runtime/graph/graph.sqlite3",
                    "supported_modes": ["vector", "local", "global", "hybrid"],
                    "default_mode": "auto",
                }
            },
        }),
        encoding="utf-8",
    )
    return registry_path, allowed_root


def test_registry_returns_resolved_power_equipment_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path, allowed_root = _write_registry(tmp_path)
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))

    workspace = WorkspaceRegistry.from_env().get("power-equipment")

    assert workspace.workspace_id == "power-equipment"
    assert workspace.chroma_collection == "power_equipment"
    assert workspace.chroma_persist_dir == (allowed_root / "chroma").resolve()
    assert workspace.graph_db_path == (allowed_root / "graph" / "graph.sqlite3").resolve()
    assert workspace.supported_modes == frozenset({
        QueryMode.VECTOR,
        QueryMode.LOCAL,
        QueryMode.GLOBAL,
        QueryMode.HYBRID,
    })
    assert workspace.default_mode is QueryMode.AUTO


def test_registry_rejects_unknown_workspace_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry_path, _ = _write_registry(tmp_path)
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))

    with pytest.raises(WorkspaceNotFoundError) as error:
        WorkspaceRegistry.from_env().get("missing")

    assert error.value.workspace_id == "missing"
    assert str(error.value) == "Workspace 'missing' is not configured."


def test_registry_resolves_relative_paths_from_registry_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path, _ = _write_registry(tmp_path)
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))

    workspace = WorkspaceRegistry.from_env().get("power-equipment")

    assert workspace.chroma_persist_dir == (registry_path.parent / "../runtime/chroma").resolve()
    assert workspace.graph_db_path == (registry_path.parent / "../runtime/graph/graph.sqlite3").resolve()


def test_registry_rejects_paths_outside_allowed_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry_path, _ = _write_registry(
        tmp_path,
        workspace={
            "chroma_persist_dir": "../outside",
            "chroma_collection": "power_equipment",
            "graph_db_path": "../runtime/graph/graph.sqlite3",
            "supported_modes": ["vector"],
            "default_mode": "vector",
        },
    )
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))

    with pytest.raises(WorkspaceConfigError, match="allowed_root"):
        WorkspaceRegistry.from_env()


@pytest.mark.parametrize("secret_key", ["api_key", "token", "secret"])
def test_registry_rejects_secret_like_keys_recursively(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, secret_key: str
) -> None:
    registry_path, _ = _write_registry(tmp_path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["workspaces"]["power-equipment"]["metadata"] = {"nested": [{secret_key: "must-not-load"}]}
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))

    with pytest.raises(WorkspaceConfigError, match=r"(?i)secret"):
        WorkspaceRegistry.from_env()


def test_workspace_config_is_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry_path, _ = _write_registry(tmp_path)
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))
    workspace = WorkspaceRegistry.from_env().get("power-equipment")

    with pytest.raises(ValidationError):
        workspace.default_mode = QueryMode.VECTOR


def test_registry_allows_workspace_without_graph_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry_path, _ = _write_registry(
        tmp_path,
        workspace={
            "chroma_persist_dir": "../runtime/chroma",
            "chroma_collection": "power_equipment",
            "graph_db_path": None,
            "supported_modes": ["vector"],
            "default_mode": "vector",
        },
    )
    monkeypatch.setenv("RAG_WORKSPACE_CONFIG", str(registry_path))

    assert WorkspaceRegistry.from_env().get("power-equipment").graph_db_path is None
