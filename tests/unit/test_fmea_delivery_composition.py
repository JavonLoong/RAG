"""Focused tests for the server-owned delivery composition boundary."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fmea_application.review_errors import ReviewError
from fmea_infrastructure.composition import (
    _RepositoryTemplateEvidenceProvider,
    build_default_workspace_delivery_runtime,
)


def _workspace(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        workspace_id="ws-1",
        chroma_persist_dir=tmp_path / "chroma",
        fmea_db_path=tmp_path / "fmea" / "fmea.sqlite3",
        fmea_template_registry_path=tmp_path / "fmea" / "templates",
        graph_db_path=tmp_path / "graph.sqlite3",
    )


def test_default_delivery_composition_registers_all_export_formats(tmp_path: Path) -> None:
    runtime = build_default_workspace_delivery_runtime(_workspace(tmp_path), migration_adapters=())

    try:
        assert tuple(runtime.export_runtime.exporters) == ("json", "xlsx", "docx")
        assert runtime.export_service is runtime.export_runtime.service
    finally:
        runtime.close()


class _InvalidEvidenceRepository:
    def get_evidence_pack(self, pack_id: str, workspace_id: str) -> object:
        del pack_id, workspace_id
        return object()


def test_template_evidence_provider_rejects_invalid_provider_result() -> None:
    provider = _RepositoryTemplateEvidenceProvider(_InvalidEvidenceRepository())

    with pytest.raises(ReviewError, match="template mapping EvidencePack") as exc_info:
        provider.load_pack("ws-1", "pack-1")
    assert exc_info.value.code == "FMEA_EVIDENCE_INVALID"
