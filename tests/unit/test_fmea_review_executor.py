"""Direct lifecycle tests for the bounded review executor."""

from __future__ import annotations

from threading import Event
from time import monotonic

from fmea_infrastructure.review_executor import ThreadPoolReviewRunExecutor


def test_nonblocking_close_cancels_pending_work_and_is_idempotent() -> None:
    executor = ThreadPoolReviewRunExecutor(max_workers=1, max_pending_runs=2)
    started = Event()
    release = Event()
    finished = Event()
    pending_ran = Event()

    def running_operation() -> None:
        started.set()
        release.wait(1.0)
        finished.set()

    executor.submit("running", running_operation)
    assert started.wait(1.0)
    executor.submit("pending", pending_ran.set)

    started_at = monotonic()
    executor.close_nonblocking()
    elapsed = monotonic() - started_at
    executor.close_nonblocking()

    release.set()
    assert finished.wait(1.0)
    assert not pending_ran.is_set()
    assert elapsed < 0.5
