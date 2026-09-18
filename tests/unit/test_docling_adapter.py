from __future__ import annotations

import tomllib
from pathlib import Path

from data_pipeline.document_intake import DocumentIntakeOptions, run_document_intake
from data_pipeline.external_document_parsers import load_docling_records


class _FakeDoclingDocument:
    def export_to_markdown(self) -> str:
        return "# Pump Manual\n\nInspect vibration and bearing temperature.\n\n| item | status |\n| --- | --- |\n| pump | ok |"


class _FakeConversionResult:
    document = _FakeDoclingDocument()


class _FakeDocumentConverter:
    def convert(self, source: str) -> _FakeConversionResult:
        assert source.endswith(".pdf")
        return _FakeConversionResult()


def test_docling_adapter_converts_markdown_export_to_source_records() -> None:
    records = load_docling_records(
        b"%PDF-1.4\nfake readable pdf",
        source_name="manual.pdf",
        converter_factory=_FakeDocumentConverter,
    )

    assert len(records) == 1
    assert records[0].source_file == "manual.pdf"
    assert records[0].metadata["parser_backend"] == "docling"
    assert records[0].metadata["external_runtime"] == "docling"
    assert records[0].blocks[0].block_type == "Title"
    assert "Pump Manual" in records[0].text
    assert "pump | ok" in records[0].text


def test_run_document_intake_uses_docling_backend_when_converter_is_available(monkeypatch) -> None:
    import data_pipeline.document_intake as document_intake

    monkeypatch.setattr(
        document_intake,
        "load_docling_records",
        lambda raw_bytes, source_name: load_docling_records(
            raw_bytes,
            source_name=source_name,
            converter_factory=_FakeDocumentConverter,
        ),
    )

    result = run_document_intake(
        "manual.pdf",
        b"%PDF-1.4\nfake readable pdf",
        options=DocumentIntakeOptions(parser_backend="docling"),
    )
    payload = result.to_dict()

    assert result.status == "parsed"
    assert payload["processing_plan"]["parser_backend"] == "docling"
    assert payload["processing_plan"]["runtime"]["name"] == "docling"
    assert payload["processing_plan"]["runtime"]["status"] == "used"
    assert payload["records"][0]["metadata"]["external_runtime"] == "docling"


def test_docling_backend_reports_native_fallback_when_runtime_missing(monkeypatch) -> None:
    import data_pipeline.document_intake as document_intake

    monkeypatch.setattr(
        document_intake,
        "load_docling_records",
        lambda raw_bytes, source_name: (_ for _ in ()).throw(document_intake.ExternalParserUnavailable("missing docling")),
    )

    result = run_document_intake(
        "manual.txt",
        b"Pump Manual\n\nInspect vibration and bearing temperature.",
        options=DocumentIntakeOptions(parser_backend="docling"),
    )
    payload = result.to_dict()

    assert result.status == "parsed"
    assert payload["processing_plan"]["runtime"]["name"] == "docling"
    assert payload["processing_plan"]["runtime"]["status"] == "fallback_to_native"
    assert "missing docling" in payload["processing_plan"]["runtime"]["error"]
    assert "missing docling" in payload["warnings"]


def test_data_pipeline_exports_docling_adapter() -> None:
    from data_pipeline import ExternalParserUnavailable, load_docling_records as exported

    assert exported is load_docling_records
    assert issubclass(ExternalParserUnavailable, RuntimeError)


def test_external_docs_extra_uses_full_docling_runtime_stack() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    external_docs = pyproject["project"]["optional-dependencies"]["external-docs"]

    assert any(item == "docling" or item.startswith("docling>") for item in external_docs)
    assert any(item.startswith("opencv-python") for item in external_docs)
