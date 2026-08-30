"""Infrastructure adapters for generic structured output."""

from .file_registry import FileTemplateRegistry
from .jsonschema_adapter import Draft202012SchemaAdapter
from .source_loader import load_template_source, load_template_source_bytes

__all__ = ["Draft202012SchemaAdapter", "FileTemplateRegistry", "load_template_source", "load_template_source_bytes"]
