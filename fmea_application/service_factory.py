"""Pure application composition for the review service."""

from __future__ import annotations

from collections.abc import Callable

from .ports import ReviewRepository, ReviewRunExecutor, ReviewSuggestionGenerator
from .review_service import ReviewService


def build_review_service(
    repository: ReviewRepository,
    generator: ReviewSuggestionGenerator,
    executor: ReviewRunExecutor,
    *,
    clock: Callable[[], str],
    id_factory: Callable[[str], str],
) -> ReviewService:
    return ReviewService(
        repository,
        generator,
        executor,
        clock=clock,
        id_factory=id_factory,
    )


__all__ = ["build_review_service"]
