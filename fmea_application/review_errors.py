"""Stable public errors for the FMEA review application boundary."""

# Public validation failures intentionally use ValueError for stable callers.
# ruff: noqa: TRY004

from __future__ import annotations

REVIEW_ERROR_CODES = frozenset(
    {
        "FMEA_REVIEW_REQUEST_INVALID",
        "FMEA_AUTH_REQUIRED",
        "FMEA_AUTH_CONFIGURATION_INVALID",
        "FMEA_REVIEW_FORBIDDEN",
        "FMEA_ROW_NOT_FOUND",
        "FMEA_REVIEW_SUGGESTION_NOT_FOUND",
        "FMEA_IDEMPOTENCY_CONFLICT",
        "FMEA_REVIEW_TERMINAL",
        "FMEA_REVIEW_SUGGESTION_STALE",
        "FMEA_VERSION_CONFLICT",
        "FMEA_RISK_VERSION_CONFLICT",
        "FMEA_REVIEW_ACTION_INVALID",
        "FMEA_REVIEW_FIELD_INVALID",
        "FMEA_EVIDENCE_INVALID",
        "FMEA_UNRESOLVED_ACK_REQUIRED",
        "FMEA_REVIEW_SOURCE_MISSING",
        "FMEA_PRECONDITION_REQUIRED",
        "FMEA_REVIEW_RATE_LIMITED",
        "FMEA_MODEL_SUGGESTION_INVALID",
        "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
        "FMEA_REVIEW_STORAGE_UNAVAILABLE",
        "FMEA_REVIEW_RUN_INTERRUPTED",
        "FMEA_REVIEW_CONFIRMATION_REQUIRED",
        "FMEA_RISK_HUMAN_CONFIRMATION_REQUIRED",
    }
)


class ReviewError(ValueError):
    """An application error whose public representation is safe to expose."""

    def __init__(self, code: str, public_message: str, retryable: bool = False) -> None:
        if code not in REVIEW_ERROR_CODES:
            raise ValueError(f"unknown review error code: {code}")  # noqa: TRY003
        if not isinstance(public_message, str) or not public_message.strip():
            raise ValueError("public_message must not be empty")  # noqa: TRY003
        if not isinstance(retryable, bool):
            raise ValueError("retryable must be a boolean")  # noqa: TRY003
        self.code = code
        self.public_message = public_message.strip()
        self.retryable = retryable
        super().__init__(self.public_message)

    def __str__(self) -> str:
        return self.public_message


__all__ = ["REVIEW_ERROR_CODES", "ReviewError"]
