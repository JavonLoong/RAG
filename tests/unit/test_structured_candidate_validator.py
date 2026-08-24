from __future__ import annotations

from dataclasses import replace

import pytest

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_output import (
    CandidateClaim,
    ClaimState,
    StructuredCandidate,
    StructuredCandidateBatch,
    TemplateLimits,
)
from structured_output_application import StructuredCandidateValidator, TemplateCompiler
from structured_output_infrastructure import Draft202012SchemaAdapter, load_template_source

DIALECT = "https://json-schema.org/draft/2020-12/schema"


def compiled_template(*, overlapping: bool = False):
    bindings: list[dict[str, object]] = [
        {
            "target": "/status",
            "requirement": "required",
            "min_refs": 1,
            "max_refs": 1,
            "allowed_source_types": ["primary_document"],
        },
        {"target": "/notes/*", "requirement": "required", "min_refs": 1},
        {"target": "/forbidden_a", "requirement": "forbidden", "max_refs": 0},
        {"target": "/forbidden_b", "requirement": "forbidden", "max_refs": 0},
    ]
    if overlapping:
        bindings.append({"target": "/notes/0", "requirement": "optional"})
    source = {
        "template": {
            "id": "evidence-demo",
            "version": "1.0.0",
            "title": "Evidence demo",
            "description": "",
            "domain_tags": [],
            "schema_dialect": DIALECT,
        },
        "output_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "notes", "forbidden_a", "forbidden_b"],
            "properties": {
                "status": {"type": "string"},
                "notes": {"type": "array", "minItems": 2, "items": {"type": "string"}},
                "forbidden_a": {"type": "string"},
                "forbidden_b": {"type": "string"},
                "free": {"type": "string"},
            },
        },
        "evidence_bindings": bindings,
    }
    return TemplateCompiler(
        schema_validator=Draft202012SchemaAdapter(),
        source_loader=load_template_source,
    ).compile(source)


def pack_with_conflict_refs(fixture_pack: EvidencePack) -> EvidencePack:
    second = replace(
        fixture_pack.refs[0],
        evidence_id="ev-2",
        source_type="graph_fact",
        quote="graph reports another state",
        normalized_quote="graph reports another state",
        evidence_hash="2" * 64,
    )
    return EvidencePack.build(
        pack_id=fixture_pack.pack_id,
        workspace_id=fixture_pack.workspace_id,
        acl_scope=fixture_pack.acl_scope,
        versions=fixture_pack.versions,
        refs=(*fixture_pack.refs, second),
        created_at=fixture_pack.created_at,
        expires_at=fixture_pack.expires_at,
    )


def candidate(
    *,
    candidate_id: str = "candidate-1",
    claims: tuple[CandidateClaim, ...] | None = None,
    payload: dict[str, object] | None = None,
) -> StructuredCandidate:
    active_payload = payload or {
        "status": "ok",
        "notes": ["low pressure", "unstable flame"],
        "forbidden_a": "unknown",
        "forbidden_b": "not applicable",
    }
    active_claims = claims or (
        CandidateClaim("/status", ClaimState.KNOWN, ("ev-1",)),
        CandidateClaim("/notes/0", ClaimState.INSUFFICIENT_EVIDENCE, ()),
        CandidateClaim("/notes/1", ClaimState.CONFLICT, ("ev-1", "ev-2")),
        CandidateClaim("/forbidden_a", ClaimState.UNKNOWN, ()),
        CandidateClaim("/forbidden_b", ClaimState.NOT_APPLICABLE, ()),
    )
    return StructuredCandidate(candidate_id=candidate_id, payload=active_payload, claims=active_claims)


def batch(template, *candidates: StructuredCandidate, pack_id: str = "pack-1") -> StructuredCandidateBatch:
    return StructuredCandidateBatch(
        template_id=template.metadata.template_id,
        template_version=template.metadata.version,
        template_hash=template.template_hash,
        evidence_pack_id=pack_id,
        candidates=candidates,
    )


def validator(limits: TemplateLimits | None = None) -> StructuredCandidateValidator:
    return StructuredCandidateValidator(Draft202012SchemaAdapter(), limits=limits)


def test_all_claim_states_and_required_wildcard_coverage_are_valid(fixture_pack: EvidencePack) -> None:
    template = compiled_template()
    evidence_pack = pack_with_conflict_refs(fixture_pack)
    candidate_batch = batch(template, candidate())

    report = validator().validate(candidate_batch, template, evidence_pack)

    assert report.valid is True
    assert report.issues == ()
    assert report.batch is candidate_batch


def test_candidate_order_is_retained_while_issues_are_sorted(fixture_pack: EvidencePack) -> None:
    template = compiled_template()
    evidence_pack = pack_with_conflict_refs(fixture_pack)
    first = candidate(
        candidate_id="z-first",
        claims=(CandidateClaim("/missing", ClaimState.UNKNOWN, ()),),
    )
    second = candidate(
        candidate_id="a-second",
        claims=(CandidateClaim("/also-missing", ClaimState.UNKNOWN, ()),),
    )
    candidate_batch = batch(template, first, second)

    report = validator().validate(candidate_batch, template, evidence_pack)

    assert tuple(item.candidate_id for item in report.batch.candidates) == ("z-first", "a-second")
    assert tuple(issue.candidate_id for issue in report.issues)[:2] == ("z-first", "z-first")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("template_id", "other", "TEMPLATE_NOT_FOUND"),
        ("template_version", "2.0.0", "TEMPLATE_NOT_FOUND"),
        ("template_hash", "b" * 64, "TEMPLATE_HASH_MISMATCH"),
        ("evidence_pack_id", "other-pack", "EVIDENCE_PACK_MISMATCH"),
    ],
)
def test_batch_identity_mismatches_are_fatal(
    fixture_pack: EvidencePack,
    field: str,
    value: str,
    code: str,
) -> None:
    template = compiled_template()
    evidence_pack = pack_with_conflict_refs(fixture_pack)
    candidate_batch = replace(batch(template, candidate()), **{field: value})

    report = validator().validate(candidate_batch, template, evidence_pack)

    assert report.valid is False
    assert tuple(issue.code for issue in report.issues) == (code,)


def test_schema_target_binding_and_required_coverage_failures_are_reported(
    fixture_pack: EvidencePack,
) -> None:
    template = compiled_template(overlapping=True)
    evidence_pack = pack_with_conflict_refs(fixture_pack)
    item = candidate(
        claims=(
            CandidateClaim("/notes/0", ClaimState.INSUFFICIENT_EVIDENCE, ()),
            CandidateClaim("/missing", ClaimState.UNKNOWN, ()),
            CandidateClaim("/free", ClaimState.UNKNOWN, ()),
        ),
        payload={
            "status": 3,
            "notes": ["one", "two"],
            "forbidden_a": "x",
            "forbidden_b": "y",
            "free": "unbound",
        },
    )

    report = validator().validate(batch(template, item), template, evidence_pack)
    codes = {issue.code for issue in report.issues}

    assert "CANDIDATE_SCHEMA_INVALID" in codes
    assert "CANDIDATE_TARGET_INVALID" in codes
    assert "CANDIDATE_BINDING_AMBIGUOUS" in codes
    assert "CANDIDATE_EVIDENCE_MISSING" in codes


@pytest.mark.parametrize(
    ("claim", "code"),
    [
        (CandidateClaim("/status", ClaimState.KNOWN, ()), "CANDIDATE_CLAIM_STATE_INVALID"),
        (
            CandidateClaim("/status", ClaimState.KNOWN, ("ev-2",)),
            "CANDIDATE_EVIDENCE_SOURCE_FORBIDDEN",
        ),
        (
            CandidateClaim("/status", ClaimState.KNOWN, ("missing",)),
            "CANDIDATE_EVIDENCE_MISSING",
        ),
        (
            CandidateClaim("/forbidden_a", ClaimState.KNOWN, ()),
            "CANDIDATE_CLAIM_STATE_INVALID",
        ),
    ],
)
def test_evidence_membership_source_and_state_rules(
    fixture_pack: EvidencePack,
    claim: CandidateClaim,
    code: str,
) -> None:
    template = compiled_template()
    evidence_pack = pack_with_conflict_refs(fixture_pack)
    claims = (
        *(existing for existing in candidate().claims if existing.target != claim.target),
        claim,
    )

    report = validator().validate(batch(template, candidate(claims=claims)), template, evidence_pack)

    assert code in {issue.code for issue in report.issues}


def test_candidate_and_claim_limits_fail_before_deep_validation(fixture_pack: EvidencePack) -> None:
    template = compiled_template()
    evidence_pack = pack_with_conflict_refs(fixture_pack)
    candidate_batch = batch(
        template,
        candidate(candidate_id="one"),
        candidate(candidate_id="two"),
    )

    report = validator(TemplateLimits(max_candidates=1)).validate(
        candidate_batch,
        template,
        evidence_pack,
    )

    assert tuple(issue.code for issue in report.issues) == ("TEMPLATE_LIMIT_EXCEEDED",)
