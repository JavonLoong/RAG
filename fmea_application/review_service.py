"""Application service for review-context reads and candidate persistence."""

# Stable public ReviewError branches intentionally stay in this orchestration method.
# ruff: noqa: TRY301

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from importlib import import_module
from typing import Any, cast

from core_domain.fmea.entities import FmeaRow
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.policies import validate_row_evidence
from core_domain.fmea.states import (
    FMEA_SCHEMA_ID,
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
    RunStatus,
)
from core_domain.fmea.value_objects import EvidencePack, VersionSet

from .ports import ReviewRepository, ReviewRunExecutor, ReviewSuggestionGenerator
from .review_contracts import (
    EDITABLE_REVIEW_FIELDS,
    ActorContext,
    AuditEvent,
    FieldReviewEdit,
    IdempotencyScope,
    PreparedReviewDecision,
    PreparedSuggestionRun,
    ReviewAction,
    ReviewCandidateBundle,
    ReviewContext,
    ReviewDecisionCommand,
    ReviewDecisionRecord,
    ReviewDecisionResult,
    ReviewModelManifest,
    ReviewModelRequest,
    ReviewSourceSnapshot,
    ReviewSuggestion,
    ReviewSuggestionDraft,
    ReviewSuggestionRun,
    StartReviewSuggestionCommand,
    UnresolvedAcknowledgement,
    canonical_payload_hash,
    idempotency_key_hash,
)
from .review_errors import ReviewError
from .review_projection import build_review_context

_FMEA_CODEC = import_module("core_domain.fmea.codec")
encode_json = cast(Callable[[object], str], _FMEA_CODEC.encode_json)

_QUERY_ROLES = frozenset({"analyst", "reviewer", "publisher"})
_SUGGESTION_ROLES = frozenset({"analyst", "reviewer"})
_SUGGESTION_COMMAND = "review.suggestion.start"
_CREATE_COMMAND = "review.suggestion.create"
_COMPLETE_COMMAND = "review.suggestion.complete"
_FAIL_COMMAND = "review.suggestion.fail"
_DECISION_COMMAND = "review.decision"
_UNRESOLVED_CLAIM_STATUSES = frozenset(
    {
        ClaimStatus.UNKNOWN,
        ClaimStatus.INSUFFICIENT_EVIDENCE,
        ClaimStatus.CONFLICT,
    }
)
_CLAIM_PRIORITY = {
    ClaimStatus.KNOWN: 0,
    ClaimStatus.NOT_APPLICABLE: 1,
    ClaimStatus.UNKNOWN: 2,
    ClaimStatus.INSUFFICIENT_EVIDENCE: 3,
    ClaimStatus.CONFLICT: 4,
}
_DECISION_REVIEW_STATUS = {
    ReviewAction.ACCEPT: ReviewStatus.ACCEPTED,
    ReviewAction.MODIFY_AND_ACCEPT: ReviewStatus.ACCEPTED,
    ReviewAction.REJECT: ReviewStatus.REJECTED,
    ReviewAction.REQUEST_EVIDENCE: ReviewStatus.IN_REVIEW,
    ReviewAction.DEFER: ReviewStatus.IN_REVIEW,
}


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

    def start_suggestion(self, command: StartReviewSuggestionCommand, actor: ActorContext) -> ReviewSuggestionRun:
        self._authorize_suggestion(actor)
        if not isinstance(command, StartReviewSuggestionCommand):
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "review suggestion request is invalid")
        if self._suggestion_generator is None or self._run_executor is None:
            raise ReviewError("FMEA_MODEL_SUGGESTION_UNAVAILABLE", "review suggestion generation is unavailable", retryable=True)

        created_at = self._now()
        run_id = self._new_id("run")
        request_id = self._new_id("request")
        trace_id = self._new_id("trace")
        payload_hash = canonical_payload_hash(command)
        scope = IdempotencyScope(
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            command=_SUGGESTION_COMMAND,
            resource_path=f"/rows/{command.row_id}",
            key_hash=idempotency_key_hash(command.idempotency_key),
        )
        run = ReviewSuggestionRun(
            run_id=run_id,
            row_id=command.row_id,
            source_record_version=command.expected_record_version,
            status=RunStatus.QUEUED,
            suggestion_id=None,
            error_code=None,
            retryable=False,
            request_id=request_id,
            trace_id=trace_id,
            created_at=created_at,
            started_at=None,
            finished_at=None,
        )
        audit = self._start_audit(
            actor=actor,
            command=command,
            event_id=self._new_id("audit"),
            occurred_at=created_at,
            payload_hash=payload_hash,
            request_id=request_id,
            trace_id=trace_id,
        )
        prepared = PreparedSuggestionRun(
            scope=scope,
            payload_hash=payload_hash,
            command=command,
            actor=actor,
            run=run,
            audit=audit,
            response_status=202,
        )
        reservation = self._repository.reserve_suggestion_run(prepared)
        if reservation.replayed:
            return reservation.run
        try:
            self._run_executor.submit(
                reservation.run.run_id,
                lambda: self._execute_suggestion(prepared),
            )
        except ReviewError as exc:
            failed_audit = self._terminal_audit(
                audit,
                event_id=self._new_id("audit"),
                occurred_at=self._now(),
                command=_FAIL_COMMAND,
                actor_id="review-system",
                actor_type=ActorType.SYSTEM,
                actor_roles=(),
                reason=exc.code,
            )
            self._repository.fail_suggestion_run(
                reservation.run.run_id,
                actor.workspace_id,
                exc.code,
                exc.retryable,
                failed_audit,
            )
            return reservation.run
        except Exception as exc:
            failed_audit = self._terminal_audit(
                audit,
                event_id=self._new_id("audit"),
                occurred_at=self._now(),
                command=_FAIL_COMMAND,
                actor_id="review-system",
                actor_type=ActorType.SYSTEM,
                actor_roles=(),
                reason="FMEA_REVIEW_STORAGE_UNAVAILABLE",
            )
            self._repository.fail_suggestion_run(
                reservation.run.run_id,
                actor.workspace_id,
                "FMEA_REVIEW_STORAGE_UNAVAILABLE",
                True,
                failed_audit,
            )
            del exc
            return reservation.run
        return reservation.run

    def get_suggestion_run(self, run_id: str, actor: ActorContext) -> ReviewSuggestionRun:
        self._authorize_query(actor)
        run = self._repository.get_suggestion_run(run_id, actor.workspace_id)
        if run is None:
            raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review run was not found")
        return run

    def _execute_suggestion(self, prepared: PreparedSuggestionRun) -> None:
        run_id = prepared.run.run_id
        try:
            self._repository.mark_suggestion_run_running(run_id, prepared.actor.workspace_id)
            request = self._model_request(prepared)
            generator = self._suggestion_generator
            if generator is None:
                raise ReviewError("FMEA_MODEL_SUGGESTION_UNAVAILABLE", "review suggestion generation is unavailable", retryable=True)
            draft, manifest = generator.generate(request)
            if not isinstance(draft, ReviewSuggestionDraft):
                raise ReviewError("FMEA_MODEL_SUGGESTION_INVALID", "review model suggestion is invalid")
            suggestion = ReviewSuggestion(
                suggestion_id=self._new_id("suggestion"),
                run_id=run_id,
                row_id=prepared.run.row_id,
                source_record_version=prepared.run.source_record_version,
                recommended_action=draft.recommended_action,
                field_findings=draft.field_findings,
                proposed_edits=draft.proposed_edits,
                evidence_requests=draft.evidence_requests,
                missing_evidence=draft.missing_evidence,
                conflicts=draft.conflicts,
                rationale=draft.rationale,
                model_manifest=manifest,
                actor_type=ActorType.MODEL,
                applied=False,
                stale=False,
                created_at=self._now(),
            )
            complete_audit = self._complete_audit(prepared.audit, suggestion)
            self._repository.complete_suggestion_run(
                run_id,
                prepared.actor.workspace_id,
                suggestion,
                complete_audit,
            )
        except ReviewError as exc:
            self._fail_worker(prepared, exc.code, exc.retryable)
        except Exception as exc:
            self._fail_worker(prepared, "FMEA_MODEL_SUGGESTION_UNAVAILABLE", True)
            del exc

    def _model_request(self, prepared: PreparedSuggestionRun) -> ReviewModelRequest:
        row = self._repository.get_row(prepared.run.row_id, prepared.actor.workspace_id)
        if row is None:
            raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
        pack = self._repository.get_evidence_pack(row.evidence_pack_id, prepared.actor.workspace_id)
        if pack is None:
            raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
        source = self._repository.get_review_source(row.row_id, prepared.actor.workspace_id)
        if source is None:
            raise ReviewError("FMEA_REVIEW_SOURCE_MISSING", "review source snapshot was not found")
        suggestions = self._repository.list_suggestions(row.row_id, prepared.actor.workspace_id)
        decisions = self._repository.list_decisions(row.row_id, prepared.actor.workspace_id)
        context = build_review_context(row, source, pack, suggestions, decisions)
        if context.evidence.workspace_id != prepared.actor.workspace_id:
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "review context is outside the actor workspace")
        return ReviewModelRequest(
            run_id=prepared.run.run_id,
            context=context,
            evidence_pack=pack,
            review_policy=prepared.command.review_policy,
            focus_fields=prepared.command.focus_fields,
            template_id="fmea-row-review",
            template_version="1.0.0",
        )

    def _fail_worker(self, prepared: PreparedSuggestionRun, error_code: str, retryable: bool) -> None:
        try:
            audit = self._terminal_audit(
                prepared.audit,
                event_id=self._new_id("audit"),
                occurred_at=self._now(),
                command=_FAIL_COMMAND,
                actor_id="review-system",
                actor_type=ActorType.SYSTEM,
                actor_roles=(),
                reason=error_code,
            )
            self._repository.fail_suggestion_run(
                prepared.run.run_id,
                prepared.actor.workspace_id,
                error_code,
                retryable,
                audit,
            )
        except Exception:
            return None

    def list_decisions(self, row_id: str, actor: ActorContext) -> tuple[ReviewDecisionRecord, ...]:
        self._authorize_query(actor)
        decisions = self._repository.list_decisions(row_id, actor.workspace_id)
        return tuple(sorted(decisions, key=lambda item: (item.record_version, item.created_at, item.decision_id)))

    def submit_decision(self, command: ReviewDecisionCommand, actor: ActorContext) -> ReviewDecisionResult:
        """Authorize and atomically apply one human review decision."""

        self._authorize_decision(actor)
        if not isinstance(command, ReviewDecisionCommand):
            raise ReviewError("FMEA_REVIEW_REQUEST_INVALID", "review decision request is invalid")

        payload_hash = canonical_payload_hash(command)
        scope = IdempotencyScope(
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            command=_DECISION_COMMAND,
            resource_path=f"/rows/{command.row_id}",
            key_hash=idempotency_key_hash(command.idempotency_key),
        )
        replay = self._repository.replay_decision(scope, payload_hash)
        if replay is not None:
            return replay

        row = self._repository.get_row(command.row_id, actor.workspace_id)
        if row is None:
            raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
        if row.record_version != command.expected_record_version:
            raise ReviewError("FMEA_VERSION_CONFLICT", "review row version does not match the request")
        if row.review_status in {ReviewStatus.ACCEPTED, ReviewStatus.REJECTED, ReviewStatus.SUPERSEDED}:
            raise ReviewError("FMEA_REVIEW_TERMINAL", "review row is already terminal")
        if row.review_status not in {ReviewStatus.SUGGESTED, ReviewStatus.IN_REVIEW}:
            raise ReviewError("FMEA_PRECONDITION_REQUIRED", "review row is not available for human review")
        if row.publication_status is not PublicationStatus.UNPUBLISHED:
            raise ReviewError("FMEA_PRECONDITION_REQUIRED", "published rows cannot receive review decisions")

        pack = self._repository.get_evidence_pack(row.evidence_pack_id, actor.workspace_id)
        if pack is None:
            raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
        source = self._repository.get_review_source(row.row_id, actor.workspace_id)
        suggestions = self._repository.list_suggestions(row.row_id, actor.workspace_id)
        self._repository.list_decisions(row.row_id, actor.workspace_id)
        return self._prepare_and_commit_decision(
            command=command,
            actor=actor,
            row=row,
            pack=pack,
            source=source,
            suggestions=suggestions,
            scope=scope,
            payload_hash=payload_hash,
        )

    def _prepare_and_commit_decision(  # noqa: C901
        self,
        *,
        command: ReviewDecisionCommand,
        actor: ActorContext,
        row: FmeaRow,
        pack: EvidencePack,
        source: ReviewSourceSnapshot | None,
        suggestions: tuple[ReviewSuggestion, ...],
        scope: IdempotencyScope,
        payload_hash: str,
    ) -> ReviewDecisionResult:
        self._validate_decision_command(command)
        if command.suggestion_id is not None:
            suggestion = next(
                (item for item in suggestions if item.suggestion_id == command.suggestion_id),
                None,
            )
            if suggestion is None:
                raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review suggestion was not found")
            if (
                suggestion.row_id != row.row_id
                or suggestion.source_record_version != row.record_version
                or suggestion.stale
            ):
                raise ReviewError("FMEA_REVIEW_SUGGESTION_STALE", "review suggestion is stale")

        if command.action in {ReviewAction.ACCEPT, ReviewAction.MODIFY_AND_ACCEPT} and source is None:
            raise ReviewError("FMEA_REVIEW_SOURCE_MISSING", "review source snapshot was not found")
        if source is not None and (
            source.row_id != row.row_id or source.source_record_version != row.record_version
        ):
            raise ReviewError("FMEA_REVIEW_SOURCE_MISSING", "review source snapshot is not current")

        status_by_field = self._source_claim_statuses(row, source)
        field_evidence = dict(row.field_evidence)
        field_support = dict(row.field_support)
        if command.action is ReviewAction.MODIFY_AND_ACCEPT:
            for edit in command.edits:
                self._validate_edit(edit, pack, field_evidence, field_support)
                field_evidence[edit.target_field] = edit.evidence_ids
                field_support[edit.target_field] = edit.support_status
                status_by_field[edit.target_field] = edit.claim_status

        if command.action in {ReviewAction.ACCEPT, ReviewAction.MODIFY_AND_ACCEPT}:
            self._validate_unresolved_acknowledgements(command.unresolved_acknowledgements, status_by_field)
        elif command.unresolved_acknowledgements:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "unresolved acknowledgements require acceptance")

        claim_status = max(
            (row.claim_status, *status_by_field.values()),
            key=lambda status: _CLAIM_PRIORITY[status],
        )
        next_row = replace(
            row,
            field_evidence=tuple((field, field_evidence[field]) for field, _ in row.field_evidence),
            field_support=tuple((field, field_support[field]) for field, _ in row.field_support),
            claim_status=claim_status,
            review_status=_DECISION_REVIEW_STATUS[command.action],
            record_version=row.record_version + 1,
        )
        for edit in command.edits:
            next_row = self._replace_row_field(next_row, edit)
        try:
            validate_row_evidence(next_row, pack)
        except (FmeaDomainError, ValueError) as exc:
            raise ReviewError("FMEA_EVIDENCE_INVALID", "review decision evidence is invalid") from exc

        created_at = self._now()
        decision_id = self._new_id("decision")
        audit_event_id = self._new_id("audit")
        request_id = self._new_id("request")
        trace_id = self._new_id("trace")
        decision = ReviewDecisionRecord(
            decision_id=decision_id,
            row_id=row.row_id,
            previous_record_version=row.record_version,
            record_version=next_row.record_version,
            actor_id=actor.actor_id,
            action=command.action,
            suggestion_id=command.suggestion_id,
            reason_code=command.reason_code,
            reason=command.reason,
            edits=command.edits,
            evidence_requests=command.evidence_requests,
            unresolved_acknowledgements=command.unresolved_acknowledgements,
            created_at=created_at,
        )
        before_hash = self._row_hash(row)
        after_hash = self._row_hash(next_row)
        evidence_ids = tuple(sorted({evidence_id for edit in command.edits for evidence_id in edit.evidence_ids}))
        audit = AuditEvent(
            event_id=audit_event_id,
            occurred_at_server=created_at,
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            actor_type=ActorType.HUMAN,
            actor_roles=tuple(sorted(actor.roles)),
            command=_DECISION_COMMAND,
            action=command.action,
            reason_code=command.reason_code,
            reason=command.reason,
            analysis_id=row.analysis_id,
            row_id=row.row_id,
            suggestion_id=command.suggestion_id,
            decision_id=decision_id,
            expected_record_version=row.record_version,
            applied_record_version=next_row.record_version,
            before_hash=before_hash,
            after_hash=after_hash,
            changed_fields=tuple(sorted(edit.target_field for edit in command.edits)),
            evidence_ids=evidence_ids,
            evidence_request_targets=tuple(sorted(item.target_field for item in command.evidence_requests)),
            idempotency_key_hash=idempotency_key_hash(command.idempotency_key),
            canonical_payload_hash=payload_hash,
            versions=self._audit_versions(payload_hash),
            template_id="fmea-row-review",
            template_version="1.0.0",
            profile_id="fmea-review",
            profile_version="1.0.0",
            model_manifest=None,
            request_id=request_id,
            trace_id=trace_id,
            retrieval_trace_id=trace_id,
        )
        prepared = PreparedReviewDecision(
            scope=scope,
            payload_hash=payload_hash,
            expected_record_version=row.record_version,
            previous_row=row,
            next_row=next_row,
            decision=decision,
            audit=audit,
            response_status=200,
        )
        return self._repository.commit_review_decision(prepared)

    @staticmethod
    def _validate_decision_command(command: ReviewDecisionCommand) -> None:
        if not isinstance(command.action, ReviewAction):
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "review action is invalid")
        if command.action is ReviewAction.MODIFY_AND_ACCEPT and not command.edits:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "modify_and_accept requires an edit")
        if command.action is not ReviewAction.MODIFY_AND_ACCEPT and command.edits:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "only modify_and_accept may contain edits")
        if command.action is ReviewAction.REQUEST_EVIDENCE and not command.evidence_requests:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "request_evidence requires an evidence request")
        if command.action is not ReviewAction.REQUEST_EVIDENCE and command.evidence_requests:
            raise ReviewError("FMEA_REVIEW_ACTION_INVALID", "only request_evidence may contain evidence requests")
        if len({edit.target_field for edit in command.edits}) != len(command.edits):
            raise ReviewError("FMEA_REVIEW_FIELD_INVALID", "a field may be edited only once")
        if len({item.target_field for item in command.evidence_requests}) != len(command.evidence_requests):
            raise ReviewError("FMEA_REVIEW_FIELD_INVALID", "a field may have only one evidence request")

    @staticmethod
    def _source_claim_statuses(row: FmeaRow, source: ReviewSourceSnapshot | None) -> dict[str, ClaimStatus]:
        result = dict.fromkeys(EDITABLE_REVIEW_FIELDS, row.claim_status)
        if source is not None:
            result.update(dict(source.field_claim_statuses))
        return result

    @staticmethod
    def _validate_edit(
        edit: FieldReviewEdit,
        pack: EvidencePack,
        field_evidence: dict[str, tuple[str, ...]],
        field_support: dict[str, EvidenceSupportStatus],
    ) -> None:
        if edit.target_field not in EDITABLE_REVIEW_FIELDS:
            raise ReviewError("FMEA_REVIEW_FIELD_INVALID", "review field is not editable")
        if edit.target_field == "failure_mode":
            if not isinstance(edit.value, str):
                raise ReviewError("FMEA_REVIEW_FIELD_INVALID", "failure_mode must be scalar text")
        elif not isinstance(edit.value, tuple):
            raise ReviewError("FMEA_REVIEW_FIELD_INVALID", "review field must be an array of text")
        pack_evidence_ids = {ref.evidence_id for ref in pack.refs}
        if not set(edit.evidence_ids).issubset(pack_evidence_ids):
            raise ReviewError("FMEA_EVIDENCE_INVALID", "review decision evidence is outside the current pack")
        if edit.claim_status is ClaimStatus.KNOWN:
            if edit.support_status is not EvidenceSupportStatus.SUPPORTED:
                raise ReviewError("FMEA_EVIDENCE_INVALID", "known review claims require supported evidence")
            if not edit.evidence_ids:
                raise ReviewError("FMEA_EVIDENCE_INVALID", "known review claims require evidence")
        if edit.target_field not in field_evidence or edit.target_field not in field_support:
            raise ReviewError("FMEA_REVIEW_FIELD_INVALID", "review field is not present on the row")

    @staticmethod
    def _replace_row_field(row: FmeaRow, edit: FieldReviewEdit) -> FmeaRow:
        return cast(FmeaRow, replace(cast(Any, row), **{edit.target_field: edit.value}))

    @staticmethod
    def _validate_unresolved_acknowledgements(
        acknowledgements: tuple[UnresolvedAcknowledgement, ...],
        status_by_field: dict[str, ClaimStatus],
    ) -> None:
        unresolved = {
            field: status for field, status in status_by_field.items() if status in _UNRESOLVED_CLAIM_STATUSES
        }
        supplied = {item.target_field: item.claim_status for item in acknowledgements}
        if len(supplied) != len(acknowledgements) or supplied != unresolved:
            raise ReviewError("FMEA_UNRESOLVED_ACK_REQUIRED", "every unresolved field requires an exact acknowledgement")

    @staticmethod
    def _row_hash(row: FmeaRow) -> str:
        return "sha256:" + sha256(encode_json(row).encode("utf-8")).hexdigest()

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
    def _authorize_suggestion(cls, actor: ActorContext) -> None:
        cls._require_actor(actor)
        if actor.actor_type is not ActorType.HUMAN or not actor.roles.intersection(_SUGGESTION_ROLES):
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "actor is not allowed to start review suggestions")

    @classmethod
    def _authorize_decision(cls, actor: ActorContext) -> None:
        cls._require_actor(actor)
        if actor.actor_type is not ActorType.HUMAN or "reviewer" not in actor.roles:
            raise ReviewError("FMEA_REVIEW_FORBIDDEN", "actor is not allowed to submit review decisions")

    def _now(self) -> str:
        return self._clock() if self._clock is not None else ""

    def _new_id(self, prefix: str) -> str:
        if self._id_factory is None:
            raise ReviewError("FMEA_REVIEW_STORAGE_UNAVAILABLE", "review IDs are unavailable", retryable=True)
        return self._id_factory(prefix)

    @staticmethod
    def _audit_versions(payload_hash: str) -> VersionSet:
        return VersionSet(
            schema_id=FMEA_SCHEMA_ID,
            data_version="review-v1",
            graph_version="review-v1",
            evidence_pack_version="review-v1",
            profile_version="review-v1",
            template_version="1.0.0",
            scoring_version="review-v1",
            prompt_version="review-v1",
            model_version="review-v1",
            input_snapshot_hash=payload_hash,
        )

    def _start_audit(
        self,
        *,
        actor: ActorContext,
        command: StartReviewSuggestionCommand,
        event_id: str,
        occurred_at: str,
        payload_hash: str,
        request_id: str,
        trace_id: str,
    ) -> AuditEvent:
        return AuditEvent(
            event_id=event_id,
            occurred_at_server=occurred_at,
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            actor_type=actor.actor_type,
            actor_roles=tuple(sorted(actor.roles)),
            command=_CREATE_COMMAND,
            action=None,
            reason_code=None,
            reason="model review suggestion requested",
            analysis_id=command.row_id,
            row_id=command.row_id,
            suggestion_id=None,
            decision_id=None,
            expected_record_version=command.expected_record_version,
            applied_record_version=None,
            before_hash=None,
            after_hash=None,
            changed_fields=(),
            evidence_ids=(),
            evidence_request_targets=(),
            idempotency_key_hash=idempotency_key_hash(command.idempotency_key),
            canonical_payload_hash=payload_hash,
            versions=self._audit_versions(payload_hash),
            template_id="fmea-row-review",
            template_version="1.0.0",
            profile_id="fmea-review",
            profile_version="1.0.0",
            model_manifest=None,
            request_id=request_id,
            trace_id=trace_id,
            retrieval_trace_id=trace_id,
        )

    @staticmethod
    def _terminal_audit(
        audit: AuditEvent,
        *,
        event_id: str,
        occurred_at: str,
        command: str,
        actor_id: str,
        actor_type: ActorType,
        actor_roles: tuple[str, ...],
        reason: str,
        action: ReviewAction | None = None,
        suggestion_id: str | None = None,
        model_manifest: ReviewModelManifest | None = None,
        evidence_ids: tuple[str, ...] = (),
        changed_fields: tuple[str, ...] = (),
        evidence_request_targets: tuple[str, ...] = (),
    ) -> AuditEvent:
        return replace(
            audit,
            event_id=event_id,
            occurred_at_server=occurred_at,
            command=command,
            actor_id=actor_id,
            actor_type=actor_type,
            actor_roles=actor_roles,
            reason=reason,
            action=action,
            suggestion_id=suggestion_id,
            model_manifest=model_manifest,
            evidence_ids=evidence_ids,
            changed_fields=changed_fields,
            evidence_request_targets=evidence_request_targets,
        )

    def _complete_audit(self, audit: AuditEvent, suggestion: ReviewSuggestion) -> AuditEvent:
        evidence_ids = {
            evidence_id
            for finding in suggestion.field_findings
            for evidence_id in finding.evidence_ids
        }
        evidence_ids.update(evidence_id for edit in suggestion.proposed_edits for evidence_id in edit.evidence_ids)
        evidence_ids.update(evidence_id for conflict in suggestion.conflicts for evidence_id in conflict.evidence_ids)
        return self._terminal_audit(
            audit,
            event_id=self._new_id("audit"),
            occurred_at=suggestion.created_at,
            command=_COMPLETE_COMMAND,
            actor_id="review-model",
            actor_type=ActorType.MODEL,
            actor_roles=(),
            reason="model review suggestion completed",
            action=suggestion.recommended_action,
            suggestion_id=suggestion.suggestion_id,
            model_manifest=suggestion.model_manifest,
            evidence_ids=tuple(sorted(evidence_ids)),
            changed_fields=tuple(sorted(edit.target_field for edit in suggestion.proposed_edits)),
            evidence_request_targets=tuple(sorted(item.target_field for item in suggestion.evidence_requests)),
        )

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
