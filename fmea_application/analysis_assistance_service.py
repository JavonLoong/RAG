"""Application service for model-proposed analysis scope drafts."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from core_domain.fmea.states import ActorType

from .assistance_contracts import AssistanceKind, AssistanceRequest, AssistanceSuggestion
from .assistance_service import make_audit, stable_id, utc_now
from .ports import AnalysisAssistanceGenerator, AssistanceRepository
from .review_contracts import ActorContext, IdempotencyScope, idempotency_key_hash
from .review_errors import ReviewError
from .risk_contracts import PreparedAssistanceSuggestion, assistance_suggestion_payload_hash


class AnalysisAssistanceService:
    def __init__(
        self,
        generator: AnalysisAssistanceGenerator,
        repository: AssistanceRepository,
        *,
        clock: Callable[[], str] = utc_now,
        id_factory: Callable[[str], str] = lambda prefix: stable_id(prefix, "factory"),
    ) -> None:
        self._generator = generator
        self._repository = repository
        self._clock = clock
        self._id_factory = id_factory

    def get(self, suggestion_id: str, actor: ActorContext) -> AssistanceSuggestion[object]:
        if not isinstance(suggestion_id, str) or not suggestion_id.strip():
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "assistance suggestion identity is invalid")
        suggestion = self._repository.get_suggestion(suggestion_id, actor.workspace_id)
        if suggestion is None:
            raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "assistance suggestion was not found")
        return suggestion

    def suggest_scope(
        self,
        request: AssistanceRequest[object],
        actor: ActorContext,
    ) -> AssistanceSuggestion[object]:
        if not isinstance(request, AssistanceRequest) or request.kind is not AssistanceKind.ANALYSIS_SCOPE_DRAFT:
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "analysis scope assistance request is invalid")
        if actor.actor_type is not ActorType.MODEL:
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "scope suggestions must be produced by a model actor")
        if actor.workspace_id != request.workspace_id:
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "workspace binding is invalid")
        if request.idempotency_key is None:
            raise ReviewError("FMEA_PRECONDITION_REQUIRED", "scope suggestion requires an idempotency key")
        try:
            suggestion = self._generator.generate(request)
        except ReviewError:
            raise
        except Exception as exc:
            raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "the scope model returned an invalid suggestion") from exc
        if not isinstance(suggestion, AssistanceSuggestion):
            raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "the scope model returned an invalid suggestion")
        if (
            suggestion.kind is not request.kind
            or suggestion.workspace_id != request.workspace_id
            or suggestion.target_type != request.target_type
            or suggestion.target_id != request.target_id
            or suggestion.target_record_version != request.target_record_version
            or suggestion.evidence_pack_ids != request.evidence_pack_ids
            or suggestion.domain_pack_id != request.domain_pack_id
            or suggestion.domain_pack_version != request.domain_pack_version
            or suggestion.template_id != request.template_id
            or suggestion.template_version != request.template_version
            or suggestion.rule_pack_id != request.rule_pack_id
            or suggestion.rule_pack_version != request.rule_pack_version
            or suggestion.applied
        ):
            raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "the scope model changed an immutable binding")
        if not isinstance(suggestion.payload, Mapping) or set(suggestion.payload) != {
            "scope",
            "system_boundary",
            "exclusions",
            "operating_modes",
            "assumptions",
            "limitations",
        }:
            raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "the scope model returned non-scope fields")

        scope = IdempotencyScope(
            workspace_id=request.workspace_id,
            actor_id=actor.actor_id,
            command="fmea.assistance.scope.suggest",
            resource_path=f"/analyses/{request.target_id}/assistance/scope",
            key_hash=idempotency_key_hash(request.idempotency_key),
        )
        payload_hash = assistance_suggestion_payload_hash(scope, suggestion)
        audit = make_audit(
            actor=actor,
            scope=scope,
            payload_hash=payload_hash,
            command=scope.command,
            reason="model scope proposal",
            row_id=request.target_id,
            analysis_id=request.target_id,
            suggestion_id=suggestion.suggestion_id,
            decision_id=None,
            expected_record_version=request.target_record_version,
            applied_record_version=None,
            evidence_ids=suggestion.evidence_ids,
            template_id=request.template_id or "unbound",
            template_version=request.template_version or "unbound",
            occurred_at=suggestion.created_at or self._clock(),
            event_id=stable_id("scope-audit", request.idempotency_key),
            request_id=request.request_id,
            trace_id=suggestion.trace_id,
            run_id=suggestion.run_id,
        )
        prepared = PreparedAssistanceSuggestion(
            scope=scope,
            payload_hash=payload_hash,
            suggestion=suggestion,
            audit=audit,
        )
        return self._repository.save_suggestion(prepared)


__all__ = ["AnalysisAssistanceService"]
