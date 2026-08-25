"""Offline end-to-end acceptance for the FMEA review/output vertical slice."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from hashlib import sha256
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
    row_keys = {
        "row_id", "analysis_id", "evidence_pack_id", "item_id", "function_id", "failure_mode", "causes",
        "mechanisms", "effects", "symptoms", "controls", "barriers", "actions", "risk_assessment",
        "field_evidence", "field_support", "claim_status", "review_status", "publication_status", "record_version",
    }
    source_keys = {
        "row_id", "source_record_version", "candidate_id", "item_label", "function_label", "template_id",
        "template_version", "profile_id", "profile_version", "generation_run_id", "requested_evidence_profile",
        "resolved_evidence_profile", "evidence_types", "trace_id", "retrieval_warnings", "retrieval_incomplete",
        "field_claim_statuses", "source_hash",
    }
    pack_keys = {"pack_id", "workspace_id", "acl_scope", "versions", "refs", "pack_hash", "created_at", "expires_at"}
    ref_keys = {
        "evidence_id", "workspace_id", "document_id", "document_version", "content_hash", "locator", "quote",
        "normalized_quote", "evidence_hash", "acl_scope", "source_type", "source_trust", "is_primary",
        "created_at", "expires_at",
    }
    for case in cases:
        assert set(case["row"]) == row_keys
        assert set(case["source"]) == source_keys
        assert set(case["evidence_pack"]) == pack_keys
        assert case["evidence_pack"]["refs"]
        assert all(set(ref) == ref_keys for ref in case["evidence_pack"]["refs"])
        assert set(case["model_payload"]) == {
            "recommended_action", "field_findings", "proposed_edits", "evidence_requests", "missing_evidence",
            "conflicts", "rationale",
        }
        assert set(case["decision"]) == {
            "action", "reason_code", "reason", "edits", "evidence_requests", "unresolved_acknowledgements",
        }


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


def _rewrite_pack_artifact(output: Path, name: str, mutate: Any) -> None:
    value = json.loads((output / name).read_text(encoding="utf-8"))
    mutate(value)
    (output / name).write_bytes(
        (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    )
    if name != "acceptance-summary.json":
        summary_path = output / "acceptance-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["hashes"]["artifacts"][name] = "sha256:" + sha256((output / name).read_bytes()).hexdigest()
        summary_path.write_bytes(
            (json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        )


@pytest.mark.parametrize(
    ("name", "mutate", "code"),
    [
        (
            "profile mapping",
            lambda value: value["data"]["profile_cases"][0].update({"resolved_profile": "rag_only"}),
            "PROFILE_MATRIX_INVALID",
        ),
        (
            "evidence pack content",
            lambda value: value["data"]["profile_cases"][0]["evidence_pack"]["refs"][0].update(
                {"locator": "page:999#span:tampered"}
            ),
            "EVIDENCE_PACK_HASH_MISMATCH",
        ),
        (
            "run suggestion binding",
            lambda value: value["data"].update({"suggestion_id": "other-suggestion"}),
            "RUN_SUGGESTION_BINDING_INVALID",
        ),
        (
            "decision version binding",
            lambda value: value["data"].update({"previous_record_version": 2}),
            "DECISION_VERSION_BINDING_INVALID",
        ),
        (
            "audit hash binding",
            lambda value: value["events"][-1].update({"before_hash": "sha256:" + "0" * 64}),
            "AUDIT_HASH_BINDING_INVALID",
        ),
        (
            "exact audit counts",
            lambda value: value["counts"].update({"audit_count": 2}),
            "AUDIT_COUNT_INVALID",
        ),
    ],
)
def test_independent_verifier_rejects_each_semantic_tamper_class(
    tmp_path: Path,
    name: str,
    mutate: Any,
    code: str,
) -> None:
    del name
    from scripts.run_fmea_review_acceptance import _run
    from scripts.verify_fmea_review_acceptance import AcceptanceVerificationError, verify_acceptance_directory

    output = _run(tmp_path / "pack")
    artifact = "context.json"
    if code.startswith("RUN_"):
        artifact = "suggestion-run.json"
    elif code.startswith("DECISION_"):
        artifact = "decision.json"
    elif code.startswith("AUDIT_"):
        artifact = "audit-summary.json"
    _rewrite_pack_artifact(output, artifact, mutate)
    with pytest.raises(AcceptanceVerificationError) as caught:
        verify_acceptance_directory(output)
    assert caught.value.code == code


def test_runner_executes_every_fixture_profile_through_bound_template_path(tmp_path: Path) -> None:
    from scripts.run_fmea_review_acceptance import _run
    from scripts.verify_fmea_review_acceptance import verify_acceptance_directory

    output = _run(tmp_path / "pack")
    summary = verify_acceptance_directory(output)
    cases = json.loads((output / "context.json").read_text(encoding="utf-8"))["data"]["profile_cases"]
    assert len(cases) == len(PROFILE_CASES)
    assert all(case["execution"]["status"] == "succeeded" for case in cases)
    assert all(case["execution"]["template_id"] == "fmea-row-review" for case in cases)
    assert all(case["execution"]["template_hash"] == summary["hashes"]["template_hash"] for case in cases)
