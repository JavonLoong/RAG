from __future__ import annotations

import inspect

from fmea_application.ports import GovernanceRepository

EXPECTED_METHODS = {
    "replay_revision",
    "commit_revision",
    "get_revision",
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
    "get_snapshot",
    "list_approval_events",
    "list_publication_events",
}


def test_governance_repository_port_exposes_the_immutable_lifecycle() -> None:
    assert set(GovernanceRepository.__dict__) >= EXPECTED_METHODS
    for method_name in EXPECTED_METHODS:
        assert inspect.isfunction(getattr(GovernanceRepository, method_name))
