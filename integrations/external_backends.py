from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

BackendArea = Literal["document_parsing", "retrieval", "graphrag", "evaluation", "product"]


class ExternalBackendUnavailable(RuntimeError):
    """Raised when an optional open-source backend is not installed or not reachable."""


@dataclass(frozen=True, slots=True)
class ExternalBackendSpec:
    key: str
    project: str
    area: BackendArea
    package_name: str | None
    import_name: str | None
    install_command: str
    license: str
    direct_use: str
    source_url: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


EXTERNAL_BACKENDS: dict[str, ExternalBackendSpec] = {
    "ragflow": ExternalBackendSpec(
        key="ragflow",
        project="RAGFlow",
        area="product",
        package_name=None,
        import_name=None,
        install_command="git clone https://github.com/infiniflow/ragflow.git external_repos/ragflow",
        license="Apache-2.0",
        direct_use="Run as an external RAGFlow service; call its API rather than vendoring the full product source.",
        source_url="https://github.com/infiniflow/ragflow",
        notes="DeepDoc is tightly coupled to the RAGFlow service stack; prefer service/API integration.",
    ),
    "docling": ExternalBackendSpec(
        key="docling",
        project="Docling",
        area="document_parsing",
        package_name="docling",
        import_name="docling",
        install_command="pip install docling",
        license="MIT",
        direct_use="Use DocumentConverter directly for PDF/DOCX/PPTX/HTML/image conversion to Markdown/JSON.",
        source_url="https://github.com/docling-project/docling",
    ),
    "unstructured": ExternalBackendSpec(
        key="unstructured",
        project="Unstructured",
        area="document_parsing",
        package_name="unstructured",
        import_name="unstructured",
        install_command='pip install "unstructured[docx,pdf]"',
        license="Apache-2.0",
        direct_use="Use unstructured.partition.auto.partition for typed document elements.",
        source_url="https://github.com/Unstructured-IO/unstructured",
    ),
    "haystack": ExternalBackendSpec(
        key="haystack",
        project="Haystack",
        area="retrieval",
        package_name="haystack-ai",
        import_name="haystack",
        install_command="pip install haystack-ai",
        license="Apache-2.0",
        direct_use="Use Haystack components and pipelines for production RAG orchestration.",
        source_url="https://github.com/deepset-ai/haystack",
    ),
    "llamaindex": ExternalBackendSpec(
        key="llamaindex",
        project="LlamaIndex",
        area="retrieval",
        package_name="llama-index",
        import_name="llama_index",
        install_command="pip install llama-index",
        license="MIT",
        direct_use="Use LlamaIndex retrievers/query engines/fusion retrievers where installed.",
        source_url="https://github.com/run-llama/llama_index",
    ),
    "lightrag": ExternalBackendSpec(
        key="lightrag",
        project="LightRAG",
        area="graphrag",
        package_name="lightrag-hku",
        import_name="lightrag",
        install_command="pip install lightrag-hku",
        license="MIT",
        direct_use="Use LightRAG SDK/server for full graph-enhanced RAG when available.",
        source_url="https://github.com/HKUDS/LightRAG",
    ),
    "ragas": ExternalBackendSpec(
        key="ragas",
        project="Ragas",
        area="evaluation",
        package_name="ragas",
        import_name="ragas",
        install_command="pip install ragas",
        license="Apache-2.0",
        direct_use="Use Ragas metrics for faithfulness, answer relevance, and context quality.",
        source_url="https://github.com/vibrantlabsai/ragas",
    ),
    "deepeval": ExternalBackendSpec(
        key="deepeval",
        project="DeepEval",
        area="evaluation",
        package_name="deepeval",
        import_name="deepeval",
        install_command="pip install -U deepeval",
        license="Apache-2.0",
        direct_use="Use DeepEval as pytest-like LLM evaluation framework.",
        source_url="https://github.com/confident-ai/deepeval",
    ),
}


@dataclass(slots=True)
class ExternalBackend:
    spec: ExternalBackendSpec
    import_name_override: str | None = None

    @property
    def import_name(self) -> str | None:
        return self.import_name_override or self.spec.import_name

    def ensure_available(self) -> Any:
        if not self.import_name:
            raise ExternalBackendUnavailable(
                f"{self.spec.project} is an external service/backend. Use: {self.spec.install_command}"
            )
        try:
            return importlib.import_module(self.import_name)
        except Exception as exc:  # noqa: BLE001
            raise ExternalBackendUnavailable(
                f"{self.spec.project} backend is not installed or importable. Use: {self.spec.install_command}"
            ) from exc

    def parse_file(self, source_path: str | Path) -> dict[str, Any]:
        if self.spec.key == "docling":
            return _parse_with_docling(source_path, self)
        if self.spec.key == "unstructured":
            return _parse_with_unstructured(source_path, self)
        raise NotImplementedError(f"{self.spec.project} does not expose parse_file through this adapter.")

    def to_dict(self) -> dict[str, Any]:
        payload = self.spec.to_dict()
        payload["available"] = backend_status(self.spec.key)["available"]
        return payload


def get_backend(key: str, *, import_name: str | None = None) -> ExternalBackend:
    try:
        spec = EXTERNAL_BACKENDS[key]
    except KeyError as exc:
        raise KeyError(f"Unknown external backend: {key}") from exc
    return ExternalBackend(spec=spec, import_name_override=import_name)


def backend_status(key: str, *, import_name: str | None = None) -> dict[str, Any]:
    spec = EXTERNAL_BACKENDS.get(key)
    if spec is None:
        return {
            "key": key,
            "available": False,
            "error": f"Unknown external backend: {key}",
            "install_command": None,
        }
    module_name = import_name or spec.import_name
    if not module_name:
        return {
            **spec.to_dict(),
            "available": False,
            "error": "External service backend; not importable as a local Python package.",
        }
    try:
        importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001
        return {
            **spec.to_dict(),
            "available": False,
            "error": str(exc),
        }
    return {
        **spec.to_dict(),
        "available": True,
        "error": None,
    }


def _parse_with_docling(source_path: str | Path, backend: ExternalBackend) -> dict[str, Any]:
    backend.ensure_available()
    try:
        converter_module = importlib.import_module("docling.document_converter")
        converter = converter_module.DocumentConverter()
    except Exception as exc:  # noqa: BLE001
        raise ExternalBackendUnavailable(f"Docling converter is unavailable. Use: {backend.spec.install_command}") from exc

    result = converter.convert(str(source_path))
    document = getattr(result, "document", result)
    text = _document_to_text(document)
    return {
        "backend": backend.spec.key,
        "project": backend.spec.project,
        "source_file": str(source_path),
        "text": text,
        "elements": [],
        "raw_result_type": result.__class__.__name__,
    }


def _parse_with_unstructured(source_path: str | Path, backend: ExternalBackend) -> dict[str, Any]:
    backend.ensure_available()
    try:
        partition_module = importlib.import_module("unstructured.partition.auto")
        elements = partition_module.partition(filename=str(source_path))
    except Exception as exc:  # noqa: BLE001
        raise ExternalBackendUnavailable(
            f"Unstructured partitioner is unavailable. Use: {backend.spec.install_command}"
        ) from exc

    payload_elements = []
    text_parts = []
    for element in elements:
        text = str(getattr(element, "text", "") or "")
        if text:
            text_parts.append(text)
        metadata = getattr(element, "metadata", None)
        metadata_dict = metadata.to_dict() if hasattr(metadata, "to_dict") else {}
        payload_elements.append(
            {
                "text": text,
                "category": str(getattr(element, "category", element.__class__.__name__)),
                "metadata": metadata_dict,
            }
        )
    return {
        "backend": backend.spec.key,
        "project": backend.spec.project,
        "source_file": str(source_path),
        "text": "\n\n".join(text_parts),
        "elements": payload_elements,
        "raw_result_type": "elements",
    }


def _document_to_text(document: Any) -> str:
    for method_name in ("export_to_markdown", "export_to_text"):
        method = getattr(document, method_name, None)
        if callable(method):
            return str(method())
    if hasattr(document, "text"):
        return str(document.text)
    return str(document)
