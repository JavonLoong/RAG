from __future__ import annotations

import inspect

from fmea_application.ports import GovernanceRepository

EXPECTED_METHODS = {
    "replay_revision",
    "commit_revision",
    "get_revision",
    "get_revision_record_version",
    "replay_readiness",
    "commit_readiness",
    "get_readiness",
    "get_approval_submission",
    "get_approval_decision",
    "get_approval_decision_for_submission",
    "get_approval_withdrawal",
    "replay_approval_submission",
    "commit_approval_submission",
    "replay_approval_decision",
    "commit_approval",
    "replay_approval_withdrawal",
    "commit_approval_withdrawal",
    "replay_publication",
    "commit_publication",
    "replay_publication_withdrawal",
    "commit_publication_withdrawal",
    "replay_supersession",
    "commit_supersession",
    "get_publication",
    "get_publication_lifecycle",
    "get_snapshot",
    "get_export_eligibility",
    "list_approval_events",
    "list_publication_events",
}


def test_governance_repository_port_exposes_the_immutable_lifecycle() -> None:
    assert set(GovernanceRepository.__dict__) >= EXPECTED_METHODS
    for method_name in EXPECTED_METHODS:
        assert inspect.isfunction(getattr(GovernanceRepository, method_name))


def test_governance_repository_port_exposes_workspace_qualified_current_reads() -> None:
    expected = {
        "get_revision_record_version": ("self", "revision_id", "workspace_id"),
        "get_approval_submission": ("self", "submission_id", "workspace_id"),
        "get_approval_decision": ("self", "approval_id", "workspace_id"),
        "get_approval_decision_for_submission": ("self", "submission_id", "workspace_id"),
        "get_approval_withdrawal": ("self", "approval_id", "workspace_id"),
        "get_publication_lifecycle": ("self", "publication_id", "workspace_id"),
    }
    for method_name, parameters in expected.items():
        assert tuple(inspect.signature(getattr(GovernanceRepository, method_name)).parameters) == parameters
