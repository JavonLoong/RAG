"""Deterministic retry policy for the DeepSeek structured gateway."""

from __future__ import annotations

_TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})


def is_transient_status(status_code: int) -> bool:
    return isinstance(status_code, int) and not isinstance(status_code, bool) and status_code in _TRANSIENT_STATUSES


def retry_delay_seconds(attempt: int) -> float:
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ValueError
    return float(min(2 ** (attempt - 1), 4))


__all__ = ["is_transient_status", "retry_delay_seconds"]
