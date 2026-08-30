"""Offline governance assistance generator.

The generator is intentionally provider-neutral.  A later adapter may use the
existing structured-model gateway, but this Task 2 default never makes a model
call and cannot alter readiness fields.
"""

# ruff: noqa: TRY003

from __future__ import annotations

from collections.abc import Mapping

from fmea_application.revision_assembler import (
    ReadinessChecklistDraft,
    ReadinessChecklistProjection,
)


class OfflineGovernanceAssistanceGenerator:
    """Return a bounded checklist projection of a deterministic report."""

    def generate(self, projection: ReadinessChecklistProjection) -> ReadinessChecklistDraft:
        if not isinstance(projection, ReadinessChecklistProjection):
            raise TypeError("projection must be a ReadinessChecklistProjection")
        checklist: tuple[Mapping[str, object], ...] = tuple(
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
        return ReadinessChecklistDraft(
            ready=projection.ready,
            blocking_codes=projection.blocking_codes,
            checklist=checklist,
            revision_id=projection.revision_id,
            revision_hash=projection.revision_hash,
        )


GovernanceAssistanceGenerator = OfflineGovernanceAssistanceGenerator

__all__ = ["GovernanceAssistanceGenerator", "OfflineGovernanceAssistanceGenerator"]
