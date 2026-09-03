from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from core_domain.structured_output import (
    CandidateClaim,
    CandidateValidationReport,
    ClaimState,
    CompiledTemplate,
    EvidenceBinding,
    StructuredCandidate,
    StructuredCandidateBatch,
    StructuredOutputError,
    TemplateMetadata,
    TemplateValidationReport,
    ValidationIssue,
)


def metadata() -> TemplateMetadata:
    return TemplateMetadata(
        template_id="maintenance-checklist",
        version="1.0.0",
        title="Maintenance checklist",
        description="",
        domain_tags=["maintenance", "equipment"],
        schema_dialect="https://json-schema.org/draft/2020-12/schema",
    )


def candidate() -> StructuredCandidate:
    claim = CandidateClaim(
        target="/checks/0/result",
        state=ClaimState.KNOWN,
        evidence_ids=["ev-1"],
    )
    return StructuredCandidate(
        candidate_id="candidate-1",
        payload={"checks": []},
        claims=[claim],
    )


def batch() -> StructuredCandidateBatch:
    item = candidate()
    return StructuredCandidateBatch(
        template_id="maintenance-checklist",
        template_version="1.0.0",
        template_hash="a" * 64,
        evidence_pack_id="pack-1",
        candidates=[item],
    )


def test_template_and_candidate_contracts_are_frozen_and_tuple_normalized() -> None:
    template_metadata = metadata()
    binding = EvidenceBinding(
        target="/checks/*/result",
        requirement="required",
        min_refs=1,
        allowed_source_types=["rag_text"],
    )
    item = candidate()
    candidate_batch = batch()

    assert template_metadata.domain_tags == ("maintenance", "equipment")
    assert binding.allowed_source_types == ("rag_text",)
    assert item.claims[0].evidence_ids == ("ev-1",)
    assert candidate_batch.candidates == (item,)
    assert tuple(field.name for field in fields(EvidenceBinding)) == (
        "target",
        "requirement",
        "min_refs",
        "max_refs",
        "allowed_source_types",
    )
    with pytest.raises(FrozenInstanceError):
        template_metadata.title = "changed"


@pytest.mark.parametrize(
    "binding",
    [
        {"target": "/x", "requirement": "required", "min_refs": 0},
        {"target": "/x", "requirement": "forbidden", "max_refs": None},
        {"target": "/x", "requirement": "optional", "min_refs": -1},
        {"target": "/x", "requirement": "optional", "min_refs": 2, "max_refs": 1},
        {"target": "/x", "requirement": "invented"},
        {"target": "/x", "requirement": "optional", "allowed_source_types": ["rag_text", "rag_text"]},
    ],
)
def test_invalid_binding_invariants_fail_closed(binding: dict[str, object]) -> None:
    with pytest.raises(StructuredOutputError):
        EvidenceBinding(**binding)


@pytest.mark.parametrize(
    ("state", "evidence_ids"),
    [
        (ClaimState.UNKNOWN, ["ev-1"]),
        (ClaimState.NOT_APPLICABLE, ["ev-1"]),
        (ClaimState.CONFLICT, ["ev-1"]),
        (ClaimState.KNOWN, ["ev-1", "ev-1"]),
    ],
)
def test_invalid_claim_invariants_fail_closed(
    state: ClaimState,
    evidence_ids: list[str],
) -> None:
    with pytest.raises(StructuredOutputError):
        CandidateClaim(target="/field", state=state, evidence_ids=evidence_ids)


def test_duplicate_claim_binding_and_candidate_id_are_rejected() -> None:
    claim = CandidateClaim(target="/field", state=ClaimState.UNKNOWN, evidence_ids=())
    with pytest.raises(StructuredOutputError, match="claim target"):
        StructuredCandidate(candidate_id="candidate-1", payload={}, claims=(claim, claim))

    binding = EvidenceBinding(target="/field", requirement="optional")
    with pytest.raises(StructuredOutputError, match="binding target"):
        CompiledTemplate(
            metadata=metadata(),
            output_schema={"type": "object"},
            evidence_bindings=(binding, binding),
            template_hash="a" * 64,
            canonical_json="{}",
        )


def test_compiled_template_reports_invalid_source_mapping_with_public_mapping_code() -> None:
    with pytest.raises(StructuredOutputError) as raised:
        CompiledTemplate(
            metadata=metadata(),
            output_schema={"type": "object", "properties": {"field": {"type": "string"}}},
            evidence_bindings=(),
            template_hash="a" * 64,
            canonical_json="{}",
            source_mappings={"1invalid": "field"},
        )

    assert raised.value.code == "TEMPLATE_MAPPING_INVALID"

    item = candidate()
    with pytest.raises(StructuredOutputError, match="candidate_id"):
        StructuredCandidateBatch(
            template_id="maintenance-checklist",
            template_version="1.0.0",
            template_hash="a" * 64,
            evidence_pack_id="pack-1",
            candidates=(item, item),
        )


@pytest.mark.parametrize("value", ["", "A" * 64, "a" * 63, "g" * 64])
def test_template_hash_must_be_lowercase_sha256(value: str) -> None:
    with pytest.raises(StructuredOutputError, match="template_hash"):
        StructuredCandidateBatch(
            template_id="maintenance-checklist",
            template_version="1.0.0",
            template_hash=value,
            evidence_pack_id="pack-1",
            candidates=(),
        )


def test_reports_require_validity_to_match_issue_presence() -> None:
    issue = ValidationIssue(code="TEMPLATE_SOURCE_INVALID", message="invalid", pointer="/")
    with pytest.raises(StructuredOutputError):
        TemplateValidationReport(valid=True, issues=(issue,), compiled_template=None)
    with pytest.raises(StructuredOutputError):
        CandidateValidationReport(valid=True, issues=(issue,), batch=batch())

    assert TemplateValidationReport(valid=False, issues=(issue,), compiled_template=None).issues == (issue,)
    assert CandidateValidationReport(valid=True, issues=(), batch=batch()).valid is True


def test_structured_output_error_exposes_stable_safe_fields() -> None:
    error = StructuredOutputError("TEMPLATE_SOURCE_INVALID", "Template source is invalid.", "/template")

    assert error.code == "TEMPLATE_SOURCE_INVALID"
    assert error.pointer == "/template"
    assert str(error) == "Template source is invalid."


@pytest.mark.parametrize(
    "factory",
    [
        lambda: TemplateMetadata(
            template_id="template",
            version="1.0.0",
            title="Template",
            description="",
            domain_tags="not-a-sequence",
            schema_dialect="dialect",
        ),
        lambda: EvidenceBinding(target="/field", requirement=[]),
        lambda: EvidenceBinding(
            target="/field",
            requirement="optional",
            allowed_source_types=1,
        ),
    ],
)
def test_malformed_sequence_and_requirement_types_fail_with_domain_error(factory: object) -> None:
    with pytest.raises(StructuredOutputError):
        factory()
