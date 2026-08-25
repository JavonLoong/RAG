"""Bounded background execution for durable FMEA review runs."""

# Constructor validation uses concise local ValueError messages.
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore

from fmea_application.review_errors import ReviewError


class ThreadPoolReviewRunExecutor:
    """Submit already-authorized review operations to a bounded thread pool."""

    def __init__(self, max_workers: int = 2, max_pending_runs: int = 16) -> None:
        if isinstance(max_workers, bool) or not 1 <= max_workers <= 4:
            raise ValueError("max_workers must be between 1 and 4")
        if isinstance(max_pending_runs, bool) or not 1 <= max_pending_runs <= 64:
            raise ValueError("max_pending_runs must be between 1 and 64")
        self._capacity = BoundedSemaphore(max_pending_runs)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="fmea-review")

    def submit(self, run_id: str, operation: Callable[[], None]) -> None:
        if not self._capacity.acquire(blocking=False):
            raise ReviewError(
                "FMEA_REVIEW_RATE_LIMITED",
                "review execution capacity is full",
                retryable=True,
            )

        def bounded_operation() -> None:
            try:
                operation()
            finally:
                self._capacity.release()

        try:
            self._executor.submit(bounded_operation)
        except Exception:
            self._capacity.release()
            raise

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)


__all__ = ["ThreadPoolReviewRunExecutor"]
