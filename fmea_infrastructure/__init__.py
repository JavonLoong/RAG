"""Infrastructure adapters for the FMEA application boundary."""

from .evidence_provider import QueryPort, QueryServiceEvidenceProvider

__all__ = ["QueryPort", "QueryServiceEvidenceProvider"]
