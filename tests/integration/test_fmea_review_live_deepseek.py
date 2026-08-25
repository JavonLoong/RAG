"""Explicit, paid live DeepSeek review suggestion gate."""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from core_domain.fmea.codec import encode_json
from core_domain.fmea.states import RunStatus
from core_domain.structured_generation import GenerationBudget, GenerationRunStatus, StructuredGenerationError
from fmea_application.review_contracts import (
    ReviewModelManifest,
    ReviewSuggestion,
    ReviewSuggestionDraft,
    StartReviewSuggestionCommand,
)
from fmea_application.review_errors import ReviewError
from fmea_application.review_template_adapter import ReviewTemplateAdapter
from fmea_infrastructure.composition import build_workspace_review_runtime
from fmea_infrastructure.review_generator import EnvironmentReviewSuggestionGenerator
from structured_generation_application.pipeline import StructuredGenerationPipeline
from structured_generation_application.services import StructuredGenerationService
from structured_generation_infrastructure.deepseek_gateway import build_deepseek_gateway_from_env
from structured_generation_infrastructure.json_codec import StrictCandidateBatchCodec, StrictCriticReportCodec
from structured_output_application.compiler import TemplateCompiler
from structured_output_application.validators import StructuredCandidateValidator
from structured_output_infrastructure.file_registry import FileTemplateRegistry
from structured_output_infrastructure.jsonschema_adapter import Draft202012SchemaAdapter
from structured_output_infrastructure.source_loader import load_template_source

REQUEST_TIMEOUT_SECONDS = 90.0
TOTAL_TIMEOUT_SECONDS = 300.0
PRIVATE_MARKERS = ("DEEPSEEK_API_KEY", "Authorization", "Bearer ", "sk-", "TOPSECRET", "C:\\private")
ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = ROOT / "api_server" / "current_console" / "chroma_rag_poc" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))


class LiveDeepSeekReviewGenerator:
    def __init__(self, registry_root: Path) -> None:
        source = Path(__file__).resolve().parents[2] / "templates" / "examples" / "fmea-row-review.yaml"
        compiler = TemplateCompiler(
            schema_validator=Draft202012SchemaAdapter(),
            source_loader=load_template_source,
        )
        template = compiler.compile_path(source)
        registry = FileTemplateRegistry(registry_root)
        registry.register(template, source.read_bytes(), source.suffix.lower())
        self.service = StructuredGenerationService(
            registry=registry,
            pipeline=StructuredGenerationPipeline(
                gateway=build_deepseek_gateway_from_env(),
                batch_codec=StrictCandidateBatchCodec(),
                critic_codec=StrictCriticReportCodec(),
                candidate_validator=StructuredCandidateValidator(Draft202012SchemaAdapter()),
            ),
        )
        self.template = template
        self.adapter = ReviewTemplateAdapter()
        self.last_budget: GenerationBudget | None = None

    def generate(self, request: Any) -> tuple[ReviewSuggestionDraft, ReviewModelManifest]:
        budget = GenerationBudget(
            request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            total_timeout_seconds=TOTAL_TIMEOUT_SECONDS,
        )
        self.last_budget = budget
        try:
            result = self.service.run(
                run_id=request.run_id,
                task=self.adapter.render_task(request),
                template_id=request.template_id,
                version=request.template_version,
                evidence_pack=request.evidence_pack,
                budget=budget,
            )
            if result.status is GenerationRunStatus.FAILED:
                raise ReviewError(  # noqa: TRY301
                    "FMEA_MODEL_SUGGESTION_UNAVAILABLE", "the review model is temporarily unavailable", retryable=True
                )
            if result.status is not GenerationRunStatus.SUCCEEDED:
                raise ReviewError(  # noqa: TRY301
                    "FMEA_MODEL_SUGGESTION_INVALID", "the review model returned an invalid suggestion"
                )
            draft = self.adapter.decode_draft(result, request.context)
            prompt_hash = EnvironmentReviewSuggestionGenerator._final_pro_trace(result)
            return draft, ReviewModelManifest(
                provider="deepseek",
                model="deepseek-v4-pro",
                template_id=self.template.metadata.template_id,
                template_version=self.template.metadata.version,
                prompt_hash=prompt_hash,
            )
        except ReviewError:
            raise
        except StructuredGenerationError as exc:
            del exc
            raise ReviewError("FMEA_MODEL_SUGGESTION_UNAVAILABLE", "the review model is temporarily unavailable", retryable=True) from None
        except Exception as exc:
            del exc
            raise ReviewError("FMEA_MODEL_SUGGESTION_UNAVAILABLE", "the review model is temporarily unavailable", retryable=True) from None


@pytest.mark.live_deepseek
def test_live_deepseek_creates_only_unapplied_model_suggestion(
    tmp_path: Path,
    fixture_review_bundle: Any,
    fixture_system_actor: Any,
    fixture_human_reviewer: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY is not configured")

    from chroma_rag_poc.workspace_registry import WorkspaceConfig

    from core_domain.query_contracts import QueryMode

    workspace = WorkspaceConfig(
        workspace_id="ws-1",
        chroma_persist_dir=tmp_path / "chroma",
        chroma_collection="workspace",
        graph_db_path=tmp_path / "graph.sqlite3",
        fmea_db_path=tmp_path / "fmea.sqlite3",
        fmea_template_registry_path=tmp_path / "template-registry",
        supported_modes=frozenset({QueryMode.VECTOR}),
        default_mode=QueryMode.VECTOR,
    )
    generator = LiveDeepSeekReviewGenerator(tmp_path / "live-registry")
    runtime = build_workspace_review_runtime(workspace, generator=generator)
    try:
        runtime.repository.save_review_candidate_bundle(fixture_review_bundle, fixture_system_actor)
        row_before = runtime.repository.get_row("row-1", "ws-1")
        assert row_before is not None
        command = StartReviewSuggestionCommand(
            row_id="row-1",
            expected_record_version=1,
            idempotency_key="00000000-0000-4000-8000-000000000081",
            review_policy="default",
            focus_fields=(),
        )
        queued = runtime.service.start_suggestion(command, fixture_human_reviewer)
        deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS + 5.0
        terminal = runtime.service.get_suggestion_run(queued.run_id, fixture_human_reviewer)
        while terminal.status in {RunStatus.QUEUED, RunStatus.RUNNING} and time.monotonic() < deadline:
            time.sleep(0.5)
            terminal = runtime.service.get_suggestion_run(queued.run_id, fixture_human_reviewer)
        if terminal.status is not RunStatus.SUCCEEDED:
            code = terminal.error_code or "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
            pytest.fail(f"LIVE_EXTERNAL_FAILURE:{code}")
        suggestions = runtime.service.list_suggestions("row-1", fixture_human_reviewer)
        assert len(suggestions) == 1
        suggestion = suggestions[0]
        assert isinstance(suggestion, ReviewSuggestion)
        assert suggestion.source_record_version == 1
        assert suggestion.applied is False
        row_after = runtime.repository.get_row("row-1", "ws-1")
        assert row_after is not None
        assert encode_json(row_after) == encode_json(row_before)
        assert generator.last_budget is not None
        assert generator.last_budget.request_timeout_seconds == REQUEST_TIMEOUT_SECONDS
        assert generator.last_budget.total_timeout_seconds == TOTAL_TIMEOUT_SECONDS
        with sqlite3.connect(runtime.repository.database_path) as connection:
            decision_count = connection.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0]
            decision_events = connection.execute(
                "SELECT COUNT(*) FROM audit_events WHERE command = 'review.decision'"
            ).fetchone()[0]
            captured_artifact = "\n".join(
                str(row[0])
                for row in connection.execute(
                    "SELECT suggestion_json FROM review_suggestions UNION ALL SELECT event_json FROM audit_events"
                )
            )
        assert decision_count == 0
        assert decision_events == 0
        captured_stdout = capsys.readouterr().out
        assert all(marker not in captured_stdout for marker in PRIVATE_MARKERS)
        assert all(marker not in captured_artifact for marker in PRIVATE_MARKERS)
    finally:
        runtime.executor.close()
