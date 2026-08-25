from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.states import (
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
    RunStatus,
)
from core_domain.fmea.value_objects import EvidencePack
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from fmea_application.review_contracts import (
    EDITABLE_REVIEW_FIELDS,
    ActorContext,
    FieldFinding,
    FieldReviewEdit,
    ReviewAction,
    ReviewCandidateBundle,
    ReviewDecisionCommand,
    ReviewDecisionRecord,
    ReviewJudgement,
    ReviewModelManifest,
    ReviewReasonCode,
    ReviewSourceSnapshot,
    ReviewSuggestion,
    ReviewSuggestionDraft,
    ReviewSuggestionRun,
    StartReviewSuggestionCommand,
)

_UTC = "2026-08-23T00:00:00Z"
_IDEMPOTENCY_KEY = "00000000-0000-4000-8000-000000000001"
_PROMPT_HASH = "sha256:" + "a" * 64


def _field_bindings() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple((field_name, ("ev-1",)) for field_name in sorted(EDITABLE_REVIEW_FIELDS))


def _field_support() -> tuple[tuple[str, EvidenceSupportStatus], ...]:
    return tuple((field_name, EvidenceSupportStatus.SUPPORTED) for field_name in sorted(EDITABLE_REVIEW_FIELDS))


def make_review_source(**overrides: Any) -> ReviewSourceSnapshot:
    source = ReviewSourceSnapshot.build(
        row_id="row-1",
        source_record_version=1,
        candidate_id="candidate-1",
        item_label="Fuel filter",
        function_label="Remove particles",
        template_id="fuel-combustion-fmea-full",
        template_version="1.0.0",
        profile_id="fuel-combustion-fmea-row",
        profile_version="1.0.0",
        generation_run_id="generation-1",
        requested_evidence_profile=EvidenceSelectionProfile.AUTO,
        resolved_evidence_profile=EvidenceSelectionProfile.COMBINED,
        evidence_types=tuple(CitationType),
        trace_id="trace-1",
        retrieval_warnings=(),
        retrieval_incomplete=False,
        field_claim_statuses=tuple((field_name, ClaimStatus.KNOWN) for field_name in sorted(EDITABLE_REVIEW_FIELDS)),
    )
    if not overrides:
        return source
    return replace(source, **overrides)


def make_review_suggestion(**overrides: Any) -> ReviewSuggestion:
    draft = ReviewSuggestionDraft(
        recommended_action=ReviewAction.ACCEPT,
        field_findings=(
            FieldFinding(
                target_field="controls",
                judgement=ReviewJudgement.SUPPORTED,
                recommended_claim_status=ClaimStatus.KNOWN,
                evidence_ids=("ev-1",),
                rationale="The current control is supported.",
            ),
        ),
        proposed_edits=(),
        evidence_requests=(),
        missing_evidence=(),
        conflicts=(),
        rationale="The candidate is supported by the current evidence.",
    )
    suggestion = ReviewSuggestion(
        suggestion_id="suggestion-1",
        run_id="run-1",
        row_id="row-1",
        source_record_version=1,
        recommended_action=draft.recommended_action,
        field_findings=draft.field_findings,
        proposed_edits=draft.proposed_edits,
        evidence_requests=draft.evidence_requests,
        missing_evidence=draft.missing_evidence,
        conflicts=draft.conflicts,
        rationale=draft.rationale,
        model_manifest=ReviewModelManifest(
            provider="test-provider",
            model="test-model",
            template_id="fmea-row-review",
            template_version="1.0.0",
            prompt_hash=_PROMPT_HASH,
        ),
        actor_type=ActorType.MODEL,
        applied=False,
        stale=False,
        created_at=_UTC,
    )
    return replace(suggestion, **overrides) if overrides else suggestion


def make_review_decision_record(**overrides: Any) -> ReviewDecisionRecord:
    record = ReviewDecisionRecord(
        decision_id="decision-1",
        row_id="row-1",
        previous_record_version=1,
        record_version=2,
        actor_id="reviewer-1",
        action=ReviewAction.ACCEPT,
        suggestion_id=None,
        reason_code=ReviewReasonCode.ACCEPT_AS_IS,
        reason="Human reviewer accepts the supported row.",
        edits=(),
        evidence_requests=(),
        unresolved_acknowledgements=(),
        created_at=_UTC,
    )
    return replace(record, **overrides) if overrides else record


def make_start_suggestion_command(**overrides: Any) -> StartReviewSuggestionCommand:
    command = StartReviewSuggestionCommand(
        row_id="row-1",
        expected_record_version=1,
        idempotency_key=_IDEMPOTENCY_KEY,
        review_policy="default",
        focus_fields=(),
    )
    return replace(command, **overrides) if overrides else command


def make_decision_command(**overrides: Any) -> ReviewDecisionCommand:
    command = ReviewDecisionCommand(
        row_id="row-1",
        expected_record_version=1,
        idempotency_key=_IDEMPOTENCY_KEY,
        action=ReviewAction.ACCEPT,
        suggestion_id=None,
        reason_code=ReviewReasonCode.ACCEPT_AS_IS,
        reason="Human reviewer accepts the supported row.",
        edits=(),
        evidence_requests=(),
        unresolved_acknowledgements=(),
    )
    return replace(command, **overrides) if overrides else command


@pytest.fixture
def fixture_human_reviewer() -> ActorContext:
    return ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1")


@pytest.fixture
def fixture_system_actor() -> ActorContext:
    return ActorContext("generation-service", ActorType.SYSTEM, frozenset(), "ws-1")


@pytest.fixture
def fixture_model_actor() -> ActorContext:
    return ActorContext("review-model", ActorType.MODEL, frozenset(), "ws-1")


@pytest.fixture
def fixture_review_row(fixture_pack: EvidencePack) -> FmeaRow:
    return FmeaRow(
        row_id="row-1",
        analysis_id="analysis-1",
        evidence_pack_id=fixture_pack.pack_id,
        item_id="filter-1",
        function_id="fuel-filter-function",
        failure_mode="low fuel pressure",
        causes=("filter blockage",),
        mechanisms=("flow restriction",),
        effects=("flame instability",),
        symptoms=("pressure alarm",),
        controls=("pressure transmitter",),
        barriers=("trip logic",),
        actions=("inspect filter",),
        risk_assessment=None,
        field_evidence=_field_bindings(),
        field_support=_field_support(),
        claim_status=ClaimStatus.KNOWN,
        review_status=ReviewStatus.SUGGESTED,
        publication_status=PublicationStatus.UNPUBLISHED,
    )


@pytest.fixture
def fixture_review_source() -> ReviewSourceSnapshot:
    return make_review_source()


@pytest.fixture
def fixture_review_bundle(
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
    fixture_review_row: FmeaRow,
    fixture_review_source: ReviewSourceSnapshot,
) -> ReviewCandidateBundle:
    return ReviewCandidateBundle(
        analysis=fixture_analysis,
        evidence_pack=fixture_pack,
        rows=(fixture_review_row,),
        source_snapshots=(fixture_review_source,),
    )


@pytest.fixture
def fixture_review_edit() -> FieldReviewEdit:
    return FieldReviewEdit(
        target_field="controls",
        operation="replace",
        value=("pressure transmitter",),
        claim_status=ClaimStatus.KNOWN,
        support_status=EvidenceSupportStatus.SUPPORTED,
        evidence_ids=("ev-1",),
        reason="The current maintenance evidence supports this control.",
    )


@pytest.fixture
def fixture_decision_command() -> ReviewDecisionCommand:
    return make_decision_command()


@pytest.fixture
def fixture_review_suggestion() -> ReviewSuggestion:
    return make_review_suggestion()


@pytest.fixture
def fixture_suggestion_run() -> ReviewSuggestionRun:
    return ReviewSuggestionRun(
        run_id="run-1",
        row_id="row-1",
        source_record_version=1,
        status=RunStatus.QUEUED,
        suggestion_id=None,
        error_code=None,
        retryable=False,
        request_id="request-1",
        trace_id="trace-1",
        created_at=_UTC,
        started_at=None,
        finished_at=None,
    )


@pytest.fixture
def fixture_start_suggestion_command() -> StartReviewSuggestionCommand:
    return make_start_suggestion_command()
