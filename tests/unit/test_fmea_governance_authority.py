"""Authority and stale-binding tests for the governance application service."""

from __future__ import annotations

import pytest
from fmea_governance_fixtures import (
    make_approval_command,
    make_governance_actor,
    make_publish_command,
    make_runtime_readiness,
)

from core_domain.fmea.states import ActorType
from fmea_application.governance_service import RevisionGovernanceService
from fmea_application.review_errors import ReviewError


class _UnusedRepository:
    """Authority tests must fail before touching persistence."""


def _service() -> RevisionGovernanceService:
    policy, _context = make_runtime_readiness()
    return RevisionGovernanceService(
        _UnusedRepository(),
        assembler=None,
        readiness_policy=policy,
        source=None,
    )


def test_model_actor_cannot_approve_or_publish() -> None:
    service = _service()
    model_actor = make_governance_actor(actor_type=ActorType.MODEL, roles=frozenset())

    with pytest.raises(ReviewError, match="FMEA_GOVERNANCE_APPROVAL_FORBIDDEN") as approval_error:
        service.approve(make_approval_command(), model_actor)
    assert approval_error.value.code == "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN"

    with pytest.raises(ReviewError, match="FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN") as publication_error:
        service.publish(make_publish_command(), model_actor)
    assert publication_error.value.code == "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN"


def test_system_actor_cannot_perform_governance_authority_writes() -> None:
    service = _service()
    system_actor = make_governance_actor(actor_type=ActorType.SYSTEM, roles=frozenset({"approver", "publisher"}))

    with pytest.raises(ReviewError) as captured:
        service.approve(make_approval_command(), system_actor)
    assert captured.value.code == "FMEA_GOVERNANCE_APPROVAL_FORBIDDEN"


def test_approver_without_publisher_role_cannot_publish() -> None:
    service = _service()
    actor = make_governance_actor(roles=frozenset({"approver"}))

    with pytest.raises(ReviewError) as captured:
        service.publish(make_publish_command(), actor)
    assert captured.value.code == "FMEA_GOVERNANCE_PUBLICATION_FORBIDDEN"
