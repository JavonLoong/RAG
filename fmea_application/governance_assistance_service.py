"""Immutable, non-authoritative assistance for publication readiness."""

# The application contract uses concise ValueError/TypeError boundaries.
# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import fields
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from core_domain.fmea.governance import ReadinessIssue, canonical_hash, canonical_json_value
from core_domain.fmea.states import ActorType

from .assistance_contracts import AssistanceKind, AssistanceSuggestion
from .review_contracts import ActorContext
from .revision_assembler import (
    PublicationReadinessReport,
    ReadinessChecklistDraft,
)

Clock = Callable[[], str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class _ChecklistGenerator(Protocol):
    def generate(self, report: PublicationReadinessReport) -> ReadinessChecklistDraft | Mapping[str, object]: ...


def _issue_checklist(report: PublicationReadinessReport) -> tuple[Mapping[str, object], ...]:
    return tuple(
        {
            "code": issue.code,
            "severity": issue.severity,
            "source_type": issue.source_type,
            "source_id": issue.source_id,
            "evidence_ids": list(issue.evidence_ids),
            "acknowledgement_decision_id": issue.acknowledgement_decision_id,
        }
        for issue in report.issues
    )


def _coerce_report(value: PublicationReadinessReport | Mapping[str, object], workspace_id: str) -> PublicationReadinessReport:
    if isinstance(value, PublicationReadinessReport):
        if value.workspace_id != workspace_id:
            raise ValueError("readiness report workspace does not match actor workspace")
        return value
    if not isinstance(value, Mapping):
        raise TypeError("readiness report must be a PublicationReadinessReport or mapping")
    allowed = {field.name for field in fields(PublicationReadinessReport)}
    unknown = set(value).difference(allowed)
    if unknown:
        raise TypeError(f"readiness report contains unsupported fields: {sorted(unknown)}")
    issues = tuple(value.get("issues", ()))
    if any(not isinstance(issue, ReadinessIssue) for issue in issues):
        raise TypeError("readiness report issues must contain ReadinessIssue objects")
    blocking_codes = tuple(
        value.get(
            "blocking_codes",
            tuple(sorted({issue.code for issue in issues if issue.severity in {"blocking", "critical"}})),
        )
    )
    fallback_hash = canonical_hash(canonical_json_value(dict(value)))
    normalized = PublicationReadinessReport(
        revision_id=str(value.get("revision_id", "readiness-report")),
        workspace_id=str(value.get("workspace_id", workspace_id)),
        analysis_id=str(value.get("analysis_id", "analysis-unbound")),
        revision_hash=str(value.get("revision_hash", fallback_hash)),
        target_record_version=int(value.get("target_record_version", 1)),
        evidence_pack_ids=tuple(value.get("evidence_pack_ids", ("readiness-report",))),
        ready=bool(value.get("ready", False)),
        issues=issues,
        blocking_codes=blocking_codes,
        deterministic=bool(value.get("deterministic", True)),
    )
    if normalized.workspace_id != workspace_id:
        raise ValueError("readiness report workspace does not match actor workspace")
    return normalized


def _draft_from_mapping(value: Mapping[str, object], report: PublicationReadinessReport) -> ReadinessChecklistDraft:
    return ReadinessChecklistDraft(
        ready=bool(value.get("ready", report.ready)),
        blocking_codes=tuple(value.get("blocking_codes", report.blocking_codes)),
        checklist=tuple(value.get("checklist", _issue_checklist(report))),
        revision_id=str(value.get("revision_id", report.revision_id)),
        revision_hash=str(value.get("revision_hash", report.revision_hash)),
    )


class GovernanceAssistanceService:
    """Create a model-labelled checklist whose authority remains deterministic."""

    def __init__(self, generator: _ChecklistGenerator | None = None, clock: Clock = _utc_now) -> None:
        self._generator = generator
        self._clock = clock

    def suggest_readiness_checklist(
        self,
        report: PublicationReadinessReport | Mapping[str, object],
        actor: ActorContext,
    ) -> AssistanceSuggestion[Mapping[str, object]]:
        if not isinstance(actor, ActorContext):
            raise TypeError("actor must be an ActorContext")
        if actor.actor_type is not ActorType.MODEL:
            raise ValueError("readiness assistance requires a model actor")
        normalized_report = _coerce_report(report, actor.workspace_id)
        if self._generator is None:
            draft = ReadinessChecklistDraft(
                ready=normalized_report.ready,
                blocking_codes=normalized_report.blocking_codes,
                checklist=_issue_checklist(normalized_report),
                revision_id=normalized_report.revision_id,
                revision_hash=normalized_report.revision_hash,
            )
        else:
            generated = self._generator.generate(normalized_report)
            if isinstance(generated, ReadinessChecklistDraft):
                draft = generated
            elif isinstance(generated, Mapping):
                draft = _draft_from_mapping(generated, normalized_report)
            else:
                raise TypeError("governance assistance generator returned an invalid draft")
            if (
                draft.ready != normalized_report.ready
                or draft.blocking_codes != normalized_report.blocking_codes
                or draft.revision_id != normalized_report.revision_id
                or draft.revision_hash != normalized_report.revision_hash
            ):
                raise ValueError("model assistance cannot change deterministic readiness")
        payload: Mapping[str, object] = {
            "ready": normalized_report.ready,
            "blocking_codes": list(normalized_report.blocking_codes),
            "checklist": [dict(item) for item in draft.checklist],
        }
        prompt_hash = canonical_hash(
            {
                "kind": AssistanceKind.APPROVAL_READINESS_CHECKLIST.value,
                "revision_id": normalized_report.revision_id,
                "revision_hash": normalized_report.revision_hash,
                "blocking_codes": normalized_report.blocking_codes,
            }
        )
        model_hash = canonical_hash({"mode": "offline", "kind": AssistanceKind.APPROVAL_READINESS_CHECKLIST.value})
        evidence_ids = tuple(
            sorted({evidence_id for issue in normalized_report.issues for evidence_id in issue.evidence_ids})
        )
        return AssistanceSuggestion(
            suggestion_id=_new_id("readiness-checklist"),
            kind=AssistanceKind.APPROVAL_READINESS_CHECKLIST,
            workspace_id=normalized_report.workspace_id,
            target_type="fmea_revision_readiness",
            target_id=normalized_report.revision_id,
            target_record_version=normalized_report.target_record_version,
            evidence_pack_ids=normalized_report.evidence_pack_ids or ("readiness-report",),
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


__all__ = ["GovernanceAssistanceService"]
