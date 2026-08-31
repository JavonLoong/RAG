from __future__ import annotations

from contextlib import suppress
from dataclasses import replace
from inspect import signature

import pytest
from fmea_governance_fixtures import (
    make_assemble_request,
    make_fmea_revision,
    make_governance_assembler,
    make_governance_inputs,
)

from core_domain.fmea.entities import FmeaRow
from core_domain.fmea.states import ReviewStatus


def _implementation():
    try:
        from fmea_application.revision_assembler import RevisionAssembler
    except ModuleNotFoundError as exc:
        pytest.fail(f"Task 2 production implementation is missing: {exc}")
    return RevisionAssembler


def _row(fixture_row: FmeaRow, row_id: str) -> FmeaRow:
    return replace(fixture_row, row_id=row_id, review_status=ReviewStatus.ACCEPTED)


def _inputs(*, rows: tuple[FmeaRow, ...] = (), **overrides: object):
    values: dict[str, object] = {
        "rows": rows,
        "evidence_packs": (),
        "requested_profile": "combined",
        "resolved_profile": "combined",
        "evidence_types": ("graph", "text"),
    }
    values.update(overrides)
    return make_governance_inputs(
        **values,
    )


def test_revision_assembler_is_order_independent(fixture_row: FmeaRow):
    first_inputs = _inputs(rows=(_row(fixture_row, "row-b"), _row(fixture_row, "row-a")))
    second_inputs = _inputs(rows=(_row(fixture_row, "row-a"), _row(fixture_row, "row-b")))
    assembler = make_governance_assembler(first_inputs)
    first = assembler.assemble(
        make_assemble_request(),
        first_inputs,
    )
    second = make_governance_assembler(second_inputs).assemble(
        make_assemble_request(),
        second_inputs,
    )
    assert first.revision_hash == second.revision_hash


def test_revision_assembler_constructor_has_no_retrieval_dependency():
    RevisionAssembler = _implementation()
    assert set(signature(RevisionAssembler).parameters) <= {"self"}
    assert "verifier" not in signature(RevisionAssembler).parameters


def test_revision_assembler_rejects_callable_authority_injection():
    RevisionAssembler = _implementation()
    with pytest.raises(TypeError):
        RevisionAssembler(verifier=lambda _inputs: None)  # type: ignore[call-arg]


def test_revision_assembler_requires_a_runtime_bound_verifier():
    RevisionAssembler = _implementation()
    inputs = make_governance_inputs()
    with pytest.raises(TypeError, match="trusted governance runtime authority"):
        RevisionAssembler().assemble(make_assemble_request(), inputs)


def test_caller_writable_runtime_marker_cannot_authorize_bare_assembler():
    RevisionAssembler = _implementation()
    assembler = RevisionAssembler()
    with suppress(AttributeError):
        assembler._runtime_marker = object()  # type: ignore[attr-defined]

    with pytest.raises(TypeError, match="trusted governance runtime authority"):
        assembler.assemble(make_assemble_request(), make_governance_inputs())


def test_legacy_module_level_resolver_issuance_helpers_are_not_importable():
    import fmea_application.revision_assembler as revision_assembler

    assert not hasattr(revision_assembler, "_resolve_registry_artifact")
    assert not hasattr(revision_assembler, "_resolve_analysis_record")
    assert not hasattr(revision_assembler, "_resolve_acknowledgement_record")


def test_assembler_preserves_retrieval_provenance_without_retrieval_dependency():
    inputs = _inputs(
        requested_profile="graphrag_only",
        resolved_profile="graphrag_only",
        evidence_types=("graph", "community"),
    )
    revision = make_governance_assembler(inputs).assemble(make_assemble_request(), inputs)
    assert revision.retrieval_provenance.resolved_profile == "graphrag_only"
    assert revision.retrieval_provenance.evidence_types == ("community", "graph")


def test_assembler_rejects_mixed_workspace_records(fixture_row: FmeaRow):
    foreign_row = replace(_row(fixture_row, "row-foreign"), analysis_id="analysis-2")
    with pytest.raises(ValueError, match="analysis"):
        _inputs(rows=(foreign_row,))


def test_assembler_does_not_accept_client_resource_overrides():
    inputs = _inputs()
    with pytest.raises(TypeError):
        make_governance_assembler(inputs).assemble(make_assemble_request(), {"workspace_id": "ws-1"})


def test_assembler_rejects_mapping_governance_inputs():
    RevisionAssembler = _implementation()
    with pytest.raises(TypeError, match="GovernanceInputs"):
        RevisionAssembler().assemble(make_assemble_request(), {"workspace_id": "ws-1"})


def test_caller_supplied_analysis_hash_is_not_an_authority():
    from fmea_application.revision_assembler import GovernanceInputs

    with pytest.raises(TypeError, match="analysis_hash"):
        GovernanceInputs(
            workspace_id="ws-1",
            analysis_id="analysis-1",
            analysis_hash="a" * 64,
        )


def test_foreign_parent_workspace_and_analysis_cannot_be_assembled():
    foreign_parent = make_fmea_revision(
        revision_id="foreign-parent",
        workspace_id="ws-foreign",
        analysis_id="analysis-foreign",
    )
    with pytest.raises(ValueError, match="parent revision"):
        _inputs(parent_revision=foreign_parent)


def test_requested_parent_hash_is_a_required_exact_precondition():
    parent = make_fmea_revision(revision_id="parent-1")
    inputs = _inputs(parent_revision=parent)
    with pytest.raises(ValueError, match="parent revision hash"):
        make_governance_assembler(inputs).assemble(
            make_assemble_request(parent_revision_id=parent.revision_id, parent_revision_hash="b" * 64),
            inputs,
        )


def test_zero_artifact_hash_cannot_be_ready():
    from fmea_application.revision_assembler import PublicationReadinessPolicy

    revision = make_fmea_revision(domain_pack_identity=("domain", "1.0.0", "0" * 64))
    from fmea_governance_fixtures import make_domain_policy, make_readiness_context

    report = PublicationReadinessPolicy(make_domain_policy()).evaluate(
        revision,
        make_readiness_context(required_evidence_present=True),
    )
    assert report.ready is False


def test_row_phantom_evidence_reference_fails_closed(fixture_pack, fixture_row):
    from dataclasses import replace

    row = replace(
        _row(fixture_row, "row-phantom"),
        field_evidence=(("failure_mode", ("phantom-evidence",)),),
    )
    inputs = _inputs(rows=(row,), evidence_packs=(fixture_pack,))
    revision = make_governance_assembler(inputs).assemble(
        make_assemble_request(),
        inputs,
    )
    assert any(issue.code == "INVALID_EVIDENCE_REFERENCE" for issue in revision.unresolved_items)


def test_resolved_identity_rejects_zero_hash_and_unverified_identity():
    from fmea_application.revision_assembler import RegistryArtifactRecord

    with pytest.raises(ValueError):
        RegistryArtifactRecord("domain_pack", "domain", "1.0.0", "0" * 64, "0" * 64)


def test_registry_verified_bool_is_not_a_public_identity_proof():
    from fmea_application.revision_assembler import ResolvedArtifactIdentity

    with pytest.raises(TypeError):
        ResolvedArtifactIdentity("domain_pack", "domain", "1.0.0", "a" * 64, registry_verified=True)


def test_domain_artifact_identity_set_is_exact_not_a_subset():
    from fmea_governance_fixtures import _identity, make_governance_inputs

    from fmea_application.revision_assembler import GovernanceArtifactSet

    base = make_governance_inputs()
    with pytest.raises(ValueError, match="template"):
        GovernanceArtifactSet(
            domain_pack=base.domain_pack,
            domain_pack_identity=base.domain_pack_identity,
            template_identities=(),
            scoring_rule_identities=base.scoring_rule_identities,
            propagation_rule_identity=base.propagation_rule_identity,
        )
    extra = _identity("template", "extra-template", "1.0.0", "e" * 64)
    with pytest.raises(ValueError, match="template"):
        GovernanceArtifactSet(
            domain_pack=base.domain_pack,
            domain_pack_identity=base.domain_pack_identity,
            template_identities=(*base.template_identities, extra),
            scoring_rule_identities=base.scoring_rule_identities,
            propagation_rule_identity=base.propagation_rule_identity,
        )


def test_artifact_set_rejects_omitted_declared_propagation_identity():
    from fmea_governance_fixtures import make_governance_inputs

    from fmea_application.revision_assembler import GovernanceArtifactSet

    base = make_governance_inputs()
    with pytest.raises(ValueError, match="propagation rule identities"):
        GovernanceArtifactSet(
            domain_pack=base.domain_pack,
            domain_pack_identity=base.domain_pack_identity,
            template_identities=base.template_identities,
            scoring_rule_identities=base.scoring_rule_identities,
            propagation_rule_identity=None,
        )


def test_governance_inputs_rejects_missing_declared_propagation_identity_even_when_optional():
    from dataclasses import replace

    base = make_governance_inputs()
    with pytest.raises(ValueError, match="propagation rule identities"):
        replace(base, propagation_rule_identity=None)


def test_human_acknowledgement_reference_requires_human_and_exact_scope():
    from core_domain.fmea.states import ActorType
    from fmea_application.revision_assembler import HumanAcknowledgementReference

    with pytest.raises(TypeError):
        HumanAcknowledgementReference(
            decision_id="decision-1",
            workspace_id="ws-1",
            analysis_id="analysis-1",
            issue_code="BLOCKED",
            issue_source_type="row",
            issue_source_id="row-1",
            actor_id="model-1",
            actor_type=ActorType.MODEL,
            revision_id="revision-1",
            revision_record_version=1,
            evidence_ids=(),
        )


def test_human_acknowledgement_reference_cannot_be_forged_without_resolver_proof():
    from core_domain.fmea.states import ActorType
    from fmea_application.revision_assembler import HumanAcknowledgementReference

    with pytest.raises(TypeError):
        HumanAcknowledgementReference(
            decision_id="decision-1",
            workspace_id="ws-1",
            analysis_id="analysis-1",
            issue_code="BLOCKED",
            issue_source_type="row",
            issue_source_id="row-1",
            actor_id="reviewer-1",
            actor_type=ActorType.HUMAN,
            revision_id="revision-1",
            revision_record_version=1,
            evidence_ids=(),
        )


def test_risk_dimension_phantom_evidence_reference_fails_closed(fixture_pack, fixture_row):
    from core_domain.fmea.scoring import RiskAssessment, RiskAssessmentRecord, ScoreDimension
    from core_domain.fmea.states import RiskStatus

    dimensions = tuple(
        ScoreDimension(name, 1, ("phantom-risk-evidence",), "confirmed", None)
        for name in ("severity", "occurrence", "detection")
    )
    derived = RiskAssessment(
        severity_by_consequence_class=(("generic", 1),),
        decision_severity=1,
        occurrence=1,
        detection=1,
        rpn=1,
        decision_priority="normal",
        inherent_risk=1,
        current_risk=1,
        target_residual_risk=1,
        verified_residual_risk=1,
        uncertainty=None,
        reason="confirmed",
        scoring_rule_pack_id="generic-scoring",
        scoring_rule_pack_version="1.0.0",
        evidence_ids=("phantom-risk-evidence",),
    )
    risk = RiskAssessmentRecord(
        assessment_id="assessment-1",
        workspace_id="ws-1",
        row_id="row-1",
        source_record_version=1,
        evidence_pack_id=fixture_pack.pack_id,
        domain_pack_id="generic-domain",
        domain_pack_version="1.0.0",
        rule_pack_id="generic-scoring",
        rule_pack_version="1.0.0",
        status=RiskStatus.CONFIRMED,
        dimensions=dimensions,
        derived=derived,
        proposal_id="proposal-1",
        assistance_suggestion_id=None,
        confirmer_actor_id="reviewer-1",
        invalidated_reason=None,
        record_version=1,
        created_at="2026-08-23T00:00:00Z",
        updated_at="2026-08-23T00:00:00Z",
    )
    inputs = _inputs(rows=(_row(fixture_row, "row-1"),), evidence_packs=(fixture_pack,), risk_records=(risk,))
    revision = make_governance_assembler(inputs).assemble(
        make_assemble_request(),
        inputs,
    )
    assert any(
        issue.code == "INVALID_EVIDENCE_REFERENCE" and issue.source_type == "risk"
        for issue in revision.unresolved_items
    )


def test_graph_edge_phantom_evidence_reference_fails_closed(fixture_pack):
    from dataclasses import replace

    from fmea_governance_fixtures import _identity, make_governance_assembler
    from fmea_propagation_fixtures import _graph

    base = make_governance_inputs(evidence_packs=(fixture_pack,))
    domain = replace(
        base.domain_pack,
        pack_id="fuel-combustion",
        propagation_rule_identities=(("fuel-propagation", "1.0.0"),),
    )
    graph = _graph("ws-1")
    bad_edge = replace(graph.edges[0], evidence_ids=("phantom-graph-evidence",))
    bad_path = replace(graph.paths[0], edges=(bad_edge,))
    graph = replace(graph, edges=(bad_edge, graph.edges[1]), paths=(bad_path, graph.paths[1]))
    inputs = make_governance_inputs(
        domain_pack=domain,
        domain_pack_identity=_identity("domain_pack", "fuel-combustion", "1.0.0", "a" * 64),
        propagation_rule_identity=_identity("propagation_rule", "fuel-propagation", "1.0.0", "d" * 64),
        propagation_graph_revision=graph,
        evidence_packs=(fixture_pack,),
    )
    revision = make_governance_assembler(inputs).assemble(make_assemble_request(), inputs)
    assert any(
        issue.code == "INVALID_EVIDENCE_REFERENCE" and issue.source_type == "propagation_edge"
        for issue in revision.unresolved_items
    )


def test_expired_evidence_pack_is_not_publishable(fixture_pack, fixture_row):
    from dataclasses import replace

    expired_pack = replace(fixture_pack, expires_at="2026-08-30T00:00:00Z")
    inputs = _inputs(rows=(_row(fixture_row, "row-1"),), evidence_packs=(expired_pack,))
    revision = make_governance_assembler(inputs, clock=lambda: "2026-08-31T00:00:00Z").assemble(
        make_assemble_request(),
        inputs,
    )
    assert any(issue.code == "EXPIRED_EVIDENCE" for issue in revision.unresolved_items)
