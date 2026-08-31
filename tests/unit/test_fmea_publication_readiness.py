from __future__ import annotations

from contextlib import suppress
from dataclasses import replace

import pytest
from fmea_governance_fixtures import (
    make_blocked_readiness_report,
    make_domain_policy,
    make_fmea_revision,
    make_human_acknowledgement_reference,
    make_readiness_context,
    make_readiness_issue,
    make_runtime_readiness,
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
    revision = make_fmea_revision(
        unresolved_items=(make_readiness_issue(code="PROPAGATION_HIGH_RISK_UNRESOLVED", severity="critical"),)
    )
    policy, context = make_runtime_readiness()
    report = policy.evaluate(revision, context)
    assert not report.ready
    assert report.blocking_codes == ("PROPAGATION_HIGH_RISK_UNRESOLVED",)


def test_active_mutating_run_blocks_readiness():
    policy, context = make_runtime_readiness(active_run_ids=("propagation-run-1",))
    report = policy.evaluate(make_fmea_revision(), context)
    assert report.blocking_codes == ("ACTIVE_MUTATION_RUN",)


def test_bare_readiness_policy_fails_closed_without_runtime_authority():
    _, PublicationReadinessPolicy = _implementation()
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(make_fmea_revision(), make_readiness_context())
    assert report.ready is False
    assert "UNVERIFIED_GOVERNANCE_INPUTS" in report.blocking_codes


def test_caller_writable_runtime_marker_cannot_authorize_bare_readiness_policy():
    _, PublicationReadinessPolicy = _implementation()
    policy = PublicationReadinessPolicy(make_domain_policy())
    with suppress(AttributeError):
        policy._runtime_marker = object()  # type: ignore[attr-defined]

    report = policy.evaluate(make_fmea_revision(), make_readiness_context())
    assert report.ready is False
    assert "UNVERIFIED_GOVERNANCE_INPUTS" in report.blocking_codes


def test_public_readiness_policy_has_no_direct_authoritative_entrypoint():
    _, PublicationReadinessPolicy = _implementation()
    policy = PublicationReadinessPolicy(make_domain_policy())
    assert not hasattr(policy, "_evaluate_authoritative")


def test_readiness_policy_rejects_callable_authority_injection():
    _, PublicationReadinessPolicy = _implementation()
    with pytest.raises(TypeError):
        PublicationReadinessPolicy(make_domain_policy(), verifier=lambda _inputs: None)  # type: ignore[call-arg]


def test_stale_child_hash_blocks_readiness():
    revision = make_fmea_revision()
    policy, context = make_runtime_readiness(
        current_analysis_version=revision.analysis_record_version,
        current_child_hashes=(("row-1", "b" * 64),),
    )
    report = policy.evaluate(revision, context)
    assert "STALE_CHILD_VERSION" in report.blocking_codes


def test_unacknowledged_critical_issue_blocks_even_when_other_gates_pass():
    revision = make_fmea_revision(unresolved_items=(make_readiness_issue(code="CRITICAL_GAP", severity="critical"),))
    policy, context = make_runtime_readiness()
    report = policy.evaluate(revision, context)
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
    issue = make_readiness_issue(code="MISSING_EVIDENCE", severity="blocking")
    revision = make_fmea_revision(unresolved_items=(issue,))
    policy, context = make_runtime_readiness(required_fields_accepted=True)
    report = policy.evaluate(revision, context)
    expected = make_blocked_readiness_report()
    assert report.ready is expected.ready
    assert issue in report.issues


def test_policy_rejects_weakly_typed_domain_policy_values():
    from fmea_application.revision_assembler import GovernanceDomainPolicy

    with pytest.raises(TypeError, match="required_propagation"):
        GovernanceDomainPolicy(required_propagation="false")


def test_empty_acknowledgement_set_is_not_a_wildcard():
    issue = make_readiness_issue(
        code="ACK_REQUIRED",
        severity="critical",
        acknowledgement_decision_id="decision-1",
    )
    revision = make_fmea_revision(unresolved_items=(issue,))
    policy, context = make_runtime_readiness()
    report = policy.evaluate(revision, context)
    assert report.ready is False
    assert "ACK_REQUIRED" in report.blocking_codes


def test_assembler_does_not_invent_a_missing_graph_blocker_when_not_required(fixture_row):
    from fmea_governance_fixtures import make_governance_assembler, make_governance_inputs

    inputs = make_governance_inputs(
        rows=(fixture_row,),
        propagation_graph_revision=None,
        evidence_packs=(),
    )
    revision = make_governance_assembler(inputs).assemble(
        __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request(),
        inputs,
    )
    assert not any(issue.code == "PROPAGATION_NOT_CONFIRMED" for issue in revision.unresolved_items)


def test_missing_graph_can_be_ready_when_domain_policy_does_not_require_it(fixture_pack, fixture_row):
    from fmea_governance_fixtures import _artifacts_for_inputs, make_governance_assembler, make_governance_inputs

    from core_domain.fmea.states import ReviewStatus
    from fmea_application.revision_assembler import (
        GovernanceDomainPolicy,
    )

    row = replace(fixture_row, review_status=ReviewStatus.ACCEPTED)
    inputs = make_governance_inputs(
        rows=(row,),
        evidence_packs=(fixture_pack,),
        propagation_graph_revision=None,
    )
    revision = make_governance_assembler(inputs).assemble(
        __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request(),
        inputs,
    )
    policy, context = make_runtime_readiness(
        domain_policy=GovernanceDomainPolicy(required_risk=False, required_propagation=False),
        governance_inputs=inputs,
        authoritative_artifacts=_artifacts_for_inputs(inputs),
    )
    report = policy.evaluate(revision, context)
    assert report.ready is True
    assert "REQUIRED_PROPAGATION_NOT_CONFIRMED" not in report.blocking_codes


def test_missing_graph_blocks_when_domain_policy_requires_it(fixture_pack, fixture_row):
    from fmea_governance_fixtures import make_governance_assembler, make_governance_inputs

    from core_domain.fmea.states import ReviewStatus
    from fmea_application.revision_assembler import GovernanceDomainPolicy

    inputs = make_governance_inputs(
        rows=(replace(fixture_row, review_status=ReviewStatus.ACCEPTED),),
        evidence_packs=(fixture_pack,),
    )
    revision = make_governance_assembler(inputs).assemble(
        __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request(),
        inputs,
    )
    policy, context = make_runtime_readiness(
        domain_policy=GovernanceDomainPolicy(required_risk=False, required_propagation=True),
        governance_inputs=inputs,
    )
    report = policy.evaluate(revision, context)
    assert report.ready is False
    assert "REQUIRED_PROPAGATION_NOT_CONFIRMED" in report.blocking_codes


def test_domain_policy_rejects_unknown_fields():
    from fmea_application.revision_assembler import GovernanceDomainPolicy

    with pytest.raises(TypeError, match="unsupported"):
        GovernanceDomainPolicy.from_mapping({"required_propagation": False, "client_override": True})


def test_required_false_does_not_allow_omitting_a_declared_template():
    from fmea_application.revision_assembler import GovernanceDomainPolicy

    revision = make_fmea_revision(template_identities=())
    policy, context = make_runtime_readiness(domain_policy=GovernanceDomainPolicy(required_template=False))
    report = policy.evaluate(revision, context)
    assert report.ready is False
    assert "UNRESOLVED_ARTIFACT_IDENTITY" in report.blocking_codes


def test_only_exact_server_resolved_human_acknowledgement_can_clear_issue():
    issue = make_readiness_issue(
        code="ACK_REQUIRED",
        severity="critical",
        acknowledgement_decision_id="decision-1",
    )
    revision = make_fmea_revision(unresolved_items=(issue,))
    reference = make_human_acknowledgement_reference(
        issue_code=issue.code,
        issue_source_type=issue.source_type,
        issue_source_id=issue.source_id,
        revision_id=revision.revision_id,
        revision_record_version=revision.analysis_record_version,
        evidence_ids=issue.evidence_ids,
    )
    policy, context = make_runtime_readiness(acknowledgement_references=(reference,))
    report = policy.evaluate(revision, context)
    assert report.ready is True


@pytest.mark.parametrize(
    ("workspace_id", "analysis_id", "issue_source_id"),
    (
        ("ws-foreign", "analysis-1", "row-1"),
        ("ws-1", "analysis-foreign", "row-1"),
        ("ws-1", "analysis-1", "row-foreign"),
    ),
)
def test_foreign_acknowledgement_scope_or_issue_cannot_clear_blocker(workspace_id, analysis_id, issue_source_id):
    issue = make_readiness_issue(
        code="ACK_REQUIRED",
        severity="critical",
        acknowledgement_decision_id="decision-1",
    )
    revision = make_fmea_revision(unresolved_items=(issue,))
    reference = make_human_acknowledgement_reference(
        workspace_id=workspace_id,
        analysis_id=analysis_id,
        issue_code=issue.code,
        issue_source_type=issue.source_type,
        issue_source_id=issue_source_id,
        revision_id=revision.revision_id,
        revision_record_version=revision.analysis_record_version,
        evidence_ids=issue.evidence_ids,
    )
    policy, context = make_runtime_readiness(acknowledgement_references=(reference,))
    report = policy.evaluate(revision, context)
    assert report.ready is False
    assert "ACK_REQUIRED" in report.blocking_codes


def test_unknown_acknowledgement_decision_cannot_clear_blocker():
    issue = make_readiness_issue(
        code="ACK_REQUIRED",
        severity="critical",
        acknowledgement_decision_id="decision-1",
    )
    revision = make_fmea_revision(unresolved_items=(issue,))
    reference = make_human_acknowledgement_reference(
        decision_id="decision-unknown",
        issue_code=issue.code,
        issue_source_type=issue.source_type,
        issue_source_id=issue.source_id,
        revision_id=revision.revision_id,
        revision_record_version=revision.analysis_record_version,
        evidence_ids=issue.evidence_ids,
    )
    policy, context = make_runtime_readiness(acknowledgement_references=(reference,))
    report = policy.evaluate(revision, context)
    assert report.ready is False
