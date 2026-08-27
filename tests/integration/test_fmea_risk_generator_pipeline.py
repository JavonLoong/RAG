from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core_domain.structured_generation import GenerationStage, StructuredModelResponse
from fmea_infrastructure.risk_generator import RiskSuggestionGenerator
from structured_generation_application import StructuredGenerationPipeline, StructuredGenerationService
from structured_generation_infrastructure import StrictCandidateBatchCodec, StrictCriticReportCodec
from structured_output_application import StructuredCandidateValidator, TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, FileTemplateRegistry, load_template_source
from tests.unit.test_fmea_risk_generator import _request_with_hidden_evidence

ROOT = Path(__file__).resolve().parents[2]


class _RepairGateway:
    def __init__(self, *, template_hash: str, evidence_pack_id: str) -> None:
        self.template_hash = template_hash
        self.evidence_pack_id = evidence_pack_id
        self.calls = []

    @staticmethod
    def _response(content: str, model_id: str) -> StructuredModelResponse:
        return StructuredModelResponse(
            content=content,
            model_id=model_id,
            finish_reason="stop",
            input_tokens=10,
            output_tokens=10,
            response_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            http_attempts=1,
        )

    def complete(self, request, *, max_attempts: int, timeout_seconds: float):
        self.calls.append((request, max_attempts, timeout_seconds))
        if request.stage is GenerationStage.GENERATE:
            return self._response("not-json", request.model_id)
        payload = {
            "template_id": "fmea-risk-proposal",
            "template_version": "1.0.0",
            "template_hash": self.template_hash,
            "evidence_pack_id": self.evidence_pack_id,
            "candidates": [
                {
                    "candidate_id": "risk-candidate-1",
                    "payload": {
                        "dimensions": [
                            {
                                "name": "severity",
                                "value": 9,
                                "evidence_ids": ["ev-1"],
                                "reason": "severe consequence",
                                "uncertainty": None,
                            },
                            {
                                "name": "occurrence",
                                "value": 3,
                                "evidence_ids": ["ev-1"],
                                "reason": "bounded frequency",
                                "uncertainty": None,
                            },
                            {
                                "name": "detection",
                                "value": 4,
                                "evidence_ids": ["ev-1"],
                                "reason": "online detection",
                                "uncertainty": None,
                            },
                        ],
                        "reason": "evidence-bound proposal",
                        "uncertainty": None,
                    },
                    "claims": [],
                }
            ],
        }
        return self._response(json.dumps(payload), request.model_id)


def test_real_compiler_registry_pipeline_repairs_to_unapplied_projection_safe_proposal(
    tmp_path, fixture_pack, fixture_review_context
) -> None:
    source_path = ROOT / "templates" / "examples" / "fmea-risk-proposal.yaml"
    compiler = TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    )
    template = compiler.compile_path(source_path)
    registry = FileTemplateRegistry(tmp_path / "templates")
    registry.register(template, source_path.read_bytes(), source_path.suffix)
    request = _request_with_hidden_evidence(fixture_pack, fixture_review_context)
    gateway = _RepairGateway(template_hash=template.template_hash, evidence_pack_id=request.evidence_pack.pack_id)
    pipeline = StructuredGenerationPipeline(
        gateway=gateway,
        batch_codec=StrictCandidateBatchCodec(),
        critic_codec=StrictCriticReportCodec(),
        candidate_validator=StructuredCandidateValidator(Draft202012SchemaAdapter()),
    )
    service = StructuredGenerationService(registry=registry, pipeline=pipeline)

    suggestion = RiskSuggestionGenerator(service).generate(request)

    assert suggestion.applied is False
    assert suggestion.template_id == "fuel-combustion-fmea"
    assert suggestion.payload["binding"]["model_template_id"] == "fmea-risk-proposal"
    assert [call[0].stage for call in gateway.calls] == [GenerationStage.GENERATE, GenerationStage.REPAIR]
    assert [call[0].model_id for call in gateway.calls] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert "severity-10" in gateway.calls[0][0].user_prompt
    assert "ev-hidden" not in gateway.calls[0][0].user_prompt
    assert "secret raw quote" not in gateway.calls[0][0].user_prompt
