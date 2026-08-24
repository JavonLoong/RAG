"""Pure conservative adaptation from generic candidates to FMEA row suggestions."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from core_domain.fmea.entities import FmeaAnalysis, FmeaRow
from core_domain.fmea.errors import FmeaDomainError
from core_domain.fmea.states import (
    ClaimStatus,
    EvidenceSupportStatus,
    PublicationStatus,
    ReviewStatus,
)
from core_domain.fmea.value_objects import EvidencePack
from core_domain.structured_generation import (
    CriticReport,
    CriticVerdict,
    GenerationIssue,
    SemanticSupport,
)
from core_domain.structured_output import (
    ClaimState,
    CompiledTemplate,
    StructuredCandidate,
    StructuredCandidateBatch,
    StructuredOutputError,
    ValidationIssue,
    resolve_pointer,
)

FMEA_PROFILE_FIELDS = (
    ("item_id", "/item"),
    ("function_id", "/function"),
    ("failure_mode", "/failure_mode"),
    ("causes", "/causes"),
    ("mechanisms", "/mechanisms"),
    ("effects", "/effects"),
    ("symptoms", "/symptoms"),
    ("controls", "/controls"),
    ("barriers", "/barriers"),
    ("actions", "/actions"),
)

_ID = re.compile(r"^[a-z0-9._-]{1,128}$")
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_ARRAY_FIELDS = frozenset(
    {"causes", "mechanisms", "effects", "symptoms", "controls", "barriers", "actions"}
)
_CLAIM_PRIORITY = {
    ClaimStatus.KNOWN: 0,
    ClaimStatus.NOT_APPLICABLE: 1,
    ClaimStatus.UNKNOWN: 2,
    ClaimStatus.INSUFFICIENT_EVIDENCE: 3,
    ClaimStatus.CONFLICT: 4,
}
_CLAIM_MAP = {
    ClaimState.KNOWN: ClaimStatus.KNOWN,
    ClaimState.NOT_APPLICABLE: ClaimStatus.NOT_APPLICABLE,
    ClaimState.UNKNOWN: ClaimStatus.UNKNOWN,
    ClaimState.INSUFFICIENT_EVIDENCE: ClaimStatus.INSUFFICIENT_EVIDENCE,
    ClaimState.CONFLICT: ClaimStatus.CONFLICT,
}
_SUPPORT_MAP = {
    SemanticSupport.SUPPORTED: EvidenceSupportStatus.SUPPORTED,
    SemanticSupport.PARTIALLY_SUPPORTED: EvidenceSupportStatus.PARTIALLY_SUPPORTED,
    SemanticSupport.CONTRADICTED: EvidenceSupportStatus.CONTRADICTED,
    SemanticSupport.NOT_SUPPORTED: EvidenceSupportStatus.NOT_SUPPORTED,
}
_SUPPORT_PRIORITY = {
    EvidenceSupportStatus.SUPPORTED: 0,
    EvidenceSupportStatus.PARTIALLY_SUPPORTED: 1,
    EvidenceSupportStatus.CONTRADICTED: 2,
    EvidenceSupportStatus.NOT_SUPPORTED: 3,
}
_PROFILE_IDENTITY_ERROR = "FMEA profile identity is invalid"
_PROFILE_FIELDS_ERROR = "FMEA profile field mapping is invalid"
_REVIEW_FLAG_ERROR = "FMEA adaptation review flag is invalid"
_FIELD_UNRESOLVED_ERROR = "FMEA candidate field is unresolved"
_TEXT_UNRESOLVED_ERROR = "FMEA candidate text field is unresolved"
_ARRAY_UNRESOLVED_ERROR = "FMEA candidate array field is unresolved"
_PROFILE_TEMPLATE_ERROR = "FMEA profile does not match template identity"
_BATCH_TEMPLATE_ERROR = "FMEA candidate batch does not match template identity"
_BATCH_PACK_ERROR = "FMEA candidate batch does not match EvidencePack"
_REPAIR_COUNT_ERROR = "FMEA repair count is invalid"
_IDENTITY_FIELDS_ERROR = "FMEA candidate identity fields are invalid"


@dataclass(frozen=True, slots=True)
class FmeaTemplateProfile:
    profile_id: str
    version: str
    template_id: str
    template_version: str
    fields: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or _ID.fullmatch(self.profile_id) is None
            or not isinstance(self.template_id, str)
            or _ID.fullmatch(self.template_id) is None
            or not isinstance(self.version, str)
            or _SEMVER.fullmatch(self.version) is None
            or not isinstance(self.template_version, str)
            or _SEMVER.fullmatch(self.template_version) is None
        ):
            raise FmeaDomainError(_PROFILE_IDENTITY_ERROR)
        object.__setattr__(self, "fields", tuple(self.fields))
        if self.fields != FMEA_PROFILE_FIELDS:
            raise FmeaDomainError(_PROFILE_FIELDS_ERROR)


@dataclass(frozen=True, slots=True)
class FmeaAdaptationResult:
    rows: tuple[FmeaRow, ...]
    issues: tuple[GenerationIssue, ...]
    needs_review: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "issues", tuple(self.issues))
        if (
            any(not isinstance(row, FmeaRow) for row in self.rows)
            or any(not isinstance(issue, GenerationIssue) for issue in self.issues)
            or not isinstance(self.needs_review, bool)
        ):
            raise FmeaDomainError(_REVIEW_FLAG_ERROR)


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _matches(target: str, pointer: str) -> bool:
    return target == pointer or target.startswith(pointer + "/")


def _adaptation_issue(code: str, message: str, pointer: str) -> GenerationIssue:
    return GenerationIssue(code=code, message=message, pointer=pointer)


def _candidate_values(candidate: StructuredCandidate, profile: FmeaTemplateProfile) -> dict[str, object]:
    values: dict[str, object] = {}
    for field_name, pointer in profile.fields:
        try:
            value = resolve_pointer(candidate.payload, pointer)
        except StructuredOutputError as exc:
            raise FmeaDomainError(_FIELD_UNRESOLVED_ERROR) from exc
        if field_name in {"item_id", "function_id", "failure_mode"}:
            if not isinstance(value, str) or not value.strip():
                raise FmeaDomainError(_TEXT_UNRESOLVED_ERROR)
        elif field_name in _ARRAY_FIELDS and (
            not isinstance(value, list)
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise FmeaDomainError(_ARRAY_UNRESOLVED_ERROR)
        values[field_name] = value
    return values


def _field_evidence(
    candidate: StructuredCandidate,
    profile: FmeaTemplateProfile,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple(
        (
            field_name,
            tuple(
                sorted(
                    {
                        evidence_id
                        for claim in candidate.claims
                        if _matches(claim.target, pointer)
                        for evidence_id in claim.evidence_ids
                    }
                )
            ),
        )
        for field_name, pointer in profile.fields
    )


def _field_support(
    candidate: StructuredCandidate,
    profile: FmeaTemplateProfile,
    critic_report: CriticReport | None,
    repair_count: int,
) -> tuple[tuple[str, EvidenceSupportStatus], ...]:
    if critic_report is None or repair_count:
        return tuple((field_name, EvidenceSupportStatus.NOT_SUPPORTED) for field_name, _ in profile.fields)
    findings = tuple(
        finding for finding in critic_report.findings if finding.candidate_id == candidate.candidate_id
    )
    support: list[tuple[str, EvidenceSupportStatus]] = []
    for field_name, pointer in profile.fields:
        statuses = tuple(
            _SUPPORT_MAP[finding.support] for finding in findings if _matches(finding.target, pointer)
        )
        active = (
            max(statuses, key=lambda item: _SUPPORT_PRIORITY[item])
            if statuses
            else EvidenceSupportStatus.NOT_SUPPORTED
        )
        support.append((field_name, active))
    return tuple(support)


def _claim_status(
    candidate: StructuredCandidate,
    field_support: tuple[tuple[str, EvidenceSupportStatus], ...],
    *,
    critic_report: CriticReport | None,
    repair_count: int,
) -> ClaimStatus:
    statuses = [_CLAIM_MAP[claim.state] for claim in candidate.claims]
    active = max(statuses, key=lambda item: _CLAIM_PRIORITY[item]) if statuses else ClaimStatus.UNKNOWN
    support_values = {status for _, status in field_support}
    if EvidenceSupportStatus.CONTRADICTED in support_values:
        active = max((active, ClaimStatus.CONFLICT), key=lambda item: _CLAIM_PRIORITY[item])
    if (
        critic_report is None
        or repair_count
        or EvidenceSupportStatus.NOT_SUPPORTED in support_values
        or EvidenceSupportStatus.PARTIALLY_SUPPORTED in support_values
    ):
        active = max(
            (active, ClaimStatus.INSUFFICIENT_EVIDENCE),
            key=lambda item: _CLAIM_PRIORITY[item],
        )
    return active


class StructuredCandidateFmeaAdapter:
    def _validate_identities(
        self,
        *,
        template: CompiledTemplate,
        batch: StructuredCandidateBatch,
        evidence_pack: EvidencePack,
        profile: FmeaTemplateProfile,
        repair_count: int,
    ) -> None:
        if (
            profile.template_id != template.metadata.template_id
            or profile.template_version != template.metadata.version
        ):
            raise FmeaDomainError(_PROFILE_TEMPLATE_ERROR)
        if (
            batch.template_id != template.metadata.template_id
            or batch.template_version != template.metadata.version
            or batch.template_hash != template.template_hash
        ):
            raise FmeaDomainError(_BATCH_TEMPLATE_ERROR)
        if batch.evidence_pack_id != evidence_pack.pack_id:
            raise FmeaDomainError(_BATCH_PACK_ERROR)
        if not isinstance(repair_count, int) or isinstance(repair_count, bool) or repair_count not in {0, 1}:
            raise FmeaDomainError(_REPAIR_COUNT_ERROR)

    @staticmethod
    def _row(
        *,
        analysis: FmeaAnalysis,
        evidence_pack: EvidencePack,
        template: CompiledTemplate,
        candidate: StructuredCandidate,
        values: dict[str, object],
        profile: FmeaTemplateProfile,
        critic_report: CriticReport | None,
        repair_count: int,
    ) -> FmeaRow:
        item_text = values["item_id"]
        function_text = values["function_id"]
        failure_mode = values["failure_mode"]
        if not isinstance(item_text, str) or not isinstance(function_text, str) or not isinstance(failure_mode, str):
            raise FmeaDomainError(_IDENTITY_FIELDS_ERROR)
        item_id = "item-" + _digest(_normalized(item_text))
        function_id = "function-" + _digest(item_id + "|" + _normalized(function_text))
        evidence = _field_evidence(candidate, profile)
        support = _field_support(candidate, profile, critic_report, repair_count)
        arrays = {
            name: tuple(value) if isinstance(value, list) else ()
            for name, value in values.items()
            if name in _ARRAY_FIELDS
        }
        return FmeaRow(
            row_id="fmea-row-"
            + _digest(
                f"{analysis.analysis_id}|{template.template_hash}|{evidence_pack.pack_hash}|{candidate.candidate_id}"
            ),
            analysis_id=analysis.analysis_id,
            evidence_pack_id=evidence_pack.pack_id,
            item_id=item_id,
            function_id=function_id,
            failure_mode=failure_mode,
            causes=arrays["causes"],
            mechanisms=arrays["mechanisms"],
            effects=arrays["effects"],
            symptoms=arrays["symptoms"],
            controls=arrays["controls"],
            barriers=arrays["barriers"],
            actions=arrays["actions"],
            risk_assessment=None,
            field_evidence=evidence,
            field_support=support,
            claim_status=_claim_status(
                candidate,
                support,
                critic_report=critic_report,
                repair_count=repair_count,
            ),
            review_status=ReviewStatus.SUGGESTED,
            publication_status=PublicationStatus.UNPUBLISHED,
        )

    def adapt(
        self,
        *,
        analysis: FmeaAnalysis,
        evidence_pack: EvidencePack,
        template: CompiledTemplate,
        batch: StructuredCandidateBatch,
        critic_report: CriticReport | None,
        profile: FmeaTemplateProfile,
        repair_count: int,
        deterministic_issues: tuple[ValidationIssue, ...],
    ) -> FmeaAdaptationResult:
        self._validate_identities(
            template=template,
            batch=batch,
            evidence_pack=evidence_pack,
            profile=profile,
            repair_count=repair_count,
        )
        if deterministic_issues:
            deterministic_adaptation_issues = tuple(
                GenerationIssue(code=issue.code, message=issue.message, pointer=issue.pointer)
                for issue in deterministic_issues
            )
            return FmeaAdaptationResult(rows=(), issues=deterministic_adaptation_issues, needs_review=True)

        rows: list[FmeaRow] = []
        issues: list[GenerationIssue] = []
        semantic_keys: set[tuple[str, str, str]] = set()
        for candidate in sorted(batch.candidates, key=lambda item: item.candidate_id):
            try:
                values = _candidate_values(candidate, profile)
            except FmeaDomainError:
                issues.append(
                    _adaptation_issue(
                        "FMEA_FIELD_UNRESOLVED",
                        "A candidate cannot be resolved through the approved FMEA profile.",
                        f"/candidates/{candidate.candidate_id}",
                    )
                )
                continue
            semantic_key = (
                _normalized(str(values["item_id"])),
                _normalized(str(values["function_id"])),
                _normalized(str(values["failure_mode"])),
            )
            if semantic_key in semantic_keys:
                issues.append(
                    _adaptation_issue(
                        "FMEA_CANDIDATE_DUPLICATE",
                        "A semantically duplicate FMEA candidate was omitted.",
                        f"/candidates/{candidate.candidate_id}",
                    )
                )
                continue
            semantic_keys.add(semantic_key)
            rows.append(
                self._row(
                    analysis=analysis,
                    evidence_pack=evidence_pack,
                    template=template,
                    candidate=candidate,
                    values=values,
                    profile=profile,
                    critic_report=critic_report,
                    repair_count=repair_count,
                )
            )

        if critic_report is not None:
            mapped_candidates = {candidate.candidate_id: candidate for candidate in batch.candidates}
            for finding in critic_report.findings:
                found_candidate = mapped_candidates.get(finding.candidate_id)
                if found_candidate is None or not any(
                    _matches(finding.target, pointer) for _, pointer in profile.fields
                ):
                    issues.append(
                        _adaptation_issue(
                            "FMEA_CRITIC_FINDING_UNMAPPED",
                            "A critic finding is outside the approved FMEA field map.",
                            finding.target,
                        )
                    )

        sorted_issues = tuple(sorted(issues, key=lambda issue: (issue.pointer, issue.code)))
        safe_critic = critic_report is not None and critic_report.verdict is CriticVerdict.ACCEPT
        needs_review = (
            bool(sorted_issues)
            or repair_count > 0
            or not safe_critic
            or any(row.claim_status is not ClaimStatus.KNOWN for row in rows)
        )
        return FmeaAdaptationResult(rows=tuple(rows), issues=sorted_issues, needs_review=needs_review)


__all__ = [
    "FMEA_PROFILE_FIELDS",
    "FmeaAdaptationResult",
    "FmeaTemplateProfile",
    "StructuredCandidateFmeaAdapter",
]
