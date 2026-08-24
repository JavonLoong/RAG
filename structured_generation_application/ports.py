"""Provider and decoder ports used by the structured-generation application."""

from __future__ import annotations

from typing import Protocol

from core_domain.structured_generation import (
    CriticReport,
    StructuredModelRequest,
    StructuredModelResponse,
)
from core_domain.structured_output import StructuredCandidateBatch


class StructuredModelGateway(Protocol):
    def complete(
        self,
        request: StructuredModelRequest,
        *,
        max_attempts: int,
        timeout_seconds: float,
    ) -> StructuredModelResponse: ...


class CandidateBatchCodec(Protocol):
    def decode_batch(self, content: str) -> StructuredCandidateBatch: ...


class CriticReportCodec(Protocol):
    def decode_critic(self, content: str) -> CriticReport: ...


__all__ = ["CandidateBatchCodec", "CriticReportCodec", "StructuredModelGateway"]
