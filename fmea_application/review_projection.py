"""Build immutable, review-safe projections from FMEA persistence values."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import replace
from typing import cast

from core_domain.fmea.entities import FmeaRow
from core_domain.fmea.states import ClaimStatus, EvidenceSupportStatus
from core_domain.fmea.value_objects import EvidencePack, EvidenceRef
from core_domain.query_contracts import CitationType, EvidenceSelectionProfile

from .review_contracts import (
    EDITABLE_REVIEW_FIELDS,
    FieldReviewState,
    RetrievalProvenance,
    ReviewContext,
    ReviewDecisionRecord,
    ReviewEvidenceProjection,
    ReviewEvidenceRef,
    ReviewSourceSnapshot,
    ReviewSuggestion,
)

_FIELD_ORDER = tuple(sorted(EDITABLE_REVIEW_FIELDS))
_CLAIM_PRIORITY = {
    ClaimStatus.KNOWN: 0,
    ClaimStatus.NOT_APPLICABLE: 1,
    ClaimStatus.UNKNOWN: 2,
    ClaimStatus.INSUFFICIENT_EVIDENCE: 3,
    ClaimStatus.CONFLICT: 4,
}
_SOURCE_TYPE_MAP = {
    "rag_text": CitationType.TEXT,
    "graphrag_relation": CitationType.GRAPH,
    "graphrag_community": CitationType.COMMUNITY,
    "primary_document": CitationType.TEXT,
    "text": CitationType.TEXT,
    "graph": CitationType.GRAPH,
    "community": CitationType.COMMUNITY,
}
_SENSITIVE_LOCATOR_KEYS = frozenset({"file", "path", "url", "uri", "database", "db"})
_WARNING_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_UNSAFE_LOCATOR = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\|^//|\.\.|file://|https?://)")
_RAW_PACK_HASH = re.compile(r"^[0-9a-f]{64}$")
_STRICT_PACK_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


class _ProjectedReviewContext(ReviewContext):
    """Add the small lookup convenience used by review consumers."""

    __slots__ = ()

    def field_by_name(self, target_field: str) -> FieldReviewState:
        for field_review in self.field_reviews:
            if field_review.target_field == target_field:
                return field_review
        raise KeyError(target_field)


def build_review_context(
    row: FmeaRow,
    source: ReviewSourceSnapshot | None,
    pack: EvidencePack,
    suggestions: tuple[ReviewSuggestion, ...],
    decisions: tuple[ReviewDecisionRecord, ...],
) -> ReviewContext:
    """Project a row and its immutable review history without mutating inputs."""

    field_reviews = _fold_field_reviews(row, source, decisions)
    aggregate_claim = _aggregate_claim_status(field_review.claim_status for field_review in field_reviews)
    projected_row = replace(row, claim_status=aggregate_claim)
    ordered_decisions = tuple(sorted(decisions, key=_decision_order))
    latest_suggestion = max(suggestions, key=_suggestion_order, default=None)
    evidence = _project_evidence(row, suggestions, ordered_decisions, pack)
    retrieval, warnings, reviewability, item_label, function_label = _project_retrieval(row, source, pack)
    return _ProjectedReviewContext(
        row=projected_row,
        item_label=item_label,
        function_label=function_label,
        reviewability=reviewability,
        field_reviews=field_reviews,
        evidence=evidence,
        retrieval=retrieval,
        latest_suggestion=latest_suggestion,
        decision_history=ordered_decisions,
        warnings=warnings,
    )


def _fold_field_reviews(
    row: FmeaRow,
    source: ReviewSourceSnapshot | None,
    decisions: tuple[ReviewDecisionRecord, ...],
) -> tuple[FieldReviewState, ...]:
    evidence_by_field = dict(row.field_evidence)
    support_by_field = dict(row.field_support)
    claim_by_field = dict(source.field_claim_statuses) if source is not None else {}
    states: dict[str, FieldReviewState] = {}
    for field_name in _FIELD_ORDER:
        value = cast(str | tuple[str, ...], getattr(row, field_name))
        states[field_name] = FieldReviewState(
            target_field=field_name,
            value=value,
            claim_status=claim_by_field.get(field_name, row.claim_status),
            support_status=support_by_field.get(field_name, EvidenceSupportStatus.NOT_SUPPORTED),
            evidence_ids=evidence_by_field.get(field_name, ()),
            last_decision_id=None,
        )

    seen_decisions: set[str] = set()
    for decision in sorted(decisions, key=_decision_order):
        if decision.decision_id in seen_decisions:
            continue
        seen_decisions.add(decision.decision_id)
        for edit in decision.edits:
            states[edit.target_field] = FieldReviewState(
                target_field=edit.target_field,
                value=edit.value,
                claim_status=edit.claim_status,
                support_status=edit.support_status,
                evidence_ids=edit.evidence_ids,
                last_decision_id=decision.decision_id,
            )
    return tuple(states[field_name] for field_name in _FIELD_ORDER)


def _decision_order(decision: ReviewDecisionRecord) -> tuple[int, str, str]:
    return decision.record_version, decision.created_at, decision.decision_id


def _suggestion_order(suggestion: ReviewSuggestion) -> tuple[str, str]:
    return suggestion.created_at, suggestion.suggestion_id


def _aggregate_claim_status(statuses: Iterable[ClaimStatus]) -> ClaimStatus:
    return max(statuses, key=lambda status: _CLAIM_PRIORITY[status], default=ClaimStatus.UNKNOWN)


def _project_retrieval(
    row: FmeaRow,
    source: ReviewSourceSnapshot | None,
    pack: EvidencePack,
) -> tuple[RetrievalProvenance, tuple[str, ...], bool, str, str]:
    if source is None:
        warnings: tuple[str, ...] = ("FMEA_REVIEW_SOURCE_MISSING",)
        evidence_types = _infer_evidence_types(pack.refs)
        retrieval = RetrievalProvenance(
            requested_profile=EvidenceSelectionProfile.CUSTOM,
            resolved_profile=EvidenceSelectionProfile.CUSTOM,
            evidence_types=evidence_types,
            trace_id="legacy:" + row.row_id,
            warnings=warnings,
            incomplete=True,
        )
        return retrieval, warnings, False, row.item_id, row.function_id

    warnings = _stable_warning_codes(source.retrieval_warnings)
    evidence_types = source.evidence_types
    incomplete = source.retrieval_incomplete
    if source.resolved_evidence_profile is EvidenceSelectionProfile.CUSTOM and not evidence_types and not warnings:
        warnings = ("FMEA_REVIEW_EVIDENCE_TYPES_EMPTY",)
        incomplete = True
    retrieval = RetrievalProvenance(
        requested_profile=source.requested_evidence_profile,
        resolved_profile=source.resolved_evidence_profile,
        evidence_types=evidence_types,
        trace_id=source.trace_id,
        warnings=warnings,
        incomplete=incomplete,
    )
    return retrieval, warnings, True, source.item_label, source.function_label


def _stable_warning_codes(warnings: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for warning in warnings:
        code = warning.split(":", 1)[0].strip().upper()
        if _WARNING_CODE.fullmatch(code) is not None and code not in result:
            result.append(code)
    return tuple(result)


def _infer_evidence_types(refs: Iterable[EvidenceRef]) -> tuple[CitationType, ...]:
    result: list[CitationType] = []
    for ref in refs:
        citation_type = _SOURCE_TYPE_MAP.get(ref.source_type)
        if citation_type is not None and citation_type not in result:
            result.append(citation_type)
    return tuple(result)


def _project_evidence(
    row: FmeaRow,
    suggestions: tuple[ReviewSuggestion, ...],
    decisions: tuple[ReviewDecisionRecord, ...],
    pack: EvidencePack,
) -> ReviewEvidenceProjection:
    evidence_ids: set[str] = {evidence_id for _, ids in row.field_evidence for evidence_id in ids}
    for suggestion in suggestions:
        evidence_ids.update(_suggestion_evidence_ids(suggestion))
    for decision in decisions:
        evidence_ids.update(edit_evidence_id for edit in decision.edits for edit_evidence_id in edit.evidence_ids)
    refs = tuple(_project_evidence_ref(ref) for ref in pack.refs if ref.evidence_id in evidence_ids)
    return ReviewEvidenceProjection(
        pack_id=pack.pack_id,
        pack_hash=_normalize_pack_hash(pack.pack_hash),
        expires_at=pack.expires_at,
        refs=refs,
    )


def _suggestion_evidence_ids(suggestion: ReviewSuggestion) -> set[str]:
    evidence_ids = {evidence_id for finding in suggestion.field_findings for evidence_id in finding.evidence_ids}
    evidence_ids.update(evidence_id for edit in suggestion.proposed_edits for evidence_id in edit.evidence_ids)
    evidence_ids.update(evidence_id for conflict in suggestion.conflicts for evidence_id in conflict.evidence_ids)
    return evidence_ids


def _project_evidence_ref(ref: EvidenceRef) -> ReviewEvidenceRef:
    return ReviewEvidenceRef(
        evidence_id=ref.evidence_id,
        source_type=ref.source_type,
        source_trust=ref.source_trust,
        is_primary=ref.is_primary,
        locator=_sanitize_locator(ref.locator),
        quote=ref.quote[:4000],
    )


def _sanitize_locator(locator: str) -> str:
    try:
        parsed = json.loads(locator)
    except (json.JSONDecodeError, TypeError):
        return locator if _UNSAFE_LOCATOR.search(locator) is None else "redacted"
    if not isinstance(parsed, dict | list):
        return locator if _UNSAFE_LOCATOR.search(locator) is None else "redacted"
    sanitized = _sanitize_json_locator(parsed)
    return json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sanitize_json_locator(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_json_locator(item)
            for key, item in value.items()
            if str(key).lower() not in _SENSITIVE_LOCATOR_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_json_locator(item) for item in value]
    return value


def _normalize_pack_hash(pack_hash: str) -> str:
    if not isinstance(pack_hash, str):
        raise ValueError("invalid pack_hash")  # noqa: TRY003,TRY004
    if _STRICT_PACK_HASH.fullmatch(pack_hash) is not None:
        return pack_hash
    if _RAW_PACK_HASH.fullmatch(pack_hash) is not None:
        return "sha256:" + pack_hash
    raise ValueError("pack_hash must be a raw or sha256-prefixed lowercase SHA-256 hash")  # noqa: TRY003


__all__ = ["build_review_context"]
