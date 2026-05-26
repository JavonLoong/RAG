"""Core domain models for the GraphRAG system.

Defines the shared vocabulary and data structures used across all modules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Document:
    """A source document in the knowledge base."""
    id: str
    title: str
    source_path: str
    content: str = ""
    page_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Entity:
    """A named entity extracted from a document."""
    name: str
    entity_type: str = "Unknown"
    description: str = ""
    source_document: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Relationship:
    """A relationship between two entities."""
    subject: str
    predicate: str
    object_name: str
    evidence: str = ""
    confidence: float | None = None
    source_document: str | None = None
    source_page: str | None = None


@dataclass(frozen=True, slots=True)
class Community:
    """A group of related entities detected by community algorithms."""
    community_id: str
    level: int = 0
    title: str = ""
    summary: str = ""
    entity_names: list[str] = field(default_factory=list)
    entity_count: int = 0
    edge_count: int = 0


@dataclass(frozen=True, slots=True)
class EvidenceChain:
    """A chain of evidence linking a question to an answer."""
    citation_id: str
    source_type: str  # "text" | "graph" | "community"
    text: str
    source: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QAResult:
    """A question-answering result with evidence."""
    question: str
    answer: str | None
    evidence: list[EvidenceChain] = field(default_factory=list)
    context: str = ""
    search_mode: str = "local"  # "local" | "global" | "hybrid"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "evidence_count": len(self.evidence),
            "search_mode": self.search_mode,
            "metadata": self.metadata,
        }
