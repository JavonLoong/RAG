"""Application orchestration for the immutable FMEA governance lifecycle."""

# Governance methods intentionally centralize a small, explicit state machine.
# ruff: noqa: C901, TRY003, TRY004, TRY301

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from core_domain.fmea.governance import (
    ApprovalDecision,
    ApprovalStatus,
    ApprovalSubmission,
    ApprovalWithdrawalRecord,
    FmeaRevision,
    PublicationLifecycleView,
    PublicationManifest,
    PublicationWithdrawalRecord,
    PublishedRevision,
    ReadinessIssue,
    RevisionPublicationStatus,
    SupersessionRecord,
    canonical_hash,
    validate_approval_binding,
    validate_supersession_binding,
)
from core_domain.fmea.states import ActorType

from .governance_contracts import (
    ApprovalCommand,
    ApprovalRejectionCommand,
    ApprovalResult,
    ApprovalSubmissionResult,
    AssembleRevisionCommand,
    GovernanceHistoryQuery,
    PreparedApproval,
    PreparedApprovalSubmission,
    PreparedApprovalWithdrawal,
    PreparedPublication,
    PreparedPublicationWithdrawal,
    PreparedRevision,
    PreparedSupersession,
    PublicationResult,
    PublicationWithdrawalResult,
    PublishCommand,
    RevisionResult,
    SubmitApprovalCommand,
    SupersedePublicationCommand,
    SupersessionResult,
    WithdrawApprovalCommand,
    WithdrawPublicationCommand,
    canonical_governance_payload,
    governance_payload_hash,
)
from .ports import ApprovalWithdrawalResult, GovernanceHistoryPage, GovernanceRepository, GovernanceSourcePort
from .review_contracts import ActorContext, AuditEvent, IdempotencyScope, VersionSet, idempotency_key_hash
from .review_errors import ReviewError
from .revision_assembler import (
    GovernanceArtifactSet,
    GovernanceInputs,
    PublicationReadinessContext,
    PublicationReadinessPolicy,
    PublicationReadinessReport,
    RevisionAssembler,
)
from .risk_contracts import OutboxEvent, outbox_payload_hash
from .snapshot_contracts import NormalizedFmeaSnapshot, NormalizedSnapshotInput, build_normalized_snapshot

Clock = Callable[[], str]
IdFactory = Callable[[str], str]


def _export_hash(value: str) -> str:
    return value.removeprefix("sha256:")


def _content_hash(value: object) -> str:
    return canonical_hash(value)


_COMMANDS = {
    "assemble": "fmea.revision.assemble",
    "readiness": "fmea.revision.readiness",
    "submit": "fmea.approval.submit",
    "decide": "fmea.approval.decide",
    "approval_withdraw": "fmea.approval.withdraw",
    "publish": "fmea.publication.publish",
    "publication_withdraw": "fmea.publication.withdraw",
    "supersede": "fmea.publication.supersede",
}
_GOVERNANCE_CODES = frozenset({
    "FMEA_GOVERNANCE_REVISION_NOT_FOUND",
    "FMEA_GOVERNANCE_REVISION_STALE",
    "FMEA_GOVERNANCE_NOT_READY",
    "FMEA_GOVERNANCE_ACTIVE_RUN",
    "FMEA_GOVERNANCE_APPROVAL_NOT_FOUND",
    "FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
    "FMEA_GOVERNANCE_APPROVAL_STALE",
    "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN",
    "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN",
    "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
    "FMEA_GOVERNANCE_SUPERSESSION_INVALID",
    "FMEA_GOVERNANCE_VERSION_CONFLICT",
    "FMEA_GOVERNANCE_IDEMPOTENCY_CONFLICT",
    "FMEA_GOVERNANCE_CURSOR_INVALID",
    "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE",
    "FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID",
})
_ROLE_QUERY = frozenset({"reviewer", "approver", "publisher"})
_MAX_SUPERSESSION_DEPTH = 64


class GovernanceServiceError(ReviewError):
    """ReviewError with a governance-specific code from the shared envelope."""

    def __init__(self, code: str, public_message: str, retryable: bool = False) -> None:
        if code not in _GOVERNANCE_CODES and not code.startswith("FMEA_GOVERNANCE_"):
            raise ValueError(f"unknown governance error code: {code}")
        if not isinstance(public_message, str) or not public_message.strip():
            raise ValueError("public_message must not be empty")
        if not isinstance(retryable, bool):
            raise ValueError("retryable must be a boolean")
        self.code = code
        self.public_message = public_message.strip()
        self.retryable = retryable
        ValueError.__init__(self, self.public_message)

    def __str__(self) -> str:
        return f"{self.code}: {self.public_message}"


def _error(code: str, message: str, *, retryable: bool = False) -> GovernanceServiceError:
    return GovernanceServiceError(code, message, retryable=retryable)


def _map_repository_error(
    exc: Exception, fallback: str = "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE"
) -> GovernanceServiceError:
    if isinstance(exc, GovernanceServiceError):
        return exc
    if isinstance(exc, ReviewError):
        mapped = {
            "FMEA_IDEMPOTENCY_CONFLICT": "FMEA_GOVERNANCE_IDEMPOTENCY_CONFLICT",
            "FMEA_VERSION_CONFLICT": "FMEA_GOVERNANCE_VERSION_CONFLICT",
            "FMEA_REVIEW_STORAGE_UNAVAILABLE": "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE",
        }.get(exc.code, fallback)
        return _error(mapped, "governance persistence rejected the request", retryable=exc.retryable)
    if isinstance(exc, ValueError) and "cursor" in str(exc).casefold():
        return _error("FMEA_GOVERNANCE_CURSOR_INVALID", "governance history cursor is invalid")
    return _error(fallback, "governance persistence is unavailable", retryable=True)


def _raise_mapped(exc: Exception, fallback: str = "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE") -> None:
    raise _map_repository_error(exc, fallback) from None


@dataclass(frozen=True, slots=True)
class _RevisionState:
    revision: FmeaRevision
    record_version: int


class RevisionGovernanceService:
    """Coordinate immutable governance contracts without owning persistence."""

    def __init__(
        self,
        repository: GovernanceRepository,
        assembler: RevisionAssembler | None,
        readiness_policy: PublicationReadinessPolicy | None,
        source: GovernanceSourcePort | None = None,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self._repository = repository
        self._assembler = assembler
        self._readiness_policy = readiness_policy
        self._source = source
        self._clock = clock or self._default_clock
        self._id_factory = id_factory

    @staticmethod
    def _default_clock() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _authorize(self, actor: ActorContext, role: str, code: str) -> None:
        if not isinstance(actor, ActorContext) or actor.actor_type is not ActorType.HUMAN or role not in actor.roles:
            raise _error(code, "actor is not authorized for this governance operation")

    def _authorize_query(self, actor: ActorContext) -> None:
        if (
            not isinstance(actor, ActorContext)
            or actor.actor_type is not ActorType.HUMAN
            or not (_ROLE_QUERY & actor.roles)
        ):
            raise _error("FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN", "actor is not authorized to query governance data")

    @staticmethod
    def _stable_id(prefix: str, scope: IdempotencyScope) -> str:
        seed = f"{prefix}:{scope.scope_key}"
        return f"{prefix}-{uuid5(NAMESPACE_URL, seed)}"

    def _event_id(self, prefix: str, scope: IdempotencyScope) -> str:
        if self._id_factory is not None:
            return self._id_factory(f"{prefix}-{scope.key_hash.removeprefix('sha256:')[:24]}")
        return self._stable_id(prefix, scope)

    @staticmethod
    def _scope(actor: ActorContext, command: str, resource_path: str, key: str) -> IdempotencyScope:
        return IdempotencyScope(
            actor.workspace_id,
            actor.actor_id,
            command,
            resource_path,
            idempotency_key_hash(key),
        )

    @staticmethod
    def _versions(payload_hash: str) -> VersionSet:
        digest = payload_hash.removeprefix("sha256:")
        return VersionSet(
            "graphrag.fmea.v1",
            "governance",
            "governance",
            "governance",
            "governance",
            "governance",
            "governance",
            "governance",
            "governance",
            digest,
        )

    def _audit(
        self,
        actor: ActorContext,
        scope: IdempotencyScope,
        payload_hash: str,
        aggregate_id: str,
        analysis_id: str,
        reason: str,
        *,
        decision_id: str | None = None,
        expected_record_version: int | None = None,
        applied_record_version: int | None = None,
        after_hash: str | None = None,
    ) -> AuditEvent:
        event_id = self._event_id("audit", scope)
        return AuditEvent(
            event_id=event_id,
            occurred_at_server=self._clock(),
            workspace_id=actor.workspace_id,
            actor_id=actor.actor_id,
            actor_type=actor.actor_type,
            actor_roles=tuple(sorted(actor.roles)),
            command=scope.command,
            action=None,
            reason_code=None,
            reason=reason,
            analysis_id=analysis_id,
            row_id=aggregate_id,
            suggestion_id=None,
            decision_id=decision_id,
            expected_record_version=expected_record_version,
            applied_record_version=applied_record_version,
            before_hash=None,
            after_hash=after_hash,
            changed_fields=(),
            evidence_ids=(),
            evidence_request_targets=(),
            idempotency_key_hash=scope.key_hash,
            canonical_payload_hash=payload_hash,
            versions=self._versions(payload_hash),
            template_id="fmea-governance",
            template_version="1.0.0",
            profile_id="governance",
            profile_version="1.0.0",
            model_manifest=None,
            request_id=event_id,
            trace_id=event_id,
            retrieval_trace_id=event_id,
            request_hash=payload_hash,
        )

    @staticmethod
    def _outbox(
        scope: IdempotencyScope, payload: Mapping[str, object], aggregate_id: str, created_at: str
    ) -> OutboxEvent:
        return OutboxEvent(
            event_id=f"outbox-{scope.scope_key}",
            workspace_id=scope.workspace_id,
            aggregate_type="fmea_governance",
            aggregate_id=aggregate_id,
            event_type=scope.command,
            payload=payload,
            payload_hash=outbox_payload_hash(payload),
            created_at=created_at,
            scope_key=scope.scope_key,
        )

    def _inputs(self, analysis_id: str, workspace_id: str) -> GovernanceInputs:
        if self._source is None:
            raise _error(
                "FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID",
                "governance source is not configured",
            )
        try:
            inputs = self._source.load_inputs(analysis_id, workspace_id)
        except Exception as exc:
            _raise_mapped(exc)
        if (
            not isinstance(inputs, GovernanceInputs)
            or inputs.analysis_id != analysis_id
            or inputs.workspace_id != workspace_id
        ):
            raise _error(
                "FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID",
                "governance source returned an invalid workspace binding",
            )
        return inputs

    def _revision_state(self, revision_id: str, workspace_id: str) -> _RevisionState | None:
        try:
            revision = self._repository.get_revision(revision_id, workspace_id)
            version = self._repository.get_revision_record_version(revision_id, workspace_id)
        except Exception as exc:
            _raise_mapped(exc)
        if revision is None:
            if version is not None:
                raise _error("FMEA_GOVERNANCE_STORAGE_UNAVAILABLE", "governance revision state is inconsistent")
            return None
        if (
            not isinstance(revision, FmeaRevision)
            or revision.revision_id != revision_id
            or revision.workspace_id != workspace_id
        ):
            raise _error("FMEA_GOVERNANCE_REVISION_NOT_FOUND", "governance revision was not found")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise _error("FMEA_GOVERNANCE_STORAGE_UNAVAILABLE", "governance revision version is invalid")
        return _RevisionState(revision, version)

    def _submission(self, submission_id: str, workspace_id: str) -> ApprovalSubmission | None:
        try:
            value = self._repository.get_approval_submission(submission_id, workspace_id)
        except Exception as exc:
            _raise_mapped(exc)
        if value is not None and (
            not isinstance(value, ApprovalSubmission)
            or value.submission_id != submission_id
            or value.workspace_id != workspace_id
        ):
            raise _error("FMEA_GOVERNANCE_APPROVAL_NOT_FOUND", "approval submission was not found")
        return value

    def _approval(self, approval_id: str, workspace_id: str) -> ApprovalDecision | None:
        try:
            value = self._repository.get_approval_decision(approval_id, workspace_id)
        except Exception as exc:
            _raise_mapped(exc)
        if value is not None and (not isinstance(value, ApprovalDecision) or value.approval_id != approval_id):
            raise _error("FMEA_GOVERNANCE_APPROVAL_NOT_FOUND", "approval decision was not found")
        return value

    def _approval_for_submission(self, submission_id: str, workspace_id: str) -> ApprovalDecision | None:
        try:
            value = self._repository.get_approval_decision_for_submission(submission_id, workspace_id)
        except Exception as exc:
            _raise_mapped(exc)
        if value is not None and (not isinstance(value, ApprovalDecision) or value.submission_id != submission_id):
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval decision state is invalid")
        return value

    def _approval_withdrawal(self, approval_id: str, workspace_id: str) -> ApprovalWithdrawalRecord | None:
        try:
            value = self._repository.get_approval_withdrawal(approval_id, workspace_id)
        except Exception as exc:
            _raise_mapped(exc)
        if value is not None and (not isinstance(value, ApprovalWithdrawalRecord) or value.approval_id != approval_id):
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval withdrawal state is invalid")
        return value

    def _lifecycle(self, publication_id: str, workspace_id: str) -> PublicationLifecycleView | None:
        try:
            value = self._repository.get_publication_lifecycle(publication_id, workspace_id)
        except Exception as exc:
            _raise_mapped(exc)
        if value is None:
            return None
        if (
            not isinstance(value, PublicationLifecycleView)
            or value.publication.publication_id != publication_id
            or value.publication.workspace_id != workspace_id
        ):
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication lifecycle is invalid")
        return value

    def _commit(
        self,
        commit: Callable[[object], object],
        prepared: object,
        *,
        fallback: str = "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE",
    ):
        try:
            return commit(prepared)
        except Exception as exc:
            _raise_mapped(exc, fallback)

    def _early_replay(
        self,
        kind: str,
        scope: IdempotencyScope,
        command: object,
        expected_type: type,
        *,
        fallback: str,
    ):
        try:
            result = self._repository.replay_governance_command(kind, scope, command)
        except Exception as exc:
            _raise_mapped(exc, fallback)
        if result is None:
            return None
        if type(result) is not expected_type or result.replayed is not True:
            raise _error(fallback, "governance command replay result is invalid")
        return result

    def _readiness_for(self, revision: FmeaRevision) -> PublicationReadinessReport:
        if self._readiness_policy is None:
            raise _error(
                "FMEA_GOVERNANCE_WORKSPACE_CONFIGURATION_INVALID",
                "readiness policy is not configured",
            )
        inputs = self._inputs(revision.analysis_id, revision.workspace_id)
        current_children: list[tuple[str, str]] = []
        current_children.extend((row.row_id, _content_hash(row)) for row in inputs.rows)
        current_children.extend((risk.assessment_id, _content_hash(risk)) for risk in inputs.risk_records)
        if inputs.propagation_graph_revision is not None:
            current_children.append((
                inputs.propagation_graph_revision.graph_revision_id,
                _content_hash(inputs.propagation_graph_revision),
            ))
        current_children.extend((pack.pack_id, pack.pack_hash) for pack in inputs.evidence_packs)
        artifacts = GovernanceArtifactSet(
            domain_pack=inputs.domain_pack,
            domain_pack_identity=inputs.domain_pack_identity,
            template_identities=inputs.template_identities,
            scoring_rule_identities=inputs.scoring_rule_identities,
            propagation_rule_identity=inputs.propagation_rule_identity,
        )
        context = PublicationReadinessContext(
            active_run_ids=inputs.active_run_ids,
            current_analysis_version=inputs.analysis.record_version,
            current_child_hashes=tuple(current_children),
            required_fields_accepted=all(row.review_status.value == "accepted" for row in inputs.rows),
            required_risk_confirmed=bool(inputs.risk_records)
            and all(risk.status.value == "confirmed" for risk in inputs.risk_records),
            propagation_confirmed=inputs.propagation_graph_revision is not None
            and inputs.propagation_graph_revision.status.value == "confirmed",
            required_evidence_present=bool(inputs.evidence_packs),
            acknowledgement_references=inputs.acknowledgement_references,
            authoritative_analysis=inputs.analysis,
            authoritative_artifacts=artifacts,
            governance_inputs=inputs,
        )
        expected_children = {row_id: child_hash for row_id, _, child_hash in revision.row_versions}
        expected_children.update({assessment_id: child_hash for assessment_id, _, child_hash in revision.risk_versions})
        if revision.propagation_graph_revision_id is not None and revision.propagation_graph_hash is not None:
            expected_children[revision.propagation_graph_revision_id] = revision.propagation_graph_hash
        expected_children.update(dict(revision.evidence_pack_hashes))
        current_children_map = dict(current_children)
        stale_children = tuple(
            sorted(
                child_id
                for child_id in set(expected_children) | set(current_children_map)
                if expected_children.get(child_id) != current_children_map.get(child_id)
            )
        )
        try:
            report = self._readiness_policy.evaluate(revision, context)
        except Exception as exc:
            _raise_mapped(exc, "FMEA_GOVERNANCE_NOT_READY")
        if not isinstance(report, PublicationReadinessReport):
            raise _error("FMEA_GOVERNANCE_NOT_READY", "governance readiness could not be evaluated")
        if stale_children:
            existing = {(issue.code, issue.source_id) for issue in report.issues}
            extra = tuple(
                ReadinessIssue(
                    code="STALE_CHILD_VERSION",
                    severity="blocking",
                    source_type="child",
                    source_id=child_id,
                    evidence_ids=(),
                    acknowledgement_decision_id=None,
                )
                for child_id in stale_children
                if ("STALE_CHILD_VERSION", child_id) not in existing
            )
            if extra:
                report = PublicationReadinessReport(
                    report.revision_id,
                    report.workspace_id,
                    report.analysis_id,
                    report.revision_hash,
                    report.target_record_version,
                    report.evidence_pack_ids,
                    False,
                    report.issues + extra,
                    tuple(sorted(set(report.blocking_codes) | {"STALE_CHILD_VERSION"})),
                    report.deterministic,
                )
        return report

    def assemble(self, command: AssembleRevisionCommand, actor: ActorContext) -> RevisionResult:
        self._authorize(actor, "reviewer", "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN")
        if not isinstance(command, AssembleRevisionCommand):
            raise _error("FMEA_GOVERNANCE_REVISION_STALE", "governance revision request is invalid")
        scope = self._scope(
            actor,
            _COMMANDS["assemble"],
            f"/fmea/analyses/{command.request.analysis_id}/revisions",
            command.idempotency_key,
        )
        replay = self._early_replay(
            "assemble",
            scope,
            command,
            RevisionResult,
            fallback="FMEA_GOVERNANCE_REVISION_STALE",
        )
        if replay is not None:
            return replay
        inputs = self._inputs(command.request.analysis_id, actor.workspace_id)
        if inputs.analysis.record_version != command.request.expected_analysis_version:
            raise _error("FMEA_GOVERNANCE_REVISION_STALE", "governance analysis version is stale")
        try:
            if self._assembler is None:
                raise ValueError("assembler is not configured")
            revision = self._assembler.assemble(command.request, inputs)
        except Exception as exc:
            _raise_mapped(exc, "FMEA_GOVERNANCE_REVISION_STALE")
        payload = canonical_governance_payload("revision.assemble", command, revision=revision)
        payload_hash = governance_payload_hash(payload)
        audit = self._audit(
            actor,
            scope,
            payload_hash,
            revision.revision_id,
            revision.analysis_id,
            "FMEA revision assembled",
            expected_record_version=command.request.expected_analysis_version,
            applied_record_version=1,
        )
        outbox = self._outbox(scope, payload, revision.revision_id, audit.occurred_at_server)
        prepared = PreparedRevision(
            scope,
            payload_hash,
            command,
            command.request.expected_analysis_version,
            revision,
            audit,
            outbox,
        )
        result = self._commit(
            self._repository.commit_revision,
            prepared,
            fallback="FMEA_GOVERNANCE_REVISION_STALE",
        )
        return result

    def readiness(self, revision_id: str, actor: ActorContext) -> PublicationReadinessReport:
        self._authorize_query(actor)
        if not isinstance(revision_id, str) or not revision_id.strip():
            raise _error("FMEA_GOVERNANCE_REVISION_STALE", "governance readiness request is invalid")
        revision_id = revision_id.strip()
        state = self._revision_state(revision_id, actor.workspace_id)
        if state is None:
            raise _error("FMEA_GOVERNANCE_REVISION_NOT_FOUND", "governance revision was not found")
        return self._readiness_for(state.revision)

    def submit_for_approval(self, command: SubmitApprovalCommand, actor: ActorContext) -> ApprovalSubmissionResult:
        self._authorize(actor, "reviewer", "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN")
        if not isinstance(command, SubmitApprovalCommand):
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval submission request is invalid")
        scope = self._scope(
            actor,
            _COMMANDS["submit"],
            f"/fmea/revisions/{command.revision_id}/approval-submissions",
            command.idempotency_key,
        )
        replay = self._early_replay(
            "submit",
            scope,
            command,
            ApprovalSubmissionResult,
            fallback="FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
        )
        if replay is not None:
            return replay
        state = self._revision_state(command.revision_id, actor.workspace_id)
        if state is None:
            raise _error("FMEA_GOVERNANCE_REVISION_NOT_FOUND", "governance revision was not found")
        if state.record_version != command.expected_revision_version:
            raise _error("FMEA_GOVERNANCE_VERSION_CONFLICT", "governance revision version is stale")
        if state.revision.revision_hash != command.revision_hash:
            raise _error("FMEA_GOVERNANCE_REVISION_STALE", "governance revision hash is stale")
        submission = ApprovalSubmission(
            self._stable_id("submission", scope),
            actor.workspace_id,
            command.revision_id,
            command.revision_hash,
            ApprovalStatus.PENDING,
            actor.actor_id,
            1,
            self._clock(),
        )
        payload = canonical_governance_payload("approval.submit", command, submission=submission)
        payload_hash = governance_payload_hash(payload)
        audit = self._audit(
            actor,
            scope,
            payload_hash,
            submission.submission_id,
            state.revision.analysis_id,
            "FMEA revision submitted for approval",
            expected_record_version=state.record_version,
            applied_record_version=1,
        )
        outbox = self._outbox(scope, payload, submission.submission_id, audit.occurred_at_server)
        prepared = PreparedApprovalSubmission(
            scope, payload_hash, command, state.record_version, submission, audit, outbox
        )
        result = self._commit(
            self._repository.commit_approval_submission,
            prepared,
            fallback="FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
        )
        return result

    def _decide(self, command: ApprovalCommand, actor: ActorContext, status: ApprovalStatus) -> ApprovalResult:
        self._authorize(actor, "approver", "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN")
        if not isinstance(command, ApprovalCommand):
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval decision request is invalid")
        scope = self._scope(
            actor,
            _COMMANDS["decide"],
            f"/fmea/approval-submissions/{command.submission_id}/decision",
            command.idempotency_key,
        )
        replay = self._early_replay(
            "approve" if status is ApprovalStatus.APPROVED else "reject",
            scope,
            command,
            ApprovalResult,
            fallback="FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
        )
        if replay is not None:
            return replay
        submission = self._submission(command.submission_id, actor.workspace_id)
        if submission is None:
            raise _error("FMEA_GOVERNANCE_APPROVAL_NOT_FOUND", "approval submission was not found")
        if self._approval_for_submission(submission.submission_id, actor.workspace_id) is not None:
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval submission already has a decision")
        state = self._revision_state(submission.revision_id, actor.workspace_id)
        if state is None:
            raise _error("FMEA_GOVERNANCE_REVISION_NOT_FOUND", "governance revision was not found")
        if command.revision_id != submission.revision_id or command.revision_hash != submission.revision_hash:
            raise _error("FMEA_GOVERNANCE_APPROVAL_STALE", "approval revision binding is stale")
        if state.revision.revision_hash != command.revision_hash:
            raise _error("FMEA_GOVERNANCE_APPROVAL_STALE", "approval revision binding is stale")
        if command.expected_submission_version != submission.record_version:
            raise _error("FMEA_GOVERNANCE_VERSION_CONFLICT", "approval submission version is stale")
        decision = ApprovalDecision(
            self._stable_id("approval", scope),
            submission.submission_id,
            submission.revision_id,
            submission.revision_hash,
            status,
            actor.actor_id,
            command.reason,
            submission.record_version + 1,
            self._clock(),
        )
        payload = canonical_governance_payload("approval.decide", command, submission=submission, decision=decision)
        payload_hash = governance_payload_hash(payload)
        audit = self._audit(
            actor,
            scope,
            payload_hash,
            decision.approval_id,
            state.revision.analysis_id,
            "FMEA revision approval decision recorded",
            decision_id=decision.approval_id,
            expected_record_version=submission.record_version,
            applied_record_version=decision.record_version,
        )
        outbox = self._outbox(scope, payload, decision.approval_id, audit.occurred_at_server)
        prepared = PreparedApproval(scope, payload_hash, command, submission, decision, audit, outbox)
        result = self._commit(
            self._repository.commit_approval,
            prepared,
            fallback="FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
        )
        return result

    def approve(self, command: ApprovalCommand, actor: ActorContext) -> ApprovalResult:
        return self._decide(command, actor, ApprovalStatus.APPROVED)

    def reject(self, command: ApprovalRejectionCommand, actor: ActorContext) -> ApprovalResult:
        if not isinstance(command, ApprovalRejectionCommand):
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval rejection request is invalid")
        return self._decide(command, actor, ApprovalStatus.REJECTED)

    def withdraw_approval(self, command: WithdrawApprovalCommand, actor: ActorContext) -> ApprovalWithdrawalResult:
        self._authorize(actor, "approver", "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN")
        if not isinstance(command, WithdrawApprovalCommand):
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval withdrawal request is invalid")
        scope = self._scope(
            actor,
            _COMMANDS["approval_withdraw"],
            f"/fmea/approvals/{command.approval_id}/withdrawal",
            command.idempotency_key,
        )
        replay = self._early_replay(
            "withdraw_approval",
            scope,
            command,
            ApprovalWithdrawalResult,
            fallback="FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
        )
        if replay is not None:
            return replay
        approval = self._approval(command.approval_id, actor.workspace_id)
        if approval is None:
            raise _error("FMEA_GOVERNANCE_APPROVAL_NOT_FOUND", "approval decision was not found")
        if approval.status is not ApprovalStatus.APPROVED:
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval is not withdrawable")
        if self._approval_withdrawal(approval.approval_id, actor.workspace_id) is not None:
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval has already been withdrawn")
        if command.revision_hash != approval.revision_hash:
            raise _error("FMEA_GOVERNANCE_APPROVAL_STALE", "approval revision binding is stale")
        if command.expected_approval_version != approval.record_version:
            raise _error("FMEA_GOVERNANCE_VERSION_CONFLICT", "approval version is stale")
        state = self._revision_state(approval.revision_id, actor.workspace_id)
        if state is None:
            raise _error("FMEA_GOVERNANCE_REVISION_NOT_FOUND", "governance revision was not found")
        withdrawal = ApprovalWithdrawalRecord(
            self._stable_id("approval-withdrawal", scope),
            approval.approval_id,
            approval.revision_id,
            approval.revision_hash,
            actor.actor_id,
            command.reason,
            self._clock(),
        )
        payload = canonical_governance_payload("approval.withdraw", command, approval=approval, withdrawal=withdrawal)
        payload_hash = governance_payload_hash(payload)
        audit = self._audit(
            actor,
            scope,
            payload_hash,
            withdrawal.withdrawal_id,
            state.revision.analysis_id,
            "FMEA approval withdrawn",
            decision_id=approval.approval_id,
            expected_record_version=approval.record_version,
            applied_record_version=approval.record_version,
        )
        outbox = self._outbox(scope, payload, withdrawal.withdrawal_id, audit.occurred_at_server)
        prepared = PreparedApprovalWithdrawal(scope, payload_hash, command, approval, withdrawal, audit, outbox)
        result = self._commit(
            self._repository.commit_approval_withdrawal,
            prepared,
            fallback="FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
        )
        return result

    def _snapshot(
        self,
        revision: FmeaRevision,
        approval: ApprovalDecision,
        publication_id: str,
        manifest_id: str,
        readiness: PublicationReadinessReport,
        created_at: str,
    ) -> NormalizedFmeaSnapshot:
        self._inputs(revision.analysis_id, revision.workspace_id)
        rows = tuple(
            {"row_id": row_id, "record_version": version, "row_hash": _export_hash(row_hash)}
            for row_id, version, row_hash in revision.row_versions
        )
        risks = tuple(
            {
                "assessment_id": assessment_id,
                "record_version": version,
                "assessment_hash": _export_hash(record_hash),
            }
            for assessment_id, version, record_hash in revision.risk_versions
        )
        propagation = (
            None
            if revision.propagation_graph_revision_id is None
            else {
                "graph_revision_id": revision.propagation_graph_revision_id,
                "graph_hash": _export_hash(revision.propagation_graph_hash or ""),
            }
        )
        evidence = tuple(
            {"pack_id": pack_id, "pack_hash": _export_hash(pack_hash)}
            for pack_id, pack_hash in revision.evidence_pack_hashes
        )

        def identity(value: tuple[str, str, str]) -> tuple[str, str, str]:
            return value[0], value[1], _export_hash(value[2])

        version_manifest = {
            "analysis_hash": _export_hash(revision.analysis_hash),
            "domain_pack_identity": identity(revision.domain_pack_identity),
            "template_identities": tuple(identity(item) for item in revision.template_identities),
            "scoring_rule_identities": tuple(identity(item) for item in revision.scoring_rule_identities),
            "propagation_rule_identity": (
                None if revision.propagation_rule_identity is None else identity(revision.propagation_rule_identity)
            ),
            "retrieval_provenance": {
                "requested_profile": revision.retrieval_provenance.requested_profile,
                "resolved_profile": revision.retrieval_provenance.resolved_profile,
                "evidence_types": revision.retrieval_provenance.evidence_types,
                "source_counts": revision.retrieval_provenance.source_counts,
                "warnings": revision.retrieval_provenance.warnings,
            },
        }
        source = NormalizedSnapshotInput(
            revision=revision,
            publication_id=publication_id,
            manifest_id=manifest_id,
            publication_revision_id=revision.revision_id,
            publication_revision_hash=revision.revision_hash,
            publication_workspace_id=revision.workspace_id,
            publication_analysis_id=revision.analysis_id,
            rows=rows,
            risk_records=risks,
            propagation=propagation,
            evidence_summary=evidence,
            decision_summary=(
                {
                    "decision_id": approval.approval_id,
                    "status": approval.status.value,
                    "revision_id": approval.revision_id,
                    "revision_hash": _export_hash(approval.revision_hash),
                },
            ),
            version_manifest=version_manifest,
            audit_summary={
                "approval_id": approval.approval_id,
                "approval_hash": _export_hash(canonical_hash(approval, prefixed=True)),
                "readiness_hash": _export_hash(canonical_hash(readiness, prefixed=True)),
            },
            created_at=created_at,
        )
        return build_normalized_snapshot(source)

    def publish(self, command: PublishCommand, actor: ActorContext) -> PublicationResult:
        self._authorize(actor, "publisher", "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN")
        if not isinstance(command, PublishCommand):
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication request is invalid")
        scope = self._scope(
            actor,
            _COMMANDS["publish"],
            f"/fmea/revisions/{command.revision_id}/publications",
            command.idempotency_key,
        )
        replay = self._early_replay(
            "publish",
            scope,
            command,
            PublicationResult,
            fallback="FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
        )
        if replay is not None:
            return replay
        state = self._revision_state(command.revision_id, actor.workspace_id)
        if state is None:
            raise _error("FMEA_GOVERNANCE_REVISION_NOT_FOUND", "governance revision was not found")
        if state.record_version != command.expected_revision_version:
            raise _error("FMEA_GOVERNANCE_VERSION_CONFLICT", "governance revision version is stale")
        if state.revision.revision_hash != command.revision_hash:
            raise _error("FMEA_GOVERNANCE_APPROVAL_STALE", "approval revision binding is stale")
        approval = self._approval(command.approval_id, actor.workspace_id)
        if approval is None:
            raise _error("FMEA_GOVERNANCE_APPROVAL_NOT_FOUND", "approval decision was not found")
        submission = self._submission(approval.submission_id, actor.workspace_id)
        if submission is None:
            raise _error("FMEA_GOVERNANCE_APPROVAL_NOT_FOUND", "approval submission was not found")
        current = self._approval_for_submission(submission.submission_id, actor.workspace_id)
        if current is None or current.approval_id != approval.approval_id:
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval decision is not current")
        if approval.status is not ApprovalStatus.APPROVED:
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "revision is not approved")
        if self._approval_withdrawal(approval.approval_id, actor.workspace_id) is not None:
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "approval has been withdrawn")
        try:
            validate_approval_binding(approval, state.revision)
        except Exception:
            raise _error("FMEA_GOVERNANCE_APPROVAL_STALE", "approval revision binding is stale") from None
        readiness = self._readiness_for(state.revision)
        if any(code == "ACTIVE_MUTATION_RUN" for code in readiness.blocking_codes):
            raise _error("FMEA_GOVERNANCE_ACTIVE_RUN", "an active governance run blocks publication")
        if not readiness.ready:
            raise _error("FMEA_GOVERNANCE_NOT_READY", "revision is not ready for publication")
        publication_id = self._stable_id("publication", scope)
        manifest_id = self._stable_id("manifest", scope)
        created_at = self._clock()
        snapshot = self._snapshot(state.revision, approval, publication_id, manifest_id, readiness, created_at)
        version_manifest = {
            "revision_hash": state.revision.revision_hash,
            "analysis_hash": state.revision.analysis_hash,
            "domain_pack_identity": state.revision.domain_pack_identity,
            "template_identities": state.revision.template_identities,
            "scoring_rule_identities": state.revision.scoring_rule_identities,
            "propagation_rule_identity": state.revision.propagation_rule_identity,
        }
        version_manifest_hash = canonical_hash(version_manifest, prefixed=True)
        try:
            previous_head = self._repository.get_current_publication_audit_head(actor.workspace_id)
        except Exception as exc:
            _raise_mapped(exc, "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID")
        if previous_head is not None:
            normalized_head = previous_head.removeprefix("sha256:") if isinstance(previous_head, str) else ""
            if len(normalized_head) != 64 or any(char not in "0123456789abcdef" for char in normalized_head):
                raise _error(
                    "FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
                    "publication audit predecessor is invalid",
                )
        manifest_hash = canonical_hash(
            {
                "manifest_id": manifest_id,
                "revision_id": state.revision.revision_id,
                "revision_hash": state.revision.revision_hash,
                "approval_id": approval.approval_id,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_hash": snapshot.snapshot_hash,
                "version_manifest_hash": version_manifest_hash,
                "previous_audit_chain_head": previous_head,
                "export_eligible": True,
            },
            prefixed=True,
        )
        manifest = PublicationManifest(
            manifest_id,
            state.revision.revision_id,
            state.revision.revision_hash,
            approval.approval_id,
            snapshot.snapshot_id,
            snapshot.snapshot_hash,
            version_manifest_hash,
            previous_head,
            True,
            manifest_hash,
            created_at,
        )
        audit_chain_head = canonical_hash(
            {
                "previous_audit_chain_head": previous_head,
                "revision_hash": state.revision.revision_hash,
                "approval_hash": canonical_hash(approval, prefixed=True),
                "snapshot_hash": snapshot.snapshot_hash,
                "manifest_hash": manifest.manifest_hash,
            },
            prefixed=True,
        )
        publication = PublishedRevision(
            publication_id,
            actor.workspace_id,
            state.revision.analysis_id,
            state.revision.revision_id,
            state.revision.revision_hash,
            approval.approval_id,
            manifest.manifest_id,
            manifest.manifest_hash,
            snapshot.snapshot_id,
            snapshot.snapshot_hash,
            audit_chain_head,
            actor.actor_id,
            1,
            created_at,
        )
        eligibility_id = self._stable_id("eligibility", scope)
        eligibility_body = {
            "eligibility_id": eligibility_id,
            "workspace_id": actor.workspace_id,
            "publication_id": publication.publication_id,
            "manifest_id": manifest.manifest_id,
            "eligible": True,
            "source_hashes": (
                ("manifest", manifest.manifest_hash),
                ("revision", state.revision.revision_hash),
                ("snapshot", snapshot.snapshot_hash),
            ),
        }
        from .governance_contracts import ExportEligibilityRecord

        eligibility = ExportEligibilityRecord(
            eligibility_id,
            actor.workspace_id,
            publication.publication_id,
            manifest.manifest_id,
            True,
            eligibility_body["source_hashes"],
            canonical_hash(eligibility_body, prefixed=True),
            created_at,
        )
        payload = canonical_governance_payload(
            "publication.publish",
            command,
            revision=state.revision,
            approval=approval,
            submission=submission,
            manifest=manifest,
            publication=publication,
            snapshot=snapshot,
            export_eligibility=eligibility,
        )
        payload_hash = governance_payload_hash(payload)
        audit = self._audit(
            actor,
            scope,
            payload_hash,
            publication.publication_id,
            state.revision.analysis_id,
            "FMEA revision published",
            decision_id=approval.approval_id,
            expected_record_version=state.record_version,
            applied_record_version=publication.record_version,
            after_hash=audit_chain_head,
        )
        outbox = self._outbox(scope, payload, publication.publication_id, audit.occurred_at_server)
        prepared = PreparedPublication(
            scope,
            payload_hash,
            command,
            state.record_version,
            state.revision,
            approval,
            submission,
            manifest,
            publication,
            snapshot,
            audit,
            outbox,
            eligibility,
        )
        result = self._commit(
            self._repository.commit_publication,
            prepared,
            fallback="FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
        )
        return result

    def withdraw_publication(
        self, command: WithdrawPublicationCommand, actor: ActorContext
    ) -> PublicationWithdrawalResult:
        self._authorize(actor, "publisher", "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN")
        if not isinstance(command, WithdrawPublicationCommand):
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication withdrawal request is invalid")
        scope = self._scope(
            actor,
            _COMMANDS["publication_withdraw"],
            f"/fmea/publications/{command.publication_id}/withdrawal",
            command.idempotency_key,
        )
        replay = self._early_replay(
            "withdraw_publication",
            scope,
            command,
            PublicationWithdrawalResult,
            fallback="FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
        )
        if replay is not None:
            return replay
        lifecycle = self._lifecycle(command.publication_id, actor.workspace_id)
        if lifecycle is None:
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication was not found")
        if lifecycle.effective_status is not RevisionPublicationStatus.PUBLISHED:
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication is not withdrawable")
        publication = lifecycle.publication
        if command.expected_publication_version != publication.record_version:
            raise _error("FMEA_GOVERNANCE_VERSION_CONFLICT", "publication version is stale")
        withdrawal = PublicationWithdrawalRecord(
            self._stable_id("publication-withdrawal", scope),
            publication.publication_id,
            command.replacement_publication_id,
            actor.actor_id,
            command.reason,
            self._clock(),
        )
        payload = canonical_governance_payload(
            "publication.withdraw", command, publication=publication, withdrawal=withdrawal
        )
        payload_hash = governance_payload_hash(payload)
        audit = self._audit(
            actor,
            scope,
            payload_hash,
            withdrawal.withdrawal_id,
            publication.analysis_id,
            "FMEA publication withdrawn",
            expected_record_version=publication.record_version,
            applied_record_version=publication.record_version,
        )
        outbox = self._outbox(scope, payload, withdrawal.withdrawal_id, audit.occurred_at_server)
        prepared = PreparedPublicationWithdrawal(scope, payload_hash, command, publication, withdrawal, audit, outbox)
        result = self._commit(
            self._repository.commit_publication_withdrawal,
            prepared,
            fallback="FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
        )
        return result

    def supersede(self, command: SupersedePublicationCommand, actor: ActorContext) -> SupersessionResult:
        self._authorize(actor, "publisher", "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN")
        if not isinstance(command, SupersedePublicationCommand):
            raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession request is invalid")
        scope = self._scope(
            actor,
            _COMMANDS["supersede"],
            f"/fmea/publications/{command.publication_id}/supersession",
            command.idempotency_key,
        )
        replay = self._early_replay(
            "supersede",
            scope,
            command,
            SupersessionResult,
            fallback="FMEA_GOVERNANCE_SUPERSESSION_INVALID",
        )
        if replay is not None:
            return replay
        old_lifecycle = self._lifecycle(command.publication_id, actor.workspace_id)
        replacement_lifecycle = self._lifecycle(command.replacement_publication_id, actor.workspace_id)
        if old_lifecycle is None or replacement_lifecycle is None:
            raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession publications were not found")
        if (
            old_lifecycle.effective_status is not RevisionPublicationStatus.PUBLISHED
            or replacement_lifecycle.withdrawal is not None
        ):
            raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession publications are not current")
        old = old_lifecycle.publication
        replacement = replacement_lifecycle.publication
        if old.record_version != command.expected_publication_version:
            raise _error("FMEA_GOVERNANCE_VERSION_CONFLICT", "old publication version is stale")
        if replacement.record_version != command.expected_replacement_version:
            raise _error("FMEA_GOVERNANCE_VERSION_CONFLICT", "replacement publication version is stale")
        old_state = self._revision_state(old.revision_id, actor.workspace_id)
        replacement_state = self._revision_state(replacement.revision_id, actor.workspace_id)
        if old_state is None or replacement_state is None:
            raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession revisions were not found")
        try:
            link = SupersessionRecord(
                self._stable_id("supersession", scope),
                old.publication_id,
                replacement.publication_id,
                actor.actor_id,
                command.reason,
                self._clock(),
            )
            validate_supersession_binding(
                link,
                old=old,
                replacement=replacement,
                old_revision=old_state.revision,
                replacement_revision=replacement_state.revision,
            )
        except Exception:
            raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession lineage is invalid") from None
        current_lifecycle = replacement_lifecycle
        seen: set[str] = set()
        for _depth in range(_MAX_SUPERSESSION_DEPTH):
            current = current_lifecycle.publication.publication_id
            if current == old.publication_id:
                raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession lineage is cyclic")
            if current in seen:
                raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession lineage is cyclic")
            if current_lifecycle.withdrawal is not None:
                raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession lineage is withdrawn")
            seen.add(current)
            next_link = current_lifecycle.supersession
            if next_link is None:
                break
            current_lifecycle = self._lifecycle(next_link.new_publication_id, actor.workspace_id)
            if current_lifecycle is None:
                raise _error(
                    "FMEA_GOVERNANCE_SUPERSESSION_INVALID",
                    "supersession lineage is incomplete",
                )
        else:
            raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession lineage is too deep")
        payload = canonical_governance_payload(
            "publication.supersede",
            command,
            old=old,
            replacement=replacement,
            old_revision=old_state.revision,
            replacement_revision=replacement_state.revision,
            supersession=link,
        )
        payload_hash = governance_payload_hash(payload)
        audit = self._audit(
            actor,
            scope,
            payload_hash,
            link.supersession_id,
            old.analysis_id,
            "FMEA publication superseded",
            expected_record_version=old.record_version,
            applied_record_version=old.record_version,
        )
        outbox = self._outbox(scope, payload, link.supersession_id, audit.occurred_at_server)
        prepared = PreparedSupersession(
            scope,
            payload_hash,
            command,
            old,
            replacement,
            old_state.revision,
            replacement_state.revision,
            link,
            audit,
            outbox,
        )
        result = self._commit(
            self._repository.commit_supersession,
            prepared,
            fallback="FMEA_GOVERNANCE_SUPERSESSION_INVALID",
        )
        return result

    def get_revision(self, revision_id: str, actor: ActorContext) -> FmeaRevision:
        self._authorize_query(actor)
        state = self._revision_state(revision_id, actor.workspace_id)
        if state is None:
            raise _error("FMEA_GOVERNANCE_REVISION_NOT_FOUND", "governance revision was not found")
        return state.revision

    def get_publication(self, publication_id: str, actor: ActorContext) -> PublicationLifecycleView:
        self._authorize_query(actor)
        lifecycle = self._lifecycle(publication_id, actor.workspace_id)
        if lifecycle is None:
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication was not found")
        return lifecycle

    def get_snapshot(self, publication_id: str, actor: ActorContext) -> NormalizedFmeaSnapshot:
        self._authorize_query(actor)
        try:
            value = self._repository.get_snapshot(publication_id, actor.workspace_id)
        except Exception as exc:
            _raise_mapped(exc)
        if (
            not isinstance(value, NormalizedFmeaSnapshot)
            or value.publication_id != publication_id
            or value.workspace_id != actor.workspace_id
        ):
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication snapshot was not found")
        return value

    def list_approval_events(self, query: GovernanceHistoryQuery, actor: ActorContext) -> GovernanceHistoryPage:
        self._authorize_query(actor)
        if (
            not isinstance(query, GovernanceHistoryQuery)
            or query.workspace_id != actor.workspace_id
            or query.resource_type != "revision"
        ):
            raise _error("FMEA_GOVERNANCE_CURSOR_INVALID", "governance history query is invalid")
        try:
            return self._repository.list_approval_events(query)
        except Exception as exc:
            _raise_mapped(exc)

    def list_publication_events(self, query: GovernanceHistoryQuery, actor: ActorContext) -> GovernanceHistoryPage:
        self._authorize_query(actor)
        if (
            not isinstance(query, GovernanceHistoryQuery)
            or query.workspace_id != actor.workspace_id
            or query.resource_type != "publication"
        ):
            raise _error("FMEA_GOVERNANCE_CURSOR_INVALID", "governance history query is invalid")
        try:
            return self._repository.list_publication_events(query)
        except Exception as exc:
            _raise_mapped(exc)


__all__ = ["GovernanceServiceError", "RevisionGovernanceService"]
