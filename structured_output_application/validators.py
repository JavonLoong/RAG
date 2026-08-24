"""Deterministic validation of structured candidates against one EvidencePack."""

from __future__ import annotations

from dataclasses import replace

from core_domain.fmea.value_objects import EvidencePack, EvidenceRef
from core_domain.structured_output import (
    CandidateClaim,
    CandidateValidationReport,
    ClaimState,
    CompiledTemplate,
    EvidenceBinding,
    StructuredCandidateBatch,
    StructuredOutputError,
    TemplateLimits,
    ValidationIssue,
    expand_pattern,
    pattern_matches,
    resolve_pointer,
    validate_json_value,
)

from .ports import SchemaValidatorPort


def _issue(
    code: str,
    message: str,
    pointer: str,
    *,
    candidate_id: str | None = None,
    target: str | None = None,
    binding: str | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        pointer=pointer,
        candidate_id=candidate_id,
        target=target,
        binding=binding,
    )


class StructuredCandidateValidator:
    def __init__(
        self,
        schema_validator: SchemaValidatorPort,
        *,
        limits: TemplateLimits | None = None,
    ) -> None:
        self._schema_validator = schema_validator
        self._limits = limits or TemplateLimits()

    @staticmethod
    def _report(
        batch: StructuredCandidateBatch,
        ranked_issues: list[tuple[int, ValidationIssue]],
    ) -> CandidateValidationReport:
        sorted_issues = tuple(
            issue
            for _, issue in sorted(
                ranked_issues,
                key=lambda item: (
                    item[0],
                    item[1].target or item[1].pointer,
                    item[1].code,
                    item[1].binding or "",
                ),
            )
        )
        return CandidateValidationReport(valid=not sorted_issues, issues=sorted_issues, batch=batch)

    def _identity_issues(
        self,
        batch: StructuredCandidateBatch,
        template: CompiledTemplate,
        evidence_pack: EvidencePack,
    ) -> list[tuple[int, ValidationIssue]]:
        issues: list[tuple[int, ValidationIssue]] = []
        if (
            batch.template_id != template.metadata.template_id
            or batch.template_version != template.metadata.version
        ):
            issues.append(
                (
                    -1,
                    _issue(
                        "TEMPLATE_NOT_FOUND",
                        "Candidate batch does not target this template version.",
                        "/template_id",
                    ),
                )
            )
        elif batch.template_hash != template.template_hash:
            issues.append(
                (
                    -1,
                    _issue(
                        "TEMPLATE_HASH_MISMATCH",
                        "Candidate batch template hash does not match.",
                        "/template_hash",
                    ),
                )
            )
        if batch.evidence_pack_id != evidence_pack.pack_id:
            issues.append(
                (
                    -1,
                    _issue(
                        "EVIDENCE_PACK_MISMATCH",
                        "Candidate batch does not target this evidence pack.",
                        "/evidence_pack_id",
                    ),
                )
            )
        return issues

    def validate(  # noqa: C901 - ordered validation phases intentionally remain explicit
        self,
        batch: StructuredCandidateBatch,
        template: CompiledTemplate,
        evidence_pack: EvidencePack,
    ) -> CandidateValidationReport:
        ranked_issues = self._identity_issues(batch, template, evidence_pack)
        if ranked_issues:
            return self._report(batch, ranked_issues)
        if len(batch.candidates) > self._limits.max_candidates:
            ranked_issues.append(
                (
                    -1,
                    _issue(
                        "TEMPLATE_LIMIT_EXCEEDED",
                        "Candidate count exceeds the configured limit.",
                        "/candidates",
                    ),
                )
            )
            return self._report(batch, ranked_issues)

        refs_by_id = {ref.evidence_id: ref for ref in evidence_pack.refs}
        for candidate_index, candidate in enumerate(batch.candidates):
            candidate_id = candidate.candidate_id
            if len(candidate.claims) > self._limits.max_claims_per_candidate:
                ranked_issues.append(
                    (
                        candidate_index,
                        _issue(
                            "TEMPLATE_LIMIT_EXCEEDED",
                            "Claim count exceeds the configured limit.",
                            "/claims",
                            candidate_id=candidate_id,
                        ),
                    )
                )
                continue
            try:
                validate_json_value(candidate.payload, self._limits)
            except StructuredOutputError as exc:
                code = exc.code if exc.code == "TEMPLATE_LIMIT_EXCEEDED" else "CANDIDATE_SCHEMA_INVALID"
                ranked_issues.append(
                    (
                        candidate_index,
                        _issue(
                            code,
                            "Candidate payload is not a valid bounded JSON value.",
                            exc.pointer,
                            candidate_id=candidate_id,
                        ),
                    )
                )
                continue

            for schema_issue in self._schema_validator.validate(
                candidate.payload,
                template.output_schema,
            ):
                ranked_issues.append(
                    (
                        candidate_index,
                        replace(schema_issue, candidate_id=candidate_id),
                    )
                )

            claim_bindings: dict[str, EvidenceBinding] = {}
            for claim in candidate.claims:
                try:
                    resolve_pointer(candidate.payload, claim.target)
                except StructuredOutputError:
                    ranked_issues.append(
                        (
                            candidate_index,
                            _issue(
                                "CANDIDATE_TARGET_INVALID",
                                "Claim target does not resolve in the candidate payload.",
                                claim.target,
                                candidate_id=candidate_id,
                                target=claim.target,
                            ),
                        )
                    )
                    continue
                matches = tuple(
                    binding
                    for binding in template.evidence_bindings
                    if pattern_matches(binding.target, claim.target)
                )
                if len(matches) != 1:
                    ranked_issues.append(
                        (
                            candidate_index,
                            _issue(
                                "CANDIDATE_BINDING_AMBIGUOUS",
                                "Claim target must match exactly one evidence binding.",
                                claim.target,
                                candidate_id=candidate_id,
                                target=claim.target,
                            ),
                        )
                    )
                    continue
                claim_bindings[claim.target] = matches[0]

            claim_targets = {claim.target for claim in candidate.claims}
            for binding in template.evidence_bindings:
                if binding.requirement != "required":
                    continue
                for target in expand_pattern(candidate.payload, binding.target):
                    if target not in claim_targets:
                        ranked_issues.append(
                            (
                                candidate_index,
                                _issue(
                                    "CANDIDATE_EVIDENCE_MISSING",
                                    "Required payload target has no claim.",
                                    target,
                                    candidate_id=candidate_id,
                                    target=target,
                                    binding=binding.target,
                                ),
                            )
                        )

            for claim in candidate.claims:
                matched_binding = claim_bindings.get(claim.target)
                if matched_binding is None:
                    continue
                self._validate_claim(
                    claim,
                    matched_binding,
                    refs_by_id,
                    candidate_index,
                    candidate_id,
                    ranked_issues,
                )
        return self._report(batch, ranked_issues)

    @staticmethod
    def _validate_claim(
        claim: CandidateClaim,
        binding: EvidenceBinding,
        refs_by_id: dict[str, EvidenceRef],
        candidate_index: int,
        candidate_id: str,
        ranked_issues: list[tuple[int, ValidationIssue]],
    ) -> None:
        existing_refs = tuple(
            ref for evidence_id in claim.evidence_ids if (ref := refs_by_id.get(evidence_id)) is not None
        )
        if len(existing_refs) != len(claim.evidence_ids):
            ranked_issues.append(
                (
                    candidate_index,
                    _issue(
                        "CANDIDATE_EVIDENCE_MISSING",
                        "Claim references evidence outside the current pack.",
                        claim.target,
                        candidate_id=candidate_id,
                        target=claim.target,
                        binding=binding.target,
                    ),
                )
            )
        if binding.allowed_source_types and any(
            ref.source_type not in binding.allowed_source_types for ref in existing_refs
        ):
            ranked_issues.append(
                (
                    candidate_index,
                    _issue(
                        "CANDIDATE_EVIDENCE_SOURCE_FORBIDDEN",
                        "Claim references a source type forbidden by its binding.",
                        claim.target,
                        candidate_id=candidate_id,
                        target=claim.target,
                        binding=binding.target,
                    ),
                )
            )

        ref_count = len(claim.evidence_ids)
        invalid_state = False
        if binding.requirement == "forbidden":
            invalid_state = claim.state not in {ClaimState.UNKNOWN, ClaimState.NOT_APPLICABLE} or ref_count > 0
        elif claim.state is ClaimState.KNOWN:
            invalid_state = ref_count < binding.min_refs or (
                binding.max_refs is not None and ref_count > binding.max_refs
            )
        elif claim.state is ClaimState.CONFLICT:
            invalid_state = ref_count < 2 or (
                binding.max_refs is not None and ref_count > binding.max_refs
            )
        elif claim.state in {ClaimState.UNKNOWN, ClaimState.NOT_APPLICABLE}:
            invalid_state = ref_count != 0
        elif claim.state is ClaimState.INSUFFICIENT_EVIDENCE:
            invalid_state = binding.max_refs is not None and ref_count > binding.max_refs
        if invalid_state:
            ranked_issues.append(
                (
                    candidate_index,
                    _issue(
                        "CANDIDATE_CLAIM_STATE_INVALID",
                        "Claim state and evidence count do not satisfy the binding.",
                        claim.target,
                        candidate_id=candidate_id,
                        target=claim.target,
                        binding=binding.target,
                    ),
                )
            )


__all__ = ["StructuredCandidateValidator"]
