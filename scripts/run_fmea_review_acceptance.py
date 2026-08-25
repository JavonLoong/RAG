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
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core_domain.fmea.codec import decode_evidence_pack, decode_row, encode_json  # noqa: E402
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
from core_domain.structured_generation import (  # noqa: E402
    CriticReport,
    CriticVerdict,
    GenerationRunResult,
    GenerationRunStatus,
)
from core_domain.structured_output import (  # noqa: E402
    CandidateClaim,
    ClaimState,
    JsonValue,
    StructuredCandidate,
    StructuredCandidateBatch,
)
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
    decode_review_source_snapshot,
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


@dataclass(frozen=True)
class _ProfileCase:
    raw: dict[str, object]
    row: FmeaRow
    evidence_pack: EvidencePack
    source: ReviewSourceSnapshot
    model_payload: dict[str, object]
    decision: dict[str, object]


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
    adapter: ReviewTemplateAdapter
    generation_result: GenerationRunResult
    manifest: ReviewModelManifest
    task: str = ""

    def generate(self, request: Any) -> tuple[ReviewSuggestionDraft, ReviewModelManifest]:
        self.task = self.adapter.render_task(request)
        manifest = self.manifest
        manifest = ReviewModelManifest(
            provider=manifest.provider,
            model=manifest.model,
            template_id=manifest.template_id,
            template_version=manifest.template_version,
            prompt_hash=_hash_bytes(self.task.encode("utf-8")),
        )
        return self.adapter.decode_draft(self.generation_result, request.context), manifest


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


_CASE_KEYS = {
    "case_id", "requested_profile", "resolved_profile", "evidence_types", "retrieval_warnings",
    "retrieval_incomplete", "row", "source", "evidence_pack", "model_payload", "decision",
}


def _fixture_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_profile_cases() -> list[_ProfileCase]:
    try:
        raw = json.loads(_CASE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcceptanceRunError("FIXTURE_INVALID") from exc
    if not isinstance(raw, list) or len(raw) != len(_PROFILE_CASES):
        raise AcceptanceRunError("FIXTURE_INVALID")
    expected = {requested: (resolved, types) for requested, resolved, types in _PROFILE_CASES}
    cases: list[_ProfileCase] = []
    for case in raw:
        if not isinstance(case, dict) or set(case) != _CASE_KEYS:
            raise AcceptanceRunError("FIXTURE_INVALID")
        requested = case.get("requested_profile")
        if requested not in expected:
            raise AcceptanceRunError("FIXTURE_INVALID")
        resolved, types = expected[requested]
        if (
            case.get("resolved_profile") != resolved
            or case.get("evidence_types") != types
            or not isinstance(case.get("retrieval_warnings"), list)
            or not isinstance(case.get("retrieval_incomplete"), bool)
        ):
            raise AcceptanceRunError("FIXTURE_INVALID")
        try:
            row = decode_row(_fixture_json(case["row"]))
            evidence_pack = decode_evidence_pack(_fixture_json(case["evidence_pack"]))
            source = decode_review_source_snapshot(_fixture_json(case["source"]))
        except Exception as exc:
            raise AcceptanceRunError("FIXTURE_INVALID") from exc
        model_payload = case["model_payload"]
        decision = case["decision"]
        if not isinstance(model_payload, dict) or not isinstance(decision, dict):
            raise AcceptanceRunError("FIXTURE_INVALID")
        if (
            row.row_id != "row-1"
            or row.evidence_pack_id != evidence_pack.pack_id
            or source.row_id != row.row_id
            or source.requested_evidence_profile.value != requested
            or source.resolved_evidence_profile.value != resolved
            or [item.value for item in source.evidence_types] != types
            or source.template_id != _TEMPLATE_ID
            or source.template_version != _TEMPLATE_VERSION
        ):
            raise AcceptanceRunError("FIXTURE_INVALID")
        cases.append(_ProfileCase(case, row, evidence_pack, source, model_payload, decision))
    return sorted(cases, key=lambda item: str(item.raw["requested_profile"]))


def _generation_result(template: Any, case: _ProfileCase) -> GenerationRunResult:
    claims: list[CandidateClaim] = []
    for collection in ("field_findings", "proposed_edits", "conflicts"):
        items = case.model_payload.get(collection)
        if not isinstance(items, list):
            raise AcceptanceRunError("FIXTURE_INVALID")
        for index, raw_item in enumerate(items):
            if not isinstance(raw_item, dict) or not isinstance(raw_item.get("evidence_ids"), list):
                raise AcceptanceRunError("FIXTURE_INVALID")
            state_name = raw_item.get("recommended_claim_status", raw_item.get("claim_status"))
            try:
                state = ClaimState(str(state_name))
                evidence_ids = tuple(str(item) for item in raw_item["evidence_ids"])
                claims.append(CandidateClaim(f"/{collection}/{index}", state, evidence_ids))
            except Exception as exc:
                raise AcceptanceRunError("FIXTURE_INVALID") from exc
    candidate = StructuredCandidate(
        candidate_id=case.source.candidate_id,
        payload=cast(JsonValue, case.model_payload),
        claims=tuple(claims),
    )
    batch = StructuredCandidateBatch(
        template_id=template.metadata.template_id,
        template_version=template.metadata.version,
        template_hash=template.template_hash,
        evidence_pack_id=case.evidence_pack.pack_id,
        candidates=(candidate,),
    )
    return GenerationRunResult(
        run_id=case.source.generation_run_id,
        status=GenerationRunStatus.SUCCEEDED,
        batch=batch,
        critic_report=CriticReport(verdict=CriticVerdict.ACCEPT, findings=(), summary="candidate accepted"),
        deterministic_issues=(),
        generation_issues=(),
        traces=(),
        repair_count=0,
    )


def _profile_output(case: _ProfileCase, execution: dict[str, object]) -> dict[str, object]:
    return {**case.raw, "execution": execution}


def _context_payload(context: Any) -> dict[str, object]:
    return {
        "row": json.loads(encode_json(context.row)),
        "row_hash": _hash_json(json.loads(encode_json(context.row))),
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
    }


def _compile_template() -> Any:
    compiler = TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    )
    return compiler.compile_path(_TEMPLATE_PATH)


def _execute_profile_case(
    case: _ProfileCase,
    temp_root: Path,
    template: Any,
    registry: FileTemplateRegistry,
    analysis: FmeaAnalysis,
    reviewer: ActorContext,
    system: ActorContext,
    case_index: int,
) -> dict[str, object]:
    requested = str(case.raw["requested_profile"])
    repository = SqliteFmeaRepository(temp_root / requested / "fmea.sqlite3")
    repository.initialize()
    registered = registry.get(template.metadata.template_id, template.metadata.version)
    adapter = ReviewTemplateAdapter()
    generator = _DeterministicGenerator(
        adapter=adapter,
        generation_result=_generation_result(registered, case),
        manifest=ReviewModelManifest(
            provider="offline-test",
            model="deterministic-fake",
            template_id=registered.metadata.template_id,
            template_version=registered.metadata.version,
            prompt_hash="sha256:" + "a" * 64,
        ),
    )
    bundle = ReviewCandidateBundle(
        analysis=analysis,
        evidence_pack=case.evidence_pack,
        rows=(case.row,),
        source_snapshots=(case.source,),
    )
    repository.save_review_candidate_bundle(bundle, system)
    service = ReviewService(
        repository,
        generator,
        _InlineExecutor(),
        clock=lambda: _UTC,
        id_factory=_stable_ids(),
    )
    context = service.get_context(case.row.row_id, reviewer)
    command = StartReviewSuggestionCommand(
        row_id=case.row.row_id,
        expected_record_version=case.row.record_version,
        idempotency_key=f"00000000-0000-4000-8000-0000000000{case_index + 1:02d}",
        review_policy="default",
        focus_fields=(),
    )
    queued = service.start_suggestion(command, reviewer)
    run = service.get_suggestion_run(queued.run_id, reviewer)
    suggestions = service.list_suggestions(case.row.row_id, reviewer)
    if run.status.value != "succeeded" or len(suggestions) != 1:
        raise AcceptanceRunError("OFFLINE_REVIEW_FAILED")
    suggestion = suggestions[0]
    decision_data = case.decision
    try:
        action = ReviewAction(str(decision_data["action"]))
        reason_code = ReviewReasonCode(str(decision_data["reason_code"]))
        reason = str(decision_data["reason"])
    except (KeyError, ValueError, TypeError) as exc:
        raise AcceptanceRunError("FIXTURE_INVALID") from exc
    decision = service.submit_decision(
        ReviewDecisionCommand(
            row_id=case.row.row_id,
            expected_record_version=case.row.record_version,
            idempotency_key=f"00000000-0000-4000-8000-0000000001{case_index:02d}",
            action=action,
            suggestion_id=suggestion.suggestion_id,
            reason_code=reason_code,
            reason=reason,
            edits=(),
            evidence_requests=(),
            unresolved_acknowledgements=(),
        ),
        reviewer,
    )
    row_before = json.loads(encode_json(case.row))
    row_after = json.loads(encode_json(decision.row))
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
    context_payload = _context_payload(context)
    execution = {
        "status": "succeeded",
        "requested_profile": case.raw["requested_profile"],
        "resolved_profile": case.raw["resolved_profile"],
        "evidence_types": case.raw["evidence_types"],
        "template_id": registered.metadata.template_id,
        "template_version": registered.metadata.version,
        "template_hash": registered.template_hash,
        "row_hash": _hash_json(row_before),
        "row_after_hash": _hash_json(row_after),
        "source_hash": case.source.source_hash,
        "evidence_pack_hash": case.evidence_pack.pack_hash,
        "model_payload_hash": _hash_json(case.model_payload),
        "run_id": run.run_id,
        "suggestion_id": suggestion.suggestion_id,
        "decision_id": decision.decision_id,
        "audit_event_ids": [str(event["event_id"]) for event in events],
        "context": context_payload,
        "run": json.loads(encode_review_json(run)),
        "suggestion": json.loads(encode_review_json(suggestion)),
        "decision": json.loads(encode_review_json(decision)),
        "audit": audit_payload,
    }
    return {
        "case": _profile_output(case, execution),
        "context": context,
        "run": run,
        "suggestion": suggestion,
        "decision": decision,
        "row_before": row_before,
        "row_after": row_after,
        "events": events,
    }


def _write_failure_pack(output_directory: Path, code: str) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    failure = {"schema_version": SCHEMA_VERSION, "error": {"code": code}}
    for filename in _ARTIFACTS[:-1]:
        _write_json(output_directory / filename, failure)
    _write_json(
        output_directory / "acceptance-summary.json",
        {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "counts": {
                "row_count": 0,
                "suggestion_count": 0,
                "decision_count": 0,
                "model_decision_count": 0,
                "audit_count": 0,
                "publication_event_count": 0,
            },
            "profile_cases": [],
            "hashes": {
                "schema_hash": _hash_json(SCHEMA_VERSION),
                "template_hash": "0" * 64,
                "row_before_hash": "sha256:" + "0" * 64,
                "row_after_hash": "sha256:" + "0" * 64,
                "artifacts": {},
            },
            "safe_errors": [{"code": code}],
        },
    )


def _run(output_directory: Path) -> Path:
    try:
        profile_cases = _load_profile_cases()
        template = _compile_template()
        analysis, _, _, _, _ = _base_values()
        reviewer = ActorContext("reviewer-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1")
        system = ActorContext("generation-service", ActorType.SYSTEM, frozenset(), "ws-1")
        with tempfile.TemporaryDirectory(prefix="fmea-review-acceptance-") as temp_root:
            temp_root_path = Path(temp_root)
            registry = FileTemplateRegistry(temp_root_path / "template-registry")
            registered = registry.register(template, _TEMPLATE_PATH.read_bytes(), _TEMPLATE_PATH.suffix.lower())
            registered = registry.get(registered.metadata.template_id, registered.metadata.version)
            executions = [
                _execute_profile_case(case, temp_root_path, registered, registry, analysis, reviewer, system, index)
                for index, case in enumerate(profile_cases)
            ]
            primary = cast(
                dict[str, Any],
                next(
                    item
                    for item in executions
                    if cast(dict[str, object], item["case"]).get("requested_profile") == "combined"
                ),
            )
            context = primary["context"]
            run = primary["run"]
            suggestion = primary["suggestion"]
            decision = primary["decision"]
            row_before = primary["row_before"]
            row_after = primary["row_after"]
            events = cast(list[dict[str, object]], primary["events"])
            profile_outputs = [item["case"] for item in executions]
            context_data = _context_payload(context)
            context_data["profile_cases"] = profile_outputs
            context_payload = {
                "schema_version": FMEA_SCHEMA_ID,
                "resource_type": "review_context",
                "data": context_data,
            }
            run_payload = {"schema_version": SCHEMA_VERSION, "data": json.loads(encode_review_json(run))}
            suggestion_payload = {"schema_version": SCHEMA_VERSION, "data": json.loads(encode_review_json(suggestion))}
            decision_payload = {"schema_version": SCHEMA_VERSION, "data": json.loads(encode_review_json(decision))}
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
    except Exception:
        _write_failure_pack(output_directory, "FMEA_MODEL_SUGGESTION_UNAVAILABLE")
        return output_directory

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
        "profile_cases": profile_outputs,
        "hashes": {
            "schema_hash": _hash_json(SCHEMA_VERSION),
            "template_hash": registered.template_hash,
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
        summary = json.loads((output / "acceptance-summary.json").read_text(encoding="utf-8"))
        if summary.get("status") != "passed":
            sys.stdout.write(
                json.dumps(
                    {"status": "failed", "error": {"code": "FMEA_MODEL_SUGGESTION_UNAVAILABLE"}},
                    separators=(",", ":"),
                )
                + "\n"
            )
            return 2
        sys.stdout.write(json.dumps({"status": "passed", "output_directory": str(output)}, separators=(",", ":")) + "\n")
    except Exception:
        sys.stdout.write(json.dumps({"status": "failed", "error": {"code": "FMEA_ACCEPTANCE_FAILED"}}, separators=(",", ":")) + "\n")
        return 2
    else:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA_VERSION", "main"]
