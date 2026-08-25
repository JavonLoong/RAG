"""Offline end-to-end acceptance for the FMEA review/output vertical slice."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from fmea_review_fixtures import (
    FakeReviewSuggestionGenerator,
    InlineReviewExecutor,
    make_decision_command,
    make_review_source,
    make_start_suggestion_command,
)

from core_domain.fmea.entities import FmeaRow
from core_domain.fmea.states import ActorType, PublicationStatus, ReviewStatus, RunStatus
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile
from fmea_application.review_contracts import (
    ActorContext,
    ReviewCandidateBundle,
    ReviewSuggestion,
    ReviewSuggestionRun,
)
from fmea_application.review_service import ReviewService
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "tests" / "fixtures" / "fmea_review_cases.json"
PROFILE_CASES = (
    ("rag_only", "rag_only", ["text"]),
    ("graphrag_local_only", "graphrag_local_only", ["graph"]),
    ("graphrag_global_only", "graphrag_global_only", ["community"]),
    ("graphrag_only", "graphrag_only", ["graph", "community"]),
    ("combined", "combined", ["text", "graph", "community"]),
    ("auto", "combined", ["text", "graph", "community"]),
    ("custom", "custom", ["text", "graph"]),
)
_UTC = "2026-08-25T00:00:00Z"


def _stable_ids() -> Any:
    counts: dict[str, int] = {}

    def make(prefix: str) -> str:
        counts[prefix] = counts.get(prefix, 0) + 1
        return f"{prefix}-acceptance-{counts[prefix]}"

    return make


@dataclass
class AcceptanceRuntime:
    repository: SqliteFmeaRepository
    service: ReviewService
    reviewer: ActorContext
    row: FmeaRow

    def seed_and_context(
        self,
        requested: str,
        types: list[str],
    ) -> Any:
        case_root = self.repository.database_path.parent / f"profile-{requested}"
        repository = SqliteFmeaRepository(case_root / "fmea.sqlite3")
        repository.initialize()
        source = make_review_source(
            requested_evidence_profile=EvidenceSelectionProfile(requested),
            resolved_evidence_profile=(
                EvidenceSelectionProfile.COMBINED
                if requested == "auto"
                else EvidenceSelectionProfile(requested)
            ),
            evidence_types=tuple(CitationType(item) for item in types),
        )
        bundle = replace(self._bundle, source_snapshots=(source,))
        repository.save_review_candidate_bundle(bundle, ActorContext("system", ActorType.SYSTEM, frozenset(), "ws-1"))
        service = ReviewService.for_queries(repository)
        return service.get_context("row-1", self.reviewer)

    def persist_generated_row(self) -> FmeaRow:
        result = self.repository.get_row("row-1", "ws-1")
        assert result is not None
        return result

    def run_fake_model_review(self, row_id: str) -> ReviewSuggestionRun:
        command = make_start_suggestion_command(row_id=row_id)
        queued = self.service.start_suggestion(command, self.reviewer)
        return self.service.get_suggestion_run(queued.run_id, self.reviewer)

    def accept_model_edit_explicitly(self, suggestion: ReviewSuggestion) -> Any:
        command = make_decision_command(
            expected_record_version=suggestion.source_record_version,
            suggestion_id=suggestion.suggestion_id,
            idempotency_key="00000000-0000-4000-8000-000000000099",
        )
        return self.service.submit_decision(command, self.reviewer)

    def count_model_decisions(self) -> int:
        with sqlite3.connect(self.repository.database_path) as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM review_decisions WHERE actor_id = ?",
                    ("review-model",),
                ).fetchone()[0]
            )

    def count_publish_events(self) -> int:
        with sqlite3.connect(self.repository.database_path) as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE command LIKE 'publish.%' OR command LIKE 'publication.%'"
                ).fetchone()[0]
            )

    @property
    def _bundle(self) -> ReviewCandidateBundle:
        return self._bundle_value

    @_bundle.setter
    def _bundle(self, value: ReviewCandidateBundle) -> None:
        self._bundle_value = value


@pytest.fixture
def acceptance_runtime(
    tmp_path: Path,
    fixture_review_bundle: ReviewCandidateBundle,
    fixture_system_actor: ActorContext,
    valid_review_suggestion_draft: Any,
    fixture_review_model_manifest: Any,
    fixture_review_row: FmeaRow,
    fixture_human_reviewer: ActorContext,
) -> AcceptanceRuntime:
    repository = SqliteFmeaRepository(tmp_path / "acceptance.sqlite3")
    repository.initialize()
    repository.save_review_candidate_bundle(fixture_review_bundle, fixture_system_actor)
    service = ReviewService(
        repository,
        FakeReviewSuggestionGenerator(valid_review_suggestion_draft, fixture_review_model_manifest),
        InlineReviewExecutor(),
        clock=lambda: _UTC,
        id_factory=_stable_ids(),
    )
    runtime = AcceptanceRuntime(repository, service, fixture_human_reviewer, fixture_review_row)
    runtime._bundle = fixture_review_bundle
    return runtime


def test_fixture_contains_one_complete_case_per_profile() -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    assert {case["requested_profile"] for case in cases} == {item[0] for item in PROFILE_CASES}
    required = {
        "case_id", "requested_profile", "resolved_profile", "evidence_types", "retrieval_warnings",
        "retrieval_incomplete", "row", "source", "evidence_pack", "model_payload", "decision",
    }
    assert all(set(case) == required for case in cases)


@pytest.mark.parametrize(("requested", "resolved", "types"), PROFILE_CASES)
def test_all_evidence_profiles_use_same_review_contract(
    acceptance_runtime: AcceptanceRuntime,
    requested: str,
    resolved: str,
    types: list[str],
) -> None:
    context = acceptance_runtime.seed_and_context(requested, types)
    assert context.retrieval.requested_profile.value == requested
    assert context.retrieval.resolved_profile.value == resolved
    assert [item.value for item in context.retrieval.evidence_types] == types
    assert context.row.publication_status is PublicationStatus.UNPUBLISHED


def test_full_candidate_suggestion_human_decision_chain(acceptance_runtime: AcceptanceRuntime) -> None:
    row = acceptance_runtime.persist_generated_row()
    row_before = row
    run = acceptance_runtime.run_fake_model_review(row.row_id)
    assert run.status is RunStatus.SUCCEEDED
    suggestion = acceptance_runtime.service.list_suggestions(row.row_id, acceptance_runtime.reviewer)[0]
    assert suggestion.actor_type is ActorType.MODEL
    assert suggestion.source_record_version == 1
    assert suggestion.applied is False
    decided = acceptance_runtime.accept_model_edit_explicitly(suggestion)
    assert decided.row.review_status is ReviewStatus.ACCEPTED
    assert decided.row.publication_status is PublicationStatus.UNPUBLISHED
    assert decided.row.record_version == 2
    assert acceptance_runtime.repository.get_row(row.row_id, "ws-1") != row_before
    assert acceptance_runtime.count_model_decisions() == 0
    assert acceptance_runtime.count_publish_events() == 0


def test_acceptance_runner_and_verifier_are_fail_closed() -> None:
    from scripts.verify_fmea_review_acceptance import AcceptanceVerificationError, verify_acceptance_directory

    with pytest.raises(AcceptanceVerificationError):
        verify_acceptance_directory(ROOT / ".local" / "missing-fmea-acceptance")


def test_offline_runner_writes_exact_pack_and_tampering_fails_closed(tmp_path: Path) -> None:
    from scripts.run_fmea_review_acceptance import _run
    from scripts.verify_fmea_review_acceptance import AcceptanceVerificationError, verify_acceptance_directory

    output = _run(tmp_path / "pack")
    summary = verify_acceptance_directory(output)
    assert summary["status"] == "passed"
    assert {path.name for path in output.iterdir()} == {
        "context.json",
        "suggestion-run.json",
        "suggestion.json",
        "decision.json",
        "audit-summary.json",
        "acceptance-summary.json",
    }
    (output / "unexpected.json").write_bytes(b"{}\n")
    with pytest.raises(AcceptanceVerificationError) as caught:
        verify_acceptance_directory(output)
    assert caught.value.code == "ARTIFACT_SET_INVALID"
