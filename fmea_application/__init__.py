"""Application-layer ports for the FMEA evidence handoff."""

from .ports import (
    EvidenceProvider,
    EvidenceRequest,
    EvidenceSnapshot,
    FmeaRepository,
    PropagationEvidenceProvider,
    PropagationRequest,
)
from .structured_candidate_adapter import (
    FmeaAdaptationResult,
    FmeaTemplateProfile,
    StructuredCandidateFmeaAdapter,
)

__all__ = [
    "EvidenceProvider",
    "EvidenceRequest",
    "EvidenceSnapshot",
    "FmeaAdaptationResult",
    "FmeaRepository",
    "FmeaTemplateProfile",
    "PropagationEvidenceProvider",
    "PropagationRequest",
    "StructuredCandidateFmeaAdapter",
]
