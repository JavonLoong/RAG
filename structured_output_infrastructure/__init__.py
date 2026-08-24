"""Infrastructure adapters for generic structured output."""

from .jsonschema_adapter import Draft202012SchemaAdapter
from .source_loader import load_template_source

__all__ = ["Draft202012SchemaAdapter", "load_template_source"]
