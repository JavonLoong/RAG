from __future__ import annotations

import inspect
from dataclasses import replace

import pytest


def _implementation():
    try:
        from fmea_application.ports import GovernanceRepositoryProviders
        from fmea_infrastructure.composition import RepositoryGovernanceSource
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"Task 2 server-owned source adapter is missing: {exc}")
    return GovernanceRepositoryProviders, RepositoryGovernanceSource


def test_source_adapter_is_typed_and_has_no_callable_loader_seam():
    GovernanceRepositoryProviders, RepositoryGovernanceSource = _implementation()
    assert "loader" not in inspect.signature(RepositoryGovernanceSource).parameters
    assert "providers" in inspect.signature(RepositoryGovernanceSource).parameters
    assert GovernanceRepositoryProviders is not None


def test_source_adapter_load_inputs_only_accepts_server_scope():
    _, RepositoryGovernanceSource = _implementation()
    with pytest.raises(TypeError):
        RepositoryGovernanceSource(object()).load_inputs(
            "analysis-1",
            "ws-1",
            rows=(),
            evidence_packs=(),
        )


def test_valid_source_rejects_client_state_overrides_at_load_boundary():
    from fmea_governance_fixtures import make_governance_inputs

    base = make_governance_inputs()
    source = _source(base)
    with pytest.raises(TypeError):
        source.load_inputs(
            "analysis-1",
            "ws-1",
            rows=(),
            evidence_packs=(),
            domain_pack=base.domain_pack,
            active_run_ids=(),
        )


def test_analysis_query_port_requires_scoped_resolved_analysis_record():
    from fmea_application.revision_assembler import ResolvedAnalysisRecord

    assert ResolvedAnalysisRecord is not None


def test_retrieval_provenance_is_a_server_query_port():
    from fmea_application.ports import RetrievalProvenanceQueryPort

    assert RetrievalProvenanceQueryPort is not None


def test_client_cannot_override_registry_identity_or_active_run_state():
    GovernanceRepositoryProviders, RepositoryGovernanceSource = _implementation()
    assert "domain_pack" not in inspect.signature(RepositoryGovernanceSource.load_inputs).parameters
    assert "active_run_ids" not in inspect.signature(RepositoryGovernanceSource.load_inputs).parameters
    assert "domain_pack" not in inspect.signature(GovernanceRepositoryProviders).parameters


class _AnalysisProvider:
    def __init__(self, analysis):
        self.analysis = analysis

    def get_analysis(self, _analysis_id, _workspace_id):
        return self.analysis


class _ReviewProvider:
    def __init__(self, rows=()):
        self.rows = rows

    def list_rows(self, _analysis_id, _workspace_id):
        return self.rows


class _RiskProvider:
    def __init__(self, records=()):
        self.records = records

    def list_risk_records(self, _analysis_id, _workspace_id):
        return self.records


class _PropagationProvider:
    def __init__(self, graph=None):
        self.graph = graph

    def get_current_graph(self, _analysis_id, _workspace_id):
        return self.graph


class _EvidenceProvider:
    def __init__(self, packs=()):
        self.packs = packs

    def list_evidence_packs(self, _analysis_id, _workspace_id):
        return self.packs


class _ArtifactProvider:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    def get_artifacts(self, _analysis_id, _workspace_id, _analysis):
        return self.artifacts


class _RunProvider:
    def __init__(self, run_ids=()):
        self.run_ids = run_ids

    def list_active_run_ids(self, _analysis_id, _workspace_id):
        return self.run_ids


class _AcknowledgementProvider:
    def __init__(self, references=()):
        self.references = references

    def list_human_acknowledgements(self, _analysis_id, _workspace_id):
        return self.references


class _RetrievalProvider:
    def __init__(self, provenance):
        self.provenance = provenance

    def get_provenance(self, _analysis_id, _workspace_id):
        return self.provenance


def _source(
    base,
    *,
    analysis=None,
    rows=(),
    risk_records=(),
    graph=None,
    packs=(),
    run_ids=(),
    acknowledgements=(),
    provenance=None,
):
    GovernanceRepositoryProviders, RepositoryGovernanceSource = _implementation()
    providers = GovernanceRepositoryProviders(
        analysis=_AnalysisProvider(analysis or base.analysis),
        review=_ReviewProvider(rows),
        risk=_RiskProvider(risk_records),
        propagation=_PropagationProvider(graph),
        evidence=_EvidenceProvider(packs),
        artifacts=_ArtifactProvider(
            __import__("fmea_application.revision_assembler", fromlist=["GovernanceArtifactSet"]).GovernanceArtifactSet(
                domain_pack=base.domain_pack,
                domain_pack_identity=base.domain_pack_identity,
                template_identities=base.template_identities,
                scoring_rule_identities=base.scoring_rule_identities,
                propagation_rule_identity=base.propagation_rule_identity,
            )
        ),
        runs=_RunProvider(run_ids),
        acknowledgements=_AcknowledgementProvider(acknowledgements),
        retrieval=_RetrievalProvider(provenance or base.retrieval_provenance),
    )
    return RepositoryGovernanceSource(providers)


def test_source_reads_active_runs_server_side_and_returns_typed_inputs():
    from fmea_governance_fixtures import make_governance_inputs

    from fmea_application.revision_assembler import GovernanceInputs

    base = make_governance_inputs()
    inputs = _source(base, run_ids=("run-1",)).load_inputs("analysis-1", "ws-1")
    assert isinstance(inputs, GovernanceInputs)
    assert inputs.active_run_ids == ("run-1",)


def test_source_rejects_provider_records_from_a_mixed_analysis_scope(fixture_row):
    from fmea_governance_fixtures import make_governance_inputs

    base = make_governance_inputs()
    foreign_row = replace(fixture_row, analysis_id="analysis-foreign")
    with pytest.raises(ValueError, match="analysis"):
        _source(base, rows=(foreign_row,)).load_inputs("analysis-1", "ws-1")


def test_source_rejects_same_analysis_id_with_foreign_analysis_workspace():
    from fmea_governance_fixtures import make_governance_inputs

    from fmea_application.revision_assembler import _resolve_analysis_record

    base = make_governance_inputs()
    foreign_analysis = _resolve_analysis_record("ws-foreign", base.analysis.analysis)
    with pytest.raises(ValueError, match="workspace"):
        _source(base, analysis=foreign_analysis).load_inputs("analysis-1", "ws-1")


def test_scoped_analysis_record_cannot_be_forged_with_only_hashes():
    from fmea_governance_fixtures import make_governance_inputs

    from fmea_application.revision_assembler import ResolvedAnalysisRecord

    base = make_governance_inputs()
    with pytest.raises(TypeError, match="attestation"):
        ResolvedAnalysisRecord(
            "ws-1",
            base.analysis.analysis,
            1,
            "a" * 64,
            "a" * 64,
        )


def test_source_rejects_foreign_acknowledgement_scope():
    from fmea_governance_fixtures import make_governance_acknowledgement_record, make_governance_inputs

    base = make_governance_inputs()
    reference = make_governance_acknowledgement_record(
        workspace_id="ws-foreign",
        analysis_id="analysis-1",
        issue_code="BLOCKED",
        issue_source_type="row",
        issue_source_id="row-1",
        evidence_ids=(),
    )
    with pytest.raises(ValueError, match="scope"):
        _source(base, acknowledgements=(reference,)).load_inputs("analysis-1", "ws-1")


@pytest.mark.parametrize(
    "record_overrides",
    (
        {"status": "rejected"},
        {"decision_hash": "b" * 64},
    ),
)
def test_source_does_not_resolve_unaccepted_or_unbound_acknowledgement_records(record_overrides):
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_acknowledgement_record, make_governance_inputs

    base = make_governance_inputs()
    record = make_governance_acknowledgement_record(**{
        key: value for key, value in record_overrides.items() if key != "decision_hash"
    })
    if "decision_hash" in record_overrides:
        record = replace(record, decision_hash=record_overrides["decision_hash"])
    with pytest.raises(ValueError):
        _source(base, acknowledgements=(record,)).load_inputs("analysis-1", "ws-1")


def test_source_rejects_acknowledgement_version_tampering():
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_acknowledgement_record, make_governance_inputs

    base = make_governance_inputs()
    record = make_governance_acknowledgement_record()
    tampered = replace(record, decision_record_version=record.decision_record_version + 1)
    with pytest.raises(ValueError, match="hash"):
        _source(base, acknowledgements=(tampered,)).load_inputs("analysis-1", "ws-1")


def test_source_preserves_server_retrieval_provenance_without_defaulting_to_combined():
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_inputs

    base = make_governance_inputs()
    provenance = replace(
        base.retrieval_provenance,
        requested_profile="graphrag_only",
        resolved_profile="graphrag_only",
        evidence_types=("graph", "community"),
    )
    inputs = _source(base, provenance=provenance).load_inputs("analysis-1", "ws-1")
    assert inputs.requested_profile == "graphrag_only"
    assert inputs.evidence_types == ("community", "graph")


def test_source_rejects_foreign_retrieval_provenance_scope():
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_inputs

    base = make_governance_inputs()
    provenance = replace(base.retrieval_provenance, workspace_id="ws-foreign")
    with pytest.raises(ValueError, match="scope"):
        _source(base, provenance=provenance).load_inputs("analysis-1", "ws-1")


@pytest.mark.parametrize(
    "provenance_overrides",
    (
        {"requested_profile": "unknown-profile"},
        {"warnings": ("https://private.example/secret",)},
        {"warnings": tuple(f"warning-{index}" for index in range(65))},
    ),
)
def test_retrieval_provenance_rejects_unknown_or_unsafe_provider_values(provenance_overrides):
    from fmea_application.revision_assembler import GovernanceRetrievalProvenance

    values = {
        "workspace_id": "ws-1",
        "analysis_id": "analysis-1",
        "requested_profile": "combined",
        "resolved_profile": "combined",
        "evidence_types": ("text",),
        "source_counts": (("text", 1),),
        "warnings": (),
    }
    values.update(provenance_overrides)
    with pytest.raises(ValueError):
        GovernanceRetrievalProvenance(**values)


def test_source_rejects_mixed_risk_graph_and_evidence_scopes(fixture_pack):
    from dataclasses import replace

    from fmea_governance_fixtures import make_governance_inputs
    from fmea_propagation_fixtures import _graph

    from core_domain.fmea.scoring import RiskAssessmentRecord
    from core_domain.fmea.states import RiskStatus

    base = make_governance_inputs()
    foreign_risk = RiskAssessmentRecord(
        assessment_id="assessment-1",
        workspace_id="ws-foreign",
        row_id="row-1",
        source_record_version=1,
        evidence_pack_id="pack-1",
        domain_pack_id="generic-domain",
        domain_pack_version="1.0.0",
        rule_pack_id="generic-scoring",
        rule_pack_version="1.0.0",
        status=RiskStatus.PROPOSED,
        dimensions=(),
        derived=None,
        proposal_id="proposal-1",
        assistance_suggestion_id=None,
        confirmer_actor_id=None,
        invalidated_reason=None,
        record_version=1,
        created_at="2026-08-30T00:00:00Z",
        updated_at="2026-08-30T00:00:00Z",
    )
    with pytest.raises(ValueError, match="workspace"):
        _source(base, risk_records=(foreign_risk,)).load_inputs("analysis-1", "ws-1")

    foreign_pack = replace(fixture_pack, workspace_id="ws-foreign")
    with pytest.raises(ValueError, match="workspace"):
        _source(base, packs=(foreign_pack,)).load_inputs("analysis-1", "ws-1")

    foreign_graph = replace(_graph("ws-1"), workspace_id="ws-foreign")
    with pytest.raises(ValueError, match="workspace"):
        _source(base, graph=foreign_graph).load_inputs("analysis-1", "ws-1")


def test_registry_adapter_rejects_registry_manifest_hash_mismatch():
    from fmea_governance_fixtures import make_governance_inputs

    from fmea_infrastructure.composition import RegistryGovernanceArtifactProvider

    base = make_governance_inputs()

    class BadDomainRegistry:
        def get(self, _pack_id, _version):
            return replace(base.domain_pack, content_hash="b" * 64)

    with pytest.raises(ValueError, match="domain pack registry"):
        RegistryGovernanceArtifactProvider(
            domain_pack=base.domain_pack,
            domain_pack_registry=BadDomainRegistry(),
            template_registry=object(),
            scoring_rule_registry=object(),
            propagation_rule_registry=object(),
        ).get_artifacts("analysis-1", "ws-1", base.analysis)
