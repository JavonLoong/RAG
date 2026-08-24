from __future__ import annotations

from dataclasses import replace

import pytest

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_generation import (
    CriticFinding,
    CriticReport,
    CriticVerdict,
    SemanticSupport,
)
from core_domain.structured_output import CandidateClaim, ClaimState, StructuredCandidate, StructuredCandidateBatch
from structured_generation_application.critic_validation import validate_critic_report


def _batch(
    *,
    state: ClaimState = ClaimState.KNOWN,
    evidence_ids: tuple[str, ...] = ("ev-1",),
    candidate_ids: tuple[str, ...] = ("candidate-1",),
) -> StructuredCandidateBatch:
    candidates = tuple(
        StructuredCandidate(
            candidate_id=candidate_id,
            payload={"failure_mode": "pressure loss"},
            claims=(CandidateClaim(target="/failure_mode", state=state, evidence_ids=evidence_ids),),
        )
        for candidate_id in candidate_ids
    )
    return StructuredCandidateBatch(
        template_id="maintenance-checklist",
        template_version="1.0.0",
        template_hash="a" * 64,
        evidence_pack_id="pack-1",
        candidates=candidates,
    )


def _finding(
    *,
    candidate_id: str = "candidate-1",
    target: str = "/failure_mode",
    support: SemanticSupport = SemanticSupport.SUPPORTED,
    evidence_ids: tuple[str, ...] = ("ev-1",),
) -> CriticFinding:
    return CriticFinding(
        candidate_id=candidate_id,
        target=target,
        support=support,
        code="EVIDENCE_SUPPORTS_CLAIM",
        evidence_ids=evidence_ids,
        explanation="The cited evidence was checked.",
    )


def _report(
    *,
    verdict: CriticVerdict = CriticVerdict.ACCEPT,
    findings: tuple[CriticFinding, ...] | None = None,
) -> CriticReport:
    return CriticReport(
        verdict=verdict,
        findings=(_finding(),) if findings is None else findings,
        summary="Critic validation completed.",
    )


def test_critic_requires_exact_coverage_of_evidence_bearing_claims(fixture_pack: EvidencePack) -> None:
    report = CriticReport(verdict=CriticVerdict.ACCEPT, findings=(), summary="none")

    issues = validate_critic_report(report, _batch(), fixture_pack)

    assert [(issue.code, issue.pointer) for issue in issues] == [
        ("CRITIC_FINDING_MISSING", "/candidates/candidate-1/claims/failure_mode")
    ]


def test_critic_cannot_cite_another_claim_or_pack(fixture_pack: EvidencePack) -> None:
    report = _report(findings=(_finding(evidence_ids=("ev-outside",)),))

    assert {issue.code for issue in validate_critic_report(report, _batch(), fixture_pack)} == {
        "CRITIC_EVIDENCE_INVALID"
    }


@pytest.mark.parametrize(
    ("finding", "expected_code"),
    [
        (_finding(candidate_id="candidate-outside"), "CRITIC_CLAIM_INVALID"),
        (_finding(target="/outside"), "CRITIC_CLAIM_INVALID"),
        (_finding(evidence_ids=()), "CRITIC_EVIDENCE_INVALID"),
    ],
)
def test_critic_rejects_unknown_claims_and_empty_evidence(
    fixture_pack: EvidencePack,
    finding: CriticFinding,
    expected_code: str,
) -> None:
    issues = validate_critic_report(_report(findings=(finding,)), _batch(), fixture_pack)

    assert expected_code in {issue.code for issue in issues}


@pytest.mark.parametrize(
    ("state", "support", "verdict"),
    [
        (ClaimState.KNOWN, SemanticSupport.CONTRADICTED, CriticVerdict.ACCEPT),
        (ClaimState.KNOWN, SemanticSupport.NOT_SUPPORTED, CriticVerdict.NEEDS_REVIEW),
        (ClaimState.KNOWN, SemanticSupport.PARTIALLY_SUPPORTED, CriticVerdict.ACCEPT),
        (ClaimState.CONFLICT, SemanticSupport.SUPPORTED, CriticVerdict.ACCEPT),
        (ClaimState.INSUFFICIENT_EVIDENCE, SemanticSupport.SUPPORTED, CriticVerdict.ACCEPT),
    ],
)
def test_critic_verdict_must_match_claim_state_and_support(
    fixture_pack: EvidencePack,
    state: ClaimState,
    support: SemanticSupport,
    verdict: CriticVerdict,
) -> None:
    evidence_ids = ("ev-1", "ev-2") if state is ClaimState.CONFLICT else ("ev-1",)
    if state is ClaimState.CONFLICT:
        second_ref = replace(fixture_pack.refs[0], evidence_id="ev-2", evidence_hash="b" * 64)
        fixture_pack = EvidencePack.build(
            pack_id=fixture_pack.pack_id,
            workspace_id=fixture_pack.workspace_id,
            acl_scope=fixture_pack.acl_scope,
            versions=fixture_pack.versions,
            refs=(fixture_pack.refs[0], second_ref),
            created_at=fixture_pack.created_at,
            expires_at=fixture_pack.expires_at,
        )
    finding = _finding(support=support, evidence_ids=evidence_ids)

    issues = validate_critic_report(
        _report(verdict=verdict, findings=(finding,)),
        _batch(state=state, evidence_ids=evidence_ids),
        fixture_pack,
    )

    assert "CRITIC_VERDICT_INVALID" in {issue.code for issue in issues}


def test_supported_known_claim_with_accepting_verdict_is_valid(fixture_pack: EvidencePack) -> None:
    report = _report()

    assert validate_critic_report(report, _batch(), fixture_pack) == ()


def test_claims_without_evidence_do_not_require_findings(fixture_pack: EvidencePack) -> None:
    report = CriticReport(verdict=CriticVerdict.ACCEPT, findings=(), summary="none")

    assert validate_critic_report(
        report,
        _batch(state=ClaimState.UNKNOWN, evidence_ids=()),
        fixture_pack,
    ) == ()


def test_critic_issue_order_is_stable_and_input_is_not_mutated(fixture_pack: EvidencePack) -> None:
    batch = _batch(candidate_ids=("candidate-b", "candidate-a"))
    report = CriticReport(verdict=CriticVerdict.ACCEPT, findings=(), summary="none")
    original_candidates = batch.candidates
    original_findings = report.findings

    issues = validate_critic_report(report, batch, fixture_pack)

    assert [issue.pointer for issue in issues] == [
        "/candidates/candidate-a/claims/failure_mode",
        "/candidates/candidate-b/claims/failure_mode",
    ]
    assert batch.candidates is original_candidates
    assert report.findings is original_findings
