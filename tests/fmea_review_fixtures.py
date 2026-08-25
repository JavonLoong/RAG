from __future__ import annotations

from dataclasses import fields, replace
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
    updated = replace(source, **overrides)
    return ReviewSourceSnapshot.build(
        **{
            field.name: getattr(updated, field.name)
            for field in fields(updated)
            if field.name != "source_hash"
        },
    )


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
def fixture_analyst() -> ActorContext:
    return ActorContext("analyst-1", ActorType.HUMAN, frozenset({"analyst"}), "ws-1")


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
def fixture_decision_record() -> ReviewDecisionRecord:
    return make_review_decision_record()


class MemoryReviewRepository:
    def __init__(self) -> None:
        self.row: FmeaRow | None = None
        self.pack: EvidencePack | None = None
        self.source: ReviewSourceSnapshot | None = None
        self.suggestions: tuple[ReviewSuggestion, ...] = ()
        self.decisions: tuple[ReviewDecisionRecord, ...] = ()
        self.saved_bundle: ReviewCandidateBundle | None = None
        self.calls: list[str] = []

    def seed(
        self,
        *,
        row: FmeaRow,
        pack: EvidencePack,
        source: ReviewSourceSnapshot | None,
        suggestions: tuple[ReviewSuggestion, ...] = (),
        decisions: tuple[ReviewDecisionRecord, ...] = (),
    ) -> None:
        self.row = row
        self.pack = pack
        self.source = source
        self.suggestions = tuple(suggestions)
        self.decisions = tuple(decisions)
        self.saved_bundle = None
        self.calls.clear()

    def _visible(self, workspace_id: str) -> bool:
        return self.pack is not None and self.pack.workspace_id == workspace_id

    def get_row(self, row_id: str, workspace_id: str) -> FmeaRow | None:
        self.calls.append("get_row")
        if not self._visible(workspace_id) or self.row is None or self.row.row_id != row_id:
            return None
        return self.row

    def get_review_source(self, row_id: str, workspace_id: str) -> ReviewSourceSnapshot | None:
        self.calls.append("get_review_source")
        if not self._visible(workspace_id) or self.source is None or self.source.row_id != row_id:
            return None
        return self.source

    def get_evidence_pack(self, pack_id: str, workspace_id: str) -> EvidencePack | None:
        self.calls.append("get_evidence_pack")
        if not self._visible(workspace_id) or self.pack is None or self.pack.pack_id != pack_id:
            return None
        return self.pack

    def list_suggestions(self, row_id: str, workspace_id: str) -> tuple[ReviewSuggestion, ...]:
        self.calls.append("list_suggestions")
        if not self._visible(workspace_id) or self.row is None or self.row.row_id != row_id:
            return ()
        return self.suggestions

    def list_decisions(self, row_id: str, workspace_id: str) -> tuple[ReviewDecisionRecord, ...]:
        self.calls.append("list_decisions")
        if not self._visible(workspace_id) or self.row is None or self.row.row_id != row_id:
            return ()
        return self.decisions

    def save_review_candidate_bundle(
        self, bundle: ReviewCandidateBundle, actor: ActorContext
    ) -> tuple[FmeaRow, ...]:
        self.calls.append("save_review_candidate_bundle")
        self.saved_bundle = bundle
        return tuple(
            replace(
                row,
                review_status=ReviewStatus.SUGGESTED,
                publication_status=PublicationStatus.UNPUBLISHED,
            )
            for row in bundle.rows
        )

    def __getattr__(self, method_name: str) -> Any:
        raise AssertionError(method_name)


@pytest.fixture
def memory_review_repository() -> MemoryReviewRepository:
    return MemoryReviewRepository()


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
def seeded_review_repository(tmp_path, fixture_review_bundle: ReviewCandidateBundle, fixture_system_actor: ActorContext):
    from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository

    repository = SqliteFmeaRepository(tmp_path / "seeded.sqlite3")
    repository.initialize()
    repository.save_review_candidate_bundle(fixture_review_bundle, fixture_system_actor)
    return repository


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
