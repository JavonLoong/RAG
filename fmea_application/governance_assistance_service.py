"""Immutable, non-authoritative assistance for publication readiness."""

# The application contract uses concise ValueError/TypeError boundaries.
# ruff: noqa: TRY003

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from core_domain.fmea.governance import canonical_hash
from core_domain.fmea.states import ActorType

from .assistance_contracts import AssistanceKind, AssistanceSuggestion
from .review_contracts import ActorContext
from .revision_assembler import (
    PublicationReadinessReport,
    ReadinessChecklistDraft,
    ReadinessChecklistProjection,
    ReadinessIssueProjection,
)

Clock = Callable[[], str]
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_DRAFT_FIELDS = {"ready", "blocking_codes", "checklist", "revision_id", "revision_hash"}
_CHECKLIST_FIELDS = {"code", "severity", "source_type", "source_id", "evidence_ids", "acknowledgement_decision_id"}
_SEVERITIES = {"info", "warning", "blocking", "critical"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _safe_identifier(value: str) -> str:
    if _SAFE_IDENTIFIER.fullmatch(value):
        return value
    return f"redacted-{canonical_hash(value)[:16]}"


def _safe_projection(report: PublicationReadinessReport) -> ReadinessChecklistProjection:
    return ReadinessChecklistProjection(
        revision_id=_safe_identifier(report.revision_id),
        revision_hash=report.revision_hash,
        target_record_version=report.target_record_version,
        ready=report.ready,
        blocking_codes=tuple(_safe_identifier(code) for code in report.blocking_codes),
        issues=tuple(
            ReadinessIssueProjection(
                code=_safe_identifier(issue.code),
                severity=issue.severity,
                source_type=_safe_identifier(issue.source_type),
                source_id=_safe_identifier(issue.source_id),
                evidence_ids=tuple(_safe_identifier(evidence_id) for evidence_id in issue.evidence_ids),
                acknowledgement_decision_id=(
                    None
                    if issue.acknowledgement_decision_id is None
                    else _safe_identifier(issue.acknowledgement_decision_id)
                ),
            )
            for issue in report.issues
        ),
        evidence_pack_ids=tuple(_safe_identifier(pack_id) for pack_id in report.evidence_pack_ids),
    )


class GovernanceAssistanceUnavailable(RuntimeError):
    """A generator is unavailable; deterministic offline output remains valid."""


class _ChecklistGenerator(Protocol):
    def generate(self, projection: ReadinessChecklistProjection) -> ReadinessChecklistDraft | Mapping[str, object]: ...


def _issue_checklist(projection: ReadinessChecklistProjection) -> tuple[Mapping[str, object], ...]:
    return tuple(
        {
            "code": issue.code,
            "severity": issue.severity,
            "source_type": issue.source_type,
            "source_id": issue.source_id,
            "evidence_ids": list(issue.evidence_ids),
            "acknowledgement_decision_id": issue.acknowledgement_decision_id,
        }
        for issue in projection.issues
    )


def _offline_draft(projection: ReadinessChecklistProjection) -> ReadinessChecklistDraft:
    return ReadinessChecklistDraft(
        ready=projection.ready,
        blocking_codes=projection.blocking_codes,
        checklist=_issue_checklist(projection),
        revision_id=projection.revision_id,
        revision_hash=projection.revision_hash,
    )


def _strict_text_sequence(value: object, label: str, limit: int) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or value is None:
        raise TypeError(f"{label} must be a sequence")
    items = tuple(value)  # type: ignore[arg-type]
    if len(items) > limit or any(not isinstance(item, str) or not _SAFE_IDENTIFIER.fullmatch(item) for item in items):
        raise ValueError(f"{label} is invalid or too large")
    return tuple(items)


def _validate_checklist_item(item: object) -> Mapping[str, object]:
    if not isinstance(item, Mapping):
        raise TypeError("checklist items must be mappings")
    if set(item) != _CHECKLIST_FIELDS:
        raise TypeError("checklist item schema is invalid")
    if not isinstance(item["severity"], str) or item["severity"] not in _SEVERITIES:
        raise ValueError("checklist item severity is invalid")
    for key in ("code", "source_type", "source_id"):
        if not isinstance(item[key], str) or _SAFE_IDENTIFIER.fullmatch(item[key]) is None:
            raise ValueError("checklist item identifier is unsafe")
    evidence_ids = _strict_text_sequence(item["evidence_ids"], "checklist evidence_ids", 64)
    acknowledgement = item["acknowledgement_decision_id"]
    if acknowledgement is not None and (
        not isinstance(acknowledgement, str) or _SAFE_IDENTIFIER.fullmatch(acknowledgement) is None
    ):
        raise ValueError("checklist acknowledgement identifier is unsafe")
    return {
        "code": item["code"],
        "severity": item["severity"],
        "source_type": item["source_type"],
        "source_id": item["source_id"],
        "evidence_ids": evidence_ids,
        "acknowledgement_decision_id": acknowledgement,
    }


def _draft_from_mapping(
    value: Mapping[str, object], projection: ReadinessChecklistProjection
) -> ReadinessChecklistDraft:
    if set(value) != _DRAFT_FIELDS:
        raise TypeError("governance assistance draft schema is invalid")
    if type(value["ready"]) is not bool:
        raise TypeError("generated ready must be a boolean")
    blocking_codes = _strict_text_sequence(value["blocking_codes"], "generated blocking_codes", 256)
    raw_checklist = value["checklist"]
    if isinstance(raw_checklist, str | bytes) or raw_checklist is None:
        raise TypeError("generated checklist must be a sequence")
    checklist = tuple(_validate_checklist_item(item) for item in tuple(raw_checklist))  # type: ignore[arg-type]
    if len(checklist) > 64:
        raise ValueError("generated checklist is too large")
    if not isinstance(value["revision_id"], str) or not isinstance(value["revision_hash"], str):
        raise TypeError("generated revision identity is invalid")
    return ReadinessChecklistDraft(
        ready=value["ready"],
        blocking_codes=blocking_codes,
        checklist=checklist,
        revision_id=value["revision_id"],
        revision_hash=value["revision_hash"],
    )


def _validate_draft(draft: ReadinessChecklistDraft, projection: ReadinessChecklistProjection) -> None:
    if (
        draft.ready != projection.ready
        or draft.blocking_codes != projection.blocking_codes
        or draft.revision_id != projection.revision_id
        or draft.revision_hash != projection.revision_hash
    ):
        raise ValueError("model assistance cannot change deterministic readiness")
    for item in draft.checklist:
        _validate_checklist_item(item)


class GovernanceAssistanceService:
    """Create a model-labelled checklist whose authority remains deterministic."""

    def __init__(self, generator: _ChecklistGenerator | None = None, clock: Clock = _utc_now) -> None:
        self._generator = generator
        self._clock = clock

    def suggest_readiness_checklist(
        self,
        report: PublicationReadinessReport,
        actor: ActorContext,
    ) -> AssistanceSuggestion[Mapping[str, object]]:
        if not isinstance(actor, ActorContext):
            raise TypeError("actor must be an ActorContext")
        if actor.actor_type is not ActorType.MODEL:
            raise ValueError("readiness assistance requires a model actor")
        if not isinstance(report, PublicationReadinessReport):
            raise TypeError("report must be a PublicationReadinessReport")
        if report.workspace_id != actor.workspace_id:
            raise ValueError("readiness report workspace does not match actor workspace")
        projection = _safe_projection(report)
        draft = _offline_draft(projection)
        if self._generator is not None:
            try:
                generated = self._generator.generate(projection)
                if isinstance(generated, ReadinessChecklistDraft):
                    draft = generated
                elif isinstance(generated, Mapping):
                    draft = _draft_from_mapping(generated, projection)
                else:
                    raise TypeError("governance assistance generator returned an invalid draft")
                _validate_draft(draft, projection)
            except (GovernanceAssistanceUnavailable, ConnectionError, TimeoutError, OSError):
                draft = _offline_draft(projection)
        payload: Mapping[str, object] = {
            "ready": report.ready,
            "blocking_codes": list(report.blocking_codes),
            "checklist": [dict(item) for item in draft.checklist],
        }
        prompt_hash = canonical_hash({
            "kind": AssistanceKind.APPROVAL_READINESS_CHECKLIST.value,
            "revision_id": report.revision_id,
            "revision_hash": report.revision_hash,
            "blocking_codes": report.blocking_codes,
        })
        model_hash = canonical_hash({"mode": "offline", "kind": AssistanceKind.APPROVAL_READINESS_CHECKLIST.value})
        evidence_ids = tuple(sorted({evidence_id for issue in projection.issues for evidence_id in issue.evidence_ids}))
        return AssistanceSuggestion(
            suggestion_id=_new_id("readiness-checklist"),
            kind=AssistanceKind.APPROVAL_READINESS_CHECKLIST,
            workspace_id=report.workspace_id,
            target_type="fmea_revision_readiness",
            target_id=report.revision_id,
            target_record_version=report.target_record_version,
            evidence_pack_ids=projection.evidence_pack_ids,
            payload=payload,
            evidence_ids=evidence_ids,
            model_hash=model_hash,
            prompt_hash=prompt_hash,
            run_id=_new_id("offline-readiness"),
            trace_id=_new_id("readiness-trace"),
            record_version=1,
            created_at=self._clock(),
            applied=False,
        )


__all__ = ["GovernanceAssistanceService", "GovernanceAssistanceUnavailable"]
