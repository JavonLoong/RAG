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


def _source(base, *, rows=(), risk_records=(), graph=None, packs=(), run_ids=(), acknowledgements=()):
    GovernanceRepositoryProviders, RepositoryGovernanceSource = _implementation()
    providers = GovernanceRepositoryProviders(
        analysis=_AnalysisProvider(base.analysis),
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


def test_source_rejects_foreign_acknowledgement_scope():
    from fmea_governance_fixtures import make_governance_inputs

    from core_domain.fmea.states import ActorType
    from fmea_application.revision_assembler import HumanAcknowledgementReference

    base = make_governance_inputs()
    reference = HumanAcknowledgementReference(
        decision_id="decision-1",
        workspace_id="ws-foreign",
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
    with pytest.raises(ValueError, match="scope"):
        _source(base, acknowledgements=(reference,)).load_inputs("analysis-1", "ws-1")


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
