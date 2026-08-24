"""Semantic validation for an independently decoded critic report."""

from __future__ import annotations

from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_generation import (
    CriticReport,
    CriticVerdict,
    GenerationIssue,
    GenerationStage,
    SemanticSupport,
)
from core_domain.structured_output import CandidateClaim, ClaimState, StructuredCandidateBatch

_EVIDENCE_BEARING_STATES = frozenset(
    {ClaimState.KNOWN, ClaimState.CONFLICT, ClaimState.INSUFFICIENT_EVIDENCE}
)
_REPAIR_SUPPORT = frozenset({SemanticSupport.CONTRADICTED, SemanticSupport.NOT_SUPPORTED})


def _escape_pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _claim_pointer(candidate_id: str, target: str) -> str:
    return f"/candidates/{_escape_pointer_segment(candidate_id)}/claims{target}"


def _issue(code: str, message: str, pointer: str) -> GenerationIssue:
    return GenerationIssue(
        code=code,
        message=message,
        stage=GenerationStage.CRITIC,
        retryable=False,
        pointer=pointer,
    )


def _verdict_is_coherent(
    verdict: CriticVerdict,
    claim: CandidateClaim,
    support: SemanticSupport,
) -> bool:
    if claim.state is ClaimState.KNOWN and support in _REPAIR_SUPPORT:
        return verdict is CriticVerdict.REPAIR
    if (
        claim.state in {ClaimState.CONFLICT, ClaimState.INSUFFICIENT_EVIDENCE}
        or support is SemanticSupport.PARTIALLY_SUPPORTED
    ):
        return verdict is CriticVerdict.NEEDS_REVIEW
    return True


def validate_critic_report(
    report: CriticReport,
    batch: StructuredCandidateBatch,
    pack: EvidencePack,
) -> tuple[GenerationIssue, ...]:
    """Return stable issues without modifying the report, batch, or evidence pack."""

    claims: dict[tuple[str, str], CandidateClaim] = {
        (candidate.candidate_id, claim.target): claim
        for candidate in batch.candidates
        for claim in candidate.claims
    }
    expected = {
        identity: claim
        for identity, claim in claims.items()
        if claim.state in _EVIDENCE_BEARING_STATES and claim.evidence_ids
    }
    findings = {(finding.candidate_id, finding.target): finding for finding in report.findings}
    pack_evidence_ids = {ref.evidence_id for ref in pack.refs}
    issues: list[GenerationIssue] = []

    for candidate_id, target in expected:
        if (candidate_id, target) not in findings:
            issues.append(
                _issue(
                    "CRITIC_FINDING_MISSING",
                    "A required critic finding is missing.",
                    _claim_pointer(candidate_id, target),
                )
            )

    for identity, finding in findings.items():
        candidate_id, target = identity
        pointer = _claim_pointer(candidate_id, target)
        found_claim = claims.get(identity)
        if found_claim is None or identity not in expected:
            issues.append(
                _issue(
                    "CRITIC_CLAIM_INVALID",
                    "A critic finding does not identify an evidence-bearing claim.",
                    pointer,
                )
            )
            continue

        finding_evidence = set(finding.evidence_ids)
        if (
            not finding_evidence
            or not finding_evidence.issubset(found_claim.evidence_ids)
            or not finding_evidence.issubset(pack_evidence_ids)
        ):
            issues.append(
                _issue(
                    "CRITIC_EVIDENCE_INVALID",
                    "A critic finding cites evidence outside its claim or evidence pack.",
                    pointer,
                )
            )

        if not _verdict_is_coherent(report.verdict, found_claim, finding.support):
            issues.append(
                _issue(
                    "CRITIC_VERDICT_INVALID",
                    "The critic verdict is inconsistent with claim state or semantic support.",
                    pointer,
                )
            )

    return tuple(sorted(issues, key=lambda issue: (issue.pointer, issue.code, issue.message)))


__all__ = ["validate_critic_report"]
