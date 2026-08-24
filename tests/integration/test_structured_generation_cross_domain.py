from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_generation import GenerationRunStatus, StructuredModelResponse
from structured_generation_application import GenerationRunRequest, StructuredGenerationPipeline
from structured_generation_infrastructure import StrictCandidateBatchCodec, StrictCriticReportCodec
from structured_output_application import StructuredCandidateValidator, TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "templates" / "examples"
CASES = (
    (
        "fuel-combustion-fmea.yaml",
        {"item": "fuel filter", "failure_mode": "blockage", "effects": ["low pressure"]},
        ("/item", "/failure_mode", "/effects/0"),
    ),
    (
        "maintenance-checklist.yaml",
        {"asset_id": "asset-1", "checks": [{"result": "pass", "note": "observed"}]},
        ("/asset_id", "/checks/0/result"),
    ),
    (
        "research-summary.yaml",
        {"paper_id": "paper-1", "claims": [{"statement": "claim", "limitations": "limited"}]},
        ("/paper_id", "/claims/0/statement"),
    ),
)


class Gateway:
    def __init__(self, responses: list[StructuredModelResponse]) -> None:
        self.responses = responses

    def complete(self, request, *, max_attempts, timeout_seconds):
        return self.responses.pop(0)


def _response(content: str, model: str) -> StructuredModelResponse:
    return StructuredModelResponse(
        content=content,
        model_id=model,
        finish_reason="stop",
        input_tokens=10,
        output_tokens=5,
        response_hash=hashlib.sha256(content.encode()).hexdigest(),
        http_attempts=1,
    )


def _pack_with_all_sources(pack: EvidencePack) -> EvidencePack:
    source_types = ("primary_document", "rag_text", "graphrag_relation", "graphrag_community")
    refs = tuple(
        replace(
            pack.refs[0],
            evidence_id=f"ev-{index + 1}",
            source_type=source_type,
            evidence_hash=f"{index + 1}" * 64,
        )
        for index, source_type in enumerate(source_types)
    )
    return EvidencePack.build(
        pack_id=pack.pack_id,
        workspace_id=pack.workspace_id,
        acl_scope=pack.acl_scope,
        versions=pack.versions,
        refs=refs,
        created_at=pack.created_at,
        expires_at=pack.expires_at,
    )


@pytest.mark.parametrize(("filename", "payload", "targets"), CASES)
def test_same_pipeline_succeeds_across_fmea_maintenance_and_research(
    fixture_pack: EvidencePack,
    filename: str,
    payload: dict[str, object],
    targets: tuple[str, ...],
) -> None:
    schema = Draft202012SchemaAdapter()
    template = TemplateCompiler(schema_validator=schema, source_loader=load_template_source).compile_path(
        EXAMPLES / filename
    )
    pack = _pack_with_all_sources(fixture_pack)
    claims = [
        {"target": target, "state": "known", "evidence_ids": [f"ev-{index + 1}"]}
        for index, target in enumerate(targets)
    ]
    batch = json.dumps(
        {
            "template_id": template.metadata.template_id,
            "template_version": template.metadata.version,
            "template_hash": template.template_hash,
            "evidence_pack_id": pack.pack_id,
            "candidates": [{"candidate_id": "candidate-1", "payload": payload, "claims": claims}],
        }
    )
    critic = json.dumps(
        {
            "verdict": "accept",
            "findings": [
                {
                    "candidate_id": "candidate-1",
                    "target": target,
                    "support": "supported",
                    "code": "EVIDENCE_SUPPORTS_CLAIM",
                    "evidence_ids": [f"ev-{index + 1}"],
                    "explanation": "The evidence supports this claim.",
                }
                for index, target in enumerate(targets)
            ],
            "summary": "All evidence-bearing claims are supported.",
        }
    )
    pipeline = StructuredGenerationPipeline(
        gateway=Gateway([_response(batch, "deepseek-v4-flash"), _response(critic, "deepseek-v4-pro")]),
        batch_codec=StrictCandidateBatchCodec(),
        critic_codec=StrictCriticReportCodec(),
        candidate_validator=StructuredCandidateValidator(schema),
    )

    result = pipeline.run(
        GenerationRunRequest(
            run_id=f"run-{template.metadata.template_id}",
            task="Produce one evidence-bound candidate.",
            template=template,
            evidence_pack=pack,
        )
    )

    assert result.status is GenerationRunStatus.SUCCEEDED


def test_pipeline_import_boundary_excludes_retrieval_and_provider_modules() -> None:
    code = """
import json, sys
import structured_generation_application.pipeline
forbidden = ('chroma_rag_poc.query_service', 'storage_layer.graph_store', 'chromadb', 'openai', 'deepseek')
print(json.dumps(sorted(name for name in sys.modules if name.startswith(forbidden))))
"""
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == []
