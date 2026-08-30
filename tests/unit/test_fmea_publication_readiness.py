from __future__ import annotations

import pytest
from fmea_governance_fixtures import (
    make_blocked_readiness_report,
    make_domain_policy,
    make_fmea_revision,
    make_readiness_context,
    make_readiness_issue,
)


def _implementation():
    try:
        from fmea_application.revision_assembler import (
            PublicationReadinessContext,
            PublicationReadinessPolicy,
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"Task 2 production implementation is missing: {exc}")
    return PublicationReadinessContext, PublicationReadinessPolicy


def test_high_risk_unresolved_propagation_blocks_approval():
    _, PublicationReadinessPolicy = _implementation()
    revision = make_fmea_revision(
        unresolved_items=(
            make_readiness_issue(code="PROPAGATION_HIGH_RISK_UNRESOLVED", severity="critical"),
        )
    )
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(revision, make_readiness_context())
    assert not report.ready
    assert report.blocking_codes == ("PROPAGATION_HIGH_RISK_UNRESOLVED",)


def test_active_mutating_run_blocks_readiness():
    _, PublicationReadinessPolicy = _implementation()
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(
        make_fmea_revision(),
        make_readiness_context(active_run_ids=("propagation-run-1",)),
    )
    assert report.blocking_codes == ("ACTIVE_MUTATION_RUN",)


def test_stale_child_hash_blocks_readiness():
    PublicationReadinessContext, PublicationReadinessPolicy = _implementation()
    revision = make_fmea_revision()
    context = PublicationReadinessContext(
        active_run_ids=(),
        current_analysis_version=revision.analysis_record_version,
        current_child_hashes=(("row-1", "b" * 64),),
    )
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(revision, context)
    assert "STALE_CHILD_VERSION" in report.blocking_codes


def test_unacknowledged_critical_issue_blocks_even_when_other_gates_pass():
    _, PublicationReadinessPolicy = _implementation()
    revision = make_fmea_revision(
        unresolved_items=(make_readiness_issue(code="CRITICAL_GAP", severity="critical"),)
    )
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(revision, make_readiness_context())
    assert report.ready is False
    assert report.blocking_codes == ("CRITICAL_GAP",)


def test_policy_accepts_a_frozen_context_and_returns_a_frozen_report():
    PublicationReadinessContext, PublicationReadinessPolicy = _implementation()
    context = PublicationReadinessContext(
        active_run_ids=(),
        current_analysis_version=1,
        current_child_hashes=(),
    )
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(make_fmea_revision(), context)
    with pytest.raises((AttributeError, TypeError)):
        report.ready = False  # type: ignore[misc]


def test_mapping_report_shape_is_stable_for_blocked_inputs():
    _, PublicationReadinessPolicy = _implementation()
    issue = make_readiness_issue(code="MISSING_EVIDENCE", severity="blocking")
    revision = make_fmea_revision(unresolved_items=(issue,))
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(
        revision,
        make_readiness_context(required_fields_accepted=True),
    )
    expected = make_blocked_readiness_report()
    assert report.ready is expected["ready"]
    assert issue in report.issues
