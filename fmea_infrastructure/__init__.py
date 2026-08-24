"""Infrastructure adapters for the FMEA application boundary."""

from .evidence_provider import QueryPort, QueryServiceEvidenceProvider
from .profile_loader import load_fmea_template_profile

__all__ = ["QueryPort", "QueryServiceEvidenceProvider", "load_fmea_template_profile"]
