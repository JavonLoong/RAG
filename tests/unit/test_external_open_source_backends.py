from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from pathlib import Path

from integrations.external_backends import (
    EXTERNAL_BACKENDS,
    ExternalBackendUnavailable,
    backend_status,
    get_backend,
)


def test_external_backend_registry_covers_top_open_source_projects() -> None:
    expected = {
        "ragflow",
        "docling",
        "unstructured",
        "haystack",
        "llamaindex",
        "lightrag",
        "ragas",
        "deepeval",
    }

    assert expected.issubset(EXTERNAL_BACKENDS)
    assert EXTERNAL_BACKENDS["docling"].install_command == "pip install docling"
    assert EXTERNAL_BACKENDS["haystack"].license == "Apache-2.0"
    assert EXTERNAL_BACKENDS["lightrag"].package_name == "lightrag-hku"


def test_backend_status_reports_install_command_when_package_is_missing() -> None:
    status = backend_status("definitely-missing-backend")

    assert status["available"] is False
    assert "Unknown external backend" in status["error"]

    status = backend_status("docling", import_name="definitely_missing_docling_module")
    assert status["available"] is False
    assert status["install_command"] == "pip install docling"


def test_docling_adapter_uses_real_document_converter_when_available(monkeypatch) -> None:
    calls: list[str] = []

    class FakeDocument:
        def export_to_markdown(self) -> str:
            return "# Parsed by Docling\n\nTable and layout aware text."

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, source: str) -> FakeResult:
            calls.append(source)
            return FakeResult()

    fake_docling = ModuleType("docling")
    fake_converter_module = ModuleType("docling.document_converter")
    fake_converter_module.DocumentConverter = FakeConverter
    monkeypatch.setitem(sys.modules, "docling", fake_docling)
    monkeypatch.setitem(sys.modules, "docling.document_converter", fake_converter_module)

    backend = get_backend("docling")
    result = backend.parse_file("manual.pdf")

    assert calls == ["manual.pdf"]
    assert result["backend"] == "docling"
    assert "Parsed by Docling" in result["text"]


def test_unstructured_adapter_uses_partition_auto_when_available(monkeypatch) -> None:
    fake_unstructured = ModuleType("unstructured")
    fake_partition = ModuleType("unstructured.partition")
    fake_auto = ModuleType("unstructured.partition.auto")

    def partition(filename: str):
        return [
            SimpleNamespace(text="Title", category="Title", metadata=SimpleNamespace(to_dict=lambda: {"page_number": 1})),
            SimpleNamespace(text="Body text", category="NarrativeText", metadata=SimpleNamespace(to_dict=lambda: {})),
        ]

    fake_auto.partition = partition
    monkeypatch.setitem(sys.modules, "unstructured", fake_unstructured)
    monkeypatch.setitem(sys.modules, "unstructured.partition", fake_partition)
    monkeypatch.setitem(sys.modules, "unstructured.partition.auto", fake_auto)

    backend = get_backend("unstructured")
    result = backend.parse_file("manual.pdf")

    assert result["backend"] == "unstructured"
    assert result["elements"][0]["category"] == "Title"
    assert "Body text" in result["text"]


def test_missing_backend_raises_actionable_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "docling", None)
    backend = get_backend("docling", import_name="definitely_missing_docling_module")

    try:
        backend.parse_file("manual.pdf")
    except ExternalBackendUnavailable as exc:
        assert "pip install docling" in str(exc)
    else:
        raise AssertionError("Expected ExternalBackendUnavailable")


def test_project_declares_external_backend_extras_and_manifest() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    manifest = Path("configs/external_open_source_backends.json")

    assert "[project.optional-dependencies]" in pyproject
    for package in ("docling", "unstructured", "haystack-ai", "llama-index", "lightrag-hku", "ragas", "deepeval"):
        assert package in pyproject
    assert manifest.exists()
    install_script = Path("scripts/install_external_rag_backends.ps1")
    assert install_script.exists()
    manifest_text = manifest.read_text(encoding="utf-8")
    for key in EXTERNAL_BACKENDS:
        assert f'"{key}"' in manifest_text
    script_text = install_script.read_text(encoding="utf-8")
    assert "external-all" in script_text
    assert "git clone --depth 1" in script_text
