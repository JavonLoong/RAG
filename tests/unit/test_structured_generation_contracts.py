from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from core_domain.fmea.states import FMEA_SCHEMA_ID
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet
from core_domain.structured_generation import (
    CriticFinding,
    CriticReport,
    CriticVerdict,
    GenerationBudget,
    GenerationIssue,
    GenerationRunResult,
    GenerationRunStatus,
    GenerationStage,
    ModelCallTrace,
    SemanticSupport,
    StructuredGenerationError,
    StructuredModelRequest,
    StructuredModelResponse,
)
from core_domain.structured_output import (
    CandidateClaim,
    ClaimState,
    CompiledTemplate,
    StructuredCandidate,
    StructuredCandidateBatch,
    TemplateMetadata,
)
from structured_generation_application.contracts import GenerationRunRequest


def template() -> CompiledTemplate:
    return CompiledTemplate(
        metadata=TemplateMetadata(
            template_id="maintenance-checklist",
            version="1.0.0",
            title="Maintenance checklist",
            description="",
            domain_tags=("maintenance",),
            schema_dialect="https://json-schema.org/draft/2020-12/schema",
        ),
        output_schema={"type": "object"},
        evidence_bindings=(),
        template_hash="a" * 64,
        canonical_json="{}",
    )


def evidence_pack() -> EvidencePack:
    versions = VersionSet(
        schema_id=FMEA_SCHEMA_ID,
        data_version="data-1",
        graph_version="graph-1",
        evidence_pack_version="evidence-1",
        profile_version="profile-1",
        template_version="template-1",
        scoring_version="scoring-1",
        prompt_version="prompt-1",
        model_version="model-1",
        input_snapshot_hash="d" * 64,
    )
    ref = EvidenceRef(
        evidence_id="ev-1",
        workspace_id="workspace-1",
        document_id="document-1",
        document_version="document-v1",
        content_hash="e" * 64,
        locator="page-1",
        quote="The pressure falls below the threshold.",
        normalized_quote="the pressure falls below the threshold.",
        evidence_hash="f" * 64,
        acl_scope=("engineering",),
        source_type="rag_text",
        source_trust="primary",
        is_primary=True,
        created_at="2026-08-24T00:00:00Z",
        expires_at=None,
    )
    return EvidencePack.build(
        pack_id="pack-1",
        workspace_id="workspace-1",
        acl_scope=("engineering",),
        versions=versions,
        refs=(ref,),
        created_at="2026-08-24T00:00:00Z",
        expires_at=None,
    )


def batch() -> StructuredCandidateBatch:
    candidate = StructuredCandidate(
        candidate_id="candidate-1",
        payload={"failure_mode": "pressure loss"},
        claims=(CandidateClaim(target="/failure_mode", state=ClaimState.UNKNOWN, evidence_ids=()),),
    )
    return StructuredCandidateBatch(
        template_id="maintenance-checklist",
        template_version="1.0.0",
        template_hash="a" * 64,
        evidence_pack_id="pack-1",
        candidates=(candidate,),
    )


def critic_report(verdict: CriticVerdict = CriticVerdict.ACCEPT) -> CriticReport:
    return CriticReport(verdict=verdict, findings=(), summary="none")


def trace() -> ModelCallTrace:
    return ModelCallTrace(
        stage=GenerationStage.GENERATE,
        model_id="deepseek-v4-flash",
        prompt_hash="b" * 64,
        response_hash="c" * 64,
        http_attempts=1,
        input_tokens=10,
        output_tokens=4,
        finish_reason="stop",
        error_code=None,
    )


def test_generation_enums_have_exact_wire_values() -> None:
    assert [(item.name, item.value) for item in GenerationStage] == [
        ("GENERATE", "generate"),
        ("CRITIC", "critic"),
        ("REPAIR", "repair"),
    ]
    assert [(item.name, item.value) for item in GenerationRunStatus] == [
        ("SUCCEEDED", "succeeded"),
        ("NEEDS_REVIEW", "needs_review"),
        ("FAILED", "failed"),
    ]
    assert [(item.name, item.value) for item in CriticVerdict] == [
        ("ACCEPT", "accept"),
        ("REPAIR", "repair"),
        ("NEEDS_REVIEW", "needs_review"),
    ]
    assert [(item.name, item.value) for item in SemanticSupport] == [
        ("SUPPORTED", "supported"),
        ("PARTIALLY_SUPPORTED", "partially_supported"),
        ("CONTRADICTED", "contradicted"),
        ("NOT_SUPPORTED", "not_supported"),
    ]


def test_generation_budget_defaults_and_bounds_are_server_owned() -> None:
    budget = GenerationBudget()
    assert (
        budget.max_candidates,
        budget.max_evidence_refs,
        budget.max_quote_chars_per_ref,
        budget.max_evidence_chars,
        budget.max_prompt_chars,
        budget.max_response_chars,
        budget.max_output_tokens,
        budget.max_logical_calls,
        budget.max_http_attempts,
        budget.max_repairs,
        budget.request_timeout_seconds,
        budget.total_timeout_seconds,
    ) == (20, 20, 2000, 24000, 48000, 128000, 8000, 3, 6, 1, 30.0, 90.0)
    with pytest.raises(StructuredGenerationError, match="configured limit"):
        GenerationBudget(max_repairs=2)
    with pytest.raises(StructuredGenerationError, match="configured limit"):
        GenerationBudget(max_response_chars=128001)
    with pytest.raises(StructuredGenerationError):
        GenerationBudget(max_logical_calls=0)
    with pytest.raises(StructuredGenerationError):
        GenerationBudget(max_candidates=1.5)  # type: ignore[arg-type]

    slow_network_budget = GenerationBudget(
        request_timeout_seconds=90.0,
        total_timeout_seconds=300.0,
    )
    assert (
        slow_network_budget.request_timeout_seconds,
        slow_network_budget.total_timeout_seconds,
    ) == (90.0, 300.0)
    with pytest.raises(StructuredGenerationError, match="configured limit"):
        GenerationBudget(request_timeout_seconds=90.1, total_timeout_seconds=300.0)
    with pytest.raises(StructuredGenerationError, match="configured limit"):
        GenerationBudget(request_timeout_seconds=90.0, total_timeout_seconds=300.1)


def test_model_response_rejects_secret_or_invalid_audit_values() -> None:
    response = StructuredModelResponse(
        content='{"ok":true}',
        model_id="deepseek-v4-flash",
        finish_reason="stop",
        input_tokens=10,
        output_tokens=4,
        response_hash="a" * 64,
        http_attempts=1,
    )
    assert "secret" not in repr(response).lower()
    with pytest.raises(StructuredGenerationError):
        replace(response, http_attempts=0)
    with pytest.raises(StructuredGenerationError):
        replace(response, response_hash="not-a-sha256")


def test_frozen_contracts_normalize_sequences_and_reject_duplicates() -> None:
    finding = CriticFinding(
        candidate_id="candidate-1",
        target="/failure_mode",
        support=SemanticSupport.SUPPORTED,
        code="EVIDENCE_SUPPORTS_CLAIM",
        evidence_ids=["ev-1"],
        explanation="The quote supports the claim.",
    )
    assert finding.evidence_ids == ("ev-1",)
    assert CriticReport(verdict=CriticVerdict.ACCEPT, findings=[finding], summary="ok").findings == (finding,)
    with pytest.raises(StructuredGenerationError, match="duplicate"):
        CriticReport(verdict=CriticVerdict.ACCEPT, findings=[finding, finding], summary="duplicate")
    with pytest.raises(StructuredGenerationError):
        CriticFinding(
            candidate_id="candidate-1",
            target="/failure_mode",
            support=SemanticSupport.SUPPORTED,
            code=" ",
            evidence_ids=(),
            explanation="ok",
        )
    with pytest.raises(FrozenInstanceError):
        finding.code = "changed"


def test_error_and_issue_expose_only_safe_stable_fields() -> None:
    error = StructuredGenerationError(
        "MODEL_TIMEOUT",
        "The structured-generation model request timed out.",
        stage=GenerationStage.GENERATE,
        retryable=True,
        attempts=2,
    )
    assert error.code == "MODEL_TIMEOUT"
    assert error.stage is GenerationStage.GENERATE
    assert error.retryable is True
    assert error.attempts == 2
    assert str(error) == "The structured-generation model request timed out."
    issue = GenerationIssue(
        code="CRITIC_FINDING_MISSING",
        message="A required critic finding is missing.",
        stage=GenerationStage.CRITIC,
        pointer="/candidates/candidate-1/claims/failure_mode",
    )
    assert issue.pointer.endswith("failure_mode")
    with pytest.raises(StructuredGenerationError):
        GenerationIssue(code="", message="bad")
    with pytest.raises(ValueError):
        StructuredGenerationError("", "bad")


def test_request_contract_has_fixed_model_aliases_and_preserves_inputs() -> None:
    compiled = template()
    pack = evidence_pack()
    request = GenerationRunRequest(run_id="run-1", task="find failures", template=compiled, evidence_pack=pack)
    assert request.generator_model == "deepseek-v4-flash"
    assert request.critic_model == "deepseek-v4-pro"
    assert request.repair_model == "deepseek-v4-pro"
    assert request.template is compiled
    assert request.evidence_pack is pack
    assert request.budget.max_response_chars == 128000
    with pytest.raises(StructuredGenerationError, match="approved model"):
        GenerationRunRequest(
            run_id="run-1",
            task="find failures",
            template=compiled,
            evidence_pack=pack,
            generator_model="provider-model",
        )
    with pytest.raises(StructuredGenerationError):
        GenerationRunRequest(run_id=" ", task="find failures", template=compiled, evidence_pack=pack)
    with pytest.raises(StructuredGenerationError):
        GenerationRunRequest(run_id="run-1", task="", template=compiled, evidence_pack=pack)


def test_model_request_and_trace_reject_invalid_hashes_and_audit_values() -> None:
    request = StructuredModelRequest(
        stage=GenerationStage.GENERATE,
        model_id="deepseek-v4-flash",
        system_prompt="system",
        user_prompt="user",
        max_output_tokens=100,
        thinking_enabled=False,
        reasoning_effort=None,
    )
    assert request.reasoning_effort is None
    assert trace().response_hash == "c" * 64
    with pytest.raises(StructuredGenerationError):
        replace(request, max_output_tokens=0)
    with pytest.raises(StructuredGenerationError):
        replace(trace(), prompt_hash="bad")
    with pytest.raises(StructuredGenerationError):
        replace(trace(), response_hash="bad")
    with pytest.raises(StructuredGenerationError):
        replace(request, thinking_enabled=True, reasoning_effort=None)


def test_result_status_and_batch_invariants_are_fail_closed() -> None:
    successful = GenerationRunResult(
        run_id="run-1",
        status=GenerationRunStatus.SUCCEEDED,
        batch=batch(),
        critic_report=critic_report(),
        deterministic_issues=(),
        generation_issues=(),
        traces=(trace(),),
        repair_count=0,
    )
    assert successful.traces == (trace(),)
    needs_review = replace(successful, status=GenerationRunStatus.NEEDS_REVIEW, critic_report=None)
    assert needs_review.status is GenerationRunStatus.NEEDS_REVIEW
    with pytest.raises(StructuredGenerationError, match="batch"):
        replace(successful, batch=None)
    with pytest.raises(StructuredGenerationError, match="critic"):
        replace(successful, critic_report=None)
    with pytest.raises(StructuredGenerationError, match="failed"):
        GenerationRunResult(
            run_id="run-1",
            status=GenerationRunStatus.FAILED,
            batch=batch(),
            critic_report=None,
            deterministic_issues=(),
            generation_issues=(),
            traces=(),
            repair_count=0,
        )
    with pytest.raises(StructuredGenerationError, match="repair"):
        replace(successful, repair_count=2)
    with pytest.raises(StructuredGenerationError, match="batch"):
        replace(successful, batch=object())  # type: ignore[arg-type]
    with pytest.raises(StructuredGenerationError, match="critic"):
        replace(successful, critic_report=object())  # type: ignore[arg-type]


def test_ports_are_provider_neutral_and_application_fmea_import_is_narrow() -> None:
    import structured_generation_application.contracts as application_contracts
    from structured_generation_application import ports

    assert ports.StructuredModelGateway.__module__ == "structured_generation_application.ports"
    assert ports.CandidateBatchCodec.__module__ == "structured_generation_application.ports"
    assert ports.CriticReportCodec.__module__ == "structured_generation_application.ports"
    tree = ast.parse(Path(application_contracts.__file__).read_text(encoding="utf-8"))
    fmea_imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("core_domain.fmea")
    ]
    assert [(node.module, tuple(alias.name for alias in node.names)) for node in fmea_imports] == [
        ("core_domain.fmea.value_objects", ("EvidencePack",)),
    ]


def test_core_generation_import_has_no_provider_or_fmea_side_effects() -> None:
    script = """
import json, sys
import core_domain.structured_generation
forbidden = ('requests', 'model_adapters', 'fmea_application', 'fmea_infrastructure')
print(json.dumps(sorted(name for name in sys.modules if name.startswith(forbidden))))
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and static script
        [sys.executable, "-c", script], text=True, capture_output=True, check=True
    )
    assert json.loads(completed.stdout) == []
