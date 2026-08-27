"""Provider-neutral human decisions over immutable assistance suggestions."""

# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from core_domain.fmea.states import FMEA_SCHEMA_ID, ActorType

from .assistance_contracts import (
    AssistanceDecision,
    AssistanceDecisionAction,
    AssistanceHandlerCheckpoint,
    AssistanceSuggestion,
)
from .ports import AssistanceRepository
from .review_contracts import (
    ActorContext,
    AuditEvent,
    IdempotencyScope,
    VersionSet,
    encode_review_json,
    idempotency_key_hash,
)
from .review_errors import ReviewError
from .risk_contracts import PreparedAssistanceDecision, assistance_decision_payload_hash


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def stable_id(prefix: str, *parts: object) -> str:
    value = "|".join(str(part) for part in parts)
    return f"{prefix}-{uuid5(NAMESPACE_URL, f'fmea:{prefix}:{value}') }"


def _version_set(*, template_version: str, scoring_version: str, payload_hash: str) -> VersionSet:
    return VersionSet(
        schema_id=FMEA_SCHEMA_ID,
        data_version="fmea-risk-v1",
        graph_version="not-applicable",
        evidence_pack_version="bound",
        profile_version="bound",
        template_version=template_version,
        scoring_version=scoring_version,
        prompt_version="bound",
        model_version="provider-neutral",
        input_snapshot_hash=payload_hash,
    )


def make_audit(
    *,
    actor: ActorContext,
    scope: IdempotencyScope,
    payload_hash: str,
    command: str,
    reason: str,
    row_id: str,
    analysis_id: str,
    suggestion_id: str | None,
    decision_id: str | None,
    expected_record_version: int | None,
    applied_record_version: int | None,
    evidence_ids: tuple[str, ...],
    template_id: str,
    template_version: str,
    scoring_version: str = "bound",
    occurred_at: str,
    event_id: str,
    request_id: str,
    trace_id: str,
    run_id: str | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        occurred_at_server=occurred_at,
        workspace_id=actor.workspace_id,
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        actor_roles=tuple(sorted(actor.roles)),
        command=command,
        action=None,
        reason_code=None,
        reason=reason,
        analysis_id=analysis_id,
        row_id=row_id,
        suggestion_id=suggestion_id,
        decision_id=decision_id,
        expected_record_version=expected_record_version,
        applied_record_version=applied_record_version,
        before_hash=None,
        after_hash=None,
        changed_fields=(),
        evidence_ids=evidence_ids,
        evidence_request_targets=(),
        idempotency_key_hash=scope.key_hash,
        canonical_payload_hash=payload_hash,
        versions=_version_set(
            template_version=template_version,
            scoring_version=scoring_version,
            payload_hash=payload_hash,
        ),
        template_id=template_id,
        template_version=template_version,
        profile_id="provider-neutral",
        profile_version="1",
        model_manifest=None,
        request_id=request_id,
        trace_id=trace_id,
        retrieval_trace_id=trace_id,
        run_id=run_id,
        request_hash=payload_hash,
    )


@dataclass(frozen=True, slots=True)
class DecideAssistanceCommand:
    suggestion_id: str
    expected_suggestion_version: int
    expected_target_record_version: int
    action: AssistanceDecisionAction
    idempotency_key: str
    reason: str
    edits: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class AssistanceHandlerRequest:
    """A durably reserved command; handlers must upsert canonically by its UUID."""

    suggestion: AssistanceSuggestion[object]
    command: DecideAssistanceCommand
    actor: ActorContext
    reservation_hash: str


@dataclass(frozen=True, slots=True)
class AssistanceHandlerResult:
    """The durable result of an adoption handler's idempotent canonical write."""

    target_type: str
    target_id: str
    idempotency_key: str
    applied_record_version: int

    def __post_init__(self) -> None:
        for field_name in ("target_type", "target_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value.strip())
        if not isinstance(self.idempotency_key, str) or str(UUID(self.idempotency_key)) != self.idempotency_key:
            raise ValueError("idempotency_key must be a canonical lowercase UUID")
        if (
            isinstance(self.applied_record_version, bool)
            or not isinstance(self.applied_record_version, int)
            or self.applied_record_version < 1
        ):
            raise ValueError("applied_record_version must be positive")


AssistanceHandler = Callable[[AssistanceHandlerRequest], AssistanceHandlerResult | None]


def _is_adoption(action: AssistanceDecisionAction) -> bool:
    return action in {
        AssistanceDecisionAction.ADOPT,
        AssistanceDecisionAction.PARTIAL_ADOPT,
        AssistanceDecisionAction.EDIT_AND_ADOPT,
    }


def _reservation_hash(
    scope: IdempotencyScope,
    suggestion: AssistanceSuggestion[object],
    command: DecideAssistanceCommand,
    actor: ActorContext,
) -> str:
    payload = {
        "contract": "fmea.assistance.decision.reservation.v1",
        "scope_key": scope.scope_key,
        "suggestion_id": suggestion.suggestion_id,
        "suggestion_hash": suggestion.suggestion_hash,
        "suggestion_record_version": suggestion.record_version,
        "target_record_version": suggestion.target_record_version,
        "action": command.action.value,
        "reason": command.reason,
        "edits": command.edits,
        "actor_id": actor.actor_id,
        "actor_type": actor.actor_type.value,
        "actor_roles": tuple(sorted(actor.roles)),
        "workspace_id": actor.workspace_id,
    }
    return "sha256:" + sha256(encode_review_json(payload).encode("utf-8")).hexdigest()


def _validate_existing_decision(
    existing: AssistanceDecision,
    suggestion: AssistanceSuggestion[object],
    command: DecideAssistanceCommand,
    actor: ActorContext,
) -> AssistanceDecision:
    if (
        existing.suggestion_id != suggestion.suggestion_id
        or existing.suggestion_hash != suggestion.suggestion_hash
        or existing.action is not command.action
        or existing.actor_id != actor.actor_id
        or existing.idempotency_key != command.idempotency_key
        or existing.reason != command.reason
        or existing.edits != tuple(command.edits)
    ):
        raise ReviewError("FMEA_IDEMPOTENCY_CONFLICT", "assistance decision key is already bound")
    return existing


def _handler_values(
    action: AssistanceDecisionAction,
    suggestion: AssistanceSuggestion[object],
    command: DecideAssistanceCommand,
    result: AssistanceHandlerResult | None,
) -> tuple[tuple[str, str] | None, int | None]:
    if _is_adoption(action):
        if not isinstance(result, AssistanceHandlerResult):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "adopt handlers must return a typed result")
        if (
            result.target_type != suggestion.target_type
            or result.target_id != suggestion.target_id
            or result.idempotency_key != command.idempotency_key
            or result.applied_record_version <= suggestion.target_record_version
        ):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "assistance handler result is not bound to the command")
        return (result.target_type, result.target_id), result.applied_record_version
    if result is not None:
        raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "non-adopt handlers must not return a resource")
    return None, None


def _checkpoint_values(
    checkpoint: AssistanceHandlerCheckpoint,
    suggestion: AssistanceSuggestion[object],
    command: DecideAssistanceCommand,
) -> tuple[tuple[str, str] | None, int | None]:
    identity = checkpoint.resulting_resource_identity
    result = (
        None
        if identity is None
        else AssistanceHandlerResult(
            target_type=identity[0],
            target_id=identity[1],
            idempotency_key=command.idempotency_key,
            applied_record_version=checkpoint.applied_record_version or 0,
        )
    )
    return _handler_values(command.action, suggestion, command, result)


class AssistanceDecisionService:
    """Apply only allowlisted typed human decisions; handlers own domain adoption."""

    def __init__(
        self,
        repository: AssistanceRepository,
        *,
        handlers: Mapping[AssistanceDecisionAction, AssistanceHandler],
        clock: Callable[[], str] = utc_now,
        id_factory: Callable[[str], str] = lambda prefix: stable_id(prefix, "factory"),
    ) -> None:
        expected = set(AssistanceDecisionAction)
        if set(handlers) != expected:
            raise ValueError("all assistance decision actions require allowlisted handlers")
        if any(not callable(handler) for handler in handlers.values()):
            raise ValueError("assistance handlers must be callable")
        self._repository = repository
        self._handlers = dict(handlers)
        self._clock = clock
        self._id_factory = id_factory

    def decide(self, command: DecideAssistanceCommand, actor: ActorContext) -> AssistanceDecision:  # noqa: C901
        if not isinstance(command, DecideAssistanceCommand):
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "assistance decision command is invalid")
        if not isinstance(command.idempotency_key, str):
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "assistance decision idempotency key is invalid")
        try:
            parsed_idempotency_key = UUID(command.idempotency_key)
        except ValueError as exc:
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "assistance decision idempotency key is invalid") from exc
        if str(parsed_idempotency_key) != command.idempotency_key:
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "assistance decision idempotency key is invalid")
        if actor.actor_type is not ActorType.HUMAN or not ({"reviewer", "risk_reviewer"} & actor.roles):
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "a human reviewer is required")
        suggestion = self._repository.get_suggestion(command.suggestion_id, actor.workspace_id)
        if suggestion is None:
            raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "assistance suggestion was not found")
        if suggestion.record_version != command.expected_suggestion_version:
            raise ReviewError("FMEA_REVIEW_SUGGESTION_STALE", "assistance suggestion version is stale")
        if suggestion.target_record_version != command.expected_target_record_version:
            raise ReviewError("FMEA_VERSION_CONFLICT", "assistance target version is stale")

        decision_id = stable_id("assistance-decision", command.idempotency_key)
        existing = self._repository.get_decision(decision_id, actor.workspace_id)
        if existing is not None:
            return _validate_existing_decision(existing, suggestion, command, actor)

        scope = IdempotencyScope(
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            command="fmea.assistance.decide",
            resource_path=f"/assistance/suggestions/{suggestion.suggestion_id}",
            key_hash=idempotency_key_hash(command.idempotency_key),
        )
        created_at = self._clock()
        reservation_hash = _reservation_hash(scope, suggestion, command, actor)
        raced = self._repository.reserve_decision(
            scope,
            reservation_hash,
            decision_id,
            created_at,
        )
        if raced is not None:
            return _validate_existing_decision(raced, suggestion, command, actor)

        checkpoint = self._repository.get_decision_handler_checkpoint(
            scope,
            reservation_hash,
            decision_id,
        )
        if checkpoint is None:
            claimed = self._repository.claim_decision_handler(scope, reservation_hash, decision_id)
            if not claimed:
                checkpoint = self._repository.get_decision_handler_checkpoint(
                    scope,
                    reservation_hash,
                    decision_id,
                )
            if not claimed and checkpoint is None:
                raise ReviewError(
                    "FMEA_REVIEW_ACTION_INVALID",
                    "assistance handler execution was already claimed and requires recovery",
                )
        if checkpoint is not None:
            resource_identity, applied_record_version = _checkpoint_values(
                checkpoint,
                suggestion,
                command,
            )
        else:
            handler_request = AssistanceHandlerRequest(suggestion, command, actor, reservation_hash)
            try:
                handler_result = self._handlers[command.action](handler_request)
            except KeyError as exc:
                raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "assistance decision action is not allowlisted") from exc
            resource_identity, applied_record_version = _handler_values(
                command.action,
                suggestion,
                command,
                handler_result,
            )
            checkpoint = AssistanceHandlerCheckpoint(
                decision_id=decision_id,
                reservation_hash=reservation_hash,
                resulting_resource_identity=resource_identity,
                applied_record_version=applied_record_version,
            )
            self._repository.save_decision_handler_checkpoint(scope, checkpoint)

        decision = AssistanceDecision(
            decision_id=decision_id,
            suggestion_id=suggestion.suggestion_id,
            suggestion_hash=suggestion.suggestion_hash,
            suggestion_record_version=suggestion.record_version,
            target_record_version=suggestion.target_record_version,
            action=command.action,
            actor_id=actor.actor_id,
            actor_type=actor.actor_type,
            edits=command.edits,
            reason=command.reason,
            idempotency_key=command.idempotency_key,
            resulting_resource_identity=resource_identity,
            created_at=created_at,
        )
        payload_hash = assistance_decision_payload_hash(scope, suggestion, decision)
        audit = make_audit(
            actor=actor,
            scope=scope,
            payload_hash=payload_hash,
            command=scope.command,
            reason=command.reason,
            row_id=suggestion.target_id,
            analysis_id=suggestion.target_id,
            suggestion_id=suggestion.suggestion_id,
            decision_id=decision.decision_id,
            expected_record_version=suggestion.target_record_version,
            applied_record_version=applied_record_version,
            evidence_ids=suggestion.evidence_ids,
            template_id=suggestion.template_id or "unbound",
            template_version=suggestion.template_version or "unbound",
            occurred_at=created_at,
            event_id=stable_id("assistance-audit", command.idempotency_key),
            request_id=suggestion.suggestion_id,
            trace_id=suggestion.trace_id,
            run_id=suggestion.run_id,
        )
        prepared = PreparedAssistanceDecision(
            scope=scope,
            payload_hash=payload_hash,
            suggestion=suggestion,
            decision=decision,
            audit=audit,
            reservation_hash=reservation_hash,
        )
        return self._repository.append_decision(prepared)


__all__ = [
    "AssistanceDecisionService",
    "AssistanceHandlerRequest",
    "AssistanceHandlerResult",
    "DecideAssistanceCommand",
    "make_audit",
    "stable_id",
]
