from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from core_domain.fmea.codec import encode_json
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
from core_domain.structured_generation import (
    CriticReport,
    CriticVerdict,
    GenerationRunResult,
    GenerationRunStatus,
)
from core_domain.structured_output import CandidateClaim, ClaimState, StructuredCandidate, StructuredCandidateBatch
from fmea_application.review_contracts import (
    EDITABLE_REVIEW_FIELDS,
    ActorContext,
    EvidenceRequestItem,
    FieldFinding,
    FieldReviewEdit,
    ReviewAction,
    ReviewCandidateBundle,
    ReviewDecisionCommand,
    ReviewDecisionRecord,
    ReviewJudgement,
    ReviewModelManifest,
    ReviewPriority,
    ReviewReasonCode,
    ReviewSourceSnapshot,
    ReviewSuggestion,
    ReviewSuggestionDraft,
    ReviewSuggestionRun,
    StartReviewSuggestionCommand,
    SuggestionRunReservation,
    encode_review_json,
)
from fmea_application.review_errors import ReviewError
from fmea_application.review_projection import build_review_context
from structured_output_application import TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

_UTC = "2026-08-23T00:00:00Z"
_IDEMPOTENCY_KEY = "00000000-0000-4000-8000-000000000001"
_PROMPT_HASH = "sha256:" + "a" * 64
_ROOT = Path(__file__).parents[1]


def valid_accept_body() -> dict[str, object]:
    """Return the side-effect-free HTTP decision body used by API tests."""

    return {
        "action": "accept",
        "suggestion_id": None,
        "reason_code": "ACCEPT_AS_IS",
        "reason": "Human reviewer accepts the supported row.",
        "edits": [],
        "evidence_requests": [],
        "unresolved_acknowledgements": [],
    }


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


def _review_generation_template():
    return TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    ).compile_path(_ROOT / "templates" / "examples" / "fmea-row-review.yaml")


def _review_claims(payload: dict[str, object]) -> tuple[CandidateClaim, ...]:
    claims: list[CandidateClaim] = []
    for collection_name in ("field_findings", "proposed_edits", "conflicts"):
        items = payload[collection_name]
        assert isinstance(items, list)
        for index, item in enumerate(items):
            assert isinstance(item, dict)
            evidence_ids = item["evidence_ids"]
            assert isinstance(evidence_ids, list)
            if collection_name == "conflicts":
                state = ClaimState.CONFLICT
            else:
                status_name = item.get("recommended_claim_status", item.get("claim_status"))
                state = ClaimState(str(status_name))
            claims.append(
                CandidateClaim(
                    target=f"/{collection_name}/{index}",
                    state=state,
                    evidence_ids=tuple(evidence_ids),
                )
            )
    return tuple(claims)


def make_review_generation_result(payload: dict[str, object]) -> GenerationRunResult:
    template = _review_generation_template()
    candidate = StructuredCandidate(
        candidate_id="candidate-1",
        payload=payload,
        claims=_review_claims(payload),
    )
    batch = StructuredCandidateBatch(
        template_id=template.metadata.template_id,
        template_version=template.metadata.version,
        template_hash=template.template_hash,
        evidence_pack_id="pack-1",
        candidates=(candidate,),
    )
    return GenerationRunResult(
        run_id="review-run-1",
        status=GenerationRunStatus.SUCCEEDED,
        batch=batch,
        critic_report=CriticReport(
            verdict=CriticVerdict.ACCEPT,
            findings=(),
            summary="candidate accepted",
        ),
        deterministic_issues=(),
        generation_issues=(),
        traces=(),
        repair_count=0,
    )


def _valid_review_payload() -> dict[str, object]:
    return {
        "recommended_action": "modify_and_accept",
        "field_findings": [
            {
                "target_field": "controls",
                "judgement": "partially_supported",
                "recommended_claim_status": "known",
                "evidence_ids": ["ev-1"],
                "rationale": "The current evidence supports a control update.",
            },
        ],
        "proposed_edits": [
            {
                "target_field": "controls",
                "operation": "replace",
                "value": ["pressure transmitter inspection"],
                "claim_status": "known",
                "support_status": "supported",
                "evidence_ids": ["ev-1"],
                "reason": "The evidence supports this replacement.",
            },
        ],
        "evidence_requests": [],
        "missing_evidence": [],
        "conflicts": [],
        "rationale": "Modify the controls field using the bound evidence.",
    }


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


@pytest.fixture
def valid_review_suggestion_draft() -> ReviewSuggestionDraft:
    suggestion = make_review_suggestion()
    return ReviewSuggestionDraft(
        recommended_action=suggestion.recommended_action,
        field_findings=suggestion.field_findings,
        proposed_edits=suggestion.proposed_edits,
        evidence_requests=suggestion.evidence_requests,
        missing_evidence=suggestion.missing_evidence,
        conflicts=suggestion.conflicts,
        rationale=suggestion.rationale,
    )


@pytest.fixture
def fixture_review_model_manifest() -> ReviewModelManifest:
    return ReviewModelManifest(
        provider="deepseek",
        model="deepseek-v4-pro",
        template_id="fmea-row-review",
        template_version="1.0.0",
        prompt_hash=_PROMPT_HASH,
    )


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


def make_evidence_request(**overrides: Any) -> EvidenceRequestItem:
    request = EvidenceRequestItem(
        target_field="causes",
        question="Which source confirms the cause?",
        preferred_source_types=("primary_document",),
        priority=ReviewPriority.NORMAL,
    )
    return replace(request, **overrides) if overrides else request


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
def fixture_review_context(
    fixture_review_row: FmeaRow,
    fixture_pack: EvidencePack,
    fixture_review_source: ReviewSourceSnapshot,
):
    return build_review_context(
        row=fixture_review_row,
        source=fixture_review_source,
        pack=fixture_pack,
        suggestions=(),
        decisions=(),
    )


@pytest.fixture
def valid_review_generation_result() -> GenerationRunResult:
    return make_review_generation_result(_valid_review_payload())


@pytest.fixture
def review_result_with_extra_actor_and_external_evidence() -> GenerationRunResult:
    payload = _valid_review_payload()
    payload["actor_type"] = "model"
    payload["field_findings"][0]["evidence_ids"] = ["external-ev"]
    payload["proposed_edits"][0]["evidence_ids"] = ["external-ev"]
    return make_review_generation_result(payload)


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


class RecordingReviewRepository(MemoryReviewRepository):
    def __init__(self) -> None:
        super().__init__()
        self.runs: dict[str, ReviewSuggestionRun] = {}
        self.reservations: dict[str, tuple[str, ReviewSuggestionRun]] = {}
        self.audits: list[Any] = []

    def reserve_suggestion_run(self, prepared: Any) -> SuggestionRunReservation:
        self.calls.append("reserve_suggestion_run")
        existing = self.reservations.get(prepared.scope.scope_key)
        if existing is not None:
            payload_hash, run = existing
            if payload_hash != prepared.payload_hash:
                raise ReviewError("FMEA_IDEMPOTENCY_CONFLICT", "idempotency key already has a different payload")
            return SuggestionRunReservation(run=run, replayed=True)
        if self.row is None or self.pack is None or self.row.row_id != prepared.command.row_id:
            raise ReviewError("FMEA_ROW_NOT_FOUND", "review row was not found")
        if self.row.record_version != prepared.command.expected_record_version:
            raise ReviewError("FMEA_VERSION_CONFLICT", "review row version does not match the request")
        active = tuple(
            run
            for run in self.runs.values()
            if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}
            and run.row_id == prepared.run.row_id
        )
        if len(active) >= 4:
            raise ReviewError("FMEA_REVIEW_RATE_LIMITED", "too many active review runs", retryable=True)
        self.runs[prepared.run.run_id] = prepared.run
        self.reservations[prepared.scope.scope_key] = (prepared.payload_hash, prepared.run)
        self.audits.append(prepared.audit)
        return SuggestionRunReservation(run=prepared.run, replayed=False)

    def get_suggestion_run(self, run_id: str, workspace_id: str) -> ReviewSuggestionRun | None:
        self.calls.append("get_suggestion_run")
        run = self.runs.get(run_id)
        return run if run is not None and self.pack is not None and self.pack.workspace_id == workspace_id else None

    def mark_suggestion_run_running(self, run_id: str, workspace_id: str) -> ReviewSuggestionRun:
        self.calls.append("mark_suggestion_run_running")
        if self.pack is None or self.pack.workspace_id != workspace_id:
            raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review run was not found")
        run = self.runs[run_id]
        if run.status in {RunStatus.SUCCEEDED, RunStatus.FAILED}:
            raise ReviewError("FMEA_REVIEW_TERMINAL", "review run is already terminal")
        updated = replace(run, status=RunStatus.RUNNING, started_at=_UTC)
        self.runs[run_id] = updated
        return updated

    def complete_suggestion_run(
        self, run_id: str, workspace_id: str, suggestion: ReviewSuggestion, audit: Any
    ) -> ReviewSuggestionRun:
        self.calls.append("complete_suggestion_run")
        if self.pack is None or self.pack.workspace_id != workspace_id:
            raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review run was not found")
        run = self.runs[run_id]
        if run.status is RunStatus.SUCCEEDED:
            return run
        if run.status is not RunStatus.RUNNING:
            raise ReviewError("FMEA_REVIEW_TERMINAL", "review run is not running")
        updated = replace(run, status=RunStatus.SUCCEEDED, suggestion_id=suggestion.suggestion_id, finished_at=_UTC)
        self.runs[run_id] = updated
        current_version = self.row.record_version if self.row is not None else suggestion.source_record_version
        self.suggestions = (*self.suggestions, replace(suggestion, stale=current_version != suggestion.source_record_version))
        self.audits.append(audit)
        return updated

    def fail_suggestion_run(
        self, run_id: str, workspace_id: str, error_code: str, retryable: bool, audit: Any
    ) -> ReviewSuggestionRun:
        self.calls.append("fail_suggestion_run")
        if self.pack is None or self.pack.workspace_id != workspace_id:
            raise ReviewError("FMEA_REVIEW_SUGGESTION_NOT_FOUND", "review run was not found")
        run = self.runs[run_id]
        if run.status is RunStatus.SUCCEEDED:
            raise ReviewError("FMEA_REVIEW_TERMINAL", "review run is already terminal")
        if run.status is RunStatus.FAILED:
            return run
        updated = replace(run, status=RunStatus.FAILED, error_code=error_code, retryable=retryable, finished_at=_UTC)
        self.runs[run_id] = updated
        self.audits.append(audit)
        return updated


class RecordingReviewExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.operations: dict[str, Callable[[], None]] = {}

    def submit(self, run_id: str, operation: Callable[[], None]) -> None:
        self.calls.append((run_id, callable(operation)))
        self.operations[run_id] = operation

    def close(self) -> None:
        return None


class InlineReviewExecutor(RecordingReviewExecutor):
    def submit(self, run_id: str, operation: Callable[[], None]) -> None:
        self.calls.append((run_id, callable(operation)))
        self.operations[run_id] = operation
        operation()


class FakeReviewSuggestionGenerator:
    def __init__(self, draft: ReviewSuggestionDraft, manifest: ReviewModelManifest) -> None:
        self.draft = draft
        self.manifest = manifest
        self.calls: list[Any] = []

    def generate(self, request: Any) -> tuple[ReviewSuggestionDraft, ReviewModelManifest]:
        self.calls.append(request)
        return self.draft, self.manifest


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
def recording_repository(
    fixture_review_bundle: ReviewCandidateBundle,
    fixture_system_actor: ActorContext,
) -> RecordingReviewRepository:
    repository = RecordingReviewRepository()
    repository.seed(
        row=fixture_review_bundle.rows[0],
        pack=fixture_review_bundle.evidence_pack,
        source=fixture_review_bundle.source_snapshots[0],
    )
    return repository


@pytest.fixture
def recording_executor() -> RecordingReviewExecutor:
    return RecordingReviewExecutor()


@pytest.fixture
def inline_executor() -> InlineReviewExecutor:
    return InlineReviewExecutor()


def _test_id_factory() -> Callable[[str], str]:
    counts: dict[str, int] = {}

    def make(prefix: str) -> str:
        counts[prefix] = counts.get(prefix, 0) + 1
        return f"{prefix}-{counts[prefix]}"

    return make


@pytest.fixture
def recording_review_service(
    recording_repository: RecordingReviewRepository,
    recording_executor: RecordingReviewExecutor,
    valid_review_suggestion_draft: ReviewSuggestionDraft,
    fixture_review_model_manifest: ReviewModelManifest,
):
    from fmea_application.review_service import ReviewService

    return ReviewService(
        recording_repository,
        FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        recording_executor,
        clock=lambda: _UTC,
        id_factory=_test_id_factory(),
    )


@pytest.fixture
def inline_review_service(
    seeded_review_repository,
    inline_executor: InlineReviewExecutor,
    valid_review_suggestion_draft: ReviewSuggestionDraft,
    fixture_review_model_manifest: ReviewModelManifest,
):
    from fmea_application.review_service import ReviewService

    return ReviewService(
        seeded_review_repository,
        FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        inline_executor,
        clock=lambda: _UTC,
        id_factory=_test_id_factory(),
    )


@pytest.fixture
def running_suggestion_run(
    seeded_review_repository,
    recording_executor: RecordingReviewExecutor,
    valid_review_suggestion_draft: ReviewSuggestionDraft,
    fixture_review_model_manifest: ReviewModelManifest,
    fixture_human_reviewer: ActorContext,
    fixture_start_suggestion_command: StartReviewSuggestionCommand,
) -> ReviewSuggestionRun:
    from fmea_application.review_service import ReviewService

    service = ReviewService(
        seeded_review_repository,
        FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        recording_executor,
        clock=lambda: _UTC,
        id_factory=_test_id_factory(),
    )
    run = service.start_suggestion(fixture_start_suggestion_command, fixture_human_reviewer)
    return run


@pytest.fixture
def suggestion_worker(
    seeded_review_repository,
    recording_executor: RecordingReviewExecutor,
):
    def work(run_id: str) -> ReviewSuggestionRun:
        recording_executor.operations[run_id]()
        result = seeded_review_repository.get_suggestion_run(run_id, "ws-1")
        assert result is not None
        return result

    return work


@pytest.fixture
def advance_seeded_row_to_version_2(seeded_review_repository):
    def advance() -> None:
        row = seeded_review_repository.get_row("row-1", "ws-1")
        assert row is not None
        updated = replace(row, record_version=2)
        from core_domain.fmea.codec import encode_json

        payload = encode_json(updated)
        digest = "sha256:" + sha256(payload.encode("utf-8")).hexdigest()
        connection = seeded_review_repository._connect()
        try:
            connection.execute(
                "UPDATE fmea_rows SET record_version = ?, row_hash = ?, row_json = ? WHERE row_id = ?",
                (2, digest, payload, "row-1"),
            )
        finally:
            connection.close()

    return advance


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
def valid_review_decision_commands(fixture_review_edit: FieldReviewEdit) -> dict[ReviewAction, ReviewDecisionCommand]:
    return {
        ReviewAction.ACCEPT: make_decision_command(
            idempotency_key="00000000-0000-4000-8000-000000000011",
            action=ReviewAction.ACCEPT,
            reason_code=ReviewReasonCode.ACCEPT_AS_IS,
            reason="Human reviewer accepts the supported row.",
            edits=(),
            evidence_requests=(),
        ),
        ReviewAction.MODIFY_AND_ACCEPT: make_decision_command(
            idempotency_key="00000000-0000-4000-8000-000000000012",
            action=ReviewAction.MODIFY_AND_ACCEPT,
            reason_code=ReviewReasonCode.FIELD_CORRECTION,
            reason="Human reviewer corrects the controls field.",
            edits=(fixture_review_edit,),
            evidence_requests=(),
        ),
        ReviewAction.REJECT: make_decision_command(
            idempotency_key="00000000-0000-4000-8000-000000000013",
            action=ReviewAction.REJECT,
            reason_code=ReviewReasonCode.UNSUPPORTED_CLAIM,
            reason="Human reviewer rejects the unsupported row.",
            edits=(),
            evidence_requests=(),
        ),
        ReviewAction.REQUEST_EVIDENCE: make_decision_command(
            idempotency_key="00000000-0000-4000-8000-000000000014",
            action=ReviewAction.REQUEST_EVIDENCE,
            reason_code=ReviewReasonCode.EVIDENCE_REQUIRED,
            reason="Human reviewer requests supporting evidence.",
            edits=(),
            evidence_requests=(make_evidence_request(),),
        ),
        ReviewAction.DEFER: make_decision_command(
            idempotency_key="00000000-0000-4000-8000-000000000015",
            action=ReviewAction.DEFER,
            reason_code=ReviewReasonCode.DEFERRED_FOR_EXPERT,
            reason="Human reviewer defers this row for an expert.",
            edits=(),
            evidence_requests=(),
        ),
    }


@pytest.fixture
def unresolved_accept_command() -> ReviewDecisionCommand:
    return make_decision_command(
        idempotency_key="00000000-0000-4000-8000-000000000021",
        action=ReviewAction.ACCEPT,
        reason_code=ReviewReasonCode.ACCEPT_AS_IS,
        reason="Human reviewer acknowledges the unresolved cause.",
        edits=(),
        evidence_requests=(),
        unresolved_acknowledgements=(),
    )


@pytest.fixture
def decision_referencing_stale_suggestion(
    seeded_review_repository,
    fixture_review_suggestion: ReviewSuggestion,
    fixture_decision_command: ReviewDecisionCommand,
) -> ReviewDecisionCommand:
    suggestion = replace(fixture_review_suggestion, stale=True)
    suggestion_json = encode_review_json(suggestion)
    connection = seeded_review_repository._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO review_suggestion_runs "
            "(run_id, row_id, workspace_id, actor_id, source_record_version, status, request_hash, "
            "idempotency_scope, suggestion_id, request_id, trace_id, created_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                suggestion.run_id,
                suggestion.row_id,
                "ws-1",
                "reviewer-1",
                suggestion.source_record_version,
                "succeeded",
                "sha256:" + "b" * 64,
                "scope-stale-suggestion",
                suggestion.suggestion_id,
                "request-stale",
                "trace-stale",
                suggestion.created_at,
                suggestion.created_at,
            ),
        )
        connection.execute(
            "INSERT INTO review_suggestions "
            "(suggestion_id, run_id, row_id, workspace_id, source_record_version, stale, suggestion_json, suggestion_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                suggestion.suggestion_id,
                suggestion.run_id,
                suggestion.row_id,
                "ws-1",
                suggestion.source_record_version,
                1,
                suggestion_json,
                "sha256:" + sha256(suggestion_json.encode("utf-8")).hexdigest(),
                suggestion.created_at,
            ),
        )
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    return replace(fixture_decision_command, suggestion_id=suggestion.suggestion_id)


def _seed_legacy_row_without_source(
    repository: Any,
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
    fixture_review_row: FmeaRow,
) -> None:
    analysis_json, analysis_hash = repository._analysis_json(fixture_analysis)
    pack_json = encode_json(fixture_pack)
    row = replace(
        fixture_review_row,
        review_status=ReviewStatus.SUGGESTED,
        publication_status=PublicationStatus.UNPUBLISHED,
    )
    row_json, row_hash = repository._row_json(row)
    connection = repository._connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO fmea_analyses(analysis_id, analysis_hash, analysis_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (fixture_analysis.analysis_id, analysis_hash, analysis_json, _UTC, _UTC),
        )
        connection.execute(
            "INSERT INTO evidence_packs(pack_id, workspace_id, pack_hash, pack_json, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fixture_pack.pack_id, fixture_pack.workspace_id, fixture_pack.pack_hash, pack_json, fixture_pack.created_at, fixture_pack.expires_at),
        )
        connection.execute(
            "INSERT INTO fmea_rows "
            "(row_id, workspace_id, analysis_id, evidence_pack_id, review_status, publication_status, "
            "record_version, row_hash, row_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.row_id,
                fixture_pack.workspace_id,
                row.analysis_id,
                row.evidence_pack_id,
                row.review_status.value,
                row.publication_status.value,
                row.record_version,
                row_hash,
                row_json,
                _UTC,
                _UTC,
            ),
        )
        connection.execute("COMMIT")
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


@pytest.fixture
def sqlite_review_service(
    seeded_review_repository,
    valid_review_suggestion_draft: ReviewSuggestionDraft,
    fixture_review_model_manifest: ReviewModelManifest,
):
    from fmea_application.review_service import ReviewService

    return ReviewService(
        seeded_review_repository,
        FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        RecordingReviewExecutor(),
        clock=lambda: _UTC,
        id_factory=_test_id_factory(),
    )


@pytest.fixture
def unresolved_accept_service(
    tmp_path,
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
    fixture_review_row: FmeaRow,
    fixture_review_bundle: ReviewCandidateBundle,
    fixture_system_actor: ActorContext,
    valid_review_suggestion_draft: ReviewSuggestionDraft,
    fixture_review_model_manifest: ReviewModelManifest,
):
    from fmea_application.review_service import ReviewService
    from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository

    unresolved_source = make_review_source(
        field_claim_statuses=tuple(
            (field_name, ClaimStatus.INSUFFICIENT_EVIDENCE if field_name == "causes" else ClaimStatus.KNOWN)
            for field_name in sorted(EDITABLE_REVIEW_FIELDS)
        )
    )
    bundle = replace(fixture_review_bundle, source_snapshots=(unresolved_source,))
    repository = SqliteFmeaRepository(tmp_path / "unresolved.sqlite3")
    repository.initialize()
    repository.save_review_candidate_bundle(bundle, fixture_system_actor)
    return ReviewService(
        repository,
        FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        RecordingReviewExecutor(),
        clock=lambda: _UTC,
        id_factory=_test_id_factory(),
    )


@pytest.fixture
def legacy_missing_source_service(
    tmp_path,
    fixture_analysis: FmeaAnalysis,
    fixture_pack: EvidencePack,
    fixture_review_row: FmeaRow,
    valid_review_suggestion_draft: ReviewSuggestionDraft,
    fixture_review_model_manifest: ReviewModelManifest,
):
    from fmea_application.review_service import ReviewService
    from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository

    repository = SqliteFmeaRepository(tmp_path / "legacy-missing-source.sqlite3")
    repository.initialize()
    _seed_legacy_row_without_source(repository, fixture_analysis, fixture_pack, fixture_review_row)
    return ReviewService(
        repository,
        FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        RecordingReviewExecutor(),
        clock=lambda: _UTC,
        id_factory=_test_id_factory(),
    )


@pytest.fixture
def missing_source_accept_command() -> ReviewDecisionCommand:
    return make_decision_command(
        idempotency_key="00000000-0000-4000-8000-000000000031",
        action=ReviewAction.ACCEPT,
        reason_code=ReviewReasonCode.ACCEPT_AS_IS,
        reason="Human reviewer accepts the legacy row.",
        edits=(),
        evidence_requests=(),
    )


@pytest.fixture
def missing_source_request_command() -> ReviewDecisionCommand:
    return make_decision_command(
        idempotency_key="00000000-0000-4000-8000-000000000032",
        action=ReviewAction.REQUEST_EVIDENCE,
        reason_code=ReviewReasonCode.EVIDENCE_REQUIRED,
        reason="Human reviewer requests evidence for the legacy row.",
        edits=(),
        evidence_requests=(make_evidence_request(),),
    )


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
