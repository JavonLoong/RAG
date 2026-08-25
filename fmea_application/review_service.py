"""Application service for review-context reads and candidate persistence."""

from __future__ import annotations

from collections.abc import Callable

from core_domain.fmea.entities import FmeaRow
from core_domain.fmea.states import ActorType

from .ports import ReviewRepository, ReviewRunExecutor, ReviewSuggestionGenerator
from .review_contracts import ActorContext, ReviewCandidateBundle, ReviewContext, ReviewDecisionRecord, ReviewSuggestion
from .review_errors import ReviewError
from .review_projection import build_review_context

_QUERY_ROLES = frozenset({"analyst", "reviewer", "publisher"})


class ReviewService:
    def __init__(
        self,
        repository: ReviewRepository,
        suggestion_generator: ReviewSuggestionGenerator | None = None,
        run_executor: ReviewRunExecutor | None = None,
        *,
        clock: Callable[[], str] | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._repository = repository
        self._suggestion_generator = suggestion_generator
        self._run_executor = run_executor
        self._clock = clock
        self._id_factory = id_factory

    @classmethod
    def for_queries(cls, repository: ReviewRepository) -> ReviewService:
        return cls(repository)

    def persist_generated_candidates(
        self, bundle: ReviewCandidateBundle, actor: ActorContext
    ) -> tuple[FmeaRow, ...]:
        self._authorize_candidate_persistence(actor, bundle)
        return self._repository.save_review_candidate_bundle(bundle, actor)

    def get_context(self, row_id: str, actor: ActorContext) -> ReviewContext:
        self._authorize_query(actor)
        row = self._repository.get_row(row_id, actor.workspace_id)
        if row is None:
            raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
        pack = self._repository.get_evidence_pack(row.evidence_pack_id, actor.workspace_id)
        if pack is None:
            raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
        source = self._repository.get_review_source(row.row_id, actor.workspace_id)
        suggestions = self._repository.list_suggestions(row.row_id, actor.workspace_id)
        decisions = self._repository.list_decisions(row.row_id, actor.workspace_id)
        return build_review_context(row, source, pack, suggestions, decisions)

    def list_suggestions(self, row_id: str, actor: ActorContext) -> tuple[ReviewSuggestion, ...]:
        self._authorize_query(actor)
        suggestions = self._repository.list_suggestions(row_id, actor.workspace_id)
        return tuple(sorted(suggestions, key=lambda item: (item.created_at, item.suggestion_id)))

    def list_decisions(self, row_id: str, actor: ActorContext) -> tuple[ReviewDecisionRecord, ...]:
        self._authorize_query(actor)
        decisions = self._repository.list_decisions(row_id, actor.workspace_id)
        return tuple(sorted(decisions, key=lambda item: (item.record_version, item.created_at, item.decision_id)))

    @staticmethod
    def _require_actor(actor: ActorContext) -> None:
        if not isinstance(actor, ActorContext) or not actor.workspace_id.strip():
            raise ReviewError("FMEA_AUTH_REQUIRED", "authentication is required")

    @classmethod
    def _authorize_query(cls, actor: ActorContext) -> None:
        cls._require_actor(actor)
        if actor.actor_type is ActorType.MODEL or actor.actor_type is not ActorType.HUMAN:
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "actor is not allowed to query review data")
        if not actor.roles.intersection(_QUERY_ROLES):
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "actor is not allowed to query review data")

    @classmethod
    def _authorize_candidate_persistence(cls, actor: ActorContext, bundle: ReviewCandidateBundle) -> None:
        cls._require_actor(actor)
        if bundle.evidence_pack.workspace_id != actor.workspace_id:
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "actor is not allowed to write this workspace")
        if actor.actor_type is ActorType.SYSTEM:
            return
        if actor.actor_type is ActorType.HUMAN and "analyst" in actor.roles:
            return
        raise ReviewError("FMEA_REVIEW_FORBIDDEN", "actor is not allowed to persist candidates")


__all__ = ["ReviewService"]
