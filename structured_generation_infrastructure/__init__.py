"""Infrastructure adapters for provider-neutral structured generation."""

from .json_codec import StrictCandidateBatchCodec, StrictCriticReportCodec

__all__ = ["StrictCandidateBatchCodec", "StrictCriticReportCodec"]
