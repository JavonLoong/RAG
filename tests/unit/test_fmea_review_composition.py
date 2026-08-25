"""Focused tests for concrete workspace review runtime composition."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from chroma_rag_poc.workspace_registry import WorkspaceConfig  # noqa: E402

from core_domain.query_contracts import QueryMode  # noqa: E402
from fmea_infrastructure.composition import build_workspace_review_runtime  # noqa: E402
from structured_output_infrastructure import FileTemplateRegistry  # noqa: E402
from tests.fmea_review_fixtures import FakeReviewSuggestionGenerator, InlineReviewExecutor  # noqa: E402


def make_workspace_config(
    *,
    allowed_root: Path,
    fmea_db_path: Path | None,
    fmea_template_registry_path: Path | None,
    graph_db_path: Path | None,
) -> WorkspaceConfig:
    return WorkspaceConfig(
        workspace_id="ws-1",
        chroma_persist_dir=allowed_root / "chroma",
        chroma_collection="workspace",
        graph_db_path=graph_db_path,
        fmea_db_path=fmea_db_path,
        fmea_template_registry_path=fmea_template_registry_path,
        supported_modes=frozenset({QueryMode.VECTOR}),
        default_mode=QueryMode.VECTOR,
    )


def test_workspace_paths_are_contained_and_separate_from_graph_db(
    tmp_path: Path,
    valid_review_suggestion_draft: Any,
    fixture_review_model_manifest: Any,
) -> None:
    workspace = make_workspace_config(
        allowed_root=tmp_path,
        fmea_db_path=tmp_path / "fmea/fmea.sqlite3",
        fmea_template_registry_path=tmp_path / "fmea/templates",
        graph_db_path=tmp_path / "graph/graph.sqlite3",
    )
    runtime = build_workspace_review_runtime(
        workspace,
        generator=FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        executor=InlineReviewExecutor(),
    )

    assert runtime.repository.database_path == (tmp_path / "fmea/fmea.sqlite3").resolve()
    assert runtime.repository.database_path != workspace.graph_db_path
    assert runtime.template_registry_root == (tmp_path / "fmea/templates").resolve()


@pytest.mark.parametrize("collision", ["db_existing_directory", "registry_existing_file", "db_ancestor", "registry_ancestor", "graph_equal"])
def test_workspace_composition_rejects_path_security_matrix(
    tmp_path: Path,
    valid_review_suggestion_draft: Any,
    fixture_review_model_manifest: Any,
    collision: str,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    database_path = root / "fmea" / "fmea.sqlite3"
    template_registry_path = root / "fmea" / "templates"
    graph_db_path = root / "graph" / "graph.sqlite3"

    if collision == "db_existing_directory":
        database_path.mkdir(parents=True)
    elif collision == "registry_existing_file":
        template_registry_path.parent.mkdir(parents=True)
        template_registry_path.write_text("collision", encoding="utf-8")
    elif collision == "db_ancestor":
        database_path = root / "fmea"
        template_registry_path = root / "fmea" / "templates"
    elif collision == "registry_ancestor":
        database_path = root / "fmea" / "fmea.sqlite3"
        template_registry_path = root / "fmea"
    elif collision == "graph_equal":
        database_path = graph_db_path

    workspace = make_workspace_config(
        allowed_root=root,
        fmea_db_path=database_path,
        fmea_template_registry_path=template_registry_path,
        graph_db_path=graph_db_path,
    )

    with pytest.raises(ValueError):
        build_workspace_review_runtime(
            workspace,
            generator=FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
            executor=InlineReviewExecutor(),
        )

    if collision in {"db_ancestor", "registry_ancestor"}:
        assert not (root / "fmea").exists()


def test_default_workspace_runtime_is_idempotent_without_deepseek_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    workspace = make_workspace_config(
        allowed_root=tmp_path,
        fmea_db_path=None,
        fmea_template_registry_path=None,
        graph_db_path=tmp_path / "graph/graph.sqlite3",
    )
    runtimes = []
    try:
        runtimes.append(build_workspace_review_runtime(workspace))
        runtimes.append(build_workspace_review_runtime(workspace))
        expected_db = (tmp_path / "fmea/fmea.sqlite3").resolve()
        expected_registry = (tmp_path / "fmea/template_registry").resolve()
        assert all(runtime.repository.database_path == expected_db for runtime in runtimes)
        assert all(runtime.template_registry_root == expected_registry for runtime in runtimes)
        assert expected_db.is_file()
        assert FileTemplateRegistry(expected_registry).get("fmea-row-review", "1.0.0").metadata.template_id == "fmea-row-review"
    finally:
        for runtime in runtimes:
            runtime.executor.close()
