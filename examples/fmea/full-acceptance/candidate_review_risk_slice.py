"""Connected candidate -> review -> risk evidence slice for Task 8.

This module is deliberately loadable by file path.  It owns no verifier or
full-acceptance manifest semantics; it only records the lifecycle that it
actually executes against one SQLite database.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.governance import canonical_hash, canonical_json_bytes
from core_domain.fmea.scoring import RiskAssessmentRecord
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet
from core_domain.query_contracts import (
    CitationType,
    EvidenceSelectionProfile,
    QueryRequest,
    citation_type_for_source_type,
    selected_citation_types,
)
from fmea_application.assistance_contracts import AssistanceKind, AssistanceSuggestion
from fmea_application.review_contracts import (
    EDITABLE_REVIEW_FIELDS,
    ActorContext,
    FieldFinding,
    ReviewAction,
    ReviewCandidateBundle,
    ReviewDecisionCommand,
    ReviewJudgement,
    ReviewModelManifest,
    ReviewReasonCode,
    ReviewSourceSnapshot,
    ReviewSuggestionDraft,
    StartReviewSuggestionCommand,
    idempotency_key_hash,
)
from fmea_application.review_projection import build_review_context
from fmea_application.review_service import ReviewService
from fmea_application.risk_contracts import ConfirmRiskCommand, StartRiskProposalCommand, risk_context_hash
from fmea_application.risk_service import RiskAssessmentService
from fmea_infrastructure.assistance_repository_sqlite import SqliteAssistanceRepository
from fmea_infrastructure.domain_pack_registry import (
    FileDomainPackRegistry,
    FileScoringRuleRegistry,
    load_domain_pack_manifest,
    load_scoring_rule_pack,
)
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository
from fmea_infrastructure.risk_repository_sqlite import SqliteRiskRepository
from fmea_infrastructure.sqlite_codec import decode_audit_event

_REPO_ROOT = Path(__file__).resolve().parents[3]
_UTC = "2026-09-04T00:00:00Z"
_WORKSPACE_ID = "task8-fuel-workspace"
_CASE_ID = "fuel-combustion"
_ROW_ID = "fuel-row-1"
_PACK_ID = "fuel-evidence-1"
_EVIDENCE_ID = "fuel-evidence-ref-1"
_DOMAIN_SOURCE_PATH = _REPO_ROOT / "domain_packs" / "fuel-combustion" / "manifest.yaml"
_RULE_SOURCE_PATH = _REPO_ROOT / "domain_packs" / "fuel-combustion" / "scoring" / "sod-rpn-1.0.0.yaml"


class _InlineReviewExecutor:
    def submit(self, _run_id: str, operation: Any) -> None:
        operation()

    def close(self) -> None:
        return None


class _DeterministicCandidateGenerator:
    """A bounded fake at the candidate-generation gateway only."""

    def generate(self) -> ReviewCandidateBundle:
        versions = VersionSet(
            schema_id="graphrag.fmea.v1",
            data_version="task8-data-1",
            graph_version="task8-graph-1",
            evidence_pack_version="task8-evidence-1",
            profile_version="task8-profile-1",
            template_version="1.0.0",
            scoring_version="1.0.0",
            prompt_version="task8-prompt-1",
            model_version="task8-model-1",
            input_snapshot_hash="1" * 64,
        )
        quote = (
            "Synthetic acceptance fixture, not engineering advice. Fuel filter blockage from particulate accumulation "
            "causes flow restriction and low fuel pressure at burner. The pressure alarm is observed by a pressure "
            "transmitter; low-pressure trip logic is a barrier. The recommended fixture action is inspect filter. "
            "The example reviewer assigns severity 8, occurrence 3, detection 4. In the fixture topology, "
            "fuel_filter supplies fuel_manifold and restriction reduces downstream fuel pressure."
        )
        normalized_quote = " ".join(quote.split())
        evidence_hash = sha256(json.dumps({
            "source_type": "primary_document", "document_id": "fuel-doc-1", "document_version": "fuel-doc-v1",
            "locator": "page:1#span:1", "normalized_quote": normalized_quote,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        evidence_ref = EvidenceRef(
            evidence_id=_EVIDENCE_ID,
            workspace_id=_WORKSPACE_ID,
            document_id="fuel-doc-1",
            document_version="fuel-doc-v1",
            content_hash=sha256(normalized_quote.encode("utf-8")).hexdigest(),
            locator="page:1#span:1",
            quote=quote,
            normalized_quote=normalized_quote,
            evidence_hash=evidence_hash,
            acl_scope=("engineering",),
            source_type="primary_document",
            source_trust="reviewed",
            is_primary=True,
            created_at=_UTC,
            expires_at=None,
        )
        selection = QueryRequest(query="fuel filter failure and controls", workspace_id=_WORKSPACE_ID,
            evidence_only=True, evidence_profile=EvidenceSelectionProfile.RAG_ONLY)
        allowed_types = selected_citation_types(selection)
        selected_refs = tuple(ref for ref in (evidence_ref,) if citation_type_for_source_type(ref.source_type) in allowed_types)
        pack = EvidencePack.build(
            pack_id=_PACK_ID,
            workspace_id=_WORKSPACE_ID,
            acl_scope=("engineering",),
            versions=versions,
            refs=selected_refs,
            created_at=_UTC,
            expires_at=None,
        )
        analysis = FmeaAnalysis(
            analysis_id="fuel-analysis-1",
            project_id="task8-project-1",
            analysis_type="system_fmea",
            lifecycle_stage="draft",
            scope="fuel delivery to combustor interface",
            system_boundary="fuel skid to burner manifold",
            exclusions=("plant electrical distribution",),
            equipment_configuration="fuel-config-1",
            control_software_version="control-1",
            fuel_type="natural_gas",
            operating_modes=("startup", "steady_state"),
            assumptions=("pressure transmitter is calibrated",),
            limitations=("no transient test data",),
            unanalysed_parts=("upstream pipeline",),
            versions=versions,
            owner_actor_id="fuel-analyst",
            reviewer_actor_ids=("fuel-reviewer",),
            approver_actor_id=None,
            approved_at=None,
            parent_revision_id=None,
            current_revision_id=None,
        )
        field_evidence = tuple((name, (_EVIDENCE_ID,)) for name in sorted(EDITABLE_REVIEW_FIELDS))
        field_support = tuple(
            (name, EvidenceSupportStatus.SUPPORTED) for name in sorted(EDITABLE_REVIEW_FIELDS)
        )
        row = FmeaRow(
            row_id=_ROW_ID,
            analysis_id=analysis.analysis_id,
            evidence_pack_id=pack.pack_id,
            item_id="fuel-filter-1",
            function_id="fuel-filter-function",
            failure_mode="fuel filter blockage",
            causes=("particulate accumulation",),
            mechanisms=("flow restriction",),
            effects=("low fuel pressure at burner",),
            symptoms=("pressure alarm",),
            controls=("pressure transmitter",),
            barriers=("low-pressure trip logic",),
            actions=("inspect filter",),
            risk_assessment=None,
            field_evidence=field_evidence,
            field_support=field_support,
            claim_status=ClaimStatus.KNOWN,
            review_status=ReviewStatus.SUGGESTED,
            publication_status=PublicationStatus.UNPUBLISHED,
        )
        source = ReviewSourceSnapshot.build(
            row_id=row.row_id,
            source_record_version=row.record_version,
            candidate_id="fuel-candidate-1",
            item_label="Fuel filter",
            function_label="Maintain fuel pressure",
            template_id="fmea-row-review",
            template_version="1.0.0",
            profile_id="fuel-review-profile",
            profile_version="1.0.0",
            generation_run_id="candidate-generation-1",
            requested_evidence_profile=EvidenceSelectionProfile.RAG_ONLY,
            resolved_evidence_profile=EvidenceSelectionProfile.RAG_ONLY,
            evidence_types=(CitationType.TEXT,),
            trace_id="candidate-trace-1",
            retrieval_warnings=(),
            retrieval_incomplete=False,
            field_claim_statuses=tuple(
                (name, ClaimStatus.KNOWN) for name in sorted(EDITABLE_REVIEW_FIELDS)
            ),
        )
        return ReviewCandidateBundle(
            analysis=analysis,
            evidence_pack=pack,
            rows=(row,),
            source_snapshots=(source,),
        )


class _DeterministicReviewSuggestionGenerator:
    """A deterministic fake at the review suggestion generation gateway."""

    def generate(self, _request: Any) -> tuple[ReviewSuggestionDraft, ReviewModelManifest]:
        return (
            ReviewSuggestionDraft(
                recommended_action=ReviewAction.ACCEPT,
                field_findings=(
                    FieldFinding(
                        target_field="failure_mode",
                        judgement=ReviewJudgement.SUPPORTED,
                        recommended_claim_status=ClaimStatus.KNOWN,
                        evidence_ids=(_EVIDENCE_ID,),
                        rationale="The bounded source supports the failure mode.",
                    ),
                ),
                proposed_edits=(),
                evidence_requests=(),
                missing_evidence=(),
                conflicts=(),
                rationale="The candidate is supported by the persisted evidence pack.",
            ),
            ReviewModelManifest(
                provider="task8-deterministic",
                model="task8-review-fake",
                template_id="fmea-row-review",
                template_version="1.0.0",
                prompt_hash="sha256:" + "4" * 64,
            ),
        )


class _PersistedReviewContextProvider:
    """Read the accepted review context from the real SQLite repository."""

    def __init__(self, repository: SqliteFmeaRepository) -> None:
        self._repository = repository

    def get_context(self, row_id: str, actor: ActorContext):
        row = self._repository.get_row(row_id, actor.workspace_id)
        if row is None:
            raise AssertionError("risk context row was not persisted")  # noqa: TRY003 - bounded harness invariant
        pack = self._repository.get_evidence_pack(row.evidence_pack_id, actor.workspace_id)
        source = self._repository.get_review_source(row_id, actor.workspace_id)
        if pack is None or source is None:
            raise AssertionError("risk context dependencies were not persisted")  # noqa: TRY003 - bounded harness invariant
        return build_review_context(
            row=row,
            source=source,
            pack=pack,
            suggestions=self._repository.list_suggestions(row_id, actor.workspace_id),
            decisions=self._repository.list_decisions(row_id, actor.workspace_id),
        )


class _DeterministicRiskSuggestionGenerator:
    """A deterministic fake at the risk proposal generation gateway."""

    def generate(self, request: Any) -> AssistanceSuggestion[object]:
        dimensions = tuple(
            {
                "name": name,
                "value": value,
                "evidence_ids": [_EVIDENCE_ID],
                "reason": f"Bounded evidence supports {name}={value}.",
                "uncertainty": "bounded-demo-input",
            }
            for name, value in (("severity", 8), ("occurrence", 3), ("detection", 4))
        )
        return AssistanceSuggestion(
            suggestion_id="risk-suggestion-fuel-1",
            kind=AssistanceKind.SCORE_RECOMMENDATION,
            workspace_id=_WORKSPACE_ID,
            target_type="fmea_row",
            target_id=request.context.row.row_id,
            target_record_version=request.context.row.record_version,
            evidence_pack_ids=(request.evidence_pack.pack_id,),
            payload={
                "dimensions": dimensions,
                "reason": "Deterministic bounded risk proposal.",
                "uncertainty": "bounded-demo-input",
                "binding": {
                    "operating_context_hash": risk_context_hash(request.context),
                    "evidence_pack_hash": request.evidence_pack.pack_hash.removeprefix("sha256:"),
                    "model_template_id": "fmea-risk-proposal",
                    "model_template_version": "1.0.0",
                },
            },
            evidence_ids=(_EVIDENCE_ID,),
            model_hash="sha256:" + "5" * 64,
            prompt_hash="sha256:" + "6" * 64,
            run_id=request.run_id,
            trace_id="risk-trace-fuel-1",
            domain_pack_id=request.domain_pack.pack_id,
            domain_pack_version=request.domain_pack.version,
            template_id=request.template_id,
            template_version=request.template_version,
            rule_pack_id=request.rule_pack.rule_pack_id,
            rule_pack_version=request.rule_pack.version,
            created_at=_UTC,
        )


def _public(value: object) -> object:
    """Serialize a native DTO with the canonical contract projection."""

    return json.loads(canonical_json_bytes(value).decode("utf-8"))


def _hash_json(value: object) -> str:
    return canonical_hash(value, prefixed=True)


def _audit_events(database_path: Path) -> tuple[object, ...]:
    with closing(sqlite3.connect(database_path)) as connection:
        rows = connection.execute(
            "SELECT event_json FROM audit_events WHERE workspace_id=? ORDER BY rowid",
            (_WORKSPACE_ID,),
        ).fetchall()
    return tuple(decode_audit_event(row[0]) for row in rows)


def _event_counts(database_path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(database_path)) as connection:
        audit_count = connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
        outbox_count = connection.execute("SELECT COUNT(*) FROM fmea_outbox_events").fetchone()[0]
    return {"audit_events": int(audit_count), "outbox_events": int(outbox_count)}


def _step(
    *,
    step_id: str,
    command: str,
    actor: ActorContext,
    request_id: str,
    request_hash: str,
    idempotency_key: str,
    before: dict[str, object],
    after: dict[str, object],
    result_ids: dict[str, str],
) -> dict[str, object]:
    return {
        "step_id": step_id,
        "command": command,
        "actor_id": actor.actor_id,
        "actor_type": actor.actor_type.value,
        "request_identity": {
            "request_id": request_id,
            "request_hash": request_hash,
            "idempotency_key_hash": idempotency_key_hash(idempotency_key),
        },
        "before": before,
        "after": after,
        "result_ids": result_ids,
    }


@dataclass(frozen=True, slots=True)
class CandidateReviewRiskRun:
    evidence: dict[str, object]
    analysis: FmeaAnalysis
    row: FmeaRow
    assessment: RiskAssessmentRecord
    evidence_pack: EvidencePack

    def write_evidence(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.evidence, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return output


def run_candidate_review_risk(work_dir: str | Path) -> CandidateReviewRiskRun:
    """Run one connected fuel case against real SQLite and immutable registries."""

    root = Path(work_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    database_path = root / "fmea.sqlite3"
    registry_root = root / "immutable-registries"
    domain_source = _DOMAIN_SOURCE_PATH.read_bytes()
    rule_source = _RULE_SOURCE_PATH.read_bytes()
    domain_pack = load_domain_pack_manifest(domain_source)
    rule_pack = load_scoring_rule_pack(rule_source)
    domain_registry = FileDomainPackRegistry(registry_root / "domain")
    scoring_registry = FileScoringRuleRegistry(registry_root / "scoring")
    domain_registry.register(domain_pack, domain_source)
    scoring_registry.register(rule_pack, rule_source)

    review_repository = SqliteFmeaRepository(database_path)
    review_repository.initialize()
    assistance_repository = SqliteAssistanceRepository(database_path)
    assistance_repository.initialize()
    risk_repository = SqliteRiskRepository(database_path)
    risk_repository.initialize()
    risk_repository.register_pack_snapshots(
        _WORKSPACE_ID,
        domain_pack,
        domain_source,
        rule_pack,
        rule_source,
        _UTC,
    )

    id_counts: dict[str, int] = {}

    def id_factory(prefix: str) -> str:
        id_counts[prefix] = id_counts.get(prefix, 0) + 1
        return f"{prefix}-{id_counts[prefix]}"

    candidate_actor = ActorContext(
        "fuel-candidate-generator", ActorType.SYSTEM, frozenset(), _WORKSPACE_ID
    )
    analyst = ActorContext("fuel-analyst", ActorType.HUMAN, frozenset({"analyst"}), _WORKSPACE_ID)
    reviewer = ActorContext("fuel-reviewer", ActorType.HUMAN, frozenset({"reviewer"}), _WORKSPACE_ID)
    risk_model = ActorContext("fuel-risk-model", ActorType.MODEL, frozenset(), _WORKSPACE_ID)
    risk_reviewer = ActorContext(
        "fuel-risk-reviewer", ActorType.HUMAN, frozenset({"risk_reviewer"}), _WORKSPACE_ID
    )

    review_service = ReviewService(
        review_repository,
        _DeterministicReviewSuggestionGenerator(),
        _InlineReviewExecutor(),
        clock=lambda: _UTC,
        id_factory=id_factory,
    )
    risk_service = RiskAssessmentService(
        risk_repository,
        assistance_repository=assistance_repository,
        domain_pack_registry=domain_registry,
        scoring_rule_registry=scoring_registry,
        generator=_DeterministicRiskSuggestionGenerator(),
        context_provider=_PersistedReviewContextProvider(review_repository),
        clock=lambda: _UTC,
    )

    steps: list[dict[str, object]] = []
    candidate_bundle = _DeterministicCandidateGenerator().generate()
    candidate = candidate_bundle.rows[0]
    steps.append(
        _step(
            step_id="step-01",
            command="candidate.generate",
            actor=candidate_actor,
            request_id="candidate-request-1",
            request_hash=_hash_json(candidate_bundle),
            idempotency_key="00000000-0000-4000-8000-000000000001",
            before={"candidate_count": 0},
            after={"candidate_count": 1},
            result_ids={"candidate_id": candidate_bundle.source_snapshots[0].candidate_id, "row_id": candidate.row_id},
        )
    )
    persisted_rows = review_service.persist_generated_candidates(candidate_bundle, candidate_actor)
    persisted_row = review_repository.get_row(_ROW_ID, _WORKSPACE_ID)
    if persisted_row is None or not persisted_rows:
        raise AssertionError("candidate was not persisted")  # noqa: TRY003 - bounded harness invariant
    steps.append(
        _step(
            step_id="step-02",
            command="review.candidates.persist",
            actor=candidate_actor,
            request_id="candidate-persist-request-1",
            request_hash=_hash_json(persisted_rows),
            idempotency_key="00000000-0000-4000-8000-000000000002",
            before={"row_count": 0},
            after={"row_count": 1, "record_version": persisted_row.record_version},
            result_ids={"row_id": persisted_row.row_id, "analysis_id": persisted_row.analysis_id},
        )
    )

    start_command = StartReviewSuggestionCommand(
        row_id=_ROW_ID,
        expected_record_version=1,
        idempotency_key="00000000-0000-4000-8000-000000000003",
        review_policy="default",
        focus_fields=(),
    )
    queued_run = review_service.start_suggestion(start_command, analyst)
    review_run = review_service.get_suggestion_run(queued_run.run_id, analyst)
    suggestions = review_service.list_suggestions(_ROW_ID, analyst)
    if review_run.suggestion_id is None or not suggestions:
        raise AssertionError("review suggestion did not complete")  # noqa: TRY003 - bounded harness invariant
    suggestion = suggestions[-1]
    steps.append(
        _step(
            step_id="step-03",
            command="review.suggestion.start",
            actor=analyst,
            request_id=review_run.request_id,
            request_hash=_hash_json(start_command),
            idempotency_key=start_command.idempotency_key,
            before={"row_record_version": 1},
            after={"run_status": review_run.status.value, "suggestion_id": suggestion.suggestion_id},
            result_ids={"run_id": review_run.run_id, "suggestion_id": suggestion.suggestion_id},
        )
    )

    decision_command = ReviewDecisionCommand(
        row_id=_ROW_ID,
        expected_record_version=1,
        idempotency_key="00000000-0000-4000-8000-000000000004",
        action=ReviewAction.ACCEPT,
        suggestion_id=suggestion.suggestion_id,
        reason_code=ReviewReasonCode.ACCEPT_AS_IS,
        reason="Reviewer accepts the evidence-bound candidate.",
        edits=(),
        evidence_requests=(),
        unresolved_acknowledgements=(),
    )
    decision_result = review_service.submit_decision(decision_command, reviewer)
    origin_source = review_repository.get_review_source(_ROW_ID, _WORKSPACE_ID)
    if origin_source is None or origin_source.source_record_version != 1:
        raise AssertionError("review origin source snapshot version changed unexpectedly")  # noqa: TRY003 - bounded harness invariant
    steps.append(
        _step(
            step_id="step-04",
            command="review.decision",
            actor=reviewer,
            request_id=decision_result.request_id,
            request_hash=_hash_json(decision_command),
            idempotency_key=decision_command.idempotency_key,
            before={"row_record_version": decision_result.previous_record_version},
            after={
                "row_record_version": decision_result.record_version,
                "review_status": decision_result.review_status.value,
                "origin_source_record_version": origin_source.source_record_version,
            },
            result_ids={"decision_id": decision_result.decision_id, "audit_event_id": decision_result.audit_event_id, "row_id": decision_result.row.row_id},
        )
    )
    decision_replay_before = _event_counts(database_path)
    decision_replay = review_service.submit_decision(decision_command, reviewer)
    decision_replay_after = _event_counts(database_path)

    risk_propose_command = StartRiskProposalCommand(
        row_id=_ROW_ID,
        expected_record_version=2,
        evidence_pack_id=_PACK_ID,
        domain_pack_id=domain_pack.pack_id,
        domain_pack_version=domain_pack.version,
        template_id="fuel-combustion-fmea",
        template_version="1.0.0",
        rule_pack_id=rule_pack.rule_pack_id,
        rule_pack_version=rule_pack.version,
        idempotency_key="00000000-0000-4000-8000-000000000005",
    )
    current_row = review_repository.get_row(_ROW_ID, _WORKSPACE_ID)
    if current_row is None:
        raise AssertionError("reviewed candidate disappeared before risk proposal")  # noqa: TRY003 - bounded harness invariant
    proposed_risk = risk_service.propose(risk_propose_command, risk_model)
    if proposed_risk.proposal_id is None:
        raise AssertionError("risk proposal did not return a proposal ID")  # noqa: TRY003 - bounded harness invariant
    steps.append(
        _step(
            step_id="step-05",
            command="fmea.risk.propose",
            actor=risk_model,
            request_id=proposed_risk.assistance_suggestion_id or proposed_risk.assessment_id,
            request_hash=_hash_json(risk_propose_command),
            idempotency_key=risk_propose_command.idempotency_key,
            before={"row_record_version": 2, "risk_status": "absent"},
            after={"risk_status": proposed_risk.status.value, "assessment_record_version": proposed_risk.record_version},
            result_ids={"assessment_id": proposed_risk.assessment_id, "proposal_id": proposed_risk.proposal_id},
        )
    )
    confirm_command = ConfirmRiskCommand(
        row_id=_ROW_ID,
        proposal_id=proposed_risk.proposal_id,
        expected_assessment_version=1,
        idempotency_key="00000000-0000-4000-8000-000000000006",
    )
    confirmed_risk = risk_service.confirm(confirm_command, risk_reviewer)
    steps.append(
        _step(
            step_id="step-06",
            command="fmea.risk.confirm",
            actor=risk_reviewer,
            request_id=confirmed_risk.decision_id,
            request_hash=_hash_json(confirm_command),
            idempotency_key=confirm_command.idempotency_key,
            before={"assessment_record_version": 1, "risk_status": "proposed"},
            after={"assessment_record_version": confirmed_risk.assessment.record_version, "risk_status": confirmed_risk.assessment.status.value},
            result_ids={"assessment_id": confirmed_risk.assessment.assessment_id, "decision_id": confirmed_risk.decision_id, "audit_event_id": confirmed_risk.audit_event_id, "outbox_event_id": confirmed_risk.outbox_event_id},
        )
    )
    confirmation_replay_before = _event_counts(database_path)
    confirmed_replay = risk_service.confirm(confirm_command, risk_reviewer)
    confirmation_replay_after = _event_counts(database_path)

    current_row = review_repository.get_row(_ROW_ID, _WORKSPACE_ID)
    current_assessment = risk_repository.get_current_assessment(_ROW_ID, _WORKSPACE_ID)
    if current_row is None or current_assessment is None:
        raise AssertionError("connected risk state was not persisted")  # noqa: TRY003 - bounded harness invariant
    audits = _audit_events(database_path)
    outbox = risk_repository.list_outbox_events(current_assessment.assessment_id, _WORKSPACE_ID)
    evidence = {
        "schema_version": "graphrag.fmea.connected-lifecycle.v1",
        "case_id": _CASE_ID,
        "scoring_rules": [_public(rule_pack)],
        "evidence_packs": [_public(candidate_bundle.evidence_pack)],
        "candidates": [_public(current_row)],
        "review_decisions": [_public(decision_result)],
        "risk_records": [_public(proposed_risk), _public(confirmed_risk.assessment)],
        "audits": [_public(item) for item in audits],
        "outbox": [_public(item) for item in outbox],
        "replays": [
            {
                "command": "review.decision",
                "first": _public(decision_result),
                "replayed": _public(decision_replay),
                "same_persisted_result": _public(decision_result) == _public(decision_replay),
                "event_counts_before": decision_replay_before,
                "event_counts_after": decision_replay_after,
            },
            {
                "command": "fmea.risk.confirm",
                "first": _public(confirmed_risk),
                "replayed": _public(confirmed_replay),
                "same_persisted_result": (
                    confirmed_risk.assessment == confirmed_replay.assessment
                    and confirmed_risk.decision_id == confirmed_replay.decision_id
                    and confirmed_risk.audit_event_id == confirmed_replay.audit_event_id
                    and confirmed_risk.outbox_event_id == confirmed_replay.outbox_event_id
                ),
                "event_counts_before": confirmation_replay_before,
                "event_counts_after": confirmation_replay_after,
            },
        ],
        "steps": steps,
    }
    return CandidateReviewRiskRun(
        evidence=evidence, analysis=candidate_bundle.analysis, row=current_row,
        assessment=current_assessment, evidence_pack=candidate_bundle.evidence_pack,
    )


__all__ = ["CandidateReviewRiskRun", "run_candidate_review_risk"]
