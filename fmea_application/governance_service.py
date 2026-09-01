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
    project_publication_lifecycle,
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
    for field_name in ("content_hash", "record_hash", "row_hash", "assessment_hash", "graph_hash"):
        candidate = getattr(value, field_name, None)
        if isinstance(candidate, str):
            normalized = candidate.removeprefix("sha256:")
            if len(normalized) == 64 and all(char in "0123456789abcdef" for char in normalized):
                return candidate
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
_GOVERNANCE_CODES = frozenset(
    {
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
    }
)
_ROLE_QUERY = frozenset({"reviewer", "approver", "publisher"})


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


def _map_repository_error(exc: Exception, fallback: str = "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE") -> GovernanceServiceError:
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
        self._revisions: dict[tuple[str, str], _RevisionState] = {}
        self._submissions: dict[tuple[str, str], ApprovalSubmission] = {}
        self._approvals: dict[tuple[str, str], ApprovalDecision] = {}
        self._approval_withdrawals: dict[tuple[str, str], ApprovalWithdrawalRecord] = {}
        self._publications: dict[tuple[str, str], PublishedRevision] = {}
        self._publication_withdrawals: dict[tuple[str, str], PublicationWithdrawalRecord] = {}
        self._supersessions: dict[tuple[str, str], SupersessionRecord] = {}
        self._snapshots: dict[tuple[str, str], NormalizedFmeaSnapshot] = {}
        self._audit_heads: dict[str, str] = {}

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
    def _stable_id(prefix: str, scope: IdempotencyScope, factory: IdFactory | None) -> str:
        seed = f"{prefix}:{scope.scope_key}"
        if factory is not None:
            return factory(f"{prefix}-{scope.key_hash.removeprefix('sha256:')[:24]}")
        return f"{prefix}-{uuid5(NAMESPACE_URL, seed)}"

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
        event_id = self._stable_id("audit", scope, self._id_factory)
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
    def _outbox(scope: IdempotencyScope, payload: Mapping[str, object], aggregate_id: str, created_at: str) -> OutboxEvent:
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
        if self._source is None or not callable(getattr(self._source, "load_inputs", None)):
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
        key = (workspace_id, revision_id)
        cached = self._revisions.get(key)
        try:
            revision = self._repository.get_revision(revision_id, workspace_id)
        except Exception as exc:
            _raise_mapped(exc)
        if revision is None:
            return cached
        if not isinstance(revision, FmeaRevision) or revision.workspace_id != workspace_id:
            raise _error("FMEA_GOVERNANCE_REVISION_NOT_FOUND", "governance revision was not found")
        version = self._revisions.get(key, _RevisionState(revision, 1)).record_version
        getter = getattr(self._repository, "get_revision_record_version", None)
        if callable(getter):
            try:
                persisted_version = getter(revision_id, workspace_id)
            except Exception as exc:
                _raise_mapped(exc)
            if persisted_version is None:
                return None
            version = persisted_version
        state = _RevisionState(revision, version)
        self._revisions[key] = state
        return state

    def _submission(self, submission_id: str, workspace_id: str) -> ApprovalSubmission | None:
        getter = getattr(self._repository, "get_approval_submission", None)
        value = None
        if callable(getter):
            try:
                value = getter(submission_id, workspace_id)
            except Exception as exc:
                _raise_mapped(exc)
        if value is None:
            value = self._submissions.get((workspace_id, submission_id))
        if value is not None:
            if not isinstance(value, ApprovalSubmission) or value.workspace_id != workspace_id:
                raise _error("FMEA_GOVERNANCE_APPROVAL_NOT_FOUND", "approval submission was not found")
            self._submissions[(workspace_id, submission_id)] = value
        return value

    def _approval(self, approval_id: str, workspace_id: str) -> ApprovalDecision | None:
        getter = getattr(self._repository, "get_approval_decision", None)
        value = None
        if callable(getter):
            try:
                value = getter(approval_id, workspace_id)
            except Exception as exc:
                _raise_mapped(exc)
        if value is None:
            value = self._approvals.get((workspace_id, approval_id))
        if value is not None:
            if not isinstance(value, ApprovalDecision):
                raise _error("FMEA_GOVERNANCE_APPROVAL_NOT_FOUND", "approval decision was not found")
            self._approvals[(workspace_id, approval_id)] = value
        return value

    def _approval_for_submission(self, submission_id: str, workspace_id: str) -> ApprovalDecision | None:
        getter = getattr(self._repository, "get_approval_decision_for_submission", None)
        value = None
        if callable(getter):
            try:
                value = getter(submission_id, workspace_id)
            except Exception as exc:
                _raise_mapped(exc)
        if value is None:
            value = next(
                (
                    decision
                    for (item_workspace, _), decision in self._approvals.items()
                    if item_workspace == workspace_id and decision.submission_id == submission_id
                ),
                None,
            )
        if value is not None:
            self._approvals[(workspace_id, value.approval_id)] = value
        return value

    def _approval_withdrawal(self, approval_id: str, workspace_id: str) -> ApprovalWithdrawalRecord | None:
        getter = getattr(self._repository, "get_approval_withdrawal", None)
        value = None
        if callable(getter):
            try:
                value = getter(approval_id, workspace_id)
            except Exception as exc:
                _raise_mapped(exc)
        if value is None:
            value = self._approval_withdrawals.get((workspace_id, approval_id))
        if value is not None:
            if not isinstance(value, ApprovalWithdrawalRecord) or value.approval_id != approval_id:
                raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval withdrawal state is invalid")
            self._approval_withdrawals[(workspace_id, approval_id)] = value
        return value

    def _lifecycle(self, publication_id: str, workspace_id: str):
        getter = getattr(self._repository, "get_publication_lifecycle", None)
        if callable(getter):
            try:
                value = getter(publication_id, workspace_id)
            except Exception as exc:
                _raise_mapped(exc)
            if value is not None:
                self._publications[(workspace_id, publication_id)] = value.publication
                if value.withdrawal is not None:
                    self._publication_withdrawals[(workspace_id, publication_id)] = value.withdrawal
                if value.supersession is not None:
                    self._supersessions[(workspace_id, publication_id)] = value.supersession
            return value
        publication = self._publications.get((workspace_id, publication_id))
        if publication is None:
            getter = getattr(self._repository, "get_publication", None)
            if callable(getter):
                try:
                    publication = getter(publication_id, workspace_id)
                except Exception as exc:
                    _raise_mapped(exc)
        if publication is None:
            return None
        return project_publication_lifecycle(
            publication,
            withdrawal=self._publication_withdrawals.get((workspace_id, publication_id)),
            supersession=self._supersessions.get((workspace_id, publication_id)),
        )

    def _commit(
        self,
        replay_name: str,
        commit_name: str,
        scope: IdempotencyScope,
        payload_hash: str,
        prepared: object,
        *,
        fallback: str = "FMEA_GOVERNANCE_STORAGE_UNAVAILABLE",
    ):
        try:
            replay = getattr(self._repository, replay_name)(scope, payload_hash)
            if replay is not None:
                return replay
            return getattr(self._repository, commit_name)(prepared)
        except Exception as exc:
            _raise_mapped(exc, fallback)

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
            current_children.append(
                (
                    inputs.propagation_graph_revision.graph_revision_id,
                    _content_hash(inputs.propagation_graph_revision),
                )
            )
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
            required_fields_accepted=all(
                getattr(row.review_status, "value", row.review_status) == "accepted" for row in inputs.rows
            ),
            required_risk_confirmed=bool(inputs.risk_records)
            and all(getattr(risk.status, "value", risk.status) == "confirmed" for risk in inputs.risk_records),
            propagation_confirmed=inputs.propagation_graph_revision is not None
            and getattr(inputs.propagation_graph_revision.status, "value", inputs.propagation_graph_revision.status)
            == "confirmed",
            required_evidence_present=bool(inputs.evidence_packs),
            acknowledgement_references=inputs.acknowledgement_references,
            authoritative_analysis=inputs.analysis,
            authoritative_artifacts=artifacts,
            governance_inputs=inputs,
        )
        expected_children = {
            row_id: child_hash for row_id, _, child_hash in revision.row_versions
        }
        expected_children.update(
            {assessment_id: child_hash for assessment_id, _, child_hash in revision.risk_versions}
        )
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
        inputs = self._inputs(command.request.analysis_id, actor.workspace_id)
        if inputs.analysis.record_version != command.request.expected_analysis_version:
            raise _error("FMEA_GOVERNANCE_REVISION_STALE", "governance analysis version is stale")
        try:
            if self._assembler is None:
                raise ValueError("assembler is not configured")
            revision = self._assembler.assemble(command.request, inputs)
        except Exception as exc:
            _raise_mapped(exc, "FMEA_GOVERNANCE_REVISION_STALE")
        scope = self._scope(
            actor,
            _COMMANDS["assemble"],
            f"/fmea/analyses/{revision.analysis_id}/revisions",
            command.idempotency_key,
        )
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
            "replay_revision", "commit_revision", scope, payload_hash, prepared,
            fallback="FMEA_GOVERNANCE_REVISION_STALE",
        )
        self._revisions[(actor.workspace_id, revision.revision_id)] = _RevisionState(
            revision, result.record_version
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
        state = self._revision_state(command.revision_id, actor.workspace_id)
        if state is None:
            raise _error("FMEA_GOVERNANCE_REVISION_NOT_FOUND", "governance revision was not found")
        if state.record_version != command.expected_revision_version:
            raise _error("FMEA_GOVERNANCE_VERSION_CONFLICT", "governance revision version is stale")
        if state.revision.revision_hash != command.revision_hash:
            raise _error("FMEA_GOVERNANCE_REVISION_STALE", "governance revision hash is stale")
        scope = self._scope(
            actor,
            _COMMANDS["submit"],
            f"/fmea/revisions/{command.revision_id}/approval-submissions",
            command.idempotency_key,
        )
        submission = ApprovalSubmission(
            self._stable_id("submission", scope, self._id_factory),
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
        prepared = PreparedApprovalSubmission(scope, payload_hash, command, state.record_version, submission, audit, outbox)
        result = self._commit(
            "replay_approval_submission", "commit_approval_submission", scope, payload_hash, prepared,
            fallback="FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
        )
        self._submissions[(actor.workspace_id, submission.submission_id)] = submission
        return result

    def _decide(self, command: ApprovalCommand, actor: ActorContext, status: ApprovalStatus) -> ApprovalResult:
        self._authorize(actor, "approver", "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN")
        if not isinstance(command, ApprovalCommand):
            raise _error("FMEA_GOVERNANCE_APPROVAL_STATE_INVALID", "approval decision request is invalid")
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
        scope = self._scope(
            actor,
            _COMMANDS["decide"],
            f"/fmea/approval-submissions/{submission.submission_id}/decision",
            command.idempotency_key,
        )
        decision = ApprovalDecision(
            self._stable_id("approval", scope, self._id_factory),
            submission.submission_id,
            submission.revision_id,
            submission.revision_hash,
            status,
            actor.actor_id,
            command.reason,
            submission.record_version + 1,
            self._clock(),
        )
        payload = canonical_governance_payload(
            "approval.decide", command, submission=submission, decision=decision
        )
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
            "replay_approval_decision", "commit_approval", scope, payload_hash, prepared,
            fallback="FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
        )
        self._approvals[(actor.workspace_id, decision.approval_id)] = decision
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
        scope = self._scope(
            actor,
            _COMMANDS["approval_withdraw"],
            f"/fmea/approvals/{approval.approval_id}/withdrawal",
            command.idempotency_key,
        )
        withdrawal = ApprovalWithdrawalRecord(
            self._stable_id("approval-withdrawal", scope, self._id_factory),
            approval.approval_id,
            approval.revision_id,
            approval.revision_hash,
            actor.actor_id,
            command.reason,
            self._clock(),
        )
        payload = canonical_governance_payload(
            "approval.withdraw", command, approval=approval, withdrawal=withdrawal
        )
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
            "replay_approval_withdrawal", "commit_approval_withdrawal", scope, payload_hash, prepared,
            fallback="FMEA_GOVERNANCE_APPROVAL_STATE_INVALID",
        )
        self._approval_withdrawals[(actor.workspace_id, approval.approval_id)] = withdrawal
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
        scope = self._scope(
            actor,
            _COMMANDS["publish"],
            f"/fmea/revisions/{command.revision_id}/publications",
            command.idempotency_key,
        )
        publication_id = self._stable_id("publication", scope, self._id_factory)
        manifest_id = self._stable_id("manifest", scope, self._id_factory)
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
        previous_head = self._audit_heads.get(actor.workspace_id)
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
        eligibility_id = self._stable_id("eligibility", scope, self._id_factory)
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
            "replay_publication", "commit_publication", scope, payload_hash, prepared,
            fallback="FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
        )
        self._publications[(actor.workspace_id, publication.publication_id)] = publication
        self._snapshots[(actor.workspace_id, publication.publication_id)] = snapshot
        self._audit_heads[actor.workspace_id] = audit_chain_head
        return result

    def withdraw_publication(self, command: WithdrawPublicationCommand, actor: ActorContext) -> PublicationWithdrawalResult:
        self._authorize(actor, "publisher", "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN")
        if not isinstance(command, WithdrawPublicationCommand):
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication withdrawal request is invalid")
        lifecycle = self._lifecycle(command.publication_id, actor.workspace_id)
        if lifecycle is None:
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication was not found")
        if lifecycle.effective_status is not RevisionPublicationStatus.PUBLISHED:
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication is not withdrawable")
        publication = lifecycle.publication
        if command.expected_publication_version != publication.record_version:
            raise _error("FMEA_GOVERNANCE_VERSION_CONFLICT", "publication version is stale")
        scope = self._scope(
            actor,
            _COMMANDS["publication_withdraw"],
            f"/fmea/publications/{publication.publication_id}/withdrawal",
            command.idempotency_key,
        )
        withdrawal = PublicationWithdrawalRecord(
            self._stable_id("publication-withdrawal", scope, self._id_factory),
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
            "replay_publication_withdrawal", "commit_publication_withdrawal", scope, payload_hash, prepared,
            fallback="FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID",
        )
        self._publication_withdrawals[(actor.workspace_id, publication.publication_id)] = withdrawal
        return result

    def supersede(self, command: SupersedePublicationCommand, actor: ActorContext) -> SupersessionResult:
        self._authorize(actor, "publisher", "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN")
        if not isinstance(command, SupersedePublicationCommand):
            raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession request is invalid")
        old_lifecycle = self._lifecycle(command.publication_id, actor.workspace_id)
        replacement_lifecycle = self._lifecycle(command.replacement_publication_id, actor.workspace_id)
        if old_lifecycle is None or replacement_lifecycle is None:
            raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession publications were not found")
        if (
            old_lifecycle.effective_status is not RevisionPublicationStatus.PUBLISHED
            or replacement_lifecycle.effective_status is not RevisionPublicationStatus.PUBLISHED
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
            scope = self._scope(
                actor,
                _COMMANDS["supersede"],
                f"/fmea/publications/{old.publication_id}/supersession",
                command.idempotency_key,
            )
            link = SupersessionRecord(
                self._stable_id("supersession", scope, self._id_factory),
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
        current = replacement.publication_id
        seen: set[str] = set()
        while current in seen:
            raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession lineage is cyclic")
        while True:
            if current == old.publication_id:
                raise _error("FMEA_GOVERNANCE_SUPERSESSION_INVALID", "supersession lineage is cyclic")
            seen.add(current)
            next_link = self._supersessions.get((actor.workspace_id, current))
            if next_link is None:
                break
            current = next_link.new_publication_id
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
            "replay_supersession", "commit_supersession", scope, payload_hash, prepared,
            fallback="FMEA_GOVERNANCE_SUPERSESSION_INVALID",
        )
        self._supersessions[(actor.workspace_id, old.publication_id)] = link
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
        getter = getattr(self._repository, "get_snapshot", None)
        value = None
        if callable(getter):
            try:
                value = getter(publication_id, actor.workspace_id)
            except Exception as exc:
                _raise_mapped(exc)
        if value is None:
            value = self._snapshots.get((actor.workspace_id, publication_id))
        if not isinstance(value, NormalizedFmeaSnapshot):
            raise _error("FMEA_GOVERNANCE_PUBLICATION_STATE_INVALID", "publication snapshot was not found")
        self._snapshots[(actor.workspace_id, publication_id)] = value
        return value

    def list_approval_events(self, query: GovernanceHistoryQuery, actor: ActorContext) -> GovernanceHistoryPage:
        self._authorize_query(actor)
        if not isinstance(query, GovernanceHistoryQuery) or query.workspace_id != actor.workspace_id or query.resource_type != "revision":
            raise _error("FMEA_GOVERNANCE_CURSOR_INVALID", "governance history query is invalid")
        try:
            return self._repository.list_approval_events(query)
        except Exception as exc:
            _raise_mapped(exc)

    def list_publication_events(self, query: GovernanceHistoryQuery, actor: ActorContext) -> GovernanceHistoryPage:
        self._authorize_query(actor)
        if not isinstance(query, GovernanceHistoryQuery) or query.workspace_id != actor.workspace_id or query.resource_type != "publication":
            raise _error("FMEA_GOVERNANCE_CURSOR_INVALID", "governance history query is invalid")
        try:
            return self._repository.list_publication_events(query)
        except Exception as exc:
            _raise_mapped(exc)


__all__ = ["GovernanceServiceError", "RevisionGovernanceService"]
