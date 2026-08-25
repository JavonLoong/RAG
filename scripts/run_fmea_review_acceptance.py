"""Build the bounded, deterministic offline FMEA review acceptance pack."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core_domain.fmea.codec import encode_json  # noqa: E402
from core_domain.fmea.entities import FmeaAnalysis, FmeaRow  # noqa: E402
from core_domain.fmea.states import (  # noqa: E402
    FMEA_SCHEMA_ID,
    ActorType,
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet  # noqa: E402
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile  # noqa: E402
from fmea_application.review_contracts import (  # noqa: E402  # noqa: E402
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
    encode_review_json,
)
from fmea_application.review_service import ReviewService  # noqa: E402
from fmea_application.review_template_adapter import ReviewTemplateAdapter  # noqa: E402
from fmea_infrastructure.repository_sqlite import SqliteFmeaRepository  # noqa: E402
from structured_output_application.compiler import TemplateCompiler  # noqa: E402
from structured_output_infrastructure.file_registry import FileTemplateRegistry  # noqa: E402
from structured_output_infrastructure.jsonschema_adapter import Draft202012SchemaAdapter  # noqa: E402
from structured_output_infrastructure.source_loader import load_template_source  # noqa: E402

SCHEMA_VERSION = "graphrag.fmea.review.acceptance.v1"
_TEMPLATE_ID = "fmea-row-review"
_TEMPLATE_VERSION = "1.0.0"
_TEMPLATE_PATH = ROOT / "templates" / "examples" / "fmea-row-review.yaml"
_CASE_PATH = ROOT / "tests" / "fixtures" / "fmea_review_cases.json"
_ARTIFACTS = (
    "context.json",
    "suggestion-run.json",
    "suggestion.json",
    "decision.json",
    "audit-summary.json",
    "acceptance-summary.json",
)
_PROFILE_CASES = (
    ("rag_only", "rag_only", ["text"]),
    ("graphrag_local_only", "graphrag_local_only", ["graph"]),
    ("graphrag_global_only", "graphrag_global_only", ["community"]),
    ("graphrag_only", "graphrag_only", ["graph", "community"]),
    ("combined", "combined", ["text", "graph", "community"]),
    ("auto", "combined", ["text", "graph", "community"]),
    ("custom", "custom", ["text", "graph"]),
)
_UTC = "2026-08-25T00:00:00Z"


class AcceptanceRunError(ValueError):
    """Internal acceptance failure that never contains input or secret text."""

    def __init__(self, code: str) -> None:
        super().__init__("FMEA offline acceptance failed.")
        self.code = code


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _hash_json(value: object) -> str:
    return _hash_bytes(_canonical_bytes(value))


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(_canonical_bytes(value))


def _stable_ids() -> Any:
    counts: dict[str, int] = {}

    def make(prefix: str) -> str:
        counts[prefix] = counts.get(prefix, 0) + 1
        return f"{prefix}-offline-{counts[prefix]}"

    return make


@dataclass
class _DeterministicGenerator:
    draft: ReviewSuggestionDraft
    manifest: ReviewModelManifest
    task: str = ""

    def generate(self, request: Any) -> tuple[ReviewSuggestionDraft, ReviewModelManifest]:
        self.task = ReviewTemplateAdapter().render_task(request)
        return self.draft, self.manifest


class _InlineExecutor:
    def submit(self, _run_id: str, operation: Any) -> None:
        operation()

    def close(self) -> None:
        return None


def _base_values() -> tuple[FmeaAnalysis, EvidencePack, FmeaRow, ReviewSourceSnapshot, ReviewCandidateBundle]:
    versions = VersionSet(
        schema_id=FMEA_SCHEMA_ID,
        data_version="data-1",
        graph_version="graph-1",
        evidence_pack_version="evidence-1",
        profile_version="profile-1",
        template_version="template-1",
        scoring_version="score-1",
        prompt_version="prompt-0",
        model_version="model-0",
        input_snapshot_hash="d" * 64,
    )
    evidence = EvidenceRef(
        evidence_id="ev-1",
        workspace_id="ws-1",
        document_id="doc-1",
        document_version="doc-v1",
        content_hash="e" * 64,
        locator="page:1#span:1",
        quote="pressure is low",
        normalized_quote="pressure is low",
        evidence_hash="f" * 64,
        acl_scope=("engineering",),
        source_type="primary_document",
        source_trust="reviewed",
        is_primary=True,
        created_at=_UTC,
        expires_at=None,
    )
    pack = EvidencePack.build(
        pack_id="pack-1",
        workspace_id="ws-1",
        acl_scope=("engineering",),
        versions=versions,
        refs=(evidence,),
        created_at=_UTC,
        expires_at=None,
    )
    analysis = FmeaAnalysis(
        analysis_id="analysis-1",
        project_id="project-1",
        analysis_type="fuel_system",
        lifecycle_stage="draft",
        scope="fuel delivery to combustor interface",
        system_boundary="fuel skid to burner manifold",
        exclusions=("plant electrical distribution",),
        equipment_configuration="configuration-1",
        control_software_version="control-1",
        fuel_type="natural_gas",
        operating_modes=("startup", "steady_state"),
        assumptions=("pressure transmitter is calibrated",),
        limitations=("no transient test data",),
        unanalysed_parts=("upstream pipeline",),
        versions=versions,
        owner_actor_id="analyst-1",
        reviewer_actor_ids=("reviewer-1",),
        approver_actor_id=None,
        approved_at=None,
        parent_revision_id=None,
        current_revision_id="revision-1",
    )
    fields = tuple(sorted(EDITABLE_REVIEW_FIELDS))
    row = FmeaRow(
        row_id="row-1",
        analysis_id="analysis-1",
        evidence_pack_id="pack-1",
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
        field_evidence=tuple((field, ("ev-1",)) for field in fields),
        field_support=tuple((field, EvidenceSupportStatus.SUPPORTED) for field in fields),
        claim_status=ClaimStatus.KNOWN,
        review_status=ReviewStatus.SUGGESTED,
        publication_status=PublicationStatus.UNPUBLISHED,
    )
    source = ReviewSourceSnapshot.build(
        row_id="row-1",
        source_record_version=1,
        candidate_id="candidate-1",
        item_label="Fuel filter",
        function_label="Remove particles",
        template_id="fuel-combustion-fmea-row",
        template_version="1.0.0",
        profile_id="fuel-combustion-fmea-row",
        profile_version="1.0.0",
        generation_run_id="generation-1",
        requested_evidence_profile=EvidenceSelectionProfile.COMBINED,
        resolved_evidence_profile=EvidenceSelectionProfile.COMBINED,
        evidence_types=(CitationType.TEXT, CitationType.GRAPH, CitationType.COMMUNITY),
        trace_id="trace-1",
        retrieval_warnings=(),
        retrieval_incomplete=False,
        field_claim_statuses=tuple((field, ClaimStatus.KNOWN) for field in fields),
    )
    return analysis, pack, row, source, ReviewCandidateBundle(analysis, pack, (row,), (source,))


def _draft() -> tuple[ReviewSuggestionDraft, ReviewModelManifest]:
    finding = FieldFinding(
        target_field="controls",
        judgement=ReviewJudgement.SUPPORTED,
        recommended_claim_status=ClaimStatus.KNOWN,
        evidence_ids=("ev-1",),
        rationale="The current control is supported.",
    )
    return (
        ReviewSuggestionDraft(
            recommended_action=ReviewAction.ACCEPT,
            field_findings=(finding,),
            proposed_edits=(),
            evidence_requests=(),
            missing_evidence=(),
            conflicts=(),
            rationale="The candidate is supported by the current evidence.",
        ),
        ReviewModelManifest(
            provider="offline-test",
            model="deterministic-fake",
            template_id=_TEMPLATE_ID,
            template_version=_TEMPLATE_VERSION,
            prompt_hash="sha256:" + "a" * 64,
        ),
    )


def _profile_cases() -> list[dict[str, object]]:
    try:
        raw = json.loads(_CASE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcceptanceRunError("FIXTURE_INVALID") from exc
    if not isinstance(raw, list) or len(raw) != len(_PROFILE_CASES):
        raise AcceptanceRunError("FIXTURE_INVALID")
    expected = {requested: (resolved, types) for requested, resolved, types in _PROFILE_CASES}
    cases: list[dict[str, object]] = []
    for case in raw:
        if not isinstance(case, dict):
            raise AcceptanceRunError("FIXTURE_INVALID")
        requested = case.get("requested_profile")
        if requested not in expected:
            raise AcceptanceRunError("FIXTURE_INVALID")
        resolved, types = expected[requested]
        if case.get("resolved_profile") != resolved or case.get("evidence_types") != types:
            raise AcceptanceRunError("FIXTURE_INVALID")
        cases.append(
            {
                "case_id": case["case_id"],
                "requested_profile": requested,
                "resolved_profile": resolved,
                "evidence_types": types,
                "retrieval_warnings": case["retrieval_warnings"],
                "retrieval_incomplete": case["retrieval_incomplete"],
            }
        )
    return sorted(cases, key=lambda item: str(item["requested_profile"]))


def _compile_template() -> Any:
    compiler = TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    )
    return compiler.compile_path(_TEMPLATE_PATH)


def _run(output_directory: Path) -> Path:
    profile_cases = _profile_cases()
    template = _compile_template()
    analysis, pack, row, source, bundle = _base_values()
    draft, manifest = _draft()
    generator = _DeterministicGenerator(draft, manifest)
    reviewer = ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1")
    system = ActorContext("generation-service", ActorType.SYSTEM, frozenset(), "ws-1")

    with tempfile.TemporaryDirectory(prefix="fmea-review-acceptance-") as temp_root:
        temp_root_path = Path(temp_root)
        repository = SqliteFmeaRepository(temp_root_path / "fmea.sqlite3")
        repository.initialize()
        registry_root = temp_root_path / "template-registry"
        registry = FileTemplateRegistry(registry_root)
        registry.register(template, _TEMPLATE_PATH.read_bytes(), _TEMPLATE_PATH.suffix.lower())
        repository.save_review_candidate_bundle(bundle, system)
        identifiers = _stable_ids()
        service = ReviewService(
            repository,
            generator,
            _InlineExecutor(),
            clock=lambda: _UTC,
            id_factory=identifiers,
        )
        context = service.get_context("row-1", reviewer)
        command = StartReviewSuggestionCommand(
            row_id="row-1",
            expected_record_version=1,
            idempotency_key="00000000-0000-4000-8000-000000000001",
            review_policy="default",
            focus_fields=(),
        )
        queued = service.start_suggestion(command, reviewer)
        run = service.get_suggestion_run(queued.run_id, reviewer)
        suggestions = service.list_suggestions("row-1", reviewer)
        if run.status.value != "succeeded" or len(suggestions) != 1:
            raise AcceptanceRunError("OFFLINE_REVIEW_FAILED")
        suggestion = suggestions[0]
        decision_command = ReviewDecisionCommand(
            row_id="row-1",
            expected_record_version=1,
            idempotency_key="00000000-0000-4000-8000-000000000099",
            action=ReviewAction.ACCEPT,
            suggestion_id=suggestion.suggestion_id,
            reason_code=ReviewReasonCode.ACCEPT_AS_IS,
            reason="Human reviewer accepts the supported row.",
            edits=(),
            evidence_requests=(),
            unresolved_acknowledgements=(),
        )
        decision = service.submit_decision(decision_command, reviewer)

        row_before = json.loads(encode_json(row))
        row_after = json.loads(encode_json(decision.row))
        context_payload = {
            "schema_version": FMEA_SCHEMA_ID,
            "resource_type": "review_context",
            "data": {
                "row": row_before,
                "row_hash": _hash_json(row_before),
                "retrieval": {
                    "requested_profile": context.retrieval.requested_profile.value,
                    "resolved_profile": context.retrieval.resolved_profile.value,
                    "evidence_types": [item.value for item in context.retrieval.evidence_types],
                    "trace_id": context.retrieval.trace_id,
                    "warnings": list(context.retrieval.warnings),
                    "incomplete": context.retrieval.incomplete,
                },
                "evidence": {
                    "pack_id": context.evidence.pack_id,
                    "pack_hash": context.evidence.pack_hash,
                    "refs": [
                        {
                            "evidence_id": item.evidence_id,
                            "source_type": item.source_type,
                            "quote": item.quote[:4000],
                        }
                        for item in context.evidence.refs
                    ],
                },
                "profile_cases": profile_cases,
            },
        }
        run_payload = {"schema_version": SCHEMA_VERSION, "data": json.loads(encode_review_json(run))}
        suggestion_payload = {"schema_version": SCHEMA_VERSION, "data": json.loads(encode_review_json(suggestion))}
        decision_payload = {"schema_version": SCHEMA_VERSION, "data": json.loads(encode_review_json(decision))}
        connection = sqlite3.connect(repository.database_path)
        try:
            event_rows = connection.execute(
                "SELECT event_json FROM audit_events ORDER BY created_at, event_id"
            ).fetchall()
        finally:
            connection.close()
        events = [json.loads(str(item[0])) for item in event_rows]
        audit_payload = {
            "schema_version": SCHEMA_VERSION,
            "events": events,
            "counts": {
                "audit_count": len(events),
                "model_decision_count": 0,
                "publication_event_count": 0,
            },
            "decision_ids": [decision.decision_id],
            "audit_event_ids": [str(event["event_id"]) for event in events],
        }

    artifacts = {
        "context.json": context_payload,
        "suggestion-run.json": run_payload,
        "suggestion.json": suggestion_payload,
        "decision.json": decision_payload,
        "audit-summary.json": audit_payload,
    }
    output_directory.mkdir(parents=True, exist_ok=False)
    for filename, payload in artifacts.items():
        _write_json(output_directory / filename, payload)
    hashes = {filename: _hash_bytes((output_directory / filename).read_bytes()) for filename in artifacts}
    summary = {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "counts": {
            "row_count": 1,
            "suggestion_count": 1,
            "decision_count": 1,
            "model_decision_count": 0,
            "audit_count": len(audit_payload["events"]),
            "publication_event_count": 0,
        },
        "profile_cases": profile_cases,
        "hashes": {
            "schema_hash": _hash_json(SCHEMA_VERSION),
            "template_hash": template.template_hash,
            "row_before_hash": _hash_json(row_before),
            "row_after_hash": _hash_json(row_after),
            "artifacts": hashes,
        },
        "safe_errors": [],
    }
    _write_json(output_directory / "acceptance-summary.json", summary)
    return output_directory


def _default_output_root() -> Path:
    return ROOT / ".local" / "fmea-review-acceptance"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--output-root", default=str(_default_output_root()))
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = _run(Path(args.output_root) / timestamp)
        sys.stdout.write(json.dumps({"status": "passed", "output_directory": str(output)}, separators=(",", ":")) + "\n")
    except Exception:
        sys.stdout.write(json.dumps({"status": "failed", "error": {"code": "FMEA_ACCEPTANCE_FAILED"}}, separators=(",", ":")) + "\n")
        return 2
    else:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA_VERSION", "main"]
