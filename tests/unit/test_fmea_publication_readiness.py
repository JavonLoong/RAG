from __future__ import annotations

from dataclasses import replace

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
        unresolved_items=(make_readiness_issue(code="PROPAGATION_HIGH_RISK_UNRESOLVED", severity="critical"),)
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
    revision = make_fmea_revision(unresolved_items=(make_readiness_issue(code="CRITICAL_GAP", severity="critical"),))
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
    assert report.ready is expected.ready
    assert issue in report.issues


def test_policy_rejects_weakly_typed_domain_policy_values():
    from fmea_application.revision_assembler import GovernanceDomainPolicy

    with pytest.raises(TypeError, match="required_propagation"):
        GovernanceDomainPolicy(required_propagation="false")


def test_empty_acknowledgement_set_is_not_a_wildcard():
    _, PublicationReadinessPolicy = _implementation()
    issue = make_readiness_issue(
        code="ACK_REQUIRED",
        severity="critical",
        acknowledgement_decision_id="decision-1",
    )
    revision = make_fmea_revision(unresolved_items=(issue,))
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(
        revision,
        make_readiness_context(),
    )
    assert report.ready is False
    assert "ACK_REQUIRED" in report.blocking_codes


def test_assembler_does_not_invent_a_missing_graph_blocker_when_not_required(fixture_row):
    from fmea_application.revision_assembler import RevisionAssembler

    revision = RevisionAssembler().assemble(
        __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request(),
        __import__("fmea_governance_fixtures", fromlist=["make_governance_inputs"]).make_governance_inputs(
            rows=(fixture_row,),
            propagation_graph_revision=None,
            evidence_packs=(),
        ),
    )
    assert not any(issue.code == "PROPAGATION_NOT_CONFIRMED" for issue in revision.unresolved_items)


def test_missing_graph_can_be_ready_when_domain_policy_does_not_require_it(fixture_pack, fixture_row):
    from core_domain.fmea.states import ReviewStatus
    from fmea_application.revision_assembler import (
        GovernanceDomainPolicy,
        PublicationReadinessPolicy,
        RevisionAssembler,
    )

    row = replace(fixture_row, review_status=ReviewStatus.ACCEPTED)
    revision = RevisionAssembler().assemble(
        __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request(),
        __import__("fmea_governance_fixtures", fromlist=["make_governance_inputs"]).make_governance_inputs(
            rows=(row,),
            evidence_packs=(fixture_pack,),
            propagation_graph_revision=None,
        ),
    )
    report = PublicationReadinessPolicy(
        GovernanceDomainPolicy(required_risk=False, required_propagation=False),
    ).evaluate(revision, make_readiness_context())
    assert report.ready is True
    assert "REQUIRED_PROPAGATION_NOT_CONFIRMED" not in report.blocking_codes


def test_missing_graph_blocks_when_domain_policy_requires_it(fixture_pack, fixture_row):
    from core_domain.fmea.states import ReviewStatus
    from fmea_application.revision_assembler import (
        GovernanceDomainPolicy,
        PublicationReadinessPolicy,
        RevisionAssembler,
    )

    revision = RevisionAssembler().assemble(
        __import__("fmea_governance_fixtures", fromlist=["make_assemble_request"]).make_assemble_request(),
        __import__("fmea_governance_fixtures", fromlist=["make_governance_inputs"]).make_governance_inputs(
            rows=(replace(fixture_row, review_status=ReviewStatus.ACCEPTED),),
            evidence_packs=(fixture_pack,),
        ),
    )
    report = PublicationReadinessPolicy(
        GovernanceDomainPolicy(required_risk=False, required_propagation=True),
    ).evaluate(revision, make_readiness_context())
    assert report.ready is False
    assert "REQUIRED_PROPAGATION_NOT_CONFIRMED" in report.blocking_codes


def test_domain_policy_rejects_unknown_fields():
    from fmea_application.revision_assembler import GovernanceDomainPolicy

    with pytest.raises(TypeError, match="unsupported"):
        GovernanceDomainPolicy.from_mapping({"required_propagation": False, "client_override": True})


def test_only_exact_server_resolved_human_acknowledgement_can_clear_issue():
    from core_domain.fmea.states import ActorType
    from fmea_application.revision_assembler import HumanAcknowledgementReference, PublicationReadinessPolicy

    issue = make_readiness_issue(
        code="ACK_REQUIRED",
        severity="critical",
        acknowledgement_decision_id="decision-1",
    )
    revision = make_fmea_revision(unresolved_items=(issue,))
    reference = HumanAcknowledgementReference(
        decision_id="decision-1",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        issue_code=issue.code,
        issue_source_type=issue.source_type,
        issue_source_id=issue.source_id,
        actor_id="reviewer-1",
        actor_type=ActorType.HUMAN,
        revision_id=revision.revision_id,
        revision_record_version=revision.analysis_record_version,
        evidence_ids=issue.evidence_ids,
    )
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(
        revision,
        make_readiness_context(acknowledgement_references=(reference,)),
    )
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
    from core_domain.fmea.states import ActorType
    from fmea_application.revision_assembler import HumanAcknowledgementReference, PublicationReadinessPolicy

    issue = make_readiness_issue(
        code="ACK_REQUIRED",
        severity="critical",
        acknowledgement_decision_id="decision-1",
    )
    revision = make_fmea_revision(unresolved_items=(issue,))
    reference = HumanAcknowledgementReference(
        decision_id="decision-1",
        workspace_id=workspace_id,
        analysis_id=analysis_id,
        issue_code=issue.code,
        issue_source_type=issue.source_type,
        issue_source_id=issue_source_id,
        actor_id="reviewer-1",
        actor_type=ActorType.HUMAN,
        revision_id=revision.revision_id,
        revision_record_version=revision.analysis_record_version,
        evidence_ids=issue.evidence_ids,
    )
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(
        revision,
        make_readiness_context(acknowledgement_references=(reference,)),
    )
    assert report.ready is False
    assert "ACK_REQUIRED" in report.blocking_codes


def test_unknown_acknowledgement_decision_cannot_clear_blocker():
    from core_domain.fmea.states import ActorType
    from fmea_application.revision_assembler import HumanAcknowledgementReference, PublicationReadinessPolicy

    issue = make_readiness_issue(
        code="ACK_REQUIRED",
        severity="critical",
        acknowledgement_decision_id="decision-1",
    )
    revision = make_fmea_revision(unresolved_items=(issue,))
    reference = HumanAcknowledgementReference(
        decision_id="decision-unknown",
        workspace_id="ws-1",
        analysis_id="analysis-1",
        issue_code=issue.code,
        issue_source_type=issue.source_type,
        issue_source_id=issue.source_id,
        actor_id="reviewer-1",
        actor_type=ActorType.HUMAN,
        revision_id=revision.revision_id,
        revision_record_version=revision.analysis_record_version,
        evidence_ids=issue.evidence_ids,
    )
    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(
        revision,
        make_readiness_context(acknowledgement_references=(reference,)),
    )
    assert report.ready is False
