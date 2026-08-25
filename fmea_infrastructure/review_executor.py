"""Bounded background execution for durable FMEA review runs."""

# Constructor validation uses concise local ValueError messages.
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Lock

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
        self._state_lock = Lock()
        self._closed = False

    def submit(self, run_id: str, operation: Callable[[], None]) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "review run ID is invalid")
        if not callable(operation):
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "review operation is invalid")

        with self._state_lock:
            if self._closed:
                raise ReviewError(
                    "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
                    "review execution is closed",
                    retryable=True,
                )
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
            except Exception as exc:
                self._capacity.release()
                raise ReviewError(
                    "FMEA_MODEL_SUGGESTION_UNAVAILABLE",
                    "review execution is unavailable",
                    retryable=True,
                ) from exc

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._executor.shutdown(wait=True, cancel_futures=False)


__all__ = ["ThreadPoolReviewRunExecutor"]
