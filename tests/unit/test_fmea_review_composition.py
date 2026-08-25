"""Focused tests for concrete workspace review runtime composition."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PACKAGE_SRC = Path(__file__).resolve().parents[2] / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from chroma_rag_poc.workspace_registry import WorkspaceConfig  # noqa: E402

from core_domain.query_contracts import QueryMode  # noqa: E402
from fmea_infrastructure.composition import build_workspace_review_runtime  # noqa: E402
from tests.fmea_review_fixtures import FakeReviewSuggestionGenerator, InlineReviewExecutor  # noqa: E402


def make_workspace_config(
    *,
    allowed_root: Path,
    fmea_db_path: Path,
    fmea_template_registry_path: Path,
    graph_db_path: Path,
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
