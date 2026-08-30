"""Offline governance assistance generator.

The generator is intentionally provider-neutral.  A later adapter may use the
existing structured-model gateway, but this Task 2 default never makes a model
call and cannot alter readiness fields.
"""

# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Mapping

from fmea_application.revision_assembler import (
    PublicationReadinessReport,
    ReadinessChecklistDraft,
)


class OfflineGovernanceAssistanceGenerator:
    """Return a bounded checklist projection of a deterministic report."""

    def generate(self, report: PublicationReadinessReport) -> ReadinessChecklistDraft:
        if not isinstance(report, PublicationReadinessReport):
            raise TypeError("report must be a PublicationReadinessReport")
        checklist: tuple[Mapping[str, object], ...] = tuple(
            {
                "code": issue.code,
                "severity": issue.severity,
                "source_type": issue.source_type,
                "source_id": issue.source_id,
                "evidence_ids": list(issue.evidence_ids),
            }
            for issue in report.issues
        )
        return ReadinessChecklistDraft(
            ready=report.ready,
            blocking_codes=report.blocking_codes,
            checklist=checklist,
            revision_id=report.revision_id,
            revision_hash=report.revision_hash,
        )


GovernanceAssistanceGenerator = OfflineGovernanceAssistanceGenerator

__all__ = ["GovernanceAssistanceGenerator", "OfflineGovernanceAssistanceGenerator"]
