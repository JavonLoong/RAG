from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from core_domain.fmea.states import FMEA_SCHEMA_ID
from core_domain.fmea.template_migration import ProposedFieldMapping
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef, VersionSet
from core_domain.structured_generation import GenerationStage, StructuredModelResponse
from fmea_application.assistance_contracts import AssistanceKind
from fmea_application.review_errors import ReviewError
from fmea_application.template_patch_contracts import TemplatePatchSuggestion, normalize_source_mapping_key
from fmea_infrastructure.template_import_excel import ExcelTemplateImporter
from fmea_infrastructure.template_patch_generator import (
    StructuredTemplatePatchGenerator,
    TemplatePatchGenerator,
    TemplatePatchRequest,
)
from structured_generation_application import StructuredGenerationPipeline, StructuredGenerationService
from structured_generation_infrastructure import StrictCandidateBatchCodec, StrictCriticReportCodec
from structured_output_application import StructuredCandidateValidator, TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, FileTemplateRegistry, load_template_source
from tests.unit.test_fmea_template_import_excel import _xlsx

HASH = "a" * 64
TIMESTAMP = "2026-08-27T12:00:00Z"
ROOT = Path(__file__).resolve().parents[2]

VERSIONS = VersionSet(
    schema_id=FMEA_SCHEMA_ID,
    data_version="data-1",
    graph_version="graph-1",
    evidence_pack_version="evidence-1",
    profile_version="profile-1",
    template_version="template-1",
    scoring_version="score-1",
    prompt_version="prompt-1",
    model_version="model-1",
    input_snapshot_hash="d" * 64,
)
PACK = EvidencePack.build(
    pack_id="evidence-pack-1",
    workspace_id="ws-1",
    acl_scope=("engineering",),
    versions=VERSIONS,
    refs=(
        EvidenceRef(
            evidence_id="evidence-1",
            workspace_id="ws-1",
            document_id="private-document-1",
            document_version="v1",
            content_hash="e" * 64,
            locator="C:/private/source.txt#1",
            quote="Failure Mode is a source header.",
            normalized_quote="failure mode is a source header.",
            evidence_hash="f" * 64,
            acl_scope=("engineering",),
            source_type="primary_document",
            source_trust="reviewed",
            is_primary=True,
            created_at=TIMESTAMP,
            expires_at=None,
        ),
    ),
    created_at=TIMESTAMP,
    expires_at=None,
)


class _FakeGateway:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[object] = []

    def generate(self, request: object) -> object:
        self.requests.append(request)
        return self.response


class _StructuredGateway:
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
            response_hash=hashlib.sha256(content.encode()).hexdigest(),
            http_attempts=1,
        )

    def complete(self, request, *, max_attempts: int, timeout_seconds: float):
        self.calls.append((request, max_attempts, timeout_seconds))
        if request.stage is GenerationStage.GENERATE:
            payload = {
                "template_id": "fmea-template-patch",
                "template_version": "1.0.0",
                "template_hash": self.template_hash,
                "evidence_pack_id": self.evidence_pack_id,
                "candidates": [
                    {
                        "candidate_id": "template-patch-candidate-1",
                        "payload": {
                            "diff": [
                                {
                                    "op": "replace",
                                    "path": "/fields/failure_mode",
                                    "value": {"type": "string", "title": "Failure Mode"},
                                }
                            ],
                            "evidence_ids": ["ref-001"],
                        },
                        "claims": [],
                    }
                ],
            }
        else:
            payload = {"verdict": "accept", "findings": [], "summary": "bounded mapping is valid"}
        return self._response(json.dumps(payload), request.model_id)


def _request(**overrides: object) -> TemplatePatchRequest:
    draft = ExcelTemplateImporter(clock=lambda: TIMESTAMP).parse(_xlsx(), "fmea.xlsx", workspace_id="ws-1")
    values: dict[str, object] = {
        "patch_id": "patch-1",
        "draft": draft,
        "evidence_pack": PACK,
        "input_template_version": "1.0.0",
        "target_template_id": "template-1",
        "target_template_version": "1.0.0",
        "target_template_hash": HASH,
        "domain_pack_id": "generic-domain",
        "domain_pack_version": "1.0.0",
        "domain_pack_hash": HASH,
        "evidence_pack_id": "evidence-pack-1",
        "evidence_pack_hash": PACK.pack_hash,
        "run_id": "run-1",
        "trace_id": "trace-1",
        "model_version": "deterministic-fake",
        "prompt_version": "template-mapping-v1",
        "created_at": TIMESTAMP,
    }
    values.update(overrides)
    return TemplatePatchRequest(**values)


def test_provider_neutral_generator_returns_unapplied_suggestion_with_exact_provenance() -> None:
    gateway = _FakeGateway({
        "diff": (
            {
                "op": "replace",
                "path": "/fields/failure_mode",
                "value": {"type": "string", "title": "Failure Mode"},
            },
        ),
        "evidence_ids": ("ref-001",),
    })
    suggestion = TemplatePatchGenerator(gateway, clock=lambda: TIMESTAMP).suggest(_request())

    assert isinstance(suggestion, TemplatePatchSuggestion)
    assert suggestion.envelope.kind is AssistanceKind.TEMPLATE_FIELD_MAPPING
    assert suggestion.applied is False
    assert suggestion.payload.patch_id == "patch-1"
    assert suggestion.payload.target_template_hash == HASH
    assert suggestion.payload.domain_pack_hash == HASH
    assert suggestion.payload.evidence_pack_hash == PACK.pack_hash
    assert suggestion.payload.run_id == "run-1"
    assert suggestion.payload.trace_id == "trace-1"
    assert len(gateway.requests) == 1
    projection = json.dumps(gateway.requests[0], ensure_ascii=False, sort_keys=True)
    assert "BEGIN_UNTRUSTED_IMPORT_HEADERS" in projection
    assert "ws-1" not in projection
    assert "evidence-pack-1" not in projection
    assert HASH not in projection
    assert "Sheet1!A1" not in projection
    assert "private-document-1" not in projection
    assert "C:/private" not in projection
    assert "evidence-1" not in projection
    assert "Failure Mode is a source header." in projection


def test_projection_exposes_stable_ascii_mapping_key_for_non_ascii_header() -> None:
    request = _request()
    chinese_draft = replace(
        request.draft,
        proposed_fields=(
            ProposedFieldMapping(
                source_key="失效模式",
                target_field="failure_mode",
                source_locator="Sheet1!A1",
            ),
        ),
    )
    gateway = _FakeGateway({"diff": (), "evidence_ids": ()})

    TemplatePatchGenerator(gateway, clock=lambda: TIMESTAMP).suggest(replace(request, draft=chinese_draft))

    projected = gateway.requests[0]["untrusted_import_headers"]["proposed_fields"][0]
    mapping_key = projected["normalized_source_key"]
    assert projected["source_header"] == "失效模式"
    assert isinstance(mapping_key, str) and mapping_key.startswith("source_")
    assert mapping_key.isascii()


def test_source_mapping_normalization_is_collision_resistant_and_bounded() -> None:
    slash = normalize_source_mapping_key("A/B")
    spaced = normalize_source_mapping_key("A B")
    oversized = normalize_source_mapping_key("a" * 200)

    assert slash != spaced
    assert slash.startswith("a_b_") and spaced.startswith("a_b_")
    assert len(oversized) <= 128
    assert normalize_source_mapping_key("already_valid") == "already_valid"


def test_source_mapping_normalization_reserves_generated_key_namespace() -> None:
    generated_key = f"x_y_{hashlib.sha256(b'x/y').hexdigest()[:24]}"

    assert normalize_source_mapping_key("x/y") == generated_key
    assert normalize_source_mapping_key(generated_key) != generated_key


def test_structured_generator_reuses_flash_pro_pipeline_without_exposing_private_pack_identity(tmp_path) -> None:
    source_path = ROOT / "templates" / "examples" / "fmea-template-patch.yaml"
    schema = Draft202012SchemaAdapter()
    template = TemplateCompiler(schema_validator=schema, source_loader=load_template_source).compile_path(source_path)
    registry = FileTemplateRegistry(tmp_path / "registry")
    registry.register(template, source_path.read_bytes(), source_path.suffix)
    redacted_pack_id = StructuredTemplatePatchGenerator.projection_pack_id(_request())
    gateway = _StructuredGateway(template_hash=template.template_hash, evidence_pack_id=redacted_pack_id)
    service = StructuredGenerationService(
        registry=registry,
        pipeline=StructuredGenerationPipeline(
            gateway=gateway,
            batch_codec=StrictCandidateBatchCodec(),
            critic_codec=StrictCriticReportCodec(),
            candidate_validator=StructuredCandidateValidator(schema),
        ),
    )

    suggestion = StructuredTemplatePatchGenerator(service, clock=lambda: TIMESTAMP).suggest(_request())

    assert suggestion.candidate.evidence_ids == ("evidence-1",)
    assert [call[0].stage for call in gateway.calls] == [GenerationStage.GENERATE, GenerationStage.CRITIC]
    assert [call[0].model_id for call in gateway.calls] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    prompt = gateway.calls[0][0].user_prompt
    assert "Failure Mode is a source header." in prompt
    for private_value in (
        "ws-1",
        "evidence-pack-1",
        PACK.pack_hash,
        "private-document-1",
        "C:/private",
        "evidence-1",
    ):
        assert private_value not in prompt
    critic_response = json.dumps({"verdict": "accept", "findings": [], "summary": "bounded mapping is valid"})
    assert suggestion.envelope.model_hash == hashlib.sha256(critic_response.encode()).hexdigest()


@pytest.mark.parametrize(
    "response",
    (
        {"diff": ({"op": "add", "path": "/fields/x", "value": "https://example.invalid"},), "evidence_ids": ()},
        {"diff": ({"op": "add", "path": "/fields/x", "value": {"code": "exec('x')"}},), "evidence_ids": ()},
        {"diff": ({"op": "remove", "path": "/fields/x", "value": None},), "evidence_ids": ()},
        {"diff": (), "evidence_ids": (), "unexpected": True},
    ),
)
def test_patch_generator_rejects_injection_extra_keys_and_non_declarative_values(response: object) -> None:
    with pytest.raises(Exception, match="invalid|declarative|unsupported|forbidden|unknown|missing"):
        TemplatePatchGenerator(_FakeGateway(response)).suggest(_request())


def test_patch_request_is_immutable_and_bound_to_the_draft_workspace() -> None:
    request = _request()
    with pytest.raises((AttributeError, TypeError)):
        request.patch_id = "changed"  # type: ignore[misc]
    with pytest.raises(Exception, match="workspace|draft"):
        TemplatePatchGenerator(_FakeGateway({"diff": (), "evidence_ids": ()})).suggest(
            replace(request, draft=object())  # type: ignore[arg-type]
        )


def test_patch_generator_normalizes_oversized_response_and_ids_to_stable_model_error() -> None:
    responses = (
        {"diff": (), "evidence_ids": ("e" * 257,)},
        {"diff": ({"op": "add", "path": "/fields/x", "value": "x" * 70_000},), "evidence_ids": ()},
    )
    for response in responses:
        with pytest.raises(ReviewError) as caught:
            TemplatePatchGenerator(_FakeGateway(response)).suggest(_request())
        assert caught.value.code == "FMEA_MODEL_SUGGESTION_INVALID"


def test_patch_generator_rejects_private_or_unbounded_evidence_identity_before_model_call() -> None:
    private_ref = replace(PACK.refs[0], evidence_id="C:/private/secret.txt")
    private_pack = EvidencePack.build(
        pack_id=PACK.pack_id,
        workspace_id=PACK.workspace_id,
        acl_scope=PACK.acl_scope,
        versions=PACK.versions,
        refs=(private_ref,),
        created_at=PACK.created_at,
        expires_at=PACK.expires_at,
    )
    gateway = _FakeGateway({"diff": (), "evidence_ids": ()})
    with pytest.raises(ReviewError) as caught:
        TemplatePatchGenerator(gateway).suggest(
            _request(evidence_pack=private_pack, evidence_pack_hash=private_pack.pack_hash)
        )
    assert caught.value.code == "FMEA_MODEL_SUGGESTION_INVALID"
    assert gateway.requests == []


def test_patch_generator_rejects_noncanonical_evidence_identity_before_model_call() -> None:
    spaced_ref = replace(PACK.refs[0], evidence_id=" evidence-1 ")
    spaced_pack = EvidencePack.build(
        pack_id=PACK.pack_id,
        workspace_id=PACK.workspace_id,
        acl_scope=PACK.acl_scope,
        versions=PACK.versions,
        refs=(spaced_ref,),
        created_at=PACK.created_at,
        expires_at=PACK.expires_at,
    )
    gateway = _FakeGateway({"diff": (), "evidence_ids": ()})

    with pytest.raises(ReviewError) as caught:
        TemplatePatchGenerator(gateway).suggest(
            _request(evidence_pack=spaced_pack, evidence_pack_hash=spaced_pack.pack_hash)
        )

    assert caught.value.code == "FMEA_MODEL_SUGGESTION_INVALID"
    assert gateway.requests == []


@pytest.mark.parametrize("evidence_id", ("/private/document.txt", "private/document.txt"))
def test_patch_generator_rejects_path_like_evidence_identity_before_model_call(evidence_id: str) -> None:
    path_ref = replace(PACK.refs[0], evidence_id=evidence_id)
    path_pack = EvidencePack.build(
        pack_id=PACK.pack_id,
        workspace_id=PACK.workspace_id,
        acl_scope=PACK.acl_scope,
        versions=PACK.versions,
        refs=(path_ref,),
        created_at=PACK.created_at,
        expires_at=PACK.expires_at,
    )
    gateway = _FakeGateway({"diff": (), "evidence_ids": ()})

    with pytest.raises(ReviewError) as caught:
        TemplatePatchGenerator(gateway).suggest(
            _request(evidence_pack=path_pack, evidence_pack_hash=path_pack.pack_hash)
        )

    assert caught.value.code == "FMEA_MODEL_SUGGESTION_INVALID"
    assert gateway.requests == []


def test_structured_generator_normalizes_unexpected_pipeline_failure() -> None:
    class _BrokenService:
        def run(self, **_kwargs):
            raise RuntimeError("private provider detail")  # noqa: TRY003

    with pytest.raises(ReviewError) as caught:
        StructuredTemplatePatchGenerator(_BrokenService()).suggest(_request())
    assert caught.value.code == "FMEA_MODEL_SUGGESTION_UNAVAILABLE"
    assert "private provider detail" not in str(caught.value)
