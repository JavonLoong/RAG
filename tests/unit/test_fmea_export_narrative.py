from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core_domain.fmea.states import ActorType
from core_domain.structured_generation import GenerationStage, StructuredModelResponse
from fmea_application.assistance_contracts import AssistanceKind
from fmea_application.export_service import (
    ExportNarrativeGenerationError,
    ExportNarrativeGenerationResult,
    ExportNarrativeRequest,
    ExportService,
    ExportServiceError,
)
from fmea_application.review_contracts import ActorContext
from fmea_infrastructure.export_narrative_generator import (
    ExportNarrativePipelineResult,
    StructuredExportNarrativeGenerator,
    StructuredExportNarrativePipeline,
    _bounded_task,
    _build_bounded_context,
)
from structured_generation_application import StructuredGenerationPipeline
from structured_generation_infrastructure import StrictCandidateBatchCodec, StrictCriticReportCodec
from structured_output_application import StructuredCandidateValidator
from structured_output_infrastructure import Draft202012SchemaAdapter
from tests.fmea_governance_fixtures import make_normalized_snapshot

HASH = "a" * 64


def _model_actor() -> ActorContext:
    return ActorContext("model-1", ActorType.MODEL, frozenset(), "ws-1")


def _payload(*, evidence_ids: tuple[str, ...] = ("evidence-001",)) -> dict[str, object]:
    return {
        "title": "Fuel system export narrative",
        "sections": [
            {
                "section_id": "overview",
                "title": "Overview",
                "body": "The bounded snapshot contains one reviewed failure mode.",
                "claim_ids": ["claim-001"],
            }
        ],
        "claims": [
            {
                "claim_id": "claim-001",
                "text": "Low pressure is the reviewed failure mode.",
                "evidence_ids": list(evidence_ids),
            }
        ],
    }


class FakePipeline:
    def __init__(self, payload: object | None = None, *, error: Exception | None = None) -> None:
        self.payload = _payload() if payload is None else payload
        self.error = error
        self.requests: list[ExportNarrativeRequest] = []

    def run(self, request: ExportNarrativeRequest) -> ExportNarrativePipelineResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return ExportNarrativePipelineResult(
            payload=self.payload,
            evidence_refs=tuple(
                item["ref"]
                for item in request.projection["evidence"]
                if isinstance(item, dict) and isinstance(item.get("ref"), str)
            ),
            model_hash=HASH,
            prompt_hash="b" * 64,
            run_id=request.run_id,
            trace_id="trace-export-narrative-1",
            status="succeeded",
            repair_count=0,
        )


class TrackingRepository:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> object:
        self.calls.append(name)
        raise AssertionError(f"narrative suggestion must not access repository: {name}")  # noqa: TRY003


class TrackingStore:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"narrative suggestion must not access artifact store: {name}")  # noqa: TRY003


class SharedGateway:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload or _payload()
        self.models: list[str] = []
        self.template = None
        self.evidence_pack_id = ""

    def bind(self, bridge: StructuredExportNarrativePipeline, snapshot) -> None:
        self.template = bridge._template
        self.evidence_pack_id = (
            "export-narrative-projection-" + hashlib.sha256(snapshot.snapshot_hash.encode("ascii")).hexdigest()[:24]
        )

    def complete(self, request, *, max_attempts: int, timeout_seconds: float) -> StructuredModelResponse:
        self.models.append(request.model_id)
        if request.stage is GenerationStage.GENERATE:
            content = json.dumps({
                "template_id": self.template.metadata.template_id,
                "template_version": self.template.metadata.version,
                "template_hash": self.template.template_hash,
                "evidence_pack_id": self.evidence_pack_id,
                "candidates": [
                    {
                        "candidate_id": "narrative-candidate-1",
                        "payload": self.payload,
                        "claims": [],
                    }
                ],
            })
        else:
            content = json.dumps({"verdict": "accept", "findings": [], "summary": "accepted"})
        return StructuredModelResponse(
            content=content,
            model_id=request.model_id,
            finish_reason="stop",
            input_tokens=10,
            output_tokens=10,
            response_hash=hashlib.sha256(content.encode()).hexdigest(),
            http_attempts=1,
        )


def _shared_pipeline(gateway: SharedGateway) -> StructuredGenerationPipeline:
    return StructuredGenerationPipeline(
        gateway=gateway,
        batch_codec=StrictCandidateBatchCodec(),
        critic_codec=StrictCriticReportCodec(),
        candidate_validator=StructuredCandidateValidator(Draft202012SchemaAdapter()),
    )


def _large_multibyte_projection():
    evidence_summary = tuple(
        {
            "pack_id": f"private-pack-{index}",
            "evidence_ids": (f"private-document-{index}",),
            "excerpt": f"{index:02d}" + "燃" * 510,
        }
        for index in range(1, 13)
    )
    rows = tuple(
        {
            "row_id": f"private-row-{index}",
            "failure_mode": "燃料压力异常" * 80,
            "current_control": "人工检查" * 80,
            "document_id": f"private-document-{index}",
            "private_document_ref": f"private-document-reference-{index}",
            "full_document": "private full document",
        }
        for index in range(8)
    )
    snapshot = make_normalized_snapshot(rows=rows, evidence_summary=evidence_summary)
    projection = dict(StructuredExportNarrativeGenerator.projection(snapshot))
    projection["unresolved"] = [
        {
            "issue_alias": f"issue-{index:03d}",
            "code": "证据不足" * 24,
            "severity": "high",
            "evidence_refs": [f"evidence-{index:03d}"],
        }
        for index in range(1, 9)
    ]
    return snapshot, projection


def _service(generator: StructuredExportNarrativeGenerator, repository: object | None = None) -> ExportService:
    return ExportService(
        repository or TrackingRepository(),
        repository or TrackingRepository(),
        TrackingStore(),
        (),
        narrative_generator=generator,
        clock=lambda: "2026-09-03T00:00:00Z",
    )


def test_narrative_suggestion_is_unapplied_and_does_not_persist_or_mutate_snapshot() -> None:
    snapshot = make_normalized_snapshot()
    before = snapshot
    pipeline = FakePipeline()
    suggestion = _service(StructuredExportNarrativeGenerator(pipeline)).suggest_narrative(snapshot, _model_actor())

    assert suggestion.kind is AssistanceKind.EXPORT_NARRATIVE_DRAFT
    assert suggestion.applied is False
    assert suggestion.draft.title == "Fuel system export narrative"
    assert suggestion.envelope.applied is False
    assert snapshot == before
    assert pipeline.requests[0].snapshot == snapshot
    assert pipeline.requests[0].snapshot is not snapshot


def test_narrative_model_projection_is_bounded_and_private_safe() -> None:
    rows = tuple(
        {
            "row_id": f"row-{index}",
            "failure_mode": "low pressure",
            "document_id": "private-document-should-not-leak",
            "private_document_ref": "private-document-reference",
            "full_document": "private full document",
        }
        for index in range(20)
    )
    snapshot = make_normalized_snapshot(rows=rows)
    pipeline = FakePipeline()
    _service(StructuredExportNarrativeGenerator(pipeline)).suggest_narrative(snapshot, _model_actor())

    projection = pipeline.requests[0].projection
    rendered = json.dumps(projection, ensure_ascii=False, sort_keys=True)
    assert "ws-1" not in rendered
    assert "private-document-should-not-leak" not in rendered
    assert "private-document-reference" not in rendered
    assert "full_document" not in rendered
    assert len(projection["rows"]) <= 8
    assert projection["summary"]["row_count"] == 20
    assert all(set(item) <= {"row_alias", "fields"} for item in projection["rows"])


def test_narrative_pipeline_result_preserves_flash_then_pro_review_metadata_and_needs_review() -> None:
    class ReviewPipeline(FakePipeline):
        def run(self, request: ExportNarrativeRequest) -> ExportNarrativePipelineResult:
            self.requests.append(request)
            return ExportNarrativePipelineResult(
                payload=_payload(),
                evidence_refs=("evidence-001",),
                model_hash=HASH,
                prompt_hash="b" * 64,
                run_id=request.run_id,
                trace_id="trace-flash-pro-repair-1",
                status="needs_review",
                repair_count=1,
                stages=("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-pro"),
            )

    result = StructuredExportNarrativeGenerator(ReviewPipeline()).generate(
        ExportNarrativeRequest(
            snapshot=make_normalized_snapshot(),
            projection=StructuredExportNarrativeGenerator.projection(make_normalized_snapshot()),
            run_id="export-narrative-run-1",
        )
    )

    assert isinstance(result, ExportNarrativeGenerationResult)
    assert result.status == "needs_review"
    assert result.repair_count == 1
    assert result.trace_id == "trace-flash-pro-repair-1"
    assert result.draft.claims[0].evidence_ids == ("evidence-001",)


def test_shared_generation_pipeline_calls_flash_then_pro_without_network() -> None:
    gateway = SharedGateway()
    snapshot = make_normalized_snapshot()
    bridge = StructuredExportNarrativePipeline(_shared_pipeline(gateway))
    gateway.bind(bridge, snapshot)
    request = ExportNarrativeRequest(
        snapshot=snapshot,
        projection=StructuredExportNarrativeGenerator.projection(snapshot),
        run_id="export-narrative-shared-run-1",
    )

    result = bridge.run(request)

    assert gateway.models == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert result.stages == ("generate:deepseek-v4-flash", "critic:deepseek-v4-pro")
    assert result.status == "succeeded"


def test_narrative_context_budget_keeps_whole_multibyte_entries_and_reports_omissions() -> None:
    _, projection = _large_multibyte_projection()

    first = _bounded_task(projection)
    second = _bounded_task(projection)
    decoded = json.loads(first)

    assert first == second
    assert len(first) <= 4000
    assert len(first.encode("utf-8")) <= 4000
    assert decoded["context_budget"]["contract"] == "unicode-characters-and-utf8-bytes"
    assert len(decoded["rows"]) >= 1
    assert decoded["context_budget"]["row_quota"] == {"minimum": 1, "status": "satisfied"}
    assert all(decoded["context_budget"]["omitted_counts"][name] > 0 for name in ("rows", "evidence", "unresolved"))
    assert all(item in projection["rows"] for item in decoded["rows"])
    assert all(item in projection["evidence"] for item in decoded["evidence"])
    assert all(item in projection["unresolved"] for item in decoded["unresolved"])
    included_evidence = {item["ref"] for item in decoded["evidence"]}
    assert all(set(item["evidence_refs"]) <= included_evidence for item in decoded["unresolved"])
    assert "private-document" not in first
    assert "private full document" not in first


def test_narrative_context_reports_when_minimum_row_cannot_fit_tiny_budget() -> None:
    snapshot = make_normalized_snapshot(
        rows=(
            {
                "row_id": "row-too-large",
                "failure_mode": "燃" * 512,
                "current_control": "检" * 512,
            },
        ),
        evidence_summary=(),
    )
    projection = StructuredExportNarrativeGenerator.projection(snapshot)

    context = _build_bounded_context(projection, max_characters=1200, max_utf8_bytes=1200)
    decoded = json.loads(context.task)

    assert decoded["rows"] == []
    assert decoded["context_budget"]["row_quota"] == {
        "minimum": 1,
        "status": "budget_insufficient",
    }
    assert decoded["context_budget"]["omitted_counts"]["rows"] == 1
    assert "燃" not in context.task
    assert len(context.task) <= 1200
    assert len(context.task.encode("utf-8")) <= 1200


def test_narrative_output_rejects_an_evidence_alias_omitted_by_context_budget() -> None:
    snapshot, projection = _large_multibyte_projection()
    gateway = SharedGateway(_payload(evidence_ids=("evidence-012",)))
    bridge = StructuredExportNarrativePipeline(_shared_pipeline(gateway))
    gateway.bind(bridge, snapshot)
    request = ExportNarrativeRequest(
        snapshot=snapshot,
        projection=projection,
        run_id="export-narrative-budget-run-1",
    )

    with pytest.raises(ExportNarrativeGenerationError) as captured:
        StructuredExportNarrativeGenerator(bridge).generate(request)

    assert captured.value.code == "FMEA_EXPORT_NARRATIVE_INVALID"
    assert "evidence-012" not in str(captured.value)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({**_payload(), "unknown": True}, "FMEA_EXPORT_NARRATIVE_INVALID"),
        (_payload(evidence_ids=("invented-evidence",)), "FMEA_EXPORT_NARRATIVE_INVALID"),
        ({**_payload(), "sections": []}, "FMEA_EXPORT_NARRATIVE_INVALID"),
    ],
)
def test_invalid_narrative_output_is_rejected_with_stable_error(payload: object, code: str) -> None:
    service = _service(StructuredExportNarrativeGenerator(FakePipeline(payload)))

    with pytest.raises(ExportServiceError) as captured:
        service.suggest_narrative(make_normalized_snapshot(), _model_actor())

    assert captured.value.code == code
    assert "invented-evidence" not in str(captured.value)


def test_narrative_provider_failure_is_safe_and_retryable() -> None:
    service = _service(StructuredExportNarrativeGenerator(FakePipeline(error=RuntimeError("api_key=secret"))))

    with pytest.raises(ExportServiceError) as captured:
        service.suggest_narrative(make_normalized_snapshot(), _model_actor())

    assert captured.value.code == "FMEA_EXPORT_NARRATIVE_UNAVAILABLE"
    assert captured.value.retryable is True
    assert "secret" not in str(captured.value)


def test_application_owned_narrative_error_preserves_safe_code_and_retryability() -> None:
    class SafeUnavailableGenerator:
        def generate(self, request):
            raise ExportNarrativeGenerationError(
                "FMEA_EXPORT_NARRATIVE_UNAVAILABLE",
                "adapter-private detail",
                retryable=False,
            )

    service = ExportService(
        TrackingRepository(), TrackingRepository(), TrackingStore(), (), narrative_generator=SafeUnavailableGenerator()
    )

    with pytest.raises(ExportServiceError) as captured:
        service.suggest_narrative(make_normalized_snapshot(), _model_actor())

    assert captured.value.code == "FMEA_EXPORT_NARRATIVE_UNAVAILABLE"
    assert captured.value.retryable is False
    assert "private" not in str(captured.value)
    assert captured.value.__cause__ is None


def test_same_shaped_third_party_narrative_error_is_not_trusted() -> None:
    class ForgedNarrativeError(ValueError):
        code = "FMEA_EXPORT_NARRATIVE_INVALID"
        retryable = False

    class ForgedGenerator:
        def generate(self, request):
            raise ForgedNarrativeError("api_key=secret")

    service = ExportService(
        TrackingRepository(), TrackingRepository(), TrackingStore(), (), narrative_generator=ForgedGenerator()
    )

    with pytest.raises(ExportServiceError) as captured:
        service.suggest_narrative(make_normalized_snapshot(), _model_actor())

    assert captured.value.code == "FMEA_EXPORT_NARRATIVE_UNAVAILABLE"
    assert captured.value.retryable is True
    assert "secret" not in str(captured.value)
    assert captured.value.__cause__ is None


class _ExplosiveNarrativeValue:
    _ERROR_DETAIL = "secret narrative operation"

    def __eq__(self, other):
        raise RuntimeError(self._ERROR_DETAIL)

    def __str__(self):
        raise RuntimeError(self._ERROR_DETAIL)

    def __hash__(self):
        raise RuntimeError(self._ERROR_DETAIL)


def test_mutated_exact_application_error_fields_are_not_trusted() -> None:
    error = ExportNarrativeGenerationError(
        "FMEA_EXPORT_NARRATIVE_UNAVAILABLE",
        "initially safe",
        retryable=False,
    )
    object.__setattr__(error, "code", _ExplosiveNarrativeValue())
    object.__setattr__(error, "retryable", _ExplosiveNarrativeValue())

    class MutatedErrorGenerator:
        def generate(self, request):
            raise error

    service = ExportService(
        TrackingRepository(), TrackingRepository(), TrackingStore(), (), narrative_generator=MutatedErrorGenerator()
    )

    with pytest.raises(ExportServiceError) as captured:
        service.suggest_narrative(make_normalized_snapshot(), _model_actor())

    assert captured.value.code == "FMEA_EXPORT_NARRATIVE_UNAVAILABLE"
    assert captured.value.retryable is True
    assert "secret" not in str(captured.value)
    assert captured.value.__cause__ is None


@pytest.mark.parametrize("mutation", ["result", "nested_claim"])
def test_mutated_exact_narrative_result_is_normalized_without_leak(mutation: str) -> None:
    delegate = StructuredExportNarrativeGenerator(FakePipeline())

    class MutatedResultGenerator:
        def generate(self, request):
            result = delegate.generate(request)
            if mutation == "result":
                object.__setattr__(result, "run_id", _ExplosiveNarrativeValue())
            else:
                object.__setattr__(result.draft.claims[0], "text", _ExplosiveNarrativeValue())
            return result

    service = ExportService(
        TrackingRepository(), TrackingRepository(), TrackingStore(), (), narrative_generator=MutatedResultGenerator()
    )

    with pytest.raises(ExportServiceError) as captured:
        service.suggest_narrative(make_normalized_snapshot(), _model_actor())

    assert captured.value.code == "FMEA_EXPORT_NARRATIVE_INVALID"
    assert captured.value.retryable is False
    assert "secret" not in str(captured.value)
    assert captured.value.__cause__ is None


@pytest.mark.parametrize("mutation", ["workspace", "snapshot_hash", "nested_row"])
def test_mutated_exact_narrative_snapshot_is_rejected_before_use(mutation: str) -> None:
    snapshot = make_normalized_snapshot()
    if mutation == "workspace":
        object.__setattr__(snapshot, "workspace_id", _ExplosiveNarrativeValue())
    elif mutation == "snapshot_hash":
        object.__setattr__(snapshot, "snapshot_hash", _ExplosiveNarrativeValue())
    else:
        object.__setattr__(
            snapshot,
            "rows",
            ({"row_id": _ExplosiveNarrativeValue(), "failure_mode": "low pressure"},),
        )
    service = _service(StructuredExportNarrativeGenerator(FakePipeline()))

    with pytest.raises(ExportServiceError) as captured:
        service.suggest_narrative(snapshot, _model_actor())

    assert captured.value.code == "FMEA_EXPORT_NARRATIVE_REQUEST_INVALID"
    assert captured.value.retryable is False
    assert "secret" not in str(captured.value)
    assert captured.value.__cause__ is None


def test_narrative_requires_model_actor_and_exact_snapshot() -> None:
    service = _service(StructuredExportNarrativeGenerator(FakePipeline()))
    human = ActorContext("human-1", ActorType.HUMAN, frozenset({"reviewer"}), "ws-1")

    with pytest.raises(ExportServiceError, match="FMEA_EXPORT_NARRATIVE_FORBIDDEN"):
        service.suggest_narrative(make_normalized_snapshot(), human)
    with pytest.raises(ExportServiceError, match="FMEA_EXPORT_NARRATIVE_REQUEST_INVALID"):
        service.suggest_narrative(object(), _model_actor())  # type: ignore[arg-type]


def test_export_runtime_accepts_explicit_narrative_generator_and_contained_artifact_root(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from fmea_infrastructure.composition import build_workspace_export_runtime

    workspace = SimpleNamespace(
        workspace_id="ws-1",
        chroma_persist_dir=tmp_path / "workspace" / "chroma",
        fmea_db_path=tmp_path / "workspace" / "fmea" / "fmea.sqlite3",
        fmea_template_registry_path=None,
        graph_db_path=None,
    )
    generator = StructuredExportNarrativeGenerator(FakePipeline())

    runtime = build_workspace_export_runtime(
        workspace,
        narrative_generator=generator,
        artifact_root=tmp_path / "workspace" / "fmea" / "artifacts",
        clock=lambda: "2026-09-03T00:00:00Z",
        id_factory=lambda prefix: f"{prefix}-1",
    )

    assert runtime.narrative_generator is generator
    assert runtime.artifact_root == (tmp_path / "workspace" / "fmea" / "artifacts").resolve()
    assert runtime.artifact_store.root == runtime.artifact_root
    assert tuple(runtime.exporters) == ("json",)
